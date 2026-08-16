from __future__ import annotations

import argparse
import struct
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from .common import stable_hash, write_json
    from .extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf, sanitize_database_url
    from .build_validation_provisioning import REQUIRED_EQUIPMENT_SLOTS, load_config, required_equipment_slots_for
    from .validation_profile_manifests import DEFAULT_COMBAT_LOOT_PROFILE_MANIFEST, load_combat_loot_profile_manifest
except ImportError:
    from common import stable_hash, write_json
    from extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf, sanitize_database_url
    from build_validation_provisioning import REQUIRED_EQUIPMENT_SLOTS, load_config, required_equipment_slots_for
    from validation_profile_manifests import DEFAULT_COMBAT_LOOT_PROFILE_MANIFEST, load_combat_loot_profile_manifest


STAT_NAMES = {
    3: "agility",
    4: "strength",
    5: "intellect",
    6: "spirit",
    7: "stamina",
    13: "dodge",
    14: "parry",
    15: "block",
    31: "hit",
    32: "crit",
    36: "haste",
    37: "expertise",
    38: "attack_power",
    45: "spell_power",
    49: "mastery",
}

ARMOR_SUBCLASS_BY_CLASS = {
    1: 4,   # warrior plate
    2: 4,   # paladin plate
    3: 3,   # hunter mail
    4: 2,   # rogue leather
    5: 1,   # priest cloth
    6: 4,   # death knight plate
    7: 3,   # shaman mail
    8: 1,   # mage cloth
    9: 1,   # warlock cloth
    11: 2,  # druid leather
}

WEAPON_SUBCLASSES_BY_CLASS = {
    1: {0, 1, 2, 3, 4, 5, 6, 7, 8, 13, 16, 18},
    2: {0, 1, 4, 5, 6, 7, 8},
    3: {0, 1, 2, 3, 6, 7, 8, 10, 18},
    4: {0, 4, 7, 13, 15, 16},
    5: {10, 15, 19},
    6: {0, 1, 4, 5, 6, 7, 8},
    7: {0, 1, 4, 5, 10, 13, 15},
    8: {7, 10, 15, 19},
    9: {7, 10, 15, 19},
    11: {4, 5, 6, 10, 13, 15},
}

SHIELD_CLASSES = {1, 2, 7}
OFFHAND_WEAPON_CLASSES = {1, 4, 6, 7}
DUAL_WIELD_CLASS_SPECS = {"assassination_rogue", "enhancement_shaman", "frost_death_knight"}
TITANS_GRIP_CLASS_SPECS = {"fury_warrior"}

INVENTORY_TO_EQUIPMENT_SLOTS = {
    1: [0],      # head
    2: [1],      # neck
    3: [2],      # shoulder
    5: [4],      # chest
    6: [5],      # waist
    7: [6],      # legs
    8: [7],      # feet
    9: [8],      # wrists
    10: [9],     # hands
    11: [10, 11],
    12: [12, 13],
    14: [16],    # shield
    15: [17],    # bow
    16: [14],    # cloak
    13: [15, 16], # one-handed weapon
    17: [15, 16], # two-handed weapon (offhand gated by Titan's Grip)
    20: [4],     # robe
    21: [15],    # main hand
    22: [16],    # off hand weapon
    23: [16],    # holdable
    25: [17],    # thrown
    26: [17],    # ranged/right
    28: [17],    # relic
}

WEAPON_INVENTORY_TYPES = {13, 14, 15, 17, 21, 22, 23, 25, 26, 28}
GENERAL_ARMOR_INVENTORY_TYPES = {2, 11, 12, 16}
ARMOR_INVENTORY_TYPES = {1, 3, 5, 6, 7, 8, 9, 10, 20}

DEFAULT_COMBAT_LOOT_PROFILES = load_combat_loot_profile_manifest(DEFAULT_COMBAT_LOOT_PROFILE_MANIFEST)
STAT_WEIGHTS_BY_ROLE = DEFAULT_COMBAT_LOOT_PROFILES["stat_weights_by_archetype"]
MAX_PLAYER_ACCESSIBLE_CATA_ITEM_LEVEL = 416

CURATED_BIS_NAMES_BY_SPEC = {
    "fire_mage": ["Dragonwrath, Tarecgosa's Rest"],
    "affliction_warlock": ["Lightning Rod"],
    "elemental_shaman": ["Vagaries of Time", "Ledger of Revolting Rituals"],
    "assassination_rogue": ["Blade of the Unmaker", "Electrowing Dagger"],
    "protection_paladin": ["Souldrinker", "Blackhorn's Mighty Bulwark"],
    "holy_priest": ["Lightning Rod", "Ledger of Revolting Rituals"],
    "marksmanship_hunter": ["Kiril, Fury of Beasts", "Vishanka, Jaws of the Earth"],
    "survival_hunter": ["Kiril, Fury of Beasts", "Vishanka, Jaws of the Earth"],
    "enhancement_shaman": ["No'Kaled, the Elements of Death", "Morningstar of Heroic Will"],
    "protection_warrior": ["Souldrinker", "Blackhorn's Mighty Bulwark"],
    "blood_death_knight": ["Gurthalak, Voice of the Deeps"],
    "restoration_druid": ["Lightning Rod"],
    "holy_paladin": ["Maw of the Dragonlord", "Ledger of Revolting Rituals"],
    "discipline_priest": ["Lightning Rod", "Ledger of Revolting Rituals"],
}

