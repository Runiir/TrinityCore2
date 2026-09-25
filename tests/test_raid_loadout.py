from __future__ import annotations

import copy
import json
import re
from collections import Counter
from pathlib import Path

import pytest

from tests.test_raid_shard_plan import _plan
from tools.bot_ml.build_validation_provisioning import (
    build_character_insert_sql,
    gem_item_enchant_map,
    load_config_with_bwd_diagnostic_shards,
    bot_primary_tree_spell_ids,
)
from tools.raid_program.raid_loadout import (
    LoadoutError,
    expected_inventory,
    item_tables,
    loadout_failures,
    materialize_loadout,
)
from tools.raid_program.raid_loadout_sql import (
    _cleanup_preamble,
    build_raid_shard_character_sql,
    loadout_equipment_cache,
    prepare_config,
)

ROOT = Path(__file__).resolve().parents[1]
DBC = ROOT / "data/dbc/enUS"
GEAR = ROOT / "dataset/validation_gear_profiles/profiles.json"
SOURCE_INDEX = ROOT / "dataset/world_planner/item_source_index.jsonl"
MAGMAW = "blackwing_descent_10n_magmaw_c0_diagnostic"
CHIMAERON = "blackwing_descent_10n_chimaeron_c0_diagnostic"

pytestmark = pytest.mark.skipif(not GEAR.is_file() or not (DBC / "Item-sparse.db2").is_file(),
                                reason="DVC gear profiles or client DBCs not hydrated")


@pytest.fixture(scope="module")
def config() -> dict:
    return prepare_config(_plan(), GEAR, DBC, [MAGMAW, CHIMAERON])


def _bot(config: dict, scenario_id: str, key: str) -> dict:
    scenario = next(row for row in config["scenarios"] if row["id"] == scenario_id)
    return next(bot for bot in scenario["bots"] if bot["character_key"] == key)


def _identities(bot: dict) -> Counter:
    gems = gem_item_enchant_map(DBC)
    return Counter((row["item_id"], row["enchantments"]) for row in expected_inventory(bot, [], gems, DBC)
                   if row["kind"] in ("equipped", "bagged"))


def test_druid_copies_own_identical_items_whichever_spec_is_active(config):
    balance = _bot(config, MAGMAW, "druid")
    feral = _bot(config, CHIMAERON, "druid")
    assert (balance["class_spec"], feral["class_spec"]) == ("balance_druid", "feral_druid_tank")
    assert _identities(balance) == _identities(feral)
    offsets = lambda bot: [row["offset"] for row in bot["loadout"]["physical_items"]]
    assert offsets(balance) == offsets(feral) == list(range(1, 33))
    assert balance["loadout"]["spec_gear_sets"] == feral["loadout"]["spec_gear_sets"]


