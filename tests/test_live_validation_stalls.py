"""World-thread stalls are recorded and gate DPS measurement validity."""
from __future__ import annotations

import json

from tools.bot_ml import live_validation_stalls as stalls
from tools.bot_ml.analyze_combat_log import analyze_combat_log
from tools.bot_ml.run_live_bot_validation import attach_measurement_validity, parse_json_objects

BOSS = "bwd.magmaw.encounter"
MANIFEST = {"routes": [
    {"route_node_id": "bwd.magmaw.drudges", "route_generation": 3, "kind": "trash"},
    {"route_node_id": BOSS, "route_generation": 4, "kind": "boss"},
]}
T0 = 1_790_000_000_000


def event(ms: int, *, kind: str = "damage", amount: int = 1000, node: str = BOSS, generation: int = 4, sequence: int = 0) -> dict:
    return {
        "timestamp_ms": T0 + ms,
        "event_sequence": sequence or ms,
        "kind": kind,
        "amount": amount,
        "originated_amount": amount,
        "route_node_id": node,
        "route_generation": generation,
        "actor_guid": 30001,
        "source_guid": 30001,
        "target_guid": 39,
        "target_entry": 41570,
    }


def burst(ms: int, count: int, **kwargs) -> list[dict]:
    return [event(ms, sequence=ms * 1000 + index, **kwargs) for index in range(count)]


def combat_log(rows: list[dict]) -> dict:
    return {"recent_events": rows, "recent_events_dropped": 0}


def steady(start_ms: int, end_ms: int, step: int = 200, **kwargs) -> list[dict]:
    return [event(ms, **kwargs) for ms in range(start_ms, end_ms, step)]


def windows() -> list[dict]:
    return [{"route_node_id": BOSS, "route_generation": 4, "first_at_ms": T0, "last_at_ms": T0 + 60_000}]


def test_heartbeat_freeze_in_boss_window_invalidates_dps():
    rows = steady(0, 20_000) + burst(25_000, 150) + steady(25_200, 60_001)
    timings = [{
        "phase": "heartbeat", "heartbeat_index": 3, "command": ".botauto trace all 128 delta",
        "mode": "full", "sent_at_ms": T0 + 19_900, "completed_at_ms": T0 + 24_990,
        "duration_ms": 4890, "response_bytes": 12_650_574,
    }]
    found, validity = stalls.world_stall_report(
        combat_log(rows), {"encounters": windows()},
        validation_route_manifest=MANIFEST, command_timings=timings,
    )
    assert len(found) == 1
    stall = found[0]
    assert stall["duration_sec"] == 5.2
    assert stall["route_node_id"] == BOSS
    assert stall["attribution"] == "console_command"
    assert stall["heartbeat_index"] == 3
    assert stall["overlapping_commands"][0]["command"] == ".botauto trace all 128 delta"
    assert validity["valid_for_dps"] is False
    assert validity["reasons"] == ["world_stall_overlaps_boss_window"]
    assert validity["boss_window_stalled_sec"] == 5.2
    assert validity["max_boss_window_stall_sec"] == 5.2
    assert validity["boss_windows"][0]["unstalled_duration_sec"] == 54.8


def test_short_unattributed_hitch_and_ordinary_lull_do_not_invalidate():
    rows = (
        steady(0, 10_000)
        + burst(10_650, 20)  # 0.85 s world hitch, not near any console command
        + steady(10_800, 30_000)
        + [event(32_000), event(32_001)]  # 2 s lull ending in ordinary combat
        + steady(32_200, 60_001)
    )
    found, validity = stalls.world_stall_report(
        combat_log(rows), {"encounters": windows()}, validation_route_manifest=MANIFEST,
        command_timings=[{"phase": "heartbeat", "heartbeat_index": 1, "command": ".botauto status", "sent_at_ms": T0 + 40_000, "completed_at_ms": T0 + 40_010}],
    )
    assert found == []
    assert validity["valid_for_dps"] is True
    assert validity["hitch_count"] == 1
    assert validity["max_hitch_sec"] == 0.85


