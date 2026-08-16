from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

import tools.bot_ml.run_cata_raid_dps_acceptance as dps_runner
from tools.bot_ml.live_validation_session import (
    EVIDENCE_ARTIFACT_HASHES,
    EVIDENCE_HASH_COMPONENTS,
    EVIDENCE_SCOPE_IDS,
    build_evidence_envelope,
    canonical_sha256,
)
from tools.bot_ml.phase8_evidence_identity import (
    build_projection as phase8_build_projection,
    profile_generation_identity,
    server_epoch_identity,
)
from tools.bot_ml.phase8_calibration_adapter import (
    Phase8CalibrationNormalizationError,
    expected_gear_manifest,
    normalize_runtime_calibration,
)
from tools.bot_ml.run_cata_raid_dps_acceptance import (
    acceptance_targets,
    attempt_accepted,
    calibration_reconstruction_identity,
    campaign_attempts,
    child_command,
    classify_physical_try,
    discovered_physical_try_paths,
    load_physical_try_result,
    load_physical_try_started,
    physical_attempt,
    physical_sequence_findings,
    physical_try_dir,
    targeted_eviction_complete,
    verify_hydrated_calibration,
    write_physical_try_result,
    write_physical_try_started,
    write_recovered_physical_try_reservation,
    write_campaign_state,
)
from tools.bot_ml.run_live_bot_validation import session_output_dir_available
from tools.bot_ml.verify_cata_raid_dps_acceptance import gear_profile_binding, verify


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/cata_raid_dps_acceptance_v1.json"


def test_session_child_accepts_only_controller_prelaunch_files(tmp_path: Path) -> None:
    attempt_dir = tmp_path / "attempt"
    assert session_output_dir_available(attempt_dir) is True

    attempt_dir.mkdir()
    (attempt_dir / "runner.log").write_text("", encoding="utf-8")
    assert session_output_dir_available(attempt_dir) is False
    (attempt_dir / "physical_try_started.json").write_text(
        "{}\n", encoding="utf-8"
    )
    assert session_output_dir_available(attempt_dir) is True

    (attempt_dir / "runner.log").unlink()
    (attempt_dir / "physical_try_started.json").unlink()
    (attempt_dir / "phase9_runner.log").write_text("", encoding="utf-8")
    (attempt_dir / "phase9_physical_try_started.json").write_text(
        "{}\n", encoding="utf-8"
    )
    assert session_output_dir_available(attempt_dir) is True

    (attempt_dir / "runner.log").write_text("", encoding="utf-8")
    assert session_output_dir_available(attempt_dir) is False
    (attempt_dir / "runner.log").unlink()

    (attempt_dir / "physical_try_result.json").write_text(
        "{}\n", encoding="utf-8"
    )
    assert session_output_dir_available(attempt_dir) is False


