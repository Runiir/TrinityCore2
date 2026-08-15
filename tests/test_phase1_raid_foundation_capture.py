import json
import io
from math import hypot
from pathlib import Path
from types import SimpleNamespace

from tools.raid_program.capture_phase1_raid_foundation import (
    accepted_foundation_status,
    accepted_drudge_contract,
    accepted_native_recovery,
    action_payloads,
    JsonLogCursor,
    json_actions,
    json_rows,
    normalized_batch_payload,
    _forbidden_assistance_entries,
    _dvc_status_is_clean,
    _protected_process_matches,
    expected_bwd_10n_roster,
    _expected_identity_by_slot,
    preflight_runtime_exclusions,
    validate_runtime_profile_assets,
    evidence_demux_report,
    evidence_demux_rejections,
    semantic_progress_signature,
    observe_monotonic_semantic_progress,
    observe_telemetry_freshness,
    TelemetryScheduler,
    material_status_signature,
    terminal_runtime_failure_reason,
    validate_forced_evidence_bundle,
    bounded_native_shutdown,
    _frozen_drudge_member_anchors,
    process_resource_sample,
    summarize_process_resource_samples,
    native_readycheck_request_identity,
    ready_for_native_readycheck,
)


def _scheduler_status(*, route_index: int = 0, encounter: bool = False) -> dict:
    return {
        "ok": True,
        "raid_runtime": {
            "active": True,
            "strategy_id": "blackwing_descent_10n",
            "assignment_generation": 1,
            "route_progress": {"manifest_index": route_index},
            "encounter_in_progress": encounter,
            "boss_states": [0] * 6,
            "alive_size": 10,
            "expected_size": 10,
            "wipe_state": "ready",
            "recovery_state": "none",
            "wipe_generation": 0,
            "boss_reset_generation": 0,
            "recovery_generation": 0,
            "ready_check_satisfied": True,
            "roster_complete": True,
        },
        "validation_route": {
            "manifest_index": route_index,
            "generation": 1,
            "node_id": f"node-{route_index}",
            "kind": "trash" if route_index else "regroup",
            "manifest_complete": False,
            "terminal_evidence": [],
            "boss_death_evidence": [],
        },
    }


def test_telemetry_scheduler_reduces_steady_state_heavy_commands():
    scheduler = TelemetryScheduler(status_interval_sec=5, diagnose_interval_sec=15, trace_interval_sec=10)
    commands = [command for now in range(0, 61) for command in scheduler.commands_due(float(now))]

    assert commands.count("botauto status") == 13
    assert commands.count("botauto diagnose all") == 5
    assert commands.count("botauto trace all 128 delta") == 7
    assert commands.count("botauto diagnose all") < commands.count("botauto status")


def test_default_scheduler_reduces_heavy_payload_volume_without_dropping_channels():
    scheduler = TelemetryScheduler()
    assert scheduler.status_interval_sec == 5.0
    assert scheduler.diagnose_interval_sec == 30.0
    assert scheduler.trace_interval_sec == 20.0
    commands = [command for now in range(0, 121) for command in scheduler.commands_due(float(now))]
    assert commands.count("botauto status") == 25
    assert commands.count("botauto diagnose all") == 5
    assert commands.count("botauto trace all 128 delta") == 7
    assert set(commands) == {
        "botauto status", "botauto diagnose all", "botauto trace all 128 delta",
    }


def test_terminal_runtime_failure_is_exact_roster_bound_and_material():
    status = accepted_status()
    status["cohort_id"] = "default"
    status["active_profile"] = "blackwing_descent_10n"
    baseline = material_status_signature(status)

    status["failure_reason"] = "drudge_partial_death_before_threat_seed"
    reason, rejections = terminal_runtime_failure_reason(status)

    assert reason == "drudge_partial_death_before_threat_seed"
    assert rejections == []
    assert material_status_signature(status) != baseline

    status["raid_runtime"]["roster"][0]["lease_owned"] = False
    reason, rejections = terminal_runtime_failure_reason(status)
    assert reason is None
    assert "terminal_failure_all_roster_leases_owned" in rejections


class _FakeShutdownProcess:
    def __init__(self, *, interrupt_once: bool = False) -> None:
        self.stdin = io.BytesIO()
        self.returncode = None
        self.wait_calls = 0
        self.interrupt_once = interrupt_once

    def poll(self):
        return self.returncode

    def wait(self, *, timeout: float):
        self.wait_calls += 1
        if self.interrupt_once:
            self.interrupt_once = False
            raise KeyboardInterrupt
        self.returncode = 0
        return self.returncode


def test_bounded_native_shutdown_sends_cleanup_and_handles_operator_interrupt():
    process = _FakeShutdownProcess(interrupt_once=True)
    result = bounded_native_shutdown(process, 20.0)

    assert process.stdin.getvalue() == b"botauto stop\nbotauto status\nserver exit\n"
    assert result["commands_sent"] is True
    assert result["operator_interrupted"] is True
    assert result["exited"] is True
    assert result["error"] is None
    assert process.wait_calls == 2


def test_process_resource_sample_reuses_baseline_proc_units_and_binds_run_identity(monkeypatch):
    monkeypatch.setattr(
        "tools.raid_program.capture_phase1_raid_foundation._baseline_process_sample",
        lambda pid: {
            "monotonic_sec": 12.5,
            "process_cpu_ticks": 321,
            "process_rss_bytes": 987654,
            "host_load_1m": 999,
        },
    )
    sample = process_resource_sample(
        4242,
        sample_sequence=3,
        scenario_id="magmaw-shard",
        runtime_profile="magmaw-shard",
        status={
            "cohort_id": "cohort-a",
            "raid_runtime": {
                "server_epoch": 8,
                "attempt_id": 9,
                "profile_generation": 2,
                "assignment_generation": 4,
                "instance_id": 55,
            },
        },
    )

    assert sample == {
        "sample_sequence": 3,
        "process_pid": 4242,
        "monotonic_sec": 12.5,
        "process_cpu_ticks": 321,
        "process_rss_bytes": 987654,
        "run_identity": {
            "scenario_id": "magmaw-shard",
            "runtime_profile": "magmaw-shard",
            "cohort_id": "cohort-a",
            "server_epoch": 8,
            "attempt_id": 9,
            "profile_generation": 2,
            "assignment_generation": 4,
            "instance_id": 55,
        },
    }


def test_process_resource_summary_matches_baseline_cpu_and_rss_semantics():
    samples = [
        {
            "process_pid": 4242,
            "monotonic_sec": 10.0,
            "process_cpu_ticks": 100,
            "process_rss_bytes": 20,
        },
        {
            "process_pid": 4242,
            "monotonic_sec": 13.0,
            "process_cpu_ticks": 160,
            "process_rss_bytes": 30,
        },
    ]
    summary = summarize_process_resource_samples(samples, tick_rate=100, sampling_errors=["one"])

    assert summary["sample_count"] == 2
    assert summary["process_pid"] == 4242
    assert summary["pid_consistent"] is True
    assert summary["cpu_ticks_delta"] == 60
    assert summary["mean_cpu_percent_one_core"] == 20.0
    assert summary["maximum_rss_bytes"] == 30
    assert summary["minimum_rss_bytes"] == 20
    assert summary["sampling_error_count"] == 1


def test_process_resource_summary_refuses_cpu_attribution_for_mixed_pids():
    samples = [
        {"process_pid": 1, "monotonic_sec": 1.0, "process_cpu_ticks": 10, "process_rss_bytes": 20},
        {"process_pid": 2, "monotonic_sec": 2.0, "process_cpu_ticks": 30, "process_rss_bytes": 40},
    ]
    summary = summarize_process_resource_samples(samples, tick_rate=100)

    assert summary["pid_consistent"] is False
    assert summary["process_pid"] is None
    assert summary["cpu_ticks_delta"] is None
    assert summary["mean_cpu_percent_one_core"] is None
    assert summary["maximum_rss_bytes"] == 40


def test_material_status_transition_forces_immediate_full_diagnosis():
    scheduler = TelemetryScheduler()
    initial = _scheduler_status(route_index=0)
    changed = _scheduler_status(route_index=1, encounter=True)
    assert material_status_signature(initial) != material_status_signature(changed)

    assert scheduler.commands_due(0.0) == [
        "botauto status", "botauto trace all 128 delta", "botauto diagnose all",
    ]
    scheduler.observe_status(initial)
    assert scheduler.commands_due(1.0) == []

    assert scheduler.observe_status(changed) is True
    assert scheduler.commands_due(1.1) == ["botauto diagnose all"]


def test_scheduler_intervals_are_below_freshness_timeout_and_channels_remain_fresh():
    scheduler = TelemetryScheduler(status_interval_sec=5, diagnose_interval_sec=15, trace_interval_sec=10)
    assert max(
        scheduler.status_interval_sec,
        scheduler.diagnose_interval_sec,
        scheduler.trace_interval_sec,
    ) < 30

    state: dict[str, dict[str, float | int]] = {}
    counts = {"status": 1, "diagnosis": 1, "trace": 1}
    assert observe_telemetry_freshness(state, counts, 0.0, 30) == []
    assert observe_telemetry_freshness(state, counts, 29.9, 30) == []
    assert observe_telemetry_freshness(state, counts, 30.1, 30) == [
        "status", "diagnosis", "trace",
    ]


def test_forced_stall_bundle_contains_diagnose_and_lossless_trace_delta():
    scheduler = TelemetryScheduler(status_interval_sec=5, diagnose_interval_sec=15, trace_interval_sec=10)
    scheduler.commands_due(0.0)
    scheduler.force_diagnosis(include_trace=True)
    assert scheduler.commands_due(2.0) == [
        "botauto trace all 128 delta", "botauto diagnose all",
    ]


def _forced_response(status: dict, action: str, *, ok: bool = True) -> dict:
    response = {
        "ok": ok,
        "action": action,
        "cohort_id": status["cohort_id"],
        "raid_runtime": status["raid_runtime"],
        "bots": [],
    }
    for member in status["raid_runtime"]["roster"]:
        if action == "botauto_diagnose":
            response["bots"].append({"identity": {"bot_guid": member["guid"]}})
        else:
            response["bots"].append({"bot_guid": member["guid"], "gap": False})
    return response


def test_final_forced_bundle_requires_both_fresh_identity_bound_ok_channels():
    status = accepted_status()
    status["cohort_id"] = "raid"
    diagnosis = _forced_response(status, "botauto_diagnose")
    trace = _forced_response(status, "botauto_trace")

    accepted = validate_forced_evidence_bundle(
        [(diagnosis, 10.1), (trace, 10.2)], status,
        requested_at_monotonic=10.0, freshness_timeout_seconds=5.0,
    )
    assert accepted["gate_passed"] is True
    assert accepted["missing_channels"] == []

    missing = validate_forced_evidence_bundle(
        [(trace, 10.2)], status,
        requested_at_monotonic=10.0, freshness_timeout_seconds=5.0,
    )
    assert missing["gate_passed"] is False
    assert missing["missing_channels"] == ["diagnosis"]

    delayed = validate_forced_evidence_bundle(
        [(diagnosis, 15.1), (trace, 15.2)], status,
        requested_at_monotonic=10.0, freshness_timeout_seconds=5.0,
    )
    assert delayed["gate_passed"] is False
    assert delayed["missing_channels"] == ["diagnosis", "trace"]
    assert "diagnosis:forced_response_stale" in delayed["rejections"]
    assert "trace:forced_response_stale" in delayed["rejections"]

    failed = validate_forced_evidence_bundle(
        [(_forced_response(status, "botauto_diagnose", ok=False), 10.1), (trace, 10.2)],
        status,
        requested_at_monotonic=10.0, freshness_timeout_seconds=5.0,
    )
    assert failed["gate_passed"] is False
    assert failed["missing_channels"] == ["diagnosis"]
    assert "diagnosis:forced_response_envelope_not_ok" in failed["rejections"]


def test_final_forced_bundle_rejects_pre_request_and_cross_identity_rows():
    status = accepted_status()
    status["cohort_id"] = "raid"
    diagnosis = _forced_response(status, "botauto_diagnose")
    trace = _forced_response(status, "botauto_trace")
    trace["cohort_id"] = "other-raid"
    result = validate_forced_evidence_bundle(
        [(diagnosis, 9.9), (trace, 10.1)], status,
        requested_at_monotonic=10.0, freshness_timeout_seconds=5.0,
    )
    assert result["gate_passed"] is False
    assert result["missing_channels"] == ["diagnosis", "trace"]
    assert "diagnosis:forced_response_before_request" in result["rejections"]
    assert "trace:forced_response_runtime_identity_unbound" in result["rejections"]


