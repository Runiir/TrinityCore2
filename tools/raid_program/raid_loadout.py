"""Two-spec character loadouts: talent groups, glyph groups and bagged off-spec gear.

Every copy of a composition character owns the same physical items. Items
with an identical entry and modifier payload in both spec gear sets are one
physical item; every other item is a separate physical copy. The shard's
active talent group chooses which set is equipped before login; the other
set's remaining items sit in one generic container bag. Item GUID offsets
are stable per character (bag 0, physical gear 1..59, consumables 60..99),
so the multiset of items never depends on the selected spec.
"""

from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
from typing import Any

from tools.bot_ml.build_validation_provisioning import (
    HOTFIX_ITEM_TEMPLATE_SOURCE,
    ITEM_SPARSE_FMT,
    NATIVE_SELF_SETUP_SPELL_IDS,
    bot_known_spell_ids,
    bot_primary_tree_spell_ids,
    bot_spell_ids,
    gem_item_enchant_map,
    load_wdb2_values,
    load_wdbc_values,
    runtime_safe_enchantments,
)

BAG_ITEM_OFFSET = 0
FIRST_GEAR_OFFSET = 1
CONSUMABLE_OFFSET = 60
MAX_GEAR_ITEMS = CONSUMABLE_OFFSET - FIRST_GEAR_OFFSET
ITEM_CLASS_CONTAINER = 1
ITEM_SUBCLASS_GENERIC_CONTAINER = 0
INVTYPE_BAG = 18
LIMIT_MODE_HAVE = 0
HOTFIX_MAXCOUNT_COLUMN = 26
HOTFIX_CLASS_COLUMNS = (1, 2)
HOTFIX_CONTAINER_SLOTS_COLUMN = 28
HOTFIX_INVENTORY_TYPE_COLUMN = 14
_ITEM_TABLE_CACHE: dict[Path, dict[str, Any]] = {}


class LoadoutError(ValueError):
    pass


def _hotfix_item_rows() -> dict[int, list[str]]:
    rows: dict[int, list[str]] = {}
    if not HOTFIX_ITEM_TEMPLATE_SOURCE.is_file():
        return rows
    for line in HOTFIX_ITEM_TEMPLATE_SOURCE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped.startswith("(") or ")," not in stripped:
            continue
        try:
            values = next(csv.reader([stripped[1:stripped.rfind("),")]], delimiter=",",
                                     quotechar="'", doublequote=True, skipinitialspace=True))
            rows[int(values[0])] = values
        except (IndexError, ValueError, StopIteration):
            continue
    return rows


def item_tables(dbc_dir: Path) -> dict[str, Any]:
    """Native item facts needed to place gear: MaxCount, limit categories, containers."""
    dbc_dir = Path(dbc_dir).resolve()
    cached = _ITEM_TABLE_CACHE.get(dbc_dir)
    if cached is not None:
        return cached
    sparse = {int(row[0]): row for row in load_wdb2_values(dbc_dir / "Item-sparse.db2", ITEM_SPARSE_FMT)}
    classes = {int(row[0]): (int(row[1]), int(row[2])) for row in load_wdb2_values(dbc_dir / "Item.db2", "niiiiiii")}
    items: dict[int, dict[str, int]] = {}
    for item_id, row in sparse.items():
        item_class, subclass = classes.get(item_id, (-1, -1))
        items[item_id] = {"max_count": int(row[21]), "container_slots": int(row[23]),
                          "inventory_type": int(row[9]), "limit_category": int(row[128]),
                          "class": item_class, "subclass": subclass}
    for item_id, values in _hotfix_item_rows().items():
        if item_id in items:
            continue
        items[item_id] = {"max_count": int(values[HOTFIX_MAXCOUNT_COLUMN]),
                          "container_slots": int(values[HOTFIX_CONTAINER_SLOTS_COLUMN]),
                          "inventory_type": int(values[HOTFIX_INVENTORY_TYPE_COLUMN]),
                          "limit_category": 0,
                          "class": int(values[HOTFIX_CLASS_COLUMNS[0]]),
                          "subclass": int(values[HOTFIX_CLASS_COLUMNS[1]])}
    limits = {int(row[0]): {"quantity": int(row[2]), "mode": int(row[3])}
              for row in load_wdbc_values(dbc_dir / "ItemLimitCategory.dbc", "nxii")}
    result = {"items": items, "limit_categories": limits}
    _ITEM_TABLE_CACHE[dbc_dir] = result
    return result


