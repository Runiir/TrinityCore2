from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.raid_program.capture_checkpoint_controller import (
    native_path_checkpoint_arm_command,
)
from tools.raid_program import recurrence_admission


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"


def _requests() -> list[dict[str, object]]:
    return [
        {
            "fixture_id": fixture_id,
            "from_revision": revisions[0],
            "to_revision": revisions[1],
            "causal_signature": f"{fixture_id}_cause",
            "required_production_boundary": f"{fixture_id}_boundary",
        }
        for fixture_id, revisions in
        recurrence_admission.NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS.items()
    ]


def test_compiled_cases_are_enumerated_and_fail_closed(tmp_path: Path) -> None:
    source = tmp_path / "native_path_checkpoint.cpp"
    binary = tmp_path / "native_path_checkpoint"
    source.write_text(
        r'''
#include "Bots/BotNativePathCheckpoint.h"
#include <cassert>

int main()
{
    using namespace BotNativePathCheckpoint;
    static_assert(Cases.size() == 5);
    assert(FindCase("a842_receipt519_complete_wrong_floor") != nullptr);
    assert(FindCase("a506_receipt636_incomplete_same_floor") != nullptr);
    assert(FindCase("unsealed_case") == nullptr);
    State state;
    assert(!state.Arm("unsealed_case", 30006, 1));
    State actorMismatch;
    assert(!actorMismatch.Arm(
        "a842_receipt519_complete_wrong_floor", 30007, 1));
    State exact;
    assert(exact.Arm(
        "a842_receipt519_complete_wrong_floor", 30006, 1));
    assert(exact.CurrentStage == Stage::Armed);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "src/common"),
            "-I", str(ROOT / "src/server/game"),
            str(source), "-o", str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_controller_emits_only_sealed_case_and_no_coordinates() -> None:
    case_id = "a506_receipt636_incomplete_same_floor"
    admission = {
        "valid": True,
        "purpose": recurrence_admission.FIXTURE_EXPANSION_PURPOSE,
        "fixture_expansion_target_ids": [
            recurrence_admission.NATIVE_PATH_CHECKPOINT_FIXTURE_ID,
            *recurrence_admission.NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS,
        ],
        "fixture_expansion_requests": _requests(),
        "checkpoint_fixture_id": (
            recurrence_admission.NATIVE_PATH_CHECKPOINT_FIXTURE_ID
        ),
        "checkpoint_case_id": case_id,
        "checkpoint_seal_sha256": "a" * 64,
        "source_commit": "b" * 40,
    }
    command = native_path_checkpoint_arm_command(admission, 30007)
    assert command == (
        "botautonativepathcheckpoint arm 30007 "
        f"{case_id} {'a' * 64} {'b' * 40}"
    )
    assert "-302." not in command
    admission["checkpoint_case_id"] = ""
    with pytest.raises(ValueError, match="verified_admission_invalid"):
        native_path_checkpoint_arm_command(admission, 30007)


def test_seal_binds_case_and_exact_pending_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    files = {
        name: tmp_path / name
        for name in ("binary", "build.json", "decision.json", "profiles.json")
    }
    files["binary"].write_bytes(b"elf")
    files["build.json"].write_text("{}", encoding="utf-8")
    decision = {
        "fixture_expansion_target_ids": [
            recurrence_admission.NATIVE_PATH_CHECKPOINT_FIXTURE_ID,
            *recurrence_admission.NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS,
        ],
        "pending_fixture_ids": [
            recurrence_admission.NATIVE_PATH_CHECKPOINT_FIXTURE_ID,
        ],
        "fixture_expansion_requests": _requests(),
    }
    import json
    files["decision.json"].write_text(json.dumps(decision), encoding="utf-8")
    files["profiles.json"].write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        recurrence_admission,
        "_git",
        lambda _worktree, *args, **_kwargs: (
            "1" * 40 if args[-1] == "HEAD" else "2" * 40
        ),
    )
    kwargs = dict(
        worktree=tmp_path,
        binary=files["binary"],
        build_receipt=files["build.json"],
        decision=files["decision.json"],
        profile_manifest=files["profiles.json"],
        runtime_profile_overlay={"profile": "map669"},
        expected_runtime_profile_id="map669",
    )
    first = recurrence_admission.native_path_checkpoint_seal(
        case_id="a506_receipt636_incomplete_same_floor", **kwargs,
    )
    second = recurrence_admission.native_path_checkpoint_seal(
        case_id="a842_receipt519_complete_wrong_floor", **kwargs,
    )
    assert first["seal_sha256"] != second["seal_sha256"]
    decision["fixture_expansion_requests"][0]["to_revision"] += 1
    files["decision.json"].write_text(json.dumps(decision), encoding="utf-8")
    with pytest.raises(
        recurrence_admission.RecurrenceAdmissionError,
        match="request_invalid",
    ):
        recurrence_admission.native_path_checkpoint_seal(
            case_id="a506_receipt636_incomplete_same_floor", **kwargs,
        )


def test_production_callback_order_and_exact_executor_wiring() -> None:
    update = (BOT_DIR / "BotWorldPopulationMgrUpdateBot.cpp").read_text()
    module = (
        BOT_DIR / "BotWorldPopulationMgrNativePathCheckpoint.cpp"
    ).read_text()
    assert update.index("ObserveReceiptTaggedMovementProgress") < update.index(
        "ObserveNativePathCheckpointBeforeUpdate"
    )
    assert module.count("ExecuteMovementIntent(state, bot, intent)") == 2
    assert "Owner::Formation" in module
    assert "Owner::Hazard" in module
    assert "StageTerminalIsExact(progress, bot, *selected)" in module
    assert module.index("StageTerminalIsExact(progress, bot, *selected)") < (
        module.index("bool const launched = ExecuteMovementIntent")
    )
