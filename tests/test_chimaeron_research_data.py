"""Chimaeron research packet, raid target, WCL references and native script repairs."""
from __future__ import annotations

import json
import re
import struct
from pathlib import Path

import pytest

from tools.raid_program import raid_shard_identity as ids
from tools.raid_program import scoreboard_core

ROOT = Path(__file__).resolve().parents[1]
ENCOUNTERS = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent"
CONTRACT = ENCOUNTERS / "chimaeron_v1.json"
LEDGER = ENCOUNTERS / "chimaeron_ledger_v1.json"
WCL_REFERENCE = ENCOUNTERS / "chimaeron_wcl_dps_reference_v1.json"
WCL_TIMELINES = ENCOUNTERS / "chimaeron_wcl_cast_timelines_v1.json"
DOSSIER = ROOT / "docs/bot_raids/strategies/t11/blackwing_descent/chimaeron.md"
TARGET = ROOT / "experiments/configs/raid_targets/blackwing_descent_10n_chimaeron.json"
COMPOSITION = ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"
AUDIT = ROOT / "experiments/configs/cata_raid_bwd_quantitative_resolution_audit_v1.json"
SCRIPT = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_chimaeron.cpp"
DBC = ROOT / "data/dbc/enUS"
# Tier-11 references (raid item level 352-366), round 3 of the BWD 10N program (2026-09-30).
T11_REFERENCES = [
    "MxFq7TRbvnjGY1hJ-fight27", "JLvtbwNpFrzf6qjQ-fight14", "B4J8vQVnbxFdjf3P-fight22",
    "HF62ky4w8ThJmrbY-fight33", "AztLjaG8wJh2fvbk-fight37", "TtAL96aBnyHgXNMJ-fight3",
    "zg18Kt3FkAdyv7jn-fight11",
]


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def function_body(source: str, signature: str) -> str:
    start = source.index(signature)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        depth += (source[index] == "{") - (source[index] == "}")
        if depth == 0:
            return source[brace + 1:index]
    raise AssertionError(signature)


def test_contract_and_ledger_keep_identity_and_fail_closed() -> None:
    contract, ledger = load(CONTRACT), load(LEDGER)
    for document in (contract, ledger):
        assert document["raid"] == "blackwing_descent"
        assert document["boss_slug"] == document["encounter"] == "chimaeron"
        assert document["modes"] == ["10N", "10H", "25N", "25H"]
        assert document["fidelity_state"] == "fidelity_blocked"
        assert document["unresolved_material_count"] == len(document["unresolved"]) == 9
    assert contract["ledger_path"] == LEDGER.relative_to(ROOT).as_posix()
    assert ledger["contract_path"] == CONTRACT.relative_to(ROOT).as_posix()
    assert ledger["dossier_path"] == DOSSIER.relative_to(ROOT).as_posix()
    # The audit report pins the ledger blocker keys; they must not drift.
    audit = next(boss for boss in load(AUDIT)["bosses"] if boss["boss_slug"] == "chimaeron")
    assert {row["key"] for row in ledger["unresolved"]} == {row["key"] for row in audit["blockers"]}


