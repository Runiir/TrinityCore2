"""OBS-011: recorded native stats survive the actual timeline/HTML consumer."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from tools.raid_program.bot_timeline import _diagnosis_events, build_timeline_from_rows
from tools.raid_program.bot_timeline_html import render_timeline_html
from tests.test_bot_timeline import _bound, _embedded_model, _event, _full, _report, _trace

FIXTURE = Path(__file__).parent / "fixtures/magmaw_89cef_blood_stats_observations.json"


def recorded():
    return json.loads(FIXTURE.read_text())


def payload(observation=0):
    fixture = recorded()
    row = deepcopy(fixture["observations"][observation])
    at = row["snapshot"]["effective_stats"]["observed_at_ms"]
    # Deliberately stale policy and later export clocks are controlled test
    # context, not modifications to the recorded native stat observations.
    row["snapshot"]["runtime"] = {"last_decision_tick_ms": at - 50_000}
    row["snapshot"]["policy"] = {"valid_action_mask_json": {
        "evaluation": {"started_at_ms": at - 60_000}, "actions": []}}
    return {**fixture["identity"], "exported_at_ms": at + 20_000,
            "bots": [{"identity": {"bot_guid": row["actor_guid"]},
                      "snapshot": row["snapshot"]}]}


def report():
    value = _report()
    value["combat_log_event_stream"]["identity"].update(recorded()["identity"])
    value["accepted_raid_runtime"] = {"roster": [{"guid": 30002, "name": "Blood"}]}
    return value


def stats(events):
    return [event for event in events if event["kind"] == "diagnosis_stats_observation"]


def retime(value, at):
    value = deepcopy(value)
    effective = value["bots"][0]["snapshot"]["effective_stats"]
    old = effective["observed_at_ms"]

    def visit(node):
        if isinstance(node, dict):
            for key, item in node.items():
                if key == "observed_at_ms" and item == old:
                    node[key] = at
                else:
                    visit(item)
        elif isinstance(node, list):
            for item in node:
                visit(item)
    visit(effective)
    return value


def test_recorded_stats_use_native_clock_and_survive_full_html_pipeline():
    first, second = payload(), payload(1)
    original = deepcopy([first, second])
    model, _ = build_timeline_from_rows(
        [_bound("diagnosis", value) for value in (first, second)], report())
    events = stats(model["events"])
    assert len(events) == 2
    for event, observation in zip(events, recorded()["observations"]):
        snapshot = observation["snapshot"]
        assert event["at_ms"] == snapshot["effective_stats"]["observed_at_ms"]
        assert event["effective_stats"] == snapshot["effective_stats"]
        assert event["native_combat_stats"] == snapshot["native_combat_stats"]
        assert event["source_identity"] == recorded()["identity"]
        assert event["source_identity_verified"] is True
        assert event["native_combat_stats_clock"] == "shared_diagnosis_snapshot_no_independent_timestamp"
    assert events[0]["native_combat_stats"]["vengeance_76691_present"] is False
    assert events[1]["native_combat_stats"]["vengeance_76691_effect0_amount"] == 1204
    assert events[0]["effective_stats"]["persistent_pet"]["effective_stats"]["observed"] is False
    assert stats(_embedded_model(render_timeline_html(model))["events"]) == events
    assert [first, second] == original


def test_equal_states_keep_each_native_time_without_cached_export_inflation_or_policy_dependency():
    first = payload()
    at = first["bots"][0]["snapshot"]["effective_stats"]["observed_at_ms"]
    repeated = retime(first, at + 1000)
    # No last decision exists, yet this new stat observation must survive.
    repeated["bots"][0]["snapshot"]["runtime"]["last_decision_tick_ms"] = 0
    events = stats(_diagnosis_events([payload(1), repeated, first, first, repeated]))
    assert len(events) == 3
    assert [event["at_ms"] for event in events] == [at, at + 1000,
        recorded()["observations"][1]["snapshot"]["effective_stats"]["observed_at_ms"]]
    assert events[0]["effective_stats"]["owner"]["observed_at_ms"] == at
    assert events[1]["effective_stats"]["owner"]["observed_at_ms"] == at + 1000
    assert events[0]["effective_stats"]["owner"]["attack_power"] == events[1]["effective_stats"]["owner"]["attack_power"]



@pytest.mark.parametrize("timestamp", [None, 0, -1, True, 1.5, "12345"])
def test_missing_or_invalid_stat_time_never_borrows_export_or_policy_clock(timestamp):
    value = payload()
    effective = value["bots"][0]["snapshot"]["effective_stats"]
    if timestamp is None:
        del effective["observed_at_ms"]
    else:
        effective["observed_at_ms"] = timestamp
    events = _diagnosis_events([value])
    assert not stats(events)
    assert any(event["kind"] == "diagnosis_decision_context" for event in events)


def test_stale_nested_clocks_and_unknown_observations_remain_distinct():
    first = payload()
    at = first["bots"][0]["snapshot"]["effective_stats"]["observed_at_ms"]
    stale = retime(first, at + 1000)
    stale["bots"][0]["snapshot"]["effective_stats"]["owner"]["observed_at_ms"] = at
    unknown = retime(first, at + 2000)
    owner = unknown["bots"][0]["snapshot"]["effective_stats"]["owner"]
    owner["observed"] = False
    owner["observed_at_ms"] = 0
    owner["attack_power"] = None
    del unknown["bots"][0]["snapshot"]["native_combat_stats"]
    null_native = retime(unknown, at + 3000)
    null_native["bots"][0]["snapshot"]["native_combat_stats"] = None
    events = stats(_diagnosis_events([first, stale, unknown, null_native]))
    assert len(events) == 4
    assert events[1]["effective_stats"]["owner"]["observed_at_ms"] == at
    assert events[2]["effective_stats"]["owner"]["observed"] is False
    assert events[2]["effective_stats"]["owner"]["attack_power"] is None
    assert "native_combat_stats" not in events[2]
    assert events[3]["native_combat_stats"] is None


def test_actor_attempt_epoch_boundaries_do_not_merge_and_foreign_attempt_is_rejected():
    first = payload()
    other_actor = deepcopy(first)
    other_actor["bots"][0]["identity"]["bot_guid"] = 30010
    other_attempt = deepcopy(first)
    other_attempt["attempt_id"] += 1
    other_epoch = deepcopy(first)
    other_epoch["server_epoch"] += 1
    events = stats(_diagnosis_events([first, other_actor, other_attempt, other_epoch]))
    assert len(events) == 4
    model, summary = build_timeline_from_rows(
        [_bound("diagnosis", value) for value in (first, other_attempt)], report())
    assert len(stats(model["events"])) == 1
    assert summary["completeness"]["identity_rejections"][0]["identity"]["attempt_id"] == other_attempt["attempt_id"]


def test_stats_leave_damage_healing_activity_and_window_accounting_unchanged():
    fixture = recorded()
    pull = fixture["pull_ms"]
    damage = [_event(1, pull, amount=123), _event(2, pull + 5000, effect=2, amount=45)]
    combat = {**_full(damage), **fixture["identity"]}
    trace = _trace([{"timestamp_ms": pull + 10_000, "sequence": 9,
                     "action": "boss_killed", "result": "confirmed_unit_death",
                     "target": {"entry": 41570}}], **fixture["identity"])
    rows = [_bound("combat_log", combat), _bound("trace", trace)]
    _, before = build_timeline_from_rows(rows, report())
    _, after = build_timeline_from_rows(
        [*rows, _bound("diagnosis", payload()), _bound("diagnosis", payload(1))], report())
    assert before["accounting"]["hostile_originated_damage"] == 168
    for field in ("accounting", "actors", "window", "incoming_damage", "melee_resolutions"):
        assert after[field] == before[field]


def test_identical_stats_remain_queryable_in_later_head_phase():
    first = payload()
    at = first["bots"][0]["snapshot"]["effective_stats"]["observed_at_ms"]
    head = retime(first, at + 1000)
    final = deepcopy(head)
    del final["bots"][0]["snapshot"]["effective_stats"]
    for value, phase, observed in ((first, "body", at - 100),
                                   (head, "head_attackable", at + 900),
                                   (final, "head_attackable", at + 2000)):
        value["bots"][0]["diagnosis"] = {"magmaw_target_return": {
            "evaluated": True, "observed_at_ms": observed, "current": True,
            "attempt_id": value["attempt_id"], "route_generation": 4,
            "route_node_id": "boss", "head_fact": phase}}
    model, _ = build_timeline_from_rows(
        [_bound("diagnosis", value) for value in (first, head, final)], report())
    events = stats(model["events"])
    assert [event["phase"] for event in events] == ["body", "head_attackable"]
    selected = [event for event in events if at + 900 <= event["at_ms"] <= at + 2000]
    assert len(selected) == 1 and selected[0]["at_ms"] == at + 1000
