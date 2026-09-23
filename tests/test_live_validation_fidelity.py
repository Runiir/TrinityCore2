"""Encounter damage fidelity: preflight classification, per-run boss melee statistics and the harness hook.

Fake creature_template row sources and a small synthetic combat log only; nothing here opens a database.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.bot_ml import live_validation_fidelity as fidelity

ROOT = Path(__file__).resolve().parents[1]
BOSS, ADD, TRASH, HEAD, STALKER = 900001, 900002, 900003, 900004, 900005
BOSS_25N = 910001
TANK, HEALER, BOSS_GUID = 30002, 30003, 50
T0 = 1_790_000_000_000  # combat-log clock; offsets below are milliseconds after it

REGISTRY = {
    "schema": fidelity.REGISTRY_SCHEMA,
    "creatures": {
        str(BOSS): {"name": "Test Boss", "raid": "r", "boss": "b", "mode": "10N", "role": "boss", "status": "calibrated",
                    "damage_modifier": 4.0,
                    "wcl_melee_reference": {"u_min": 9000, "u_max": 11000, "u_mean": None, "landed_samples": 3}},
        str(ADD): {"name": "Test Add", "role": "add", "status": "open", "damage_modifier": None},
        str(STALKER): {"name": "Test Stalker", "role": "add", "status": "not_applicable", "damage_modifier": None,
                       "reason": "never swings"},
    },
}


def template(entry, name, modifier=1.0, rank=1, flags=0, attack=2000, difficulty=(0, 0, 0)):
    return {"entry": entry, "name": name, "rank": rank, "unit_class": 1, "DamageModifier": modifier,
            "BaseAttackTime": attack, "BaseVariance": 1.0, "flags_extra": flags,
            "difficulty_entry_1": difficulty[0], "difficulty_entry_2": difficulty[1], "difficulty_entry_3": difficulty[2]}


def rows(boss_modifier=4.0):
    return {
        BOSS: template(BOSS, "Test Boss", boss_modifier, flags=1, difficulty=(BOSS_25N, 0, 0)),
        BOSS_25N: template(BOSS_25N, "Test Boss (1)", 1.0, flags=1, attack=1500),
        ADD: template(ADD, "Test Add", rank=0),
        TRASH: template(TRASH, "Test Trash"),
        HEAD: template(HEAD, "Test Head", rank=3),
        STALKER: template(STALKER, "Test Stalker", rank=0),
    }


class FakeRows:
    """Row source double: returns only the rows asked for and records each request."""

    def __init__(self, table):
        self.table, self.calls = table, []

    def __call__(self, entries):
        self.calls.append(list(entries))
        return {entry: self.table[entry] for entry in entries if entry in self.table}


def manifest(scenario="r_10n_b_diagnostic", head=False):
    targets = [BOSS, ADD, STALKER] + ([HEAD] if head else [])
    return {"schema": "bot_live_validation_route_manifest_v1", "scenario_id": scenario, "routes": [
        {"route_node_id": "t.regroup", "kind": "regroup", "source_entry": 0},
        {"route_node_id": "t.trash", "kind": "trash", "source_entry": TRASH, "pack_target_entries": [TRASH],
         "hazard_source_entry": 777, "target_priority": {"source_entry": TRASH, "alternate_target_entries": []}},
        {"route_node_id": "t.interaction", "kind": "interaction", "source_entry": 888},
        {"route_node_id": "t.boss", "kind": "boss", "source_entry": BOSS, "scripted_event_entries": [999],
         "mechanic_contract": {"target_entries": targets}},
    ]}


def by_entry(result):
    return {row["entry"]: row for row in result["entries"]}


# --- preflight ------------------------------------------------------------------------------------

def test_preflight_classifies_every_engaged_entry():
    source = FakeRows(rows())
    result = fidelity.preflight(manifest(), REGISTRY, source)
    assert result["status"] == "ok" and result["difficulty"]["mode"] == "10N"
    # Only engageable creatures are read: not hazards, interactions or scripted event objects.
    assert source.calls == [[BOSS, ADD, TRASH, STALKER]]
    entries = by_entry(result)
    assert entries[BOSS]["classification"] == "calibrated" and entries[BOSS]["role"] == "boss"
    assert entries[BOSS]["boss_basis"] == ["boss_route_node", "instance_bind", "registry_role_boss"]
    assert entries[BOSS]["route_nodes"] == ["t.boss"] and entries[BOSS]["db"]["base_attack_time_ms"] == 2000
    assert entries[ADD]["classification"] == "uncalibrated" and entries[ADD]["role"] == "add"
    assert entries[ADD]["detail"] == "registry open; DB DamageModifier 1"
    assert entries[TRASH]["classification"] == "uncalibrated" and entries[TRASH]["role"] == "trash"
    assert entries[TRASH]["detail"] == "not in registry; DB DamageModifier 1"
    assert entries[STALKER]["classification"] == "not_applicable"
    assert result["counts"] == {"calibrated": 1, "not_applicable": 1, "uncalibrated": 2}
    assert result["boss_entries"] == [BOSS] and result["not_blizzlike_entries"] == [ADD, TRASH]
    assert fidelity.fidelity_verdict(result, {}) == (True, [])  # trash and adds do not decide blizzlike


def test_registry_value_not_in_the_db_is_a_mismatch_and_not_blizzlike():
    result = fidelity.encounter_fidelity(manifest(), REGISTRY, FakeRows(rows(boss_modifier=1.0)))
    boss = by_entry(result["preflight"])[BOSS]
    assert boss["classification"] == "mismatch" and boss["detail"] == "registry DamageModifier 4, DB 1"
    assert result["blizzlike"] is False
    assert result["reasons"] == ["boss 900001 Test Boss: mismatch (registry DamageModifier 4, DB 1)"]
    assert result["informational"] is True


def test_rank_3_target_is_a_boss_and_an_uncalibrated_boss_breaks_blizzlike():
    result = fidelity.encounter_fidelity(manifest(head=True), REGISTRY, FakeRows(rows()))
    head = by_entry(result["preflight"])[HEAD]
    assert head["role"] == "boss" and head["boss_basis"] == ["rank_3"] and head["classification"] == "uncalibrated"
    assert result["blizzlike"] is False
    assert result["reasons"] == ["boss 900004 Test Head: uncalibrated (not in registry; DB DamageModifier 1)"]


def test_unregistered_db_change_is_reported_as_uncalibrated():
    table = rows()
    table[TRASH] = template(TRASH, "Test Trash", modifier=3.0)
    trash = by_entry(fidelity.preflight(manifest(), REGISTRY, FakeRows(table)))[TRASH]
    assert trash["classification"] == "uncalibrated"
    assert trash["detail"] == "not in registry; DB DamageModifier 3 without registry evidence"


def test_missing_template_row():
    table = rows()
    del table[ADD]
    assert by_entry(fidelity.preflight(manifest(), REGISTRY, FakeRows(table)))[ADD]["classification"] == "missing_template"


def test_difficulty_template_is_the_one_classified():
    result = fidelity.preflight(manifest("r_25n_b_diagnostic"), REGISTRY, FakeRows(rows()))
    boss = by_entry(result)[BOSS]
    assert result["difficulty"] == {"mode": "25N", "spawn_mode": 1, "is_raid": True, "source": "route_manifest.scenario_id"}
    assert boss["effective_entry"] == BOSS_25N and boss["db"]["base_attack_time_ms"] == 1500
    assert boss["classification"] == "uncalibrated"  # the 10N value is never borrowed
    assert fidelity.fidelity_verdict(result, {})[0] is False


def test_effective_entry_follows_the_native_difficulty_fallback():
    templates = {BOSS: {"difficulty_entries": [BOSS_25N, 0, 0]}, BOSS_25N: {"difficulty_entries": [0, 0, 0]}}
    assert fidelity.effective_entry(BOSS, templates, 0, True) == BOSS
    assert fidelity.effective_entry(BOSS, templates, 1, True) == BOSS_25N
    assert fidelity.effective_entry(BOSS, templates, 2, True) == BOSS  # 10H without a template -> 10N
    assert fidelity.effective_entry(BOSS, templates, 3, True) == BOSS_25N  # 25H without a template -> 25N
    assert fidelity.effective_entry(BOSS, templates, 2, False) == BOSS_25N  # non-raid steps down by one


@pytest.mark.parametrize("text,mode", [("blackwing_descent_10n_magmaw_diagnostic", "10N"), ("normal_25man", "25N"),
                                       ("heroic_10man", "10H"), ("bwd_25hc_nefarian", "25H"), ("stonecore", None)])
def test_resolve_difficulty(text, mode):
    assert fidelity.resolve_difficulty({"scenario_id": text})["mode"] == mode
    assert fidelity.resolve_difficulty({}, "10H")["spawn_mode"] == 2


def test_db_failure_never_raises_and_runtime_swings_decide():
    def broken(entries):
        raise SystemExit("pymysql is required; run through pixi")
    result = fidelity.encounter_fidelity(manifest(), REGISTRY, broken)
    assert result["preflight"]["status"] == "db_unavailable" and "pymysql" in result["preflight"]["db_error"]
    assert by_entry(result["preflight"])[BOSS]["classification"] == "unverified"
    assert result["blizzlike"] is None
    confirmed = fidelity.encounter_fidelity(manifest(), REGISTRY, broken, combat_log=combat_log(modifier=4.0))
    assert confirmed["blizzlike"] is True and confirmed["reasons"] == []
    wrong = fidelity.encounter_fidelity(manifest(), REGISTRY, broken, combat_log=combat_log(modifier=1.0))
    assert wrong["blizzlike"] is False
    assert wrong["reasons"] == ["boss 900001 Test Boss: runtime DamageModifier 1 != registry 4"]


# --- per-run melee --------------------------------------------------------------------------------

def swing(at, outcome, attacker, *, target=TANK, source=BOSS, guid=BOSS_GUID, modifier=4.0, armor=None, hit=None,
          absorbed=0, blocked=0, resolved=None, pet=False):
    armor = int(attacker * 0.4) if armor is None else armor
    hit = armor if hit is None else hit
    resolved = hit - absorbed if resolved is None else resolved
    sequence = at + 1
    return {"kind": "melee_resolution", "event_sequence": sequence, "melee_resolution_sequence": sequence,
            "timestamp_ms": T0 + at, "route_node_id": "t.boss", "source_entry": source, "source_guid": guid,
            "source_name": "Test Boss" if source == BOSS else "Test Trash", "source_is_pet": pet, "target_guid": target,
            "actor_guid": target, "actor_role": "tank" if target == TANK else "healer",
            "melee_resolution": {
                "stage_mask": 511, "weapon_roll_amount": attacker - 100, "after_attacker_bonus_amount": attacker,
                "after_target_bonus_amount": int(attacker * 0.9), "after_script_hook_amount": int(attacker * 0.9),
                "after_armor_amount": armor, "after_hit_outcome_amount": hit, "after_resilience_amount": hit,
                "resolved_damage_amount": resolved, "blocked_amount": blocked, "absorbed_amount": absorbed,
                "resisted_amount": 0, "attack_type": 0, "hit_outcome_name": outcome,
                "attacker_base_attack_time_ms": 2000, "attacker_template_damage_modifier": modifier,
                "attacker_rank": 1, "attacker_level": 88, "attacker_published_min_damage": 7000.0,
                "attacker_published_max_damage": 11000.0}}


def damage(at, amount, related=None, spell=0, target=TANK):
    return {"kind": "damage", "timestamp_ms": T0 + at, "amount": amount, "related_event_sequence": related,
            "spell_id": spell, "source_entry": BOSS, "target_guid": target, "actor_guid": target,
            "actor_role": "tank" if target == TANK else "healer", "route_node_id": "t.boss"}


def combat_log(modifier=4.0):
    events = [
        swing(0, "normal", 10000, armor=4000, absorbed=1000, modifier=modifier), damage(0, 3000, 1),
        swing(2000, "critical", 12000, armor=4000, hit=8000, absorbed=8000, modifier=modifier), damage(2000, 0, 2001),
        swing(4000, "parry", 8000, hit=0, resolved=0, modifier=modifier),
        damage(5000, 1000, spell=12345),
        swing(6500, "block", 10000, armor=4000, hit=2800, blocked=1200, modifier=modifier), damage(6500, 2800, 6501),
        swing(9000, "miss", 9000, hit=0, resolved=0, modifier=modifier),
        swing(9500, "normal", 5000, source=TRASH, guid=77, modifier=1.0),
        swing(9600, "normal", 700, source=28017, guid=78, pet=True),  # pets are never creature melee
        damage(9700, 400, target=HEALER),
    ]
    return {"recent_events": events, "recent_events_dropped": 0}


ANALYSIS = {"encounters": [{"route_node_id": "t.boss", "first_at_ms": T0, "last_at_ms": T0 + 10000,
                            "duration_sec": 10.0}]}


def test_boss_melee_statistics():
    result = fidelity.encounter_fidelity(manifest(), REGISTRY, FakeRows(rows()), combat_log=combat_log(),
                                         combat_analysis=ANALYSIS)
    boss = result["boss_melee"][str(BOSS)]
    assert boss["schema"] == fidelity.BOSS_MELEE_SCHEMA and boss["name"] == "Test Boss"
    assert boss["swings"] == 5 and boss["landed"] == 3
    assert boss["outcomes"] == {"block": 1, "crit": 1, "hit": 1, "miss": 1, "parry": 1}
    assert boss["swing_gap_ms"] == {"count": 4, "median": 2250.0, "base_attack_time_ms": 2000, "median_over_base": 1.125}
    stages = boss["stages"]
    assert stages["after_attacker_bonus_amount"] == {"population": "all_swings", "count": 5, "min": 8000.0,
                                                     "mean": 9800.0, "max": 12000.0}
    assert stages["after_armor_amount"]["count"] == 5 and stages["after_hit_outcome_amount"]["population"] == "landed"
    assert stages["health_damage"] == {"population": "landed", "basis": "linked_damage_event_amount", "count": 3,
                                       "min": 0.0, "mean": 1933.3, "max": 3000.0}
    assert stages["blocked_amount"]["max"] == 1200.0
    assert boss["absorbed"] == {"pre_absorb_total": 14800.0, "absorbed_total": 9000.0, "absorbed_share": 0.6081,
                                "fully_absorbed_hits": 1}
    assert boss["boss_window"]["basis"] == "combat_analysis_encounter" and boss["boss_window"]["duration_sec"] == 10.0
    assert boss["tank_damage_taken_per_sec"] == {"all_sources": 680.0, "this_creature_melee": 580.0}
    assert boss["tank_target_share"] == 1.0
    assert boss["runtime_template"]["damage_modifier"] == 4.0 and boss["runtime_template"]["damage_modifiers_seen"] == [4.0]
    wcl = boss["wcl_comparison"]
    assert wcl["u_mean"] == 10000.0 and wcl["mean_basis"] == "wcl_envelope_midpoint"
    assert wcl["ratios"] == {"min": 0.8889, "mean": 0.98, "max": 1.0909}
    assert wcl["flags"] == ["min_outside_10pct"] and wcl["within_tolerance"] is False
    assert wcl["implied_damage_modifier_from_mean"] == pytest.approx(4.08)
    assert result["creature_melee"] == {str(TRASH): {"name": "Test Trash", "swings": 1, "landed": 1,
                                                     "after_attacker_mean": 5000.0, "runtime_damage_modifier": 1.0,
                                                     "registry_status": None}}
    assert result["blizzlike"] is True


def test_boss_melee_without_route_uses_rank_3_swings_and_first_to_last_window():
    log = combat_log()
    for event in log["recent_events"]:
        if event.get("source_entry") == BOSS and event["kind"] == "melee_resolution":
            event["melee_resolution"]["attacker_rank"] = 3
    melee, others = fidelity.boss_melee(log, {}, REGISTRY)
    assert list(melee) == [str(BOSS)] and str(TRASH) in others
    assert melee[str(BOSS)]["boss_window"] == {"route_node_id": None, "first_at_ms": T0, "last_at_ms": T0 + 9000,
                                                "duration_sec": 9.0, "basis": "first_to_last_swing"}


def test_uncalibrated_boss_that_swings_is_not_blizzlike_even_without_db():
    registry = {"schema": fidelity.REGISTRY_SCHEMA, "creatures": {}}
    result = fidelity.encounter_fidelity(manifest(), registry, None, combat_log=combat_log(modifier=1.0))
    assert result["preflight"]["status"] == "db_not_read"
    assert result["blizzlike"] is False
    assert result["reasons"][0].startswith("boss 900001 Test Boss: uncalibrated (not in registry")


# --- hook and scoreboard helpers ------------------------------------------------------------------

@pytest.fixture
def repo(tmp_path):
    path = tmp_path / fidelity.REGISTRY_PATH
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps(REGISTRY))
    return tmp_path


def test_attach_writes_report_and_combat_analysis(repo):
    report = {"combat_log": combat_log(), "combat_analysis": json.loads(json.dumps(ANALYSIS))}
    result = fidelity.attach_encounter_fidelity(report, manifest(), None, root=repo, fetch_rows=FakeRows(rows()))
    assert report["encounter_fidelity"] is result and result["blizzlike"] is True
    assert result["preflight"]["schema"] == fidelity.PREFLIGHT_SCHEMA
    mirrored = report["combat_analysis"]["encounter_fidelity"]
    assert set(mirrored) == {"schema", "informational", "blizzlike", "reasons", "boss_melee", "creature_melee"}
    assert mirrored["boss_melee"][str(BOSS)]["swings"] == 5


def test_attach_never_raises(repo, monkeypatch, tmp_path):
    config = tmp_path / "worldserver.conf"
    config.write_text("# no WorldDatabaseInfo here\n")
    report = {"combat_log": {"recent_events": ["junk", {"kind": "melee_resolution", "melee_resolution": None}]},
              "combat_analysis": {}}
    result = fidelity.attach_encounter_fidelity(report, manifest(), config, root=repo)
    assert result["preflight"]["status"] == "db_unavailable" and "WorldDatabaseInfo" in result["preflight"]["db_error"]
    assert "encounter_fidelity" not in report["combat_analysis"]  # nothing to mirror into an empty analysis

    def explode(*args, **kwargs):
        raise RuntimeError("bug")
    monkeypatch.setattr(fidelity, "encounter_fidelity", explode)
    report = {"combat_analysis": {"encounters": []}}
    result = fidelity.attach_encounter_fidelity(report, manifest(), None, root=repo)
    assert result["status"] == "error" and result["blizzlike"] is None and result["error"] == "RuntimeError: bug"
    assert report["combat_analysis"]["encounter_fidelity"]["blizzlike"] is None


def test_no_route_skips_the_database(repo):
    def forbidden(entries):
        raise AssertionError("no engaged entries: the DB must not be read")
    result = fidelity.attach_encounter_fidelity({"combat_log": {"recent_events": []}}, {}, None, root=repo,
                                                fetch_rows=forbidden)
    assert result["preflight"]["status"] == "no_engaged_entries" and result["blizzlike"] is None


def test_scoreboard_summary_and_recompute_from_run_dir(repo, tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    (run / "report.json").write_text(json.dumps({"completion_reason": "x"}))
    (run / "validation_route_manifest.json").write_text(json.dumps(manifest()))
    (run / "combat_log.json").write_text(json.dumps(combat_log(modifier=1.0)))
    (run / "combat_analysis.json").write_text(json.dumps(ANALYSIS))
    result = fidelity.fidelity_from_run_dir(run, root=repo)
    assert result["basis"] == "combat_log_recomputed_without_db" and result["blizzlike"] is False
    summary = fidelity.scoreboard_summary(result)
    assert summary["blizzlike"] is False and summary["basis"] == "combat_log_recomputed_without_db"
    assert summary["reasons"] == ["boss 900001 Test Boss: runtime DamageModifier 1 != registry 4"]
    assert summary["bosses"][str(BOSS)] == {
        "name": "Test Boss", "swings": 5, "after_attacker_mean": 9800.0, "wcl_mean": 10000.0,
        "wcl_mean_basis": "wcl_envelope_midpoint", "mean_ratio": 0.98, "wcl_flags": ["min_outside_10pct"],
        "runtime_damage_modifier": 1.0, "registry_damage_modifier": 4.0}
    # A harness block wins over recomputation.
    (run / "report.json").write_text(json.dumps({"encounter_fidelity": {"schema": fidelity.FIDELITY_SCHEMA,
                                                                        "blizzlike": True, "basis": "harness"}}))
    assert fidelity.fidelity_from_run_dir(run, root=repo)["basis"] == "harness"
    assert fidelity.scoreboard_summary({"schema": "other"}) is None


def test_wcl_reference_comes_from_the_registry_or_its_ledger():
    registry = fidelity.load_registry(ROOT)
    direct = fidelity.wcl_reference(registry, 41570, ROOT)
    assert (direct["u_min"], direct["u_max"], direct["u_mean"]) == (111531.0, 178540.0, 145035.5)
    assert direct["mean_basis"] == "wcl_envelope_midpoint" and direct["source"].startswith("registry:")
    row = dict(registry["creatures"]["41570"])
    row.pop("wcl_melee_reference")
    ledger = fidelity.wcl_reference({"creatures": {"41570": row}}, 41570, ROOT)
    assert (ledger["u_min"], ledger["u_max"]) == (111531.0, 178540.0) and ledger["source"].startswith("ledger:")
    assert fidelity.wcl_reference(registry, 51101, ROOT) is None


def test_scenario_closure_rule(repo):
    assert fidelity.scenario_damage_fidelity(repo, {"raid": "r", "boss": "b", "mode": "10N"}) == {
        "registry": fidelity.REGISTRY_PATH.as_posix(), "boss_entries": {str(BOSS): "calibrated"}, "closable": True,
        "reason": None}
    fidelity.check_scenario_damage_fidelity(repo, {"raid": "r", "boss": "b", "mode": "10N"})
    with pytest.raises(ValueError, match="no boss entry"):
        fidelity.check_scenario_damage_fidelity(repo, {"raid": "r", "boss": "b", "mode": "25H"})
    real = fidelity.scenario_damage_fidelity(ROOT, {"raid": "blackwing_descent", "boss": "magmaw", "mode": "10N"})
    assert real["boss_entries"] == {"41570": "calibrated", "42347": "not_applicable", "48270": "not_applicable"}
    assert real["closable"] is True and real["reason"] is None