def test_session_child_preflight_accepts_dps_controller_reservation(
    tmp_path: Path,
) -> None:
    attempt_dir = tmp_path / "attempt"
    attempt_dir.mkdir()
    (attempt_dir / "runner.log").write_text("", encoding="utf-8")
    (attempt_dir / "physical_try_started.json").write_text(
        "{}\n", encoding="utf-8"
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.bot_ml.run_live_bot_validation",
            "--transport",
            "session",
            "--output-dir",
            str(attempt_dir),
            "--validation-route-sequence",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode != 0
    assert "--validation-route-sequence requires --validation-scenario-id" in completed.stderr
    assert "requires a new or empty --output-dir" not in completed.stderr


def _phase8_v2_manifest(
    *, git_commit: str = "d" * 40, worldserver_binary_sha256: str = "e" * 64
) -> dict[str, object]:
    server = server_epoch_identity(
        server_epoch=11,
        server_process_id=22,
        session_fingerprint="phase8-v2-real-session",
    )
    profile = profile_generation_identity(
        profile_generation=1,
        profile_content_hash="c" * 64,
    )
    build = {
        "git_commit": git_commit,
        "source_tree_clean": True,
        "worldserver_binary_sha256": worldserver_binary_sha256,
        "database_snapshot_sha256": "a" * 64,
        "database_schema_sha256": "b" * 64,
        "profile_content_hash": profile["profile_content_hash"],
    }
    projection = phase8_build_projection({"build_identity": build})
    manifest: dict[str, object] = {
        "schema": "all_spec_phase8_evidence_identity_manifest_v2",
        "component_hashes": {
            "source_identity_sha256": canonical_sha256(
                {"git_commit": build["git_commit"], "source_tree_clean": True}
            ),
            "worldserver_binary_sha256": build["worldserver_binary_sha256"],
            "database_snapshot_sha256": build["database_snapshot_sha256"],
            "database_schema_sha256": build["database_schema_sha256"],
            "server_epoch_sha256": canonical_sha256(server),
            "profile_generation_sha256": canonical_sha256(profile),
            "build_projection_sha256": canonical_sha256(projection),
        },
        "build_identity": build,
        "runtime_identity": {**server, **profile},
        "database_summary": {},
    }
    manifest["manifest_sha256"] = canonical_sha256(manifest)
    return manifest


def _real_phase8_envelope(
    manifest: dict[str, object], *, binary_sha256: str | None = None
) -> dict[str, object]:
    components = {
        name: canonical_sha256({"test_component": name})
        for name in EVIDENCE_HASH_COMPONENTS
    }
    components.update(dps_runner.phase8_envelope_build_projection(manifest))
    if binary_sha256 is not None:
        components["binary_sha256"] = binary_sha256
    envelope = build_evidence_envelope(
        components,
        {name: f"phase8-{name}" for name in EVIDENCE_SCOPE_IDS},
        {
            name: canonical_sha256({"test_artifact": name})
            for name in EVIDENCE_ARTIFACT_HASHES
        },
    )
    envelope["identity_manifest_sha256"] = manifest["manifest_sha256"]
    return envelope


def _accepted_result(physical: dict[str, object]) -> dict[str, object]:
    row = {
        **physical,
        "child_returncode_observed": True,
        "returncode": 0,
        "transport_classification": "child_exited",
        "outer_timeout_sec": 1800.0,
        "outer_timed_out": False,
        "controller_interrupted": False,
        "process_group_gone": True,
        "report_returncode": 0,
        "timed_out": False,
        "calibration_acceptance_passed": True,
        "acceptable_final_evidence": True,
        "all_passed": True,
        "remote_transport_verified": True,
        "remote_provenance_verified": True,
        "remote_evidence_class": "non_certifying_calibration_fixture",
        "remote_excluded_from_training_corpus": True,
        "remote_runtime_mode": "calibration_fixture",
        "remote_non_certifying_assistance": True,
        "published": True,
        "remote_reconstruction_verified": True,
        "passed": True,
        "hard_floor_passed": True,
        "optimization_target_met": True,
        "targeted_eviction_complete": True,
    }
    row["classification"] = classify_physical_try(row)
    row["accepted"] = attempt_accepted(row)
    return row


def _qualification_failure(physical: dict[str, object]) -> dict[str, object]:
    row = _accepted_result(physical)
    row.update(
        {
            "passed": False,
            "hard_floor_passed": False,
            "optimization_target_met": False,
            "acceptable_final_evidence": False,
            "all_passed": False,
        }
    )
    row["classification"] = classify_physical_try(row)
    row["accepted"] = attempt_accepted(row)
    return row


def test_current_25h_dps_contract_has_exact_75_85_gates() -> None:
    report = verify(CONFIG)

    assert report["passed"] is True
    assert report["supported_dps_spec_count"] == 16
    assert report["supported_specialization_target_count"] == 24
    assert report["attempt_count"] == 16
    assert report["qualification_mode"] == "single_target_300"
    assert report["qualification_seed"] == 1
    assert report["max_tries_per_dps_spec"] == 2
    assert report["hard_reference_ratio"] == 0.75
    assert report["optimization_reference_ratio"] == 0.85
    assert len(report["targets"]) == 16
    assert all(row["hard_floor_dps"] > 0 for row in report["targets"])
    assert all(
        row["optimization_target_dps"] > row["hard_floor_dps"]
        for row in report["targets"]
    )
    assert all(row["gear_profile_binding_verified"] for row in report["targets"])
    assert all(len(row["gear_manifest_sha256"]) == 64 for row in report["targets"])
    fire = next(row for row in report["targets"] if row["spec_target_id"] == "fire_mage")
    assert fire["gear_profile_id"] == "wowsims_cata_p4_fire_mage"


def test_dps_gate_rejects_gear_profile_identity_mismatch() -> None:
    target = {
        "gear_profile_id": "wowsims_cata_p4_fire_mage",
        "provisioning_bot": {
            "gear_profile_id": "wowsims_cata_p4_fire_mage",
            "gear_profile": "fire_mage",
        },
    }
    reference = {
        "gear": {
            "gear_profile_id": "wowsims_cata_p4_fire_mage",
            "runtime_profile_id": "wowsims_cata_p4_fire_mage",
        }
    }

    binding = gear_profile_binding(target, reference)

    assert binding["gear_profile_binding_verified"] is False
    assert binding["provisioning_gear_profile"] == "fire_mage"


def test_runtime_calibration_identity_carries_canonical_gear_profile_id() -> None:
    gear_profile_id = "wowsims_cata_p4_fire_mage"
    target = {
        "spec_target_id": "fire_mage",
        "runtime_join_key": "fire_mage",
        "role": "dps",
        "class_id": 8,
        "gear_profile_id": gear_profile_id,
        "provisioning_bot": {
            "gear_profile_id": gear_profile_id,
            "gear_profile": gear_profile_id,
        },
        "consumable_item_ids": [],
    }
    reference = {
        "reference_id": "cata_p4:fire_mage",
        "reference_conditions": {},
        "gear": {
            "gear_profile_id": gear_profile_id,
            "runtime_profile_id": gear_profile_id,
        },
        "expected_output": {"metrics": {"dps": 100.0}},
    }
    scenario = {"primary": {"scenario_id": "calibration:fire_mage:primary"}}
    quality = {
        "active_uptime_ratio": 1.0,
        "rotation_group_coverage": 1.0,
        "cast_failure_ratio": 0.0,
        "resource_capped_ratio": 0.0,
        "resource_starved_ratio": 0.0,
        "movement_range_loss_ratio": 0.0,
        "pet_damage_ratio": 0.0,
        "illegal_action_count": 0,
    }
    calibration = {
        "window_complete": True,
        "phase": "complete",
        "mode": "single_target_300",
        "target_spec": "fire_mage",
        "runtime_mode": "calibration_fixture",
        "non_certifying_assistance": True,
        "target_guid": 101,
        "seed": 1,
        "scored_seconds": 300,
        "warmup_seconds": 10,
        "scored_started_at_ms": 1_000,
        "scored_ended_at_ms": 301_000,
        "normalization": {},
        "fixture_target": {
            "isolated_single_target": True,
            "entry": 44548,
            "runtime_guid": 9001,
            "map_id": 0,
            "x": -9060.0,
            "y": 520.0,
            "z": 68.3695,
            "nearest_other_hostile_clearance": 46.7,
            "provisioned_at_ms": 500,
            "provisioned_before_scoring": True,
        },
        "previous_window": {
            "mode": "single_target_300",
            "bots": [{
                "guid": 101,
                "role": "dps",
                "class_id": 8,
                "dps": 90.0,
                "damage": 27_000,
                "primary_target_guid": 9001,
                "primary_target_damage": 27_000,
                "off_target_damage": 0,
                "observed_distinct_damage_targets": 1,
                "target_count": 1,
                "reference_setup": {},
                "quality_metrics": quality,
                "spell_damage": [],
                "gear_profile_observation": {
                    "items": list(expected_gear_manifest(gear_profile_id)),
                },
            }],
        },
    }

    record = normalize_runtime_calibration(
        calibration,
        target_row=target,
        reference_row=reference,
        scenario_row=scenario,
        mode="single_target_300",
    )

    assert record["identity"]["gear_profile_id"] == gear_profile_id
    assert len(record["identity"]["gear_manifest_sha256"]) == 64
    assert record["identity"]["target_sha256"] == canonical_sha256(target)

    calibration["previous_window"]["bots"][0]["gear_profile_observation"][
        "items"
    ][0]["item_id"] += 1
    with pytest.raises(
        Phase8CalibrationNormalizationError,
        match="runtime_gear_manifest_mismatch:wowsims_cata_p4_fire_mage",
    ):
        normalize_runtime_calibration(
            calibration,
            target_row=target,
            reference_row=reference,
            scenario_row=scenario,
            mode="single_target_300",
        )


def test_campaign_controller_lock_rejects_concurrent_process_before_launch(
    tmp_path: Path,
) -> None:
    output_root = tmp_path / "locked-campaign"

    with dps_runner.campaign_controller_lock(output_root):
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "tools.bot_ml.run_cata_raid_dps_acceptance",
                "--output-root",
                str(output_root),
            ],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )

    assert completed.returncode == 2
    assert "campaign controller lock is already held" in completed.stderr
    assert not (output_root / "campaign_plan.json").exists()
    assert not (output_root / "campaign_state.json").exists()


