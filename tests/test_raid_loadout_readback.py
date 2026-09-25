from __future__ import annotations

import copy
from pathlib import Path

import pytest

from tests.test_raid_loadout import CHIMAERON, DBC, GEAR, MAGMAW, _bot, config  # noqa: F401 (module fixture)
from tools.bot_ml import validate_validation_provisioning as verifier
from tools.bot_ml.build_validation_provisioning import gem_item_enchant_map
from tools.raid_program.capture_phase1_provisioning_readback import (
    loadout_readback_reasons,
    validate_readback,
)
from tools.raid_program.raid_loadout import (
    expected_glyph_rows,
    expected_inventory,
    expected_talent_rows,
    expected_talent_tree,
)
from tools.raid_program.raid_loadout_readback import loadout_readback_failures
from tools.raid_program.raid_loadout_sql import loadout_equipment_cache

pytestmark = pytest.mark.skipif(not GEAR.is_file() or not (DBC / "Item-sparse.db2").is_file(),
                                reason="DVC gear profiles or client DBCs not hydrated")


def observed_state(bot: dict) -> dict:
    """What a correct DB readback returns for one provisioned loadout bot."""
    gems = gem_item_enchant_map(DBC)
    guid = int(bot["expected_character_guid"])
    return {
        "guid": guid,
        "talent_groups_count": bot["loadout"]["talent_groups_count"],
        "active_talent_group": bot["loadout"]["active_talent_group"],
        "talent_tree": expected_talent_tree(bot),
        "talents": expected_talent_rows(bot),
        "glyphs": {group: slots for group, slots in expected_glyph_rows(bot).items() if any(slots)},
        "known_spells": list(bot["loadout"]["known_spell_ids"]),
        "inventory": [{**row, "owner_guid": guid} for row in expected_inventory(bot, [], gems, DBC)],
    }


def _checks(bot: dict, observed: dict) -> set[str]:
    return {row["check"] for row in loadout_readback_failures(bot, observed, [], gem_item_enchant_map(DBC), DBC)}


def test_exact_loadout_readback_passes_for_either_active_group(config):
    for scenario_id in (MAGMAW, CHIMAERON):
        for key in ("druid", "shaman", "hunter"):
            bot = _bot(config, scenario_id, key)
            assert _checks(bot, observed_state(bot)) == set()


@pytest.mark.parametrize("mutate,check", [
    (lambda o: o.update(active_talent_group=0), "loadout_active_talent_group"),
    (lambda o: o.update(talent_groups_count=1), "loadout_talent_groups_count"),
    (lambda o: o.update(talent_tree="750 752 "), "loadout_talent_tree"),
    (lambda o: o["talents"][1].pop(), "loadout_talent_group_spells"),
    (lambda o: o["talents"].pop(0), "loadout_talent_group_spells"),
    (lambda o: o["glyphs"].pop(1), "loadout_glyph_group"),
    (lambda o: o["glyphs"][0].reverse(), "loadout_glyph_group"),
    (lambda o: o["known_spells"].pop(), "loadout_known_spells_missing"),
    (lambda o: [row for row in o["inventory"] if row["bag"] != 0][0].update(bag=0, slot=30), "loadout_inventory_mismatch"),
    (lambda o: o["inventory"].remove([row for row in o["inventory"] if row["bag"] != 0][0]), "loadout_inventory_missing"),
    (lambda o: o["inventory"].append({"item_guid": 1, "bag": 0, "slot": 23, "item_id": 6948, "owner_guid": o["guid"], "count": 1}), "loadout_inventory_unexpected"),
    (lambda o: [row for row in o["inventory"] if row["bag"] != 0][0].update(owner_guid=30001), "loadout_inventory_mismatch"),
    (lambda o: [row for row in o["inventory"] if row["bag"] != 0][0].update(enchantments="1 " * 45), "loadout_item_modifiers"),
    (lambda o: [row for row in o["inventory"] if row["slot"] == 19 and row["bag"] == 0][0].update(item_id=41599), "loadout_inventory_mismatch"),
    (lambda o: o["known_spells"].remove(63644), "loadout_dual_spec_switch_spells_missing"),
    (lambda o: o["glyphs"].update({2: [0] * 9}), "loadout_glyph_group_beyond_count"),
])
def test_group_one_and_bag_contents_are_read_back_exactly(config, mutate, check):
    bot = _bot(config, CHIMAERON, "druid")
    observed = copy.deepcopy(observed_state(bot))
    mutate(observed)
    assert check in _checks(bot, observed)


