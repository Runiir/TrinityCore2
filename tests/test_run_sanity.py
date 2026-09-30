"""Hand-off hardening (2026-09-29): run-sanity findings over stored scoreboard records.

tools/raid_program/run_sanity.py flags results a coordinator used to reject by eye (the BWD 10N
round-1/2 Nefarian kills: 18-25 minute windows past Berserk, bots revived in place, stranded DPS),
and tools/raid_program/run_sanity_inputs.py records what older records lacked. Nothing here may
change evaluate_target output (Magmaw b5-d1898555 stays byte-identical)."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from tools.bot_ml.live_validation_heartbeat import TRACE_HISTORY_FILE
from tools.bot_ml.live_validation_terminal_signals import TERMINAL_TRACE_DRAIN_FILE
from tools.raid_program import run_sanity
from tools.raid_program.run_sanity import NOT_EVALUABLE, sanity_findings
from tools.raid_program.run_sanity_inputs import enrage_rows, sanity_input_fields, sanity_inputs
from tools.raid_program.scoreboard_core import KILL_SCHEMA, SCOREBOARD_DIR
from tools.raid_program.scoreboard_verdict import evaluate_target

ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "blackwing_descent_10n_nefarian"
LABEL = "l1"
NODE = "bwd.nefarian.encounter"
R01 = "blackwing_descent_10n-r01-553da85c98"
R02 = "blackwing_descent_10n-r02-a82a035b81"
ROSTER = {"1": {"name": "Tank", "spec": "blood_death_knight", "role": "tank"},
          "2": {"name": "Bear", "spec": "feral_druid_tank", "role": "tank"},
          "3": {"name": "Mage", "spec": "fire_mage", "role": "dps"},
          "4": {"name": "Heal", "spec": "holy_paladin", "role": "healer"}}
REGISTRY = {"schema": "creature_damage_calibration_v1", "creatures": {
    "41376": {"name": "Nefarian", "raid": "blackwing_descent", "boss": "nefarian", "mode": "10N",
              "status": "calibrated", "damage_modifier": 12.75, "enrage_after_ms": 630000,
              "enrage_anchor_entries": [41270, 41376]},
    "41270": {"name": "Onyxia", "raid": "blackwing_descent", "boss": "nefarian", "mode": "10N",
              "status": "calibrated", "damage_modifier": 10.34}}}


def make_root(tmp_path: Path, durations=(300.0, 250.0), scenario: str = SCENARIO) -> Path:
    root = tmp_path / "root"
    refs = [{"id": f"r{index}", "duration_sec": duration, "raid_dps": 100000.0,
             "actor_dps": {"blood_death_knight": 12000.0, "fire_mage": 30000.0}}
            for index, duration in enumerate(durations)]
    files = {
        "experiments/configs/wcl.json": {"schema": "test", "references": refs},
        f"experiments/configs/raid_targets/{scenario}.json": {
            "schema": "raid_target_v1", "scenario": scenario, "encounter_route_node_id": NODE,
            "wcl_reference_manifest": "experiments/configs/wcl.json", "matched_reference_ids": [ref["id"] for ref in refs],
            "kills_per_measurement": 1, "actor_dps_ratio": 0.95, "max_boss_window_deaths": 0,
            "roles_without_dps_target": ["healer"], "dps_gate_exempt_specs": ["feral_druid_tank"], "roster": ROSTER},
        run_sanity.REGISTRY_PATH: REGISTRY,
    }
    for relative, document in files.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(json.dumps(document))
    return root


def actors(**changes) -> list[dict]:
    rows = [{"actor_id": "1", "spec": "blood_death_knight", "role": "tank", "encounter_window_dps": 12000.0,
             "damage_uptime": 0.8},
            {"actor_id": "2", "spec": "feral_druid_tank", "role": "tank", "encounter_window_dps": 10.0,
             "damage_uptime": 0.05},
            {"actor_id": "3", "spec": "fire_mage", "role": "dps", "encounter_window_dps": 30000.0, "damage_uptime": 0.9},
            {"actor_id": "4", "spec": "holy_paladin", "role": "healer", "encounter_window_dps": 0.0, "damage_uptime": 0.0}]
    for row in rows:
        row.update(changes.get(row["actor_id"], {}))
    return rows


def inputs(**changes) -> dict:
    document = {
        "schema": "raid_run_sanity_inputs_v1",
        "combat_log": {"available": True, "retained_events": 10, "recent_events_dropped": 0,
                       "boss_window_retained": True, "capture_truncated": False},
        "deaths": {"basis": "combat_log_lethal_damage_encounter_reconciled", "lethal_events": 0,
                   "lethal_events_in_boss_window": 0, "lethal_events_in_boss_window_by_actor": {},
                   "native_death_signal": {"basis": "native_life_edges", "members": 4, "deaths": 0, "resurrections": 0},
                   "death_signal_conflict": False},
        "enrage_pulls": {"41376": {"name": "Nefarian", "enrage_after_ms": 630000, "anchor_entries": [41270, 41376],
                                   "pulls": 1, "engaged_sec": [200.0], "longest_engaged_sec": 200.0,
                                   "post_enrage_anchor_events": 0}},
        "health_half": {"hits": 139, "at_half": 0, "fraction": 0.0, "tolerance_hp": 1, "by_actor": {}},
        # Chimaeron r02: one death, battle-resurrected 16.6 s later
        "revives": {"native": [{"actor_id": "1", "deaths": 1, "resurrections": 1, "last_death_ms": 1_000,
                                "last_resurrection_ms": 17_629, "gap_ms": 16_629, "measured": True,
                                "in_boss_window": True}], "native_available": True,
                    "combat_log": {"pairs": 0, "min_gap_ms_by_actor": {}}},
        # a complete decision trace of the boss window with none of the round 3 observations
        "nefarian_observations": {"bone_warrior_active_over_45s": 0, "bone_warrior_on_pillar": 0, "move_refused": {}},
        "decision_trace": {"available": True, "files": {"trace_history.jsonl.gz": 40}, "window_rows": 40, "actors": 4,
                           "sequence_gaps": 0, "unsequenced_rows": 0, "actors_without_rows": [], "unreadable": [],
                           "complete": True, "incomplete_reason": None},
    }
    for key, value in changes.items():
        document[key] = value if value is None else {**document[key], **value}
    return document


def kill(kill_id: str, *, duration: float | None = 200.0, **fields) -> dict:
    record = {"schema": KILL_SCHEMA, "kill_id": kill_id, "scenario": SCENARIO, "label": LABEL, "native_clear": True,
              "outcome": "clear", "evidence_dvc_pointer": f"{kill_id}.dvc",
              "measurement_validity": {"valid_for_dps": True, "reasons": []},
              "encounter": {"duration_sec": duration, "encounter_window_party_dps": 1.0} if duration else None,
              "actors": actors(), "route_deaths": 0, "boss_window_deaths": 0, "death_basis": "no_route_deaths",
              "deaths": [], "worldserver_sha256": "a", "source_commit": "b"}
    record.update(fields)
    return record


def write_scoreboard(root: Path, records: list[dict], scenario: str = SCENARIO) -> None:
    path = root / SCOREBOARD_DIR / f"{scenario}.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(record, sort_keys=True) + "\n" for record in records))


def by_check(findings: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for row in findings:
        grouped.setdefault(row["check"], []).append(row)
    return grouped


def lethal_list(counts: dict[str, int]) -> list[dict]:
    return [{"actor_id": actor, "in_boss_window": True, "timestamp_ms": index}
            for actor, count in counts.items() for index in range(count)]


# --- synthetic records ------------------------------------------------------------------------------

def test_a_clean_new_record_has_no_findings(tmp_path):
    root = make_root(tmp_path)
    write_scoreboard(root, [kill("k1", sanity_inputs=inputs())])
    assert sanity_findings(root, SCENARIO, LABEL) == []
    assert sanity_findings(root, SCENARIO, "other") == []


def test_a_nefarian_like_kill_is_blocked_on_every_count(tmp_path):
    root = make_root(tmp_path)
    scan = {"lethal_events": 1196, "lethal_events_in_boss_window": 1196,
            "lethal_events_in_boss_window_by_actor": {"1": 341, "3": 229, "4": 2},
            "native_death_signal": {"basis": "native_life_edges", "members": 4, "deaths": 1196, "resurrections": 1196}}
    pulls = {"41376": {**inputs()["enrage_pulls"]["41376"], "engaged_sec": [1415.0], "longest_engaged_sec": 1415.0,
                       "post_enrage_anchor_events": 6114}}
    pinned = {"hits": 2873, "at_half": 2728, "by_actor": {"1": {"hits": 900, "at_half": 880},
                                                          "3": {"hits": 500, "at_half": 470}}}
    measured = {"measured": True, "in_boss_window": True}
    revive = {"native": [{"actor_id": "1", "deaths": 341, "gap_ms": 6, **measured},
                         {"actor_id": "3", "deaths": 229, "gap_ms": 4, **measured}],
              "combat_log": {"pairs": 1187, "min_gap_ms_by_actor": {"1": 10, "3": 3239}}}
    record = kill("k1", duration=1415.0, actors=actors(**{"3": {"encounter_window_dps": 2000.0, "damage_uptime": 0.4}}),
                  sanity_inputs={**inputs(deaths=scan), "enrage_pulls": pulls, "health_half": pinned,
                                 "revives": revive})
    write_scoreboard(root, [record])
    findings = by_check(sanity_findings(root, SCENARIO, LABEL))
    blocking = {check for check, rows in findings.items() if any(row["severity"] == "blocking" for row in rows)}
    assert blocking == {"duration_outlier", "enrage_reached", "death_signal_conflict", "repeated_deaths",
                        "health_pinned_half", "instant_revive", "idle_actor"}
    assert findings["health_pinned_half"][0]["evidence"]["fraction"] == 0.9495
    assert [(row["id"], row.get("native_gap_ms"), row.get("combat_log_gap_ms"))
            for row in findings["instant_revive"][0]["evidence"]["actors"]] == [("3", 4, None), ("1", 6, 10)]
    assert "recorded as 0 from route_deaths 0, but 1196 lethal" in findings["death_signal_conflict"][0]["detail"]
    assert [row["id"] for row in findings["repeated_deaths"][0]["evidence"]["actors"]] == ["1", "3"]
    assert findings["idle_actor"][0]["evidence"]["actors"][0]["why"] == "dps"
    assert findings["duration_outlier"][0]["evidence"]["limit_ratio"] == 2.0
    assert all(row["kill_id"] == "k1" for rows in findings.values() for row in rows)


def test_death_signal_conflict_flag_and_silent_native_signal(tmp_path):
    root = make_root(tmp_path)
    flagged = kill("k1", death_basis="combat_log_lethal_damage_unreconciled", route_deaths=1,
                   deaths=lethal_list({"3": 1}), death_signal_conflict=True)
    silent = kill("k2", sanity_inputs=inputs(deaths={"lethal_events": 3, "lethal_events_in_boss_window": 0}))
    reconciled = kill("k3", death_basis="combat_log_lethal_damage", route_deaths=1, deaths=lethal_list({"3": 1}),
                      boss_window_deaths=1)
    write_scoreboard(root, [flagged, silent, reconciled])
    rows = by_check(sanity_findings(root, SCENARIO, LABEL))["death_signal_conflict"]
    assert [(row["kill_id"], row["severity"]) for row in rows] == [("k1", "blocking"), ("k2", "blocking")]


def test_old_records_are_not_evaluable_once_per_check_and_only_for_counted_kills(tmp_path):
    root = make_root(tmp_path, durations=(400.0,))
    stalled = {"valid_for_dps": False, "reasons": ["boss_window_stall_fraction_exceeded"], "stalled_sec": 3.0,
               "max_stall_sec": 1.0}
    write_scoreboard(root, [kill("k1", duration=700.0), kill("k2", duration=650.0),
                            kill("k3", duration=700.0, measurement_validity=stalled)])
    findings = sanity_findings(root, SCENARIO, LABEL)
    # the round 3 acceptance observation has no not_evaluable escape: unavailable evidence blocks (counted kills only)
    assert [(row["check"], row["kill_id"]) for row in findings if row["severity"] == "blocking"] == [
        ("acceptance_observation", "k1"), ("acceptance_observation", "k2")]
    unevaluable = {row["check"]: row for row in findings if row["evidence"].get("status") == NOT_EVALUABLE}
    assert set(unevaluable) == {"enrage_reached", "death_signal_conflict", "repeated_deaths", "health_pinned_half",
                                "instant_revive"}
    for row in unevaluable.values():
        assert row["kill_id"] is None and row["severity"] == "warn"
        assert row["evidence"]["kill_ids"] == ["k1", "k2"]  # the stalled k3 never reaches a verdict
    assert "predates per-pull timing" in unevaluable["enrage_reached"]["detail"]


def test_a_window_shorter_than_the_enrage_passes_without_pull_timing(tmp_path):
    root = make_root(tmp_path)
    write_scoreboard(root, [kill("k1", duration=500.0, death_basis="combat_log_lethal_damage", route_deaths=1,
                                 deaths=lethal_list({"3": 1}), boss_window_deaths=1)])
    findings = sanity_findings(root, SCENARIO, LABEL)
    assert "enrage_reached" not in by_check(findings)
    assert not [row for row in findings if row["severity"] == "blocking" and row["check"] != "acceptance_observation"]


@pytest.mark.parametrize("hits, at_half, blocked", [
    (2873, 2728, True),   # round 2 Nefarian: 95% of hits at exactly half health
    (20, 5, True),        # 25%
    (20, 4, False),       # exactly 20% is not more than 20%
    (19, 19, False),      # too few hits to judge
    (64, 0, False),       # round 2 Atramedes (negative control)
])
def test_health_pinned_half(tmp_path, hits, at_half, blocked):
    root = make_root(tmp_path)
    half = {"hits": hits, "at_half": at_half, "tolerance_hp": 1, "by_actor": {"3": {"hits": hits, "at_half": at_half}}}
    write_scoreboard(root, [kill("k1", sanity_inputs=inputs(health_half=half))])
    rows = by_check(sanity_findings(root, SCENARIO, LABEL)).get("health_pinned_half") or []
    assert [(row["severity"], row["kill_id"]) for row in rows] == ([("blocking", "k1")] if blocked else [])


@pytest.mark.parametrize("native_gap, log_gap, blocked", [
    (5, None, True),          # round 2 Nefarian: native life edges 2-11 ms apart
    (250, None, True),
    (None, 10, True),         # a lethal hit, then a hit finding the bot alive 10 ms later
    (251, 3239, False),
    (16_629, None, False),    # round 2 Chimaeron battle resurrection (negative control)
    (96_736, 143_431, False),  # round 2 Magmaw release and run back (negative control)
])
def test_instant_revive(tmp_path, native_gap, log_gap, blocked):
    root = make_root(tmp_path)
    revive = {"native": [] if native_gap is None else [{"actor_id": "3", "deaths": 1, "gap_ms": native_gap,
                                                        "measured": True, "in_boss_window": True}],
              "combat_log": {"pairs": 1, "min_gap_ms_by_actor": {} if log_gap is None else {"3": log_gap}}}
    write_scoreboard(root, [kill("k1", sanity_inputs=inputs(revives=revive))])
    rows = by_check(sanity_findings(root, SCENARIO, LABEL)).get("instant_revive") or []
    assert [(row["severity"], row["evidence"]["actors"][0]["id"]) for row in rows] == ([("blocking", "3")] if blocked else [])


def test_an_uncounted_kill_downgrades_blocking_checks_to_warn(tmp_path):
    root = make_root(tmp_path)
    stalled = {"valid_for_dps": False, "reasons": ["boss_window_stall_too_long"], "stalled_sec": 4.0,
               "max_stall_sec": 4.0, "stall_fraction": 0.004, "thresholds": {"max_boss_window_stall_fraction": 0.02}}
    write_scoreboard(root, [kill("k1", duration=2000.0, measurement_validity=stalled, sanity_inputs=inputs())])
    findings = by_check(sanity_findings(root, SCENARIO, LABEL))
    outlier = findings["duration_outlier"][0]
    assert outlier["severity"] == "warn" and outlier["evidence"]["counted"] is False
    assert outlier["evidence"]["exclusion_reason"] == "stalled_boss_window" and "kill not counted" in outlier["detail"]
    excluded = findings["excluded_kills"][0]
    assert excluded["evidence"]["max_stall_fraction"] == 0.02 and "suspect" not in excluded["detail"]


def test_a_stall_label_without_stall_time_is_called_suspect(tmp_path):
    root = make_root(tmp_path)
    validity = {"valid_for_dps": False, "reasons": ["world_stall_overlaps_boss_window"], "stalled_sec": 0,
                "max_stall_sec": 0.0}
    write_scoreboard(root, [kill("k1", measurement_validity=validity)])
    row = by_check(sanity_findings(root, SCENARIO, LABEL))["excluded_kills"][0]
    assert row["severity"] == "warn" and "stall label is suspect" in row["detail"]


def test_unmeasured_and_truncated_kills_warn(tmp_path):
    root = make_root(tmp_path)
    unmeasured = kill("k1", duration=None, measurement_validity={
        "valid_for_dps": False, "reasons": ["combat_log_unavailable", "no_boss_window"]})
    truncated = kill("k2", sanity_inputs=inputs(combat_log={"capture_truncated": True}))
    ring = kill("k3", encounter_reconciliation={"window_retained": False}, sanity_inputs=inputs())
    voided = kill("k4", voided={"reason": "wrong binary"})
    write_scoreboard(root, [unmeasured, truncated, ring, voided])
    findings = by_check(sanity_findings(root, SCENARIO, LABEL))
    rows = {row["kill_id"]: row for row in findings["unmeasured_kills"]}
    assert set(rows) == {"k1", "k2", "k3"} and all(row["severity"] == "warn" for row in rows.values())
    assert rows["k1"]["evidence"]["exclusion_reason"] == "unmeasured_boss_window"
    assert "truncated the worldserver capture" in rows["k2"]["detail"]
    assert "ring dropped events" in rows["k3"]["detail"]
    assert [row["kill_id"] for row in findings["excluded_kills"]] == ["k4"]
    assert "wrong binary" in findings["excluded_kills"][0]["detail"]


def test_boss_melee_fidelity_needs_a_calibrated_creature_and_enough_swings(tmp_path):
    root = make_root(tmp_path)

    def fidelity(ratio, swings, entry="41376", blizzlike=True, reasons=()):
        return {"blizzlike": blizzlike, "reasons": list(reasons), "bosses": {
            entry: {"name": "Boss", "mean_ratio": ratio, "swings": swings, "after_attacker_mean": 1, "wcl_mean": 1}}}

    write_scoreboard(root, [kill("k1", sanity_inputs=inputs(), encounter_fidelity=fidelity(1.2, 30)),
                            kill("k2", sanity_inputs=inputs(), encounter_fidelity=fidelity(1.5, 5)),
                            kill("k3", sanity_inputs=inputs(), encounter_fidelity=fidelity(1.5, 50, entry="99999")),
                            kill("k4", sanity_inputs=inputs(), encounter_fidelity=fidelity(1.05, 50)),
                            kill("k5", sanity_inputs=inputs(), encounter_fidelity=fidelity(
                                1.0, 50, blizzlike=False, reasons=["boss 1: runtime DamageModifier 1 != registry 12.75"]))])
    rows = {row["kill_id"]: row for row in by_check(sanity_findings(root, SCENARIO, LABEL))["boss_melee_fidelity"]}
    assert set(rows) == {"k1", "k5"} and {row["severity"] for row in rows.values()} == {"warn"}
    assert rows["k1"]["evidence"]["creatures"][0]["mean_ratio"] == 1.2
    assert "not Blizzlike" in rows["k5"]["detail"]


@pytest.mark.parametrize("change, idle", [
    ({"3": {"encounter_window_dps": 7100.0}}, "dps"),        # 0.237 of the 30,000 reference
    ({"3": {"damage_uptime": 0.19}}, "uptime"),
    ({"1": {"encounter_window_dps": 2000.0, "damage_uptime": 0.1}}, "dps+uptime"),  # the Blood DK tank is gated
    ({"3": {"encounter_window_dps": 7800.0, "damage_uptime": 0.25}}, None),
    ({"2": {"encounter_window_dps": 0.0, "damage_uptime": 0.0}}, None),  # the Feral tank is exempt
    ({"4": {"encounter_window_dps": 0.0, "damage_uptime": 0.0}}, None),  # healers are never judged
])
def test_idle_actor_thresholds(tmp_path, change, idle):
    root = make_root(tmp_path)
    write_scoreboard(root, [kill("k1", actors=actors(**change), sanity_inputs=inputs())])
    rows = by_check(sanity_findings(root, SCENARIO, LABEL)).get("idle_actor") or []
    assert [row["evidence"]["actors"][0]["why"] for row in rows] == ([idle] if idle else [])


# --- acceptance_observation (BWD 10N round 3: the Nefarian decision-trace observations) ---------------

ACTIVE, PILLAR = "bone_warrior_active_over_45s", "bone_warrior_on_pillar"
LEDGE = "pillar_descent_step_off:native_ledge_drop_landing_height_mismatch"


def observation_findings(tmp_path, *, observations=None, trace=None, scenario=SCENARIO, actor_changes=None, **fields):
    """acceptance_observation findings of one kill whose sanity inputs carry the given observation fields."""
    root = make_root(tmp_path, scenario=scenario)
    document = inputs()
    if observations is not None:
        document["nefarian_observations"] = {**document["nefarian_observations"], **observations}
    if trace is not None:
        document["decision_trace"] = {**document["decision_trace"], **trace}
    record = kill("k1", scenario=scenario, actors=actors(**(actor_changes or {})), sanity_inputs=document, **fields)
    write_scoreboard(root, [record], scenario)
    return by_check(sanity_findings(root, scenario, LABEL)).get("acceptance_observation") or []


@pytest.mark.parametrize("observations", [{ACTIVE: 1}, {PILLAR: 1}, {ACTIVE: 1, PILLAR: 1}, {ACTIVE: 3, PILLAR: 2}])
def test_a_bone_warrior_observation_is_one_blocking_finding(tmp_path, observations):
    rows = observation_findings(tmp_path, observations=observations)
    assert [(row["severity"], row["kill_id"]) for row in rows] == [("blocking", "k1")]
    assert {key: rows[0]["evidence"][key] for key in (ACTIVE, PILLAR)} == {ACTIVE: observations.get(ACTIVE, 0),
                                                                          PILLAR: observations.get(PILLAR, 0)}
    assert "acceptance observation allows none" in rows[0]["detail"]


def test_no_bone_warrior_observation_is_no_finding(tmp_path):
    """Negative control of the one-entry case: the same record with a complete trace and zero entries."""
    assert observation_findings(tmp_path, observations={ACTIVE: 0, PILLAR: 0}) == []
    # Refusals alone are not an acceptance failure: with no idle actor they are not even a finding.
    assert observation_findings(tmp_path, observations={"move_refused": {"3": {LEDGE: 812}}}) == []


def test_an_uncounted_kill_downgrades_the_observation_to_warn(tmp_path):
    stalled = {"valid_for_dps": False, "reasons": ["boss_window_stall_too_long"], "stalled_sec": 4.0,
               "max_stall_sec": 4.0, "stall_fraction": 0.004, "thresholds": {"max_boss_window_stall_fraction": 0.02}}
    rows = observation_findings(tmp_path, observations={ACTIVE: 1}, measurement_validity=stalled)
    assert [row["severity"] for row in rows] == ["warn"] and rows[0]["evidence"]["counted"] is False
    assert "kill not counted" in rows[0]["detail"]


@pytest.mark.parametrize("case", ["field absent", "no trace file", "sequence gaps", "silent actors", "unreadable",
                                  "partial counts", "malformed counts"])
def test_a_missing_or_partial_trace_is_unproven_and_blocks(tmp_path, case):
    document = inputs()
    trace = {"available": False, "complete": False, "incomplete_reason": "no_trace_file"}
    if case == "field absent":  # a record from before sanity_inputs.nefarian_observations
        del document["nefarian_observations"], document["decision_trace"]
    elif case == "no trace file":
        document["nefarian_observations"], document["decision_trace"] = None, {**document["decision_trace"], **trace}
    elif case == "partial counts":
        document["nefarian_observations"] = {ACTIVE: 0}
    elif case == "malformed counts":
        document["nefarian_observations"] = {ACTIVE: "0", PILLAR: None, "move_refused": {}}
    else:  # zeros the retained trace cannot vouch for
        reason = {"sequence gaps": "sequence_gaps", "silent actors": "actors_without_rows", "unreadable": "unreadable"}[case]
        document["decision_trace"] = {**document["decision_trace"], "complete": False, "incomplete_reason": reason}
    root = make_root(tmp_path)
    write_scoreboard(root, [kill("k1", sanity_inputs=document)])
    rows = by_check(sanity_findings(root, SCENARIO, LABEL))["acceptance_observation"]
    assert [(row["severity"], row["kill_id"], row["evidence"]["status"]) for row in rows] == [
        ("blocking", "k1", "unproven")]
    counts_gone = "records before sanity_inputs.nefarian_observations"
    fragment = {"field absent": counts_gone, "partial counts": counts_gone, "malformed counts": counts_gone,
                "no trace file": "holds no retained decision trace", "sequence gaps": "lost rows",
                "silent actors": "no rows of some actors", "unreadable": "unreadable or has malformed rows"}[case]
    assert "acceptance observation is unproven" in rows[0]["detail"] and fragment in rows[0]["detail"]


def test_an_observation_is_blocking_even_when_the_trace_is_partial(tmp_path):
    """A count above zero is evidence whatever the coverage; only a zero needs a complete trace."""
    rows = observation_findings(tmp_path, observations={PILLAR: 1},
                                trace={"complete": False, "incomplete_reason": "sequence_gaps"})
    assert [row["severity"] for row in rows] == ["blocking"]
    assert rows[0]["evidence"]["trace_complete"] is False
    assert rows[0]["evidence"]["trace_incomplete_reason"] == "sequence_gaps"


def test_a_record_without_a_coverage_claim_proves_no_zero(tmp_path):
    """A synthetic record holding only the counts: one entry is a blocking finding, and so is a zero with no claim."""
    root = make_root(tmp_path)
    counts = {ACTIVE: 1, PILLAR: 0, "move_refused": {}}
    document = {key: value for key, value in inputs().items() if key != "decision_trace"}
    write_scoreboard(root, [kill("one", sanity_inputs={**document, "nefarian_observations": counts}),
                            kill("zero", sanity_inputs={**document, "nefarian_observations": {**counts, ACTIVE: 0}})])
    rows = by_check(sanity_findings(root, SCENARIO, LABEL))["acceptance_observation"]
    assert [(row["kill_id"], row["severity"]) for row in rows] == [("one", "blocking"), ("zero", "blocking")]
    assert "allows none" in rows[0]["detail"] and rows[1]["evidence"]["status"] == "unproven"


def test_the_top_move_refused_reasons_are_listed_for_an_idle_actor(tmp_path):
    refused = {"3": {LEDGE: 812, "hop:native_no_path": 40, "pillar_descent_step_off:blocked": 40, "hop:stunned": 2},
               "1": {"tank_step:leg_in_flight": 9}}  # the Blood DK is not idle
    idle_mage = {"3": {"encounter_window_dps": 7100.0, "damage_uptime": 0.9}}
    rows = observation_findings(tmp_path, observations={"move_refused": refused}, actor_changes=idle_mage)
    assert [row["severity"] for row in rows] == ["warn"]
    (listed,) = rows[0]["evidence"]["actors"]
    assert (listed["id"], listed["name"], listed["spec"], listed["why"]) == ("3", "Mage", "fire_mage", "dps")
    assert listed["move_refused"] == [{"reason": LEDGE, "count": 812}, {"reason": "hop:native_no_path", "count": 40},
                                      {"reason": "pillar_descent_step_off:blocked", "count": 40}]  # top 3, ties by name
    assert "fire_mage (id 3)" in rows[0]["detail"] and f"{LEDGE} x812" in rows[0]["detail"]
    assert "tank_step" not in rows[0]["detail"]


def test_move_refused_reasons_need_an_idle_actor_with_refusals(tmp_path):
    refused = {"3": {LEDGE: 812}}
    assert observation_findings(tmp_path / "busy", observations={"move_refused": refused}) == []  # nobody idle
    idle_without = {"1": {"encounter_window_dps": 2000.0, "damage_uptime": 0.1}}  # idle, but never refused a step
    assert observation_findings(tmp_path / "quiet", observations={"move_refused": refused},
                                actor_changes=idle_without) == []
    both = observation_findings(tmp_path / "both", observations={ACTIVE: 1, "move_refused": refused},
                                actor_changes={"3": {"encounter_window_dps": 7100.0}})
    assert [row["severity"] for row in both] == ["blocking", "warn"]  # the warn never replaces the blocking finding


@pytest.mark.parametrize("scenario", ["blackwing_descent_10n_magmaw", "blackwing_descent_25n_nefarian"])
def test_a_non_nefarian_scenario_is_not_affected(tmp_path, scenario):
    """Even a record that carries a bone warrior observation, or none of the fields, gets no finding there."""
    assert observation_findings(tmp_path / "counts", scenario=scenario, observations={ACTIVE: 4, PILLAR: 2}) == []
    root = make_root(tmp_path / "old", scenario=scenario)
    write_scoreboard(root, [kill("k1", scenario=scenario, sanity_inputs={
        key: value for key, value in inputs().items() if key not in ("nefarian_observations", "decision_trace")})],
        scenario)
    assert "acceptance_observation" not in by_check(sanity_findings(root, scenario, LABEL))


def test_evidence_fits_the_assess_budget(tmp_path):
    root = make_root(tmp_path, durations=(100.0,))
    long_id = "x" * 150
    records = [kill(f"{long_id}-{index}", duration=150.0) for index in range(40)]
    records.append(kill("k-idle", actors=[{"actor_id": f"9{index:02d}", "spec": "fire_mage", "role": "dps",
                                           "encounter_window_dps": 1.0, "damage_uptime": 0.01} for index in range(60)]))
    write_scoreboard(root, records)
    findings = sanity_findings(root, SCENARIO, LABEL)
    assert findings and all(len(json.dumps(row["evidence"], sort_keys=True)) <= 2000 for row in findings)
    idle = by_check(findings)["idle_actor"][0]["evidence"]
    assert idle["actors_omitted"] + len(idle["actors"]) == 60


def test_play_mode_kills_are_never_checked(tmp_path):
    root = make_root(tmp_path)
    write_scoreboard(root, [kill("k1", duration=5000.0, shard_identity={"cohort_purpose": "play"})])
    assert sanity_findings(root, SCENARIO, LABEL) == []


def test_the_verdict_ignores_sanity_inputs(tmp_path):
    root = make_root(tmp_path)
    plain = [kill("k1", sanity_inputs=None), kill("k2", duration=900.0)]
    write_scoreboard(root, [{key: value for key, value in record.items() if value is not None} for record in plain])
    before = evaluate_target(root, SCENARIO, LABEL)
    noisy = inputs(deaths={"lethal_events": 99, "lethal_events_in_boss_window": 99,
                           "lethal_events_in_boss_window_by_actor": {"1": 99}})
    write_scoreboard(root, [{**record, "sanity_inputs": noisy} for record in
                            [{key: value for key, value in record.items() if value is not None} for record in plain]])
    assert evaluate_target(root, SCENARIO, LABEL) == before


# --- record-time inputs -------------------------------------------------------------------------------

def _anchor(at, guid, entry=41376, node=NODE):
    return {"kind": "damage", "timestamp_ms": at, "route_node_id": node, "target_guid": guid, "target_entry": entry,
            "source_guid": 1, "source_entry": 0, "actor_guid": 1, "amount": 10,
            "landed_damage_observation": {"target_health_before_damage": 1_000_000, "target_max_health": 1_000_000}}


def _lethal(at, target, node=NODE):
    return {"kind": "damage", "timestamp_ms": at, "route_node_id": node, "target_guid": target, "actor_guid": 0,
            "source_entry": 41376, "source_guid": 900, "amount": 500,
            "landed_damage_observation": {"target_health_before_damage": 400}}


WINDOW_START, WINDOW_END = 10_000, 800_000  # write_run's analysed boss window (ms)
# The identity of write_run's combat-log capture (the native event-stream identity of the full export): the
# judged capture the status counters must belong to (run_sanity_inputs.capture_identity).
CAPTURE = {"cohort_id": "shard-nefarian", "server_epoch": 5_000_000_001, "attempt_id": 7, "combat_log_epoch": 3}


def write_run(path: Path, events, *, report=None, dropped=0, capture=CAPTURE) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    analysis = {"encounters": [{"route_node_id": NODE, "first_at_ms": WINDOW_START, "last_at_ms": WINDOW_END,
                                "actors": [{"actor_guid": guid} for guid in (1, 2, 3, 4)]}],
                "killed_hostile_damage_reconciliation": {"mismatch_count": 0, "mismatches": [],
                                                         "hostiles": [{"route_node_id": NODE, "target_entry": 41376}]}}
    (path / "combat_analysis.json").write_text(json.dumps(analysis))
    (path / "combat_log.json").write_text(json.dumps({"recent_events": events, "recent_events_dropped": dropped,
                                                      **(capture or {})}))
    if report is not None:
        (path / "report.json").write_text(json.dumps(report))
    return path


def test_sanity_inputs_scan_lethal_hits_whatever_the_route_count_and_time_each_pull(tmp_path):
    first_pull = [_anchor(at, 900) for at in range(10_000, 700_001, 10_000)]    # engaged 690 s, past 630 s
    second_pull = [_anchor(at, 901) for at in range(750_000, 800_001, 10_000)]  # a respawned Nefarian after 50 s
    lethal = [_lethal(20_000 + index * 1000, 3) for index in range(5)] + [_lethal(30_000, 2)]
    members = [{"guid": guid, "death_sequence": 0, "native_death_count": 5 * (guid == 3) + (guid == 2),
                "native_resurrection_count": 5 * (guid == 3) + (guid == 2)} for guid in (1, 2, 3, 4)]
    report = {"status": {"raid_runtime": {"native_recovery": {"members": members}}},
              "failure_labels": ["worldserver_output_truncated"]}
    run = write_run(tmp_path / "run", [_anchor(5_000, 77, entry=1, node="bwd.trash"), *first_pull, *second_pull,
                                       *lethal], report=report)
    result = sanity_inputs(run, {"encounter_route_node_id": NODE, "scenario": SCENARIO}, ROOT)
    assert result["combat_log"] == {"available": True, "retained_events": 1 + 70 + 6 + 6, "recent_events_dropped": 0,
                                    "boss_window_retained": True, "capture_truncated": True}
    deaths = result["deaths"]
    assert deaths["lethal_events"] == 6 and deaths["lethal_events_in_boss_window"] == 6
    assert deaths["lethal_events_in_boss_window_by_actor"] == {"2": 1, "3": 5}
    assert deaths["native_death_signal"]["deaths"] == 6 and deaths["death_signal_conflict"] is False
    pulls = result["enrage_pulls"]["41376"]
    assert pulls["pulls"] == 2 and pulls["engaged_sec"] == [690.0, 50.0] and pulls["longest_engaged_sec"] == 690.0
    assert pulls["post_enrage_anchor_events"] == 7  # 640-700 s


def test_sanity_input_fields_never_raise_and_skip_scenarios_without_an_enrage(tmp_path):
    run = write_run(tmp_path / "run", [_lethal(20_000, 3)])
    assert "error" in sanity_input_fields(run, {"scenario": SCENARIO}, ROOT)["sanity_inputs"]  # no route node
    result = sanity_input_fields(run, {"encounter_route_node_id": NODE, "scenario": "x_10n_y"}, ROOT)["sanity_inputs"]
    assert result["enrage_pulls"] == {} and result["deaths"]["lethal_events"] == 1
    missing = sanity_inputs(tmp_path / "absent", {"encounter_route_node_id": NODE, "scenario": SCENARIO}, ROOT)
    assert missing["combat_log"]["available"] is False and missing["deaths"]["lethal_events"] is None


def _hit(at, target, before, maximum=10_000, amount=100):
    return {"kind": "damage", "timestamp_ms": at, "route_node_id": NODE, "target_guid": target, "actor_guid": 0,
            "source_entry": 41376, "source_guid": 900, "amount": amount,
            "landed_damage_observation": {"target_health_before_damage": before, "target_max_health": maximum}}


def _members(gaps: dict[int, int]) -> dict:
    members = [{"guid": guid, "death_sequence": 0, "native_death_count": int(guid in gaps),
                "native_resurrection_count": int(guid in gaps), "native_last_death_ms": 500_000 if guid in gaps else 0,
                "native_last_resurrection_ms": 500_000 + gaps.get(guid, -500_000)} for guid in (1, 2, 3, 4)]
    return {"status": {"raid_runtime": {"native_recovery": {"members": members}}}}


def test_sanity_inputs_measure_half_health_and_revive_gaps(tmp_path):
    target = {"encounter_route_node_id": NODE, "scenario": SCENARIO}
    # The round-2 pin: a bot dies, is back at 5,000 of 10,000 health 5 ms later, and every hit finds it there.
    pinned = [_hit(20_000 + index * 1_000, 3, 5_000, amount=5_000 if index % 5 == 0 else 100) for index in range(40)]
    pinned[1] = {**pinned[1], "timestamp_ms": 20_005}
    pinned += [_hit(21_500 + index * 1_000, 1, 9_000 - index * 100) for index in range(10)]
    pinned.append({**_hit(5_000, 2, 5_000), "route_node_id": "bwd.trash"})  # before the window: not counted
    run = write_run(tmp_path / "pinned", pinned, report=_members({3: 5, 1: 60_000}))
    result = sanity_inputs(run, target, ROOT)
    half = result["health_half"]
    assert (half["hits"], half["at_half"], half["fraction"]) == (50, 40, 0.8)
    assert half["by_actor"] == {"1": {"hits": 10, "at_half": 0}, "3": {"hits": 40, "at_half": 40}}
    revive = result["revives"]
    assert [(row["actor_id"], row["gap_ms"]) for row in revive["native"]] == [("1", 60_000), ("3", 5)]
    assert revive["combat_log"]["min_gap_ms_by_actor"] == {"3": 5}
    # Negative control: varied health, a death answered by a battle resurrection 16.6 s later.
    control = [_hit(20_000 + index * 1_000, 3, 9_500 - index * 200) for index in range(40)]
    control += [_hit(70_000, 3, 800, amount=900), _hit(86_629, 3, 4_000)]
    run = write_run(tmp_path / "control", control, report=_members({3: 16_629}))
    result = sanity_inputs(run, target, ROOT)
    assert result["health_half"]["at_half"] == 0 and result["health_half"]["hits"] == 42
    assert [row["gap_ms"] for row in result["revives"]["native"]] == [16_629]
    assert result["revives"]["combat_log"]["min_gap_ms_by_actor"] == {"3": 16_629}
    root = make_root(tmp_path)
    write_scoreboard(root, [kill("pinned", sanity_inputs=sanity_inputs(tmp_path / "pinned", target, ROOT)),
                            kill("control", sanity_inputs=result)])
    new_checks = {(row["check"], row["kill_id"], row["severity"]) for row in sanity_findings(root, SCENARIO, LABEL)
                  if row["check"] in ("health_pinned_half", "instant_revive")}
    assert new_checks == {("health_pinned_half", "pinned", "blocking"), ("instant_revive", "pinned", "blocking")}


def _revive_findings(tmp_path: Path, name: str, events: list, report: dict | None = None) -> list[dict]:
    """instant_revive findings of one kill recorded from a run directory (write_run: boss window 10-800 s)."""
    boss_hits = [_hit(20_000 + index * 1_000, 1, 9_000 - index * 10) for index in range(30)]  # a normal boss fight
    run = write_run(tmp_path / name, [*boss_hits, *events], report=report)
    root = make_root(tmp_path / f"{name}-root")
    target = {"encounter_route_node_id": NODE, "scenario": SCENARIO}
    write_scoreboard(root, [kill(name, sanity_inputs=sanity_inputs(run, target, ROOT))])
    return [row for row in sanity_findings(root, SCENARIO, LABEL) if row["check"] == "instant_revive"]


WINDOWS = {"before": (5_000, "bwd.trash"), "after": (900_000, "bwd.after_kill"), "in_boss_window": (50_000, NODE)}


@pytest.mark.parametrize("when", ["before", "after"])
def test_log_revive_outside_boss_does_not_block_clean_kill(tmp_path, when):
    def revived_at(at, node):  # a lethal hit, then the bot is hit alive 10 ms later
        return [{**_hit(at, 3, 800, amount=900), "route_node_id": node},
                {**_hit(at + 10, 3, 5_000), "route_node_id": node}]

    assert _revive_findings(tmp_path, when, revived_at(*WINDOWS[when])) == []
    control = _revive_findings(tmp_path, "control", revived_at(*WINDOWS["in_boss_window"]))
    assert [(row["severity"], row["evidence"]["actors"][0]) for row in control] == [
        ("blocking", {"id": "3", "name": "Mage", "combat_log_gap_ms": 10})]


@pytest.mark.parametrize("when", ["before", "after"])
def test_native_revive_outside_boss_does_not_block_clean_kill(tmp_path, when):
    def member(died):  # the native life edges: died and resurrected 5 ms later
        return {"status": {"raid_runtime": {"native_recovery": {"members": [
            {"guid": 3, "native_death_count": 1, "native_resurrection_count": 1, "native_last_death_ms": died,
             "native_last_resurrection_ms": died + 5, "native_dead": False}]}}}}

    assert _revive_findings(tmp_path, when, [], member(WINDOWS[when][0])) == []
    control = _revive_findings(tmp_path, "control", [], member(WINDOWS["in_boss_window"][0]))
    assert [(row["severity"], row["evidence"]["actors"][0]["native_gap_ms"]) for row in control] == [("blocking", 5)]


@pytest.mark.parametrize("fields, measured", [
    ({"native_dead": True}, False),                                          # StepLethal's inferred resurrection
    ({"native_dead": False, "native_last_resurrection_inferred": True}, False),  # a producer that marks it
    ({}, False),                                                             # no native_dead: ambiguous
    ({"native_dead": False}, True),                                          # an observed 0 ms dead -> alive edge
])
def test_inferred_native_resurrection_is_not_a_measured_zero_ms_revival(tmp_path, fields, measured):
    report = {"status": {"raid_runtime": {"native_recovery": {"members": [
        {"guid": 3, "native_death_count": 2, "native_resurrection_count": 2, "native_last_death_ms": 50_000,
         "native_last_resurrection_ms": 50_000, **fields}]}}}}
    run = write_run(tmp_path / "run", [_hit(20_000, 1, 9_000)], report=report)
    row = sanity_inputs(run, {"encounter_route_node_id": NODE, "scenario": SCENARIO}, ROOT)["revives"]["native"][0]
    assert row["measured"] is measured and row["in_boss_window"] is True
    assert row["gap_ms"] == (0 if measured else None) and ("unmeasured" in row) is not measured
    findings = _revive_findings(tmp_path, "kill", [], report)
    assert [row["severity"] for row in findings] == (["blocking"] if measured else [])


def test_retained_v2_native_gap_is_not_silently_treated_as_clean(tmp_path):
    root = make_root(tmp_path)
    legacy = {"native": [{"actor_id": "3", "deaths": 1, "gap_ms": 5}],  # written before measured/in_boss_window
              "combat_log": {"pairs": 0, "min_gap_ms_by_actor": {}}}
    write_scoreboard(root, [kill("k1", sanity_inputs=inputs(revives=legacy))])
    rows = by_check(sanity_findings(root, SCENARIO, LABEL))["instant_revive"]
    assert [(row["severity"], row["evidence"]["status"], row["evidence"]["kill_ids"]) for row in rows] == [
        ("warn", NOT_EVALUABLE, ["k1"])]
    assert "native_revive_unattributed_legacy_row" in rows[0]["detail"]


@pytest.mark.parametrize("died", [7_000, 50_000], ids=["pre_pull", "inside_window"])
def test_native_pre_pull_hull_does_not_override_explicit_trash_attribution(tmp_path, died):
    def member(at):
        return {"status": {"raid_runtime": {"native_recovery": {"members": [
            {"guid": 3, "native_death_count": 1, "native_resurrection_count": 1, "native_last_death_ms": at,
             "native_last_resurrection_ms": at + 5, "native_dead": False}]}}}}

    heal = {"kind": "heal", "timestamp_ms": 5_000, "route_node_id": NODE, "target_guid": 1, "actor_guid": 2,
            "amount": 100}  # a pre-pull heal on the boss node (window 10-800 s)
    trash_kill = {**_hit(died, 3, 800, amount=900), "route_node_id": "bwd.trash"}
    assert _revive_findings(tmp_path, "trash", [heal, trash_kill], member(died)) == []
    boss_kill = _hit(50_000, 3, 800, amount=900)  # control: the same revive after a boss-node lethal hit
    control = _revive_findings(tmp_path, "boss", [heal, boss_kill], member(50_000))
    assert [row["evidence"]["actors"][0]["native_gap_ms"] for row in control] == [5]


# --- record-time decision-trace observations (write_run: boss window 10-800 s, actors 1-4) -----------

TARGET = {"encounter_route_node_id": NODE, "scenario": SCENARIO}
BONE_ACTIVE, BONE_PILLAR = "nefarian_bone_warrior_active_over_45s", "nefarian_bone_warrior_on_pillar"
REFUSED = "nefarian_move_refused:"


# What a native decision-trace entry names (BotWorldTrace::AppendDecisionTraceEntryJson): its cohort, server epoch and
# attempt. write_run's combat-log capture is the same three (plus the combat-log epoch an entry does not carry).
TRACE_IDENTITY = {field: CAPTURE[field] for field in ("cohort_id", "server_epoch", "attempt_id")}


def _trace_row(bot, sequence, action, *, at=None, node=NODE, result="hold", actor=True, identity=TRACE_IDENTITY):
    """One retained-trace row: the harness's {bot_guid, bot_name, entry} wrapper around a decision-trace entry.

    The entry names the judged capture by default (``identity``; None leaves the identity fields out)."""
    entry = {"sequence": sequence, "timestamp_ms": 20_000 + sequence * 1_000 if at is None else at,
             "route_node_id": node, "situation": "adaptive_nefarian", "action": action, "result": result,
             **(identity or {})}
    return {"bot_guid": bot, "bot_name": f"Bot{bot}", "entry": entry} if actor else {"entry": {**entry, "actor": {"guid": bot}}}


def _write_gz(path: Path, rows: list) -> Path:
    with gzip.open(path, "wt", encoding="utf-8") as handle:
        handle.write("".join(json.dumps(row) + "\n" for row in rows))
    return path


def _trace(entries=(), *, bots=(1, 2, 3, 4), count=6, actor=True) -> list[dict]:
    """A contiguous trace covering the boss window (sequences 1..count per bot) and then the given
    (bot, action, result) entries, each with the bot's next sequence number. Each bot's first row is
    stamped before the window opens and its last after the window closes (run_sanity_inputs proves the
    window edges from those rows); the ones between fall inside the window."""
    final = {bot: count + sum(entry[0] == bot for entry in entries) for bot in bots}

    def at(bot: int, sequence: int) -> int:
        if sequence == 1:
            return WINDOW_START - 1_000
        return WINDOW_END + 1_000 if sequence == final[bot] else 20_000 + sequence * 1_000

    rows = [_trace_row(bot, sequence, "nefarian_platform_hold", at=at(bot, sequence), actor=actor)
            for bot in bots for sequence in range(1, count + 1)]
    last = {bot: count for bot in bots}
    for bot, action, result in entries:
        last[bot] += 1
        rows.append(_trace_row(bot, last[bot], action, at=at(bot, last[bot]), result=result, actor=actor))
    return rows


def _trace_run(tmp_path: Path, rows: list | None, name: str = "run", file: str = TRACE_HISTORY_FILE) -> Path:
    run = write_run(tmp_path / name, [_hit(20_000, 1, 9_000)])
    if rows is not None:
        _write_gz(run / file, rows)
    return run


def _observation_findings(tmp_path: Path, run: Path, name: str = "k1") -> list[dict]:
    """acceptance_observation findings of one kill recorded from a run directory."""
    root = make_root(tmp_path / f"{name}-root")
    write_scoreboard(root, [kill(name, sanity_inputs=sanity_inputs(run, TARGET, ROOT))])
    return by_check(sanity_findings(root, SCENARIO, LABEL)).get("acceptance_observation") or []


def test_sanity_inputs_count_the_nefarian_trace_observations(tmp_path):
    entries = [(3, BONE_ACTIVE, "observation"), (2, BONE_PILLAR, "observation"), (2, BONE_PILLAR, "observation"),
               (3, f"{REFUSED}{LEDGE}", "refused"), (3, f"{REFUSED}{LEDGE}", "refused"),
               (3, f"{REFUSED}hop:native_no_path", "refused"), (1, f"{REFUSED}hop:native_no_path", "refused")]
    rows = _trace(entries)
    # Not counted: an entry of another node before the window, and the terminal drain's copies of rows already held.
    rows.append(_trace_row(3, 0, BONE_PILLAR, at=5_000, node="bwd.trash", result="observation"))
    run = _trace_run(tmp_path, rows)
    _write_gz(run / TERMINAL_TRACE_DRAIN_FILE, [rows[-2], _trace_row(3, 3, "nefarian_platform_hold")])
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] == {
        ACTIVE: 1, PILLAR: 2,
        "move_refused": {"1": {"hop:native_no_path": 1}, "3": {"hop:native_no_path": 1, LEDGE: 2}}}
    trace = result["decision_trace"]
    assert (trace["complete"], trace["incomplete_reason"], trace["window_rows"], trace["actors"]) == (True, None, 31, 4)
    assert trace["files"] == {TRACE_HISTORY_FILE: len(rows), TERMINAL_TRACE_DRAIN_FILE: 2}
    assert trace["sequence_gaps"] == 0 and trace["actors_without_rows"] == []


def test_the_actor_of_a_row_falls_back_to_the_entry(tmp_path):
    rows = _trace([(3, f"{REFUSED}hop:stunned", "refused")], count=3, actor=False)
    result = sanity_inputs(_trace_run(tmp_path, rows), TARGET, ROOT)
    assert result["nefarian_observations"]["move_refused"] == {"3": {"hop:stunned": 1}}
    assert result["decision_trace"]["complete"] is True


def test_one_recorded_bone_warrior_entry_is_one_blocking_finding_and_none_is_none(tmp_path):
    one = _trace_run(tmp_path, _trace([(3, BONE_ACTIVE, "observation")]), "one")
    control = _trace_run(tmp_path, _trace([(3, f"{REFUSED}{LEDGE}", "refused")]), "control")
    rows = _observation_findings(tmp_path, one, "one")
    assert [(row["severity"], row["kill_id"], row["evidence"][ACTIVE], row["evidence"][PILLAR]) for row in rows] == [
        ("blocking", "one", 1, 0)]
    assert _observation_findings(tmp_path, control, "control") == []  # a complete trace with no entry


def test_a_missing_trace_is_unproven_end_to_end(tmp_path):
    run = _trace_run(tmp_path, None)  # a run directory without either retained trace file
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] is None
    assert result["decision_trace"]["available"] is False and result["decision_trace"]["complete"] is False
    assert result["decision_trace"]["incomplete_reason"] == "no_trace_file"
    (row,) = _observation_findings(tmp_path, run)
    assert (row["severity"], row["evidence"]["status"]) == ("blocking", "unproven")
    assert "holds no retained decision trace" in row["detail"]


@pytest.mark.parametrize("case, reason", [
    ("gaps", "sequence_gaps"),       # light heartbeat tails keep a few rows of a bot's stream
    ("silent actor", "actors_without_rows"),
    ("outside the window", "no_window_rows"),
    ("truncated gzip", "unreadable"),
    ("malformed row", "unreadable"),
    ("no sequence", "unsequenced_rows"),
])
def test_a_partial_trace_records_its_counts_but_cannot_vouch_for_a_zero(tmp_path, case, reason):
    rows = _trace()
    if case == "gaps":
        rows = [row for row in rows if row["bot_guid"] != 3 or row["entry"]["sequence"] not in (3, 4)]
    elif case == "silent actor":
        rows = [row for row in rows if row["bot_guid"] != 4]
    elif case == "outside the window":
        rows = [_trace_row(1, sequence, "x", at=5_000, node="bwd.trash") for sequence in range(1, 4)]
    elif case == "no sequence":
        rows = [{**row, "entry": {**row["entry"], "sequence": 0}} for row in rows]
    run = _trace_run(tmp_path, rows)
    path = run / TRACE_HISTORY_FILE
    if case == "truncated gzip":
        path.write_bytes(path.read_bytes()[:-40])
    elif case == "malformed row":
        with gzip.open(path, "at", encoding="utf-8") as handle:
            handle.write("{not json\n")
    result = sanity_inputs(run, TARGET, ROOT)
    trace = result["decision_trace"]
    assert (trace["complete"], trace["incomplete_reason"]) == (False, reason)
    assert {"gaps": trace["sequence_gaps"] == 2, "silent actor": trace["actors_without_rows"] == ["4"],
            "outside the window": trace["window_rows"] == 0, "truncated gzip": bool(trace["unreadable"]),
            "malformed row": bool(trace["unreadable"]), "no sequence": trace["unsequenced_rows"] == 24}[case]
    (row,) = _observation_findings(tmp_path, run)  # zeros the trace cannot vouch for: blocking, never a pass
    assert (row["severity"], row["evidence"]["status"]) == ("blocking", "unproven")


def test_a_partial_trace_still_blocks_on_an_observation_it_holds(tmp_path):
    rows = [row for row in _trace([(3, BONE_PILLAR, "observation")]) if row["bot_guid"] != 4]  # no rows of actor 4
    run = _trace_run(tmp_path, rows)
    assert sanity_inputs(run, TARGET, ROOT)["nefarian_observations"][PILLAR] == 1
    assert [row["severity"] for row in _observation_findings(tmp_path, run)] == ["blocking"]


def test_a_boss_window_that_is_unknown_is_not_evaluable(tmp_path):
    run = _trace_run(tmp_path, _trace([(3, BONE_ACTIVE, "observation")]))
    (run / "combat_analysis.json").write_text(json.dumps({"encounters": []}))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] is None
    assert result["decision_trace"]["incomplete_reason"] == "boss_window_unknown"


def test_only_the_nefarian_scenario_records_trace_observations(tmp_path):
    run = _trace_run(tmp_path, _trace([(3, BONE_ACTIVE, "observation")]))
    other = sanity_inputs(run, {"encounter_route_node_id": NODE, "scenario": "blackwing_descent_10n_magmaw"}, ROOT)
    assert "nefarian_observations" not in other and "decision_trace" not in other
    assert sanity_inputs(run, TARGET, ROOT)["nefarian_observations"][ACTIVE] == 1


def test_the_trace_scan_never_costs_the_record_its_other_inputs(tmp_path, monkeypatch):
    from tools.raid_program import run_sanity_inputs

    def broken(*_args, **_kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(run_sanity_inputs, "scan_decision_trace", broken)
    result = sanity_input_fields(_trace_run(tmp_path, _trace()), TARGET, ROOT)["sanity_inputs"]
    assert result["nefarian_observations"] is None and result["deaths"]["lethal_events"] == 0
    assert result["decision_trace"]["complete"] is False and "boom" in result["decision_trace"]["error"]


def test_enrage_rows_match_the_scenario_or_a_seen_entry():
    assert set(enrage_rows(REGISTRY, SCENARIO)) == {41376}
    assert set(enrage_rows(REGISTRY, "blackwing_descent_10n_magmaw")) == set()
    assert set(enrage_rows(REGISTRY, "other", {41376})) == {41376}


# --- stored BWD 10N rounds (git-tracked scoreboard) ------------------------------------------------------

def _stored(scenario: str, label: str) -> list[dict]:
    if not (ROOT / SCOREBOARD_DIR / f"{scenario}.jsonl").is_file():
        pytest.skip(f"{scenario} scoreboard not present")
    return sanity_findings(ROOT, scenario, label)


def _blocking(findings) -> set[tuple[str, str]]:
    """(check, first 8 characters of the run id) of each blocking finding."""
    return {(row["check"], str(row["kill_id"]).split("-")[3][:8]) for row in findings if row["severity"] == "blocking"}


def test_round_one_nefarian_is_blocked():
    findings = _stored(SCENARIO, R01)
    assert {("duration_outlier", "6bf52232"), ("repeated_deaths", "6bf52232"), ("idle_actor", "6bf52232")} <= _blocking(findings)
    unevaluable = {row["check"] for row in findings if row["evidence"].get("status") == NOT_EVALUABLE}
    assert "enrage_reached" in unevaluable


def test_round_two_nefarian_is_blocked():
    blocking = _blocking(_stored(SCENARIO, R02))
    assert {("duration_outlier", key) for key in ("9f22aff7", "ae5e8cc7", "c4c110ea")} <= blocking
    assert {("repeated_deaths", "ae5e8cc7"), ("repeated_deaths", "c4c110ea")} <= blocking


def test_round_two_magmaw_has_no_blocking_finding_and_atramedes_only_the_kiter_sound_evidence():
    # Round 3 fix (user decision 2026-09-30, "Bound kiter Sound"): a record before
    # sanity_inputs.atramedes_observations cannot prove the kiter stayed at 10 Sound or less, and that
    # unproven acceptance observation is its only blocking finding (tests/test_atramedes_sanity_observation.py).
    atramedes = _blocking(_stored("blackwing_descent_10n_atramedes", R02))
    assert atramedes and {check for check, _ in atramedes} == {"acceptance_observation"}
    magmaw = _stored("blackwing_descent_10n_magmaw", R02)  # records before health_half / revives
    assert {row["check"] for row in magmaw} == {"health_pinned_half", "instant_revive"}
    assert all(row["evidence"]["status"] == NOT_EVALUABLE and row["severity"] == "warn" for row in magmaw)


def test_command_line_exit_code(capsys):
    _stored(SCENARIO, R02)
    assert run_sanity.main([SCENARIO, "--label", R02]) == 1
    assert "blocking duration_outlier" in capsys.readouterr().out
    assert run_sanity.main(["blackwing_descent_10n_magmaw", "--label", R02, "--json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert set(printed) == {"blackwing_descent_10n_magmaw"}
    assert all(row["severity"] == "warn" for row in printed["blackwing_descent_10n_magmaw"])


def test_magmaw_b5_verdict_stays_byte_identical():
    path = ROOT / "artifacts/cata_raid_program/verdicts/blackwing_descent_10n_magmaw-b5-d1898555-7fcea04e9dd3.json"
    if not path.is_file():
        pytest.skip("accepted Magmaw verdict not hydrated")
    fresh = json.dumps(evaluate_target(ROOT, "blackwing_descent_10n_magmaw", "b5-d1898555"), indent=2, sort_keys=True)
    assert (fresh + "\n").encode() == path.read_bytes()