ITEM_FMT = "niiiiiii"
ITEM_SPARSE_FMT = "niiiffiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiifiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiisssssiiiiiiiiiiiiiiiiiiiiiifiiifii"
SPELL_ITEM_ENCHANTMENT_FMT = "nxiiiiiixxxiiisiiiiiiix"
GEM_PROPERTIES_FMT = "nixxii"
ITEM_LIMIT_CATEGORY_FMT = "nxii"
ITEM_ENCHANTMENT_TYPE_STAT = 5
MAX_ENCHANTMENT_SLOT = 15
MAX_ENCHANTMENT_OFFSET = 3
SOCKET_ENCHANTMENT_FIELD_OFFSETS = [6, 9, 12]


def read_c_string(data: bytes, offset: int) -> str:
    if offset <= 0 or offset >= len(data):
        return ""
    end = data.find(b"\0", offset)
    if end == -1:
        end = len(data)
    return data[offset:end].decode("utf-8", errors="replace")


def load_wdb2(path: Path, fmt: str) -> list[dict[str, Any]]:
    blob = path.read_bytes()
    if len(blob) < 48 or blob[:4] != b"WDB2":
        raise ValueError(f"{path} is not a WDB2 file")
    record_count, field_count, record_size, string_size, _table_hash, build, _unk1 = struct.unpack_from("<7I", blob, 4)
    offset = 32
    min_index = max_index = 0
    if build > 12880:
        min_index, max_index, _locale, _unk5 = struct.unpack_from("<4i", blob, offset)
        offset += 16
    if max_index:
        span = max_index - min_index + 1
        offset += span * 4 + span * 2
    if field_count != len(fmt):
        raise ValueError(f"{path} field count {field_count} does not match format length {len(fmt)}")
    records_blob = blob[offset:offset + (record_count * record_size)]
    string_blob = blob[offset + (record_count * record_size):offset + (record_count * record_size) + string_size]
    rows = []
    for row_index in range(record_count):
        row_offset = row_index * record_size
        values = []
        field_offset = 0
        for field_type in fmt:
            if field_type == "f":
                values.append(struct.unpack_from("<f", records_blob, row_offset + field_offset)[0])
            elif field_type == "s":
                values.append(read_c_string(string_blob, struct.unpack_from("<I", records_blob, row_offset + field_offset)[0]))
            else:
                raw = struct.unpack_from("<I", records_blob, row_offset + field_offset)[0]
                if field_type == "i" and raw >= 0x80000000:
                    raw -= 0x100000000
                values.append(raw)
            field_offset += 4
        rows.append({"values": values})
    return rows


def load_wdbc(path: Path, fmt: str) -> list[dict[str, Any]]:
    blob = path.read_bytes()
    if len(blob) < 20 or blob[:4] != b"WDBC":
        raise ValueError(f"{path} is not a WDBC file")
    record_count, field_count, record_size, string_size = struct.unpack_from("<4I", blob, 4)
    if field_count != len(fmt):
        raise ValueError(f"{path} field count {field_count} does not match format length {len(fmt)}")
    records_offset = 20
    records_blob = blob[records_offset:records_offset + (record_count * record_size)]
    string_blob = blob[records_offset + (record_count * record_size):records_offset + (record_count * record_size) + string_size]
    rows = []
    for row_index in range(record_count):
        row_offset = row_index * record_size
        values = []
        field_offset = 0
        for field_type in fmt:
            if field_type == "f":
                values.append(struct.unpack_from("<f", records_blob, row_offset + field_offset)[0])
            elif field_type == "s":
                values.append(read_c_string(string_blob, struct.unpack_from("<I", records_blob, row_offset + field_offset)[0]))
            else:
                raw = struct.unpack_from("<I", records_blob, row_offset + field_offset)[0]
                if field_type == "i" and raw >= 0x80000000:
                    raw -= 0x100000000
                values.append(raw)
            field_offset += 4
        rows.append({"values": values})
    return rows


def load_db2_item_rows(dbc_dir: Path) -> list[dict[str, Any]]:
    item_rows = load_wdb2(dbc_dir / "Item.db2", ITEM_FMT)
    sparse_rows = load_wdb2(dbc_dir / "Item-sparse.db2", ITEM_SPARSE_FMT)
    item_by_id = {
        int(row["values"][0]): {
            "ID": int(row["values"][0]),
            "ClassID": int(row["values"][1]),
            "SubclassID": int(row["values"][2]),
            "InventoryType": int(row["values"][6]),
        }
        for row in item_rows
    }
    merged = []
    for row in sparse_rows:
        values = row["values"]
        item_id = int(values[0])
        base = item_by_id.get(item_id)
        if not base:
            continue
        merged_row: dict[str, Any] = {
            **base,
            "Display": values[99] if values[99] not in {-1, ""} else values[96],
            "Quality": int(values[1]),
            "ItemLevel": int(values[12]),
            "RequiredLevel": int(values[13]),
            "AllowableClass": int(values[10]),
            "InventoryType": int(base.get("InventoryType") or values[9] or 0),
            "SocketColor1": int(values[118]),
            "SocketColor2": int(values[119]),
            "SocketColor3": int(values[120]),
            "GemProperties": int(values[125]),
            "ItemLimitCategory": int(values[128]),
            "source": "client_db2",
        }
        for index in range(1, 11):
            merged_row[f"ItemStatType{index}"] = int(values[23 + index])
            merged_row[f"ItemStatValue{index}"] = int(values[33 + index])
        merged.append(merged_row)
    return merged


