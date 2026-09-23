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


def windows(last_ms: int = 60_000) -> list[dict]:
    return [{"route_node_id": BOSS, "route_generation": 4, "first_at_ms": T0, "last_at_ms": T0 + last_ms}]


TRASH = {"node": "bwd.magmaw.drudges", "generation": 3}


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
    assert stall["detection"] == "catchup_burst"
    assert stall["attribution"] == "console_command"
    assert stall["heartbeat_index"] == 3
    assert stall["overlapping_commands"][0]["command"] == ".botauto trace all 128 delta"
    assert validity["valid_for_dps"] is False
    assert validity["reasons"] == ["boss_window_stall_fraction_exceeded", "boss_window_stall_too_long"]
    assert validity["stall_fraction"] == 0.086667
    assert validity["boss_window_stalled_sec"] == 5.2
    assert validity["max_boss_window_stall_sec"] == 5.2
    assert validity["boss_windows"][0]["unstalled_duration_sec"] == 54.8
    assert validity["thresholds"]["max_boss_window_stall_fraction"] == 0.02
    assert validity["thresholds"]["max_single_boss_window_stall_sec"] == 2.0


def test_boss_window_flags_every_half_second_gap_whatever_its_burst():
    rows = (
        steady(0, 10_000)
        + burst(10_650, 20)  # 0.85 s catch-up hitch, no console command
        + steady(10_800, 30_000)
        + [event(30_400), event(30_401)]  # 0.6 s gap ending in ordinary combat
        + steady(30_600, 60_001)
    )
    found, validity = stalls.world_stall_report(
        combat_log(rows), {"encounters": windows()}, validation_route_manifest=MANIFEST,
    )
    assert [(row["duration_sec"], row["detection"]) for row in found] == [
        (0.85, "catchup_burst"),
        (0.6, "boss_window_event_gap"),
    ]
    assert validity["boss_windows"][0]["catchup_burst_stall_count"] == 1
    assert validity["boss_windows"][0]["event_gap_stall_count"] == 1
    # 1.45 s of 60 s is above the 2% tolerance; no single stall reaches 2 s.
    assert validity["stall_fraction"] == 0.024167
    assert validity["reasons"] == ["boss_window_stall_fraction_exceeded"]


def test_small_boss_window_stalls_stay_valid_on_a_shared_host():
    """Smoke-kill shape: 1.202 s of stall in a 112.1 s kill is 1.07%."""
    rows = (
        steady(0, 50_000)
        + burst(50_412, 3)  # 0.612 s after the 49.8 s event
        + steady(50_600, 80_000)
        + burst(80_390, 12)  # 0.59 s
        + steady(80_600, 112_101)
    )
    found, validity = stalls.world_stall_report(
        combat_log(rows), {"encounters": windows(112_100)}, validation_route_manifest=MANIFEST,
    )
    assert [row["duration_sec"] for row in found] == [0.612, 0.59]
    assert validity["valid_for_dps"] is True
    assert validity["reasons"] == []
    assert validity["stall_fraction"] == 0.010723
    assert validity["max_boss_window_stall_sec"] == 0.612


def test_one_two_second_boss_window_stall_is_too_long_even_below_the_fraction():
    rows = steady(0, 50_000) + burst(51_800, 3) + steady(52_000, 112_101)
    _, validity = stalls.world_stall_report(
        combat_log(rows), {"encounters": windows(112_100)}, validation_route_manifest=MANIFEST,
    )
    assert validity["stall_fraction"] <= 0.02
    assert validity["max_boss_window_stall_sec"] == 2.0
    assert validity["reasons"] == ["boss_window_stall_too_long"]


def test_outside_boss_windows_short_hitches_and_lulls_do_not_invalidate():
    rows = (
        steady(-60_000, -40_000, **TRASH)
        + burst(-39_350, 20, **TRASH)  # 0.85 s unattributed catch-up hitch
        + steady(-39_000, -30_000, **TRASH)
        + [event(-27_000, **TRASH)]  # 3.2 s lull with nothing due
        + steady(0, 60_001)
    )
    found, validity = stalls.world_stall_report(
        combat_log(rows), {"encounters": windows()}, validation_route_manifest=MANIFEST,
    )
    assert found == []
    assert validity["valid_for_dps"] is True
    assert validity["hitch_count"] == 1
    assert validity["max_hitch_sec"] == 0.85


def test_command_sent_into_a_running_hitch_is_not_blamed():
    rows = steady(-60_000, -30_000, **TRASH) + burst(-29_400, 25, **TRASH) + steady(-29_200, -10_000, **TRASH) + steady(0, 60_001)
    timings = [{"phase": "heartbeat", "heartbeat_index": 4, "command": ".botauto status",
                "sent_at_ms": T0 - 29_700, "completed_at_ms": T0 - 29_390}]
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
    receipts = "\n".join([
        '{"action":"harness_console_pipe","requested_bytes":1048576,"achieved_bytes":1048576,"set_errno":null}',
        '{"action":"harness_cleanup_step","command":".botauto combatlog","returncode":0,"timed_out":false,"completed":true}',
        '{"action":"harness_cleanup_summary","complete":true,"cleanup_overrun_sec":1.5,"shutdown_killed":false}',
    ])
    attach_measurement_validity(report, tmp_path, parse_json_objects(receipts), validation_route_manifest=MANIFEST)
    assert report["console_pipe_buffer"] == {"requested_bytes": 1048576, "achieved_bytes": 1048576, "set_errno": None}
    assert report["harness_cleanup"]["complete"] is True
    assert report["cleanup_overrun_sec"] == 1.5
    assert report["measurement_validity"]["valid_for_dps"] is False
    assert report["measurement_validity"]["boss_window_stalled_sec"] == 5.2
    assert report["world_stalls"][0]["heartbeat_index"] == 2
    assert report["heartbeat_command_timings"][0]["command"] == ".botauto trace all 128 delta"
    assert report["harness_cleanup_steps"][0]["command"] == ".botauto combatlog"
    assert "killed_hostile_damage_reconciliation" in report["combat_analysis"]
