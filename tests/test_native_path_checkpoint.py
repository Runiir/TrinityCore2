from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tools.raid_program.capture_checkpoint_controller import (
    checkpoint_controller_dialect,
    native_path_checkpoint_arm_command,
)
from tools.raid_program.controller_route_hold import (
    ControllerRouteHoldLaunchIdentity,
    ControllerRouteHoldScheduler,
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


def _seal_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict[str, object], Path, dict[str, object]]:
    files = {
        name: tmp_path / name
        for name in ("binary", "build.json", "decision.json", "profiles.json")
    }
    files["binary"].write_bytes(b"elf")
    files["build.json"].write_text("{}", encoding="utf-8")
    decision = {
        "fixture_expansion_target_ids": list(
            recurrence_admission.NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS
        ),
        "pending_fixture_ids": list(
            recurrence_admission.NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS
        ),
        "fixture_expansion_requests": _requests(),
    }
    files["decision.json"].write_text(json.dumps(decision), encoding="utf-8")
    files["profiles.json"].write_text("{}", encoding="utf-8")
    monkeypatch.setattr(
        recurrence_admission,
        "_git",
        lambda _worktree, *args, **_kwargs: (
            "1" * 40 if args[-1] == "HEAD" else "2" * 40
        ),
    )
    kwargs = {
        "worktree": tmp_path,
        "binary": files["binary"],
        "build_receipt": files["build.json"],
        "decision": files["decision.json"],
        "profile_manifest": files["profiles.json"],
        "runtime_profile_overlay": {"profile": "map669"},
        "expected_runtime_profile_id": "map669",
    }
    return decision, files["decision.json"], kwargs


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
            *recurrence_admission.NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS,
        ],
        "fixture_expansion_requests": _requests(),
        "pending_fixture_ids": [
            *recurrence_admission.NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS,
        ],
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


def _native_admission(
    case_id: str = "a842_receipt519_complete_wrong_floor",
) -> dict[str, object]:
    return {
        "valid": True,
        "purpose": recurrence_admission.FIXTURE_EXPANSION_PURPOSE,
        "fixture_expansion_target_ids": list(
            recurrence_admission.NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS
        ),
        "fixture_expansion_requests": _requests(),
        "pending_fixture_ids": list(
            recurrence_admission.NATIVE_PATH_CHECKPOINT_REQUIRED_REQUESTS
        ),
        "checkpoint_fixture_id": (
            recurrence_admission.NATIVE_PATH_CHECKPOINT_FIXTURE_ID
        ),
        "checkpoint_case_id": case_id,
        "checkpoint_seal_sha256": "a" * 64,
        "source_commit": "b" * 40,
    }


def _native_identity() -> ControllerRouteHoldLaunchIdentity:
    return ControllerRouteHoldLaunchIdentity(
        scenario_id="blackwing_descent_10n_magmaw_diagnostic",
        runtime_profile="blackwing_descent_10n_magmaw_diagnostic",
        pool_tag="blackwing_descent_10n_magmaw_diagnostic",
        route_manifest_sha256="c" * 64,
        route_node_id="bwd.magmaw.chainwielder",
        actor_guid=30006,
        fixture_id=recurrence_admission.NATIVE_PATH_CHECKPOINT_FIXTURE_ID,
        seal_sha256="a" * 64,
        source_commit="b" * 40,
    )