def load_spell_item_enchantments(dbc_dir: Path, max_level: int = 85) -> list[dict[str, Any]]:
    path = dbc_dir / "SpellItemEnchantment.dbc"
    if not path.exists():
        return []
    enchantments = []
    for row in load_wdbc(path, SPELL_ITEM_ENCHANTMENT_FMT):
        values = row["values"]
        effects = [int(value) for value in values[2:5]]
        effect_points = [int(value) for value in values[5:8]]
        effect_args = [int(value) for value in values[11:14]]
        if not any(effect == ITEM_ENCHANTMENT_TYPE_STAT for effect in effects):
            continue
        stats: dict[str, int] = {}
        for effect, points, arg in zip(effects, effect_points, effect_args):
            stat_name = STAT_NAMES.get(arg)
            if effect == ITEM_ENCHANTMENT_TYPE_STAT and stat_name and points > 0:
                stats[stat_name] = stats.get(stat_name, 0) + points
        if not stats:
            continue
        total_points = sum(stats.values())
        min_level = int(values[21])
        required_skill = int(values[19])
        if min_level > max_level or total_points > 250:
            continue
        enchantments.append(
            {
                "id": int(values[0]),
                "name": values[14],
                "stats": stats,
                "min_level": min_level,
                "required_skill_id": required_skill,
                "required_skill_rank": int(values[20]),
                "selection_source": "spell_item_enchantment_dbc_stat_score",
            }
        )
    return enchantments


def load_gem_properties(dbc_dir: Path) -> dict[int, dict[str, int]]:
    path = dbc_dir / "GemProperties.dbc"
    if not path.exists():
        return {}
    properties = {}
    for row in load_wdbc(path, GEM_PROPERTIES_FMT):
        values = row["values"]
        properties[int(values[0])] = {
            "enchant_id": int(values[1]),
            "color": int(values[4]),
            "min_item_level": int(values[5]),
        }
    return properties


def load_enchantment_source_items(dbc_dir: Path) -> dict[int, int]:
    path = dbc_dir / "SpellItemEnchantment.dbc"
    if not path.exists():
        return {}
    return {
        int(row["values"][0]): int(row["values"][17])
        for row in load_wdbc(path, SPELL_ITEM_ENCHANTMENT_FMT)
        if int(row["values"][0]) > 0 and int(row["values"][17]) > 0
    }


def load_item_limit_categories(dbc_dir: Path) -> dict[int, dict[str, int]]:
    path = dbc_dir / "ItemLimitCategory.dbc"
    if not path.exists():
        return {}
    return {
        int(row["values"][0]): {
            "quantity": int(row["values"][2]),
            "flags": int(row["values"][3]),
        }
        for row in load_wdbc(path, ITEM_LIMIT_CATEGORY_FMT)
        if int(row["values"][0]) > 0 and int(row["values"][2]) > 0
    }


def role_archetype(bot: dict[str, Any], profile_manifest: dict[str, Any] | None = None) -> str:
    manifest = profile_manifest or DEFAULT_COMBAT_LOOT_PROFILES
    spec = str(bot.get("class_spec", ""))
    configured = manifest.get("class_spec_archetypes", {}).get(spec)
    if configured:
        return configured
    role = str(bot.get("role", "dps"))
    class_id = int(bot.get("class", 0))
    if role in {"tank", "healer"}:
        return role
    if class_id in {1, 2, 6}:
        return "dps_strength"
    if class_id in {3, 4} or (class_id == 11 and "feral" in spec):
        return "dps_agility"
    if class_id == 7 and "enhancement" in spec:
        return "dps_agility"
    return "dps_intellect"


def stat_weights_for_bot(bot: dict[str, Any], profile_manifest: dict[str, Any] | None = None) -> dict[str, float]:
    manifest = profile_manifest or DEFAULT_COMBAT_LOOT_PROFILES
    archetype = role_archetype(bot, manifest)
    weights = dict(manifest["stat_weights_by_archetype"].get(archetype, {}))
    weights.update(manifest.get("stat_weight_overrides_by_spec", {}).get(str(bot.get("class_spec", "")), {}))
    return weights


def stat_map(item: dict[str, Any]) -> dict[str, int]:
    stats: dict[str, int] = {}
    for index in range(1, 11):
        stat_type = int(item.get(f"ItemStatType{index}") or 0)
        stat_value = int(item.get(f"ItemStatValue{index}") or 0)
        name = STAT_NAMES.get(stat_type)
        if name and stat_value:
            stats[name] = stats.get(name, 0) + stat_value
    return stats