def item_identity(item: dict[str, Any], gem_mapping: dict[int, int], dbc_dir: Path) -> tuple[int, str]:
    return int(item["item_id"]), runtime_safe_enchantments(item, gem_mapping, dbc_dir)


def group_equipment(profiles: dict[str, Any], gear_profile_id: str) -> list[dict[str, Any]]:
    profile = profiles.get(gear_profile_id)
    if not profile or not profile.get("equipment"):
        raise LoadoutError(f"gear_profile_missing:{gear_profile_id}")
    return copy.deepcopy(profile["equipment"])


def physical_items(group_sets: list[list[dict[str, Any]]], gem_mapping: dict[int, int],
                   dbc_dir: Path) -> tuple[list[dict[str, Any]], list[dict[int, int]]]:
    """Share identical items across spec sets; return physical items and per-group slot maps."""
    physical: list[dict[str, Any]] = []
    sets: list[dict[int, int]] = []
    for group_index, equipment in enumerate(group_sets):
        used: set[int] = set()
        slot_map: dict[int, int] = {}
        for item in sorted(equipment, key=lambda row: int(row["slot"])):
            identity = item_identity(item, gem_mapping, dbc_dir)
            match = next((row["offset"] for row in physical
                          if row["identity"] == identity and row["offset"] not in used), None)
            if match is None:
                match = FIRST_GEAR_OFFSET + len(physical)
                physical.append({"offset": match, "identity": identity, "item": copy.deepcopy(item),
                                 "first_group": group_index})
            used.add(match)
            slot_map[int(item["slot"])] = match
        sets.append(slot_map)
    return physical, sets


def _view(bot: dict[str, Any], group: dict[str, Any]) -> dict[str, Any]:
    return {"class": bot["class"], "class_spec": group["class_spec"], "spells": bot.get("spells", []),
            "primary_talent_tree_id": group["primary_talent_tree_id"], "talents": group["talents"]}


def loadout_known_spells(bot: dict[str, Any], action_profiles: dict[str, Any] | None = None) -> dict[str, list[int]]:
    """Active group's full spellbook plus every group's baseline class spells.

    Talent and primary-tree spells of an inactive group are excluded: the
    native ActivateSpec path learns them only when that group is activated.
    """
    loadout = bot["loadout"]
    groups = loadout["groups"]
    active = groups[int(loadout["active_talent_group"])]
    known = set(bot_known_spell_ids(_view(bot, active), action_profiles))
    for group in groups:
        known.update(bot_spell_ids(_view(bot, group), action_profiles))
        known.update(NATIVE_SELF_SETUP_SPELL_IDS.get(str(group["class_spec"]), ()))
    active_specialization = {int(t["spell_id"]) for t in active["talents"]} | set(bot_primary_tree_spell_ids(active))
    inactive_only = set()
    for group in groups:
        group_specialization = {int(t["spell_id"]) for t in group["talents"]} | set(bot_primary_tree_spell_ids(group))
        inactive_only |= group_specialization - active_specialization
    leaked = sorted(known & inactive_only)
    if leaked:
        raise LoadoutError(f"inactive_group_spells_in_spellbook:{bot.get('name')}:{leaked}")
    return {"known_spell_ids": sorted(known), "inactive_only_specialization_spell_ids": sorted(inactive_only)}