def _native_hold(
    *, phase: str = "held", generation: int = 1,
    native_stage: str = "disabled",
) -> dict[str, object]:
    identity = _native_identity()
    terminal = phase == "checkpoint_terminal"
    submitted = native_stage == "completed"
    lifecycle = {
        "stage": native_stage,
        "terminal": terminal,
        "case_id": "a842_receipt519_complete_wrong_floor",
        "stage_submit_count": 1 if submitted else 0,
        "hazard_submit_count": 1 if submitted else 0,
        "stage_receipt_id": 41 if submitted else 0,
        "hazard_receipt_id": 42 if submitted else 0,
        "outcome": (
            "native_path_checkpoint_no_launch_verified"
            if terminal else "native_path_checkpoint_armed"
            if native_stage == "armed" else "disabled"
        ),
    }
    return {
        "ok": True,
        "phase": phase,
        "cohort_id": "default",
        "server_epoch": 71,
        "attempt_id": 9,
        "scenario_id": identity.scenario_id,
        "runtime_profile": identity.runtime_profile,
        "route_manifest_sha256": identity.route_manifest_sha256,
        "route_generation": generation,
        "route_node_id": identity.route_node_id,
        "actor_guid": identity.actor_guid,
        "fixture_id": identity.fixture_id,
        "seal_sha256": identity.seal_sha256,
        "source_commit": identity.source_commit,
        "acquire_count": 1,
        "arm_ack_count": 1 if phase not in {"held", "released"} else 0,
        "release_count": 1 if phase == "released" else 0,
        "checkpoint_stage": "completed" if terminal else "disabled",
        "checkpoint_terminal": terminal,
        "checkpoint_identity_preserved": terminal,
        "checkpoint_lifecycle": lifecycle,
        "failure_reason": None,
    }


def _native_status(
    *, phase: str = "held", generation: int = 1,
    native_stage: str = "disabled",
) -> dict[str, object]:
    hold = _native_hold(
        phase=phase, generation=generation,
        native_stage=native_stage,
    )
    return {
        "ok": True,
        "action": "botauto_status",
        "active_profile": _native_identity().runtime_profile,
        "raid_runtime": {
            "active": True,
            "server_epoch": 71,
            "attempt_id": 9,
            "route_progress": {"generation": generation},
            "controller_route_hold": hold,
        },
        "validation_route": {"generation": generation},
    }


def _native_checkpoint_row(
    *, phase: str, native_stage: str,
    action: str = "botauto_native_path_checkpoint",
    case_id: str = "a842_receipt519_complete_wrong_floor",
) -> dict[str, object]:
    hold = _native_hold(phase=phase, native_stage=native_stage)
    lifecycle = hold["checkpoint_lifecycle"]
    return {
        "ok": True,
        "action": action,
        "authority": "sealed_compiled_map669_native_path_observation_only",
        "actor_guid": 30006,
        "fixture_id": recurrence_admission.NATIVE_PATH_CHECKPOINT_FIXTURE_ID,
        "case_id": case_id,
        **{
            field: lifecycle[field]
            for field in (
                "stage", "terminal", "stage_submit_count",
                "hazard_submit_count", "stage_receipt_id",
                "hazard_receipt_id", "outcome",
            )
        },
        "controller_route_hold": hold,
    }


def _native_failed_terminal_row(
    *,
    outcome: str = "native_path_checkpoint_stage_submit_failed",
    stage_submit_count: int = 1,
    hazard_submit_count: int = 0,
    stage_receipt_id: int = 0,
    hazard_receipt_id: int = 0,
) -> dict[str, object]:
    row = _native_checkpoint_row(
        phase="checkpoint_terminal", native_stage="failed",
    )
    lifecycle = row["controller_route_hold"]["checkpoint_lifecycle"]
    row["controller_route_hold"]["checkpoint_stage"] = "failed"
    lifecycle.update({
        "stage": "failed",
        "terminal": True,
        "stage_submit_count": stage_submit_count,
        "hazard_submit_count": hazard_submit_count,
        "stage_receipt_id": stage_receipt_id,
        "hazard_receipt_id": hazard_receipt_id,
        "outcome": outcome,
    })
    row.update({
        "ok": False,
        "stage": "failed",
        "terminal": True,
        "stage_submit_count": stage_submit_count,
        "hazard_submit_count": hazard_submit_count,
        "stage_receipt_id": stage_receipt_id,
        "hazard_receipt_id": hazard_receipt_id,
        "outcome": outcome,
        "movement_planner": {
            "available": True,
            "request": {"map": 669, "z": 210.098007},
            "target_floor": {"sampled": True, "z": -106.245819},
            "z_delta": {"available": True, "absolute": 316.343811},
            "planner": {
                "gate": "target_z_transition",
                "result": "rejected",
                "reason": "route_destination_invalid_z_transition",
            },
        },
    })
    return row


