import base64
import json
from pathlib import Path

from tools.raid_program.tactical_replay_lite import build_replay


def _bound(channel: str, action: str, payload: dict) -> dict:
    return {
        "action": action,
        "capture_sequence": 1,
        "evidence_channel": channel,
        "identity_binding": {"state": "bound"},
        "normalized_schema_version": 2,
        "payload": payload,
    }


def _movement(receipt_id: int, timestamp_ms: int, z: float, *, submitted: bool) -> dict:
    return {
        "available": True,
        "bot_guid": 7,
        "gate": "executor_admission",
        "result": "accepted" if submitted else "rejected",
        "reason": "" if submitted else "route_destination_partial_path",
        "planner": {
            "gate": "path_admission",
            "result": "accepted" if submitted else "rejected",
            "reason": "" if submitted else "route_destination_partial_path",
        },
        "launch_receipt": {
            "id": receipt_id,
            "identity": {
                "bot_guid": 7,
                "intent_reason": "ranged_formation_restore",
                "intent_fingerprint": "7a4fd042a9143195",
                "owner": "mechanic",
                "scope": {"attempt_id": 1, "route_generation": 4},
            },
            "actor_before_planning": {
                "available": True,
                "x": 1.0,
                "y": 2.0,
                "z": z,
            },
            "executor": {
                "generate_path": submitted,
                "requested": {"x": 5.0, "y": 6.0, "z": 211.0},
                "actor_before_submission": {
                    "available": submitted,
                    "x": 1.0,
                    "y": 2.0,
                    "z": z,
                },
            },
            "planner_path": {
                "calculated": True,
                "complete": submitted,
                "type": 1 if submitted else 196,
                "controls": {"count": 3, "fingerprint": "abc"},
                "floor_observation_conflict": submitted,
                "floor_observation": {"failure": "sample_floor_gap" if submitted else "none"},
                "selected_endpoint": {
                    "available": submitted,
                    "x": 5.0,
                    "y": 6.0,
                    "z": 211.0,
                },
            },
            "launches": (
                [
                    {
                        "spline_launch": {
                            "attempted": True,
                            "succeeded": True,
                            "spline_id": 77,
                            "controls": {"count": 3, "fingerprint": "abc"},
                        }
                    }
                ]
                if submitted
                else []
            ),
            "progress": {
                "available": submitted,
                "armed_at_ms": timestamp_ms if submitted else 0,
                "last_observed_at_ms": timestamp_ms + 100 if submitted else 0,
                "terminal": False,
                "terminal_outcome": "pending",
                "samples": (
                    [
                        {
                            "observed_at_ms": timestamp_ms + 100,
                            "actor": {
                                "available": True,
                                "alive": True,
                                "x": 2.0,
                                "y": 3.0,
                                "z": 211.0,
                            },
                            "floor": {
                                "z": 211.0,
                                "valid": True,
                                "selected_platform_compatible": True,
                            },
                            "native_motion": {
                                "spline_id": 77,
                                "matches_launched_spline": True,
                                "moving": True,
                            },
                            "outcome": "native_motion_in_progress",
                            "terminal": False,
                        }
                    ]
                    if submitted
                    else []
                ),
            },
        },
    }