def test_material_signature_schedules_hostile_and_per_guid_recovery_edges():
    status = accepted_status()
    baseline = material_status_signature(status)
    hostile = json.loads(json.dumps(status))
    runtime = hostile["raid_runtime"]
    runtime.update(
        native_hostile_activity_active=True,
        native_hostile_reset_generation=2,
        native_hostile_activity_reason="hostile_pack_still_active",
    )
    assert material_status_signature(hostile) != baseline

    scheduler = TelemetryScheduler()
    scheduler.observe_status(status)
    assert scheduler.commands_due(0.0) == [
        "botauto status", "botauto trace all 128 delta", "botauto diagnose all",
    ]
    scheduler.observe_status(hostile)
    assert scheduler.commands_due(1.0) == ["botauto diagnose all"]

    recovery = json.loads(json.dumps(status))
    recovery["raid_runtime"]["native_recovery"]["members"] = [{
        "guid": 1001,
        "wipe_generation": 1,
        "death_sequence": 10,
        "corpse_sequence": 11,
        "release_sequence": 12,
        "runback_sequence": 13,
        "reentry_sequence": 14,
        "resurrection_sequence": 15,
    }]
    assert material_status_signature(recovery) != baseline


def test_readycheck_request_accepts_exact_trash_hostile_reset_without_boss_reset():
    status = accepted_status()
    runtime = status["raid_runtime"]
    status["validation_route"] = {"generation": 3, "node_id": "drudge-node"}
    runtime.update(
        attempt_id=2,
        assignment_generation=7,
        alive_size=10,
        encounter_in_progress=False,
        wipe_generation=1,
        boss_reset_generation=0,
        boss_reset_generation_at_wipe=0,
        native_hostile_activity_active=False,
        native_hostile_inactivity_observed=True,
        native_hostile_reset_generation=3,
        native_hostile_reset_generation_at_wipe=2,
        native_hostile_observation_attempt_id=2,
        native_hostile_observation_route_generation=3,
        native_hostile_observation_node_id="drudge-node",
        native_recovery_hold_active=True,
        native_recovery_route_generation=3,
        native_recovery_node_id="drudge-node",
    )
    runtime["native_recovery"].update(
        death_observed=True,
        corpse_observed=True,
        release_observed=True,
        resurrection_observed=True,
        runback_observed=True,
        ready_check_action_observed=False,
    )

    assert ready_for_native_readycheck(status) is True
    assert native_readycheck_request_identity(status) == (
        2, 1, 7, 3, "drudge-node",
    )


def test_readycheck_request_rejects_stale_or_active_native_hostile_reset():
    status = accepted_status()
    runtime = status["raid_runtime"]
    status["validation_route"] = {"generation": 3, "node_id": "drudge-node"}
    runtime.update(
        attempt_id=2,
        assignment_generation=1,
        alive_size=10,
        encounter_in_progress=False,
        wipe_generation=1,
        boss_reset_generation=0,
        boss_reset_generation_at_wipe=0,
        native_hostile_activity_active=False,
        native_hostile_inactivity_observed=True,
        native_hostile_reset_generation=2,
        native_hostile_reset_generation_at_wipe=2,
        native_hostile_observation_attempt_id=2,
        native_hostile_observation_route_generation=3,
        native_hostile_observation_node_id="drudge-node",
        native_recovery_hold_active=True,
        native_recovery_route_generation=3,
        native_recovery_node_id="drudge-node",
    )
    runtime["native_recovery"].update(
        death_observed=True,
        corpse_observed=True,
        release_observed=True,
        resurrection_observed=True,
        runback_observed=True,
        ready_check_action_observed=False,
    )
    assert ready_for_native_readycheck(status) is False

    runtime["native_hostile_reset_generation"] = 3
    runtime["native_hostile_activity_active"] = True
    assert ready_for_native_readycheck(status) is False

    runtime["native_hostile_activity_active"] = False
    runtime["native_hostile_observation_node_id"] = "stale-node"
    assert ready_for_native_readycheck(status) is False

    runtime["native_hostile_observation_node_id"] = "drudge-node"
    runtime["native_recovery_node_id"] = "other-node"
    assert ready_for_native_readycheck(status) is False


def test_readycheck_request_accepts_boss_reset_with_exact_recovery_scope():
    status = accepted_status()
    runtime = status["raid_runtime"]
    status["validation_route"] = {"generation": 4, "node_id": "magmaw-node"}
    runtime.update(
        attempt_id=3,
        assignment_generation=2,
        alive_size=10,
        encounter_in_progress=False,
        wipe_generation=2,
        boss_reset_generation=5,
        boss_reset_generation_at_wipe=4,
        native_hostile_activity_active=False,
        native_hostile_inactivity_observed=False,
        native_recovery_hold_active=True,
        native_recovery_route_generation=4,
        native_recovery_node_id="magmaw-node",
    )
    runtime["native_recovery"].update(
        death_observed=True,
        corpse_observed=True,
        release_observed=True,
        resurrection_observed=True,
        runback_observed=True,
        ready_check_action_observed=False,
    )

    assert ready_for_native_readycheck(status) is True


def _write_runtime_profile_assets(root: Path, route_payload: str) -> None:
    profile_dir = root / "dataset/bot_runtime_profiles"
    route_dir = root / "dataset/validation_scenarios"
    profile_dir.mkdir(parents=True, exist_ok=True)
    route_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "profiles.json").write_text(json.dumps({
        "profiles": [{
            "name": "blackwing_descent_10n",
            "validation_route": {
                "enable": True,
                "manifest_path": "dataset/validation_scenarios/validation_routes.jsonl",
                "scenario_id": "blackwing_descent_10n",
            },
        }],
    }), encoding="utf-8")
    (route_dir / "validation_routes.jsonl").write_text(route_payload, encoding="utf-8")


def _bwd_route_payload() -> str:
    route_identity = (
        (1, "regroup", "BWD entrance junction regroup", 0, "blackwing_descent_10n.start_position"),
        (2, "trash", "Magmaw Chainwielder trash", 42649, "250050"),
        (3, "trash", "Magmaw Drudge pair", 42362, "250140"),
        (4, "boss", "Magmaw", 41570, "@CGUID+8"),
        (5, "trash", "Omnotron Golem Sentries", 42800, "250049"),
        (6, "boss", "Omnotron Defense System", 42166, "script_summoned"),
        (7, "trash", "laboratory trash", 42803, "250119"),
        (8, "boss", "Maloriak", 41378, "@CGUID+69"),
        (9, "boss", "Atramedes", 41442, "native_instance_unlock"),
        (10, "boss", "Chimaeron", 43296, "@CGUID+70"),
        (11, "boss", "Nefarian", 41376, "native_instance_unlock"),
    )
    return "".join(json.dumps({
        "scenario_id": "blackwing_descent_10n",
        "step": step,
        "route_node_id": f"node-{step}",
        "kind": kind,
        "label": label,
        "source_entry": source_entry,
        "source_guid": source_guid,
    }) + "\n" for step, kind, label, source_entry, source_guid in route_identity)


def test_capture_preflight_requires_matching_hydrated_route_manifest(tmp_path: Path):
    worktree = tmp_path / "worktree"
    reference = tmp_path / "reference"
    route = _bwd_route_payload()
    _write_runtime_profile_assets(worktree, route)
    _write_runtime_profile_assets(reference, route)

    accepted = validate_runtime_profile_assets(worktree, reference, require_dvc_lineage=False)
    assert accepted["passed"] is True
    assert accepted["matching_route_rows"] == 11
    assert accepted["route_sha256"] == accepted["reference_route_sha256"]

    reordered_rows = route.splitlines()
    reordered_rows[1], reordered_rows[2] = reordered_rows[2], reordered_rows[1]
    reordered = "\n".join(reordered_rows) + "\n"
    _write_runtime_profile_assets(worktree, reordered)
    _write_runtime_profile_assets(reference, reordered)
    rejected_order = validate_runtime_profile_assets(
        worktree, reference, require_dvc_lineage=False
    )
    assert rejected_order["passed"] is False
    assert "worktree_route_steps_not_ordered_one_through_eleven" in rejected_order["reasons"]
    assert "worktree_route_identity_mismatch" in rejected_order["reasons"]

    _write_runtime_profile_assets(worktree, route)
    _write_runtime_profile_assets(reference, route)

    (worktree / "dataset/validation_scenarios/validation_routes.jsonl").unlink()
    missing = validate_runtime_profile_assets(worktree, reference, require_dvc_lineage=False)
    assert missing["passed"] is False
    assert "worktree_route_manifest_unreadable" in missing["reasons"]

    _write_runtime_profile_assets(worktree, json.dumps({
        "scenario_id": "stonecore_5n", "route_node_id": "wrong", "kind": "boss",
    }) + "\n")
    wrong = validate_runtime_profile_assets(worktree, reference, require_dvc_lineage=False)
    assert wrong["passed"] is False
    assert "worktree_route_expected_eleven_rows" in wrong["reasons"]
    assert "runtime_route_differs_from_reference" in wrong["reasons"]


def test_capture_preflight_rejects_dirty_dvc_lineage(tmp_path: Path, monkeypatch):
    worktree = tmp_path / "worktree"
    reference = tmp_path / "reference"
    route = _bwd_route_payload()
    _write_runtime_profile_assets(worktree, route)
    _write_runtime_profile_assets(reference, route)
    monkeypatch.setattr(
        "tools.raid_program.capture_phase1_raid_foundation.subprocess.run",
        lambda *args, **kwargs: SimpleNamespace(returncode=0, stdout="validation_scenarios:\n\tchanged deps:\n"),
    )

    rejected = validate_runtime_profile_assets(worktree, reference)

    assert rejected["passed"] is False
    assert "runtime_route_dvc_lineage_dirty" in rejected["reasons"]


def test_canonical_capture_explicitly_starts_the_frozen_bwd_10n_profile():
    source = (
        Path(__file__).resolve().parents[1]
        / "tools/raid_program/capture_phase1_raid_foundation.py"
    ).read_text(encoding="utf-8")
    assert 'process.stdin.write(b"botauto start blackwing_descent_10n\\n")' in source
    assert '"botauto_profile": "profile_selection"' in source


def accepted_status() -> dict:
    frozen_roster = expected_bwd_10n_roster()
    frozen_identity = _expected_identity_by_slot()
    return {
        "ok": True,
        "action": "botauto_status",
        "bots": 10,
        "lease_count": 10,
        "raid_runtime": {
            "active": True,
            "expected_size": 10,
            "active_size": 10,
            "alive_size": 10,
            "roster_complete": True,
            "expected_difficulty": 0,
            "group_difficulty": 0,
            "map_difficulty": 0,
            "difficulty_matches": True,
            "map_id": 669,
            "instance_id": 42,
            "lockout_save_id": 42,
            "group_guid": 77,
            "leader_guid": 1001,
            "server_epoch": 88,
            "attempt_id": 1,
            "profile_generation": 1,
            "profile_content_hash": "fixture-profile-sha256",
            "assignment_generation": 1,
            "evidence_sequence": 1,
            "wipe_generation": 0,
            "boss_reset_generation": 0,
            "boss_reset_generation_at_wipe": 0,
            "recovery_generation": 0,
            "encounter_in_progress": False,
            "wipe_state": "ready",
            "recovery_state": "none",
            "strategy_id": "blackwing_descent_10n",
            "route_progress": {"generation": 4, "node_index": 3},
            "boss_states": [0] * 6,
            "ready_check_satisfied": True,
            "unique_leases": True,
            "roster": [
                {
                    "roster_slot_id": frozen_roster[index][0],
                    "lease_role_slot": frozen_roster[index][0],
                    "slot": index, "guid": 1001 + index,
                    "subgroup": index // 5, "role": "tank" if index < 2 else ("healer" if index < 5 else "dps"),
                    "class_id": frozen_roster[index][2],
                    "class_spec": frozen_roster[index][3],
                    "gear_identity": f"fixture_gear_{index}",
                    "active": True, "lease_owned": True,
                    "account_id": 1000 + index,
                    "account": frozen_identity[frozen_roster[index][0]]["account"],
                    "name": frozen_identity[frozen_roster[index][0]]["name"],
                    "talents": list(frozen_identity[frozen_roster[index][0]]["talents"]),
                    "glyphs": list(frozen_identity[frozen_roster[index][0]]["glyphs"]),
                    "gear_identity_manifest": {
                        "items": [
                            {
                                "slot": item["slot"], "guid": 500000 + index * 100 + item["slot"],
                                "entry": item["entry"], "enchant_id": item["enchant_id"],
                                "gem_item_ids": list(item["gem_item_ids"]), "reforge_id": item["reforge_id"],
                            }
                            for item in frozen_identity[frozen_roster[index][0]]["gear"]
                        ]
                    },
                }
                for index in range(10)
            ],
            "roster_composition_valid": True,
            "native_recovery": {
                "death_observed": False, "corpse_observed": False, "release_observed": False,
                "resurrection_observed": False, "runback_observed": False,
                "ready_check_action_observed": True, "evidence_complete": False,
                "ready_check_action_generation": 1, "ready_check_action_attempt_id": 1,
                "ready_check_action_wipe_generation": 0,
                "ready_check_assignment_generation": 1,
                "ready_check_action_evidence_sequence": 1,
                "recovery_wipe_generation": 0,
            },
        },
    }