def test_phase8_launch_source_guard_rejects_dirty_tree_and_rebuilt_binary(
    tmp_path: Path,
) -> None:
    repository = tmp_path / "source"
    repository.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
    subprocess.run(
        ["git", "config", "user.email", "phase8-test@example.invalid"],
        cwd=repository,
        check=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Phase8 Test"],
        cwd=repository,
        check=True,
    )
    (repository / ".gitignore").write_text("worldserver\n", encoding="utf-8")
    tracked_source = repository / "source.txt"
    tracked_source.write_text("committed source\n", encoding="utf-8")
    subprocess.run(
        ["git", "add", ".gitignore", "source.txt"], cwd=repository, check=True
    )
    subprocess.run(
        ["git", "commit", "-q", "-m", "phase8 source"],
        cwd=repository,
        check=True,
    )
    git_commit = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=repository,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    worldserver = repository / "worldserver"
    worldserver.write_bytes(b"bound binary")
    manifest = _phase8_v2_manifest(
        git_commit=git_commit,
        worldserver_binary_sha256=hashlib.sha256(worldserver.read_bytes()).hexdigest(),
    )

    observed = dps_runner.require_current_phase8_source_identity(
        repository, worldserver, manifest
    )
    assert observed["git_commit"] == git_commit

    tracked_source.write_text("dirty source\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="requires a clean source tree"):
        dps_runner.require_current_phase8_source_identity(
            repository, worldserver, manifest
        )

    tracked_source.write_text("committed source\n", encoding="utf-8")
    worldserver.write_bytes(b"rebuilt stale binary")
    with pytest.raises(SystemExit, match="worldserver binary does not match"):
        dps_runner.require_current_phase8_source_identity(
            repository, worldserver, manifest
        )


def test_child_outer_timeout_is_an_immutable_consumed_infrastructure_try(
    tmp_path: Path,
) -> None:
    runner_log = tmp_path / "runner.log"
    with runner_log.open("w", encoding="utf-8") as stream:
        outcome, interruption = dps_runner.run_child_process_group(
            [sys.executable, "-c", "import time; time.sleep(60)"],
            cwd=ROOT,
            env={},
            output_stream=stream,
            timeout_sec=0.05,
            terminate_grace_sec=0.1,
            kill_grace_sec=0.5,
        )

    assert interruption is None
    assert outcome["transport_classification"] == "outer_timeout"
    assert outcome["outer_timed_out"] is True
    assert outcome["returncode_observed"] is True
    assert outcome["process_group_terminate_sent"] is True
    assert outcome["process_group_gone"] is True

    output_root = tmp_path / "campaign"
    logical = {
        "attempt_index": 1,
        "attempt_id": "qualification/timeout-demo",
        "cohort_id": "dps85-timeout-demo",
    }
    physical = physical_attempt(logical, 1)
    attempt_dir = physical_try_dir(output_root, logical, 1)
    attempt_dir.mkdir(parents=True)
    started = write_physical_try_started(
        attempt_dir, output_root, logical, physical, ["fake-child"]
    )
    result = dps_runner.bind_child_transport_result(
        _accepted_result(physical), outcome, timeout_sec=0.05
    )
    write_physical_try_result(attempt_dir, started, result)
    loaded, _receipt = load_physical_try_result(attempt_dir, started, physical)

    assert loaded["outer_timed_out"] is True
    assert loaded["timed_out"] is True
    assert loaded["transport_classification"] == "outer_timeout"
    assert loaded["classification"] == "infrastructure_failure"
    assert loaded["accepted"] is False


def test_child_outer_timeout_kills_ignoring_descendant_process_group(
    tmp_path: Path,
) -> None:
    descendant_pid_path = tmp_path / "descendant.pid"
    fake_child = tmp_path / "fake_child.py"
    fake_child.write_text(
        "import pathlib, signal, subprocess, sys, time\n"
        "signal.signal(signal.SIGTERM, signal.SIG_IGN)\n"
        "descendant = subprocess.Popen([\n"
        "    sys.executable, '-c',\n"
        "    'import signal, time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)',\n"
        "])\n"
        "pathlib.Path(sys.argv[1]).write_text(str(descendant.pid), encoding='utf-8')\n"
        "time.sleep(60)\n",
        encoding="utf-8",
    )
    runner_log = tmp_path / "orphan-runner.log"
    with runner_log.open("w", encoding="utf-8") as stream:
        outcome, interruption = dps_runner.run_child_process_group(
            [sys.executable, str(fake_child), str(descendant_pid_path)],
            cwd=tmp_path,
            env={},
            output_stream=stream,
            timeout_sec=0.3,
            terminate_grace_sec=0.1,
            kill_grace_sec=1.0,
        )

    assert interruption is None
    assert descendant_pid_path.is_file()
    descendant_pid = int(descendant_pid_path.read_text(encoding="utf-8"))
    assert outcome["transport_classification"] == "outer_timeout"
    assert outcome["process_group_terminate_sent"] is True
    assert outcome["process_group_kill_sent"] is True
    assert outcome["process_group_gone"] is True

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        stat_path = Path(f"/proc/{descendant_pid}/stat")
        try:
            state = stat_path.read_text(encoding="utf-8").split()[2]
        except (FileNotFoundError, IndexError, OSError):
            state = "gone"
        if state in {"gone", "Z"}:
            break
        time.sleep(0.02)
    assert state in {"gone", "Z"}


def test_controller_termination_signal_cleans_child_group_before_exit(
    tmp_path: Path,
) -> None:
    runner_log = tmp_path / "interrupted-runner.log"
    interrupt = threading.Timer(0.15, os.kill, args=(os.getpid(), signal.SIGTERM))
    interrupt.start()
    try:
        with runner_log.open("w", encoding="utf-8") as stream:
            outcome, pending_exit = dps_runner.run_child_process_group(
                [sys.executable, "-c", "import time; time.sleep(60)"],
                cwd=tmp_path,
                env={},
                output_stream=stream,
                timeout_sec=5,
                terminate_grace_sec=0.2,
                kill_grace_sec=0.5,
            )
    finally:
        interrupt.cancel()
        interrupt.join(timeout=1)

    assert isinstance(pending_exit, SystemExit)
    assert pending_exit.code == 128 + signal.SIGTERM
    assert outcome["transport_classification"] == "controller_interrupted"
    assert outcome["controller_interrupted"] is True
    assert outcome["controller_signal"] == signal.SIGTERM
    assert outcome["returncode_observed"] is True
    assert outcome["process_group_gone"] is True

def test_acceptance_plan_qualifies_each_unique_dps_spec_once() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    targets = acceptance_targets(config)
    attempts = campaign_attempts(
        targets,
        config["qualification_mode"],
        config["qualification_seed"],
    )

    assert len(attempts) == 16
    assert {row["spec_target_id"] for row in attempts} == set(
        config["dps_targets"]
    )
    assert {row["mode"] for row in attempts} == {"single_target_300"}
    assert {row["seed"] for row in attempts} == {1}


def test_physical_try_identity_and_directory_are_deterministic_and_unique(
    tmp_path: Path,
) -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    logical = campaign_attempts(
        acceptance_targets(config),
        config["qualification_mode"],
        config["qualification_seed"],
    )
    first = physical_attempt(logical[0], 1)
    retry = physical_attempt(logical[0], 2)
    next_spec = physical_attempt(logical[1], 1)

    assert first["attempt_id"] == f"{logical[0]['attempt_id']}/try-1"
    assert retry["attempt_id"] == f"{logical[0]['attempt_id']}/try-2"
    assert first["cohort_id"] == f"{logical[0]['cohort_id']}-try-1"
    assert retry["cohort_id"] == f"{logical[0]['cohort_id']}-try-2"
    assert [first["attempt_index"], retry["attempt_index"], next_spec["attempt_index"]] == [1, 2, 3]
    assert len(
        {
            first["physical_identity_sha256"],
            retry["physical_identity_sha256"],
            next_spec["physical_identity_sha256"],
        }
    ) == 3
    policy = ROOT / "experiments/configs/all_spec_role_calibration_policy_v2.json"
    manifest = {"manifest_sha256": "a" * 64}
    assert calibration_reconstruction_identity(first, policy, manifest) != (
        calibration_reconstruction_identity(retry, policy, manifest)
    )
    assert physical_try_dir(tmp_path, logical[0], 1).name == logical[0]["spec_target_id"]
    assert physical_try_dir(tmp_path, logical[0], 2).name.endswith("-retry-01")


def test_first_pass_stops_without_retry_and_fail_then_pass_is_valid() -> None:
    logical = {
        "attempt_index": 1,
        "attempt_id": "qualification/demo",
        "cohort_id": "dps85-demo",
    }
    first = physical_attempt(logical, 1)
    retry = physical_attempt(logical, 2)

    assert physical_sequence_findings(
        [_accepted_result(first)], materialized_count=1
    ) == []
    assert physical_sequence_findings(
        [_qualification_failure(first), _accepted_result(retry)],
        materialized_count=2,
    ) == []


def test_two_failures_are_classified_terminal_without_synthesizing_success() -> None:
    logical = {
        "attempt_index": 1,
        "attempt_id": "qualification/demo",
        "cohort_id": "dps85-demo",
    }
    rows = [
        _qualification_failure(physical_attempt(logical, ordinal))
        for ordinal in (1, 2)
    ]

    assert physical_sequence_findings(rows, materialized_count=2) == []
    assert all(row["classification"] == "qualification_failure" for row in rows)
    assert not any(attempt_accepted(row) for row in rows)


def test_campaign_state_retains_failure_and_counts_logical_success_separately(
    tmp_path: Path,
) -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    attempts = campaign_attempts(
        acceptance_targets(config),
        config["qualification_mode"],
        config["qualification_seed"],
    )
    git_commit = "d" * 40
    manifest = {
        "manifest_sha256": "a" * 64,
        "runtime_identity": {
            "profile_generation": 9,
            "profile_content_hash": "b" * 64,
        },
    }
    results: list[dict[str, object]] = []
    for logical_index, logical in enumerate(attempts):
        ordinals = (1, 2) if logical_index == 0 else (1,)
        for ordinal in ordinals:
            physical = physical_attempt(logical, ordinal)
            physical_try_dir(tmp_path, logical, ordinal).mkdir(parents=True)
            row = (
                _qualification_failure(physical)
                if logical_index == 0 and ordinal == 1
                else _accepted_result(physical)
            )
            row.update(
                {
                    "identity_manifest_sha256": manifest["manifest_sha256"],
                    "git_commit_sha256": hashlib.sha256(
                        git_commit.encode("utf-8")
                    ).hexdigest(),
                    "profile_generation": 9,
                    "profile_content_hash": "b" * 64,
                }
            )
            results.append(row)
    plan = {
        "plan_sha256": "c" * 64,
        "git_head": git_commit,
        "max_tries_per_dps_spec": 2,
        "child_outer_timeout_sec": 1800,
    }
    verification = {"verification_sha256": "e" * 64, "input_hashes": {}}
    state = write_campaign_state(
        tmp_path,
        attempts,
        results,
        active_attempt=None,
        config_path=CONFIG,
        policy_path=ROOT
        / "experiments/configs/all_spec_role_calibration_policy_v2.json",
        verification=verification,
        plan=plan,
        evidence_manifest=manifest,
    )

    assert state["passed"] is True
    assert state["logical_attempt_count"] == 16
    assert state["logical_success_count"] == 16
    assert state["physical_try_count"] == 17
    assert state["classified_physical_try_count"] == 17
    assert state["physical_success_count"] == 16
    assert state["results"] == state["physical_try_ledger"]
    assert state["results"][0]["classification"] == "qualification_failure"
    assert state["results"][1]["classification"] == "accepted"


def test_extra_try_and_duplicate_or_post_success_are_rejected(tmp_path: Path) -> None:
    logical = {
        "attempt_index": 1,
        "attempt_id": "qualification/demo",
        "cohort_id": "dps85-demo",
    }
    first = _accepted_result(physical_attempt(logical, 1))
    retry = _accepted_result(physical_attempt(logical, 2))
    findings = physical_sequence_findings(
        [first, retry], materialized_count=2
    )
    assert "multiple_successful_physical_tries" in findings
    assert "physical_try_after_success" in findings

    extra = physical_try_dir(tmp_path, logical, 1).parent / "demo-retry-02"
    extra.mkdir(parents=True)
    assert extra in discovered_physical_try_paths(tmp_path, logical)
    assert "physical_try_limit_exceeded" in physical_sequence_findings(
        [first, retry, retry], materialized_count=3
    )


def test_resume_receipt_preserves_unknown_child_returncode(tmp_path: Path) -> None:
    output_root = tmp_path / "campaign"
    logical = {
        "attempt_index": 1,
        "attempt_id": "qualification/demo",
        "cohort_id": "dps85-demo",
    }
    physical = physical_attempt(logical, 1)
    attempt_dir = physical_try_dir(output_root, logical, 1)
    attempt_dir.mkdir(parents=True)
    started = write_physical_try_started(
        attempt_dir,
        output_root,
        logical,
        physical,
        ["runner", "--attempt", str(physical["attempt_id"])],
    )
    interrupted = {
        **physical,
        "child_returncode_observed": False,
        "returncode": None,
        "report_returncode": 0,
        "timed_out": False,
        "calibration_acceptance_passed": True,
        "acceptable_final_evidence": True,
        "all_passed": True,
        "published": True,
        "remote_reconstruction_verified": True,
        "passed": True,
        "hard_floor_passed": True,
        "optimization_target_met": True,
        "targeted_eviction_complete": True,
    }
    write_physical_try_result(attempt_dir, started, interrupted)

    loaded_started = load_physical_try_started(
        attempt_dir, output_root, logical, physical
    )
    loaded, receipt = load_physical_try_result(
        attempt_dir, loaded_started, physical
    )
    assert receipt["child_returncode_observed"] is False
    assert receipt["child_returncode"] is None
    assert loaded["returncode"] is None
    assert loaded["classification"] == "infrastructure_failure"
    assert loaded["accepted"] is False
    with pytest.raises(ValueError, match="immutable"):
        write_physical_try_result(attempt_dir, started, interrupted)


def test_resume_consumes_directory_created_before_start_receipt(
    tmp_path: Path,
) -> None:
    logical = {
        "attempt_index": 1,
        "attempt_id": "qualification/demo",
        "cohort_id": "dps85-demo",
    }
    physical = physical_attempt(logical, 1)
    roots = [tmp_path / "campaign-a", tmp_path / "campaign-b"]
    recovered_receipts = []
    for output_root in roots:
        attempt_dir = physical_try_dir(output_root, logical, 1)
        attempt_dir.mkdir(parents=True)
        recovered = write_recovered_physical_try_reservation(
            attempt_dir, output_root, logical, physical
        )
        recovered_receipts.append(recovered)
        unknown = {
            **physical,
            "child_returncode_observed": False,
            "returncode": None,
            "report_returncode": None,
            "timed_out": None,
            "calibration_acceptance_passed": False,
            "acceptable_final_evidence": False,
            "all_passed": False,
            "remote_transport_verified": False,
            "remote_provenance_verified": False,
            "published": False,
            "remote_reconstruction_verified": False,
            "passed": False,
            "hard_floor_passed": False,
            "optimization_target_met": False,
            "targeted_eviction_complete": False,
            "resume_failure_reason": "child_not_launched_or_observation_unknown",
        }
        write_physical_try_result(attempt_dir, recovered, unknown)
        loaded, _receipt = load_physical_try_result(
            attempt_dir, recovered, physical
        )

        assert loaded["physical_try_ordinal"] == 1
        assert loaded["returncode"] is None
        assert loaded["child_returncode_observed"] is False
        assert loaded["classification"] == "infrastructure_failure"
        assert loaded["reservation_recovered_on_resume"] is True
        assert (
            loaded["launch_observation"]
            == "child_not_launched_or_observation_unknown"
        )

    assert recovered_receipts[0] == recovered_receipts[1]
    with pytest.raises(FileExistsError):
        physical_try_dir(roots[0], logical, 1).mkdir(parents=True, exist_ok=False)


@pytest.mark.parametrize(
    ("field", "spoofed_value"),
    [
        ("evidence_class", None),
        ("excluded_from_training_corpus", False),
        ("runtime_mode", "player_like"),
        ("non_certifying_assistance", False),
    ],
)
def test_attempt_acceptance_rejects_missing_or_false_remote_fixture_provenance(
    field: str, spoofed_value: object
) -> None:
    physical = physical_attempt(
        {
            "attempt_index": 1,
            "attempt_id": "qualification/demo",
            "cohort_id": "dps85-demo",
        },
        1,
    )
    row = _accepted_result(physical)
    remote_field = {
        "evidence_class": "remote_evidence_class",
        "excluded_from_training_corpus": "remote_excluded_from_training_corpus",
        "runtime_mode": "remote_runtime_mode",
        "non_certifying_assistance": "remote_non_certifying_assistance",
    }[field]
    row[remote_field] = spoofed_value

    assert attempt_accepted(row) is False


def test_attempt_acceptance_rejects_failed_remote_transport() -> None:
    physical = physical_attempt(
        {
            "attempt_index": 1,
            "attempt_id": "qualification/demo",
            "cohort_id": "dps85-demo",
        },
        1,
    )
    row = _accepted_result(physical)
    row["remote_transport_verified"] = False

    assert attempt_accepted(row) is False


def _remote_fixture_source(attempt: dict[str, object]) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    identity = {"profile_generation": 1, "profile_content_hash": "c" * 64}
    record: dict[str, object] = {
        "schema": "all_spec_role_calibration_record_v1",
        "evidence_class": "non_certifying_calibration_fixture",
        "excluded_from_training_corpus": True,
        "runtime_mode": "calibration_fixture",
        "non_certifying_assistance": True,
        "identity": identity,
    }
    evaluation: dict[str, object] = {
        "schema": "all_spec_role_calibration_evaluation_v1",
        "passed": True,
        "hard_floor_passed": True,
        "optimization_target_met": True,
        "reference_ratio": 0.9,
        "failure_reasons": [],
    }
    source: dict[str, object] = {
        "returncode": 0,
        "timed_out": False,
        "calibration_acceptance": {"passed": True},
        "acceptable_final_evidence": True,
        "all_passed": True,
        "requested_calibration": {
            "target_spec": attempt["runtime_join_key"],
            "mode": attempt["mode"],
            "seed": attempt["seed"],
        },
        "combat_calibration": {
            "runtime_mode": "calibration_fixture",
            "non_certifying_assistance": True,
        },
        "role_calibration_record": record,
        "role_calibration_evaluation": evaluation,
        "session": {
            "cohort_id": attempt["cohort_id"],
            "attempt_index": attempt["attempt_index"],
            **identity,
        },
        "evidence_envelope": {
            "identity_complete": True,
            "identity_manifest_sha256": "a" * 64,
            "component_hashes": {},
            "scope_ids": {},
        },
    }
    return source, record, evaluation


def _verify_remote_fixture(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    source: dict[str, object],
    record: dict[str, object],
    evaluation: dict[str, object],
    attempt: dict[str, object],
) -> dict[str, object]:
    raw = tmp_path / "raw"
    raw.mkdir(parents=True)
    (raw / "acceptance_source_report.json").write_text(
        json.dumps(source), encoding="utf-8"
    )
    monkeypatch.setattr(
        dps_runner,
        "evaluate_runtime_calibration",
        lambda *_args, **_kwargs: (record, evaluation),
    )
    monkeypatch.setattr(
        dps_runner,
        "validate_evidence_manifest",
        lambda manifest, runtime_identity=None: manifest,
    )
    monkeypatch.setattr(
        dps_runner,
        "phase8_envelope_build_compatible",
        lambda _manifest, _components: True,
    )
    return verify_hydrated_calibration(
        tmp_path,
        attempt,
        ROOT / "experiments/configs/all_spec_role_calibration_policy_v2.json",
        {"manifest_sha256": "a" * 64, "component_hashes": {}},
    )


@pytest.mark.parametrize(
    ("field", "spoofed_value"),
    [
        ("evidence_class", None),
        ("excluded_from_training_corpus", False),
        ("runtime_mode", "player_like"),
        ("non_certifying_assistance", False),
    ],
)
def test_remote_reconstruction_rejects_spoofed_fixture_provenance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    spoofed_value: object,
) -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    logical = campaign_attempts(
        acceptance_targets(config),
        config["qualification_mode"],
        config["qualification_seed"],
    )[0]
    attempt = physical_attempt(logical, 1)
    source, record, evaluation = _remote_fixture_source(attempt)
    if spoofed_value is None:
        record.pop(field)
    else:
        record[field] = spoofed_value

    verification = _verify_remote_fixture(
        tmp_path, monkeypatch, source, record, evaluation, attempt
    )
    assert verification["verified"] is False
    assert verification["provenance_verified"] is False