def _native_scheduler() -> ControllerRouteHoldScheduler:
    dialect = checkpoint_controller_dialect(_native_admission(), 30006)
    assert isinstance(dialect, dict)
    return ControllerRouteHoldScheduler(
        _native_identity(), **dialect["scheduler_kwargs"],
    )


def test_native_scheduler_exact_held_arm_terminal_no_release_transcript() -> None:
    scheduler = _native_scheduler()
    assert scheduler.start() == [
        "botautochaincheckpoint start-held 30006 "
        f"{recurrence_admission.NATIVE_PATH_CHECKPOINT_FIXTURE_ID} "
        f"{'a' * 64} {'b' * 40}"
    ]
    assert scheduler.observe(_native_hold()) == ["botauto status"]
    assert scheduler.observe(_native_status()) == ["botauto status"]
    assert scheduler.observe(_native_status()) == [
        "botautonativepathcheckpoint arm 30006 "
        f"a842_receipt519_complete_wrong_floor {'a' * 64} {'b' * 40}"
    ]
    assert scheduler.observe(_native_checkpoint_row(
        phase="armed", native_stage="armed",
    )) == ["botautonativepathcheckpoint status"]
    assert scheduler.observe(_native_checkpoint_row(
        phase="armed", native_stage="armed",
    )) == ["botautonativepathcheckpoint status"]
    assert scheduler.observe(_native_checkpoint_row(
        phase="checkpoint_terminal", native_stage="completed",
    )) == []
    receipt = scheduler.receipt()
    assert receipt["gate_passed"] is True
    assert receipt["command_transcript"] == [
        "botautochaincheckpoint start-held 30006 "
        f"{recurrence_admission.NATIVE_PATH_CHECKPOINT_FIXTURE_ID} "
        f"{'a' * 64} {'b' * 40}",
        "botauto status",
        "botauto status",
        "botautonativepathcheckpoint arm 30006 "
        f"a842_receipt519_complete_wrong_floor {'a' * 64} {'b' * 40}",
        "botautonativepathcheckpoint status",
        "botautonativepathcheckpoint status",
    ]
    assert receipt["command_counts"]["release"] == 0
    assert receipt["release_ack_count"] == 0
    assert receipt["native_scope"]["route_generation"] == 1


def test_native_scheduler_records_truthful_failed_terminal_without_gate_pass() -> None:
    scheduler = _native_scheduler()
    scheduler.start()
    scheduler.observe(_native_hold())
    scheduler.observe(_native_status())
    scheduler.observe(_native_status())
    scheduler.observe(_native_checkpoint_row(
        phase="armed", native_stage="armed",
    ))

    assert scheduler.observe(_native_failed_terminal_row()) == []
    assert scheduler.complete is True
    assert scheduler.failed is False
    assert scheduler.failure_reason is None
    receipt = scheduler.receipt()
    assert receipt["phase"] == "checkpoint_terminal_failed"
    assert receipt["gate_passed"] is False
    assert receipt["checkpoint_terminal_count"] == 1
    assert receipt["checkpoint_terminal_stage"] == "failed"
    assert receipt["checkpoint_terminal_lifecycle"]["outcome"] == (
        "native_path_checkpoint_stage_submit_failed"
    )
    observation = receipt["checkpoint_terminal_observation"]
    assert observation["outcome"] == "native_path_checkpoint_stage_submit_failed"
    assert observation["movement_planner"]["planner"] == {
        "gate": "target_z_transition",
        "result": "rejected",
        "reason": "route_destination_invalid_z_transition",
    }