def test_active_group_is_equipped_and_the_other_set_is_bagged(config):
    feral = _bot(config, CHIMAERON, "druid")
    loadout = feral["loadout"]
    assert loadout["active_talent_group"] == 1
    equipped = set(loadout["spec_gear_sets"][1].values())
    assert set(loadout["equipped_offsets"]) == equipped
    bagged = [row["offset"] for row in loadout["bag_contents"]]
    assert set(bagged) == set(loadout["spec_gear_sets"][0].values()) - equipped
    assert [row["bag_slot_index"] for row in loadout["bag_contents"]] == list(range(len(bagged)))
    assert 0 < len(bagged) <= loadout["bag"]["container_slots"]
    rows = expected_inventory(feral, [], gem_item_enchant_map(DBC), DBC)
    bag = next(row for row in rows if row["kind"] == "bag")
    assert (bag["bag"], bag["slot"], bag["item_id"]) == (0, 19, 38082)
    assert {row["bag"] for row in rows if row["kind"] == "bagged"} == {bag["item_guid"]}
    assert {row["slot"] for row in rows if row["kind"] == "equipped"} == {int(item["slot"]) for item in feral["equipment"]}
    assert all(row["item_guid"] // 100 == loadout["item_guid_base"] // 100 for row in rows)


def test_single_spec_character_keeps_an_empty_bag_and_mirrored_groups(config):
    mage = _bot(config, CHIMAERON, "mage")
    assert mage["loadout"]["bag_contents"] == []
    assert mage["loadout"]["groups"][1]["mirrors_talent_group"] == 0
    assert mage["loadout"]["active_talent_group"] == 0


def test_spellbook_holds_active_specialization_and_both_baselines(config):
    for scenario_id, active_index in ((MAGMAW, 0), (CHIMAERON, 1)):
        druid = _bot(config, scenario_id, "druid")
        groups = druid["loadout"]["groups"]
        active, other = groups[active_index], groups[1 - active_index]
        known = set(druid["loadout"]["known_spell_ids"])
        specialization = lambda group: {int(t["spell_id"]) for t in group["talents"]} | set(bot_primary_tree_spell_ids(group))
        assert specialization(active) <= known
        assert not (specialization(other) - specialization(active)) & known
        assert set(druid["loadout"]["inactive_only_specialization_spell_ids"]) == specialization(other) - specialization(active)


def test_both_specs_profession_requirements_are_provisioned(config):
    druid = _bot(config, CHIMAERON, "druid")
    union = {row["native_skill_id"] for row in druid["loadout"]["profession_setup_union"]["requirements"]}
    assert union <= {int(skill["id"]) for skill in druid["skills"]}
    assert 197 in union  # Balance Lightweave stays usable while Feral is active.


def _statements(sql: str, name: str) -> list[str]:
    return [line for line in sql.splitlines() if f"'{name}'" in line and line.startswith("INSERT")]


def test_sql_writes_both_groups_and_real_container_rows(config):
    sql = build_raid_shard_character_sql(config, DBC)
    feral = _bot(config, CHIMAERON, "druid")
    rows = _statements(sql, feral["name"])
    character = next(row for row in rows if row.startswith("INSERT INTO `characters`.`characters` "))
    assert ", 2, 1, '752 750 ', " in character
    assert loadout_equipment_cache(feral).endswith(" 38082 0 0 0 0 0 0 0 ")
    talents = [row for row in rows if "`character_talent`" in row]
    for group in feral["loadout"]["groups"]:
        assert sum(row.endswith(f", {group['talent_group']} FROM `characters`.`characters` c WHERE c.`name` = '{feral['name']}';")
                   for row in talents) == len(group["talents"])
    assert len([row for row in rows if "`character_glyphs`" in row]) == 2
    bag_guid = feral["loadout"]["item_guid_base"]
    inventory = [row for row in rows if "`character_inventory`" in row]
    assert sum(f"SELECT c.`guid`, {bag_guid}, " in row for row in inventory) == len(feral["loadout"]["bag_contents"])
    assert sum(f"SELECT c.`guid`, 0, 19, {bag_guid} " in row for row in inventory) == 1
    pool = next(row for row in rows if "`character_bot_pool`" in row)
    assert "'tank', 'feral_druid_tank', 1, 0, 'blackwing_descent_10n_chimaeron_c0_diagnostic'" in pool
    assert sql.rstrip().endswith(f"'{MAGMAW}', '{CHIMAERON}');")


def _columns(sql: str) -> dict[str, str]:
    columns = {}
    for line in sql.splitlines():
        match = re.match(r"INSERT INTO `characters`\.`(\w+)` (\([^)]*\))", line)
        if match:
            columns.setdefault(match[1], match[2])
    return columns


def test_insert_column_lists_match_the_legacy_writer(config):
    legacy_config = load_config_with_bwd_diagnostic_shards(
        ROOT / "experiments/configs/validation_provisioning_cata_001.json",
        ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json")
    legacy = _columns(build_character_insert_sql(legacy_config, scenario_ids=["blackwing_descent_10n_magmaw_diagnostic"]))
    new = _columns(build_raid_shard_character_sql(config, DBC))
    assert set(legacy) <= set(new)
    for table, columns in legacy.items():
        assert new[table] == columns, table


def test_cleanup_preamble_is_the_legacy_writer_cleanup(config):
    lines = _cleanup_preamble(config)
    names = [bot["name"] for scenario in config["scenarios"] for bot in scenario["bots"]]
    assert lines[1].startswith("-- Review before applying")
    assert all(f"'{name}'" in lines[2] for name in names)
    assert any(line.startswith("DELETE FROM `characters`.`character_pet` WHERE `owner`") for line in lines)
    assert not any(line.startswith("INSERT INTO `characters`.`characters` ") for line in lines)


def test_loadout_defects_fail_closed(config):
    tables = item_tables(DBC)
    druid = copy.deepcopy(_bot(config, CHIMAERON, "druid"))
    small = copy.deepcopy(druid)
    small["loadout"]["bag"]["container_slots"] = 4
    assert "bag_capacity" in {row["check"] for row in loadout_failures(small, tables)}
    wrong_bag = copy.deepcopy(druid)
    wrong_bag["loadout"]["bag"]["item_id"] = int(druid["equipment"][0]["item_id"])
    assert "bag_not_generic_container" in {row["check"] for row in loadout_failures(wrong_bag, tables)}
    duplicated = Counter(int(row["item"]["item_id"]) for row in druid["loadout"]["physical_items"])
    item_id = next(item for item, count in duplicated.items() if count > 1)
    unique_tables = copy.deepcopy(tables)
    unique_tables["items"][item_id]["max_count"] = 1
    assert "unique_item_duplicated_across_specs" in {row["check"] for row in loadout_failures(druid, unique_tables)}


def test_active_equipment_must_match_the_selected_spec_profile(config):
    from tools.bot_ml.build_validation_provisioning import load_gear_profiles
    druid = copy.deepcopy(_bot(config, CHIMAERON, "druid"))
    druid["equipment"] = druid["equipment"][1:]
    with pytest.raises(LoadoutError, match="active_group_equipment_drift"):
        materialize_loadout(druid, load_gear_profiles(GEAR, dbc_dir=DBC), DBC)


def test_scoped_cohort_sql_keeps_fixed_item_guids_and_names(config, tmp_path):
    from tools.raid_program.raid_loadout_sql import scoped_provisioning_sql
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(_plan()), encoding="utf-8")
    scoped = scoped_provisioning_sql(plan_path, [CHIMAERON], GEAR, DBC)
    assert scoped["scenario_ids"] == [CHIMAERON]
    full = build_raid_shard_character_sql(config, DBC)
    feral = _bot(config, CHIMAERON, "druid")
    item_rows = lambda sql: sorted(line for line in _statements(sql, feral["name"]) if "`item_instance`" in line)
    assert item_rows(scoped["character_sql"]) == item_rows(full)
    magmaw_names = {bot["name"] for bot in next(s for s in config["scenarios"] if s["id"] == MAGMAW)["bots"]}
    assert not any(f"'{name}'" in scoped["character_sql"] for name in magmaw_names)
    assert scoped["account_sql"].count("INSERT INTO `auth`.`account`") == 10


@pytest.mark.skipif(not SOURCE_INDEX.is_file(), reason="world planner item source index not hydrated")
def test_off_spec_bag_has_a_retained_player_acquisition_record():
    composition = json.loads((ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json").read_text())
    bag = composition["off_spec_bag"]
    facts = item_tables(DBC)["items"][bag["item_id"]]
    assert (facts["class"], facts["subclass"], facts["inventory_type"], facts["container_slots"]) == (1, 0, 18, 22)
    wanted = f'{{"item_id": {bag["item_id"]},'
    with SOURCE_INDEX.open(encoding="utf-8") as handle:
        row = next(json.loads(line) for line in handle if line.startswith(wanted))
    assert any(source["source_type"] == bag["acquisition"]["source_type"]
               and source["source_entry"] == bag["acquisition"]["source_entry"]
               and not source.get("reference") for source in row["sources"])