@pytest.mark.parametrize(
    ("field", "failed_value"),
    [
        ("returncode", None),
        ("returncode", 1),
        ("returncode", True),
        ("timed_out", True),
        ("calibration_acceptance", {"passed": False}),
        ("acceptable_final_evidence", False),
        ("all_passed", False),
    ],
)
def test_remote_reconstruction_rejects_failed_source_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    failed_value: object,
) -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    logical = campaign_attempts(
        acceptance_targets(config),
        config["qualification_mode"],
        config["qualification_seed"],
    )[0]
    attempt = physical_attempt(logical, 1)
    source, record, evaluation = _remote_fixture_source(attempt)
    if failed_value is None:
        source.pop(field)
    else:
        source[field] = failed_value

    verification = _verify_remote_fixture(
        tmp_path, monkeypatch, source, record, evaluation, attempt
    )
    assert verification["verified"] is False
    assert verification["source_transport_verified"] is False


def test_remote_reconstruction_accepts_only_explicit_fixture_and_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    logical = campaign_attempts(
        acceptance_targets(config),
        config["qualification_mode"],
        config["qualification_seed"],
    )[0]
    attempt = physical_attempt(logical, 1)
    source, record, evaluation = _remote_fixture_source(attempt)

    verification = _verify_remote_fixture(
        tmp_path, monkeypatch, source, record, evaluation, attempt
    )
    assert verification["verified"] is True
    assert verification["source_transport_verified"] is True
    assert verification["provenance_verified"] is True
    assert verification["evidence_class"] == "non_certifying_calibration_fixture"
    assert verification["excluded_from_training_corpus"] is True
    assert verification["runtime_mode"] == "calibration_fixture"
    assert verification["non_certifying_assistance"] is True