def normalize_item_name(value: str) -> str:
    return " ".join(value.lower().replace("'", "").split())


def item_player_accessible(item: dict[str, Any]) -> bool:
    name = normalize_item_name(str(item.get("Display") or ""))
    if any(token in name for token in ("test", "debug", "deprecated", "gm ", "zzold")):
        return False
    return 1 <= int(item.get("ItemLevel") or 0) <= MAX_PLAYER_ACCESSIBLE_CATA_ITEM_LEVEL and int(item.get("RequiredLevel") or 0) <= 85


def curated_items_by_slot(bot: dict[str, Any], items: list[dict[str, Any]]) -> tuple[dict[int, dict[str, Any]], list[str], list[dict[str, Any]]]:
    wanted_names = CURATED_BIS_NAMES_BY_SPEC.get(str(bot.get("class_spec") or ""), [])
    if not wanted_names:
        return {}, [], []
    by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        by_name[normalize_item_name(str(item.get("Display") or ""))].append(item)

    resolved: dict[int, dict[str, Any]] = {}
    missing: list[str] = []
    rejected: list[dict[str, Any]] = []
    class_id = int(bot["class"])
    for wanted in wanted_names:
        candidates = [
            item for item in by_name.get(normalize_item_name(wanted), [])
            if class_allowed(item, class_id) and armor_allowed(item, class_id)
        ]
        candidates.sort(key=lambda item: (int(item.get("ItemLevel") or 0), int(item.get("ID") or 0)), reverse=True)
        selected = None
        for item in candidates:
            if item_player_accessible(item):
                selected = item
                break
            rejected.append({"name": wanted, "item_id": int(item.get("ID") or 0), "item_level": int(item.get("ItemLevel") or 0), "reason": "not_player_accessible"})
        if not selected:
            missing.append(wanted)
            continue
        for slot in INVENTORY_TO_EQUIPMENT_SLOTS.get(int(selected.get("InventoryType") or 0), []):
            if not weapon_slot_allowed(bot, selected, slot):
                continue
            if slot in REQUIRED_EQUIPMENT_SLOTS and slot not in resolved:
                resolved[slot] = selected
                break
    return resolved, missing, rejected


def class_allowed(item: dict[str, Any], class_id: int) -> bool:
    mask = int(item.get("AllowableClass") or -1)
    return mask in {-1, 0} or bool(mask & (1 << (class_id - 1)))


def armor_allowed(item: dict[str, Any], class_id: int) -> bool:
    inventory_type = int(item.get("InventoryType") or 0)
    subclass = int(item.get("SubclassID") or 0)
    class_id_item = int(item.get("ClassID") or 0)
    if inventory_type == 22:
        return class_id in OFFHAND_WEAPON_CLASSES and subclass in WEAPON_SUBCLASSES_BY_CLASS.get(class_id, set())
    if class_id_item == 2:
        return inventory_type in WEAPON_INVENTORY_TYPES and subclass in WEAPON_SUBCLASSES_BY_CLASS.get(class_id, set())
    if inventory_type == 14:
        return class_id in SHIELD_CLASSES
    if inventory_type in GENERAL_ARMOR_INVENTORY_TYPES:
        return True
    if inventory_type in ARMOR_INVENTORY_TYPES:
        return subclass == ARMOR_SUBCLASS_BY_CLASS.get(class_id, subclass)
    return inventory_type in INVENTORY_TO_EQUIPMENT_SLOTS


def weapon_slot_allowed(bot: dict[str, Any], item: dict[str, Any], slot: int) -> bool:
    inventory_type = int(item.get("InventoryType") or 0)
    item_class = int(item.get("ClassID") or 0)
    subclass = int(item.get("SubclassID") or 0)
    class_id = int(bot.get("class") or 0)
    class_spec = str(bot.get("class_spec") or "")
    if slot == 16 and inventory_type == 13:
        return class_spec in DUAL_WIELD_CLASS_SPECS
    if slot == 16 and inventory_type == 17:
        return class_spec in TITANS_GRIP_CLASS_SPECS and subclass != 6
    if slot == 17:
        if class_id == 3:
            return item_class == 2 and inventory_type in {15, 26} and subclass in {2, 3, 18}
        if class_id in {1, 4}:
            return item_class == 2 and inventory_type in {15, 25, 26} and subclass in {2, 3, 16, 18}
        if class_id in {5, 8, 9}:
            return item_class == 2 and inventory_type == 26 and subclass == 19
        if class_id in {2, 6, 7, 11}:
            return item_class == 4 and inventory_type == 28
    return True


def item_score(item: dict[str, Any], weights: dict[str, float]) -> float:
    stats = stat_map(item)
    return float(item.get("ItemLevel") or 0) * 10.0 + sum(float(value) * weights.get(name, 0.0) for name, value in stats.items())


def enchant_score(enchantment: dict[str, Any], weights: dict[str, float]) -> float:
    stats = enchantment.get("stats", {})
    return sum(float(value) * weights.get(name, 0.0) for name, value in stats.items())