def test_research_completion_covers_the_10n_obligations_with_known_sources() -> None:
    ledger = load(LEDGER)
    sources = {row["id"] for row in ledger["source_catalog"]}
    rows = {row["key"]: row for row in ledger["research_completion"]}
    for key in ("encounter_engage_and_finkle_interaction", "caustic_slime", "break_double_attack_tank_exchange",
                "massacre_and_mixture_floor", "systems_failure_feud_outage", "mortality_burn", "boss_health",
                "boss_melee_damage_fidelity", "wcl_dps_reference", "berserk"):
        row = rows[key]
        assert row["status"] and row["known"] and row["next"], key
        assert set(row["source_refs"]) <= sources, key
    for section in ("values", "timers"):
        for row in ledger[section]:
            assert set(row["source_refs"]) <= sources, row["key"]
    # WCL-dependent work is promoted only with a WCL source attached.
    assert rows["wcl_dps_reference"]["status"] == "resolved_t11_band_seven_kills"
    assert "wcl_t11_chimaeron_refs_20260930" in rows["wcl_dps_reference"]["source_refs"]
    # Round 3: the knockout rule and the Slime repeat are resolved for 10N from WCL.
    for key in ("caustic_slime", "systems_failure_feud_outage"):
        assert rows[key]["status"] == "resolved_10N", key
        assert "wcl_chimaeron_mechanics_census_20260930" in rows[key]["source_refs"], key
    census = ledger["knockout_census_10N"]["by_cycle_position"]
    assert census["1"]["knockouts"] == 0 and census["3"]["knockouts"] == census["3"]["massacres"]
    assert 0 < census["2"]["knockouts"] < census["2"]["massacres"]
    assert sum(row["massacres"] for row in census.values()) == sum(
        len(kill["massacres"]) for kill in ledger["knockout_census_10N"]["kills"])
    assert rows["boss_melee_damage_fidelity"]["status"] == "calibrated_staged"
    assert rows["boss_health"]["status"] == "resolved_10N"
    for key in ("wcl_dps_reference", "boss_melee_damage_fidelity", "boss_health"):
        assert "wcl_MxFq7TRbvnjGY1hJ_27" in rows[key]["source_refs"], key
    # User raid experience 2026-09-30: no berserk on normal or heroic; native unchanged.
    assert rows["berserk"]["status"] == "resolved_by_user_raid_experience"
    assert rows["berserk"]["modes"] == ["10N", "10H", "25N", "25H"]
    assert "user_raid_experience_20260930_chimaeron_berserk" in rows["berserk"]["source_refs"]
    assert ledger["wcl_extraction_plan"]["status"] == "extracted_2026_09_27"


def test_berserk_decision_is_quoted_and_the_native_script_stays_without_one() -> None:
    quote = ("Chima hc and normal doesnt have berserks. After the 20% its basically a soft enrage. "
             "Kill it before it kills you due to the 99% reduced healing")
    ledger, contract = load(LEDGER), load(CONTRACT)
    source = next(row for row in ledger["source_catalog"]
                  if row["id"] == "user_raid_experience_20260930_chimaeron_berserk")
    assert source["quote"] == quote and "user raid experience 2026-09-30" in source["authority"]
    assert "user_raid_experience_20260930_chimaeron_berserk" in contract["source_refs"]
    assert next(row for row in ledger["values"] if row["key"] == "berserk")["user_raid_experience_20260930"] == quote
    assert next(row for row in contract["timer_contract"] if row["key"] == "berserk")["native"] == "none"
    assert quote in DOSSIER.read_text(encoding="utf-8")
    assert "berserk" not in SCRIPT.read_text(encoding="utf-8").lower()


def test_mode_scopes_keep_10n_blocked_only_by_its_open_claims() -> None:
    # event_cadence lost its last 10N part (the berserk) on 2026-09-30 and stays open for the 2 s-swing modes.
    open_10n = {"helper_field_reset", "retail_reset_credit_loot"}
    for document in (load(CONTRACT), load(LEDGER)):
        assert document["fidelity_state_by_mode"] == dict.fromkeys(("10N", "10H", "25N", "25H"), "fidelity_blocked")
        for claim in document["unresolved"]:
            assert claim["modes"] and set(claim["modes"]) <= {"10N", "10H", "25N", "25H"}, claim["key"]
        covering = {claim["key"] for claim in document["unresolved"] if "10N" in claim["modes"]}
        assert covering == open_10n
        cadence = next(claim for claim in document["unresolved"] if claim["key"] == "event_cadence")
        assert cadence["modes"] == ["10H", "25N", "25H"]


