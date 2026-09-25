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
    assert {entry["key"] for entry in ledger["unresolved"]} == set(contract["unresolved"])
    assert ledger["fidelity_state"] == contract["fidelity_state"] == "fidelity_blocked"
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
    assert completion["wcl_dps_references"] == "blocked"
    assert completion["boss_melee_damage_modifier_10n"] == "blocked"
    assert ledger["acceptance_observations"]


def test_wcl_placeholders_carry_no_measured_value() -> None:
    dps, casts = load(WCL_DPS), load(WCL_CASTS)
    assert dps["status"] == casts["status"] == "pending_extraction"
    assert dps["references"] == [] and casts["actors"] == []
    plan = dps["extraction_plan"]
    assert {"summary", "casts", "boss_casts", "boss_melee", "health"} <= set(plan["views"])
    assert plan["candidate_reports_to_open_first"]
    for spec in ("blood_death_knight", "beast_mastery_hunter"):
        assert spec in plan["wanted_specs"]


def test_raid_target_is_scoreboard_loadable_and_honest() -> None:
    from tools.raid_program import scoreboard_core

    target = scoreboard_core.load_target(ROOT, "blackwing_descent_10n_atramedes")
    assert target["matched_reference_ids"] == []
    assert (ROOT / target["wcl_reference_manifest"]).is_file()
    assert "wcl_cast_timelines" not in target  # added only once actors exist
    references = scoreboard_core.reference_targets(ROOT, target)
    assert all(ref["basis"] == "wowsims_fallback" for ref in references.values())
    assert "blood_death_knight" not in references and "beast_mastery_hunter" not in references
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