def accepted_drudge_status() -> dict:
    status = accepted_status()
    runtime = status["raid_runtime"]
    roster_guids = [row["guid"] for row in runtime["roster"]]
    tank_guids = [row["guid"] for row in runtime["roster"] if row["role"] == "tank"]
    offensive_guids = [row["guid"] for row in runtime["roster"] if row["role"] in {"tank", "dps"}]
    lane_a_slots = {1, 3, 4, 6, 7}
    lane_b_slots = {2, 5, 8, 9, 10}
    config = json.loads((
        Path(__file__).resolve().parents[1]
        / "experiments/configs/validation_scenarios_cata_001.json"
    ).read_text(encoding="utf-8"))
    scenario = next(row for row in config["scenarios"] if row["id"] == "blackwing_descent_10n")
    drudges = next(row for row in scenario["route"] if row.get("mechanic_profile") == "trash_two_tank_charge_lanes")
    anchors = {
        row["roster_slot"]: (row["x"], row["y"])
        for row in drudges["split_member_anchors"]
    }
    anchors.update({
        row["roster_slot"]: (row["x"], row["y"])
        for row in drudges["split_tank_recovery_anchors"]
    })
    home0 = (-298.833, -50.349)
    home1 = (-307.913, -49.5694)
    midpoint = ((home0[0] + home1[0]) * 0.5, (home0[1] + home1[1]) * 0.5)
    axis_length = hypot(home1[0] - home0[0], home1[1] - home0[1])
    axis = ((home1[0] - home0[0]) / axis_length, (home1[1] - home0[1]) / axis_length)
    projection = lambda x, y: (x - midpoint[0]) * axis[0] + (y - midpoint[1]) * axis[1]
    tank0 = anchors[1]
    tank1 = anchors[2]
    tank_pair_distance = hypot(tank1[0] - tank0[0], tank1[1] - tank0[1])
    tank_pair_axis = (
        (tank1[0] - tank0[0]) / tank_pair_distance,
        (tank1[1] - tank0[1]) / tank_pair_distance,
    )
    melee_stop = drudges["split_native_melee_stop_yards"]
    source0 = (
        tank0[0] + tank_pair_axis[0] * melee_stop,
        tank0[1] + tank_pair_axis[1] * melee_stop,
    )
    source1 = (
        tank1[0] - tank_pair_axis[0] * melee_stop,
        tank1[1] - tank_pair_axis[1] * melee_stop,
    )
    member_geometry = []
    for row in runtime["roster"]:
        slot = row["slot"] + 1
        lane_a = slot in lane_a_slots
        x, y = anchors[slot]
        if row["role"] == "tank":
            member_geometry.append({
                "guid": row["guid"], "roster_slot": slot, "x": x, "y": y,
                "projection": projection(x, y), "anchor_x": 0.0, "anchor_y": 0.0,
                "group_anchor_base_x": 0.0, "group_anchor_base_y": 0.0,
                "anchor_distance": 0.0, "nearest_same_lane_distance": 0.0,
                "anchor_candidate_index": 0, "lane_side_valid": True,
                "anchor_selected": False, "anchor_path_valid": False,
                "same_lane_spacing_valid": False,
            })
            continue
        same_lane_distance = min(
            hypot(x - anchors[other][0], y - anchors[other][1])
            for other in (lane_a_slots if lane_a else lane_b_slots)
            if other != slot and other not in {1, 2}
        )
        member_geometry.append({
            "guid": row["guid"], "roster_slot": slot, "x": x, "y": y,
            "projection": projection(x, y), "anchor_x": x, "anchor_y": y,
            "group_anchor_base_x": x, "group_anchor_base_y": y,
            "anchor_distance": 0.0, "nearest_same_lane_distance": same_lane_distance,
            "anchor_candidate_index": 0, "lane_side_valid": True,
            "anchor_selected": True, "anchor_path_valid": True,
            "same_lane_spacing_valid": True,
        })
    geometry = {
        "home0_x": home0[0], "home0_y": home0[1], "home1_x": home1[0], "home1_y": home1[1],
        "midpoint_x": midpoint[0], "midpoint_y": midpoint[1], "axis_x": axis[0], "axis_y": axis[1],
        "lane_separation": 17.0, "minimum_distance": 15.0,
        "navigation_margin": 2.0,
        "source0_x": source0[0], "source0_y": source0[1], "source0_projection": projection(*source0),
        "source0_health_pct": 100.0,
        "source0_lane_side_valid": True, "source1_x": source1[0], "source1_y": source1[1],
        "source1_projection": projection(*source1), "source1_health_pct": 100.0, "source1_lane_side_valid": True,
        "source0_victim_guid": tank_guids[0], "source1_victim_guid": tank_guids[1],
        "source0_alive": True, "source1_alive": True,
        "source_separation": hypot(source1[0] - source0[0], source1[1] - source0[1]), "minimum_source_separation": 15.0,
        "lane_tank_x": tank0[0], "lane_tank_y": tank0[1], "lane_tank_guid": tank_guids[0],
        "lane_tank_slot": 1, "lane_tank_projection": projection(*tank0),
        "lane_tank_source_distance": hypot(tank0[0] - source0[0], tank0[1] - source0[1]),
        "other_tank_x": tank1[0], "other_tank_y": tank1[1], "other_tank_guid": tank_guids[1],
        "other_tank_slot": 2, "other_tank_projection": projection(*tank1),
        "other_tank_source_distance": hypot(tank1[0] - source1[0], tank1[1] - source1[1]),
        "minimum_member_spacing": 3.0, "arrival_tolerance": 2.0,
        "tank_arrival_tolerance": 1.0,
        "tank0_x": tank0[0], "tank0_y": tank0[1], "tank0_guid": tank_guids[0],
        "tank0_slot": 1, "tank0_projection": projection(*tank0),
        "tank0_source_distance": hypot(tank0[0] - source0[0], tank0[1] - source0[1]),
        "tank1_x": tank1[0], "tank1_y": tank1[1], "tank1_guid": tank_guids[1],
        "tank1_slot": 2, "tank1_projection": projection(*tank1),
        "tank1_source_distance": hypot(tank1[0] - source1[0], tank1[1] - source1[1]),
        "members": member_geometry,
    }
    observations = []
    sequence = 0
    # The native first-Rush snapshots below include the complete (bounded)
    # threat list.  The seeded opposite-lane DPS is the farthest eligible
    # candidate for each source. Tanks and same-lane players remain native
    # selector candidates even though they are not tactic-eligible.
    for source, target in ((250140, roster_guids[7]), (250141, roster_guids[5])):
        for interval in (0, 20000):
            sequence += 1
            observations.append({
                "sequence": sequence,
                "attempt_id": runtime["attempt_id"],
                "wipe_generation": 0,
                "route_generation": 3,
                "observed_at_ms": sequence * 20000,
                "observed_interval_ms": interval,
                "source_guid": 5000 + source,
                "source_spawn_id": source,
                "target_guid": target,
                "target_raw_guid": target,
                "selected_distance": 40.0,
                "source_combat_reach": 1.5,
                "target_combat_reach": 1.5,
                "same_map": True,
                "same_phase": True,
                "range_valid": True,
                "interval_valid": interval == 20000,
                "landed": True,
                "reseparated_roster_guids": roster_guids,
                "geometry": geometry,
            })
    for observation in observations:
        if observation["sequence"] not in (1, 3):
            continue
        source = observation["source_spawn_id"]
        source_lane = 0 if source == 250140 else 1
        farthest_guid = roster_guids[7] if source == 250140 else roster_guids[5]
        distances = {
            slot: (40.0 if guid == farthest_guid else 35.0 - abs(slot - 6) * 0.5)
            for slot, guid in ((row["slot"] + 1, row["guid"]) for row in runtime["roster"])
        }
        candidate_rows = []
        for row in runtime["roster"]:
            slot = row["slot"] + 1
            lane = 0 if slot in lane_a_slots else 1
            role = row["role"]
            cross_lane = lane != source_lane
            native_selector_eligible = True
            tactic_cross_lane_eligible = cross_lane and role != "tank"
            candidate_rows.append({
                "guid": row["guid"],
                "raw_guid": row["guid"],
                "slot": slot,
                "lane": lane,
                "threat": float(1000 + slot),
                "distance": distances[slot],
                "source_combat_reach": 1.5,
                "candidate_combat_reach": 1.5,
                "is_player": True,
                "alive": True,
                "same_map": True,
                "same_phase": True,
                "available": True,
                "line_of_sight": True,
                "in_range": True,
                "native_combat_range": True,
                "cross_lane": cross_lane,
                "native_selector_eligible": native_selector_eligible,
                "tactic_cross_lane_eligible": tactic_cross_lane_eligible,
                "role": role,
            })
        observation["native_threat_candidates"] = candidate_rows
        observation["native_threat_candidates_count"] = len(candidate_rows)
        observation["native_threat_candidates_complete"] = True
        observation["native_threat_candidates_truncated"] = False
    runtime["drudge_charge"] = {
        "generation": 4,
        "landed_generation": 4,
        "evidence_attempt_id": runtime["attempt_id"],
        "evidence_wipe_generation": 0,
        "evidence_route_generation": 3,
        "prepared_count": 4,
        "delivered_count": 4,
        "queue_overflow": False,
        "sources": [
            {"spawn_id": 250140, "delivered_count": 2, "valid_interval_count": 1},
            {"spawn_id": 250141, "delivered_count": 2, "valid_interval_count": 1},
        ],
        "reseparated_roster_guids": roster_guids,
        "ownership_roster_guids": tank_guids,
        "taunt_roster_guids": tank_guids,
        "health_sync_roster_guids": tank_guids,
        "health_sync_evaluated_roster_guids": tank_guids,
        "health_sync_hold_source_spawn_id": 250140,
        "health_sync_hold_tank_guid": tank_guids[0],
        "health_sync_hold_lower_pct": 40.0,
        "health_sync_hold_peer_pct": 50.0,
        "health_sync_hold_lower_alive": True,
        "health_sync_hold_peer_alive": True,
        "death_attempt_id": runtime["attempt_id"],
        "death_wipe_generation": 0,
        "death_route_generation": 3,
        "death_source_spawn_id": 250140,
        "death_source_guid": 255140,
        "survivor_source_spawn_id": 250141,
        "survivor_source_guid": 255141,
        "death_evidence_sequence": 5,
        "rage_wait_evidence_sequence": 6,
        "rage_aura_evidence_sequence": 7,
        "health_sync_evidence_attempt_id": runtime["attempt_id"],
        "health_sync_evidence_wipe_generation": 0,
        "health_sync_evidence_route_generation": 3,
        "profile_action_roster_guids": offensive_guids,
        "observations": observations,
    }
    runtime["drudge_threat_seed"] = {
        "attempt_id": runtime["attempt_id"],
        "wipe_generation": 0,
        "route_generation": 3,
        "closed": True,
        "complete": True,
        "failure": False,
        "roster_guids": [roster_guids[5], roster_guids[7]],
        "observations": [
            {
                "sequence": 8,
                "attempt_id": runtime["attempt_id"],
                "wipe_generation": 0,
                "route_generation": 3,
                "observed_at_ms": 5000,
                "member_guid": roster_guids[7],
                "member_slot": 8,
                "member_lane": 1,
                "source_spawn_id": 250140,
                "source_guid": 255140,
                "source_lane": 0,
                "spell_id": 100001,
                "selected_distance": 40.0,
                "min_range": 5.0,
                "max_range": 80.0,
                "position_safe": True,
                "line_of_sight": True,
                "in_range": True,
                "profile_action_valid": True,
                "action_succeeded": True,
                "selected_offense_unsuppressed": True,
                "other_offense_suppressed": True,
                "action_debug_name": "trained_single_target",
                "action_result": "ok",
            },
            {
                "sequence": 9,
                "attempt_id": runtime["attempt_id"],
                "wipe_generation": 0,
                "route_generation": 3,
                "observed_at_ms": 10000,
                "member_guid": roster_guids[5],
                "member_slot": 6,
                "member_lane": 0,
                "source_spawn_id": 250141,
                "source_guid": 255141,
                "source_lane": 1,
                "spell_id": 100002,
                "selected_distance": 40.0,
                "min_range": 5.0,
                "max_range": 80.0,
                "position_safe": True,
                "line_of_sight": True,
                "in_range": True,
                "profile_action_valid": True,
                "action_succeeded": True,
                "selected_offense_unsuppressed": True,
                "other_offense_suppressed": True,
                "action_debug_name": "trained_single_target",
                "action_result": "ok",
            },
        ],
    }
    return status


