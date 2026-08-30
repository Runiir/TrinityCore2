from __future__ import annotations

import json
from pathlib import Path
import shutil
import subprocess

import pytest

import tools.raid_program.chainwielder_prestart_bundle as prestart_bundle
from tools.raid_program.chainwielder_prestart_bundle import (
    ACTOR_GUID,
    BUNDLE_NAMES,
    BundleError,
    SCENARIO_ID,
    create_bundle,
    verify_bundle,
)
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
        ["git", "-C", str(root), *args], check=True, text=True,
        capture_output=True,
    ).stdout.strip()


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _gate(_receipt: Path, _policy: Path) -> dict[str, object]:
    return {"valid": True, "gate_bearing": True}


@pytest.fixture(autouse=True)
def _stub_external_build_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        prestart_bundle, "_verify_gate_bearing_build_receipt", _gate
    )


def _fixture(tmp_path: Path) -> dict[str, object]:
    root = tmp_path / "source"
    root.mkdir()
    _git(root, "init")
    _git(root, "config", "user.email", "test@example.invalid")
    _git(root, "config", "user.name", "Test")
    (root / "tracked.txt").write_text("source\n", encoding="utf-8")
    _git(root, "add", "tracked.txt")
    _git(root, "commit", "-m", "source")
    external = tmp_path / "inputs"
    external.mkdir()
    binary = tmp_path / "worldserver"
    binary.write_bytes(b"\x7fELFchainwielder")
    receipt = external / "build.json"
    _write_json(receipt, {
        "classification": "success",
        "exit_code": 0,
        "commit": _git(root, "rev-parse", "HEAD"),
        "output_artifacts": [{
            "kind": "worldserver_elf", "path": str(binary.resolve()),
            "sha256": sha256_file(binary), "produced_by_ticket": True,
        }],
    })
    policy = external / "policy.json"
    _write_json(policy, {"test": "policy"})
    decision = external / "decision.json"
    _write_json(decision, {
        "build_admitted": False,
        "canary_admitted": False,
        "fixture_expansion_admitted": True,
        "fixture_expansion_target_ids": [CHAINWIELDER_CHECKPOINT_FIXTURE_ID],
        "fixture_expansion_requests": [],
        "invalidated_fixture_ids": [],
        "failing_fixture_ids": [],
        "missing_fixture_ids": [],
        "pending_fixture_ids": [CHAINWIELDER_CHECKPOINT_FIXTURE_ID],
        "stale_fixture_ids": [],
    })
    suite = external / "suite.json"
    _write_json(suite, {
        "schema": "trinity_raid_regression_suite_receipt_v1",
        "source_identity": _git(root, "rev-parse", "HEAD"),
        "verifications": [{
            "fixture_id": CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
            "fixture_revision": 1,
            "passed": True,
        }],
    })
    route = external / "route.json"
    _write_json(route, {
        "schema": "bot_live_validation_route_manifest_v1",
        "scenario_id": SCENARIO_ID,
        "routes": [{
            "scenario_id": SCENARIO_ID,
            "runtime_profile_id": SCENARIO_ID,
            "route_node_id": "bwd.magmaw.chainwielder",
            "map_id": 669,
            "source_entry": 42649,
            "expected_bot_count": 10,
        }],
    })
    base = external / "base.conf"
    base.write_text(
        'BotWorld.RuntimeProfile = "old"\nBotWorld.AutoStart = 1\n',
        encoding="utf-8",
    )
    ledger = external / "ledger.json"
    _write_json(ledger, {"schema": "recurrence_ledger_test_v1"})
    paths = {
        "binary": binary,
        "build_receipt": receipt,
        "build_policy": policy,
        "decision": decision,
        "suite_receipt": suite,
        "route_manifest": route,
        "base_runtime_config": base,
        "ledger": ledger,
    }
    return {
        "root": root,
        "external": external,
        "output": tmp_path / "bundle",
        "paths": paths,
        "kwargs": {
            "worktree": root,
            "output_dir": tmp_path / "bundle",
            "source_commit": _git(root, "rev-parse", "HEAD"),
            "source_tree": _git(root, "rev-parse", "HEAD^{tree}"),
            **{key: path for key, path in paths.items()},
            **{f"{key}_sha256": sha256_file(path) for key, path in paths.items()},
            "scenario_id": SCENARIO_ID,
            "runtime_profile_id": SCENARIO_ID,
            "pool_tag": SCENARIO_ID,
            "actor_guid": ACTOR_GUID,
            "checkpoint_fixture_id": CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
        },
    }


def _create(fixture: dict[str, object]) -> dict[str, object]:
    return create_bundle(**fixture["kwargs"])  # type: ignore[arg-type]