def test_ledger_values_reproduce_the_native_formulas() -> None:
    values = {row["key"]: row for row in load(LEDGER)["values"]}
    health = values["health"]["mode_values_native"]
    total_hp_88_warrior = 85892
    modifiers = {"10N": 241, "25N": 844, "10H": 422, "25H": 1476}
    assert health == {mode: total_hp_88_warrior * modifier for mode, modifier in modifiers.items()}
    assert values["health"]["status"].startswith("resolved_10N")
    assert values["health"]["wcl_10N_derivation"]["derived_max_health"] == health["10N"]
    roll = values["boss_melee"]["mode_values"]["10N"]["native_roll_at_damage_modifier_1"]
    base, ap_term, speed = 2947.9421, 1226 / 14, 4.0
    assert roll["min"] == round((base + ap_term) * speed, 1)
    assert roll["max"] == round((base * 1.5 + ap_term) * speed, 1)
    assert values["caustic_slime"]["mode_values"] == {"10N": 235200, "25N": 270480, "10H": 235200, "25H": 270480}
    assert values["pips_mixture_health_floor"]["mode_values"]["10N"] == 10000


def _wdbc(name: str) -> list[tuple[int, ...]]:
    data = (DBC / name).read_bytes()
    magic, count, fields, size, _ = struct.unpack_from("<4s4i", data)
    assert magic == b"WDBC" and size == fields * 4
    return list(struct.iter_unpack(f"<{fields}i", data[20:20 + count * size]))


@pytest.mark.skipif(not (DBC / "SpellEffect.dbc").exists(), reason="client DBC not extracted")
def test_recorded_values_match_the_execution_client_rows() -> None:
    effects: dict[tuple[int, int], tuple[int, ...]] = {}
    for row in _wdbc("SpellEffect.dbc"):
        effects[(row[24], row[25])] = row  # (spell id, effect index)
    # SpellEffect columns: 1 effect, 3 aura, 4 period, 5 base points, 21 trigger.
    assert [effects[(spell, 0)][5] for spell in (82935, 88915, 88916, 88917)] == [235200, 270480, 235200, 270480]
    assert effects[(82935, 1)][5] == -75 and effects[(82935, 1)][3] == 54
    assert effects[(82848, 0)][5] == 999999
    assert effects[(82705, 0)][5] == 10000 and effects[(82705, 0)][4] == 1000
    assert effects[(88861, 0)][4] == 26000 and effects[(88861, 0)][21] == 82705
    assert effects[(88861, 1)][21] == 91106
    assert effects[(82881, 0)][5] == 25 and effects[(82881, 1)][5] == -15
    assert effects[(82890, 0)][5] == -99
    assert effects[(82934, 2)][5] == 10
    durations = {row[0]: row[1] for row in _wdbc("SpellDuration.dbc")}
    spells = {row[0]: row for row in _wdbc("Spell.dbc")}
    assert durations[spells[88872][13]] == 30000  # Feud
    assert durations[spells[88861][13]] == 26000  # Reroute Power
    assert durations[spells[82881][13]] == 60000  # Break