def test_drudge_contract_reconstructs_delivery_interval_and_exact_roster_tactics():
    accepted, reasons = accepted_drudge_contract([accepted_drudge_status()])
    assert accepted is True
    assert reasons == []


def test_drudge_geometry_is_loaded_from_explicit_sealed_route_manifest(tmp_path, monkeypatch):
    sealed = (
        Path(__file__).resolve().parents[1]
        / "dataset/validation_scenarios/validation_routes.jsonl"
    )
    # A mutable controller checkout with no route assets cannot influence the
    # explicit generated manifest bound by the capture worktree.
    monkeypatch.setattr(
        "tools.raid_program.capture_phase1_raid_foundation.ROOT", tmp_path,
    )
    anchors = _frozen_drudge_member_anchors(sealed)
    assert set(anchors) == set(range(1, 11))
    assert anchors[1] == (-288.8, -43.0, 212.301)
    assert anchors[2] == (-321.5, -30.0, 211.283429)
    assert _frozen_drudge_member_anchors() == {}


def test_drudge_contract_does_not_skip_an_earlier_unlanded_observation():
    status = accepted_drudge_status()
    observations = status["raid_runtime"]["drudge_charge"]["observations"]
    observations[0]["landed"] = False
    accepted, reasons = accepted_drudge_contract([status])
    assert accepted is False
    assert "drudge_delivered_count_mismatch" in reasons
    observations[0]["landed"] = True
    accepted, reasons = accepted_drudge_contract([status])
    assert accepted is True
    assert reasons == []


def test_drudge_contract_rejects_prepared_only_stale_and_incomplete_tactics():
    prepared_only = accepted_drudge_status()
    prepared_only["raid_runtime"]["drudge_charge"]["observations"][0]["landed"] = False
    accepted, reasons = accepted_drudge_contract([prepared_only])
    assert accepted is False
    assert "drudge_delivered_count_mismatch" in reasons

    stale = accepted_drudge_status()
    stale["raid_runtime"]["drudge_charge"]["observations"][0]["attempt_id"] = 99
    accepted, reasons = accepted_drudge_contract([stale])
    assert accepted is False
    assert "drudge_observation_scope_mismatch" in reasons

    wrong_source_guid = accepted_drudge_status()
    wrong_source_guid["raid_runtime"]["drudge_charge"]["observations"][0]["source_guid"] = 0
    accepted, reasons = accepted_drudge_contract([wrong_source_guid])
    assert accepted is False
    assert "drudge_observation_source_guid_invalid" in reasons

    incomplete = accepted_drudge_status()
    incomplete["raid_runtime"]["drudge_charge"]["health_sync_evaluated_roster_guids"] = []
    accepted, reasons = accepted_drudge_contract([incomplete])
    assert accepted is False
    assert "drudge_exact_tank_health_sync_evaluation_missing" in reasons

    missing_ownership = accepted_drudge_status()
    missing_ownership["raid_runtime"]["drudge_charge"]["ownership_roster_guids"] = []
    accepted, reasons = accepted_drudge_contract([missing_ownership])
    assert accepted is False
    assert "drudge_exact_tank_ownership_missing" in reasons

    no_redundant_taunt = accepted_drudge_status()
    no_redundant_taunt["raid_runtime"]["drudge_charge"]["taunt_roster_guids"] = []
    accepted, reasons = accepted_drudge_contract([no_redundant_taunt])
    assert accepted is True
    assert reasons == []

    foreign_taunt = accepted_drudge_status()
    foreign_taunt["raid_runtime"]["drudge_charge"]["taunt_roster_guids"] = [
        foreign_taunt["raid_runtime"]["roster"][2]["guid"]
    ]
    accepted, reasons = accepted_drudge_contract([foreign_taunt])
    assert accepted is False
    assert "drudge_taunt_evidence_identity_mismatch" in reasons

    partial_sync = accepted_drudge_status()
    partial_sync["raid_runtime"]["drudge_charge"]["health_sync_roster_guids"] = [
        partial_sync["raid_runtime"]["roster"][0]["guid"]
    ]
    accepted, reasons = accepted_drudge_contract([partial_sync])
    assert accepted is True
    assert reasons == []

    foreign_sync = accepted_drudge_status()
    foreign_sync["raid_runtime"]["drudge_charge"]["health_sync_roster_guids"] = [
        foreign_sync["raid_runtime"]["roster"][2]["guid"]
    ]
    accepted, reasons = accepted_drudge_contract([foreign_sync])
    assert accepted is False
    assert "drudge_tank_health_sync_hold_identity_mismatch" in reasons

    out_of_scope_sync = accepted_drudge_status()
    evidence = out_of_scope_sync["raid_runtime"]["drudge_charge"]
    evidence["health_sync_evidence_attempt_id"] += 1
    accepted, reasons = accepted_drudge_contract([out_of_scope_sync])
    assert accepted is False
    assert "drudge_health_sync_scope_attempt_mismatch" in reasons

    tank_target = accepted_drudge_status()
    tank_target["raid_runtime"]["drudge_charge"]["observations"][0]["target_guid"] = 1001
    accepted, reasons = accepted_drudge_contract([tank_target])
    assert accepted is False
    assert "drudge_native_rush_target_tank" in reasons

    same_lane = accepted_drudge_status()
    # Source 250140 is lane A; roster slot 6 is also lane A.  A later clean
    # snapshot must not erase this earlier native selector violation.
    same_lane["raid_runtime"]["drudge_charge"]["observations"][0]["target_guid"] = 1006
    clean = accepted_drudge_status()
    accepted, reasons = accepted_drudge_contract([same_lane, clean])
    assert accepted is False
    assert "drudge_native_rush_lane_target_invalid" in reasons


def test_drudge_geometry_rejects_crossed_sources_and_unsafe_member_spacing():
    crossed = accepted_drudge_status()
    geometry = crossed["raid_runtime"]["drudge_charge"]["observations"][0]["geometry"]
    geometry["source0_x"] = geometry["source1_x"]
    geometry["source0_y"] = geometry["source1_y"]
    accepted, reasons = accepted_drudge_contract([crossed])
    assert accepted is False
    assert "drudge_geometry_source0_lane_side_unsafe" in reasons
    assert "drudge_geometry_source_separation_unsafe" in reasons

    too_close = accepted_drudge_status()
    geometry = too_close["raid_runtime"]["drudge_charge"]["observations"][0]["geometry"]
    member = next(row for row in geometry["members"] if row["roster_slot"] == 3)
    member["x"] = geometry["source0_x"]
    member["y"] = geometry["source0_y"]
    accepted, reasons = accepted_drudge_contract([too_close])
    assert accepted is False
    assert "drudge_geometry_member_source_distance_unsafe" in reasons


def test_drudge_geometry_rejects_forged_native_source_victim():
    status = accepted_drudge_status()
    geometry = status["raid_runtime"]["drudge_charge"]["observations"][0]["geometry"]
    geometry["source0_victim_guid"] = geometry["source1_victim_guid"]
    accepted, reasons = accepted_drudge_contract([status])
    assert accepted is False
    assert "drudge_geometry_source0_victim_invalid" in reasons


def test_drudge_geometry_rejects_unverified_path_fallback():
    status = accepted_drudge_status()
    geometry = status["raid_runtime"]["drudge_charge"]["observations"][0]["geometry"]
    member = next(row for row in geometry["members"] if row["roster_slot"] == 3)
    member["anchor_path_valid"] = False
    accepted, reasons = accepted_drudge_contract([status])
    assert accepted is False
    assert "drudge_geometry_member_anchor_path_unverified" in reasons


def test_drudge_threat_seed_rejects_same_lane_or_unsuppressed_offense():
    same_lane = accepted_drudge_status()
    same_lane["raid_runtime"]["drudge_threat_seed"]["observations"][0]["member_lane"] = 0
    accepted, reasons = accepted_drudge_contract([same_lane])
    assert accepted is False
    assert "drudge_threat_seed_cross_lane_invalid" in reasons

    unsuppressed = accepted_drudge_status()
    unsuppressed["raid_runtime"]["drudge_threat_seed"]["observations"][1][
        "other_offense_suppressed"
    ] = False
    accepted, reasons = accepted_drudge_contract([unsuppressed])
    assert accepted is False
    assert "drudge_threat_seed_safety_evidence_invalid" in reasons

    late = accepted_drudge_status()
    late["raid_runtime"]["drudge_threat_seed"]["observations"][0]["observed_at_ms"] = 20000
    accepted, reasons = accepted_drudge_contract([late])
    assert accepted is False
    assert "drudge_threat_seed_not_pre_first_rush" in reasons


def test_drudge_native_threat_evidence_fails_closed_when_candidate_list_is_missing_or_truncated():
    missing = accepted_drudge_status()
    del missing["raid_runtime"]["drudge_charge"]["observations"][0]["native_threat_candidates"]
    accepted, reasons = accepted_drudge_contract([missing])
    assert accepted is False
    assert "drudge_native_threat_candidates_missing" in reasons

    truncated = accepted_drudge_status()
    first = truncated["raid_runtime"]["drudge_charge"]["observations"][0]
    first["native_threat_candidates_count"] = 33
    first["native_threat_candidates_complete"] = False
    first["native_threat_candidates_truncated"] = True
    accepted, reasons = accepted_drudge_contract([truncated])
    assert accepted is False
    assert "drudge_native_threat_candidates_metadata_invalid" in reasons
    assert "drudge_native_threat_candidates_truncated" in reasons


def test_drudge_native_threat_evidence_rejects_forged_eligibility_farthest_and_seed_linkage():
    forged_eligibility = accepted_drudge_status()
    first = forged_eligibility["raid_runtime"]["drudge_charge"]["observations"][0]
    first["native_threat_candidates"][0]["tactic_cross_lane_eligible"] = True
    accepted, reasons = accepted_drudge_contract([forged_eligibility])
    assert accepted is False
    assert "drudge_native_threat_candidate_eligibility_mismatch" in reasons

    same_lane_farthest = accepted_drudge_status()
    first = same_lane_farthest["raid_runtime"]["drudge_charge"]["observations"][0]
    first["native_threat_candidates"][2]["distance"] = 75.0
    accepted, reasons = accepted_drudge_contract([same_lane_farthest])
    assert accepted is False
    assert "drudge_native_threat_selected_target_not_farthest" in reasons

    combat_reach_farthest = accepted_drudge_status()
    first = combat_reach_farthest["raid_runtime"]["drudge_charge"]["observations"][0]
    first["native_threat_candidates"][2]["distance"] = 81.0
    first["native_threat_candidates"][2]["in_range"] = False
    accepted, reasons = accepted_drudge_contract([combat_reach_farthest])
    assert accepted is False
    assert "drudge_native_threat_selected_target_not_farthest" in reasons

    non_player_reference = accepted_drudge_status()
    for observation in non_player_reference["raid_runtime"]["drudge_charge"]["observations"]:
        if observation["observed_interval_ms"] != 0:
            continue
        observation["native_threat_candidates"].append({
            "guid": non_player_reference["raid_runtime"]["roster"][0]["guid"],
            "raw_guid": (4 << 60) + 900000 + observation["source_spawn_id"],
            "slot": 0,
            "lane": 0,
            "threat": 1.0,
            "distance": 79.0,
            "source_combat_reach": 1.5,
            "candidate_combat_reach": 1.5,
            "is_player": False,
            "alive": True,
            "same_map": True,
            "same_phase": True,
            "available": True,
            "line_of_sight": True,
            "in_range": True,
            "native_combat_range": True,
            "cross_lane": False,
            "native_selector_eligible": False,
            "tactic_cross_lane_eligible": False,
            "role": "unregistered",
        })
        observation["native_threat_candidates_count"] += 1
    accepted, reasons = accepted_drudge_contract([non_player_reference])
    assert accepted is True
    assert reasons == []