def enchantments_string(enchant_id: int, gem_enchant_ids: list[int] | None = None) -> str:
    fields = [0] * (MAX_ENCHANTMENT_SLOT * MAX_ENCHANTMENT_OFFSET)
    fields[0] = int(enchant_id)
    for field_offset, gem_enchant_id in zip(SOCKET_ENCHANTMENT_FIELD_OFFSETS, gem_enchant_ids or []):
        fields[field_offset] = int(gem_enchant_id)
    return " ".join(str(value) for value in fields)


def select_enchantment(enchantments: list[dict[str, Any]], weights: dict[str, float]) -> dict[str, Any] | None:
    ranked = sorted(
        ((enchant_score(enchantment, weights), int(enchantment["id"]), enchantment) for enchantment in enchantments),
        key=lambda row: (row[0], row[1]),
        reverse=True,
    )
    return next((enchantment for score, _id, enchantment in ranked if score > 0.0), None)


def build_gem_catalog(
    items: list[dict[str, Any]],
    gem_properties: dict[int, dict[str, int]],
    enchantments_by_id: dict[int, dict[str, Any]],
    enchantment_source_items: dict[int, int] | None = None,
) -> list[dict[str, Any]]:
    gems = []
    for item in items:
        gem_property_id = int(item.get("GemProperties") or 0)
        gem_property = gem_properties.get(gem_property_id)
        if not gem_property:
            continue
        enchantment = enchantments_by_id.get(int(gem_property["enchant_id"]))
        if not enchantment:
            continue
        if enchantment_source_items is not None and enchantment_source_items.get(int(gem_property["enchant_id"])) != int(item["ID"]):
            continue
        gems.append(
            {
                "item_id": int(item["ID"]),
                "name": item.get("Display") or "",
                "quality": int(item.get("Quality") or 0),
                "item_level": int(item.get("ItemLevel") or 0),
                "required_level": int(item.get("RequiredLevel") or 0),
                "gem_property_id": gem_property_id,
                "enchant_id": int(gem_property["enchant_id"]),
                "color": int(gem_property["color"]),
                "item_limit_category": int(item.get("ItemLimitCategory") or 0),
                "stats": enchantment.get("stats", {}),
            }
        )
    return gems


def select_gem(
    socket_color: int,
    gems: list[dict[str, Any]],
    weights: dict[str, float],
    limit_counts: dict[int, int] | None = None,
    limit_categories: dict[int, dict[str, int]] | None = None,
) -> dict[str, Any] | None:
    if limit_counts is None:
        limit_counts = {}
    if limit_categories is None:
        limit_categories = {}
    compatible = []
    for gem in gems:
        if not (int(gem.get("color") or 0) & int(socket_color)):
            continue
        category = int(gem.get("item_limit_category") or 0)
        limit = int(limit_categories.get(category, {}).get("quantity") or 0)
        if category:
            # A category without a quantity oracle is not safe to equip.  The
            # core applies the category quantity to socketed gems regardless
            # of the category's HAVE/EQUIP flag when validating equipment.
            if not limit or limit_counts.get(category, 0) >= limit:
                continue
        compatible.append(gem)
    ranked = sorted(
        ((sum(float(value) * weights.get(name, 0.0) for name, value in gem.get("stats", {}).items()), int(gem["item_level"]), int(gem["item_id"]), gem) for gem in compatible),
        key=lambda row: (row[0], row[1], row[2]),
        reverse=True,
    )
    return next((gem for score, _level, _id, gem in ranked if score > 0.0), None)


def fetch_hotfix_items(hotfix_url: str, min_item_level: int, max_required_level: int) -> list[dict[str, Any]]:
    conn = connect_mysql(hotfix_url)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT i.ID, s.Display, i.ClassID, i.SubclassID, COALESCE(NULLIF(i.InventoryType, 0), s.InventoryType) AS InventoryType, "
                "s.Quality, s.ItemLevel, s.RequiredLevel, s.AllowableClass, s.SocketColor1, s.SocketColor2, s.SocketColor3, "
                "s.GemProperties, s.ItemLimitCategory, "
                + ", ".join(f"s.ItemStatType{i}, s.ItemStatValue{i}" for i in range(1, 11))
                + " FROM item i JOIN item_sparse s ON s.ID = i.ID "
                "WHERE i.ClassID IN (2, 4) AND s.Quality >= 3 AND s.RequiredLevel <= %s AND s.ItemLevel >= %s",
                (max_required_level, min_item_level),
            )
            rows = list(cursor.fetchall())
            for row in rows:
                row["source"] = "hotfix_db"
            return rows
    finally:
        conn.close()


def fetch_items(hotfix_url: str, dbc_dir: Path | None, min_item_level: int, max_required_level: int) -> list[dict[str, Any]]:
    by_id: dict[int, dict[str, Any]] = {}
    if dbc_dir and (dbc_dir / "Item.db2").exists() and (dbc_dir / "Item-sparse.db2").exists():
        for row in load_db2_item_rows(dbc_dir):
            if int(row.get("ItemLevel") or 0) >= min_item_level and int(row.get("RequiredLevel") or 0) <= max_required_level:
                by_id[int(row["ID"])] = row
    if hotfix_url:
        try:
            for row in fetch_hotfix_items(hotfix_url, min_item_level, max_required_level):
                by_id[int(row["ID"])] = row
        except Exception:
            if not by_id:
                raise
    return list(by_id.values())


