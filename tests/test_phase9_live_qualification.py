from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from tools.bot_ml.generate_bot_admission_identities import build_identity_catalog
from tools.bot_ml.build_phase9_pairwise_matrix import build_matrix
from tools.bot_ml.build_phase9_serial_run_plan import build_plan
from tools.bot_ml.live_validation_session import canonical_sha256
from tools.bot_ml.phase8_evidence_identity import build_projection as phase8_build_projection
from tools.bot_ml.phase9_evidence_identity import (
    build_projection as phase9_build_projection,
    profile_generation_identity as phase9_profile_generation_identity,
    server_epoch_identity as phase9_server_epoch_identity,
    validate_manifest as validate_phase9_evidence_manifest,
)
from tools.bot_ml.run_phase9_serial_canaries import (
    attempt_directory_matches,
    campaign_identities_compatible,
    classify_phase9_physical_try,
    close_interrupted_phase9_tries,
    exact_phase9_campaign_coverage,
    next_attempt_directory,
    phase9_attempt_accepted,
    phase9_physical_attempt,
    phase9_physical_command,
    phase9_physical_result,
    phase9_physical_sequence_findings,
    phase9_source_transport_verified,
    phase9_physical_try_directory,
    scan_phase9_physical_ledger,
    write_phase9_physical_try_result,
    write_phase9_physical_try_started,
)
from tools.bot_ml import run_phase9_serial_canaries as phase9_runner
from tools.bot_ml.run_live_bot_validation import (
    expected_admission_identity_source_sha256,
    expected_class_spec_gear_identities,
    expected_class_spec_pet_identities,
    validate_heroic_admission_receipt,
)
from tools.bot_ml.promote_live_validation_artifact import promotion_manifest
from tools.bot_ml.verify_phase9_pairwise_matrix import verify


ROOT = Path(__file__).resolve().parents[1]
TARGETS = ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
POLICY = ROOT / "experiments/configs/stonecore_phase9_pair_policy_v1.json"
MATRIX = ROOT / "experiments/configs/stonecore_phase9_pairwise_matrix_v1.json"


TARGETED_EXCLUSIONS = [
    "arcane_mage",
    "beast_mastery_hunter",
    "destruction_warlock",
    "enhancement_shaman",
    "frost_mage",
    "protection_warrior",
    "subtlety_rogue",
]


def phase9_evidence_identity_fixture(*, server_epoch: int = 20) -> dict:
    server_binding = phase9_server_epoch_identity(
        server_epoch=server_epoch,
        server_process_id=200 + server_epoch,
        session_fingerprint=f"phase9-session-{server_epoch}",
    )
    profile_binding = phase9_profile_generation_identity(
        profile_generation=9,
        profile_content_hash="c" * 64,
    )
    build_identity = {
        "git_commit": "d" * 40,
        "source_tree_clean": True,
        "worldserver_binary_sha256": "e" * 64,
        "database_snapshot_sha256": "a" * 64,
        "database_schema_sha256": "b" * 64,
        "profile_content_hash": profile_binding["profile_content_hash"],
    }
    projection = phase9_build_projection({"build_identity": build_identity})
    artifact_hashes = {
        "target_catalog_sha256": "1" * 64,
        "pair_policy_sha256": "2" * 64,
        "pairwise_matrix_sha256": "3" * 64,
        "route_manifest_sha256": "4" * 64,
    }
    manifest = {
        "schema": "all_spec_phase9_evidence_identity_manifest_v2",
        "component_hashes": {
            "source_identity_sha256": canonical_sha256(
                {"git_commit": build_identity["git_commit"], "source_tree_clean": True}
            ),
            "worldserver_binary_sha256": build_identity["worldserver_binary_sha256"],
            "database_snapshot_sha256": build_identity["database_snapshot_sha256"],
            "database_schema_sha256": build_identity["database_schema_sha256"],
            "server_epoch_sha256": canonical_sha256(server_binding),
            "profile_generation_sha256": canonical_sha256(profile_binding),
            "build_projection_sha256": canonical_sha256(projection),
        },
        "artifact_hashes": artifact_hashes,
        "build_identity": build_identity,
        "runtime_identity": {**server_binding, **profile_binding},
        "database_summary": {},
        "route_summary": {},
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return manifest


def test_phase9_manifest_build_projection_is_cross_campaign_and_epoch_independent() -> None:
    manifest = phase9_evidence_identity_fixture(server_epoch=20)
    validated = validate_phase9_evidence_manifest(
        manifest,
        artifact_hashes=manifest["artifact_hashes"],
    )
    assert phase8_build_projection(validated) == phase9_build_projection(validated)

    another_epoch = phase9_evidence_identity_fixture(server_epoch=21)
    assert phase9_build_projection(another_epoch) == phase9_build_projection(manifest)
    assert another_epoch["runtime_identity"] != manifest["runtime_identity"]


def test_phase9_manifest_rejects_rehashed_dirty_or_mismatched_build_binding() -> None:
    dirty = phase9_evidence_identity_fixture()
    dirty["build_identity"]["source_tree_clean"] = False
    dirty["manifest_sha256"] = canonical_sha256(
        {key: value for key, value in dirty.items() if key != "manifest_sha256"}
    )
    with pytest.raises(ValueError, match="build projection is invalid"):
        validate_phase9_evidence_manifest(dirty)

    mismatched = phase9_evidence_identity_fixture()
    mismatched["build_identity"]["database_snapshot_sha256"] = "f" * 64
    mismatched["manifest_sha256"] = canonical_sha256(
        {key: value for key, value in mismatched.items() if key != "manifest_sha256"}
    )
    with pytest.raises(ValueError, match="build binding is invalid"):
        validate_phase9_evidence_manifest(mismatched)


def test_joined_campaign_requires_same_clean_build_projection() -> None:
    dps = phase9_evidence_identity_fixture(server_epoch=20)
    phase9 = json.loads(json.dumps(dps))
    assert campaign_identities_compatible(dps, phase9) is True
    phase9["build_identity"]["worldserver_binary_sha256"] = "f" * 64
    assert campaign_identities_compatible(dps, phase9) is False


def test_phase9_launch_guard_rechecks_clean_source_and_worldserver(
    tmp_path: Path, monkeypatch
) -> None:
    identity = phase9_evidence_identity_fixture()
    binary = tmp_path / "worldserver"
    binary.write_bytes(b"synthetic-worldserver")
    attempts = [{"command": ["runner", "--worldserver", str(binary)]}]

    monkeypatch.setattr(phase9_runner, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        phase9_runner,
        "git_head",
        lambda _repository: identity["build_identity"]["git_commit"],
    )
    monkeypatch.setattr(
        phase9_runner,
        "sha256_file",
        lambda _path: identity["build_identity"]["worldserver_binary_sha256"],
    )
    monkeypatch.setattr(
        phase9_runner.subprocess,
        "run",
        lambda *_args, **_kwargs: phase9_runner.subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        ),
    )
    observed = phase9_runner.require_current_phase9_source_binary(
        identity, attempts
    )
    assert observed == phase9_build_projection(identity)

    monkeypatch.setattr(
        phase9_runner.subprocess,
        "run",
        lambda *_args, **_kwargs: phase9_runner.subprocess.CompletedProcess(
            args=[], returncode=0, stdout=" M source.cpp\n", stderr=""
        ),
    )
    with pytest.raises(ValueError, match="clean source tree"):
        phase9_runner.require_current_phase9_source_binary(identity, attempts)

    monkeypatch.setattr(
        phase9_runner.subprocess,
        "run",
        lambda *_args, **_kwargs: phase9_runner.subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        ),
    )
    monkeypatch.setattr(phase9_runner, "sha256_file", lambda _path: "0" * 64)
    with pytest.raises(ValueError, match="worldserver binary changed"):
        phase9_runner.require_current_phase9_source_binary(identity, attempts)