def test_missing_glyph_rows_read_back_as_all_zero_groups(config):
    bot = copy.deepcopy(_bot(config, CHIMAERON, "druid"))
    observed = observed_state(bot)
    # Player::_SaveGlyphs writes an all-zero row for a group without glyphs.
    bot["loadout"]["groups"][0]["glyphs"] = []
    observed["glyphs"][0] = [0] * 9
    assert _checks(bot, observed) == set()
    observed["glyphs"].pop(0)
    assert _checks(bot, observed) == set()
    # A group with glyphs must not be missing: group 1 is below talentGroupsCount.
    observed["glyphs"].pop(1)
    assert "loadout_glyph_group" in _checks(bot, observed)


def test_mangle_bear_and_sunfire_are_leak_checked_in_the_readback(config):
    balance = _bot(config, MAGMAW, "druid")
    observed = observed_state(balance)
    observed["known_spells"].append(33878)
    assert "loadout_inactive_group_spells_known" in _checks(balance, observed)
    feral = _bot(config, CHIMAERON, "druid")
    observed = observed_state(feral)
    observed["known_spells"].append(93402)
    assert "loadout_inactive_group_spells_known" in _checks(feral, observed)


def test_inactive_group_specialization_spells_must_not_be_known(config):
    bot = _bot(config, CHIMAERON, "druid")
    observed = observed_state(bot)
    observed["known_spells"].append(bot["loadout"]["inactive_only_spell_ids"][0])
    assert "loadout_inactive_group_spells_known" in _checks(bot, observed)


def test_missing_character_is_reported(config):
    assert _checks(_bot(config, CHIMAERON, "druid"), {}) == {"loadout_character_missing"}


def _legacy_runtime(bot: dict) -> dict:
    gems = gem_item_enchant_map(DBC)
    from tools.bot_ml.build_validation_provisioning import runtime_safe_enchantments
    rows = expected_inventory(bot, bot.get("consumables", []), gems, DBC)
    return {
        "guid": int(bot["expected_character_guid"]), "account_id": int(bot["expected_account_id"]),
        "talentTree": expected_talent_tree(bot), "equipmentCache": loadout_equipment_cache(bot),
        "items": {int(item["slot"]): {"item_id": int(item["item_id"]), "durability": 100,
                                      "enchantments": [int(v) for v in runtime_safe_enchantments(item, gems, DBC).split()]}
                  for item in bot["equipment"]},
        "inventory": {row["slot"]: {"bag": 0, "slot": row["slot"], "item_id": row["item_id"],
                                    "owner_guid": int(bot["expected_character_guid"]), "count": row["count"]}
                      for row in rows if row["bag"] == 0 and row["slot"] >= 19},
        # Legacy group-0 fields: for an active group 1 these are the *inactive* spec.
        "glyphs": expected_glyph_rows(bot)[0],
        "talent_spells": set(expected_talent_rows(bot)[0]),
        "known_spells": set(bot["loadout"]["known_spell_ids"]),
    }


def test_strict_verifier_uses_group_aware_checks_for_loadout_bots(config, monkeypatch):
    bot = copy.deepcopy(_bot(config, CHIMAERON, "druid"))
    single = {**config, "scenarios": [{**config["scenarios"][1], "bots": [bot]}]}
    for name in ("fetch_columns",):
        monkeypatch.setattr(verifier, name, lambda url, table: set().union(*[
            columns for group in verifier.REQUIRED_COLUMNS.values() for t, columns in group.items() if t == table]))
    monkeypatch.setattr(verifier, "database_url_from_worldserver_conf", lambda path, key: "mysql://u:p@h:1/" + key)
    monkeypatch.setattr(verifier, "fetch_existing_values", lambda url, table, column, values: set(values))
    monkeypatch.setattr(verifier, "fetch_runtime_gear", lambda url, names: {bot["name"]: _legacy_runtime(bot)})
    observed = observed_state(bot)
    observed["inventory"] = [{**row, "owner_guid": observed["guid"]} for row in
                             expected_inventory(bot, bot.get("consumables", []), gem_item_enchant_map(DBC), DBC)]
    import tools.raid_program.raid_loadout_readback as readback
    monkeypatch.setattr(readback, "fetch_runtime_loadouts", lambda url, names: {bot["name"]: observed})
    failures, evidence = verifier.validate_database(single, Path("unused.conf"), require_applied=True, dbc_dir=DBC)
    assert failures == []
    assert evidence["runtime_gear"][bot["name"]]["loadout"]["active_talent_group"] == {"expected": 1, "actual": 1}
    observed["talents"][1] = observed["talents"][1][:-1]
    failures, _ = verifier.validate_database(single, Path("unused.conf"), require_applied=True, dbc_dir=DBC)
    assert [row["check"] for row in failures] == ["loadout_talent_group_spells"]