def _receipt_history(receipt_id: int) -> dict:
    sample_times = [1_025_100, 1_025_500, 1_026_000, 1_026_663]
    return {
        "available": True,
        "bot_guid": 7,
        "active_receipt_id": 599,
        "requested_receipt_id": receipt_id,
        "ordering": "active_then_newest",
        "receipts": [
            {
                "available": True,
                "receipt_id": 599,
                "bot_guid": 7,
                "map": 669,
                "instance": 42,
                "scope": {
                    "attempt_id": 1,
                    "wipe_generation": 2,
                    "route_generation": 4,
                },
                "selected_endpoint": {"x": 6.0, "y": 6.0, "z": 211.0},
                "actor_at_launch": {"x": 2.0, "y": 3.0, "z": 211.0},
                "launched_spline": {
                    "initialized": True,
                    "id": 78,
                    "final_destination": {"x": 6.0, "y": 6.0, "z": 211.0},
                },
                "armed_at_ms": 1_028_700,
                "last_observed_at_ms": 0,
                "last_sample_at_ms": 0,
                "terminal_at_ms": 0,
                "terminal": False,
                "terminal_outcome": "pending",
                "superseded_by_receipt_id": 0,
                "samples": [],
                "sample_capacity": 16,
                "dropped_sample_count": 0,
            },
            {
                "available": True,
                "receipt_id": receipt_id,
                "bot_guid": 7,
                "map": 669,
                "instance": 42,
                "scope": {
                    "attempt_id": 1,
                    "wipe_generation": 2,
                    "route_generation": 4,
                },
                "selected_endpoint": {"x": 5.0, "y": 6.0, "z": 211.0},
                "actor_at_launch": {"x": 1.0, "y": 2.0, "z": 211.0},
                "launched_spline": {
                    "initialized": True,
                    "id": 77,
                    "final_destination": {"x": 5.0, "y": 6.0, "z": 211.0},
                },
                "armed_at_ms": 1_025_000,
                "last_observed_at_ms": sample_times[-1],
                "last_sample_at_ms": sample_times[-1],
                "terminal_at_ms": 1_028_700,
                "terminal": True,
                "terminal_outcome": "superseded_by_native_launch",
                "superseded_by_receipt_id": 599,
                "samples": [
                    {
                        "receipt_id": receipt_id,
                        "observed_at_ms": timestamp_ms,
                        "actor": {
                            "available": True,
                            "in_world": True,
                            "alive": True,
                            "map": 669,
                            "instance": 42,
                            "x": 2.0,
                            "y": 3.0,
                            "z": 211.0,
                        },
                        "floor": {
                            "sampled": True,
                            "valid": True,
                            "z": 211.0,
                            "selected_platform_compatible": True,
                        },
                        "native_motion": {
                            "moving": True,
                            "spline_id": 77,
                            "matches_launched_spline": True,
                        },
                        "outcome": "native_motion_in_progress",
                        "terminal": False,
                    }
                    for timestamp_ms in sample_times
                ],
                "sample_capacity": 16,
                "dropped_sample_count": 0,
            }
        ],
        "retained_receipt_count": 2,
        "published_receipt_count": 2,
        "receipt_capacity": 4,
        "omitted_receipt_count": 0,
        "receipts_truncated": False,
        "published_sample_count": 4,
        "sample_capacity_per_receipt": 16,
        "max_published_sample_count": 64,
        "dropped_sample_count": 0,
        "payload_complete": True,
    }


