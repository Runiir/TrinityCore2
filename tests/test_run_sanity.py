"""Hand-off hardening (2026-09-29): run-sanity findings over stored scoreboard records.

tools/raid_program/run_sanity.py flags results a coordinator used to reject by eye (the BWD 10N
round-1/2 Nefarian kills: 18-25 minute windows past Berserk, bots revived in place, stranded DPS),
and tools/raid_program/run_sanity_inputs.py records what older records lacked. Nothing here may
change evaluate_target output (Magmaw b5-d1898555 stays byte-identical)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

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


def make_root(tmp_path: Path, durations=(300.0, 250.0)) -> Path:
    root = tmp_path / "root"
    refs = [{"id": f"r{index}", "duration_sec": duration, "raid_dps": 100000.0,
             "actor_dps": {"blood_death_knight": 12000.0, "fire_mage": 30000.0}}
            for index, duration in enumerate(durations)]
    files = {
        "experiments/configs/wcl.json": {"schema": "test", "references": refs},
        f"experiments/configs/raid_targets/{SCENARIO}.json": {
            "schema": "raid_target_v1", "scenario": SCENARIO, "encounter_route_node_id": NODE,
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
    }
    for key, value in changes.items():
        document[key] = {**document[key], **value}
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


def write_scoreboard(root: Path, records: list[dict]) -> None:
    path = root / SCOREBOARD_DIR / f"{SCENARIO}.jsonl"
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
    assert not [row for row in findings if row["severity"] == "blocking"]
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
    assert "enrage_reached" not in by_check(findings) and not [row for row in findings if row["severity"] == "blocking"]


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


def write_run(path: Path, events, *, report=None, dropped=0) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    analysis = {"encounters": [{"route_node_id": NODE, "first_at_ms": 10_000, "last_at_ms": 800_000,
                                "actors": [{"actor_guid": guid} for guid in (1, 2, 3, 4)]}],
                "killed_hostile_damage_reconciliation": {"mismatch_count": 0, "mismatches": [],
                                                         "hostiles": [{"route_node_id": NODE, "target_entry": 41376}]}}
    (path / "combat_analysis.json").write_text(json.dumps(analysis))
    (path / "combat_log.json").write_text(json.dumps({"recent_events": events, "recent_events_dropped": dropped}))
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


def test_round_two_atramedes_and_magmaw_have_no_blocking_finding():
    assert not _blocking(_stored("blackwing_descent_10n_atramedes", R02))
    magmaw = _stored("blackwing_descent_10n_magmaw", R02)  # records before health_half / revives
    assert {row["check"] for row in magmaw} == {"health_pinned_half", "instant_revive"}
    assert all(row["evidence"]["status"] == NOT_EVALUABLE and row["severity"] == "warn" for row in magmaw)


def test_command_line_exit_code(capsys):
    _stored(SCENARIO, R02)
    assert run_sanity.main([SCENARIO, "--label", R02]) == 1
    assert "blocking duration_outlier" in capsys.readouterr().out
    assert run_sanity.main(["blackwing_descent_10n_atramedes", "--label", R02, "--json"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert set(printed) == {"blackwing_descent_10n_atramedes"}
    assert all(row["severity"] == "warn" for row in printed["blackwing_descent_10n_atramedes"])


def test_magmaw_b5_verdict_stays_byte_identical():
    path = ROOT / "artifacts/cata_raid_program/verdicts/blackwing_descent_10n_magmaw-b5-d1898555-7fcea04e9dd3.json"
    if not path.is_file():
        pytest.skip("accepted Magmaw verdict not hydrated")
    fresh = json.dumps(evaluate_target(ROOT, "blackwing_descent_10n_magmaw", "b5-d1898555"), indent=2, sort_keys=True)
    assert (fresh + "\n").encode() == path.read_bytes()
