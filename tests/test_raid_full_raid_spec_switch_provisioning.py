"""Round 10: the canonical full raid switches talent groups per boss, so its characters are provisioned for it.

Only the end-to-end cohort's loadouts carry `runtime_spec_switch` (raid_shard_plan.full_raid_shard): every talent
group's own spells are in the spellbook (a player knows both Faerie Fires), and each talent group's gear is one
native equipment set (character_equipmentsets, setindex = talent group) the runtime equips through
CMSG_EQUIPMENT_SET_USE (BotRaidSpecSwitch.h). Boss shards and legacy rosters stay byte-identical.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tools.raid_program.raid_loadout_spells import loadout_known_spells
from tools.raid_program.raid_shard_scenarios import build_plan

ROOT = Path(__file__).resolve().parents[1]
COMPOSITION = ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"
GEAR = ROOT / "dataset/validation_gear_profiles/profiles.json"
DBC = ROOT / "data/dbc/enUS"
TRAINERS = ROOT / "dataset/world_knowledge/trainers.jsonl"
FULL = "blackwing_descent_10n_full_c0"

pytestmark = pytest.mark.skipif(not (DBC / "Talent.dbc").is_file() or not GEAR.is_file() or not TRAINERS.is_file(),
                                reason="client DBCs, gear profiles or trainers not hydrated")


@pytest.fixture(scope="module")
def plan() -> dict:
    return build_plan(COMPOSITION)


@pytest.fixture(scope="module")
def config(plan) -> dict:
    from tools.raid_program.raid_loadout_sql import prepare_config

    return prepare_config(plan, GEAR, DBC)


def test_only_the_full_raid_loadouts_switch_at_runtime(plan):
    for shard in plan["shards"]:
        flags = {bool(bot["loadout"].get("runtime_spec_switch")) for bot in shard["bots"]}
        assert flags == {shard["shard_kind"] == "full_raid"}, shard["scenario_id"]


def test_the_full_raid_druid_knows_both_groups_own_spells(plan):
    for shard in plan["shards"]:
        druid = next(bot for bot in shard["bots"] if bot["character_key"] == "druid")
        known = set(loadout_known_spells(druid, DBC)["known_spell_ids"])
        feral = {16857, 5229, 22842}
        if shard["shard_kind"] == "full_raid":
            assert {770} | feral <= known  # Faerie Fire for Balance, the Feral tank's upkeep and self-care
        elif druid["class_spec"] == "balance_druid":
            assert 770 in known and not feral & known  # unchanged: group spells only while active
        else:
            assert feral <= known and 770 not in known


def test_each_full_raid_member_gets_one_equipment_set_per_talent_group(config):
    from tools.raid_program.raid_loadout_sql import equipment_set_rows, switches_spec

    for scenario in config["scenarios"]:
        for bot in scenario["bots"]:
            if scenario["id"] != FULL:
                assert not switches_spec(bot)
                continue
            loadout = bot["loadout"]
            rows = equipment_set_rows(bot)
            assert len(rows) == len(loadout["groups"]) == 2
            base = int(loadout["item_guid_base"])
            for row, group, group_set in zip(rows, loadout["groups"], loadout["spec_gear_sets"]):
                values = re.search(r"SELECT c\.`guid`, (\d+), '([a-z_]+)', 'INV_Misc_QuestionMark', (\d+), ([\d, ]+) FROM",
                                   row)
                index, name, mask, items = int(values[1]), values[2], int(values[3]), [
                    int(value) for value in values[4].split(", ")]
                assert (index, name) == (int(group["talent_group"]), group["class_spec"][:31])
                assert items == [base + int(group_set[str(slot)]) if str(slot) in group_set else 0
                                 for slot in range(19)]
                used = set().union(*(set(map(int, other)) for other in loadout["spec_gear_sets"]))
                assert mask == sum(1 << slot for slot in range(19) if slot not in used)
                # Every set item is one of the character's own provisioned physical items.
                physical = {base + int(item["offset"]) for item in loadout["physical_items"]}
                assert {item for item in items if item} <= physical
    druid = next(bot for scenario in config["scenarios"] if scenario["id"] == FULL for bot in scenario["bots"]
                 if bot["character_key"] == "druid")
    assert druid["loadout"]["spec_gear_sets"][0] != druid["loadout"]["spec_gear_sets"][1]  # Balance vs Feral gear


def test_the_full_raid_cohort_sql_clears_and_writes_the_sets_and_boss_cohorts_do_not(plan, config):
    from tools.raid_program.raid_loadout_sql import cohort_sql
    from tools.raid_program.raid_shard_preflight import plan_reservation
    from tools.bot_ml.build_validation_provisioning import gem_item_enchant_map

    reservation, gems = plan_reservation(plan), gem_item_enchant_map(DBC)
    for scenario in config["scenarios"]:
        lines = cohort_sql(config, scenario, reservation, gems, DBC)
        sets = [line for line in lines if "character_equipmentsets" in line]
        if scenario["id"] != FULL:
            assert sets == [], scenario["id"]
            continue
        delete = next(index for index, line in enumerate(lines) if line.startswith(
            "DELETE FROM `characters`.`character_equipmentsets`"))
        characters = next(index for index, line in enumerate(lines) if line.startswith(
            "DELETE FROM `characters`.`characters`"))
        assert delete < characters  # cleared while the character rows still name them
        assert len([line for line in sets if line.startswith("INSERT")]) == 2 * len(scenario["bots"])