@pytest.mark.parametrize(
    ("outcome", "shape"),
    [
        ("native_path_checkpoint_scope_or_timeout", (0, 0, 0, 0)),
        ("native_path_checkpoint_stage_submit_failed", (1, 0, 0, 0)),
        ("native_path_checkpoint_stage_receipt_missing", (1, 0, 0, 0)),
        ("native_path_checkpoint_stage_identity_failed", (1, 0, 41, 0)),
        ("native_path_checkpoint_hazard_identity_failed", (1, 1, 41, 0)),
        ("native_path_checkpoint_outcome_mismatch", (1, 1, 41, 42)),
        ("native_path_checkpoint_launch_progress_failed", (1, 1, 41, 42)),
    ],
)
def test_native_scheduler_accepts_only_native_failure_state_shapes(
    outcome: str, shape: tuple[int, int, int, int],
) -> None:
    scheduler = _native_scheduler()
    scheduler.start()
    scheduler.observe(_native_hold())
    scheduler.observe(_native_status())
    scheduler.observe(_native_status())
    scheduler.observe(_native_checkpoint_row(
        phase="armed", native_stage="armed",
    ))
    row = _native_failed_terminal_row(
        outcome=outcome,
        stage_submit_count=shape[0],
        hazard_submit_count=shape[1],
        stage_receipt_id=shape[2],
        hazard_receipt_id=shape[3],
    )

    scheduler.observe(row)
    assert scheduler.complete is True
    assert scheduler.failed is False
    receipt = scheduler.receipt()
    assert receipt["gate_passed"] is False
    assert receipt["checkpoint_terminal_lifecycle"]["outcome"] == outcome


@pytest.mark.parametrize(
    ("outcome", "impossible_shape"),
    [
        ("native_path_checkpoint_scope_or_timeout", (1, 0, 0, 0)),
        ("native_path_checkpoint_stage_submit_failed", (1, 0, 41, 0)),
        ("native_path_checkpoint_stage_receipt_missing", (1, 1, 41, 42)),
        ("native_path_checkpoint_stage_identity_failed", (1, 0, 0, 0)),
        ("native_path_checkpoint_hazard_identity_failed", (1, 0, 41, 0)),
        ("native_path_checkpoint_outcome_mismatch", (1, 1, 41, 0)),
        ("native_path_checkpoint_launch_progress_failed", (1, 1, 0, 42)),
    ],
)
def test_native_scheduler_rejects_impossible_failure_state_shapes(
    outcome: str, impossible_shape: tuple[int, int, int, int],
) -> None:
    scheduler = _native_scheduler()
    scheduler.start()
    scheduler.observe(_native_hold())
    scheduler.observe(_native_status())
    scheduler.observe(_native_status())
    scheduler.observe(_native_checkpoint_row(
        phase="armed", native_stage="armed",
    ))
    row = _native_failed_terminal_row(
        outcome=outcome,
        stage_submit_count=impossible_shape[0],
        hazard_submit_count=impossible_shape[1],
        stage_receipt_id=impossible_shape[2],
        hazard_receipt_id=impossible_shape[3],
    )

    scheduler.observe(row)
    assert scheduler.failed is True
    assert scheduler.failure_reason == (
        "controller_route_hold_checkpoint_lifecycle_invalid"
    )


def test_native_scheduler_rejects_unknown_failed_outcome() -> None:
    scheduler = _native_scheduler()
    scheduler.start()
    scheduler.observe(_native_hold())
    scheduler.observe(_native_status())
    scheduler.observe(_native_status())
    scheduler.observe(_native_checkpoint_row(
        phase="armed", native_stage="armed",
    ))

    scheduler.observe(_native_failed_terminal_row(
        outcome="native_path_checkpoint_unknown_failure",
    ))
    assert scheduler.failed is True
    assert scheduler.failure_reason == (
        "controller_route_hold_checkpoint_lifecycle_invalid"
    )