def test_drudge_native_threat_ignores_ordinary_pre_rush_snapshot_until_complete():
    early = accepted_drudge_status()
    early["raid_runtime"]["drudge_charge"]["observations"] = []
    early["raid_runtime"]["drudge_charge"]["prepared_count"] = 0
    early["raid_runtime"]["drudge_charge"]["delivered_count"] = 0
    accepted, reasons = accepted_drudge_contract([early, accepted_drudge_status()])
    assert accepted is True
    assert reasons == []

    started = accepted_drudge_status()
    started["raid_runtime"]["drudge_charge"]["observations"][0]["landed"] = False
    landed = accepted_drudge_status()
    accepted, reasons = accepted_drudge_contract([started, landed])
    assert accepted is True
    assert "drudge_native_threat_source_250140_first_rush_not_landed" not in reasons

    regressed = accepted_drudge_status()
    regressed["raid_runtime"]["drudge_charge"]["observations"][0]["landed"] = False
    accepted, reasons = accepted_drudge_contract([landed, regressed])
    assert accepted is False
    assert "drudge_native_threat_landing_regressed" in reasons

    changed_target = accepted_drudge_status()
    changed_target["raid_runtime"]["drudge_charge"]["observations"][0]["landed"] = False
    changed_target_landed = accepted_drudge_status()
    changed = changed_target_landed["raid_runtime"]["drudge_charge"]["observations"][0]
    changed["target_guid"] = changed_target_landed["raid_runtime"]["roster"][4]["guid"]
    changed["target_raw_guid"] = changed["target_guid"]
    accepted, reasons = accepted_drudge_contract([changed_target, changed_target_landed])
    assert accepted is False
    assert "drudge_native_threat_observation_identity_drift" in reasons

    changed_scope = accepted_drudge_status()
    changed_scope["raid_runtime"]["drudge_charge"]["observations"][0]["landed"] = False
    changed_scope["raid_runtime"]["drudge_charge"]["observations"][0]["attempt_id"] = 99
    accepted, reasons = accepted_drudge_contract([changed_scope, accepted_drudge_status()])
    assert accepted is False
    assert "drudge_native_threat_observation_scope_drift" in reasons

    malformed_landing = accepted_drudge_status()
    malformed_landing["raid_runtime"]["drudge_charge"]["observations"][0]["landed"] = "false"
    accepted, reasons = accepted_drudge_contract([malformed_landing, accepted_drudge_status()])
    assert accepted is False
    assert "drudge_native_threat_landing_type_invalid" in reasons

    forged_farthest = accepted_drudge_status()
    first = forged_farthest["raid_runtime"]["drudge_charge"]["observations"][0]
    first["target_guid"] = forged_farthest["raid_runtime"]["roster"][4]["guid"]
    first["target_raw_guid"] = first["target_guid"]
    first["selected_distance"] = 34.5
    accepted, reasons = accepted_drudge_contract([forged_farthest])
    assert accepted is False
    assert "drudge_native_threat_selected_target_not_farthest" in reasons

    forged_seed = accepted_drudge_status()
    forged_seed["raid_runtime"]["drudge_threat_seed"]["observations"][0]["source_guid"] = 999999
    accepted, reasons = accepted_drudge_contract([forged_seed])
    assert accepted is False
    assert "drudge_threat_seed_source_identity_invalid" in reasons


