from __future__ import annotations

import json

from tools.bot_ml.run_live_bot_validation import (
    advance_semantic_liveness,
    persist_rolling_heartbeat,
)


def _report(*, damage: int | None, alive: int = 10, recovery: str = "none") -> dict:
    live_damage = [] if damage is None else [{
        "route_node_id": "bwd.magmaw.encounter",
        "route_generation": 4,
        "attempt_epoch": 0,
        "party_damage": damage,
    }]
    return {
        "expected_cohort_id": "default",
        "status": {
            "cohort_id": "default",
            "server_epoch": 41,
            "attempt_id": 7,
            "profile_generation": 3,
            "profile_content_hash": "a" * 64,
            "validation_route": {
                "node_id": "bwd.magmaw.encounter",
                "generation": 4,
            },
            "raid_runtime": {
                "server_epoch": 41,
                "attempt_id": 7,
                "profile_generation": 3,
                "expected_size": 10,
                "alive_size": alive,
                "wipe_state": "wiped" if alive == 0 else "engaged",
                "wipe_generation": 2 if alive == 0 else 0,
                "recovery_state": recovery,
                "recovery_generation": 2 if recovery != "none" else 0,
                "recovery_attempts_remaining": 1 if recovery != "none" else 0,
            },
        },
        "watchdog_state": {
            "progress_total": 6,
            "live_combat_progress": {"health": [], "damage": live_damage},
        },
    }


def _initial_clock() -> dict:
    return {
        "last_progress_total": 6,
        "last_progress_monotonic": 10.0,
        "last_progress_unix": 1010,
        "last_progress_type": "route_party_damage",
        "last_progress_value": 100,
        "last_progress_route_node_id": "bwd.magmaw.encounter",
        "last_progress_route_generation": 4,
        "previous_live_combat_progress": _report(damage=100)["watchdog_state"]["live_combat_progress"],
        "previous_terminal_catchup_progress": {},
    }


def _advance(report: dict, clock: dict, *, now: float, emergency: bool = False) -> tuple[dict, dict]:
    advanced = advance_semantic_liveness(
        report,
        observed_monotonic=now,
        observed_unix=1000 + int(now),
        no_progress_window_sec=300,
        emergency_cap_reached=emergency,
        **clock,
    )
    receipt = advanced.pop("receipt")
    return advanced, receipt


def test_damage_progress_resets_identity_bound_semantic_clock() -> None:
    clock, receipt = _advance(_report(damage=250), _initial_clock(), now=25.0)

    assert clock["last_progress_monotonic"] == 25.0
    assert receipt["last_progress_type"] == "route_party_damage"
    assert receipt["last_progress_value"] == 250
    assert receipt["route_node_id"] == "bwd.magmaw.encounter"
    assert receipt["route_generation"] == 4
    assert receipt["attempt_id"] == 7
    assert receipt["elapsed_no_progress_sec"] == 0.0


def test_139_second_gap_does_not_expire_300_second_window() -> None:
    _clock, receipt = _advance(_report(damage=100), _initial_clock(), now=149.0)

    assert receipt["elapsed_no_progress_sec"] == 139.0
    assert receipt["remaining_no_progress_sec"] == 161.0
    assert receipt["semantic_progress_expired"] is False


def test_recovery_then_resumed_damage_records_new_progress() -> None:
    clock, recovery = _advance(
        _report(damage=None, alive=0, recovery="release_resurrection_pending"),
        _initial_clock(),
        now=149.0,
    )
    assert recovery["alive_count"] == 0
    assert recovery["recovery_generation"] == 2
    assert recovery["recovery_budget_remaining"] == 1

    clock, _first_resumed = _advance(_report(damage=250), clock, now=160.0)
    clock, resumed = _advance(_report(damage=300), clock, now=165.0)
    assert resumed["last_progress_at_unix"] == 1165
    assert resumed["last_progress_value"] == 300
    assert resumed["elapsed_no_progress_sec"] == 0.0


def test_semantic_expiry_and_emergency_cap_are_distinct() -> None:
    _clock, expired = _advance(_report(damage=100), _initial_clock(), now=310.0)
    assert expired["semantic_progress_expired"] is True
    assert expired["emergency_cap_reached"] is False
    assert expired["remaining_no_progress_sec"] == 0.0
    assert expired["emergency_cap_interrupted_recent_progress_or_recovery"] is False

    _clock, capped = _advance(
        _report(damage=100), _initial_clock(), now=149.0, emergency=True
    )
    assert capped["semantic_progress_expired"] is False
    assert capped["emergency_cap_reached"] is True
    assert capped["emergency_cap_interrupted_recent_progress_or_recovery"] is True


def test_compact_heartbeat_and_latest_retain_only_liveness_receipt(tmp_path) -> None:
    _clock, receipt = _advance(_report(damage=250), _initial_clock(), now=25.0)
    heartbeat = {
        "heartbeat_index": 3,
        "heartbeat_generated_at_unix": 1025,
        "semantic_liveness": receipt,
    }

    persist_rolling_heartbeat(tmp_path, heartbeat)

    stream_row = json.loads((tmp_path / "heartbeat_events.jsonl").read_text())
    latest = json.loads((tmp_path / "latest.json").read_text())
    report = json.loads((tmp_path / "report.json").read_text())
    assert stream_row["semantic_liveness"] == receipt
    assert latest["semantic_liveness"] == receipt
    assert report["semantic_liveness"] == receipt
    assert "status" not in stream_row
    assert "diagnosis" not in stream_row
    assert "trace" not in stream_row