def test_bagged_off_spec_items_get_payload_checks(config):
    bot = _bot(config, CHIMAERON, "druid")
    assert len(verifier.bagged_loadout_items(bot)) == len(bot["loadout"]["bag_contents"])
    broken = copy.deepcopy(bot)
    bagged_offset = broken["loadout"]["bag_contents"][0]["offset"]
    item = next(row["item"] for row in broken["loadout"]["physical_items"] if row["offset"] == bagged_offset)
    item["reforge_id"] = 999999
    failures, _ = verifier.validate_payloads({"scenarios": [{"bots": [broken]}]}, DBC)
    assert "reforge_id" in {row["check"] for row in failures}
    assert verifier.bagged_loadout_items({"name": "legacy"}) == []


def test_phase1_readback_roster_size_follows_the_contract():
    expected = [{"guid": index, "name": f"N{chr(97 + index)}", "role": "dps", "class_spec": "x", "class": 1}
                for index in range(25)]
    reasons = validate_readback(expected, [], start={"map_id": 1, "x": 0, "y": 0, "z": 0, "o": 0},
                                character_instance_rows=0, group_member_rows=0, ghost_aura_rows=0,
                                corpse_rows=0, corpse_phase_rows=0, roster_size=25)
    assert "exact_25_names" in reasons and "exact_ten_names" not in reasons


def test_phase1_readback_adds_loadout_reasons(config):
    bot = _bot(config, CHIMAERON, "shaman")
    contract = {"expected": [bot], "default_consumables": []}
    reasons, failures = loadout_readback_reasons(contract, {bot["name"]: observed_state(bot)}, DBC)
    assert reasons == [] and failures == []
    broken = observed_state(bot)
    broken["active_talent_group"] = 0
    reasons, _ = loadout_readback_reasons(contract, {bot["name"]: broken}, DBC)
    assert reasons == [f"{bot['name']}:loadout_active_talent_group"]


def test_unmodified_plan_config_has_no_payload_failures():
    from tests.test_raid_shard_plan import _plan
    from tools.raid_program.raid_loadout_sql import prepare_config
    full = prepare_config(_plan(), GEAR, DBC)
    assert len(full["scenarios"]) == 6
    failures, evidence = verifier.validate_payloads(full, DBC)
    assert failures == []
    assert evidence["reforge_count"] > 0


def test_positive_phase1_readback_of_a_raid_shard_cohort(config):
    from tools.bot_ml.build_validation_provisioning import VALIDATION_FULL_STAT_SEED
    scenario = next(row for row in config["scenarios"] if row["id"] == CHIMAERON)
    start = scenario["start_position"]
    expected = [{**bot, "guid": bot["expected_character_guid"], "experiment_tags": CHIMAERON} for bot in scenario["bots"]]
    observed = [{
        "guid": bot["expected_character_guid"], "account_id": bot["expected_account_id"],
        "account_registry_id": bot["expected_account_id"], "account": bot["account"], "pool_tag": CHIMAERON,
        "name": bot["name"], "role": bot["role"], "class_spec": bot["class_spec"], "class_id": bot["class"],
        "map_id": start["map_id"], "x": start["x"], "y": start["y"], "z": start["z"], "o": start.get("o", 0.0),
        "online": 0, "enabled": 1, "in_use": 0, "health": VALIDATION_FULL_STAT_SEED,
        "power1": VALIDATION_FULL_STAT_SEED, "character_flags": 0, "at_login": 0, "experiment_tags": CHIMAERON,
    } for bot in scenario["bots"]]
    reasons = validate_readback(expected, observed, start=start, required_roles=scenario["required_roles"],
                                character_instance_rows=0, group_member_rows=0, ghost_aura_rows=0,
                                corpse_rows=0, corpse_phase_rows=0, roster_size=len(expected))
    assert reasons == []
    contract = {"expected": expected, "default_consumables": []}
    loadout_reasons, _ = loadout_readback_reasons(contract, {bot["name"]: observed_state(bot) for bot in expected}, DBC)
    assert loadout_reasons == []