def test_command_sent_into_a_running_hitch_is_not_blamed():
    rows = steady(0, 30_000) + burst(30_600, 25) + steady(30_800, 60_001)
    timings = [{"phase": "heartbeat", "heartbeat_index": 4, "command": ".botauto status",
                "sent_at_ms": T0 + 30_300, "completed_at_ms": T0 + 30_610}]
    found, validity = stalls.world_stall_report(
        combat_log(rows), {"encounters": windows()}, validation_route_manifest=MANIFEST,
        command_timings=timings,
    )
    assert found == []
    assert validity["valid_for_dps"] is True
    hitch = validity["hitches"][0]
    assert hitch["attribution"] == "unattributed"
    assert hitch["overlapping_commands"][0]["freeze_started_after_send"] is False


def test_long_unattributed_catchup_gap_is_a_stall_but_zero_heal_bursts_are_not():
    rows = steady(0, 5_000) + burst(7_000, 12) + steady(7_200, 60_001)
    rows += burst(61_000, 11, kind="heal", amount=0, node="bwd.magmaw.drudges", generation=3)
    found, validity = stalls.world_stall_report(combat_log(rows), {"encounters": windows()}, validation_route_manifest=MANIFEST)
    assert [row["attribution"] for row in found] == ["unattributed"]
    assert found[0]["duration_sec"] == 2.2
    assert validity["valid_for_dps"] is False


def test_legacy_runs_attribute_by_heartbeat_report_second():
    rows = steady(0, 20_000) + burst(26_000, 100) + steady(26_200, 60_001)
    heartbeat_events = [{"heartbeat_index": 7, "generated_at_unix": (T0 + 26_000) // 1000}]
    found, validity = stalls.world_stall_report(
        combat_log(rows), {"encounters": windows()}, validation_route_manifest=MANIFEST,
        heartbeat_events=heartbeat_events,
    )
    assert found[0]["attribution"] == "heartbeat_report_time"
    assert found[0]["heartbeat_index"] == 7
    assert validity["boss_window_stalled_sec"] == 6.2


def test_missing_combat_log_or_boss_window_is_never_valid():
    _, validity = stalls.world_stall_report(None, None, validation_route_manifest=MANIFEST)
    assert validity["valid_for_dps"] is False
    assert validity["reasons"] == ["combat_log_unavailable", "no_boss_window"]
    rows = steady(0, 60_001, node="bwd.magmaw.drudges", generation=3)
    _, trash_only = stalls.world_stall_report(combat_log(rows), {"encounters": []}, validation_route_manifest=MANIFEST)
    assert trash_only["reasons"] == ["no_boss_window"]


def test_final_report_exposes_stall_validity_and_cleanup_fields(tmp_path):
    rows = steady(0, 20_000) + burst(25_000, 150) + steady(25_200, 60_001)
    for row in rows:
        row["landed_damage_observation"] = {"target_health_before_damage": 10**9, "target_max_health": 10**9}
    (tmp_path / "heartbeat_command_timings.jsonl").write_text(json.dumps({
        "phase": "heartbeat", "heartbeat_index": 2, "command": ".botauto trace all 128 delta",
        "sent_at_ms": T0 + 20_050, "completed_at_ms": T0 + 25_000,
    }) + "\n", encoding="utf-8")
    log = {
        "abilities": [{
            "route_generation": 4, "route_node_id": BOSS, "perspective": "damage_done",
            "actor_guid": 30001, "amount": 1, "originated_amount": 1,
            "first_at_ms": T0, "last_at_ms": T0 + 60_000, "event_count": 1,
        }],
        "recent_events": rows,
    }
    report = {"combat_log": log, "combat_analysis": analyze_combat_log(log)}
    receipt = '{"action":"harness_cleanup_step","command":".botauto combatlog","returncode":0,"timed_out":false,"completed":true}'
    attach_measurement_validity(report, tmp_path, parse_json_objects(receipt), validation_route_manifest=MANIFEST)
    assert report["measurement_validity"]["valid_for_dps"] is False
    assert report["measurement_validity"]["boss_window_stalled_sec"] == 5.2
    assert report["world_stalls"][0]["heartbeat_index"] == 2
    assert report["heartbeat_command_timings"][0]["command"] == ".botauto trace all 128 delta"
    assert report["harness_cleanup_steps"][0]["command"] == ".botauto combatlog"
    assert "killed_hostile_damage_reconciliation" in report["combat_analysis"]