def test_phase9_controller_lock_is_anchored_to_plan_campaign_root(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(phase9_runner, "REPO_ROOT", tmp_path)
    plan = {
        "session_runtime_dir": "campaign/session_runtime",
        "attempts": [{"output_dir": "campaign/attempts/one"}],
    }
    campaign_root = phase9_runner.phase9_campaign_root(plan)
    assert campaign_root == tmp_path / "campaign"
    first = phase9_runner.acquire_phase9_controller_lock(campaign_root)
    try:
        with pytest.raises(ValueError, match="already held"):
            phase9_runner.acquire_phase9_controller_lock(
                phase9_runner.phase9_campaign_root(plan)
            )
    finally:
        first.close()


def test_phase9_append_ledger_fails_closed_on_torn_final_record(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(phase9_runner, "REPO_ROOT", tmp_path)
    logical = logical_phase9_attempt(tmp_path)
    output = tmp_path / logical["output_dir"]
    output.mkdir(parents=True)
    physical = phase9_physical_attempt(logical, 1)
    phase9_runner.write_phase9_physical_try_started(
        output,
        logical,
        physical,
        phase9_physical_command(logical, physical, output),
    )
    ledger = tmp_path / "campaign/phase9_physical_try_ledger.jsonl"
    phase9_runner.reconcile_phase9_append_ledger(
        ledger,
        [logical],
        plan_sha256="a" * 64,
        identity_manifest_sha256="b" * 64,
    )
    complete_without_newline = ledger.read_bytes().rstrip(b"\n")
    ledger.write_bytes(complete_without_newline)
    with pytest.raises(ValueError, match="unterminated"):
        phase9_runner.reconcile_phase9_append_ledger(
            ledger,
            [logical],
            plan_sha256="a" * 64,
            identity_manifest_sha256="b" * 64,
        )
    ledger.write_bytes(complete_without_newline + b"\n")
    with ledger.open("ab") as stream:
        stream.write(b'{"schema":"phase9_physical_try_ledger_event_v1"')
    torn = ledger.read_bytes()
    with pytest.raises((ValueError, json.JSONDecodeError)):
        phase9_runner.reconcile_phase9_append_ledger(
            ledger,
            [logical],
            plan_sha256="a" * 64,
            identity_manifest_sha256="b" * 64,
        )
    assert ledger.read_bytes() == torn
    assert b'"event": "physical_try_started"' in torn


def test_phase9_child_runs_without_overall_wall_clock_timeout(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(phase9_runner, "REPO_ROOT", tmp_path)
    logical = logical_phase9_attempt(tmp_path)
    output = tmp_path / logical["output_dir"]
    output.mkdir(parents=True)
    physical = phase9_physical_attempt(logical, 1)
    started = phase9_runner.write_phase9_physical_try_started(
        output,
        logical,
        physical,
        phase9_physical_command(logical, physical, output),
    )
    log_path = output / "phase9_runner.log"
    execution, interruption = phase9_runner.run_phase9_child(
        [sys.executable, "-c", "pass"],
        log_path,
        termination_grace_sec=0.05,
    )
    assert interruption is None
    assert execution["execution_policy"] == "run_to_completion"
    assert execution["overall_wall_clock_timeout_sec"] is None
    assert execution["outer_timed_out"] is False
    assert execution["process_group_terminate_sent"] is False
    assert execution["process_group_kill_sent"] is False
    assert execution["process_group_gone"] is True
    assert execution["process_exit_observed"] is True
    result = phase9_runner.phase9_physical_result(
        logical_attempt=logical,
        physical=physical,
        output_dir=output,
        log_path=log_path,
        child_returncode=execution["returncode"],
        receipt={},
        reconstruction_valid=False,
        reconstruction={},
        reconstruction_error="missing_publication",
        child_execution=execution,
    )
    assert result["timed_out"] is None
    assert result["classification"] == "publication_failure"
    receipt = phase9_runner.write_phase9_physical_try_result(
        output, started, result
    )
    loaded, _ = phase9_runner.load_phase9_physical_try_result(
        output, started, physical
    )
    assert loaded["classification"] == "publication_failure"
    assert loaded["outer_timed_out"] is False
    assert loaded["overall_wall_clock_timeout_sec"] is None
    assert receipt["classification"] == "publication_failure"


def test_phase9_normal_leader_exit_cleans_lingering_descendant(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(phase9_runner, "REPO_ROOT", tmp_path)
    descendant_pid_path = tmp_path / "descendant.pid"
    script = tmp_path / "leader.py"
    script.write_text(
        "import os, pathlib, subprocess, sys\n"
        "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
        "pathlib.Path(sys.argv[1]).write_text(str(child.pid), encoding='utf-8')\n"
        "os._exit(0)\n",
        encoding="utf-8",
    )
    outcome, interruption = phase9_runner.run_phase9_child(
        [sys.executable, str(script), str(descendant_pid_path)],
        tmp_path / "leader.log",
        termination_grace_sec=0.2,
        kill_grace_sec=0.5,
    )
    assert interruption is None
    assert descendant_pid_path.is_file()
    assert outcome["returncode"] == 0
    assert outcome["transport_classification"] == (
        "child_exited_with_lingering_descendants"
    )
    assert outcome["process_group_terminate_sent"] is True
    assert outcome["process_group_gone"] is True
    accepted_looking = accepted_phase9_row(1)
    accepted_looking.update(outcome)
    assert phase9_attempt_accepted(accepted_looking) is False
    assert classify_phase9_physical_try(accepted_looking) == (
        "infrastructure_failure"
    )


def test_phase9_controller_signal_cleans_group_before_propagation(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(phase9_runner, "REPO_ROOT", tmp_path)
    interrupt = threading.Timer(
        0.15, os.kill, args=(os.getpid(), signal.SIGTERM)
    )
    interrupt.start()
    try:
        outcome, pending = phase9_runner.run_phase9_child(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            tmp_path / "interrupted.log",
            termination_grace_sec=0.2,
            kill_grace_sec=0.5,
        )
    finally:
        interrupt.cancel()
        interrupt.join(timeout=1)
    assert isinstance(pending, SystemExit)
    assert pending.code == 128 + signal.SIGTERM
    assert outcome["transport_classification"] == "controller_interrupted"
    assert outcome["controller_interrupted"] is True
    assert outcome["process_group_gone"] is True
    assert outcome["process_exit_observed"] is True


def test_joined_publication_reuses_canonical_batch_after_interruption(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(phase9_runner, "REPO_ROOT", tmp_path)
    state_path = tmp_path / "campaign/operator_state.json"
    state_path.parent.mkdir(parents=True)
    state = {
        "state_sha256": "1" * 64,
        "run_plan_sha256": "2" * 64,
        "dps_acceptance_state_sha256": "3" * 64,
        "run_plan": "campaign/run_plan.json",
    }
    verification = {"verification_sha256": "4" * 64}
    closure = {"closure_sha256": "5" * 64}
    calls = {"capture": 0, "publish": 0, "reconstruct": 0}
    stored_reconstruction: dict = {}

    monkeypatch.setattr(
        phase9_runner,
        "build_joined_campaign_closure",
        lambda *_args, **_kwargs: closure,
    )

    def fake_capture(batch_root: Path, *, batch_id: str, **_kwargs):
        calls["capture"] += 1
        (batch_root / "raw").mkdir(parents=True)
        (batch_root / "compact").mkdir(parents=True)
        manifest = {
            "schema": "bot_immutable_batch_manifest_v1",
            "batch_id": batch_id,
            "raw": {"bundle_sha256": "a" * 64},
            "compact": {"bundle_sha256": "b" * 64},
        }
        manifest["identity_sha256"] = canonical_sha256(manifest)
        phase9_runner.write_json(
            batch_root / "retained/final_manifest.json", manifest
        )
        return manifest

    def fake_publish(_repository: Path, batch_root: Path):
        calls["publish"] += 1
        manifest = phase9_runner.read_json(
            batch_root / "retained/final_manifest.json"
        )
        receipt = {
            "schema": "bot_immutable_batch_publication_receipt_v1",
            "batch_id": manifest["batch_id"],
            "batch_identity_sha256": manifest["identity_sha256"],
            "raw_bundle_sha256": "a" * 64,
            "compact_bundle_sha256": "b" * 64,
            "remote_verified": True,
            "pointers": [],
        }
        receipt["receipt_sha256"] = canonical_sha256(receipt)
        phase9_runner.write_json(
            batch_root / "retained/publication_receipt.json", receipt
        )
        return receipt

    monkeypatch.setattr(phase9_runner, "capture_batch", fake_capture)
    monkeypatch.setattr(phase9_runner, "publish_batch", fake_publish)
    monkeypatch.setattr(
        phase9_runner,
        "valid_reconstruction_receipt",
        lambda *_args, **_kwargs: (
            (True, stored_reconstruction)
            if stored_reconstruction
            else (False, {})
        ),
    )

    def fake_reconstruct(*_args, **_kwargs):
        calls["reconstruct"] += 1
        if calls["reconstruct"] == 1:
            raise RuntimeError("synthetic crash after outer publication")
        stored_reconstruction.update(
            {
                "receipt_sha256": "6" * 64,
                "remote_reconstructed": True,
                "targeted_eviction_complete": True,
            }
        )
        return dict(stored_reconstruction)

    monkeypatch.setattr(
        phase9_runner,
        "verify_remote_reconstruction_and_evict",
        fake_reconstruct,
    )
    bootstrap = {"bootstrap_sha256": "7" * 64}
    monkeypatch.setattr(
        phase9_runner,
        "build_outer_bootstrap",
        lambda *_args, **_kwargs: bootstrap,
    )

    def fake_write_bootstrap(_repository: Path, _bootstrap: dict) -> Path:
        path = tmp_path / "experiments/evidence_indexes/joined/bootstrap.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(bootstrap), encoding="utf-8")
        return path

    monkeypatch.setattr(
        phase9_runner, "write_outer_bootstrap", fake_write_bootstrap
    )
    with pytest.raises(RuntimeError, match="synthetic crash"):
        phase9_runner.publish_joined_campaign(
            state_path, state, verification
        )
    pending = phase9_runner.publish_joined_campaign(
        state_path, state, verification
    )
    repeated = phase9_runner.publish_joined_campaign(
        state_path, state, verification
    )
    assert pending == repeated
    assert pending["passed"] is False
    assert pending["status"] == "pending_committed_bootstrap_fresh_checkout_audit"
    assert pending["batch_path"] == "campaign/joined_campaign_promotion_batch"
    assert not (tmp_path / "campaign/joined_campaign_promotion_batch-retry-01").exists()
    assert calls == {"capture": 1, "publish": 1, "reconstruct": 2}


def test_committed_bootstrap_audit_uses_fresh_clean_worktree(
    tmp_path: Path, monkeypatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    (repository / ".gitignore").write_text(
        ".dvc/config.local\n", encoding="utf-8"
    )
    local_config = repository / ".dvc/config.local"
    local_config.parent.mkdir(parents=True)
    local_config.write_bytes(b"[remote \"sentinel\"]\npassword = secret\n")
    subprocess.run(
        ["git", "config", "user.email", "test@example.invalid"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Focused Test"],
        cwd=repository,
        check=True,
    )
    bootstrap_path = repository / "experiments/evidence_indexes/campaign/bootstrap.json"
    bootstrap_path.parent.mkdir(parents=True)
    bootstrap_path.write_text('{"bootstrap_sha256":"a"}\n', encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repository, check=True)
    subprocess.run(
        ["git", "commit", "-q", "-m", "bootstrap"],
        cwd=repository,
        check=True,
    )
    monkeypatch.setattr(
        phase9_runner,
        "verify_joined_campaign_bootstrap",
        lambda _bootstrap: {
            "passed": True,
            "bootstrap_sha256": "a",
            "closure_sha256": "b" * 64,
        },
    )

    audited_checkout: list[Path] = []

    def fake_clean_reconstruct(checkout: Path, checkout_bootstrap: Path) -> dict:
        audited_checkout.append(checkout)
        assert checkout.resolve() != repository.resolve()
        assert checkout_bootstrap.read_bytes() == bootstrap_path.read_bytes()
        copied_config = checkout / ".dvc/config.local"
        assert copied_config.read_bytes() == local_config.read_bytes()
        assert copied_config.stat().st_mode & 0o777 == 0o600
        status = subprocess.run(
            ["git", "status", "--porcelain=v1", "--untracked-files=all"],
            cwd=checkout,
            text=True,
            capture_output=True,
            check=True,
        )
        assert status.stdout == ""
        return {
            "receipt_sha256": "c" * 64,
            "remote_reconstructed": True,
            "targeted_eviction_complete": True,
            "domain_verification": {
                "verified": True,
                "closure_sha256": "b" * 64,
                "verified_dps_logical_qualifications": 16,
                "verified_phase9_player_like_clears": 14,
                "accepted_leaf_remote_reconstructions": 30,
                "accepted_leaf_targeted_eviction_complete": True,
            },
        }

    monkeypatch.setattr(
        phase9_runner,
        "reconstruct_outer_from_bootstrap",
        fake_clean_reconstruct,
    )
    audit = phase9_runner.audit_committed_joined_bootstrap(
        repository, bootstrap_path
    )
    assert audit["fresh_checkout_clean_before_and_after"] is True
    assert audit["accepted_leaf_remote_reconstructions"] == 30
    assert local_config.is_file()
    assert len(audited_checkout) == 1
    assert not audited_checkout[0].exists()
    local_config_bytes = local_config.read_bytes()
    local_config.unlink()
    with pytest.raises(ValueError, match="local DVC auth config"):
        phase9_runner.audit_committed_joined_bootstrap(
            repository, bootstrap_path
        )
    local_config.write_bytes(local_config_bytes)
    (repository / "dirty.txt").write_text("dirty\n", encoding="utf-8")
    with pytest.raises(ValueError, match="clean Git checkout"):
        phase9_runner.audit_committed_joined_bootstrap(
            repository, bootstrap_path
        )


def test_joined_promotion_resume_is_idempotent_after_fresh_audit(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(phase9_runner, "REPO_ROOT", tmp_path)
    root = tmp_path / "campaign"
    state_path = root / "operator_state.json"
    state = {
        "schema": "phase9_serial_canary_operator_state_v3",
        "status": "passed",
    }
    state["state_sha256"] = canonical_sha256(state)
    phase9_runner.write_json(state_path, state)
    bootstrap_path = tmp_path / "experiments/evidence_indexes/joined/bootstrap.json"
    phase9_runner.write_json(bootstrap_path, {"bootstrap_sha256": "7" * 64})
    pending = {
        "schema": "phase9_joined_campaign_promotion_pending_v1",
        "passed": False,
        "status": "pending_committed_bootstrap_fresh_checkout_audit",
        "state_path": "campaign/operator_state.json",
        "state_sha256": state["state_sha256"],
        "verification_sha256": "4" * 64,
        "closure_sha256": "5" * 64,
        "batch_path": "campaign/joined_campaign_promotion_batch",
        "bootstrap_path": "experiments/evidence_indexes/joined/bootstrap.json",
        "bootstrap_sha256": "7" * 64,
        "publication_receipt_sha256": "8" * 64,
        "reconstruction_receipt_sha256": "9" * 64,
    }
    pending["pending_sha256"] = canonical_sha256(pending)
    phase9_runner.write_json(root / phase9_runner.JOINED_PENDING_PROMOTION, pending)
    monkeypatch.setattr(
        phase9_runner,
        "verify_joined_campaign_bootstrap",
        lambda _bootstrap: {
            "passed": True,
            "bootstrap_sha256": "7" * 64,
            "closure_sha256": "5" * 64,
        },
    )
    audit = {
        "schema": "phase9_joined_campaign_fresh_checkout_audit_v1",
        "audit_sha256": "a" * 64,
    }
    monkeypatch.setattr(
        phase9_runner,
        "audit_committed_joined_bootstrap",
        lambda *_args, **_kwargs: audit,
    )
    first = phase9_runner.resume_joined_campaign_promotion(state_path)
    second = phase9_runner.resume_joined_campaign_promotion(state_path)
    assert first == second
    assert first["passed"] is True
    assert first["fresh_checkout_audit"] == audit


def accepted_phase9_row(index: int, physical_try_ordinal: int = 1) -> dict:
    combination_index = (index - 1) // 2 + 1
    row = {
        "serial_index": index,
        "logical_attempt_id": f"logical-attempt-{index}",
        "attempt_id": f"logical-attempt-{index}/try-{physical_try_ordinal:02d}",
        "cohort_id": f"cohort-{index}-try-{physical_try_ordinal}",
        "attempt_index": (physical_try_ordinal - 1) * 14 + index,
        "physical_try_ordinal": physical_try_ordinal,
        "physical_identity_sha256": f"{index + 300:064x}",
        "composition_id": f"composition-{combination_index}",
        "clear_ordinal": (index - 1) % 2 + 1,
        "success_ordinal": (index - 1) % 2 + 1,
        "reconstruction_receipt_sha256": f"{index:064x}",
        "remote_source_report_sha256": f"{index + 100:064x}",
        "child_returncode_observed": True,
        "returncode": 0,
        "transport_classification": "child_exited",
        "execution_policy": "run_to_completion",
        "overall_wall_clock_timeout_sec": None,
        "outer_timed_out": False,
        "controller_interrupted": False,
        "process_group_gone": True,
        "report_returncode": 0,
        "timed_out": False,
        "remote_verified": True,
        "remote_reconstruction_verified": True,
        "remote_domain_verified": True,
        "remote_transport_verified": True,
        "targeted_eviction_complete": True,
        "exact_party_verified": True,
        "heroic_admission_verified": True,
        "heroic_admission_receipt_sha256": f"{index + 200:064x}",
        "server_route_start_provisioned": True,
        "identity_matches": True,
        "cleanup_complete": True,
        "classification": "accepted",
        "passed": True,
    }
    assert phase9_attempt_accepted(row)
    return row


def logical_phase9_attempt(tmp_path: Path, serial_index: int = 1) -> dict:
    return {
        "attempt_id": "phase9_combo_01_clear_1_composition-1",
        "serial_index": serial_index,
        "combination_index": 1,
        "clear_ordinal": 1,
        "composition_id": "composition-1",
        "cohort_id": "phase9-serial-canary",
        "composition_sha256": "a" * 64,
        "ordered_party": ["tank", "healer", "dps1", "dps2", "dps3"],
        "party_sha256": "b" * 64,
        "execution_policy": "run_to_completion",
        "overall_wall_clock_timeout_sec": None,
        "output_dir": str(Path("runs") / "logical-01"),
        "command": [
            "pixi",
            "run",
            "python",
            "-m",
            "tools.bot_ml.run_live_bot_validation",
            "--cohort-id",
            "phase9-serial-canary",
            "--session-attempt-index",
            str(serial_index),
            "--output-dir",
            str(tmp_path / "unused"),
        ],
    }


def normal_phase9_child_execution(returncode: int = 0) -> dict:
    return {
        "returncode": returncode,
        "returncode_observed": True,
        "transport_classification": "child_exited",
        "execution_policy": "run_to_completion",
        "overall_wall_clock_timeout_sec": None,
        "outer_timed_out": False,
        "controller_interrupted": False,
        "process_group_id": 123,
        "process_group_terminate_sent": False,
        "process_group_kill_sent": False,
        "process_group_gone": True,
        "process_group_isolated": True,
        "process_exit_observed": True,
        "outer_timeout_sec": None,
    }


def test_phase9_live_qualification_matches_targeted_25h_roster(tmp_path: Path) -> None:
    matrix = build_matrix(TARGETS, POLICY)
    assert matrix["canonical_target_count"] == 31
    assert matrix["target_count"] == 24
    assert matrix["qualification_excluded_targets"] == TARGETED_EXCLUSIONS
    assert matrix["uncovered_pair_count"] == 0
    assert not (set(TARGETED_EXCLUSIONS) & set(matrix["serial_target_union"]))
    assert {
        row["ordered_party"][0] for row in matrix["serial_canaries"]
    } == {"blood_death_knight", "feral_druid_tank", "protection_paladin"}
    assert matrix["serial_canary_count"] == 7
    assert all(
        {"marksmanship_hunter", "survival_hunter"}
        & set(row["ordered_party"])
        for row in matrix["serial_canaries"]
    )

    generated = tmp_path / "matrix.json"
    generated.write_text(json.dumps(matrix, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    report = verify(TARGETS, POLICY, generated)
    assert report["passed"] is True


def test_phase9_serial_plan_covers_targeted_specs_and_protection_regression(tmp_path: Path) -> None:
    dps_state = tmp_path / "campaign_state.json"
    dps_state.write_text("{}\n", encoding="utf-8")
    plan = build_plan(
        MATRIX,
        ROOT / "artifacts/all_spec_program/test_phase9_live_qualification_plan",
        ROOT / "artifacts/all_spec_program/test_phase9_live_qualification_identity.json",
        "phase9-live-qualification-test",
        "phase9-serial-canary",
        dps_state,
    )
    assert plan["canonical_target_count"] == 31
    assert plan["qualification_excluded_targets"] == TARGETED_EXCLUSIONS
    assert plan["target_union_count"] == 24
    assert plan["matrix_execution_scope"] == "pinned_seven_serial_canary_combinations_twice"
    assert plan["combination_count"] == 7
    assert plan["required_successes_per_combination"] == 2
    assert plan["server_provisions_route_start_each_attempt"] is True
    assert plan["publish_each_closed_batch"] is True
    assert plan["remote_verify_before_evict"] is True
    assert plan["retain_published_batch"] is False
    assert plan["promotion_requires_dps_acceptance"] is True
    assert plan["execution_policy"] == "run_to_completion"
    assert plan["overall_wall_clock_timeout_sec"] is None
    assert plan["retry_policy"] == "unlimited_physical_tries_until_terminal_success"
    assert tuple(plan["terminal_conditions"]) == (
        "strict_route_clear",
        "server_attributed_machine_failure",
        "semantic_progress_plateau_watchdog",
        "no_progress_watchdog",
        "repeated_decision_watchdog",
        "death_loop_watchdog",
        "controller_interruption",
    )
    assert "timeout_sec" not in plan
    assert all(
        "--run-to-completion" in attempt["command"]
        and "--timeout-sec" not in attempt["command"]
        and attempt["execution_policy"] == "run_to_completion"
        and attempt["overall_wall_clock_timeout_sec"] is None
        for attempt in plan["attempts"]
    )
    assert plan["dps_acceptance_state_sha256"]
    assert not (set(TARGETED_EXCLUSIONS) & set(plan["target_union"]))
    assert all(
        "--reset-bot-pool" not in attempt["command"]
        for attempt in plan["attempts"]
    )
    assert all(
        "--retain-published-batch" not in attempt["command"]
        for attempt in plan["attempts"]
    )
    assert all(
        attempt["command"][attempt["command"].index("--party-pool-tag") + 1]
        == "all_spec_candidate_pool"
        for attempt in plan["attempts"]
    )
    matrix = json.loads(MATRIX.read_text(encoding="utf-8"))
    assert [row["composition_id"] for row in plan["attempts"]] == [
        row["composition_id"]
        for row in matrix["serial_canaries"]
        for _clear_ordinal in (1, 2)
    ]
    assert [row["clear_ordinal"] for row in plan["attempts"]] == [1, 2] * 7
    assert len(plan["attempts"]) == matrix["serial_canary_count"] * 2 == 14


def test_phase9_campaign_gate_rejects_passing_slices_and_duplicates() -> None:
    rows = [accepted_phase9_row(index) for index in range(1, 15)]
    assert exact_phase9_campaign_coverage(rows)
    assert not exact_phase9_campaign_coverage(rows[:1])
    duplicate = [dict(row) for row in rows]
    duplicate[-1]["remote_source_report_sha256"] = duplicate[0][
        "remote_source_report_sha256"
    ]
    assert not exact_phase9_campaign_coverage(duplicate)


def test_phase9_physical_try_identity_binds_slot_retry_and_runtime_command(
    tmp_path: Path,
) -> None:
    logical = logical_phase9_attempt(tmp_path, serial_index=3)
    first = phase9_physical_attempt(logical, 1)
    retry = phase9_physical_attempt(logical, 2)
    assert first["success_ordinal"] == retry["success_ordinal"] == 1
    assert first["composition_id"] == retry["composition_id"] == "composition-1"
    assert first["attempt_index"] == 3
    assert retry["attempt_index"] == 17
    assert first["attempt_id"].endswith("/try-01")
    assert retry["attempt_id"].endswith("/try-02")
    assert first["physical_identity_sha256"] != retry["physical_identity_sha256"]

    retry_dir = tmp_path / "runs/logical-01-retry-01"
    command = phase9_physical_command(logical, retry, retry_dir)
    assert command[command.index("--session-attempt-index") + 1] == "17"
    assert command[command.index("--cohort-id") + 1] == retry["cohort_id"]
    assert command[command.index("--output-dir") + 1] == str(retry_dir)


def test_phase9_sequence_keeps_failures_and_rejects_any_try_after_success() -> None:
    first = accepted_phase9_row(1)
    first.update(
        {
            "classification": "process_failure",
            "passed": False,
            "returncode": 1,
        }
    )
    second = accepted_phase9_row(1, physical_try_ordinal=2)
    assert phase9_physical_sequence_findings(
        [first, second], materialized_count=2
    ) == []
    third = accepted_phase9_row(1, physical_try_ordinal=3)
    assert phase9_physical_sequence_findings(
        [first, second, third], materialized_count=3
    ) == ["multiple_successful_physical_tries", "physical_try_after_success"]
    accepted_first = accepted_phase9_row(1)
    assert phase9_physical_sequence_findings(
        [accepted_first, second], materialized_count=2
    ) == ["multiple_successful_physical_tries", "physical_try_after_success"]


def test_phase9_retry_sequence_has_no_retry_ceiling_and_keeps_watchdog_failures() -> None:
    failures = []
    for ordinal in range(1, 51):
        row = accepted_phase9_row(1, physical_try_ordinal=ordinal)
        row.update(
            {
                "classification": "terminal_liveness_failure",
                "passed": False,
                "timed_out": True,
            }
        )
        failures.append(row)
    success = accepted_phase9_row(1, physical_try_ordinal=51)
    rows = [*failures, success]
    assert phase9_physical_sequence_findings(
        rows, materialized_count=len(rows)
    ) == []

    logical = logical_phase9_attempt(Path("/tmp"), serial_index=1)
    physical = phase9_physical_attempt(logical, 10_000)
    assert physical["physical_try_ordinal"] == 10_000
    assert physical["attempt_index"] == (9_999 * 14) + 1

    semantic_stall = accepted_phase9_row(1)
    semantic_stall.update(
        {
            "returncode": 1,
            "report_completion_reason": "semantic_progress_plateau_watchdog",
            "classification": "terminal_liveness_failure",
            "passed": False,
        }
    )
    assert classify_phase9_physical_try(semantic_stall) == (
        "terminal_liveness_failure"
    )


def test_phase9_source_transport_fails_closed_on_missing_or_spoofed_outcome() -> None:
    valid = {
        "returncode": 0,
        "timed_out": False,
        "acceptable_final_evidence": True,
        "all_passed": True,
    }
    assert phase9_source_transport_verified(valid)
    for invalid in (
        {key: value for key, value in valid.items() if key != "returncode"},
        {**valid, "returncode": True},
        {**valid, "returncode": 1},
        {**valid, "timed_out": True},
        {**valid, "acceptable_final_evidence": False},
        {**valid, "all_passed": False},
    ):
        assert not phase9_source_transport_verified(invalid)
    interrupted = accepted_phase9_row(1)
    interrupted["child_returncode_observed"] = False
    interrupted["returncode"] = None
    assert classify_phase9_physical_try(interrupted) == "infrastructure_failure"
    assert not phase9_attempt_accepted(interrupted)
    boolean_returncode = accepted_phase9_row(1)
    boolean_returncode["returncode"] = False
    boolean_returncode["report_returncode"] = False
    assert not phase9_attempt_accepted(boolean_returncode)


def test_phase9_resume_ledger_scans_every_materialized_try(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(phase9_runner, "REPO_ROOT", tmp_path)
    logical = logical_phase9_attempt(tmp_path)
    attempts = [logical]
    base = tmp_path / logical["output_dir"]

    first = phase9_physical_attempt(logical, 1)
    first_dir = phase9_physical_try_directory(base, 1)
    first_dir.mkdir(parents=True)
    first_command = phase9_physical_command(logical, first, first_dir)
    first_started = write_phase9_physical_try_started(
        first_dir, logical, first, first_command
    )
    first_result = phase9_physical_result(
        logical_attempt=logical,
        physical=first,
        output_dir=first_dir,
        log_path=first_dir / "phase9_runner.log",
        child_returncode=2,
        receipt={},
        reconstruction_valid=False,
        reconstruction={},
        reconstruction_error="missing_publication",
        child_execution=normal_phase9_child_execution(2),
    )
    write_phase9_physical_try_result(first_dir, first_started, first_result)

    second = phase9_physical_attempt(logical, 2)
    second_dir = phase9_physical_try_directory(base, 2)
    second_dir.mkdir()
    second_command = phase9_physical_command(logical, second, second_dir)
    second_started = write_phase9_physical_try_started(
        second_dir, logical, second, second_command
    )
    (second_dir / "report.json").write_text(
        json.dumps({"returncode": 0, "timed_out": False}) + "\n",
        encoding="utf-8",
    )
    remote = {
        "verified": True,
        "exact_party_valid": True,
        "heroic_admission": {"verified": True},
        "heroic_admission_receipt_sha256": "c" * 64,
        "server_route_start_provisioned": True,
        "runtime_identity_valid": True,
        "cleanup_complete": True,
        "source_transport_verified": True,
        "source_report_sha256": "d" * 64,
        "compact_binding_sha256": "e" * 64,
    }
    second_result = phase9_physical_result(
        logical_attempt=logical,
        physical=second,
        output_dir=second_dir,
        log_path=second_dir / "phase9_runner.log",
        child_returncode=0,
        receipt={"remote_verified": True, "receipt_sha256": "f" * 64},
        reconstruction_valid=True,
        reconstruction={
            "receipt_sha256": "1" * 64,
            "domain_verification": remote,
        },
        reconstruction_error="",
        child_execution=normal_phase9_child_execution(),
    )
    write_phase9_physical_try_result(second_dir, second_started, second_result)

    ledger, findings = scan_phase9_physical_ledger(attempts)
    assert findings == []
    assert [row["classification"] for row in ledger] == [
        "process_failure",
        "accepted",
    ]
    assert [row["physical_try_ordinal"] for row in ledger] == [1, 2]

    third_dir = phase9_physical_try_directory(base, 3)
    third_dir.mkdir()
    _ledger, findings = scan_phase9_physical_ledger(attempts)
    assert any("materialized_try_not_classified" in row for row in findings)
    assert any("physical_try_after_success" in row for row in findings)


def test_phase9_resume_consumes_mkdir_only_ordinal_as_infrastructure_failure(
    tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.setattr(phase9_runner, "REPO_ROOT", tmp_path)
    logical = logical_phase9_attempt(tmp_path)
    base = tmp_path / logical["output_dir"]
    base.mkdir(parents=True)

    close_interrupted_phase9_tries(
        [logical],
        plan_sha256="a" * 64,
        identity={"manifest_sha256": "b" * 64},
    )
    started_path = base / phase9_runner.STARTED_RECEIPT
    result_path = base / phase9_runner.RESULT_RECEIPT
    started_bytes = started_path.read_bytes()
    result_bytes = result_path.read_bytes()
    started = json.loads(started_bytes)
    result_receipt = json.loads(result_bytes)
    result = result_receipt["result"]

    assert started["schema"] == "phase9_physical_try_recovered_reservation_v1"
    assert started["recovered_missing_prelaunch_receipt"] is True
    assert (
        started["child_launch_observation"]
        == "child_not_launched_or_observation_unknown"
    )
    assert result["classification"] == "infrastructure_failure"
    assert result["child_returncode_observed"] is False
    assert result["returncode"] is None
    assert result["resume_failure_reason"] == (
        "child_not_launched_or_observation_unknown"
    )
    assert result["physical_try_ordinal"] == 1

    ledger, findings = scan_phase9_physical_ledger([logical])
    assert findings == []
    assert len(ledger) == 1
    assert ledger[0]["classification"] == "infrastructure_failure"

    close_interrupted_phase9_tries(
        [logical],
        plan_sha256="a" * 64,
        identity={"manifest_sha256": "b" * 64},
    )
    assert started_path.read_bytes() == started_bytes
    assert result_path.read_bytes() == result_bytes


def test_phase9_retry_preserves_failed_attempt_directory(tmp_path: Path) -> None:
    base = tmp_path / "attempt"
    base.mkdir()
    retry = next_attempt_directory(base)
    assert retry.name == "attempt-retry-01"
    assert attempt_directory_matches(base, retry)
    retry.mkdir()
    assert next_attempt_directory(base).name == "attempt-retry-02"
    assert base.is_dir()


def test_stonecore_5h_attempt_cannot_promote_without_joined_campaign_gate(
    tmp_path: Path,
) -> None:
    report = {
        "schema": "bot_live_validation_report_v1",
        "returncode": 0,
        "timed_out": False,
        "stages": [{"stage": "full_clear", "missing": []}],
        "failure_labels": [],
        "validation_context": {"scenario_id": "stonecore_5h"},
        "validation_route_manifest": {},
        "evidence": {},
        "watchdog_state": {},
        "exact_party_class_specs": ["tank", "healer", "dps1", "dps2", "dps3"],
    }
    manifest = promotion_manifest(
        tmp_path / "report.json",
        tmp_path / "canonical.json",
        report,
    )
    assert manifest["accepted"] is False
    assert (
        "individual_stonecore_5h_report_not_promotable_use_joined_campaign_artifact"
        in manifest["final_evidence_rejections"]
    )


def test_native_phase9_gear_gate_matches_canonical_catalog() -> None:
    native_rows = {
        row["class_spec"]: {
            "gear_profile_id": row["gear_profile_id"],
            "manifest_sha256": row["gear_manifest_sha256"],
        }
        for row in build_identity_catalog()["identities"]
    }
    expected = expected_class_spec_gear_identities()
    assert set(native_rows) == set(expected)
    assert native_rows == {
        spec: {
            "gear_profile_id": identity["gear_profile_id"],
            "manifest_sha256": identity["manifest_sha256"],
        }
        for spec, identity in expected.items()
    }


def test_heroic_admission_receipt_binds_actions_roster_difficulty_and_entrance() -> None:
    targets = json.loads(TARGETS.read_text(encoding="utf-8"))["targets"]
    talent_spells = {
        target["spec_target_id"]: sorted(
            row["spell_id"] for row in target["provisioning_bot"]["talents"]
        )
        for target in targets
    }
    runtime_identities = {
        "blood_death_knight": (6, 398),
        "holy_paladin": (2, 831),
        "fire_mage": (8, 851),
        "combat_rogue": (4, 181),
        "marksmanship_hunter": (3, 807),
    }
    members = [
        {
            "guid": 100 + index,
            "group_guid": 900,
            "leader_guid": 100,
            "roster_slot_id": [
                "party_tank_1",
                "party_healer_1",
                "party_dps_1",
                "party_dps_2",
                "party_dps_3",
            ][index],
            "role": "tank" if index == 0 else "healer" if index == 1 else "dps",
            "class_spec": spec,
            "class_id": runtime_identities[spec][0],
            "active_spec_index": 0,
            "primary_talent_tree_id": runtime_identities[spec][1],
            "active_talent_count": len(talent_spells[spec]),
            "active_talent_spell_ids": talent_spells[spec],
            "pet_identity_present": False,
            "pet_id": 0,
            "pet_entry": 0,
            "pet_spell_count": 0,
            "pet_spellbook": [],
            "pet_spellbook_sha256": "",
            "map_id": 725,
            "instance_id": 77,
            "expected_difficulty": 1,
            "player_difficulty": 1,
            "map_difficulty": 1,
            "spawn_x": 851.052,
            "spawn_y": 986.474,
            "spawn_z": 317.266,
            "spawn_o": 0.0,
            "server_provisioned": True,
            "initial_alive_state_verified": True,
            "initial_baseline_normalized": True,
        }
        for index, spec in enumerate(
            [
                "blood_death_knight",
                "holy_paladin",
                "fire_mage",
                "combat_rogue",
                "marksmanship_hunter",
            ]
        )
    ]
    expected_hunter_pet = expected_class_spec_pet_identities()["marksmanship_hunter"]
    expected_gear = expected_class_spec_gear_identities()
    for member in members:
        gear = expected_gear[member["class_spec"]]
        member.update(
            {
                "gear_profile_id": gear["gear_profile_id"],
                "gear_item_count": len(gear["manifest"]),
                "gear_manifest": gear["manifest"],
                "gear_manifest_sha256": gear["manifest_sha256"],
                "current_gear_manifest_sha256": gear["manifest_sha256"],
                "gear_identity_current_matches_admission": True,
            }
        )
    members[4].update(
        {
            "pet_identity_present": True,
            "pet_id": expected_hunter_pet["pet_id"],
            "pet_entry": expected_hunter_pet["pet_entry"],
            "pet_spell_count": len(expected_hunter_pet["spellbook"]),
            "pet_spellbook": [
                {"spell_id": spell_id, "active": active}
                for spell_id, active in expected_hunter_pet["spellbook"]
            ],
            "pet_spellbook_sha256": expected_hunter_pet["spellbook_sha256"],
        }
    )
    status = {
        "attempt_id": 42,
        "profile_generation": 8,
        "profile_content_hash": "a" * 64,
        "raid_runtime": {
            "admission_phase": "active",
            "server_provisioning_complete": True,
            "bot_actions_enabled": True,
            "difficulty_matches": True,
            "expected_difficulty": 1,
            "group_difficulty": 1,
            "map_difficulty": 1,
            "expected_size": 5,
            "group_guid": 900,
            "leader_guid": 100,
            "instance_id": 77,
            "admission_receipt": {
                "attempt_id": 42,
                "bot_actions_enabled_at_commit": True,
                    "scenario_id": "stonecore_5h",
                    "runtime_profile": "stonecore_5h",
                    "identity_catalog_source_sha256":
                        expected_admission_identity_source_sha256(),
                "route_manifest_sha256": "B" * 64,
                "recovery_entrance_area_trigger_id": 6196,
                "recovery_entrance_source_map_id": 646,
                "recovery_entrance_target_map_id": 725,
                "entrance_map_id": 725,
                "entrance_x": 851.052,
                "entrance_y": 986.474,
                "entrance_z": 317.266,
                "entrance_o": 0.0,
                "profile_generation": 8,
                "profile_content_hash": "a" * 64,
                "leader_guid": 100,
                "all_current_gear_matches_admission": True,
                "members": members,
            },
        },
    }
    admission_contract = {
        "expected_start": (851.052, 986.474, 317.266),
        "expected_route_manifest_sha256": "b" * 64,
        "expected_recovery_entrance": (6196, 646, 725),
    }

    accepted = validate_heroic_admission_receipt(
        status,
        expected_class_specs=[member["class_spec"] for member in members],
        **admission_contract,
    )
    assert accepted["verified"] is True

    original_item_id = members[0]["gear_manifest"][0]["item_id"]
    members[0]["gear_manifest"][0]["item_id"] = original_item_id + 1
    tampered_non_hunter_gear = validate_heroic_admission_receipt(
        status,
        expected_class_specs=[member["class_spec"] for member in members],
        **admission_contract,
    )
    assert tampered_non_hunter_gear["verified"] is False
    assert "member_gear_manifest_mismatch" in tampered_non_hunter_gear["failure_reasons"]
    assert "member_gear_manifest_hash_mismatch" in tampered_non_hunter_gear["failure_reasons"]

    forged_hash = canonical_sha256(members[0]["gear_manifest"])
    members[0]["gear_manifest_sha256"] = forged_hash
    members[0]["current_gear_manifest_sha256"] = forged_hash
    forged_non_hunter_gear = validate_heroic_admission_receipt(
        status,
        expected_class_specs=[member["class_spec"] for member in members],
        **admission_contract,
    )
    assert forged_non_hunter_gear["verified"] is False
    assert "member_gear_manifest_mismatch" in forged_non_hunter_gear["failure_reasons"]
    assert "member_gear_manifest_hash_mismatch" in forged_non_hunter_gear["failure_reasons"]
    members[0]["gear_manifest"][0]["item_id"] = original_item_id
    members[0]["gear_manifest_sha256"] = expected_gear[members[0]["class_spec"]][
        "manifest_sha256"
    ]
    members[0]["current_gear_manifest_sha256"] = members[0][
        "gear_manifest_sha256"
    ]

    members[0]["current_gear_manifest_sha256"] = "f" * 64
    members[0]["gear_identity_current_matches_admission"] = False
    status["raid_runtime"]["admission_receipt"][
        "all_current_gear_matches_admission"
    ] = False
    drifted_live_gear = validate_heroic_admission_receipt(
        status,
        expected_class_specs=[member["class_spec"] for member in members],
        **admission_contract,
    )
    assert drifted_live_gear["verified"] is False
    assert "member_current_gear_identity_drift" in drifted_live_gear["failure_reasons"]
    assert "admission_current_gear_identity_unverified" in drifted_live_gear[
        "failure_reasons"
    ]
    members[0]["current_gear_manifest_sha256"] = members[0][
        "gear_manifest_sha256"
    ]
    members[0]["gear_identity_current_matches_admission"] = True
    status["raid_runtime"]["admission_receipt"][
        "all_current_gear_matches_admission"
    ] = True

    members[4]["primary_talent_tree_id"] = 813
    wrong_loaded_spec = validate_heroic_admission_receipt(
        status,
        expected_class_specs=[member["class_spec"] for member in members],
        **admission_contract,
    )
    assert wrong_loaded_spec["verified"] is False
    assert "member_runtime_spec_identity_mismatch" in wrong_loaded_spec["failure_reasons"]
    members[4]["primary_talent_tree_id"] = 807

    removed_talent_spell = members[4]["active_talent_spell_ids"].pop()
    members[4]["active_talent_count"] -= 1
    wrong_talent_build = validate_heroic_admission_receipt(
        status,
        expected_class_specs=[member["class_spec"] for member in members],
        **admission_contract,
    )
    assert wrong_talent_build["verified"] is False
    assert "member_active_talent_identity_mismatch" in wrong_talent_build["failure_reasons"]
    members[4]["active_talent_spell_ids"].append(removed_talent_spell)
    members[4]["active_talent_spell_ids"].sort()
    members[4]["active_talent_count"] += 1

    members[4]["pet_entry"] = 1
    wrong_hunter_pet = validate_heroic_admission_receipt(
        status,
        expected_class_specs=[member["class_spec"] for member in members],
        **admission_contract,
    )
    assert wrong_hunter_pet["verified"] is False
    assert "member_hunter_pet_identity_mismatch" in wrong_hunter_pet["failure_reasons"]
    members[4]["pet_entry"] = expected_hunter_pet["pet_entry"]

    removed_pet_spell = members[4]["pet_spellbook"].pop()
    members[4]["pet_spell_count"] -= 1
    stale_hunter_spellbook = validate_heroic_admission_receipt(
        status,
        expected_class_specs=[member["class_spec"] for member in members],
        **admission_contract,
    )
    assert stale_hunter_spellbook["verified"] is False
    assert "member_hunter_pet_identity_mismatch" in stale_hunter_spellbook["failure_reasons"]
    assert (
        "member_hunter_pet_spellbook_hash_mismatch"
        in stale_hunter_spellbook["failure_reasons"]
    )
    members[4]["pet_spellbook"].append(removed_pet_spell)
    members[4]["pet_spellbook"].sort(key=lambda row: row["spell_id"])
    members[4]["pet_spell_count"] += 1

    members[0]["pet_identity_present"] = True
    non_hunter_pet = validate_heroic_admission_receipt(
        status,
        expected_class_specs=[member["class_spec"] for member in members],
        **admission_contract,
    )
    assert non_hunter_pet["verified"] is False
    assert "non_hunter_pet_identity_fabricated" in non_hunter_pet["failure_reasons"]
    members[0]["pet_identity_present"] = False

    members[4]["role"] = "healer"
    wrong_role = validate_heroic_admission_receipt(status, **admission_contract)
    assert wrong_role["verified"] is False
    assert "admission_role_shape_mismatch" in wrong_role["failure_reasons"]
    members[4]["role"] = "dps"

    members[4]["spawn_x"] = 900.0
    rejected = validate_heroic_admission_receipt(status, **admission_contract)
    assert rejected["verified"] is False
    assert "member_not_provisioned_at_dungeon_entrance" in rejected["failure_reasons"]