def loadout_failures(bot: dict[str, Any], tables: dict[str, Any]) -> list[dict[str, Any]]:
    loadout = bot["loadout"]
    failures: list[dict[str, Any]] = []
    items = tables["items"]
    bag = loadout["bag"]
    bag_facts = items.get(int(bag["item_id"]))
    if (not bag_facts or bag_facts["class"] != ITEM_CLASS_CONTAINER
            or bag_facts["subclass"] != ITEM_SUBCLASS_GENERIC_CONTAINER
            or bag_facts["inventory_type"] != INVTYPE_BAG
            or bag_facts["container_slots"] != int(bag["container_slots"])):
        failures.append({"check": "bag_not_generic_container", "item_id": bag["item_id"], "facts": bag_facts})
    physical = loadout["physical_items"]
    if len(physical) > MAX_GEAR_ITEMS:
        failures.append({"check": "gear_item_offsets_exhausted", "count": len(physical)})
    for group in loadout["groups"]:
        bagged = [row for row in physical
                  if row["offset"] not in set(loadout["spec_gear_sets"][int(group["talent_group"])].values())]
        if len(bagged) > int(bag["container_slots"]):
            failures.append({"check": "bag_capacity", "talent_group": group["talent_group"],
                             "items": len(bagged), "capacity": bag["container_slots"]})
    counts: dict[int, int] = {}
    categories: dict[int, int] = {}
    for row in physical:
        item_id = int(row["item"]["item_id"])
        counts[item_id] = counts.get(item_id, 0) + 1
        facts = items.get(item_id)
        if facts is None:
            failures.append({"check": "item_facts_missing", "item_id": item_id})
            continue
        category = int(facts.get("limit_category") or 0)
        limit = tables["limit_categories"].get(category)
        if limit and limit["mode"] == LIMIT_MODE_HAVE:
            categories[category] = categories.get(category, 0) + 1
    for item_id, count in counts.items():
        max_count = int((items.get(item_id) or {}).get("max_count") or 0)
        if max_count and count > max_count:
            failures.append({"check": "unique_item_duplicated_across_specs", "item_id": item_id,
                             "count": count, "max_count": max_count})
    for category, count in categories.items():
        if count > tables["limit_categories"][category]["quantity"]:
            failures.append({"check": "have_limit_category_exceeded", "category": category, "count": count})
    return failures


