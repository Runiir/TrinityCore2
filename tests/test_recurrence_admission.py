from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from tools.raid_program.recurrence_admission import (
    CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
    FIXTURE_EXPANSION_PURPOSE,
    RecurrenceAdmissionError,
    chainwielder_checkpoint_seal,
    create_recurrence_admission,
    sha256_file,
    verify_recurrence_admission,
)


def _git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.strip()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")


def _fixture(tmp_path: Path) -> dict[str, Path | str]:
    root = tmp_path / "repo"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    tracked = root / "tracked.txt"
    tracked.write_text("identity\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "identity")

    binary = tmp_path / "worldserver"
    build_receipt = tmp_path / "build.json"
    route = tmp_path / "route.json"
    config = tmp_path / "worldserver.conf"
    ledger = tmp_path / "ledger.json"
    decision = tmp_path / "decision.json"
    suite = tmp_path / "suite.json"
    binary.write_bytes(b"\x7fELFtest")
    _write_json(
        build_receipt,
        {
            "classification": "success",
            "exit_code": 0,
            "commit": _git(root, "rev-parse", "HEAD"),
            "output_artifacts": [
                {
                    "kind": "worldserver_elf",
                    "path": str(binary.resolve()),
                    "sha256": sha256_file(binary),
                    "produced_by_ticket": True,
                }
            ],
        },
    )
    _write_json(route, {"scenario_id": "blackwing_descent_10n_magmaw_diagnostic"})
    config.write_text(
        f'BotWorld.ValidationRoute.ManifestPath = "{route}"\n', encoding="utf-8"
    )
    _write_json(ledger, {"schema": "ledger"})
    clear_lists = {
        "invalidated_fixture_ids": [],
        "failing_fixture_ids": [],
        "missing_fixture_ids": [],
        "pending_fixture_ids": [],
        "stale_fixture_ids": [],
    }
    _write_json(
        decision,
        {"build_admitted": True, "canary_admitted": True, **clear_lists},
    )
    _write_json(
        suite,
        {
            "schema": "trinity_raid_regression_suite_receipt_v1",
            "source_identity": _git(root, "rev-parse", "HEAD"),
            "verifications": [
                {
                    "fixture_id": "magmaw_parasite_control_full_runtime_v1",
                    "fixture_revision": 4,
                    "passed": True,
                }
            ],
        },
    )
    bindings = {}
    for name, path in {
        "binary": binary,
        "build_receipt": build_receipt,
        "runtime_config": config,
        "route_manifest": route,
        "ledger": ledger,
        "decision": decision,
        "suite_receipt": suite,
    }.items():
        bindings[name] = {"path": str(path.resolve()), "sha256": sha256_file(path)}
    admission = tmp_path / "admission.json"
    _write_json(
        admission,
        {
            "schema": "cata_raid_recurrence_admission_v1",
            "build_admitted": True,
            "canary_admitted": True,
            **clear_lists,
            "source": {
                "commit": _git(root, "rev-parse", "HEAD"),
                "tree": _git(root, "rev-parse", "HEAD^{tree}"),
                "porcelain_sha256": hashlib.sha256(b"").hexdigest(),
            },
            "bindings": bindings,
            "fixture_revisions": {
                "magmaw_parasite_control_full_runtime_v1": 4,
            },
        },
    )
    return {
        "root": root,
        "binary": binary,
        "build_receipt": build_receipt,
        "config": config,
        "admission": admission,
        "route": route,
        "ledger": ledger,
        "decision": decision,
        "suite": suite,
    }


def _verify(paths: dict[str, Path | str]) -> dict[str, object]:
    admission = Path(paths["admission"])
    return verify_recurrence_admission(
        admission_path=admission,
        expected_sha256=sha256_file(admission),
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        runtime_config=Path(paths["config"]),
    )


def _replacement_request() -> dict[str, object]:
    return {
        "fixture_id": "native_planner_executor_launch_proof_v1",
        "from_revision": 2,
        "to_revision": 3,
        "causal_signature": "native_planner_executor_launch_divergence",
        "required_production_boundary": (
            "worldserver-backed map-669 planner, executor, MotionMaster, "
            "point generator, and launched spline observed over multiple ticks"
        ),
    }


def _create_chainwielder_checkpoint_admission(
    paths: dict[str, Path | str],
) -> dict[str, str]:
    admission = Path(paths["admission"])
    decision = Path(paths["decision"])
    suite = Path(paths["suite"])
    config = Path(paths["config"])
    admission.unlink()
    decision_value = json.loads(decision.read_text(encoding="utf-8"))
    decision_value.update(
        {
            "build_admitted": False,
            "canary_admitted": False,
            "fixture_expansion_admitted": True,
            "fixture_expansion_target_ids": [
                CHAINWIELDER_CHECKPOINT_FIXTURE_ID
            ],
            "fixture_expansion_requests": [],
            "pending_fixture_ids": [CHAINWIELDER_CHECKPOINT_FIXTURE_ID],
        }
    )
    _write_json(decision, decision_value)
    suite_value = json.loads(suite.read_text(encoding="utf-8"))
    suite_value["verifications"] = [
        {
            "fixture_id": CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
            "fixture_revision": 1,
            "passed": True,
        }
    ]
    _write_json(suite, suite_value)
    seal = chainwielder_checkpoint_seal(
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        decision=decision,
    )
    source_commit = _git(Path(paths["root"]), "rev-parse", "HEAD")
    config.write_text(
        config.read_text(encoding="utf-8")
        + "BotWorld.ValidationRoute.PrepullCheckpointEnable = 1\n"
        + "BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.Enable = 1\n"
        + "BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint."
        + f'FixtureId = "{CHAINWIELDER_CHECKPOINT_FIXTURE_ID}"\n'
        + "BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint."
        + f'SealSha256 = "{seal["seal_sha256"]}"\n'
        + "BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint."
        + f'SourceCommit = "{source_commit}"\n',
        encoding="utf-8",
    )
    create_recurrence_admission(
        output=admission,
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        runtime_config=config,
        route_manifest=Path(paths["route"]),
        ledger=Path(paths["ledger"]),
        decision=decision,
        suite_receipt=suite,
        purpose=FIXTURE_EXPANSION_PURPOSE,
    )
    return seal


def _verify_chainwielder(
    paths: dict[str, Path | str],
) -> dict[str, object]:
    admission = Path(paths["admission"])
    return verify_recurrence_admission(
        admission_path=admission,
        expected_sha256=sha256_file(admission),
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        runtime_config=Path(paths["config"]),
        required_purpose=FIXTURE_EXPANSION_PURPOSE,
    )


def test_exact_recurrence_admission_passes(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)

    assert _verify(paths)["valid"] is True


def test_creator_seals_a_verifiable_admission(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    admission = Path(paths["admission"])
    admission.unlink()

    create_recurrence_admission(
        output=admission,
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        runtime_config=Path(paths["config"]),
        route_manifest=Path(paths["route"]),
        ledger=Path(paths["ledger"]),
        decision=Path(paths["decision"]),
        suite_receipt=Path(paths["suite"]),
    )

    assert _verify(paths)["valid"] is True


def test_chainwielder_checkpoint_uses_precomputed_non_circular_seal(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    seal = _create_chainwielder_checkpoint_admission(paths)

    result = _verify_chainwielder(paths)

    assert result["valid"] is True
    assert result["checkpoint_seal_sha256"] == seal["seal_sha256"]
    admission = json.loads(
        Path(paths["admission"]).read_text(encoding="utf-8")
    )
    assert admission["checkpoint_seal"] == seal
    assert admission["bindings"]["runtime_config"]["sha256"] == sha256_file(
        Path(paths["config"])
    )


@pytest.mark.parametrize(
    ("binding", "reason"),
    [
        ("runtime_config", "runtime_config_hash_mismatch"),
        ("binary", "binary_hash_mismatch"),
        ("build_receipt", "build_receipt_hash_mismatch"),
    ],
)
def test_chainwielder_checkpoint_rejects_bound_input_mutation(
    tmp_path: Path, binding: str, reason: str,
) -> None:
    paths = _fixture(tmp_path)
    _create_chainwielder_checkpoint_admission(paths)
    path = Path(paths["config" if binding == "runtime_config" else binding])
    path.write_bytes(path.read_bytes() + b"tampered")

    with pytest.raises(RecurrenceAdmissionError, match=reason):
        _verify_chainwielder(paths)


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("seal", "checkpoint_seal_identity_mismatch"),
        ("fixture", "fixture_expansion_request_target_mismatch"),
        ("source", "checkpoint_seal_identity_mismatch"),
    ],
)
def test_chainwielder_checkpoint_rejects_admission_identity_tamper(
    tmp_path: Path, mutation: str, reason: str,
) -> None:
    paths = _fixture(tmp_path)
    _create_chainwielder_checkpoint_admission(paths)
    admission = Path(paths["admission"])
    value = json.loads(admission.read_text(encoding="utf-8"))
    if mutation == "seal":
        value["checkpoint_seal"]["seal_sha256"] = "0" * 64
    elif mutation == "fixture":
        value["fixture_expansion_target_ids"] = ["wrong_fixture"]
    else:
        value["checkpoint_seal"]["source_commit"] = "0" * 40
    _write_json(admission, value)

    with pytest.raises(RecurrenceAdmissionError, match=reason):
        _verify_chainwielder(paths)


def test_chainwielder_checkpoint_rejects_final_admission_file_mutation(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    _create_chainwielder_checkpoint_admission(paths)
    admission = Path(paths["admission"])
    admitted_sha = sha256_file(admission)
    admission.write_bytes(admission.read_bytes() + b" ")

    with pytest.raises(RecurrenceAdmissionError, match="admission_hash_mismatch"):
        verify_recurrence_admission(
            admission_path=admission,
            expected_sha256=admitted_sha,
            worktree=Path(paths["root"]),
            binary=Path(paths["binary"]),
            build_receipt=Path(paths["build_receipt"]),
            runtime_config=Path(paths["config"]),
            required_purpose=FIXTURE_EXPANSION_PURPOSE,
        )


def test_fixture_expansion_admission_is_distinct_from_gameplay_canary(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    admission = Path(paths["admission"])
    decision = Path(paths["decision"])
    config = Path(paths["config"])
    admission.unlink()
    decision_value = json.loads(decision.read_text(encoding="utf-8"))
    decision_value.update(
        {
            "build_admitted": False,
            "canary_admitted": False,
            "fixture_expansion_admitted": True,
            "fixture_expansion_target_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
            "invalidated_fixture_ids": ["same_level_native_path_proof_v1"],
            "failing_fixture_ids": ["same_level_native_path_proof_v1"],
            "pending_fixture_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
        }
    )
    _write_json(decision, decision_value)
    config.write_text(
        config.read_text(encoding="utf-8")
        + "BotWorld.ValidationRoute.PrepullCheckpointEnable = 1\n",
        encoding="utf-8",
    )

    create_recurrence_admission(
        output=admission,
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        runtime_config=config,
        route_manifest=Path(paths["route"]),
        ledger=Path(paths["ledger"]),
        decision=decision,
        suite_receipt=Path(paths["suite"]),
        purpose=FIXTURE_EXPANSION_PURPOSE,
    )

    result = verify_recurrence_admission(
        admission_path=admission,
        expected_sha256=sha256_file(admission),
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        runtime_config=config,
        required_purpose=FIXTURE_EXPANSION_PURPOSE,
    )
    assert result["valid"] is True
    assert result["purpose"] == FIXTURE_EXPANSION_PURPOSE
    assert result["fixture_expansion_target_ids"] == [
        "native_planner_executor_launch_proof_v1"
    ]
    with pytest.raises(RecurrenceAdmissionError, match="admission_purpose_mismatch"):
        _verify(paths)


def test_invalidated_replacement_request_seals_target_and_revisions(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    admission = Path(paths["admission"])
    decision = Path(paths["decision"])
    suite = Path(paths["suite"])
    config = Path(paths["config"])
    admission.unlink()
    decision_value = json.loads(decision.read_text(encoding="utf-8"))
    decision_value.update(
        {
            "build_admitted": False,
            "canary_admitted": False,
            "fixture_expansion_admitted": True,
            "fixture_expansion_target_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
            "fixture_expansion_requests": [_replacement_request()],
            "invalidated_fixture_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
            "failing_fixture_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
            "pending_fixture_ids": [],
        }
    )
    _write_json(decision, decision_value)
    suite_value = json.loads(suite.read_text(encoding="utf-8"))
    suite_value["verifications"] = [
        {
            "fixture_id": "native_planner_executor_launch_proof_v1",
            "fixture_revision": 2,
            "passed": True,
        }
    ]
    _write_json(suite, suite_value)
    config.write_text(
        config.read_text(encoding="utf-8")
        + "BotWorld.ValidationRoute.PrepullCheckpointEnable = 1\n",
        encoding="utf-8",
    )

    create_recurrence_admission(
        output=admission,
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        runtime_config=config,
        route_manifest=Path(paths["route"]),
        ledger=Path(paths["ledger"]),
        decision=decision,
        suite_receipt=suite,
        purpose=FIXTURE_EXPANSION_PURPOSE,
    )

    result = verify_recurrence_admission(
        admission_path=admission,
        expected_sha256=sha256_file(admission),
        worktree=Path(paths["root"]),
        binary=Path(paths["binary"]),
        build_receipt=Path(paths["build_receipt"]),
        runtime_config=config,
        required_purpose=FIXTURE_EXPANSION_PURPOSE,
    )
    assert result["fixture_expansion_target_ids"] == [
        "native_planner_executor_launch_proof_v1"
    ]
    assert result["fixture_expansion_requests"] == [_replacement_request()]


@pytest.mark.parametrize(
    "target_ids",
    [[], ["native_planner_executor_launch_proof_v1", "extra"]],
)
def test_fixture_expansion_rejects_missing_or_extra_request_target(
    tmp_path: Path, target_ids: list[str]
) -> None:
    paths = _fixture(tmp_path)
    admission = Path(paths["admission"])
    decision = Path(paths["decision"])
    admission.unlink()
    decision_value = json.loads(decision.read_text(encoding="utf-8"))
    decision_value.update(
        {
            "build_admitted": False,
            "canary_admitted": False,
            "fixture_expansion_admitted": True,
            "fixture_expansion_target_ids": target_ids,
            "fixture_expansion_requests": [_replacement_request()],
            "invalidated_fixture_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
            "failing_fixture_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
            "pending_fixture_ids": [],
        }
    )
    _write_json(decision, decision_value)

    with pytest.raises(
        RecurrenceAdmissionError,
        match="fixture_expansion_(target_invalid|request_target_mismatch)",
    ):
        create_recurrence_admission(
            output=admission,
            worktree=Path(paths["root"]),
            binary=Path(paths["binary"]),
            build_receipt=Path(paths["build_receipt"]),
            runtime_config=Path(paths["config"]),
            route_manifest=Path(paths["route"]),
            ledger=Path(paths["ledger"]),
            decision=decision,
            suite_receipt=Path(paths["suite"]),
            purpose=FIXTURE_EXPANSION_PURPOSE,
        )


def test_fixture_expansion_creator_rejects_stale_suite_and_dirty_source(
    tmp_path: Path,
) -> None:
    paths = _fixture(tmp_path)
    admission = Path(paths["admission"])
    decision = Path(paths["decision"])
    suite = Path(paths["suite"])
    admission.unlink()
    decision_value = json.loads(decision.read_text(encoding="utf-8"))
    decision_value.update(
        {
            "build_admitted": False,
            "canary_admitted": False,
            "fixture_expansion_admitted": True,
            "fixture_expansion_target_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
            "fixture_expansion_requests": [_replacement_request()],
            "invalidated_fixture_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
            "failing_fixture_ids": [
                "native_planner_executor_launch_proof_v1"
            ],
            "pending_fixture_ids": [],
        }
    )
    _write_json(decision, decision_value)
    suite_value = json.loads(suite.read_text(encoding="utf-8"))
    suite_value["source_identity"] = "stale"
    _write_json(suite, suite_value)

    kwargs = {
        "output": admission,
        "worktree": Path(paths["root"]),
        "binary": Path(paths["binary"]),
        "build_receipt": Path(paths["build_receipt"]),
        "runtime_config": Path(paths["config"]),
        "route_manifest": Path(paths["route"]),
        "ledger": Path(paths["ledger"]),
        "decision": decision,
        "suite_receipt": suite,
        "purpose": FIXTURE_EXPANSION_PURPOSE,
    }
    with pytest.raises(RecurrenceAdmissionError, match="suite_receipt_source_stale"):
        create_recurrence_admission(**kwargs)

    suite_value["source_identity"] = _git(Path(paths["root"]), "rev-parse", "HEAD")
    _write_json(suite, suite_value)
    (Path(paths["root"]) / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(RecurrenceAdmissionError, match="source_worktree_dirty"):
        create_recurrence_admission(**kwargs)


def test_recurrence_admission_rejects_wrong_hash(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)

    with pytest.raises(RecurrenceAdmissionError, match="admission_hash_mismatch"):
        verify_recurrence_admission(
            admission_path=Path(paths["admission"]),
            expected_sha256="0" * 64,
            worktree=Path(paths["root"]),
            binary=Path(paths["binary"]),
            build_receipt=Path(paths["build_receipt"]),
            runtime_config=Path(paths["config"]),
        )


def test_recurrence_admission_rejects_missing_file(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)

    with pytest.raises(RecurrenceAdmissionError, match="admission_missing"):
        verify_recurrence_admission(
            admission_path=tmp_path / "missing.json",
            expected_sha256="0" * 64,
            worktree=Path(paths["root"]),
            binary=Path(paths["binary"]),
            build_receipt=Path(paths["build_receipt"]),
            runtime_config=Path(paths["config"]),
        )


def test_recurrence_admission_rejects_new_head(tmp_path: Path) -> None:
    paths = _fixture(tmp_path)
    root = Path(paths["root"])
    (root / "tracked.txt").write_text("new identity\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "new identity")

    with pytest.raises(RecurrenceAdmissionError, match="source_identity_stale"):
        _verify(paths)


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("canary_admitted", False, "canary_not_admitted"),
        (
            "invalidated_fixture_ids",
            ["magmaw_parasite_control_full_runtime_v1"],
            "invalidated_fixture_ids_present",
        ),
        (
            "pending_fixture_ids",
            ["native_planner_executor_launch_proof_v1"],
            "pending_fixture_ids_present",
        ),
    ],
)
def test_recurrence_admission_rejects_closed_gate(
    tmp_path: Path, field: str, value: object, reason: str
) -> None:
    paths = _fixture(tmp_path)
    admission = Path(paths["admission"])
    value_json = json.loads(admission.read_text(encoding="utf-8"))
    value_json[field] = value
    _write_json(admission, value_json)

    with pytest.raises(RecurrenceAdmissionError, match=reason):
        _verify(paths)