def test_wcl_references_and_timelines_are_extracted() -> None:
    reference, timelines = load(WCL_REFERENCE), load(WCL_TIMELINES)
    assert reference["schema"] == "chimaeron_wcl_dps_reference_v1"
    assert reference["extraction_status"] == "extracted"
    ids_ = [row["id"] for row in reference["references"]]
    assert ids_ == T11_REFERENCES
    band = reference["item_level_band"]
    for row in reference["references"]:
        assert row["mode"] == "10N" and row["duration_sec"] > 0 and row["raid_dps"] > 0
        assert row["limitations"] and row["url"].startswith("https://classic.warcraftlogs.com/reports/")
        # Tier-11 band (user decision 2026-09-30) and T11 era.
        assert band["min"] <= row["item_level"] <= band["max"] and row["in_item_level_band"]
        assert row["after_hotfix_cutoff_2025_02_20"] is False
        healers = {r["spec"] for r in row["roster"] if r["role"] == "healer"}
        assert not healers & set(row["actor_dps"])
    assert "xAhkN2y9YP3KRmnJ-fight14" not in ids_
    fight27 = reference["references"][0]["actor_dps"]
    assert fight27["survival_hunter"] == pytest.approx((26557.1 + 29102.4) / 2, abs=0.1)
    assert timelines["schema"] == "chimaeron_wcl_cast_timelines_v1"
    assert timelines["reference_id"] == "MxFq7TRbvnjGY1hJ-fight27"
    actors = list(timelines["actors"])
    for extra in timelines["additional_references"]:
        assert extra["reference_id"] in ids_ and extra["duration_sec"] > 0
        actors += extra["actors"]
    # Every timeline actor comes from an in-band reference (the 401.4 kill's actors are gone).
    assert {actor["actor_id"].split("-source")[0] for actor in actors} <= {i.split("-fight")[0] for i in ids_}
    assert {actor["class_spec"] for actor in actors} >= {
        "blood_death_knight", "survival_hunter", "fire_mage", "retribution_paladin",
        "assassination_rogue", "demonology_warlock"}
    for actor in actors:
        assert actor["row_count"] == len(actor["casts"]) > 0
        assert all(cast["ability"] != "Begin Cast" for cast in actor["casts"])
    massacre = [e["t"] for e in timelines["boss_events"] if e["spell_id"] == 82848 and e["event"] == "Begin Cast"]
    assert massacre == [25.966, 55.958]


def test_raid_target_roster_is_the_canonical_chimaeron_copy() -> None:
    target = load(TARGET)
    assert target["schema"] == "raid_target_v1" and target["scenario"] == "blackwing_descent_10n_chimaeron"
    assert target["encounter_route_node_id"] == "bwd.chimaeron.encounter"
    assert target["wcl_reference_manifest"] == WCL_REFERENCE.relative_to(ROOT).as_posix()
    assert target["wcl_cast_timelines"] == WCL_TIMELINES.relative_to(ROOT).as_posix()
    assert target["matched_reference_ids"] == T11_REFERENCES
    assert target["actor_dps_ratio"] == 0.95 and target["fallback_reference"]["ratio"] == 0.90
    assert target["roles_without_dps_target"] == ["healer"] and target["max_boss_window_deaths"] == 0
    assert target["shard"]["lockout"]["precompleted_boss_keys"] == ["magmaw", "omnotron"]

    composition = load(COMPOSITION)
    boss = next(row for row in composition["bosses"] if row["boss_key"] == "chimaeron")
    assert target["shard"]["spec_selection"] == boss["spec_selection"]
    expected = {}
    for character in composition["characters"]:
        slot = character["slot"]
        packed = ids.packed_index("blackwing_descent", "10N", boss["boss_number"], 0, slot)
        specs = character["specs"]
        spec = boss["spec_selection"].get(character["character_key"], specs[0])
        expected[str(ids.character_guid(packed))] = (
            ids.character_name("blackwing_descent", boss["name_code"], "10N", 0, slot), spec)
    assert {guid: (row["name"], row["spec"]) for guid, row in target["roster"].items()} == expected
    roles = [row["role"] for row in target["roster"].values()]
    assert (roles.count("tank"), roles.count("healer"), roles.count("dps")) == (2, 3, 5)