def materialize_loadout(bot: dict[str, Any], profiles: dict[str, Any], dbc_dir: Path,
                        gem_mapping: dict[int, int] | None = None,
                        tables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Resolve both spec gear sets into physical items and this shard's placement."""
    from tools.bot_ml.wowsims_gear_binding import merge_profession_skills, resolve_profession_setup

    loadout = bot["loadout"]
    gem_mapping = gem_mapping if gem_mapping is not None else gem_item_enchant_map(dbc_dir)
    tables = tables or item_tables(dbc_dir)
    groups = loadout["groups"]
    active = int(loadout["active_talent_group"])
    group_sets = [group_equipment(profiles, str(group["gear_profile_id"])) for group in groups]
    equipped = bot.get("equipment") or []
    key = lambda item: item_identity(item, gem_mapping, dbc_dir) + (int(item["slot"]),)
    if sorted(map(key, equipped)) != sorted(map(key, group_sets[active])):
        raise LoadoutError(f"active_group_equipment_drift:{bot.get('name')}")
    physical, sets = physical_items(group_sets, gem_mapping, dbc_dir)
    loadout["physical_items"] = [{"offset": row["offset"], "item": row["item"],
                                  "first_talent_group": row["first_group"]} for row in physical]
    loadout["spec_gear_sets"] = [{str(slot): offset for slot, offset in sorted(slot_map.items())} for slot_map in sets]
    equipped_offsets = set(sets[active].values())
    loadout["equipped_offsets"] = sorted(equipped_offsets)
    loadout["bag_contents"] = [{"bag_slot_index": index, "offset": row["offset"]}
                               for index, row in enumerate(row for row in physical if row["offset"] not in equipped_offsets)]
    union = resolve_profession_setup([row["item"] for row in physical], configured_skills=bot.get("skills", []))
    loadout["profession_setup_union"] = union
    bot["skills"] = merge_profession_skills(bot.get("skills", []), union)
    loadout.update(loadout_known_spells(bot))
    failures = loadout_failures(bot, tables)
    if failures:
        raise LoadoutError(json.dumps({"bot": bot.get("name"), "failures": failures}, sort_keys=True, default=str))
    return loadout


def expected_talent_tree(bot: dict[str, Any]) -> str:
    """`characters.talentTree`: one primary tree per talent group, space terminated."""
    return " ".join(str(int(group["primary_talent_tree_id"])) for group in bot["loadout"]["groups"]) + " "


def expected_talent_rows(bot: dict[str, Any]) -> dict[int, list[int]]:
    return {int(group["talent_group"]): sorted(int(row["spell_id"]) for row in group["talents"])
            for group in bot["loadout"]["groups"]}


def expected_glyph_rows(bot: dict[str, Any]) -> dict[int, list[int]]:
    from tools.bot_ml.build_validation_provisioning import normalized_glyph_slots

    return {int(group["talent_group"]): normalized_glyph_slots({"glyphs": group["glyphs"]})
            for group in bot["loadout"]["groups"]}


def expected_inventory(bot: dict[str, Any], default_consumables: list[dict[str, Any]],
                       gem_mapping: dict[int, int], dbc_dir: Path) -> list[dict[str, Any]]:
    """Every item_instance/character_inventory row of one materialized loadout bot.

    `bag` is 0 for equipped/backpack rows and the container item GUID for
    rows inside the off-spec bag, exactly like native character_inventory.
    """
    loadout = bot["loadout"]
    base = int(loadout["item_guid_base"])
    bag = loadout["bag"]
    bag_guid = base + BAG_ITEM_OFFSET
    active_slots = {int(offset): int(slot)
                    for slot, offset in loadout["spec_gear_sets"][int(loadout["active_talent_group"])].items()}
    equipped_by_slot = {int(item["slot"]): item for item in bot.get("equipment", [])}
    rows = [{"kind": "bag", "item_guid": bag_guid, "item_id": int(bag["item_id"]), "bag": 0,
             "slot": int(bag["bag_slot"]), "count": 1, "durability": 0, "enchantments": ""}]
    bag_index = {int(row["offset"]): int(row["bag_slot_index"]) for row in loadout["bag_contents"]}
    for physical in loadout["physical_items"]:
        offset = int(physical["offset"])
        if offset in active_slots:
            slot = active_slots[offset]
            item = equipped_by_slot[slot]
            rows.append({"kind": "equipped", "item_guid": base + offset, "item_id": int(item["item_id"]),
                         "bag": 0, "slot": slot, "count": 1, "durability": int(item.get("durability", 100)),
                         "enchantments": runtime_safe_enchantments(item, gem_mapping, dbc_dir)})
        else:
            item = physical["item"]
            rows.append({"kind": "bagged", "item_guid": base + offset, "item_id": int(item["item_id"]),
                         "bag": bag_guid, "slot": bag_index[offset], "count": 1,
                         "durability": int(item.get("durability", 100)),
                         "enchantments": runtime_safe_enchantments(item, gem_mapping, dbc_dir)})
    for index, consumable in enumerate(bot.get("consumables", default_consumables)):
        rows.append({"kind": "consumable", "item_guid": base + CONSUMABLE_OFFSET + index,
                     "item_id": int(consumable["item_id"]), "bag": 0, "slot": int(consumable["slot"]),
                     "count": int(consumable.get("count", 20)), "durability": 1, "enchantments": ""})
    if CONSUMABLE_OFFSET + len(bot.get("consumables", default_consumables)) > 100:
        raise LoadoutError(f"consumable_item_offsets_exhausted:{bot.get('name')}")
    return rows


def materialize_config(config: dict[str, Any], profiles: dict[str, Any], dbc_dir: Path) -> dict[str, Any]:
    """Materialize every loadout bot of an already gear-applied provisioning config."""
    gem_mapping = gem_item_enchant_map(dbc_dir)
    tables = item_tables(dbc_dir)
    for scenario in config["scenarios"]:
        for bot in scenario["bots"]:
            if bot.get("loadout"):
                materialize_loadout(bot, profiles, dbc_dir, gem_mapping, tables)
    return config