def test_native_scheduler_rejects_false_armed_row_instead_of_polling() -> None:
    scheduler = _native_scheduler()
    scheduler.start()
    scheduler.observe(_native_hold())
    scheduler.observe(_native_status())
    scheduler.observe(_native_status())
    scheduler.observe(_native_checkpoint_row(
        phase="armed", native_stage="armed",
    ))
    row = _native_checkpoint_row(phase="armed", native_stage="armed")
    row["ok"] = False

    assert scheduler.observe(row) == []
    assert scheduler.failed is True
    assert scheduler.failure_reason == (
        "controller_route_hold_checkpoint_lifecycle_invalid"
    )


@pytest.mark.parametrize(
    ("mutation", "field"),
    [
        ("authority", "authority"),
        ("actor", "actor_guid"),
        ("fixture", "fixture_id"),
        ("receipt", "case_id"),
        ("mirror", "outcome"),
    ],
)
def test_native_failed_terminal_still_rejects_identity_drift(
    mutation: str, field: str,
) -> None:
    scheduler = _native_scheduler()
    scheduler.start()
    scheduler.observe(_native_hold())
    scheduler.observe(_native_status())
    scheduler.observe(_native_status())
    scheduler.observe(_native_checkpoint_row(
        phase="armed", native_stage="armed",
    ))
    row = _native_failed_terminal_row()
    if mutation == "authority":
        row[field] = "wrong_authority"
    elif mutation == "actor":
        row[field] = 30007
    elif mutation == "fixture":
        row[field] = "wrong_fixture"
    elif mutation == "receipt":
        row[field] = "wrong_case"
    else:
        row[field] = "native_path_checkpoint_scope_or_timeout"

    scheduler.observe(row)
    assert scheduler.failed is True
    assert scheduler.failure_reason == (
        "controller_route_hold_checkpoint_receipt_identity_invalid"
    )


def test_native_failed_terminal_rejects_missing_planner_reason() -> None:
    scheduler = _native_scheduler()
    scheduler.start()
    scheduler.observe(_native_hold())
    scheduler.observe(_native_status())
    scheduler.observe(_native_status())
    scheduler.observe(_native_checkpoint_row(
        phase="armed", native_stage="armed",
    ))
    row = _native_failed_terminal_row()
    row["movement_planner"]["planner"]["reason"] = ""

    scheduler.observe(row)
    assert scheduler.failed is True
    assert scheduler.failure_reason == (
        "controller_route_hold_checkpoint_planner_missing"
    )


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("action", "controller_route_hold_arm_ack_missing"),
        (
            "fixture",
            "controller_route_hold_checkpoint_receipt_identity_invalid",
        ),
        ("case", "controller_route_hold_checkpoint_receipt_identity_invalid"),
    ],
)
def test_native_scheduler_rejects_wrong_action_fixture_or_case(
    mutation: str, reason: str,
) -> None:
    scheduler = _native_scheduler()
    scheduler.start()
    scheduler.observe(_native_hold())
    scheduler.observe(_native_status())
    scheduler.observe(_native_status())
    row = _native_checkpoint_row(
        phase="armed", native_stage="armed",
    )
    if mutation == "action":
        row["action"] = "botauto_chainwielder_checkpoint"
        scheduler.observe(row)
        scheduler.finish()
    elif mutation == "fixture":
        row["fixture_id"] = "wrong_fixture"
        scheduler.observe(row)
    else:
        row["case_id"] = "a842_receipt551_complete_wrong_floor"
        scheduler.observe(row)
    assert scheduler.failure_reason == reason


@pytest.mark.parametrize("field", ["actor_guid", "fixture_id", "case_id"])
def test_native_scheduler_rejects_terminal_row_identity_drift(field: str) -> None:
    scheduler = _native_scheduler()
    scheduler.start()
    scheduler.observe(_native_hold())
    scheduler.observe(_native_status())
    scheduler.observe(_native_status())
    scheduler.observe(_native_checkpoint_row(
        phase="armed", native_stage="armed",
    ))
    row = _native_checkpoint_row(
        phase="checkpoint_terminal", native_stage="completed",
    )
    row[field] = "wrong" if field != "actor_guid" else 30007
    scheduler.observe(row)
    assert scheduler.failure_reason == (
        "controller_route_hold_checkpoint_receipt_identity_invalid"
    )