def test_raid_target_reads_through_the_scoreboard_with_declared_gaps() -> None:
    target = scoreboard_core.load_target(ROOT, "blackwing_descent_10n_chimaeron")
    references = scoreboard_core.reference_targets(ROOT, target)
    declared = target["reference_status"]
    for spec in declared["no_reference_until_wcl"]:
        assert spec not in references
    for spec in declared["wowsims_fallback_available"]:
        assert references[spec]["basis"] == "wowsims_fallback"
    for spec, dps in declared["wcl_matched"].items():
        assert references[spec] == {"dps": pytest.approx(dps), "basis": "wcl", "ratio": 0.95}
    assert not declared["wowsims_fallback_available"]
    assert {spec: references[spec]["dps"] for spec in declared["wcl_matched"]} == pytest.approx({
        "blood_death_knight": 15316.5, "survival_hunter": 26254.9, "fire_mage": 24654.6,
        "retribution_paladin": 26133.6, "assassination_rogue": 26350.7, "demonology_warlock": 23443.3})
    raid_dps = sorted(row["raid_dps"] for row in load(WCL_REFERENCE)["references"])
    assert scoreboard_core.party_reference_dps(ROOT, target) == pytest.approx(raid_dps[len(raid_dps) // 2])


def test_dossier_discloses_sources_state_and_strategy() -> None:
    text = DOSSIER.read_text(encoding="utf-8")
    lowered = text.lower()
    for needle in ("4.4.2", "fidelity_blocked", "unresolved", "wowhead.com", "icy-veins.com", "repository",
                   "gossip_select_sequence", "Burn window", "Taunt exchange", "235,200", "20,699,972"):
        assert needle.lower() in lowered, needle


def test_native_script_repairs_are_in_place() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    initialize = function_body(source, "void Initialize()")
    for field in ("_massacresInCycle = 0;", "_killedPlayerCount = 0;", "_isInFeud = false;"):
        assert field in initialize
    reset = function_body(source, "void Reset() override")
    assert "Initialize();" in reset and "SetMortalityTauntImmunity(false);" in reset
    damage = function_body(source, "void DamageTaken(Unit* /*attacker*/, uint32& damage) override")
    assert "SetMortalityTauntImmunity(true);" in damage
    immunity = function_body(source, "void SetMortalityTauntImmunity(bool apply)")
    assert "IMMUNITY_EFFECT, SPELL_EFFECT_ATTACK_ME, apply" in immunity
    assert "IMMUNITY_STATE, SPELL_AURA_MOD_TAUNT, apply" in immunity
    evade = function_body(source, "void EnterEvadeMode(EvadeReason /*why*/) override")
    assert "SetMortalityTauntImmunity(false);" in evade
    engage = function_body(source, "void JustEngagedWith(Unit* who) override")
    assert "_killedPlayerCount = 0;" in engage
    # WCL 10N: the first Caustic Slime impacts land at 17.2 s (15 s cast + flight).
    assert "events.ScheduleEvent(EVENT_CAUSTIC_SLIME, 15s, 0, PHASE_1);" in engage
    # WCL 10N (three kills, ten Massacre cycles): two Slime volleys per cycle, about 6 s apart.
    # 10N only: the other modes keep the 5 s repeat (test_chimaeron_mode_gating.py).
    assert "events.Repeat(Logic::CausticSlimeRepeatMs(IsTenNormal()));" in source
    assert "events.Repeat(5s);" not in source
    # Feud pacifies his melee: on 10N no Break or Double Attack while it lasts (WCL: no Double Attack
    # application inside either observed 30 s Feud window); the timers keep running.
    update = function_body(source, "void UpdateAI(uint32 diff) override")
    for cast in ("DoCastVictim(SPELL_BREAK);", "DoCastSelf(SPELL_DOUBLE_ATTACK, true);"):
        guard = update.index(cast)
        assert "if (!Logic::SkipsBreakAndDoubleAttack(IsTenNormal(), _isInFeud))" in update[guard - 120:guard], cast
    timer = function_body(source, "uint32 GetTimeUntilEncounterMechanic(uint32 spellId) const override")
    assert "spellId != SPELL_MASSACRE" in timer
    assert "events.GetTimeUntilEvent(EVENT_MASSACRE)" in timer
    assert "Logic::MassacreRemainingMs(" in timer
    slime = function_body(source, "void FilterTargets(std::list<WorldObject*>& targets)")
    assert "unit == victim" in slime and "HasAura(SPELL_BREAK)" in slime
    assert "Logic::PlanCausticSlimeTargets(" in slime
    assert "Chimaeron no longer casts" in (SCRIPT.parent / "boss_chimaeron_logic.h").read_text(encoding="utf-8")
    # Uninitialized helper members are gone.
    assert re.search(r"uint8 _killedPlayerCount = 0;", source)
    assert len(source.splitlines()) < 1000