def test_drudge_anchor_fallback_is_generation_scoped_and_native_path_validated():
    source = (Path(__file__).parents[1] / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(
        encoding="utf-8",
    )
    assert "ValidationRouteDrudgeAnchorAttemptId" in source
    assert "ValidationRouteDrudgeAnchorWipeGeneration" in source
    assert "ValidationRouteDrudgeAnchorRouteGeneration" in source
    assert "selectPathableDrudgeAnchor" in source
    assert "strictNativePath(candidates[candidateIndex].first" in source
    assert "anchor_path_valid" in source


def test_acceptance_reconstructs_all_identity_facts():
    accepted, reasons = accepted_foundation_status(accepted_status())
    assert accepted is True
    assert reasons == []


def test_magmaw_diagnostic_accepts_only_its_materialized_roster_identity():
    status = accepted_status()
    runtime = status["raid_runtime"]
    profile = "blackwing_descent_10n_magmaw_diagnostic"
    expected = _expected_identity_by_slot(profile)
    runtime["strategy_id"] = profile
    runtime["route_progress"] = {"generation": 4, "node_index": 3}
    for row in runtime["roster"]:
        identity = expected[row["roster_slot_id"]]
        gear_guid_by_slot = {
            item["slot"]: item["guid"]
            for item in row["gear_identity_manifest"]["items"]
        }
        row.update(
            guid=identity["character_guid"],
            account_id=identity["account_id"],
            account=identity["account"],
            name=identity["name"],
            class_id=identity["class_id"],
            class_spec=identity["class_spec"],
            talents=list(identity["talents"]),
            glyphs=list(identity["glyphs"]),
        )
        row["gear_identity_manifest"]["items"] = [
            {
                "slot": item["slot"],
                "guid": gear_guid_by_slot[item["slot"]],
                "entry": item["entry"],
                "enchant_id": item["enchant_id"],
                "gem_item_ids": list(item["gem_item_ids"]),
                "reforge_id": item["reforge_id"],
            }
            for item in identity["gear"]
        ]
    runtime["leader_guid"] = runtime["roster"][0]["guid"]
    accepted, reasons = accepted_foundation_status(
        status,
        profile_name=profile,
        route_partition={"node_count": 4, "terminal_index": 3},
    )
    assert accepted is True
    assert reasons == []


def test_diagnostic_capture_rejects_cross_shard_account_and_guid_identity():
    status = accepted_status()
    runtime = status["raid_runtime"]
    profile = "blackwing_descent_10n_magmaw_diagnostic"
    runtime["strategy_id"] = profile
    runtime["route_progress"] = {"generation": 4, "node_index": 3}
    magmaw = _expected_identity_by_slot(profile)["raid_tank_1"]
    omnotron = _expected_identity_by_slot("blackwing_descent_10n_omnotron_diagnostic")["raid_tank_1"]
    row = runtime["roster"][0]
    row.update(
        guid=omnotron["character_guid"],
        account_id=omnotron["account_id"],
        account=omnotron["account"],
        name=omnotron["name"],
    )
    accepted, reasons = accepted_foundation_status(
        status,
        profile_name=profile,
        route_partition={"node_count": 4, "terminal_index": 3},
    )
    assert accepted is False
    assert "frozen_identity_account_mismatch" in reasons
    assert "frozen_identity_character_guid_mismatch" in reasons
    assert magmaw["account"] != omnotron["account"]


def test_wrong_difficulty_duplicate_identity_and_cleanup_shape_fail():
    status = accepted_status()
    status["raid_runtime"]["map_difficulty"] = 2
    status["raid_runtime"]["roster"][-1]["guid"] = status["raid_runtime"]["roster"][0]["guid"]
    accepted, reasons = accepted_foundation_status(status)
    assert accepted is False
    assert "live_map_difficulty_10n" in reasons
    assert "unique_roster_guids" in reasons


def test_leader_must_be_one_of_the_exact_frozen_roster_guids():
    status = accepted_status()
    status["raid_runtime"]["leader_guid"] = 999999
    accepted, reasons = accepted_foundation_status(status)
    assert accepted is False
    assert "leader_not_in_exact_roster" in reasons


def test_foundation_rejects_empty_profile_assignment_and_stale_lockout_identity():
    status = accepted_status()
    status["raid_runtime"].update(
        profile_generation=0,
        profile_content_hash="",
        assignment_generation=0,
        lockout_save_id=43,
    )
    accepted, reasons = accepted_foundation_status(status)
    assert accepted is False
    assert "profile_generation_owned" in reasons
    assert "profile_content_hash_owned" in reasons
    assert "assignment_generation_owned" in reasons
    assert "lockout_save_matches_live_instance" in reasons


def test_roster_serialization_order_does_not_change_assignment_acceptance():
    status = accepted_status()
    status["raid_runtime"]["roster"].reverse()
    accepted, reasons = accepted_foundation_status(status)
    assert accepted is True
    assert reasons == []


def test_json_action_parser_ignores_prefix_and_malformed_rows():
    log = b'TC> {"ok":true,"action":"botauto_status","bots":10}\nnot-json\n{"action":"other"}\n'
    assert json_actions(log, "botauto_status") == [{"ok": True, "action": "botauto_status", "bots": 10}]


def test_json_log_cursor_reads_append_only_chunks_once_and_preserves_partial_rows(tmp_path: Path):
    path = tmp_path / "worldserver.log"
    first = b'TC> {"action":"botauto_status","evidence_sequence":1}\n'
    second = b'TC> {"action":"botauto_diagnose","evidence_sequence":2}\n'
    third = b'TC> {"action":"botauto_trace","evidence_sequence":3}\n'
    path.write_bytes(first + second[:17])
    cursor = JsonLogCursor(path)

    assert cursor.read_new_rows() == json_rows(first)
    assert cursor.read_new_rows() == []

    with path.open("ab") as handle:
        handle.write(second[17:] + third)
    incremental = cursor.read_new_rows()
    assert incremental == json_rows(second + third)
    assert cursor.read_new_rows() == []
    assert cursor.offset == path.stat().st_size
    assert [row["action"] for row in incremental] == [
        "botauto_diagnose", "botauto_trace",
    ]


def test_action_projection_reuses_normalized_payloads_without_reparsing_log():
    rows = normalized_batch_payload(
        b'{"action":"botauto_status"}\n{"action":"botauto_trace"}\n'
    )
    projected = action_payloads(rows, "botauto_trace")
    assert projected == [rows[1]["payload"]]
    assert projected[0] is rows[1]["payload"]


def test_normalized_batch_payload_is_ordered_and_forbidden_assistance_is_recomputed():
    log = (
        b'TC> {"action":"botauto_status","evidence_sequence":3}\n'
        b'TC> {"action":"botauto_trace","forbidden_completion_assists":[]}\n'
        b'TC> {"action":"botauto_diagnose","forbidden_completion_assists":[{"action":"forced_kill"}]}\n'
    )
    rows = normalized_batch_payload(log)
    assert [row["capture_sequence"] for row in rows] == [1, 2, 3]
    assert [row["action"] for row in rows] == ["botauto_status", "botauto_trace", "botauto_diagnose"]
    assert _forbidden_assistance_entries(rows)[0]["path"].endswith("forbidden_completion_assists")


def test_native_wipe_reset_recovery_is_reconstructed_across_statuses():
    ready = accepted_status()
    ready["raid_runtime"]["evidence_sequence"] = 1
    engaged = accepted_status()
    engaged["raid_runtime"].update(
        evidence_sequence=2, encounter_in_progress=True, boss_states=[1] + [0] * 5,
        ready_check_satisfied=False, wipe_state="engaged", recovery_state="none",
    )
    wiped = accepted_status()
    wiped["raid_runtime"].update(
        evidence_sequence=70, alive_size=0, ready_check_satisfied=False, wipe_generation=1,
        encounter_in_progress=False, recovery_state="release_resurrection_pending",
        wipe_state="wiped",
    )
    reset = accepted_status()
    reset["raid_runtime"].update(
        evidence_sequence=71, alive_size=0, boss_reset_generation=1, wipe_generation=1,
        recovery_state="release_resurrection_pending", wipe_state="wiped",
    )
    recovered = accepted_status()
    recovered["raid_runtime"].update(
        evidence_sequence=72, boss_reset_generation=1, wipe_generation=1, recovery_generation=1,
        recovery_state="recovered_ready_check", wipe_state="ready",
    )
    recovered["raid_runtime"]["native_recovery"] = {
        "death_observed": True, "corpse_observed": True, "release_observed": True,
        "resurrection_observed": True, "runback_observed": True,
        "ready_check_action_observed": True, "evidence_complete": True,
        "ready_check_action_generation": 2, "ready_check_action_attempt_id": 1,
        "ready_check_action_wipe_generation": 1,
        "ready_check_assignment_generation": 1,
        "ready_check_action_evidence_sequence": 72,
        "recovery_wipe_generation": 1,
        "members": [
            {
                "guid": 1001 + index, "wipe_generation": 1,
                "death_sequence": 10 + index * 6,
                "corpse_sequence": 11 + index * 6,
                "release_sequence": 12 + index * 6,
                "runback_sequence": 13 + index * 6,
                "reentry_sequence": 14 + index * 6,
                "resurrection_sequence": 15 + index * 6,
            }
            for index in range(10)
        ],
    }
    accepted, reasons = accepted_native_recovery([ready, engaged, wiped, reset, recovered])
    assert accepted is True
    assert reasons == []

    pre_magmaw = json.loads(json.dumps([ready, engaged, wiped, reset, recovered]))
    for status in pre_magmaw:
        status["raid_runtime"]["route_progress"] = {"generation": 3, "node_index": 2}
    accepted, reasons = accepted_native_recovery(pre_magmaw)
    assert accepted is False
    assert "native_magmaw_engagement_not_observed" in reasons

    stale = json.loads(json.dumps([ready, engaged, wiped, reset, recovered]))
    stale[1]["raid_runtime"]["evidence_sequence"] = 101
    stale[2]["raid_runtime"]["evidence_sequence"] = 102
    stale[3]["raid_runtime"]["evidence_sequence"] = 103
    stale[4]["raid_runtime"]["evidence_sequence"] = 170
    stale[4]["raid_runtime"]["native_recovery"]["ready_check_action_evidence_sequence"] = 170
    accepted, reasons = accepted_native_recovery(stale)
    assert accepted is False
    assert "native_per_member_recovery_predates_latest_engagement" in reasons

    future_deaths = json.loads(json.dumps([ready, engaged, wiped, reset, recovered]))
    future_deaths[1]["raid_runtime"]["evidence_sequence"] = 101
    future_deaths[2]["raid_runtime"]["evidence_sequence"] = 102
    future_deaths[3]["raid_runtime"]["evidence_sequence"] = 180
    future_deaths[4]["raid_runtime"]["evidence_sequence"] = 240
    future_deaths[4]["raid_runtime"]["native_recovery"]["ready_check_action_evidence_sequence"] = 240
    for index, member in enumerate(future_deaths[4]["raid_runtime"]["native_recovery"]["members"]):
        for offset, field in enumerate((
            "death_sequence", "corpse_sequence", "release_sequence",
            "runback_sequence", "reentry_sequence", "resurrection_sequence",
        )):
            member[field] = 120 + index * 6 + offset
    accepted, reasons = accepted_native_recovery(future_deaths)
    assert accepted is False
    assert "native_per_member_death_postdates_latest_wipe_snapshot" in reasons


def test_native_recovery_requires_post_wipe_reset_increment_and_bounded_member_sequences():
    ready = accepted_status()
    ready["raid_runtime"].update(evidence_sequence=1, boss_reset_generation=7)
    engaged = accepted_status()
    engaged["raid_runtime"].update(
        evidence_sequence=2, boss_reset_generation=7, encounter_in_progress=True,
        boss_states=[1] + [0] * 5, ready_check_satisfied=False,
        wipe_state="engaged", recovery_state="none",
    )
    wiped = accepted_status()
    wiped["raid_runtime"].update(
        evidence_sequence=3, boss_reset_generation=7, wipe_generation=1,
        boss_reset_generation_at_wipe=7,
        alive_size=0, ready_check_satisfied=False, encounter_in_progress=False,
        wipe_state="wiped", recovery_state="release_resurrection_pending",
    )
    unchanged_reset = accepted_status()
    unchanged_reset["raid_runtime"].update(
        evidence_sequence=4, boss_reset_generation=7, wipe_generation=1,
        alive_size=0, wipe_state="wiped",
        recovery_state="release_resurrection_pending",
    )
    recovered = accepted_status()
    recovered["raid_runtime"].update(
        evidence_sequence=5, boss_reset_generation=7, wipe_generation=1,
        recovery_generation=1, recovery_state="recovered_ready_check",
        wipe_state="ready",
    )
    recovered["raid_runtime"]["native_recovery"] = {
        "death_observed": True, "corpse_observed": True, "release_observed": True,
        "resurrection_observed": True, "runback_observed": True,
        "ready_check_action_observed": True, "evidence_complete": True,
        "ready_check_action_generation": 2, "ready_check_action_attempt_id": 1,
        "ready_check_action_wipe_generation": 1,
        "ready_check_assignment_generation": 1,
        "ready_check_action_evidence_sequence": 5,
        "recovery_wipe_generation": 1,
        "members": [
            {
                "guid": 1001 + index, "wipe_generation": 1,
                "death_sequence": 10 + index * 6,
                "corpse_sequence": 11 + index * 6,
                "release_sequence": 12 + index * 6,
                "runback_sequence": 13 + index * 6,
                "reentry_sequence": 14 + index * 6,
                "resurrection_sequence": 15 + index * 6,
            }
            for index in range(10)
        ],
    }
    accepted, reasons = accepted_native_recovery(
        [ready, engaged, wiped, unchanged_reset, recovered]
    )
    assert accepted is False
    assert "boss_reset_observed" in reasons

    valid = json.loads(json.dumps(recovered))
    accepted, reasons = accepted_native_recovery(
        [ready, engaged, wiped, unchanged_reset, valid]
    )
    assert accepted is False
    assert "native_per_member_death_postdates_latest_wipe_snapshot" in reasons


def test_native_recovery_does_not_cross_pair_reset_from_an_earlier_wipe():
    ready = accepted_status()
    engaged1 = accepted_status()
    engaged1["raid_runtime"].update(
        evidence_sequence=2, encounter_in_progress=True,
        boss_states=[1] + [0] * 5, ready_check_satisfied=False,
        wipe_state="engaged", recovery_state="none",
    )
    wiped1 = accepted_status()
    wiped1["raid_runtime"].update(
        evidence_sequence=3, alive_size=0, wipe_generation=1,
        boss_reset_generation_at_wipe=0, ready_check_satisfied=False,
        wipe_state="wiped", recovery_state="release_resurrection_pending",
    )
    reset1 = json.loads(json.dumps(wiped1))
    reset1["raid_runtime"].update(evidence_sequence=4, boss_reset_generation=1)
    recovered1 = accepted_status()
    recovered1["raid_runtime"].update(
        evidence_sequence=70, wipe_generation=1, boss_reset_generation=1,
        recovery_generation=1, recovery_state="recovered_ready_check",
    )
    engaged2 = json.loads(json.dumps(engaged1))
    engaged2["raid_runtime"].update(
        evidence_sequence=71, wipe_generation=1, boss_reset_generation=1,
        recovery_generation=1,
    )
    wiped2 = json.loads(json.dumps(wiped1))
    wiped2["raid_runtime"].update(
        evidence_sequence=72, wipe_generation=2, boss_reset_generation=1,
        boss_reset_generation_at_wipe=1, recovery_generation=1,
    )
    recovered2 = accepted_status()
    recovered2["raid_runtime"].update(
        evidence_sequence=140, wipe_generation=2, boss_reset_generation=1,
        boss_reset_generation_at_wipe=1, recovery_generation=2,
        recovery_state="recovered_ready_check",
    )
    recovered2["raid_runtime"]["native_recovery"] = {
        "death_observed": True, "corpse_observed": True, "release_observed": True,
        "resurrection_observed": True, "runback_observed": True,
        "ready_check_action_observed": True, "evidence_complete": True,
        "ready_check_action_generation": 3, "ready_check_action_attempt_id": 1,
        "ready_check_action_wipe_generation": 2,
        "ready_check_assignment_generation": 1,
        "ready_check_action_evidence_sequence": 140,
        "recovery_wipe_generation": 2,
        "members": [
            {
                "guid": 1001 + index, "wipe_generation": 2,
                "death_sequence": 75 + index * 6,
                "corpse_sequence": 76 + index * 6,
                "release_sequence": 77 + index * 6,
                "runback_sequence": 78 + index * 6,
                "reentry_sequence": 79 + index * 6,
                "resurrection_sequence": 80 + index * 6,
            }
            for index in range(10)
        ],
    }
    accepted, reasons = accepted_native_recovery(
        [ready, engaged1, wiped1, reset1, recovered1, engaged2, wiped2, recovered2]
    )
    assert accepted is False
    assert "boss_reset_observed" in reasons


def test_native_recovery_requires_the_latest_wipe_transition_in_retained_evidence():
    ready = accepted_status()
    engaged = accepted_status()
    engaged["raid_runtime"].update(
        evidence_sequence=2, encounter_in_progress=True,
        boss_states=[1] + [0] * 5, ready_check_satisfied=False,
        wipe_state="engaged", recovery_state="none",
    )
    wiped = accepted_status()
    wiped["raid_runtime"].update(
        evidence_sequence=3, alive_size=0, wipe_generation=1,
        boss_reset_generation_at_wipe=0, ready_check_satisfied=False,
        wipe_state="wiped", recovery_state="release_resurrection_pending",
    )
    reset = json.loads(json.dumps(wiped))
    reset["raid_runtime"].update(evidence_sequence=4, boss_reset_generation=1)
    recovered = accepted_status()
    recovered["raid_runtime"].update(
        evidence_sequence=70, wipe_generation=1, boss_reset_generation=1,
        recovery_generation=1, recovery_state="recovered_ready_check",
    )
    final_without_observed_second_wipe = accepted_status()
    final_without_observed_second_wipe["raid_runtime"].update(
        evidence_sequence=140, wipe_generation=2, boss_reset_generation=2,
        recovery_generation=2, recovery_state="recovered_ready_check",
    )
    final_without_observed_second_wipe["raid_runtime"]["native_recovery"] = {
        "death_observed": True, "corpse_observed": True, "release_observed": True,
        "resurrection_observed": True, "runback_observed": True,
        "ready_check_action_observed": True, "evidence_complete": True,
        "ready_check_action_generation": 3, "ready_check_action_attempt_id": 1,
        "ready_check_action_wipe_generation": 2,
        "ready_check_assignment_generation": 1,
        "ready_check_action_evidence_sequence": 140,
        "recovery_wipe_generation": 2,
        "members": [
            {
                "guid": 1001 + index, "wipe_generation": 2,
                "death_sequence": 75 + index * 6,
                "corpse_sequence": 76 + index * 6,
                "release_sequence": 77 + index * 6,
                "runback_sequence": 78 + index * 6,
                "reentry_sequence": 79 + index * 6,
                "resurrection_sequence": 80 + index * 6,
            }
            for index in range(10)
        ],
    }
    accepted, reasons = accepted_native_recovery(
        [ready, engaged, wiped, reset, recovered, final_without_observed_second_wipe]
    )
    assert accepted is False
    assert "native_latest_wipe_transition_not_observed" in reasons


def test_native_recovery_rejects_stored_ready_without_observed_transitions():
    accepted, reasons = accepted_native_recovery([accepted_status()])
    assert accepted is False
    assert "native_wipe_observed" in reasons
    assert "boss_reset_observed" in reasons
    assert "native_recovery_observed" in reasons


def test_native_recovery_rejects_mixed_identity_duplicate_sequence_and_wrong_composition():
    first = accepted_status()
    second = accepted_status()
    second["raid_runtime"]["group_guid"] = 999
    second["raid_runtime"]["evidence_sequence"] = 2
    accepted, reasons = accepted_native_recovery([first, second])
    assert accepted is False
    assert "native_recovery_mixed_identity" in reasons

    decreasing = accepted_status()
    first_sequence = accepted_status()
    first_sequence["raid_runtime"]["evidence_sequence"] = 2
    accepted, reasons = accepted_native_recovery([first_sequence, decreasing])
    assert accepted is False
    assert "native_evidence_sequence_not_monotonic" in reasons

    bad_roles = accepted_status()
    bad_roles["raid_runtime"]["roster"][9]["role"] = "healer"
    accepted, reasons = accepted_foundation_status(bad_roles)
    assert accepted is False
    assert "exact_10n_role_composition" in reasons


def test_repeated_snapshots_are_allowed_but_strategy_transition_requires_route_advance():
    first = accepted_status()
    repeated = accepted_status()
    accepted, reasons = accepted_native_recovery([first, repeated])
    assert not accepted
    assert "native_wipe_observed" in reasons

    transitioned = accepted_status()
    transitioned["raid_runtime"].update(
        evidence_sequence=2,
        strategy_id="blackwing_descent_10n_boss_route",
        route_progress={"generation": 5, "node_index": 4},
        strategy_transition={
            "from_strategy": "blackwing_descent_10n",
            "to_strategy": "blackwing_descent_10n_boss_route",
            "advanced": True,
        },
    )
    accepted, reasons = accepted_native_recovery([first, transitioned])
    assert "native_strategy_transition_without_route_advancement" not in reasons


def test_forbidden_event_markers_are_rejected_while_native_fields_are_not():
    rows = normalized_batch_payload(
        b'{"action":"native_recovery","result":"direct_resurrection"}\n'
        b'{"action":"botauto_status","recovery_state":"release_resurrection_pending"}\n'
    )
    found = _forbidden_assistance_entries(rows)
    assert any(entry["kind"] == "forbidden_event_marker" for entry in found)
    assert all("release_resurrection_pending" not in str(entry) for entry in found)


def test_no_fallback_diagnostic_is_not_misclassified_as_fallback_assistance():
    rows = normalized_batch_payload(
        b'{"action":"botauto_trace","recovery_mode":"blocked_no_fallback"}\n'
        b'{"action":"botauto_trace","recovery_mode":"fallback_action"}\n'
    )
    found = _forbidden_assistance_entries(rows)
    assert all(entry["value"] != "blocked_no_fallback" for entry in found)
    assert any(entry["value"] == "fallback_action" for entry in found)


def test_preflight_reports_coordinator_and_protected_process_overlap():
    report = preflight_runtime_exclusions(__import__("pathlib").Path.cwd())
    assert "coordinator_idle" in report
    assert "process_overlap" in report


def test_process_overlap_classifies_entrypoint_not_binary_data_argument():
    assert _protected_process_matches([
        "/usr/bin/pixi",
        "run",
        "python",
        "-m",
        "tools.raid_program.capture_phase1_raid_foundation",
        "--binary",
        "/tmp/build/worldserver",
    ]) == []
    assert _protected_process_matches(["/tmp/build/worldserver", "--config", "test.conf"]) == [
        "worldserver"
    ]
    assert _protected_process_matches([
        "/usr/bin/python3",
        "/repo/tools/bot_ml/run_live_bot_validation.py",
        "--worldserver",
        "/tmp/build/worldserver",
    ]) == ["run_live_bot_validation.py"]


def test_dvc_lineage_requires_an_exact_empty_json_status():
    assert _dvc_status_is_clean("{}") is True
    assert _dvc_status_is_clean('{"validation_scenarios": [{"changed outs": {}}]}') is False
    assert _dvc_status_is_clean("WARN inherited manifest\n{}") is False


def test_live_evidence_demux_rejects_cross_identity_runtime():
    first = accepted_status()
    first["cohort_id"] = "raid"
    second = accepted_status()
    second["cohort_id"] = "raid"
    second["raid_runtime"]["attempt_id"] = 2
    rows = normalized_batch_payload(
        (json.dumps(first) + "\n" + json.dumps(second) + "\n").encode()
    )
    assert "evidence_demux_cross_identity_row" in evidence_demux_rejections(rows)


def test_live_evidence_demux_rejects_profile_and_assignment_drift():
    active = accepted_status()
    active["cohort_id"] = "raid"
    drifted = json.loads(json.dumps(active))
    drifted["raid_runtime"]["profile_generation"] = 2
    drifted["raid_runtime"]["profile_content_hash"] = "different-profile"
    drifted["raid_runtime"]["assignment_generation"] = 9
    rows = normalized_batch_payload(
        (json.dumps(active) + "\n" + json.dumps(drifted) + "\n").encode()
    )
    assert "evidence_demux_cross_identity_row" in evidence_demux_rejections(rows)


def test_live_evidence_demux_binds_declared_route_transition_and_partial_death():
    active = accepted_status()
    active["cohort_id"] = "raid"
    transitioned = json.loads(json.dumps(active))
    transitioned["raid_runtime"]["strategy_id"] = "trash_two_tank_charge_lanes"
    transitioned["raid_runtime"]["route_progress"] = {"generation": 5, "node_index": 4}
    transitioned["raid_runtime"]["strategy_transition"] = {
        "from_strategy": active["raid_runtime"]["strategy_id"],
        "to_strategy": "trash_two_tank_charge_lanes",
        "advanced": True,
    }
    transitioned["raid_runtime"]["roster"][1]["active"] = False
    transitioned["raid_runtime"]["alive_size"] = 9
    bots = [{"bot_guid": 1001 + index} for index in range(10)]
    diagnosis = {
        "ok": True, "action": "botauto_diagnose", "cohort_id": "raid",
        "raid_runtime": transitioned["raid_runtime"], "bots": bots,
    }
    trace = {
        "ok": True, "action": "botauto_trace", "cohort_id": "raid",
        "raid_runtime": transitioned["raid_runtime"],
        "bots": [{"bot_guid": 1001 + index, "entries": [], "delta": True, "gap": False}
                 for index in range(10)],
    }
    readycheck = {
        "ok": True, "action": "botauto_readycheck", "cohort_id": "raid",
        "raid_runtime": transitioned["raid_runtime"],
    }
    stop = {
        "ok": True, "action": "botauto_stop", "cohort_id": "raid",
        "server_epoch": 88, "attempt_id": 1,
        "raid_runtime_before_cleanup": transitioned["raid_runtime"],
        "post_cleanup": {"active": False, "bots": 0, "lease_count": 0},
    }
    inactive = json.loads(json.dumps(transitioned))
    inactive["active"] = False
    inactive["bots"] = 0
    inactive["lease_count"] = 0
    inactive["server_epoch"] = 88
    inactive["attempt_id"] = 1
    inactive["raid_runtime"]["active"] = False
    rows = normalized_batch_payload(
        b"\n".join(json.dumps(row).encode()
                   for row in (active, transitioned, diagnosis, trace, readycheck, stop, inactive)) + b"\n"
    )
    report = evidence_demux_report(rows)
    assert report["rejections"] == []
    assert report["bound_rows"] == report["retained_rows"] == 7


def test_live_evidence_demux_rejects_lease_drift_and_trace_cursor_gap():
    active = accepted_status()
    active["cohort_id"] = "raid"
    drifted = json.loads(json.dumps(active))
    drifted["raid_runtime"]["roster"][1]["lease_owned"] = False
    gap = {
        "ok": True, "action": "botauto_trace", "cohort_id": "raid",
        "raid_runtime": active["raid_runtime"],
        "bots": [{"bot_guid": 1001 + index, "entries": [], "delta": True, "gap": index == 0}
                 for index in range(10)],
    }
    rows = normalized_batch_payload(
        b"\n".join(json.dumps(row).encode() for row in (active, drifted, gap)) + b"\n"
    )
    reasons = evidence_demux_rejections(rows)
    assert "evidence_demux_roster_binding_lease_invalid" in reasons
    assert "evidence_demux_trace_delta_gap" in reasons


def test_live_evidence_demux_rejects_frozen_character_build_drift():
    active = accepted_status()
    active["cohort_id"] = "raid"
    for field, replacement in (
        ("talents", [{"spell_id": 999999, "rank": 1}]),
        ("glyphs", [999999]),
        ("gear_identity_manifest", {"sha256": "forged"}),
    ):
        drifted = json.loads(json.dumps(active))
        drifted["raid_runtime"]["roster"][0][field] = replacement
        rows = normalized_batch_payload(
            b"\n".join(json.dumps(row).encode() for row in (active, drifted)) + b"\n"
        )
        assert "evidence_demux_cross_identity_row" in evidence_demux_rejections(rows)


def test_capture_telemetry_poll_is_incremental_and_bounded():
    root = Path(__file__).resolve().parents[1]
    capture_source = (root / "tools/raid_program/capture_phase1_raid_foundation.py").read_text(encoding="utf-8")
    manager_source = (root / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(encoding="utf-8")
    header_source = (root / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text(encoding="utf-8")

    # A long capture must not re-export the complete ring on every poll.  Keep
    # this source-level regression independent of a heavyweight worldserver
    # build while checking the command, cursor, and hard server-side bound.
    assert "botauto trace all 128 delta" in capture_source
    assert "TraceExportCursorByGuid" in manager_source
    assert "TraceExportCursorByGuid" in header_source
    assert "std::min<uint32>(limit, 128)" in manager_source
    assert "BuildRaidRuntimeJson(true)" in manager_source


def test_live_evidence_demux_rejects_strategy_drift():
    active = accepted_status()
    active["cohort_id"] = "raid"
    drifted = json.loads(json.dumps(active))
    drifted["action"] = "botauto_diagnose"
    drifted["raid_runtime"]["strategy_id"] = "different_strategy"
    rows = normalized_batch_payload(
        (json.dumps(active) + "\n" + json.dumps(drifted) + "\n").encode()
    )
    assert "evidence_demux_strategy_transition_without_route_advancement" in evidence_demux_rejections(rows)

    drifted["raid_runtime"].update(
            route_progress={"generation": 5, "node_index": 4},
        strategy_transition={
            "from_strategy": active["raid_runtime"]["strategy_id"],
            "to_strategy": "different_strategy",
            "advanced": True,
        },
    )
    rows = normalized_batch_payload(
        (json.dumps(active) + "\n" + json.dumps(drifted) + "\n").encode()
    )
    assert "evidence_demux_strategy_transition_without_route_advancement" not in evidence_demux_rejections(rows)


def test_live_evidence_demux_binds_readycheck_stop_and_inactive_cleanup():
    active = accepted_status()
    active["cohort_id"] = "raid"
    bot_rows = [{"bot_guid": 1001 + index} for index in range(10)]
    diagnosis = {
        "ok": True, "action": "botauto_diagnose", "cohort_id": "raid",
        "raid_runtime": active["raid_runtime"], "bots": bot_rows,
    }
    trace = {
        "ok": True, "action": "botauto_trace", "cohort_id": "raid",
        "raid_runtime": active["raid_runtime"], "bots": bot_rows,
    }
    readycheck = {
        "ok": True, "action": "botauto_readycheck", "cohort_id": "raid",
        "raid_runtime": active["raid_runtime"],
    }
    stop = {
        "ok": True, "action": "botauto_stop", "cohort_id": "raid",
        "server_epoch": 88, "attempt_id": 1,
        "raid_runtime_before_cleanup": active["raid_runtime"],
        "post_cleanup": {"active": False, "bots": 0, "lease_count": 0},
    }
    inactive = accepted_status()
    inactive["cohort_id"] = "raid"
    inactive["bots"] = 0
    inactive["lease_count"] = 0
    inactive["server_epoch"] = 88
    inactive["attempt_id"] = 1
    inactive["raid_runtime"]["active"] = False
    rows = normalized_batch_payload(
        b"\n".join(
            json.dumps(row).encode()
            for row in (active, diagnosis, trace, readycheck, stop, inactive)
        ) + b"\n"
    )
    report = evidence_demux_report(rows)
    assert report["rejections"] == []
    assert report["bound_rows"] == report["retained_rows"] == 6
    assert report["rejected_rows"] == report["unchecked_rows"] == 0
    assert len(report["canonical_identity_sha256"]) == 64
    assert len(report["canonical_roster_sha256"]) == 64
    assert all(row["identity_binding"]["state"] == "bound" for row in rows)


def test_live_evidence_demux_rejects_empty_diagnose_and_trace_roster_envelopes():
    active = accepted_status()
    active["cohort_id"] = "raid"
    envelopes = []
    for action in ("botauto_diagnose", "botauto_trace"):
        envelopes.append({
            "ok": True, "action": action, "cohort_id": "raid",
            "raid_runtime": active["raid_runtime"], "bots": [],
        })
    rows = normalized_batch_payload(
        b"\n".join(json.dumps(row).encode() for row in (active, *envelopes)) + b"\n"
    )
    reasons = evidence_demux_rejections(rows)
    assert "evidence_demux_diagnosis_roster_empty" in reasons
    assert "evidence_demux_trace_roster_empty" in reasons


def test_live_evidence_demux_rejects_missing_and_duplicate_telemetry_bot_rows():
    active = accepted_status()
    active["cohort_id"] = "raid"
    missing = {
        "ok": True, "action": "botauto_diagnose", "cohort_id": "raid",
        "raid_runtime": active["raid_runtime"],
        "bots": [{"bot_guid": 1001 + index} for index in range(9)],
    }
    duplicate = {
        "ok": True, "action": "botauto_trace", "cohort_id": "raid",
        "raid_runtime": active["raid_runtime"],
        "bots": [{"bot_guid": 1001 + index} for index in range(9)] + [{"bot_guid": 1001}],
    }
    rows = normalized_batch_payload(
        b"\n".join(json.dumps(row).encode() for row in (active, missing, duplicate)) + b"\n"
    )
    reasons = evidence_demux_rejections(rows)
    assert "evidence_demux_diagnosis_canonical_roster_incomplete" in reasons
    assert "evidence_demux_diagnosis_bot_row_count_invalid" in reasons
    assert "evidence_demux_trace_duplicate_bot_guid" in reasons
    assert "evidence_demux_trace_canonical_roster_incomplete" in reasons


def test_live_evidence_demux_rejects_failed_telemetry_envelopes_with_full_roster():
    active = accepted_status()
    active["cohort_id"] = "raid"
    bot_rows = [{"bot_guid": 1001 + index} for index in range(10)]
    failed = []
    for action in ("botauto_diagnose", "botauto_trace"):
        failed.append({
            "ok": False, "action": action, "cohort_id": "raid",
            "raid_runtime": active["raid_runtime"], "bots": bot_rows,
            "failure_reason": "synthetic_channel_failure",
        })
    rows = normalized_batch_payload(
        b"\n".join(json.dumps(row).encode() for row in (active, *failed)) + b"\n"
    )
    reasons = evidence_demux_rejections(rows)
    assert "evidence_demux_diagnosis_envelope_not_ok" in reasons
    assert "evidence_demux_trace_envelope_not_ok" in reasons


def test_live_evidence_demux_rejects_unclassified_and_unbound_readycheck():
    active = accepted_status()
    active["cohort_id"] = "raid"
    rows = normalized_batch_payload(
        (json.dumps(active) + "\n" + json.dumps({"action": "unknown"}) + "\n").encode()
    )
    reasons = evidence_demux_rejections(rows)
    assert "evidence_demux_unclassified_row" in reasons
    assert "evidence_demux_cleanup_missing" in reasons


def test_live_evidence_demux_accepts_bound_terminal_without_readycheck():
    active = accepted_status()
    active["cohort_id"] = "default"
    active["active_profile"] = "blackwing_descent_10n"
    terminal = json.loads(json.dumps(active))
    terminal["failure_reason"] = "drudge_partial_death_before_threat_seed"
    terminal["raid_runtime"]["alive_size"] = 3
    bots = [{"bot_guid": 1001 + index} for index in range(10)]
    diagnosis = {
        "ok": True, "action": "botauto_diagnose", "cohort_id": "default",
        "failure_reason": terminal["failure_reason"],
        "raid_runtime": terminal["raid_runtime"], "bots": bots,
    }
    trace = {
        "ok": True, "action": "botauto_trace", "cohort_id": "default",
        "failure_reason": terminal["failure_reason"],
        "raid_runtime": terminal["raid_runtime"],
        "bots": [{"bot_guid": 1001 + index, "entries": [], "delta": True, "gap": False}
                 for index in range(10)],
    }
    profile = {
        "ok": True, "action": "botauto_profile", "cohort_id": "default",
        "active_profile": "blackwing_descent_10n",
    }
    stop = {
        "ok": True, "action": "botauto_stop", "cohort_id": "default",
        "server_epoch": 88, "attempt_id": 1,
        "raid_runtime_before_cleanup": terminal["raid_runtime"],
        "post_cleanup": {"active": False, "bots": 0, "lease_count": 0},
    }
    inactive = json.loads(json.dumps(terminal))
    inactive["active"] = False
    inactive["bots"] = 0
    inactive["lease_count"] = 0
    inactive["server_epoch"] = 88
    inactive["attempt_id"] = 1
    inactive["raid_runtime"]["active"] = False
    rows = normalized_batch_payload(
        b"\n".join(json.dumps(row).encode() for row in (
            profile, active, terminal, diagnosis, trace, stop, inactive,
        )) + b"\n"
    )

    report = evidence_demux_report(rows)

    assert "evidence_demux_required_action_missing:botauto_readycheck" not in report["rejections"]
    assert report["rejections"] == []
    assert report["gate_passed"] is True


def test_live_evidence_demux_reconstructs_bindings_and_rejects_missing_lifecycle_identity():
    active = accepted_status()
    active["cohort_id"] = "raid"
    missing_runtime = {
        "ok": False, "action": "botauto_readycheck", "cohort_id": "raid",
        "failure_reason": "not_ready",
    }
    bad_stop = {
        "ok": True, "action": "botauto_stop", "cohort_id": "raid",
        "server_epoch": 88, "attempt_id": 1,
        "post_cleanup": {"active": False, "bots": 0, "lease_count": 0},
    }
    rows = normalized_batch_payload(
        b"\n".join(json.dumps(row).encode() for row in (active, missing_runtime, bad_stop)) + b"\n"
    )
    rows[0]["identity_binding"] = {"state": "bound", "canonical_identity_sha256": "0" * 64}
    report = evidence_demux_report(rows)
    assert "evidence_demux_identity_missing" in report["rejections"]
    assert report["rejected_rows"] == 2
    assert report["unchecked_rows"] == 0
    assert rows[0]["identity_binding"]["canonical_identity_sha256"] != "0" * 64


def test_canonical_capture_owns_tracked_v8_policy_and_has_no_policy_override():
    source = (
        Path(__file__).resolve().parents[1]
        / "tools/raid_program/capture_phase1_raid_foundation.py"
    ).read_text(encoding="utf-8")
    assert 'parser.add_argument("--build-policy"' not in source
    assert "cata_raid_build_resource_policy_degraded_v8.json" in source
    assert 'parser.add_argument("--build-attestation"' in source


def test_canonical_capture_is_terminal_gate_driven_without_a_raid_duration_cap():
    source = (
        Path(__file__).resolve().parents[1]
        / "tools/raid_program/capture_phase1_raid_foundation.py"
    ).read_text(encoding="utf-8")
    assert '"--observe-sec", type=int, default=0' in source
    assert "deadline = time.monotonic() + args.observe_sec if args.observe_sec else None" in source
    assert "deadline is None or time.monotonic() < deadline" in source
    assert '"wall_clock_mode": "uncapped" if args.observe_sec == 0' in source
    assert '"policy": "capture-process-heartbeat-terminal-gate-driven"' in source
    assert 'parser.add_argument("--semantic-stall-sec", type=int, default=300)' in source
    assert 'parser.add_argument("--telemetry-timeout-sec", type=int, default=60)' in source
    assert '"--diagnose-interval-sec", type=float, default=30.0,' in source
    assert '"--trace-interval-sec", type=float, default=20.0,' in source
    assert '"classification": "success" if success else (' in source


def test_phase1_capture_uses_approved_fail_closed_taxonomy():
    source = (
        Path(__file__).resolve().parents[1]
        / "tools/raid_program/capture_phase1_raid_foundation.py"
    ).read_text(encoding="utf-8")
    assert 'else "incomplete_evidence"' in source
    assert '"diagnostic_only" if forbidden_entries' in source
    assert '"infrastructure_abort" if (' in source
    for condition in (
        "process_return_code != 0",
        "not identity_stable",
        "bool(demux_rejections)",
        'not telemetry_envelopes["gate_passed"]',
    ):
        assert condition in source
    assert '"foundation_gate_failed"' not in source


def test_capture_interrupt_is_native_cleanup_backed_and_classified_without_traceback():
    source = (
        Path(__file__).resolve().parents[1]
        / "tools/raid_program/capture_phase1_raid_foundation.py"
    ).read_text(encoding="utf-8")
    assert "except KeyboardInterrupt:" in source
    assert 'startup_error = "KeyboardInterrupt:operator_interrupt"' in source
    assert 'process.stdin.write(b"botauto stop\\nbotauto status\\nserver exit\\n")' in source
    assert '"operator_interrupt": operator_interrupt' in source
    assert '"operator_reason": "operator_interrupt" if operator_interrupt else None' in source
    assert 'forced_evidence_report = request_final_evidence("operator_interrupt")' in source
    assert 'signal.signal(signal.SIGINT, signal.SIG_IGN)' in source
    # The explicit handler must appear before the generic Exception handler;
    # otherwise Ctrl-C remains an uncaught BaseException.
    assert source.index("except KeyboardInterrupt:") < source.index(
        "except Exception as error:  # captured as infrastructure evidence below"
    )


def test_every_terminal_capture_path_requests_a_fresh_full_evidence_bundle():
    source = (
        Path(__file__).resolve().parents[1]
        / "tools/raid_program/capture_phase1_raid_foundation.py"
    ).read_text(encoding="utf-8")
    for reason in (
        '"telemetry_channel_stale"',
        '"terminal_gate_or_process_exit"',
        '"operator_interrupt"',
        '"capture_exception"',
    ):
        assert reason in source
    assert source.count("request_final_evidence(") >= 5
    success = source[source.index("success = ("):source.index("report = {", source.index("success = ("))]
    assert "operator_interrupt is False" in success
    assert 'forced_evidence_report.get("gate_passed") is True' in success
    classification = source[source.index('"classification": "success"'):source.index('"started_at_utc"')]
    assert "or operator_interrupt" in classification
    assert 'forced_evidence_report.get("gate_passed") is not True' in classification
    post_capture = source[source.index("def defer_post_capture_interrupt"):source.index("success = (")]
    assert "nonlocal operator_interrupt, startup_error" in post_capture
    assert 'startup_error = "KeyboardInterrupt:operator_interrupt"' in post_capture
    assert "signal.signal(signal.SIGINT, defer_post_capture_interrupt)" in post_capture
    assert post_capture.rindex("signal.signal(signal.SIGINT, signal.SIG_IGN)") > post_capture.index(
        "normalized_rows = normalized_batch_payload(log_bytes)"
    )
    watchdog = source[source.index('"watchdog": {'):source.index('"preflight": preflight')]
    assert "operator_interrupt is False" in watchdog
    assert 'forced_evidence_report.get("gate_passed") is True' in watchdog


def test_uncapped_capture_fails_closed_when_any_telemetry_channel_is_stale():
    state = {}
    assert observe_telemetry_freshness(
        state, {"status": 1, "diagnosis": 1, "trace": 1}, 100.0, 30.0,
    ) == []
    assert observe_telemetry_freshness(
        state, {"status": 2, "diagnosis": 2, "trace": 1}, 125.0, 30.0,
    ) == []
    assert observe_telemetry_freshness(
        state, {"status": 3, "diagnosis": 3, "trace": 1}, 131.0, 30.0,
    ) == ["trace"]
    assert observe_telemetry_freshness(
        state, {"status": 3, "diagnosis": 3, "trace": 2}, 132.0, 30.0,
    ) == []


def test_semantic_progress_signature_tracks_boss_and_bot_decisions_not_heartbeats():
    status = accepted_status()
    status["duration_seconds"] = 1
    diagnosis = {
        "bots": [{
            "identity": {"bot_guid": 1001},
            "snapshot": {
                "decision": {"action": "attack", "result": "ok", "reason": "boss"},
                "route_progress": {"target": {"guid": 9001, "hp_pct": 75.0}},
            },
        }],
    }
    status["deaths"] = 0
    baseline = semantic_progress_signature(status, diagnosis)
    status["duration_seconds"] = 999
    assert semantic_progress_signature(status, diagnosis) == baseline
    status["deaths"] += 99
    assert semantic_progress_signature(status, diagnosis) == baseline
    diagnosis["bots"][0]["snapshot"]["decision"]["action"] = "different_wrong_action"
    assert semantic_progress_signature(status, diagnosis) == baseline
    diagnosis["bots"][0]["snapshot"]["route_progress"]["target"]["hp_pct"] = 74.0
    assert semantic_progress_signature(status, diagnosis) != baseline


def test_monotonic_semantic_progress_rejects_cast_victim_and_hp_oscillation():
    status = accepted_status()
    status["validation_route"] = {"generation": 1, "manifest_index": 1}
    diagnosis = {
        "bots": [{
            "identity": {"bot_guid": 1001},
            "snapshot": {"route_progress": {
                "target": {"guid": 9001, "entry": 41570, "hp_pct": 75.0, "best_hp_pct": 75.0},
                "state": {"victim_guid": 9001, "bot_casting": False},
            }},
        }],
    }
    status["deaths"] = 0
    status["raid_runtime"]["encounter_phase"] = "combat"
    state = {}
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is True
    diagnosis["bots"][0]["snapshot"]["route_progress"]["state"] = {
        "victim_guid": 9002, "bot_casting": True,
    }
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    status["deaths"] += 1
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    diagnosis["bots"][0]["snapshot"]["route_progress"]["target"]["guid"] = 9002
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    status["raid_runtime"]["encounter_phase"] = "impaled"
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is True
    status["raid_runtime"]["encounter_phase"] = "combat"
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    diagnosis["bots"][0]["snapshot"]["route_progress"]["target"].update(
        hp_pct=80.0, best_hp_pct=80.0,
    )
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    diagnosis["bots"][0]["snapshot"]["route_progress"]["target"].update(
        hp_pct=74.0, best_hp_pct=74.0,
    )
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is True
    status["raid_runtime"]["wipe_generation"] += 1
    status["raid_runtime"]["boss_reset_generation"] += 1
    status["raid_runtime"]["recovery_generation"] += 1
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    status["raid_runtime"]["boss_reset_generation"] += 1
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    status["raid_runtime"]["native_recovery"].update(
        death_observed=True,
        corpse_observed=True,
        release_observed=True,
    )
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    status["raid_runtime"]["evidence_sequence"] = 80
    status["raid_runtime"]["native_recovery"].update(
        runback_observed=True,
        resurrection_observed=True,
        ready_check_action_observed=True,
        evidence_complete=True,
        recovery_wipe_generation=status["raid_runtime"]["wipe_generation"],
        ready_check_action_generation=2,
        ready_check_response_count=10,
        ready_check_action_attempt_id=status["raid_runtime"]["attempt_id"],
        ready_check_action_wipe_generation=status["raid_runtime"]["wipe_generation"],
        ready_check_assignment_generation=status["raid_runtime"]["assignment_generation"],
        ready_check_action_evidence_sequence=80,
        members=[
            {
                "guid": 1001 + index,
                "wipe_generation": status["raid_runtime"]["wipe_generation"],
                "death_sequence": 10 + index * 6,
                "corpse_sequence": 11 + index * 6,
                "release_sequence": 12 + index * 6,
                "runback_sequence": 13 + index * 6,
                "reentry_sequence": 14 + index * 6,
                "resurrection_sequence": 15 + index * 6,
            }
            for index in range(10)
        ],
    )
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is True
    status["raid_runtime"]["recovery_generation"] += 1
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
    status["raid_runtime"]["boss_reset_generation"] += 1
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is False