def test_v6_manual_missing_flag_fails_before_atomic_bundle_passes_after(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    paths = fixture["paths"]
    root = fixture["root"]
    manual = tmp_path / "manual"
    manual.mkdir()
    route = manual / "route.json"
    shutil.copyfile(paths["route_manifest"], route)
    config = manual / "worldserver.conf"
    seal = chainwielder_checkpoint_seal(
        worktree=root, binary=paths["binary"],
        build_receipt=paths["build_receipt"], decision=paths["decision"],
    )
    config.write_text(
        f'BotWorld.ValidationRoute.ManifestPath = "{route.resolve()}"\n'
        "BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.Enable = 1\n"
        f'BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.FixtureId = "{CHAINWIELDER_CHECKPOINT_FIXTURE_ID}"\n'
        f'BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.SealSha256 = "{seal["seal_sha256"]}"\n'
        f'BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.SourceCommit = "{fixture["kwargs"]["source_commit"]}"\n',
        encoding="utf-8",
    )
    admission = manual / "admission.json"
    create_recurrence_admission(
        output=admission, worktree=root, binary=paths["binary"],
        build_receipt=paths["build_receipt"], runtime_config=config,
        route_manifest=route, ledger=paths["ledger"], decision=paths["decision"],
        suite_receipt=paths["suite_receipt"], purpose=FIXTURE_EXPANSION_PURPOSE,
    )
    with pytest.raises(
        RecurrenceAdmissionError, match="fixture_expansion_checkpoint_disabled"
    ):
        verify_recurrence_admission(
            admission_path=admission, expected_sha256=sha256_file(admission),
            worktree=root, binary=paths["binary"],
            build_receipt=paths["build_receipt"], runtime_config=config,
            required_purpose=FIXTURE_EXPANSION_PURPOSE,
        )

    result = _create(fixture)
    assert result["valid"] is True
    assert result["pre_rename_verified"] is True


def test_bundle_is_deterministic_and_does_not_mutate_inputs(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    paths = fixture["paths"]
    before = {key: sha256_file(path) for key, path in paths.items()}
    _create(fixture)
    output = fixture["output"]
    first = {path.name: path.read_bytes() for path in output.iterdir()}
    shutil.rmtree(output)
    _create(fixture)
    second = {path.name: path.read_bytes() for path in output.iterdir()}
    assert first == second
    assert before == {key: sha256_file(path) for key, path in paths.items()}


def test_existing_empty_output_directory_is_atomically_replaced(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture["output"].mkdir()

    assert _create(fixture)["valid"] is True
    assert (fixture["output"] / BUNDLE_NAMES["launch_contract"]).is_file()


@pytest.mark.parametrize(
    "name",
    [
        "route_manifest", "runtime_config", "build_receipt", "ledger",
        "decision", "suite_receipt", "checkpoint_seal", "admission",
        "launch_contract",
        "base_runtime_config", "build_policy",
    ],
)
def test_verify_rejects_each_internal_material_tamper(
    tmp_path: Path, name: str,
) -> None:
    fixture = _fixture(tmp_path)
    _create(fixture)
    path = fixture["output"] / BUNDLE_NAMES[name]
    path.write_bytes(path.read_bytes() + b"tamper")
    with pytest.raises(BundleError, match="bundle_file_hash_mismatch"):
        verify_bundle(fixture["output"])


@pytest.mark.parametrize("name", ["binary"])
def test_verify_rejects_each_external_material_tamper(
    tmp_path: Path, name: str,
) -> None:
    fixture = _fixture(tmp_path)
    _create(fixture)
    path = fixture["paths"][name]
    path.write_bytes(path.read_bytes() + b"tamper")
    with pytest.raises(BundleError, match=f"{name}_hash_mismatch"):
        verify_bundle(fixture["output"])


def test_verify_rejects_partial_bundle(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    _create(fixture)
    (fixture["output"] / BUNDLE_NAMES["admission"]).unlink()
    with pytest.raises(BundleError, match="bundle_partial_or_extra_files"):
        verify_bundle(fixture["output"])


def test_conflicting_duplicate_required_config_fails_closed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    base = fixture["paths"]["base_runtime_config"]
    base.write_text(
        "BotWorld.AutoStart = 0\nBotWorld.AutoStart = 1\n", encoding="utf-8"
    )
    fixture["kwargs"]["base_runtime_config_sha256"] = sha256_file(base)
    with pytest.raises(BundleError, match="config_duplicate_key:BotWorld.AutoStart"):
        _create(fixture)
    assert not fixture["output"].exists()
    failure = fixture["output"].with_name("bundle.failure.json")
    assert json.loads(failure.read_text(encoding="utf-8"))["launchable"] is False


def test_output_inside_worktree_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture["kwargs"]["output_dir"] = fixture["root"] / "bundle"
    with pytest.raises(BundleError, match="output_inside_worktree"):
        _create(fixture)


def test_launch_contract_is_exact_one_start_completion_watchdog(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    result = _create(fixture)
    launch = json.loads(
        (fixture["output"] / BUNDLE_NAMES["launch_contract"]).read_text(encoding="utf-8")
    )
    assert launch["start_budget"] == {
        "owner": "capture_controller", "worldserver_starts": 1,
    }
    assert launch["completion_watchdog"]["duration_policy"] == "completion-watchdog"
    assert launch["fixed_success_timer_seconds"] is None
    assert launch["expected_arm_predicates"]["emission_count"] == 1
    assert launch["expected_lifecycle_predicates"]["outcome"] == "hazard_exit_completed"
    assert "--observe-sec" not in result["launch_argv"]


def test_wrong_actor_fixture_or_source_and_dirty_source_fail_closed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    fixture["kwargs"]["actor_guid"] = ACTOR_GUID + 1
    with pytest.raises(BundleError, match="chainwielder_identity_input_mismatch"):
        _create(fixture)
    fixture["kwargs"]["actor_guid"] = ACTOR_GUID
    fixture["kwargs"]["checkpoint_fixture_id"] = "wrong"
    with pytest.raises(BundleError, match="chainwielder_identity_input_mismatch"):
        _create(fixture)
    fixture["kwargs"]["checkpoint_fixture_id"] = CHAINWIELDER_CHECKPOINT_FIXTURE_ID
    fixture["kwargs"]["source_commit"] = "0" * 40
    with pytest.raises(BundleError, match="source_identity_mismatch"):
        _create(fixture)
    fixture["kwargs"]["source_commit"] = _git(fixture["root"], "rev-parse", "HEAD")
    (fixture["root"] / "tracked.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(BundleError, match="source_worktree_dirty"):
        _create(fixture)


def test_atomic_relocation_is_sibling_only_and_default_verifier_unchanged(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    paths = fixture["paths"]
    root = fixture["root"]
    final = tmp_path / "relocated"
    staging = tmp_path / ".relocated.staging-test"
    staging.mkdir()
    for key, name in {
        "build_receipt": "build.json", "route_manifest": "route.json",
        "ledger": "ledger.json", "decision": "decision.json",
        "suite_receipt": "suite.json",
    }.items():
        shutil.copyfile(paths[key], staging / name)
    seal = chainwielder_checkpoint_seal(
        worktree=root, binary=paths["binary"], build_receipt=staging / "build.json",
        decision=staging / "decision.json",
    )
    config = staging / "config.conf"
    config.write_text(
        f'BotWorld.ValidationRoute.ManifestPath = "{final / "route.json"}"\n'
        "BotWorld.ValidationRoute.PrepullCheckpointEnable = 1\n"
        "BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.Enable = 1\n"
        f'BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.FixtureId = "{CHAINWIELDER_CHECKPOINT_FIXTURE_ID}"\n'
        f'BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.SealSha256 = "{seal["seal_sha256"]}"\n'
        f'BotWorld.ValidationFixture.ChainwielderOwnerCheckpoint.SourceCommit = "{fixture["kwargs"]["source_commit"]}"\n',
        encoding="utf-8",
    )
    admission = staging / "admission.json"
    create_recurrence_admission(
        output=admission, worktree=root, binary=paths["binary"],
        build_receipt=staging / "build.json", runtime_config=config,
        route_manifest=staging / "route.json", ledger=staging / "ledger.json",
        decision=staging / "decision.json", suite_receipt=staging / "suite.json",
        purpose=FIXTURE_EXPANSION_PURPOSE,
        atomic_bundle_roots=(final, staging),
    )
    with pytest.raises(RecurrenceAdmissionError, match="build_receipt_path_mismatch"):
        verify_recurrence_admission(
            admission_path=admission, expected_sha256=sha256_file(admission),
            worktree=root, binary=paths["binary"], build_receipt=staging / "build.json",
            runtime_config=config, required_purpose=FIXTURE_EXPANSION_PURPOSE,
        )
    assert verify_recurrence_admission(
        admission_path=admission, expected_sha256=sha256_file(admission),
        worktree=root, binary=paths["binary"], build_receipt=staging / "build.json",
        runtime_config=config, required_purpose=FIXTURE_EXPANSION_PURPOSE,
        atomic_bundle_roots=(final, staging),
    )["valid"] is True
    with pytest.raises(RecurrenceAdmissionError, match="atomic_bundle_roots_invalid"):
        verify_recurrence_admission(
            admission_path=admission, expected_sha256=sha256_file(admission),
            worktree=root, binary=paths["binary"], build_receipt=staging / "build.json",
            runtime_config=config, required_purpose=FIXTURE_EXPANSION_PURPOSE,
            atomic_bundle_roots=(final, tmp_path / "arbitrary" / "stage"),
        )
