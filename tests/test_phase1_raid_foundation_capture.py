import json
from pathlib import Path
from types import SimpleNamespace

from tools.raid_program.capture_phase1_raid_foundation import (
    accepted_foundation_status,
    accepted_native_recovery,
    json_actions,
    normalized_batch_payload,
    _forbidden_assistance_entries,
    expected_bwd_10n_roster,
    _expected_identity_by_slot,
    preflight_runtime_exclusions,
    validate_runtime_profile_assets,
    evidence_demux_report,
    evidence_demux_rejections,
    semantic_progress_signature,
    observe_monotonic_semantic_progress,
    observe_telemetry_freshness,
)


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


def test_capture_preflight_requires_matching_hydrated_route_manifest(tmp_path: Path):
    worktree = tmp_path / "worktree"
    reference = tmp_path / "reference"
    route = "".join(json.dumps({
        "scenario_id": "blackwing_descent_10n",
        "step": step,
        "route_node_id": f"node-{step}",
        "kind": "boss",
    }) + "\n" for step in range(1, 10))
    _write_runtime_profile_assets(worktree, route)
    _write_runtime_profile_assets(reference, route)

    accepted = validate_runtime_profile_assets(worktree, reference, require_dvc_lineage=False)
    assert accepted["passed"] is True
    assert accepted["matching_route_rows"] == 9
    assert accepted["route_sha256"] == accepted["reference_route_sha256"]

    (worktree / "dataset/validation_scenarios/validation_routes.jsonl").unlink()
    missing = validate_runtime_profile_assets(worktree, reference, require_dvc_lineage=False)
    assert missing["passed"] is False
    assert "worktree_route_manifest_unreadable" in missing["reasons"]

    _write_runtime_profile_assets(worktree, json.dumps({
        "scenario_id": "stonecore_5n", "route_node_id": "wrong", "kind": "boss",
    }) + "\n")
    wrong = validate_runtime_profile_assets(worktree, reference, require_dvc_lineage=False)
    assert wrong["passed"] is False
    assert "worktree_route_expected_nine_rows" in wrong["reasons"]
    assert "runtime_route_differs_from_reference" in wrong["reasons"]


def test_capture_preflight_rejects_dirty_dvc_lineage(tmp_path: Path, monkeypatch):
    worktree = tmp_path / "worktree"
    reference = tmp_path / "reference"
    route = "".join(json.dumps({
        "scenario_id": "blackwing_descent_10n",
        "route_node_id": f"node-{step}",
        "kind": "boss",
    }) + "\n" for step in range(9))
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


def test_acceptance_reconstructs_all_identity_facts():
    accepted, reasons = accepted_foundation_status(accepted_status())
    assert accepted is True
    assert reasons == []


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
        route_progress={"generation": 1, "node_index": 1},
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
        route_progress={"generation": 1, "node_index": 1},
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
    assert 'parser.add_argument("--telemetry-timeout-sec", type=int, default=30)' in source
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
    baseline = semantic_progress_signature(status, diagnosis)
    status["duration_seconds"] = 999
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
                "target": {"guid": 9001, "hp_pct": 75.0, "best_hp_pct": 75.0},
                "state": {"victim_guid": 9001, "bot_casting": False},
            }},
        }],
    }
    state = {}
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is True
    diagnosis["bots"][0]["snapshot"]["route_progress"]["state"] = {
        "victim_guid": 9002, "bot_casting": True,
    }
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
    assert observe_monotonic_semantic_progress(state, status, diagnosis) is True