def test_phase8_v2_build_projection_binds_real_envelope_and_rejects_binary_mismatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    logical = campaign_attempts(
        acceptance_targets(config),
        config["qualification_mode"],
        config["qualification_seed"],
    )[0]
    attempt = physical_attempt(logical, 1)
    manifest = _phase8_v2_manifest()
    source, record, evaluation = _remote_fixture_source(attempt)
    source["session"] = {
        "cohort_id": attempt["cohort_id"],
        "attempt_index": attempt["attempt_index"],
        **dict(manifest["runtime_identity"]),
    }
    source["evidence_envelope"] = _real_phase8_envelope(manifest)
    raw = tmp_path / "raw"
    raw.mkdir(parents=True)
    source_path = raw / "acceptance_source_report.json"
    source_path.write_text(json.dumps(source), encoding="utf-8")
    monkeypatch.setattr(
        dps_runner,
        "evaluate_runtime_calibration",
        lambda *_args, **_kwargs: (record, evaluation),
    )

    verification = verify_hydrated_calibration(
        tmp_path,
        attempt,
        ROOT / "experiments/configs/all_spec_role_calibration_policy_v2.json",
        manifest,
    )
    assert verification["verified"] is True
    assert verification["evidence_build_identity_compatible"] is True
    assert set(dps_runner.phase8_envelope_build_projection(manifest)) == {
        "git_commit_sha256",
        "git_dirty_state_sha256",
        "binary_sha256",
        "database_snapshot_sha256",
        "database_schema_sha256",
        "server_epoch_sha256",
        "profile_generation_sha256",
    }

    source["evidence_envelope"] = _real_phase8_envelope(
        manifest, binary_sha256="f" * 64
    )
    source_path.write_text(json.dumps(source), encoding="utf-8")
    mismatched = verify_hydrated_calibration(
        tmp_path,
        attempt,
        ROOT / "experiments/configs/all_spec_role_calibration_policy_v2.json",
        manifest,
    )
    assert mismatched["verified"] is False
    assert mismatched["evidence_build_identity_compatible"] is False


