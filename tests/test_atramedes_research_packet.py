"""Data checks for the Atramedes (BWD) research packet, WCL placeholders, raid
target and staged SQL.

Nothing here reads WCL: the reference files must stay honest placeholders
(no measured value) until a report page is actually extracted.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BWD = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent"
LEDGER = BWD / "atramedes_ledger_v1.json"
CONTRACT = BWD / "atramedes_v1.json"
WCL_DPS = BWD / "atramedes_wcl_dps_reference_v1.json"
WCL_CASTS = BWD / "atramedes_wcl_cast_timelines_v1.json"
TARGET = ROOT / "experiments/configs/raid_targets/blackwing_descent_10n_atramedes.json"
CATALOG = ROOT / "experiments/configs/cata_raid_strategy_catalog_v1.json"
DOSSIER = ROOT / "docs/bot_raids/strategies/t11/blackwing_descent/atramedes.md"
SQL = ROOT / "sql/custom/world/2026_09_25_40_atramedes_devastation_noisy_target.sql"
COMPOSITION = ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"
PREREQUISITES = ROOT / "experiments/configs/raid_prerequisites/blackwing_descent.json"

DEVASTATION_IDS = (78868, 92460, 92461, 92462)
ROUND2_KILLS = ("PpFW3bgy7m6Kxk1t-fight8", "Bgcm6RavhWK7DLd1-fight34", "hxz7MH8gW9BYGNdr-fight41",
                "jxNrbDtq9BdwAcam-fight30", "X7tWdbvxYn3MjACD-fight28")
# Round 3 (2026-09-30, tier-11 phase gear): the in-band gap-fill kill.
ROUND3_KILLS = ("9Rdhq6BkMXKNw3CP-fight13",)
NOISY = 78897


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_ledger_and_contract_agree_with_the_catalog() -> None:
    ledger, contract = load(LEDGER), load(CONTRACT)
    row = next(r for r in load(CATALOG)["raids"]["blackwing_descent"]["bosses"]
               if r["boss_slug"] == "atramedes")
    assert ledger["unresolved_material_count"] == len(ledger["unresolved"]) \
        == row["ledger_unresolved_material_count"]
    assert contract["unresolved_material_count"] == len(contract["unresolved"]) \
        == row["contract_unresolved_material_count"]
    assert [(entry["key"], entry["modes"]) for entry in ledger["unresolved"]] \
        == [(entry["key"], entry["modes"]) for entry in contract["unresolved"]]
    assert ledger["fidelity_state"] == contract["fidelity_state"] == "fidelity_blocked"
    # Per-mode gate: the Sonar Bomb count, which WCL cannot observe (round 3,
    # 2026-09-30), was the last claim covering 10N; the user decision "Switch to 3"
    # closed it for 10N. The resolved 10N claims and the count keep their other
    # modes open, so 10N is accepted and 10H, 25N and 25H stay blocked.
    assert ledger["fidelity_state_by_mode"] == contract["fidelity_state_by_mode"] == {
        "10N": "accepted", "10H": "fidelity_blocked", "25N": "fidelity_blocked", "25H": "fidelity_blocked"}
    covering_10n = [entry["key"] for entry in contract["unresolved"] if "10N" in entry["modes"]]
    assert covering_10n == []
    sonar = {entry["key"]: entry["modes"] for entry in contract["unresolved"]}["sonar_bomb_count_by_mode"]
    assert sonar == ["10H", "25N", "25H"]
    resolved = {row["key"]: row for row in ledger["resolved_claims"]}
    assert {"ground_air_phase_timestamps_10n", "breath_initial_target_rule_10n",
            "breath_speed_scaling_with_sound_10n", "sonar_bomb_count_by_mode_10n"} <= set(resolved)
    assert resolved["sonar_bomb_count_by_mode_10n"]["status"] == "resolved_by_user_decision"
    from tools.raid_program.raid_program_inputs import mode_scoped_research_state
    assert mode_scoped_research_state(ROOT, contract, None, "10N") == ("accepted", None)
    for mode in ("10H", "25N", "25H"):
        assert mode_scoped_research_state(ROOT, contract, None, mode)[0] == "fidelity_blocked"
    assert "wcl_atramedes_10n_air_20260930" in ledger["source_catalog"]
    assert ledger["fidelity_target"]["build"] == "4.4.2.59185"


def test_ledger_resolves_client_values_and_records_the_native_audit() -> None:
    ledger = load(LEDGER)
    values = {row["key"]: row for row in ledger["client_spell_values"]}
    for key in ("sound_bar", "sonar_pulse_disk", "modulation", "sonic_breath", "searing_flame",
                "roaring_flame_patch", "roaring_flame_breath_air", "sonar_bomb_air",
                "devastation", "shield_strike", "noisy"):
        assert key in values
    assert "no Sound in normal" in values["modulation"]["value"]
    audit = {row["key"]: row["status"] for row in ledger["native_audit"]["findings"]}
    assert audit["module_size"] == "fixed"
    assert audit["sound_bar_persists_after_attempt"] == "fixed"
    assert audit["intro_vertigo_resume"] == "fixed"
    assert audit["devastation_targets_raid"] == "promoted"
    completion = {row["key"]: row["status"] for row in ledger["research_completion"]}
    assert completion["wcl_dps_references"] == "resolved"
    assert completion["boss_melee_damage_modifier_10n"] == "resolved"
    assert completion["boss_health_10n"] == "resolved"
    assert ledger["acceptance_observations"]


def test_wcl_references_are_the_extracted_10n_kills() -> None:
    dps, casts = load(WCL_DPS), load(WCL_CASTS)
    assert dps["status"] == casts["status"] == "extracted"
    references = {ref["id"]: ref for ref in dps["references"]}
    assert set(references) == {"MxFq7TRbvnjGY1hJ-fight32", *ROUND2_KILLS, *ROUND3_KILLS}
    matched = references["MxFq7TRbvnjGY1hJ-fight32"]
    assert matched["mode"] == "10N" and matched["duration_sec"] == 165.6
    # Active tank only (the off-tank is excluded); Survival is the median of two hunters.
    assert matched["actor_dps"]["blood_death_knight"] == 13254
    assert matched["actor_dps"]["survival_hunter"] == 25513.05
    # Tier-11 band (user decision 2026-09-30): every reference is in 352-366;
    # the 401.4 short kill is dropped, never a target.
    band = dps["item_level_band"]
    assert (band["min"], band["max"]) == (352.0, 366.0)
    for ref in references.values():
        assert band["min"] <= ref["item_level"] <= band["max"] and ref["in_item_level_band"], ref["id"]
        assert ref["after_hotfix_cutoff_2025_02_20"] is False, ref["id"]
    assert [ref["id"] for ref in dps["dropped_references"]] == ["xAhkN2y9YP3KRmnJ-fight17"]
    gap = references["9Rdhq6BkMXKNw3CP-fight13"]
    assert gap["actor_dps"] == {"survival_hunter": 25762.0, "elemental_shaman": 27488.0}
    assert gap["phase_coverage"]["full_air_phase"] and gap["duration_sec"] == 180.0
    # Round 2: five full-cycle 10N kills that field the specs fight 32 lacks.
    for ref_id in ROUND2_KILLS:
        ref = references[ref_id]
        assert ref["mode"] == "10N" and ref["duration_sec"] >= 130, ref_id
        assert len(ref["roster"]) == 10, ref_id
        assert 350 <= ref["average_item_level"] <= 372, ref_id
        for spec in ("balance_druid", "assassination_rogue", "demonology_warlock"):
            assert spec in ref["actor_dps"], (ref_id, spec)
        healers = {row["spec"] for row in ref["roster"] if row["role"] == "healer"}
        assert not healers & set(ref["actor_dps"]), ref_id
    assert casts["reference_id"] == "MxFq7TRbvnjGY1hJ-fight32"
    assert len(casts["actors"]) == 8
    assert all(actor["complete"] and actor["row_count"] == len(actor["casts"]) for actor in casts["actors"])
    plan = dps["extraction_plan"]
    assert {"summary", "casts", "boss_casts", "boss_melee", "health"} <= set(plan["views"])
    assert plan["candidate_reports_to_open_first"]
    for spec in ("blood_death_knight", "survival_hunter"):
        assert spec in plan["wanted_specs"]
    # The canonical hunter is Survival (user decision 2026-09-26).
    assert "beast_mastery_hunter" not in plan["wanted_specs"]


def test_raid_target_is_scoreboard_loadable_and_honest() -> None:
    from tools.raid_program import scoreboard_core

    target = scoreboard_core.load_target(ROOT, "blackwing_descent_10n_atramedes")
    assert target["matched_reference_ids"] == ["MxFq7TRbvnjGY1hJ-fight32", *ROUND2_KILLS, *ROUND3_KILLS]
    item_levels = target["reference_item_level"]["reference_raid_item_levels"]
    assert list(item_levels) == target["matched_reference_ids"]
    assert all(352.0 <= value <= 366.0 for value in item_levels.values())
    assert (ROOT / target["wcl_reference_manifest"]).is_file()
    assert (ROOT / target["wcl_cast_timelines"]).is_file()
    references = scoreboard_core.reference_targets(ROOT, target)
    # Every canonical non-healer spec is judged against the median of the matched WCL kills.
    expected = {"blood_death_knight": 13292.75, "balance_druid": 18355.0, "survival_hunter": 21609.55,
                "fire_mage": 18718.9, "retribution_paladin": 19929.9, "assassination_rogue": 17469.4,
                "elemental_shaman": 24949.4, "demonology_warlock": 20626.1}
    for spec, dps in expected.items():
        assert references[spec]["basis"] == "wcl", spec
        assert references[spec]["dps"] == pytest.approx(dps), spec
    assert target["reference_status"]["wcl_matched"] == expected
    assert target["reference_status"]["wowsims_fallback_available"] == []
    assert target["roster"]["11003003"]["spec"] == "survival_hunter"
    # Every non-healer roster spec now has a target.
    for actor in target["roster"].values():
        if actor["role"] != "healer":
            assert actor["spec"] in references, actor
    assert target["encounter_route_node_id"] == "bwd.atramedes.encounter"
    assert target["lockout"]["precompleted_boss_keys"] == ["magmaw", "omnotron"]
    assert target["run_plan"]["requires_seeded_lockout"] is True
    assert "300" not in " ".join(target["run_plan"]["argv_template"])


def test_raid_target_roster_is_the_canonical_c0_shard() -> None:
    from tools.raid_program import raid_shard_plan

    plan = raid_shard_plan.build_shard_plan(load(COMPOSITION), load(PREREQUISITES),
                                            boss_keys=["atramedes"])
    shard = plan["shards"][0]
    target = load(TARGET)
    assert shard["cohort_id"] == target["cohort_id"]
    assert shard["scenario_id"] == target["validation_scenario_id"]
    expected = {str(bot["character_guid"]): {"name": bot["name"], "spec": bot["class_spec"],
                                             "role": bot["role"]} for bot in shard["bots"]}
    assert target["roster"] == expected
    assert shard["role_counts"] == {"tank": 1, "healer": 2, "dps": 7}
    assert shard["lockout"]["precompleted_boss_keys"] == target["lockout"]["precompleted_boss_keys"]


def test_native_melee_roll_at_modifier_one() -> None:
    # gt_npc_damage_by_class_exp3[88].Warrior, creature_classlevelstats(88,1).attackpower,
    # creature_template 41442 BaseAttackTime 1500, BaseVariance 1 (TDB 434.22011).
    base, attack_power, attack_time = 2947.9421, 1226, 1.5
    low = (base + attack_power / 14) * attack_time
    high = (base * 1.5 + attack_power / 14) * attack_time
    assert round(low, 1) == 4553.3 and round(high, 1) == 6764.2
    completion = {row["key"]: row["known"] for row in load(LEDGER)["research_completion"]}
    assert "4,553.3-6,764.2" in completion["boss_melee_damage_modifier_10n"]


def _statements(sql: str, reverse: bool) -> str:
    if reverse:
        block = sql[sql.index("-- BEGIN REVERSE MIGRATION"):sql.index("-- END REVERSE MIGRATION")]
        return "\n".join(line.lstrip("- ").rstrip() for line in block.splitlines()[1:])
    return "\n".join(line for line in sql.splitlines() if not line.lstrip().startswith("--"))


@pytest.fixture()
def conditions() -> sqlite3.Connection:
    db = sqlite3.connect(":memory:")
    db.execute("""CREATE TABLE `conditions` (
        `SourceTypeOrReferenceId` INT, `SourceGroup` INT, `SourceEntry` INT, `SourceId` INT,
        `ElseGroup` INT, `ConditionTypeOrReference` INT, `ConditionTarget` INT,
        `ConditionValue1` INT, `ConditionValue2` INT, `ConditionValue3` INT,
        `NegativeCondition` INT, `ErrorType` INT, `ErrorTextId` INT, `ScriptName` TEXT,
        `Comment` TEXT,
        PRIMARY KEY (`SourceTypeOrReferenceId`, `SourceGroup`, `SourceEntry`, `SourceId`,
            `ElseGroup`, `ConditionTypeOrReference`, `ConditionTarget`, `ConditionValue1`,
            `ConditionValue2`, `ConditionValue3`))""")
    # Existing TDB rows for other Atramedes spells must survive both directions.
    db.execute("INSERT INTO `conditions` VALUES (13,1,78098,0,0,31,0,3,41879,0,0,0,0,'',"
               "'Sonic Breath - Target Tracking Flames')")
    return db


def test_devastation_condition_is_idempotent_and_reversible(conditions: sqlite3.Connection) -> None:
    sql = SQL.read_text(encoding="utf-8")
    forward = _statements(sql, reverse=False)
    conditions.executescript(forward)
    conditions.executescript(forward)
    rows = conditions.execute(
        "SELECT SourceEntry, SourceGroup, ConditionTypeOrReference, ConditionValue1, ConditionValue2,"
        " NegativeCondition FROM conditions WHERE SourceEntry <> 78098 ORDER BY SourceEntry").fetchall()
    assert rows == [(entry, 1, 1, NOISY, 0, 0) for entry in DEVASTATION_IDS]
    conditions.executescript(_statements(sql, reverse=True))
    assert conditions.execute("SELECT SourceEntry FROM conditions").fetchall() == [(78098,)]
    # Only conditions change: no spell value, template or script binding is touched.
    assert not re.search(r"\b(UPDATE|spell_dbc|spelleffect_dbc|creature_template)\b", forward)


def test_dossier_carries_the_superseding_claims() -> None:
    text = DOSSIER.read_text(encoding="utf-8")
    for fragment in ("4.4.2", "fidelity_blocked", "wowhead.com", "icy-veins.com", "repository",
                     "Sound Bar and Noisy! are removed on evade and on death",
                     "2026_09_25_40_atramedes_devastation_noisy_target.sql",
                     "human-verification interstitial"):
        assert fragment in text, fragment


def test_sonar_bomb_10n_count_follows_the_user_decision() -> None:
    # User decision 2026-09-30, "Switch to 3" (Wowhead 4.4.2: 3 bombs per wave in normal): only the
    # 10N spell (SpellDifficulty row 3155 index 0) changes; 10H keeps 5 and 25-player keeps 12.
    import struct
    data = (ROOT / "data/dbc/enUS/SpellDifficulty.dbc").read_bytes()
    _, count, fields, size, _ = struct.unpack_from("<4s4i", data)
    rows = {row[0]: row[1:] for row in struct.iter_unpack(f"<{fields}i", data[20:20 + count * size])}
    ten_normal, twenty_five_normal, ten_heroic, twenty_five_heroic = rows[3155]
    assert (ten_normal, ten_heroic) == (92526, 92532)
    corrections = (ROOT / "src/server/game/Spells/SpellMgrCorrectionsPart04.cpp").read_text(encoding="utf-8")

    def targets(*spell_ids: int) -> int:
        pattern = (r"ApplySpellFix\(\{\s*" + r",\s*".join(str(spell) for spell in spell_ids)
                   + r",?\s*\},\s*\[\]\(SpellInfo\* spellInfo\)\s*\{\s*spellInfo->MaxAffectedTargets = (\d+);")
        match = re.search(pattern, corrections)
        assert match, spell_ids
        return int(match.group(1))

    assert targets(ten_normal) == 3
    assert targets(ten_heroic) == 5
    assert targets(twenty_five_normal, twenty_five_heroic) == 12
    block = corrections[corrections.index("// Sonar Bomb (10 player normal"):corrections.index("// Roaring Flame Breath")]
    assert "User decision 2026-09-30" in block and "Wowhead 4.4.2" in block
    ledger = load(LEDGER)
    assert ledger["source_catalog"]["user_decision_20260930_atramedes_sonar_bomb_10n"]["quote"] == "Switch to 3"
    assert '"Switch to 3"' in DOSSIER.read_text(encoding="utf-8")


KITER_SOUND_SOURCE = "user_decision_20260930_atramedes_kiter_sound_bound"
KITER_SOUND_QUOTE = ("Bound kiter Sound (Recommended): keep the time-only ramp and add a 10N acceptance rule: "
                     "the tracked kiter stays at 10 Sound or less during the chase")


def test_breath_speed_10n_is_bounded_by_the_user_decision_and_an_acceptance_observation() -> None:
    # Round 3 review (scoreboard/research, item 5): the 10N closure "with bounds" was unsupported, since every
    # measured WCL chase had its kiter at 0-10 Sound. The user decided "Bound kiter Sound" (2026-09-30): the
    # time-only ramp stays, and a 10N kill counts only while the tracked kiter stays at 10 Sound or less.
    ledger, contract = load(LEDGER), load(CONTRACT)
    decision = ledger["source_catalog"][KITER_SOUND_SOURCE]
    assert decision["quote"] == KITER_SOUND_QUOTE and decision["accessed"] == "2026-09-30"
    assert "breath_speed_scaling_with_sound (10N)" in decision["used_for"]
    claims = {row["key"]: row for row in ledger["unresolved"]}
    claim = claims["breath_speed_scaling_with_sound"]
    assert claim["modes"] == ["10H", "25N", "25H"]  # open for every other mode
    assert claim["status"] == "resolved_10n_by_user_bound_other_modes_unobserved"
    assert KITER_SOUND_SOURCE in claim["evidence_gap"] and KITER_SOUND_QUOTE in claim["evidence_gap"]
    assert "0-10 Sound" in claim["evidence_gap"]  # the measured range the bound keeps acceptance inside
    assert {row["key"]: row["status"] for row in contract["unresolved"]}["breath_speed_scaling_with_sound"] \
        == claim["status"]
    resolved = {row["key"]: row for row in ledger["resolved_claims"]}["breath_speed_scaling_with_sound_10n"]
    assert resolved["status"] == "resolved_by_user_decision" and KITER_SOUND_SOURCE in resolved["evidence_gap"]
    observation = [row for row in ledger["acceptance_observations"] if row.startswith("Kiter Sound bound (10N;")]
    assert len(observation) == 1 and "10 Sound or less" in observation[0]
    assert "encounter_observations.atramedes" in observation[0] and "samples_above_10 0" in observation[0]
    assert "air_kiter_sound_at_most_10_during_chase" in contract["gates"]
    completion = {row["key"]: row for row in ledger["research_completion"]}["air_breath_target_and_speed_10n"]
    assert KITER_SOUND_SOURCE in completion["source_refs"]
    assert ledger["fidelity_state_by_mode_note"] == contract["fidelity_state_by_mode_note"]
    assert "Bound kiter Sound" in contract["fidelity_state_by_mode_note"]
    dossier = DOSSIER.read_text(encoding="utf-8")
    assert KITER_SOUND_QUOTE in dossier.replace("\n  ", " ") and KITER_SOUND_SOURCE in dossier
    assert "## Round 3 fix: the kiter Sound bound (user decision 2026-09-30)" in dossier


DODGE_SOURCE = "user_raid_experience_20260930_atramedes_dodge"
DODGE_QUOTE = ("For atramedes ideally everyone is as close to 0 sound as possible, meaning the bots dodge "
               "everything.")


def test_raid_wide_dodge_tactic_is_recorded_with_its_source() -> None:
    # User tactic (2026-09-30, authoritative): every bot, in both phases, avoids every avoidable Sound source.
    ledger, contract = load(LEDGER), load(CONTRACT)
    source = ledger["source_catalog"][DODGE_SOURCE]
    assert source["quote"] == DODGE_QUOTE and source["accessed"] == "2026-09-30"
    assert source["source_label"] == "user raid experience 2026-09-30"
    assert "Modulation adds no Sound" in source["supporting_source"]
    observation = [row for row in ledger["acceptance_observations"] if row.startswith("Raid-wide Sound (10N;")]
    assert len(observation) == 1 and DODGE_SOURCE in observation[0] and DODGE_QUOTE in observation[0]
    assert "tests/test_atramedes_raid_sound.py" in observation[0]
    completion = {row["key"]: row for row in ledger["research_completion"]}["bot_strategy_obligations"]
    assert DODGE_SOURCE in completion["source_refs"] and "130k raid-DPS floor" in completion["known"]
    assert DODGE_SOURCE in contract["tactics_sources"] and "raid_wide_avoidable_sound_near_zero" in contract["gates"]
    assert any(DODGE_QUOTE in line for line in contract["known_behavior_summary"])
    assert "hold_boss_from_melee_slot_radius_21_58yd_and_dodge_disk_lanes_inside_melee_range" in contract["roles"]["tank"]
    dossier = DOSSIER.read_text(encoding="utf-8")
    assert "## Round 3 fix: everyone dodges everything (user raid experience 2026-09-30)" in dossier
    assert DODGE_QUOTE in dossier.replace("\n> ", " ") and "user raid experience 2026-09-30" in dossier
    # The stale 150k floor is gone from the strategy text (history kept in parentheses).
    assert "At a 150k raid-DPS floor" not in dossier and "At a 130k raid-DPS floor" in dossier