def test_recovers_displaced_receipt_progress_history(tmp_path: Path) -> None:
    submitted = {
        "timestamp_ms": 1_025_000,
        "bot_guid": 7,
        "bot_name": "Mage",
        "sequence": 10,
        "action": "ranged_formation_restore",
        "result": "ok",
        "movement_planner": _movement(598, 1_025_000, 211.0, submitted=True),
    }
    trace = _bound(
        "trace",
        "botauto_trace",
        {"bots": [{"bot_guid": 7, "bot_name": "Mage", "entries": [submitted]}]},
    )
    diagnosis = _bound(
        "diagnosis",
        "botauto_diagnose",
        {
            "bots": [
                {
                    "identity": {"bot_guid": 7, "bot_name": "Mage"},
                    "snapshot": {
                        "combat_attempt": {"recorded_at_ms": 1_029_100},
                        "decision": {"action": "validation_route_recovery"},
                        "movement_planner": _movement(
                            599, 1_028_700, 211.0, submitted=True
                        ),
                        "movement_receipt_progress": _receipt_history(598),
                    },
                },
                {
                    "identity": {"bot_guid": 8, "bot_name": "OutsideWindow"},
                    "snapshot": {
                        "combat_attempt": {"recorded_at_ms": 900_000},
                        "decision": {"action": "wait"},
                    },
                },
            ]
        },
    )
    combat = _bound(
        "combat_log",
        "botauto_combatlog",
        {
            "action": "botauto_combatlog",
            "combat_log_schema_version": 2,
            "recent_events": [
                {
                    "timestamp_ms": 1_010_000,
                    "kind": "damage",
                    "actor_guid": 7,
                    "source_guid": 7,
                    "target_guid": 39,
                    "source_x": 1.0,
                    "source_y": 2.0,
                    "source_z": 211.0,
                    "amount": 1,
                },
                {
                    "timestamp_ms": 1_029_000,
                    "kind": "damage",
                    "actor_guid": 7,
                    "source_guid": 7,
                    "target_guid": 39,
                    "source_x": 3.0,
                    "source_y": 4.0,
                    "source_z": 202.0,
                    "amount": 1,
                },
            ],
        },
    )
    raw_path = tmp_path / "raw.jsonl"
    raw_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in [trace, diagnosis, combat]),
        encoding="utf-8",
    )
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "identity": {"head": "abc"},
                "terminal_failure": {
                    "failure_reason": "death_loop_watchdog",
                    "elapsed_seconds": 40,
                    "terminal_status": {"deaths": 3},
                    "raid_runtime": {
                        "admission_receipt": {"committed_at_ms": 1_000_000}
                    },
                },
                "watchdog": {"controller_terminal": {"death_loop_count": 4}},
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    first, first_summary = build_replay(raw_path, report_path)
    second, second_summary = build_replay(raw_path, report_path)

    assert first == second
    assert first_summary == second_summary
    assert first["window"]["anchor"] == "death_loop_watchdog"
    assert first_summary["controller_death_loop_count"] == 4
    assert first_summary["terminal_status_deaths"] == 3
    assert first_summary["observed_death_events"] == 0
    assert json.dumps(first, sort_keys=True, separators=(",", ":")) == json.dumps(
        second, sort_keys=True, separators=(",", ":")
    )
    assert json.dumps(
        first_summary, sort_keys=True, separators=(",", ":")
    ) == json.dumps(second_summary, sort_keys=True, separators=(",", ":"))
    receipt = next(row for row in first["movement_receipts"] if row["receipt_id"] == 598)
    assert [row["receipt_id"] for row in first["movement_receipts"]] == [598, 599]
    assert receipt["progress"]["sample_count"] == 4
    assert receipt["progress"]["last_sample_at_ms"] == 1_026_663
    assert receipt["progress"]["last_sample_timestamp_basis"] == "last_sample_at_ms"
    assert receipt["progress"]["terminal_at_ms"] == 1_028_700
    assert receipt["progress"]["superseded_by_receipt_id"] == 599
    assert receipt["progress"]["terminal_outcome"] == "superseded_by_native_launch"
    assert receipt["intent_fingerprint"] == "7a4fd042a9143195"
    assert receipt["retention_requested"] is True
    assert receipt["planner"]["complete"] is True
    assert receipt["admission"]["result"] == "accepted"
    assert receipt["executor"]["spline_launch_succeeded"] is True
    causal = first_summary["causal_assessment"]
    assert causal["suspected_upstream_receipt"]["receipt_id"] == 598
    assert causal["suspected_upstream_receipt"]["sampling_gap_to_infection_ms"] == 2_337
    expected_completeness = {
        "status": "complete",
        "complete": True,
        "bot_guid": 7,
        "receipt_id": 598,
        "completeness_scope": "bounded_receipt_publication_only",
        "continuous_actor_position": "unavailable",
        "causal_closure": False,
    }
    replay_completeness = first["completeness"]["movement_receipt_progress"]
    assert replay_completeness["missing_history_field"] is False
    assert replay_completeness["snapshots_examined"] == 1
    assert replay_completeness["snapshots_missing_history_field"] == 0
    assert replay_completeness["receipts_truncated"] is False
    assert replay_completeness["omitted_receipt_count"] == 0
    assert replay_completeness["dropped_sample_count"] == 0
    assert replay_completeness["causal_receipt_lifecycle"] == expected_completeness
    assert (
        first_summary["movement_receipt_progress_completeness"]
        == replay_completeness
    )

    partial_history = _receipt_history(598)
    for receipt_id in (597, 596):
        older = json.loads(json.dumps(partial_history["receipts"][0]))
        older["receipt_id"] = receipt_id
        older["armed_at_ms"] = 1_024_000 - (598 - receipt_id) * 100
        older["launched_spline"]["id"] = receipt_id
        older["terminal"] = True
        older["terminal_at_ms"] = (
            1_025_000 if receipt_id == 597 else older["armed_at_ms"] + 100
        )
        older["terminal_outcome"] = "superseded_by_native_launch"
        older["superseded_by_receipt_id"] = receipt_id + 1
        partial_history["receipts"].append(older)
    receipt_598 = next(
        row for row in partial_history["receipts"] if row["receipt_id"] == 598
    )
    receipt_598["dropped_sample_count"] = 2
    partial_history.update(
        {
            "retained_receipt_count": 5,
            "published_receipt_count": 4,
            "omitted_receipt_count": 1,
            "receipts_truncated": True,
            "dropped_sample_count": 2,
            "payload_complete": False,
        }
    )
    diagnosis["payload"]["bots"][0]["snapshot"][
        "movement_receipt_progress"
    ] = partial_history
    raw_path.write_text(
        "".join(
            json.dumps(row, sort_keys=True) + "\n"
            for row in [trace, diagnosis, combat]
        ),
        encoding="utf-8",
    )

    partial, partial_summary = build_replay(raw_path, report_path)

    partial_completeness = partial["completeness"]["movement_receipt_progress"]
    assert partial_completeness["status"] == "partial"
    assert partial_completeness["receipts_truncated"] is True
    assert partial_completeness["omitted_receipt_count"] == 1
    assert partial_completeness["dropped_sample_count"] == 2
    assert partial_completeness["causal_receipt_lifecycle"]["status"] == "partial"
    assert partial_completeness["causal_receipt_lifecycle"]["complete"] is False
    assert partial_completeness["causal_receipt_lifecycle"]["causal_closure"] is False
    assert (
        partial_summary["movement_receipt_progress_completeness"]
        == partial_completeness
    )


