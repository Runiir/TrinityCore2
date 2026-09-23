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


def test_boss_window_lulls_are_reported_but_never_gate():
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
    assert [(row["duration_sec"], row["detection"]) for row in found] == [(0.85, "catchup_burst")]
    assert [(row["duration_sec"], row["detection"]) for row in validity["lulls"]] == [(0.6, "combat_lull")]
    assert validity["lull_count"] == 1 and validity["boss_window_lull_sec"] == 0.6
    assert validity["boss_windows"][0]["catchup_burst_stall_count"] == 1
    assert validity["boss_windows"][0]["event_gap_stall_count"] == 0
    assert validity["stall_fraction"] == 0.014167
    assert validity["stall_basis"] == "combat_log_inference"
    assert validity["valid_for_dps"] is True


def test_base_0891a99_kill_shapes_keep_lulls_out_of_the_gate():
    """Kill 1: three short lulls.  Kill 3: two lulls and one real stall."""
    kill_one = (
        steady(0, 20_000) + burst(20_528, 6)  # 0.728 s / 6 events
        + steady(20_600, 50_000) + burst(50_377, 3)  # 0.577 s / 3
        + steady(50_400, 80_000) + burst(80_301, 3)  # 0.501 s / 3
        + steady(80_400, 112_101)
    )
    _, first = stalls.world_stall_report(
        combat_log(kill_one), {"encounters": windows(112_100)}, validation_route_manifest=MANIFEST,
    )
    assert first["boss_window_stall_count"] == 0
    assert [row["duration_sec"] for row in first["lulls"]] == [0.728, 0.577, 0.501]
    assert first["valid_for_dps"] is True
    kill_three = (
        steady(0, 20_000) + burst(20_723, 2)  # 0.923 s / 2
        + steady(20_800, 50_000) + burst(50_348, 1)  # 0.548 s / 1
        + steady(50_400, 80_000) + burst(80_746, 54)  # 0.946 s / 54: frozen
        + steady(80_800, 113_491)
    )
    found, third = stalls.world_stall_report(
        combat_log(kill_three), {"encounters": windows(113_490)}, validation_route_manifest=MANIFEST,
    )
    assert [(row["duration_sec"], row["catchup_events"]) for row in found] == [(0.946, 54)]
    assert [row["duration_sec"] for row in third["lulls"]] == [0.923, 0.548]
    assert third["stall_fraction"] == 0.008336
    assert third["valid_for_dps"] is True


def test_boss_window_gap_caused_by_a_console_command_is_a_stall():
    rows = steady(0, 30_000) + [event(30_600), event(30_601)] + steady(30_800, 60_001)
    timings = [{"phase": "heartbeat", "heartbeat_index": 5, "command": ".botauto trace all 128 delta",
                "sent_at_ms": T0 + 29_850, "completed_at_ms": T0 + 30_590}]
    found, validity = stalls.world_stall_report(
        combat_log(rows), {"encounters": windows()}, validation_route_manifest=MANIFEST,
        command_timings=timings,
    )
    assert [(row["duration_sec"], row["attribution"], row["heartbeat_index"]) for row in found] == [
        (0.8, "console_command", 5)
    ]
    assert validity["lulls"] == []


def test_small_boss_window_stalls_stay_valid_on_a_shared_host():
    """Smoke-kill shape: a 0.59 s catch-up stall in a 112.1 s kill."""
    rows = (
        steady(0, 50_000)
        + burst(50_412, 3)  # 0.612 s gap with 3 events: a lull
        + steady(50_600, 80_000)
        + burst(80_390, 12)  # 0.59 s catch-up burst: a stall
        + steady(80_600, 112_101)
    )
    found, validity = stalls.world_stall_report(
        combat_log(rows), {"encounters": windows(112_100)}, validation_route_manifest=MANIFEST,
    )
    assert [row["duration_sec"] for row in found] == [0.59]
    assert [row["duration_sec"] for row in validity["lulls"]] == [0.612]
    assert validity["valid_for_dps"] is True
    assert validity["reasons"] == []
    assert validity["stall_fraction"] == 0.005263
    assert validity["max_boss_window_stall_sec"] == 0.59


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


def ledger(*rows, now_ms=70_000, first_update_ms=-600_000, missing=(), stall_count=None):
    stalls_rows = [
        {"sequence": index + 1, "at_ms": T0 + at_ms, "diff_ms": diff_ms}
        for index, (at_ms, diff_ms) in enumerate(rows)
    ]
    stalls_rows = [row for row in stalls_rows if row["sequence"] not in set(missing)]
    return {
        "reads": 4,
        "now_ms": T0 + now_ms,
        "threshold_ms": 500,
        "update_count": 12_000,
        "first_update_at_ms": T0 + first_update_ms,
        "max_diff_ms": max((diff for _, diff in rows), default=0),
        "stall_count": len(rows) if stall_count is None else stall_count,
        "dropped_count": len(missing),
        "missing_sequences": list(missing),
        "stalls": stalls_rows,
    }