def test_live_acceptance_command_forces_publish_and_eviction(tmp_path: Path) -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    logical = campaign_attempts(
        acceptance_targets(config),
        config["qualification_mode"],
        config["qualification_seed"],
    )[0]
    attempt = physical_attempt(logical, 2)
    args = argparse.Namespace(
        worldserver=Path("build/src/server/worldserver/worldserver"),
        worldserver_config=Path("trinity-worldserver-test.conf"),
        timeout_sec=900,
        heartbeat_sec=30,
        session_transition_timeout_sec=360,
        session_environment="test-dps85",
    )
    command = child_command(
        args,
        attempt,
        tmp_path / "attempt",
        ROOT / "experiments/configs/all_spec_role_calibration_policy_v2.json",
        tmp_path / "identity.json",
    )

    assert "--publish-batch" in command
    assert "--retain-published-batch" not in command
    assert command[command.index("--role-calibration-policy") + 1].endswith(
        "all_spec_role_calibration_policy_v2.json"
    )
    seed_index = command.index("--calibration-seed")
    assert command[seed_index + 1] == str(attempt["seed"])
    assert command[seed_index + 2] == "--role-calibration-policy"
    assert command[command.index("--cohort-id") + 1] == attempt["cohort_id"]
    assert command[command.index("--session-attempt-index") + 1] == str(
        attempt["attempt_index"]
    )