def choose_loadout(
    bot: dict[str, Any],
    items: list[dict[str, Any]],
    enchantments: list[dict[str, Any]] | None = None,
    gems: list[dict[str, Any]] | None = None,
    profile_manifest: dict[str, Any] | None = None,
    item_limit_categories: dict[int, dict[str, int]] | None = None,
) -> list[dict[str, Any]]:
    class_id = int(bot["class"])
    profile_manifest = profile_manifest or DEFAULT_COMBAT_LOOT_PROFILES
    weights = stat_weights_for_bot(bot, profile_manifest)
    selected_enchantment = select_enchantment(enchantments or [], weights)
    curated_slots, missing_curated, rejected_curated = curated_items_by_slot(bot, items)
    curated_item_ids = {int(item["ID"]) for item in curated_slots.values()}
    candidates_by_slot: dict[int, list[tuple[float, dict[str, Any]]]] = defaultdict(list)
    for item in items:
        if not item_player_accessible(item):
            continue
        if not class_allowed(item, class_id) or not armor_allowed(item, class_id):
            continue
        inventory_type = int(item.get("InventoryType") or 0)
        for slot in INVENTORY_TO_EQUIPMENT_SLOTS.get(inventory_type, []):
            if not weapon_slot_allowed(bot, item, slot):
                continue
            if slot in REQUIRED_EQUIPMENT_SLOTS:
                candidates_by_slot[slot].append((item_score(item, weights), item))

    used: set[int] = set()
    loadout = []
    titan_grip = str(bot.get("class_spec") or "") in TITANS_GRIP_CLASS_SPECS
    gem_limit_counts: dict[int, int] = defaultdict(int)
    item_limit_categories = item_limit_categories or {}

    def limit_category_available(item: dict[str, Any]) -> bool:
        category = int(item.get("ItemLimitCategory") or 0)
        if not category:
            return True
        quantity = int(item_limit_categories.get(category, {}).get("quantity") or 0)
        return quantity > 0 and gem_limit_counts[category] < quantity

    for slot in REQUIRED_EQUIPMENT_SLOTS:
        if slot == 16 and not titan_grip and any(int(item.get("slot", -1)) == 15 and int(item.get("inventory_type", 0)) == 17 for item in loadout):
            continue
        selected = curated_slots.get(slot)
        if selected and (int(selected["ID"]) in used or not limit_category_available(selected)):
            selected = None
        if not selected:
            ranked = sorted(candidates_by_slot.get(slot, []), key=lambda pair: (pair[0], int(pair[1].get("ItemLevel") or 0), int(pair[1].get("ID") or 0)), reverse=True)
            selected = next(
                (item for _score, item in ranked if int(item["ID"]) not in used and limit_category_available(item)),
                None,
            )
        if not selected:
            continue
        used.add(int(selected["ID"]))
        selected_category = int(selected.get("ItemLimitCategory") or 0)
        if selected_category:
            gem_limit_counts[selected_category] += 1
        sockets = [int(selected.get(f"SocketColor{i}") or 0) for i in range(1, 4)]
        enchant_id = int(selected_enchantment["id"]) if selected_enchantment else 0
        socket_colors = [socket for socket in sockets if socket]
        selected_gems = []
        for socket in socket_colors:
            gem = select_gem(socket, gems or [], weights, gem_limit_counts, item_limit_categories)
            if gems and gem is None:
                raise ValueError(
                    f"no runtime-legal gem for profile={bot.get('class_spec')} slot={slot} socket_color={socket}"
                )
            selected_gems.append(gem)
            if gem:
                category = int(gem.get("item_limit_category") or 0)
                if category:
                    gem_limit_counts[category] += 1
        gem_item_ids = [int(gem["item_id"]) for gem in selected_gems if gem]
        gem_enchant_ids = [int(gem["enchant_id"]) for gem in selected_gems if gem]
        loadout.append(
            {
                "slot": slot,
                "item_id": int(selected["ID"]),
                "name": selected.get("Display") or "",
                "item_level": int(selected.get("ItemLevel") or 0),
                "inventory_type": int(selected.get("InventoryType") or 0),
                "subclass": int(selected.get("SubclassID") or 0),
                "source": selected.get("source") or "unknown",
                "source_label": "curated_tauri_veins_434_player_accessible" if int(selected["ID"]) in curated_item_ids else selected.get("source") or "unknown",
                "player_accessible": item_player_accessible(selected),
                "stats": stat_map(selected),
                "socket_colors": socket_colors,
                "gem_item_ids": gem_item_ids,
                "gem_enchant_ids": gem_enchant_ids,
                "enchant_id": enchant_id,
                "enchant_name": selected_enchantment.get("name", "") if selected_enchantment else "",
                "enchant_stats": selected_enchantment.get("stats", {}) if selected_enchantment else {},
                "enchantments": enchantments_string(enchant_id, gem_enchant_ids) if enchant_id or gem_enchant_ids else "",
                "enchant_selection_source": selected_enchantment.get("selection_source", "") if selected_enchantment else "",
                "selection_score": round(item_score(selected, weights), 3),
                "stat_weight_archetype": role_archetype(bot, profile_manifest),
                "stat_weight_manifest_hash": profile_manifest["hash"],
                "curated_missing_source_items": missing_curated,
                "rejected_high_ilvl_candidates": rejected_curated,
            }
        )
    return loadout