def test_native_world_ticks_override_combat_log_inference():
    # The combat log shows a 0.946 s catch-up stall; the native recorder saw
    # a 520 ms tick there and a 610 ms tick during a lull-looking gap.
    rows = (
        steady(0, 20_000) + burst(20_723, 2)
        + steady(20_800, 50_000) + burst(50_746, 54)
        + steady(50_800, 60_001)
    )
    ticks = ledger((-90_000, 2_500), (20_723, 610), (50_746, 520))
    timings = [{"phase": "heartbeat", "heartbeat_index": 3, "command": ".botauto status",
                "sent_at_ms": T0 + 50_200, "completed_at_ms": T0 + 50_760}]
    found, validity = stalls.world_stall_report(
        combat_log(rows), {"encounters": windows()}, validation_route_manifest=MANIFEST,
        command_timings=timings, world_ticks=ticks,
    )
    assert validity["stall_basis"] == "native_world_tick"
    assert [(row["detection"], row["duration_sec"], row["boss_window_overlap_sec"]) for row in found] == [
        ("native_world_tick", 2.5, 0.0),
        ("native_world_tick", 0.61, 0.61),
        ("native_world_tick", 0.52, 0.52),
    ]
    assert found[2]["attribution"] == "console_command"
    assert found[2]["heartbeat_index"] == 3
    assert found[2]["catchup_events"] == 54
    assert validity["boss_window_stalled_sec"] == 1.13
    assert validity["boss_windows"][0]["native_world_tick_stall_count"] == 2
    assert validity["valid_for_dps"] is True
    assert validity["thresholds"]["native_world_tick_min_diff_ms"] == 500
    assert validity["combat_log_inference"]["boss_window_stall_count"] == 1
    assert validity["native_world_tick"]["complete_for_boss_windows"] is True
    assert [row["sequence"] for row in validity["native_world_tick"]["stalls"]] == [1, 2, 3]
    # Lulls are still reported from the combat log for comparison.
    assert [row["duration_sec"] for row in validity["lulls"]] == [0.923]


def test_native_world_ticks_gate_like_any_stall():
    rows = steady(0, 60_001)
    found, validity = stalls.world_stall_report(
        combat_log(rows), {"encounters": windows()}, validation_route_manifest=MANIFEST,
        world_ticks=ledger((30_000, 2_100)),
    )
    assert validity["stall_basis"] == "native_world_tick"
    assert validity["reasons"] == ["boss_window_stall_fraction_exceeded", "boss_window_stall_too_long"]
    assert found[0]["duration_sec"] == 2.1


def test_incomplete_native_coverage_falls_back_to_the_combat_log():
    rows = steady(0, 20_000) + burst(20_800, 30) + steady(21_000, 60_001)
    cases = {
        "no_world_update_read_after_boss_window": ledger((20_800, 900), now_ms=40_000),
        "world_update_recorder_started_after_boss_window": ledger((20_800, 900), first_update_ms=5_000),
        "world_update_rows_lost_near_boss_window": ledger(
            (-5_000, 700), (20_800, 900), (65_000, 600), missing=(1, 2),
        ),
    }
    for reason, ticks in cases.items():
        found, validity = stalls.world_stall_report(
            combat_log(rows), {"encounters": windows()}, validation_route_manifest=MANIFEST,
            world_ticks=ticks,
        )
        assert validity["stall_basis"] == "combat_log_inference", reason
        assert validity["native_world_tick"]["reason"] == reason
        assert [row["detection"] for row in found] == ["catchup_burst"]
    # A lost row is harmless when a retained row older than the window follows it.
    _, validity = stalls.world_stall_report(
        combat_log(rows), {"encounters": windows()}, validation_route_manifest=MANIFEST,
        world_ticks=ledger((-9_000, 700), (-5_000, 800), (20_800, 900), missing=(1,)),
    )
    assert validity["stall_basis"] == "native_world_tick"
    _, validity = stalls.world_stall_report(
        combat_log(rows), {"encounters": windows()}, validation_route_manifest=MANIFEST,
    )
    assert validity["native_world_tick"] == {
        "available": False, "complete_for_boss_windows": False, "reason": "no_world_update_reads", "stalls": [],
    }


def test_final_report_reads_the_native_ledger_file(tmp_path):
    rows = steady(0, 60_001)
    for row in rows:
        row["landed_damage_observation"] = {"target_health_before_damage": 10**9, "target_max_health": 10**9}
    log = {
        "abilities": [{
            "route_generation": 4, "route_node_id": BOSS, "perspective": "damage_done",
            "actor_guid": 30001, "amount": 1, "originated_amount": 1,
            "first_at_ms": T0, "last_at_ms": T0 + 60_000, "event_count": 1,
        }],
        "recent_events": rows,
    }
    (tmp_path / "world_update_ticks.json").write_text(json.dumps(ledger((30_000, 700))), encoding="utf-8")
    report = {"combat_log": log, "combat_analysis": analyze_combat_log(log)}
    attach_measurement_validity(report, tmp_path, [], validation_route_manifest=MANIFEST)
    assert report["measurement_validity"]["stall_basis"] == "native_world_tick"
    assert report["world_stalls"][0]["detection"] == "native_world_tick"
    assert report["measurement_validity"]["valid_for_dps"] is True
    # Without the ledger file the final status snapshot is the fallback.
    (tmp_path / "world_update_ticks.json").unlink()
    status_ticks = {
        "schema": "bot_world_update_ticks_v1", "now_ms": T0 + 70_000, "threshold_ms": 500,
        "update_count": 9, "first_update_at_ms": T0 - 60_000, "max_diff_ms": 700,
        "stall_count": 1, "dropped_count": 0,
        "stalls": [{"sequence": 1, "at_ms": T0 + 30_000, "diff_ms": 700}],
    }
    report = {"combat_log": log, "combat_analysis": analyze_combat_log(log), "status": {"world_update": status_ticks}}
    attach_measurement_validity(report, tmp_path, [], validation_route_manifest=MANIFEST)
    assert report["measurement_validity"]["stall_basis"] == "native_world_tick"
    assert report["measurement_validity"]["native_world_tick"]["reads"] == 1