def test_seal_binds_case_and_exact_pending_requests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    decision, decision_path, kwargs = _seal_fixture(tmp_path, monkeypatch)
    first = recurrence_admission.native_path_checkpoint_seal(
        case_id="a506_receipt636_incomplete_same_floor", **kwargs,
    )
    second = recurrence_admission.native_path_checkpoint_seal(
        case_id="a842_receipt519_complete_wrong_floor", **kwargs,
    )
    assert first["seal_sha256"] != second["seal_sha256"]
    decision["fixture_expansion_requests"][0]["to_revision"] += 1
    decision_path.write_text(json.dumps(decision), encoding="utf-8")
    with pytest.raises(
        recurrence_admission.RecurrenceAdmissionError,
        match="request_invalid",
    ):
        recurrence_admission.native_path_checkpoint_seal(
            case_id="a506_receipt636_incomplete_same_floor", **kwargs,
        )


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("missing", "native_path_checkpoint_request_contract_mismatch"),
        ("extra", "native_path_checkpoint_request_contract_mismatch"),
        ("stale_floor_revision", "native_path_checkpoint_request_contract_mismatch"),
        ("duplicate", "native_path_checkpoint_request_duplicate"),
        ("wrong_target", "native_path_checkpoint_request_target_mismatch"),
    ],
)
def test_seal_rejects_non_authoritative_pending_request_contracts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected_error: str,
) -> None:
    decision, decision_path, kwargs = _seal_fixture(tmp_path, monkeypatch)
    targets = decision["fixture_expansion_target_ids"]
    pending = decision["pending_fixture_ids"]
    requests = decision["fixture_expansion_requests"]
    assert isinstance(targets, list)
    assert isinstance(pending, list)
    assert isinstance(requests, list)
    if mutation == "missing":
        targets.pop()
        pending.pop()
        requests.pop()
    elif mutation == "extra":
        extra = {
            "fixture_id": "unexpected_native_path_fixture_v1",
            "from_revision": 1,
            "to_revision": 2,
            "causal_signature": "unexpected_native_path_cause",
            "required_production_boundary": "unexpected_native_path_boundary",
        }
        targets.append(extra["fixture_id"])
        pending.append(extra["fixture_id"])
        requests.append(extra)
    elif mutation == "stale_floor_revision":
        requests[0]["from_revision"] = 3
        requests[0]["to_revision"] = 4
    elif mutation == "duplicate":
        requests.append(dict(requests[0]))
    else:
        targets[-1] = "wrong_native_path_target_v1"
    decision_path.write_text(json.dumps(decision), encoding="utf-8")

    with pytest.raises(
        recurrence_admission.RecurrenceAdmissionError,
        match=expected_error,
    ):
        recurrence_admission.native_path_checkpoint_seal(
            case_id="a506_receipt636_incomplete_same_floor", **kwargs,
        )


@pytest.mark.parametrize("mutation", ["wrong_purpose", "wrong_target"])
def test_controller_rejects_wrong_purpose_or_target(mutation: str) -> None:
    admission = _native_admission()
    if mutation == "wrong_purpose":
        admission["purpose"] = recurrence_admission.GAMEPLAY_CANARY_PURPOSE
    else:
        admission["fixture_expansion_target_ids"] = [
            "wrong_native_path_target_v1"
        ]
    with pytest.raises(
        ValueError, match="native_path_checkpoint_verified_admission_invalid"
    ):
        native_path_checkpoint_arm_command(admission, 30007)


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


def test_normal_fixture_capture_installs_verified_native_dialect() -> None:
    setup = (
        ROOT / "tools/raid_program/capture_setup.py"
    ).read_text(encoding="utf-8")
    assert "checkpoint_controller_dialect(" in setup
    assert "expected_checkpoint_fixture_id=checkpoint_dialect[\"fixture_id\"]" \
        in setup
    assert "**checkpoint_dialect[\"scheduler_kwargs\"]" in setup