def test_builds_deterministic_bounded_causal_replay(tmp_path: Path) -> None:
    admitted_ms = 1_000_000
    terminal_ms = 1_040_000
    submitted = {
        "timestamp_ms": 1_025_000,
        "bot_guid": 7,
        "bot_name": "Mage",
        "sequence": 10,
        "action": "ranged_formation_restore",
        "result": "ok",
        "route_generation": 4,
        "movement_planner": _movement(98, 1_025_000, 211.0, submitted=True),
    }
    rejected = {
        "timestamp_ms": 1_029_100,
        "bot_guid": 7,
        "bot_name": "Mage",
        "sequence": 11,
        "action": "validation_route_recovery",
        "result": "route_destination_partial_path",
        "route_generation": 4,
        "movement_planner": _movement(99, 1_029_100, 202.0, submitted=False),
    }
    trace = _bound(
        "trace",
        "botauto_trace",
        {
            "action": "botauto_trace",
            "bots": [{"bot_guid": 7, "bot_name": "Mage", "entries": [submitted, rejected]}],
        },
    )
    combat = {
        "action": "botauto_combatlog",
        "combat_log_schema_version": 2,
        "recent_events_dropped": 2,
        "recent_events": [
            {
                "timestamp_ms": 1_010_000,
                "kind": "damage",
                "actor_guid": 7,
                "actor_name": "Mage",
                "actor_role": "dps",
                "source_guid": 7,
                "target_guid": 39,
                "target_entry": 41570,
                "target_name": "Magmaw",
                "spell_id": 1,
                "spell_name": "Bolt",
                "amount": 100,
                "originated_amount": 100,
                "source_x": 1.0,
                "source_y": 2.0,
                "source_z": 211.0,
            },
            {
                "timestamp_ms": 1_029_000,
                "kind": "damage",
                "actor_guid": 7,
                "actor_name": "Mage",
                "actor_role": "dps",
                "source_guid": 7,
                "target_guid": 39,
                "target_entry": 41570,
                "target_name": "Magmaw",
                "spell_id": 1,
                "spell_name": "Bolt",
                "amount": 210,
                "originated_amount": 210,
                "source_x": 3.0,
                "source_y": 4.0,
                "source_z": 202.0,
            },
            {
                "timestamp_ms": terminal_ms,
                "kind": "heal",
                "actor_guid": 8,
                "actor_name": "Healer",
                "actor_role": "healer",
                "source_guid": 8,
                "target_guid": 7,
                "target_name": "Mage",
                "spell_id": 2,
                "spell_name": "Heal",
                "amount": 155,
                "originated_amount": 155,
                "source_x": 0.0,
                "source_y": 0.0,
                "source_z": 211.0,
            },
        ],
    }
    encoded = json.dumps(combat, separators=(",", ":")).encode()
    combat_rows = [
        _bound(
            "combat_log",
            "botauto_combatlog_chunk",
            {
                "action": "botauto_combatlog_chunk",
                "cohort_id": "default",
                "combat_log_chunk_schema_version": 1,
                "encoding": "base64",
                "sequence": 0,
                "chunk_count": 1,
                "data": base64.b64encode(encoded).decode(),
            },
        ),
        _bound(
            "combat_log",
            "botauto_combatlog_complete",
            {
                "action": "botauto_combatlog_complete",
                "cohort_id": "default",
                "combat_log_chunk_schema_version": 1,
                "chunk_count": 1,
                "total_bytes": len(encoded),
            },
        ),
    ]
    raw_path = tmp_path / "raw.jsonl"
    raw_path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in [trace, *combat_rows]),
        encoding="utf-8",
    )
    report_path = tmp_path / "report.json"
    report_path.write_text(
        json.dumps(
            {
                "identity": {"head": "abc"},
                "evidence_demux": {
                    "canonical_identity_sha256": "identity",
                    "canonical_roster_sha256": "roster",
                },
                "combat_log_transport": {"complete_marker": True, "reassembled": True},
                "terminal_failure": {
                    "elapsed_seconds": 40,
                    "raid_runtime": {
                        "admission_receipt": {"committed_at_ms": admitted_ms}
                    },
                },
            },
            sort_keys=True,
        ),
        encoding="utf-8",
    )

    first, first_summary = build_replay(raw_path, report_path)
    second, second_summary = build_replay(raw_path, report_path)

    assert first == second
    assert first_summary == second_summary
    assert first["window"]["terminal_at_ms"] == terminal_ms
    assert first_summary["party_dps"] == 10.0
    assert first_summary["party_hps"] == 5.0
    assert first_summary["vertical_discontinuities"] == 1
    causal = first_summary["causal_assessment"]
    assert causal["status"] == "localized_not_causally_closed"
    assert causal["suspected_upstream_receipt"]["receipt_id"] == 98
    assert "continuous_receipt_tagged" in causal["exact_missing_field"]
    old_receipt = next(
        row for row in first["movement_receipts"] if row["receipt_id"] == 98
    )
    assert (
        old_receipt["progress"]["last_sample_timestamp_basis"]
        == "legacy_last_observed_at_ms"
    )
    assert first["derived"]["target_correctness"]["status"] == "unavailable"
    assert first["derived"]["hazard_reaction"]["status"] == "unavailable"
    assert first["derived"]["cast_downtime"]["status"] == "unavailable"
    receipt_completeness = first["completeness"]["movement_receipt_progress"]
    assert receipt_completeness["status"] == "unavailable"
    assert receipt_completeness["missing_history_field"] is True
    assert receipt_completeness["receipts_truncated"] is None
    assert receipt_completeness["omitted_receipt_count"] is None
    assert receipt_completeness["dropped_sample_count"] is None
    assert receipt_completeness["causal_receipt_lifecycle"]["status"] == "unavailable"
    assert first_summary["causal_assessment"]["status"] == "localized_not_causally_closed"
    assert (
        first_summary["movement_receipt_progress_completeness"]
        == receipt_completeness
    )


def test_rejects_evidence_without_reconstructible_terminal(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw.jsonl"
    raw_path.write_text("", encoding="utf-8")
    report_path = tmp_path / "report.json"
    report_path.write_text("{}", encoding="utf-8")

    try:
        build_replay(raw_path, report_path)
    except ValueError as error:
        assert str(error) == "terminal timestamp cannot be reconstructed"
    else:
        raise AssertionError("missing terminal identity must fail closed")