def build_profiles(
    config: dict[str, Any],
    items: list[dict[str, Any]],
    enchantments: list[dict[str, Any]] | None = None,
    gems: list[dict[str, Any]] | None = None,
    profile_manifest: dict[str, Any] | None = None,
    item_limit_categories: dict[int, dict[str, int]] | None = None,
) -> dict[str, Any]:
    profile_manifest = profile_manifest or DEFAULT_COMBAT_LOOT_PROFILES
    profiles: dict[str, Any] = {}
    for scenario in config["scenarios"]:
        for bot in scenario["bots"]:
            key = str(bot.get("class_spec") or bot["name"])
            profiles.setdefault(
                key,
                {
                    "class_id": int(bot["class"]),
                    "role": bot["role"],
                    "archetype": role_archetype(bot, profile_manifest),
                    "stat_weights": stat_weights_for_bot(bot, profile_manifest),
                    "stat_weight_manifest": {
                        "path": profile_manifest["path"],
                        "schema": profile_manifest["schema"],
                        "hash": profile_manifest["hash"],
                    },
                    "equipment": choose_loadout(bot, items, enchantments, gems, profile_manifest, item_limit_categories),
                    "enchant_selection_mode": "dbc_stat_score_unverified_slot_applicability" if enchantments else "none",
                    "gem_selection_mode": "gem_properties_dbc_socket_color_score" if gems else "none",
                },
            )
    for profile in profiles.values():
        covered = {int(item["slot"]) for item in profile["equipment"]}
        profile["missing_slots"] = sorted(set(required_equipment_slots_for(profile["equipment"])) - covered)
        profile["complete_equipment_slots"] = not profile["missing_slots"]
        profile["gemmed"] = all(not item.get("socket_colors") or item.get("gem_item_ids") for item in profile["equipment"])
        profile["enchanted"] = all(int(item.get("enchant_id") or 0) for item in profile["equipment"])
        profile["average_item_level"] = round(sum(int(item.get("item_level") or 0) for item in profile["equipment"]) / max(len(profile["equipment"]), 1), 2)
        source_counts: dict[str, int] = {}
        for item in profile["equipment"]:
            source = str(item.get("source") or "unknown")
            source_counts[source] = source_counts.get(source, 0) + 1
        profile["equipment_source_counts"] = source_counts
        profile["bis_source_report"] = [
            {
                "slot": int(item["slot"]),
                "item_id": int(item["item_id"]),
                "name": item.get("name", ""),
                "item_level": int(item.get("item_level") or 0),
                "source": item.get("source", "unknown"),
                "source_label": item.get("source_label", item.get("source", "unknown")),
                "player_accessible": bool(item.get("player_accessible", False)),
                "selection_score": item.get("selection_score", 0.0),
            }
            for item in profile["equipment"]
        ]
        profile["selected_item_ids"] = [int(item["item_id"]) for item in profile["equipment"]]
        profile["all_selected_items_player_accessible"] = all(bool(item.get("player_accessible", False)) for item in profile["equipment"])
        profile["curated_missing_source_items"] = sorted({name for item in profile["equipment"] for name in item.get("curated_missing_source_items", [])})
        profile["rejected_high_ilvl_candidates"] = [row for item in profile["equipment"] for row in item.get("rejected_high_ilvl_candidates", [])]
    return profiles