def test_targeted_eviction_requires_receipt_and_no_bulk_payload(tmp_path: Path) -> None:
    batch = tmp_path / "batch"
    (batch / "retained").mkdir(parents=True)
    (batch / "retained/publication_receipt.json").write_text(
        "{}", encoding="utf-8"
    )
    assert targeted_eviction_complete(tmp_path)

    (batch / "raw").mkdir()
    assert not targeted_eviction_complete(tmp_path)


def test_world_validation_path_uses_kernel_and_recovery_supervisor() -> None:
    source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(
        encoding="utf-8"
    )
    update_start = source.index("void BotWorldPopulationMgr::UpdateBot(")
    update_end = source.index("\nPlayer* BotWorldPopulationMgr::GetLoadedBot", update_start)
    update = source[update_start:update_end]

    assert "validationKernelOwnsTick" in update
    assert "state.DecisionKernel.Resolve()" in update
    assert "TryRecoverStuckBot(state, bot)" in update
    assert "validation_route_stuck_no_fallback" not in update
    assert "stuck_no_fallback" not in update

    recovery_start = source.index("bool BotWorldPopulationMgr::TryRecoverStuckBot(")
    recovery_end = source.index("void BotWorldPopulationMgr::ObserveBotCandidateFailure", recovery_start)
    recovery = source[recovery_start:recovery_end]
    assert "recoveryStrategy" in recovery
    assert "world.recovery.sidestep_left" in recovery
    assert "world.recovery.sidestep_right" in recovery

    prepare_start = source.index(
        "std::string BotWorldPopulationMgr::PrepareValidationProfile("
    )
    prepare_end = source.index(
        "bool BotWorldPopulationMgr::PrepareCurrentValidationProfile", prepare_start
    )
    prepare = source[prepare_start:prepare_end]
    assert "exactPartyRequested" in prepare
    assert "!exactPartyRequested" in prepare
    assert "invalid_exact_party_contract" in prepare

    record_start = source.index("void BotWorldPopulationMgr::RecordDecision(")
    record_end = source.index("void BotWorldPopulationMgr::RecordDecisionFingerprintMemory", record_start)
    record = source[record_start:record_end]
    assert "bot_decision_mask_v3" in record
    assert "decision_kernel" in record
    assert "state.LastDecisionKernelJson" in record
