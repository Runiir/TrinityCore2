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
    assert first["derived"]["target_correctness"]["status"] == "unavailable"
    assert first["derived"]["hazard_reaction"]["status"] == "unavailable"
    assert first["derived"]["cast_downtime"]["status"] == "unavailable"


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