def build_report(profiles: dict[str, Any], source_database: dict[str, Any], profile_manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    profile_manifest = profile_manifest or DEFAULT_COMBAT_LOOT_PROFILES
    complete = sum(1 for profile in profiles.values() if profile["complete_equipment_slots"])
    selected_items = [item for profile in profiles.values() for item in profile["equipment"]]
    source_counts: dict[str, int] = {}
    for item in selected_items:
        source = str(item.get("source") or "unknown")
        source_counts[source] = source_counts.get(source, 0) + 1
    return {
        "schema": "bot_validation_gear_profiles_report_v1",
        "profile_count": len(profiles),
        "complete_equipment_profiles": complete,
        "all_equipment_slots_complete": complete == len(profiles),
        "all_gemmed": all(profile["gemmed"] for profile in profiles.values()),
        "all_enchanted": all(profile["enchanted"] for profile in profiles.values()),
        "all_selected_items_player_accessible": all(profile.get("all_selected_items_player_accessible", False) for profile in profiles.values()),
        "selected_item_ids": sorted({int(item["item_id"]) for item in selected_items}),
        "missing_source_failures": {name: profile.get("curated_missing_source_items", []) for name, profile in profiles.items() if profile.get("curated_missing_source_items")},
        "rejected_high_ilvl_candidates": [row for profile in profiles.values() for row in profile.get("rejected_high_ilvl_candidates", [])],
        "enchant_selection_modes": sorted({profile.get("enchant_selection_mode", "none") for profile in profiles.values()}),
        "gem_selection_modes": sorted({profile.get("gem_selection_mode", "none") for profile in profiles.values()}),
        "enchant_applicability_verified_by_server": False,
        "profile_manifest": {
            "path": profile_manifest["path"],
            "schema": profile_manifest["schema"],
            "hash": profile_manifest["hash"],
        },
        "stat_weight_archetypes": sorted({profile.get("archetype", "") for profile in profiles.values()}),
        "smart_loot_validation_surface": {
            "ready_for_upgrade_scoring": complete == len(profiles) and all(profile["enchanted"] for profile in profiles.values()),
            "stat_weights_manifest_hash": profile_manifest["hash"],
            "selected_equipment_count": len(selected_items),
            "equipment_source_counts": source_counts,
            "average_profile_item_level": round(sum(float(profile.get("average_item_level") or 0.0) for profile in profiles.values()) / max(len(profiles), 1), 2),
            "loot_validation_manifest": profile_manifest.get("loot_validation", {}),
        },
        "source_counts": {
            "client_db2_items": sum(1 for profile in profiles.values() for item in profile["equipment"] if item.get("source") in {"client_db2", "hotfix_db"}),
            "hotfix_db_items": sum(1 for profile in profiles.values() for item in profile["equipment"] if item.get("source") == "hotfix_db"),
            "enchanted_items": sum(1 for profile in profiles.values() for item in profile["equipment"] if int(item.get("enchant_id") or 0)),
            "socketed_items": sum(1 for profile in profiles.values() for item in profile["equipment"] if item.get("socket_colors")),
            "gemmed_items": sum(1 for profile in profiles.values() for item in profile["equipment"] if item.get("socket_colors") and item.get("gem_item_ids")),
        },
        "source_database": source_database,
        "runtime_ml_control": "disabled_teacher_policy_validation_only",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build validation gear profiles from Cataclysm hotfix item data.")
    parser.add_argument("--config", type=Path, default=Path("experiments/configs/validation_provisioning_cata_001.json"))
    parser.add_argument("--worldserver-conf", type=Path, default=Path("trinity-worldserver-test.conf"))
    parser.add_argument("--hotfix-database-url", help="MySQL URL for the hotfix database. Defaults to HotfixDatabaseInfo from --worldserver-conf.")
    parser.add_argument("--dbc-dir", type=Path, default=Path("data/dbc/enUS"), help="Directory containing Item.db2 and Item-sparse.db2.")
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/validation_gear_profiles"))
    parser.add_argument("--min-item-level", type=int, default=1)
    parser.add_argument("--max-required-level", type=int, default=85)
    parser.add_argument("--profile-manifest", type=Path, default=DEFAULT_COMBAT_LOOT_PROFILE_MANIFEST)
    args = parser.parse_args()

    config = load_config(args.config)
    profile_manifest = load_combat_loot_profile_manifest(args.profile_manifest)
    hotfix_url = args.hotfix_database_url or database_url_from_worldserver_conf(args.worldserver_conf, "HotfixDatabaseInfo")
    items = fetch_items(hotfix_url, args.dbc_dir, args.min_item_level, args.max_required_level)
    enchantments = load_spell_item_enchantments(args.dbc_dir, args.max_required_level) if args.dbc_dir else []
    enchantments_by_id = {int(enchantment["id"]): enchantment for enchantment in enchantments}
    enchantment_source_items = load_enchantment_source_items(args.dbc_dir) if args.dbc_dir else {}
    gems = build_gem_catalog(
        items,
        load_gem_properties(args.dbc_dir),
        enchantments_by_id,
        enchantment_source_items,
    ) if args.dbc_dir else []
    item_limit_categories = load_item_limit_categories(args.dbc_dir) if args.dbc_dir else {}
    if args.dbc_dir and (not enchantment_source_items or not item_limit_categories):
        raise ValueError("validation gear requires nonempty enchant-source and item-limit-category DBC oracles")
    profiles = build_profiles(config, items, enchantments, gems, profile_manifest, item_limit_categories)
    source_database = sanitize_database_url(hotfix_url)
    report = build_report(profiles, source_database, profile_manifest)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(
        args.output_dir / "profiles.json",
        {
            "schema": "bot_validation_gear_profiles_v1",
            "profiles": profiles,
            "source_database": source_database,
            "dbc_dir": str(args.dbc_dir),
            "profile_manifest": {
                "path": profile_manifest["path"],
                "schema": profile_manifest["schema"],
                "hash": profile_manifest["hash"],
            },
        },
    )
    write_json(args.output_dir / "report.json", report)
    write_json(
        args.output_dir / "manifest.json",
        {
            "schema": "bot_validation_gear_profiles_manifest_v1",
            "config_hash": stable_hash(config),
            "profile_hash": stable_hash(profiles),
            "profile_count": len(profiles),
            "enchantment_count": len(enchantments),
            "gem_count": len(gems),
            "profile_manifest_hash": profile_manifest["hash"],
            "profile_manifest_path": profile_manifest["path"],
            "outputs": {"profiles": "profiles.json", "report": "report.json"},
            "runtime_ml_control": "disabled_teacher_policy_validation_only",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
