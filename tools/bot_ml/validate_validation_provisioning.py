from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

try:
    from .build_validation_gear_profiles import (
        SOCKET_ENCHANTMENT_FIELD_OFFSETS,
        build_gem_catalog,
        build_profiles,
        fetch_items,
        load_gem_properties,
        load_enchantment_source_items,
        load_item_limit_categories,
        load_wdbc,
        load_spell_item_enchantments,
        SPELL_ITEM_ENCHANTMENT_FMT,
    )
    from .build_validation_provisioning import DEFAULT_BWD_DIAGNOSTIC_SHARD_FIXTURE, EQUIPMENT_SLOT_END, REQUIRED_EQUIPMENT_SLOTS, account_commands, apply_gear_profiles, bot_known_spell_ids, bot_talent_spell_ids, build_account_insert_sql, build_character_insert_sql, enchantment_source_item_map, equipment_cache, gem_item_enchant_map, item_limit_category_by_item_map, load_config_with_bwd_diagnostic_shards, load_gear_profiles, load_wdbc_values, normalized_glyphs, required_equipment_slots_for, runtime_safe_enchantments, scenario_report, talent_point_count
    from .common import stable_hash, write_json
    from .extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf, sanitize_database_url
except ImportError:
    from build_validation_gear_profiles import (
        SOCKET_ENCHANTMENT_FIELD_OFFSETS,
        build_gem_catalog,
        build_profiles,
        fetch_items,
        load_gem_properties,
        load_enchantment_source_items,
        load_item_limit_categories,
        load_wdbc,
        load_spell_item_enchantments,
        SPELL_ITEM_ENCHANTMENT_FMT,
    )
    from build_validation_provisioning import DEFAULT_BWD_DIAGNOSTIC_SHARD_FIXTURE, EQUIPMENT_SLOT_END, REQUIRED_EQUIPMENT_SLOTS, account_commands, apply_gear_profiles, bot_known_spell_ids, bot_talent_spell_ids, build_account_insert_sql, build_character_insert_sql, enchantment_source_item_map, equipment_cache, gem_item_enchant_map, item_limit_category_by_item_map, load_config_with_bwd_diagnostic_shards, load_gear_profiles, load_wdbc_values, normalized_glyphs, required_equipment_slots_for, runtime_safe_enchantments, scenario_report, talent_point_count
    from common import stable_hash, write_json
    from extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf, sanitize_database_url


REPO_ROOT = Path(__file__).resolve().parents[2]


REQUIRED_COLUMNS = {
    "world": {
        "bot_rotation_profile": {
            "id",
            "class_id",
            "spec_tag",
            "role",
            "movement_directive",
            "auto_attack_mode",
            "enabled",
        },
        "bot_rotation_action": {
            "profile_id",
            "spell_id",
            "category",
            "movement_directive",
            "auto_attack_mode",
            "requires_pet",
            "forbids_pet",
            "enabled",
        },
    },
    "characters": {
        "characters": {
            "guid",
            "account",
            "name",
            "slot",
            "race",
            "class",
            "gender",
            "level",
            "xp",
            "money",
            "position_x",
            "position_y",
            "position_z",
            "map",
            "orientation",
            "taximask",
            "online",
            "cinematic",
            "totaltime",
            "leveltime",
            "logout_time",
            "health",
            "power1",
            "talentGroupsCount",
            "activeTalentGroup",
            "talentTree",
            "equipmentCache",
        },
        "item_instance": {
            "guid",
            "itemEntry",
            "owner_guid",
            "creatorGuid",
            "giftCreatorGuid",
            "count",
            "duration",
            "charges",
            "flags",
            "enchantments",
            "randomPropertyType",
            "randomPropertyId",
            "durability",
            "creationTime",
            "text",
        },
        "character_inventory": {"guid", "bag", "slot", "item"},
        "character_bot_pool": {"guid", "role", "class_spec", "enabled", "in_use", "experiment_tags", "notes"},
        "character_glyphs": {"guid", "talentGroup", "glyph1", "glyph2", "glyph3", "glyph4", "glyph5", "glyph6", "glyph7", "glyph8", "glyph9"},
        "character_talent": {"guid", "spell", "talentGroup"},
        "character_spell": {"guid", "spell", "active", "disabled"},
        "character_skills": {"guid", "skill", "value", "max"},
    },
    "auth": {
        "account": {"id", "username"},
    },
}


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def parse_enchantment_payload(text: str) -> list[int]:
    try:
        return [int(token) for token in str(text).split()]
    except ValueError:
        return []


def wdbc_record_ids(path: Path) -> set[int]:
    blob = path.read_bytes()
    if len(blob) < 20 or blob[:4] != b"WDBC":
        raise ValueError(f"{path} is not a WDBC file")
    record_count, _, record_size, _ = struct.unpack_from("<4I", blob, 4)
    return {
        struct.unpack_from("<I", blob, 20 + row_index * record_size)[0]
        for row_index in range(record_count)
    }


def configured_bots(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [bot for scenario in config.get("scenarios", []) for bot in scenario.get("bots", [])]


def account_names(config: dict[str, Any]) -> set[str]:
    return {str(bot.get("account", "")).upper() for bot in configured_bots(config) if bot.get("account")}


def character_names(config: dict[str, Any]) -> set[str]:
    return {str(bot.get("name", "")) for bot in configured_bots(config) if bot.get("name")}


def canonical_rotation_targets(config: dict[str, Any]) -> list[dict[str, Any]]:
    catalog_reference = str(config.get("canonical_target_catalog") or "")
    if not catalog_reference:
        return []
    catalog_path = Path(catalog_reference)
    if not catalog_path.is_absolute():
        catalog_path = REPO_ROOT / catalog_path
    catalog = load_json(catalog_path)
    targets = catalog.get("targets", [])
    if len(targets) != int(catalog.get("target_count") or 0):
        raise ValueError("canonical target catalog is incomplete")
    return targets


def validate_payloads(config: dict[str, Any], dbc_dir: Path, hotfix_url: str | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    enchantments = {int(row["id"]): row for row in load_spell_item_enchantments(dbc_dir)}
    all_enchantment_rows = {
        int(row["values"][0]): row["values"]
        for row in load_wdbc(dbc_dir / "SpellItemEnchantment.dbc", SPELL_ITEM_ENCHANTMENT_FMT)
    }
    all_enchantment_ids = set(all_enchantment_rows)
    spell_ids = wdbc_record_ids(dbc_dir / "Spell.dbc")
    reforge_ids = {
        int(row[0]) for row in load_wdbc_values(dbc_dir / "ItemReforge.dbc", "nifif")
    }
    gem_properties = load_gem_properties(dbc_dir)
    gem_enchantment_ids = {int(row["enchant_id"]) for row in gem_properties.values()}
    gem_item_enchantments = gem_item_enchant_map(dbc_dir)
    enchantment_source_items = enchantment_source_item_map(dbc_dir)
    item_limit_categories_by_item = item_limit_category_by_item_map(dbc_dir)
    item_limit_categories = load_item_limit_categories(dbc_dir)
    if not gem_item_enchantments:
        failures.append({"check": "gem_item_enchant_oracle", "reason": "missing_or_empty"})
    if not enchantment_source_items:
        failures.append({"check": "enchantment_source_item_oracle", "reason": "missing_or_empty"})
    if not item_limit_categories:
        failures.append({"check": "item_limit_category_oracle", "reason": "missing_or_empty"})
    gem_catalog_count = 0
    if hotfix_url:
        try:
            items = fetch_items(hotfix_url, dbc_dir, min_item_level=1, max_required_level=85)
            gem_catalog_count = len(build_gem_catalog(
                items,
                gem_properties,
                enchantments,
                load_enchantment_source_items(dbc_dir),
            ))
        except Exception as exc:  # pragma: no cover - defensive path for unavailable DBs
            failures.append({"check": "gem_catalog", "reason": "unable_to_build_from_items", "detail": str(exc)})

    for scenario in config.get("scenarios", []):
        for bot in scenario.get("bots", []):
            gem_limit_counts: dict[int, int] = {}
            class_spec = str(bot.get("class_spec") or "")
            if class_spec in config.get("talent_builds_by_spec", {}):
                points = talent_point_count(bot, dbc_dir)
                if points != 41:
                    failures.append({"check": "complete_talent_build", "bot": bot.get("name"), "class_spec": class_spec, "points": points})
            equipment = bot.get("equipment", [])
            covered = {int(item.get("slot", -1)) for item in equipment}
            missing_slots = sorted(set(required_equipment_slots_for(equipment)) - covered)
            if missing_slots:
                failures.append({"check": "equipment_slots", "bot": bot.get("name"), "missing_slots": missing_slots})
            for item in equipment:
                item_category = item_limit_categories_by_item.get(int(item.get("item_id") or 0), 0)
                if item_category:
                    gem_limit_counts[item_category] = gem_limit_counts.get(item_category, 0) + 1
                enchant_id = int(item.get("enchant_id") or 0)
                payload = parse_enchantment_payload(item.get("enchantments", ""))
                reforge_id = int(item.get("reforge_id") or 0)
                if enchant_id and enchant_id not in all_enchantment_ids:
                    failures.append({"check": "permanent_enchant_id", "bot": bot.get("name"), "item_id": item.get("item_id"), "enchant_id": enchant_id})
                if enchant_id and len(payload) != 45:
                    failures.append({"check": "enchantment_payload_length", "bot": bot.get("name"), "item_id": item.get("item_id"), "length": len(payload)})
                if enchant_id and payload and payload[0] != enchant_id:
                    failures.append({"check": "permanent_enchant_payload", "bot": bot.get("name"), "item_id": item.get("item_id"), "payload_enchant_id": payload[0], "enchant_id": enchant_id})
                temp_enchant_id = int(item.get("temp_enchant_id") or 0)
                temp_enchant_duration_ms = int(item.get("temp_enchant_duration_ms") or 0)
                if temp_enchant_id and temp_enchant_id not in all_enchantment_ids:
                    failures.append({"check": "temporary_enchant_id", "bot": bot.get("name"), "item_id": item.get("item_id"), "enchant_id": temp_enchant_id})
                if temp_enchant_id and len(payload) != 45:
                    failures.append({"check": "temporary_enchant_payload_length", "bot": bot.get("name"), "item_id": item.get("item_id"), "length": len(payload)})
                if temp_enchant_id and payload and payload[3] != temp_enchant_id:
                    failures.append({"check": "temporary_enchant_payload", "bot": bot.get("name"), "item_id": item.get("item_id"), "payload_enchant_id": payload[3], "enchant_id": temp_enchant_id})
                if temp_enchant_id and (temp_enchant_duration_ms <= 0 or (payload and payload[4] != temp_enchant_duration_ms)):
                    failures.append({"check": "temporary_enchant_duration", "bot": bot.get("name"), "item_id": item.get("item_id"), "payload_duration_ms": payload[4] if len(payload) > 4 else 0, "duration_ms": temp_enchant_duration_ms})
                enchantment_row = all_enchantment_rows.get(temp_enchant_id)
                if enchantment_row:
                    effects = [int(value) for value in enchantment_row[2:5]]
                    effect_args = [int(value) for value in enchantment_row[11:14]]
                    missing_proc_spells = sorted(
                        spell_id
                        for effect, spell_id in zip(effects, effect_args)
                        if effect == 1 and spell_id and spell_id not in spell_ids
                    )
                    if missing_proc_spells:
                        failures.append({"check": "temporary_enchant_combat_spells", "bot": bot.get("name"), "item_id": item.get("item_id"), "enchant_id": temp_enchant_id, "missing_spell_ids": missing_proc_spells})
                socket_colors = item.get("socket_colors") or []
                gem_item_ids = item.get("gem_item_ids") or []
                gem_enchant_ids = item.get("gem_enchant_ids") or []
                if socket_colors and len(gem_item_ids) != len(socket_colors):
                    failures.append({"check": "socket_gem_items", "bot": bot.get("name"), "item_id": item.get("item_id"), "sockets": len(socket_colors), "gems": len(gem_item_ids)})
                if socket_colors and len(gem_enchant_ids) != len(socket_colors):
                    failures.append({"check": "socket_gem_enchants", "bot": bot.get("name"), "item_id": item.get("item_id"), "sockets": len(socket_colors), "gem_enchants": len(gem_enchant_ids)})
                if (gem_item_ids or gem_enchant_ids) and len(gem_item_ids) != len(gem_enchant_ids):
                    failures.append({"check": "socket_gem_mapping_length", "bot": bot.get("name"), "item_id": item.get("item_id"), "gem_items": len(gem_item_ids), "gem_enchants": len(gem_enchant_ids)})
                if len(gem_item_ids) > len(SOCKET_ENCHANTMENT_FIELD_OFFSETS) or len(gem_enchant_ids) > len(SOCKET_ENCHANTMENT_FIELD_OFFSETS):
                    failures.append({"check": "socket_gem_capacity", "bot": bot.get("name"), "item_id": item.get("item_id"), "gem_items": len(gem_item_ids), "gem_enchants": len(gem_enchant_ids), "capacity": len(SOCKET_ENCHANTMENT_FIELD_OFFSETS)})
                for offset, gem_enchant_id in zip(SOCKET_ENCHANTMENT_FIELD_OFFSETS, gem_enchant_ids):
                    if gem_enchant_id and gem_enchant_id not in gem_enchantment_ids:
                        failures.append({"check": "gem_enchant_id", "bot": bot.get("name"), "item_id": item.get("item_id"), "gem_enchant_id": gem_enchant_id})
                    if payload and payload[offset] != int(gem_enchant_id):
                        failures.append({"check": "gem_enchant_payload", "bot": bot.get("name"), "item_id": item.get("item_id"), "offset": offset, "payload_value": payload[offset], "gem_enchant_id": gem_enchant_id})
                for gem_item_id, gem_enchant_id in zip(gem_item_ids, gem_enchant_ids):
                    if int(gem_item_id) == 0 and int(gem_enchant_id) == 0:
                        continue
                    catalog_enchant_id = gem_item_enchantments.get(int(gem_item_id))
                    runtime_source_item_id = enchantment_source_items.get(int(gem_enchant_id))
                    if catalog_enchant_id != int(gem_enchant_id) or runtime_source_item_id != int(gem_item_id):
                        failures.append({
                            "check": "gem_item_enchant_mapping",
                            "bot": bot.get("name"),
                            "item_id": item.get("item_id"),
                            "gem_item_id": int(gem_item_id),
                            "expected_enchant_id": catalog_enchant_id,
                            "actual_enchant_id": int(gem_enchant_id),
                            "runtime_source_item_id": runtime_source_item_id,
                        })
                    category = item_limit_categories_by_item.get(int(gem_item_id), 0)
                    if category:
                        gem_limit_counts[category] = gem_limit_counts.get(category, 0) + 1
                if reforge_id and reforge_id not in reforge_ids:
                    failures.append({"check": "reforge_id", "bot": bot.get("name"), "item_id": item.get("item_id"), "reforge_id": reforge_id})
                if reforge_id and payload and payload[24] != reforge_id:
                    failures.append({"check": "reforge_payload", "bot": bot.get("name"), "item_id": item.get("item_id"), "payload_value": payload[24], "reforge_id": reforge_id})
            for category, count in sorted(gem_limit_counts.items()):
                quantity = int(item_limit_categories.get(category, {}).get("quantity") or 0)
                if not quantity or count > quantity:
                    failures.append({"check": "equipped_item_or_socket_gem_limit", "bot": bot.get("name"), "category": category, "count": count, "quantity": quantity})

    evidence = {
        "enchantment_count": len(enchantments),
        "all_enchantment_id_count": len(all_enchantment_ids),
        "spell_id_count": len(spell_ids),
        "reforge_count": len(reforge_ids),
        "gem_property_count": len(gem_properties),
        "gem_catalog_count": gem_catalog_count,
        "item_limit_category_count": len(item_limit_categories),
        "item_limit_categorized_item_count": len(item_limit_categories_by_item),
        "enchantment_source_item_count": len(enchantment_source_items),
    }
    return failures, evidence


def fetch_columns(database_url: str, table: str) -> set[str]:
    conn = connect_mysql(database_url)
    try:
        with conn.cursor() as cursor:
            cursor.execute(f"SHOW COLUMNS FROM `{table}`")
            return {str(row.get("Field")) for row in cursor.fetchall()}
    finally:
        conn.close()


def fetch_existing_values(database_url: str, table: str, column: str, values: set[str]) -> set[str]:
    if not values:
        return set()
    conn = connect_mysql(database_url)
    try:
        placeholders = ", ".join(["%s"] * len(values))
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT `{column}` FROM `{table}` WHERE `{column}` IN ({placeholders})", tuple(values))
            return {str(row[column]) for row in cursor.fetchall()}
    finally:
        conn.close()


def fetch_runtime_gear(database_url: str, names: set[str]) -> dict[str, dict[str, Any]]:
    if not names:
        return {}
    conn = connect_mysql(database_url)
    try:
        placeholders = ", ".join(["%s"] * len(names))
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT c.guid, c.account, c.name, c.talentTree, c.equipmentCache, ci.slot, ii.itemEntry, ii.durability, ii.enchantments "
                "FROM characters c "
                "LEFT JOIN character_inventory ci ON ci.guid = c.guid AND ci.bag = 0 AND ci.slot < %s "
                "LEFT JOIN item_instance ii ON ii.guid = ci.item "
                f"WHERE c.name IN ({placeholders})",
                (EQUIPMENT_SLOT_END, *tuple(names)),
            )
            rows = cursor.fetchall()
            payload: dict[str, dict[str, Any]] = {}
            for row in rows:
                name = str(row["name"])
                entry = payload.setdefault(name, {"guid": int(row["guid"]), "account_id": int(row.get("account") or 0), "talentTree": str(row.get("talentTree") or ""), "equipmentCache": str(row.get("equipmentCache") or ""), "items": {}})
                entry["guid"] = int(row["guid"])
                entry["account_id"] = int(row.get("account") or 0)
                if row.get("slot") is not None:
                    entry["items"][int(row["slot"])] = {
                        "item_id": int(row.get("itemEntry") or 0),
                        "durability": int(row.get("durability") or 0),
                        "enchantments": parse_enchantment_payload(str(row.get("enchantments") or "")),
                    }

            cursor.execute(
                "SELECT c.name, cg.glyph1, cg.glyph2, cg.glyph3, cg.glyph4, cg.glyph5, cg.glyph6, cg.glyph7, cg.glyph8, cg.glyph9 "
                "FROM characters c LEFT JOIN character_glyphs cg ON cg.guid = c.guid AND cg.talentGroup = 0 "
                f"WHERE c.name IN ({placeholders})",
                tuple(names),
            )
            for row in cursor.fetchall():
                entry = payload.setdefault(str(row["name"]), {"guid": 0, "talentTree": "", "equipmentCache": "", "items": {}})
                entry["glyphs"] = [int(row.get(f"glyph{i}") or 0) for i in range(1, 10)]

            cursor.execute(
                "SELECT c.name, ct.spell FROM characters c JOIN character_talent ct ON ct.guid = c.guid AND ct.talentGroup = 0 "
                f"WHERE c.name IN ({placeholders})",
                tuple(names),
            )
            for row in cursor.fetchall():
                payload.setdefault(str(row["name"]), {"guid": 0, "talentTree": "", "equipmentCache": "", "items": {}}).setdefault("talent_spells", set()).add(int(row["spell"]))

            cursor.execute(
                "SELECT c.name, cs.spell FROM characters c JOIN character_spell cs ON cs.guid = c.guid AND cs.active = 1 AND cs.disabled = 0 "
                f"WHERE c.name IN ({placeholders})",
                tuple(names),
            )
            for row in cursor.fetchall():
                payload.setdefault(str(row["name"]), {"guid": 0, "talentTree": "", "equipmentCache": "", "items": {}}).setdefault("known_spells", set()).add(int(row["spell"]))
            return payload
    finally:
        conn.close()


def fetch_runtime_rotation_profiles(
    database_url: str,
    profile_keys: set[tuple[int, str, str]],
) -> dict[tuple[int, str, str], dict[str, Any]]:
    if not profile_keys:
        return {}
    conn = connect_mysql(database_url)
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                "SELECT p.id, p.class_id, p.spec_tag, p.role, p.enabled, "
                "p.movement_directive AS profile_movement_directive, "
                "p.auto_attack_mode AS profile_auto_attack_mode, "
                "a.spell_id, a.category, a.movement_directive, a.auto_attack_mode, "
                "a.requires_pet, a.forbids_pet "
                "FROM bot_rotation_profile p "
                "LEFT JOIN bot_rotation_action a ON a.profile_id = p.id AND a.enabled = 1"
            )
            profiles: dict[tuple[int, str, str], dict[str, Any]] = {}
            for row in cursor.fetchall():
                key = (int(row["class_id"]), str(row["spec_tag"]), str(row["role"]))
                if key not in profile_keys:
                    continue
                profile = profiles.setdefault(
                    key,
                    {
                        "profile_id": int(row["id"]),
                        "enabled": bool(row["enabled"]),
                        "movement_directive": str(row.get("profile_movement_directive") or ""),
                        "auto_attack_mode": str(row.get("profile_auto_attack_mode") or ""),
                        "actions": [],
                    },
                )
                if row.get("spell_id") is not None:
                    profile["actions"].append(
                        {
                            "spell_id": int(row.get("spell_id") or 0),
                            "category": str(row.get("category") or ""),
                            "movement_directive": str(row.get("movement_directive") or ""),
                            "auto_attack_mode": str(row.get("auto_attack_mode") or ""),
                            "requires_pet": bool(row.get("requires_pet")),
                            "forbids_pet": bool(row.get("forbids_pet")),
                        }
                    )
            return profiles
    finally:
        conn.close()


def validate_database(
    config: dict[str, Any],
    worldserver_conf: Path,
    require_applied: bool = False,
    dbc_dir: Path = Path("data/dbc/enUS"),
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    auth_url = database_url_from_worldserver_conf(worldserver_conf, "LoginDatabaseInfo")
    character_url = database_url_from_worldserver_conf(worldserver_conf, "CharacterDatabaseInfo")
    canonical_targets = canonical_rotation_targets(config)
    world_url = database_url_from_worldserver_conf(worldserver_conf, "WorldDatabaseInfo") if canonical_targets else ""

    if canonical_targets:
        for table, required in REQUIRED_COLUMNS["world"].items():
            columns = fetch_columns(world_url, table)
            missing = sorted(required - columns)
            if missing:
                failures.append({"check": "world_schema_columns", "table": table, "missing_columns": missing})
    for table, required in REQUIRED_COLUMNS["auth"].items():
        columns = fetch_columns(auth_url, table)
        missing = sorted(required - columns)
        if missing:
            failures.append({"check": "auth_schema_columns", "table": table, "missing_columns": missing})
    for table, required in REQUIRED_COLUMNS["characters"].items():
        columns = fetch_columns(character_url, table)
        missing = sorted(required - columns)
        if missing:
            failures.append({"check": "character_schema_columns", "table": table, "missing_columns": missing})

    expected_accounts = account_names(config)
    existing_accounts = fetch_existing_values(auth_url, "account", "username", expected_accounts)
    missing_accounts = sorted(expected_accounts - existing_accounts)
    if missing_accounts:
        failures.append({"check": "validation_accounts", "missing_accounts": missing_accounts, "recovery": "apply generated provision_accounts.sql or run account_commands.txt in the worldserver console"})

    expected_characters = character_names(config)
    existing_characters = fetch_existing_values(character_url, "characters", "name", expected_characters)
    missing_characters = sorted(expected_characters - existing_characters)
    if require_applied and missing_characters:
        failures.append({"check": "validation_characters_applied", "missing_characters": missing_characters, "recovery": "apply generated provision_characters.sql after creating accounts"})

    runtime_gear_report: dict[str, Any] = {}
    runtime: dict[str, dict[str, Any]] = {}
    gem_mapping = gem_item_enchant_map(dbc_dir)
    if require_applied and not missing_characters:
        runtime = fetch_runtime_gear(character_url, expected_characters)
        for bot in configured_bots(config):
            name = str(bot.get("name"))
            actual_identity = runtime.get(name, {})
            expected_guid = bot.get("expected_character_guid")
            if expected_guid is not None and int(actual_identity.get("guid") or 0) != int(expected_guid):
                failures.append({"check": "runtime_character_guid", "bot": name, "expected": int(expected_guid), "actual": int(actual_identity.get("guid") or 0)})
            expected_account_id = bot.get("expected_account_id")
            if expected_account_id is not None and int(actual_identity.get("account_id") or 0) != int(expected_account_id):
                failures.append({"check": "runtime_account_id", "bot": name, "expected": int(expected_account_id), "actual": int(actual_identity.get("account_id") or 0)})
            equipment = bot.get("equipment", [])
            expected_slots = set(required_equipment_slots_for(equipment))
            expected_by_slot = {int(item.get("slot", -1)): int(item.get("item_id") or 0) for item in equipment}
            expected_modifier_payload_by_slot = {
                int(item.get("slot", -1)): parse_enchantment_payload(runtime_safe_enchantments(item, gem_mapping))
                for item in equipment
            }
            expected_durability_by_slot = {int(item.get("slot", -1)): int(item.get("durability") or 0) for item in equipment}
            actual = runtime.get(name, {"items": {}, "talentTree": "", "equipmentCache": "", "glyphs": [], "talent_spells": set(), "known_spells": set()})
            actual_items = actual.get("items", {})
            expected_talent_tree = int(bot.get("primary_talent_tree_id") or 0)
            talent_tree_tokens = [int(token) for token in str(actual.get("talentTree") or "").split() if token.lstrip("-").isdigit()]
            actual_talent_tree = talent_tree_tokens[0] if talent_tree_tokens else None
            expected_talent_spells = set(bot_talent_spell_ids(bot))
            actual_talent_spells = {int(spell) for spell in actual.get("talent_spells", set())}
            missing_talent_spells = sorted(expected_talent_spells - actual_talent_spells)
            expected_known_spells = set(bot_known_spell_ids(bot))
            actual_known_spells = {int(spell) for spell in actual.get("known_spells", set())}
            missing_known_spells = sorted(expected_known_spells - actual_known_spells)
            missing_slots = sorted(slot for slot in expected_slots if int(actual_items.get(slot, {}).get("item_id") or 0) <= 0)
            wrong_items = [
                {"slot": slot, "expected_item_id": item_id, "actual_item_id": int(actual_items.get(slot, {}).get("item_id") or 0)}
                for slot, item_id in sorted(expected_by_slot.items())
                if slot in expected_slots and int(actual_items.get(slot, {}).get("item_id") or 0) != item_id
            ]
            modifier_offsets = (0, *SOCKET_ENCHANTMENT_FIELD_OFFSETS, 24)
            wrong_modifiers = []
            for slot, expected_payload in sorted(expected_modifier_payload_by_slot.items()):
                actual_payload = actual_items.get(slot, {}).get("enchantments", [])
                mismatches = [
                    {
                        "offset": offset,
                        "expected": expected_payload[offset] if len(expected_payload) > offset else None,
                        "actual": actual_payload[offset] if len(actual_payload) > offset else None,
                    }
                    for offset in modifier_offsets
                    if (expected_payload[offset] if len(expected_payload) > offset else None)
                    != (actual_payload[offset] if len(actual_payload) > offset else None)
                ]
                if mismatches:
                    wrong_modifiers.append({"slot": slot, "mismatches": mismatches})
            zero_durability = sorted(
                slot
                for slot, item in actual_items.items()
                if slot in expected_slots
                and expected_durability_by_slot.get(slot, 0) > 0
                and int(item.get("durability") or 0) <= 0
            )
            expected_cache = equipment_cache(equipment)
            cache_tokens = [int(token) for token in str(actual.get("equipmentCache") or "").split() if token.lstrip("-").isdigit()]
            visible_missing = sorted(slot for slot in expected_slots if len(cache_tokens) <= slot * 2 or cache_tokens[slot * 2] != expected_by_slot.get(slot, 0))
            expected_glyphs = normalized_glyphs(bot)
            actual_glyphs = [int(value or 0) for value in actual.get("glyphs", [])]
            invalid_actual_glyphs = [value for value in actual_glyphs if value < 0]
            glyphs_missing = sorted(set(expected_glyphs) - set(actual_glyphs)) if expected_glyphs else []
            avg_item_level = None
            if equipment:
                levels = [int(item.get("item_level") or item.get("ItemLevel") or 0) for item in equipment]
                avg_item_level = round(sum(levels) / len(levels), 2) if levels else 0
            runtime_gear_report[name] = {
                "talent_tree": {"expected": expected_talent_tree, "actual": actual_talent_tree},
                "missing_talent_spells": missing_talent_spells,
                "missing_known_spells": missing_known_spells,
                "equipped_slots": sorted(actual_items),
                "expected_slots": sorted(expected_slots),
                "missing_slots": missing_slots,
                "wrong_items": wrong_items,
                "wrong_modifiers": wrong_modifiers,
                "zero_durability_slots": zero_durability,
                "visible_missing_slots": visible_missing,
                "average_item_level": avg_item_level,
                "glyphs_missing": glyphs_missing,
                "invalid_actual_glyphs": invalid_actual_glyphs,
            }
            if actual_talent_tree != expected_talent_tree:
                failures.append({"check": "runtime_talent_tree", "bot": name, "expected_talent_tree": expected_talent_tree, "actual_talent_tree": actual_talent_tree})
            if missing_talent_spells:
                failures.append({"check": "runtime_character_talent", "bot": name, "missing_spells": missing_talent_spells})
            if missing_known_spells:
                failures.append({"check": "runtime_character_spell", "bot": name, "missing_spells": missing_known_spells})
            if missing_slots:
                failures.append({"check": "runtime_equipment_slots", "bot": name, "missing_slots": missing_slots})
            if wrong_items:
                failures.append({"check": "runtime_equipment_items", "bot": name, "wrong_items": wrong_items})
            if wrong_modifiers:
                failures.append({"check": "runtime_equipment_modifiers", "bot": name, "wrong_modifiers": wrong_modifiers})
            if zero_durability:
                failures.append({"check": "runtime_equipment_durability", "bot": name, "slots": zero_durability})
            if visible_missing:
                failures.append({"check": "runtime_equipment_cache", "bot": name, "visible_missing_slots": visible_missing, "expected_cache": expected_cache})
            if invalid_actual_glyphs or glyphs_missing:
                failures.append({"check": "runtime_glyphs", "bot": name, "missing_glyphs": glyphs_missing, "invalid_glyphs": invalid_actual_glyphs})

    expected_profiles = {
        (
            int(row["runtime_rotation_profile"]["class_id"]),
            str(row["runtime_rotation_profile"]["spec_tag"]),
            str(row["runtime_rotation_profile"]["role"]),
        ): row
        for row in canonical_targets
    }
    runtime_profiles = fetch_runtime_rotation_profiles(world_url, set(expected_profiles))
    runtime_profile_report: dict[str, Any] = {}
    for key, target in expected_profiles.items():
        target_id = str(target["spec_target_id"])
        profile = runtime_profiles.get(key)
        if profile is None or not profile.get("enabled"):
            failures.append(
                {
                    "check": "runtime_rotation_profile",
                    "reason": "missing_db_rotation_profile",
                    "spec_target_id": target_id,
                    "identity": f"{key[0]}:{key[1]}:{key[2]}",
                }
            )
            runtime_profile_report[target_id] = {
                "identity": f"{key[0]}:{key[1]}:{key[2]}",
                "state": "missing_db_rotation_profile",
                "enabled_action_count": 0,
                "known_action_count": 0,
            }
            continue
        actions = [
            action
            for action in profile.get("actions", [])
            if int(action.get("spell_id") or 0) > 0 and str(action.get("category") or "")
        ]
        name = str((target.get("provisioning_bot") or {}).get("name") or "")
        character = runtime.get(name, {})
        known_spells = {
            int(spell)
            for spell in character.get("known_spells", set()) | character.get("talent_spells", set())
        }
        known_actions = [action for action in actions if int(action["spell_id"]) in known_spells]
        capabilities = set(target.get("pet_form_stance_presence") or [])
        pet_contract_state = "ready"
        if "felguard_pet" in capabilities:
            summon_felguard = next(
                (action for action in actions if int(action["spell_id"]) == 30146),
                None,
            )
            demon_soul = next(
                (action for action in actions if int(action["spell_id"]) == 77801),
                None,
            )
            if not summon_felguard or not summon_felguard.get("forbids_pet"):
                pet_contract_state = "felguard_summon_missing_or_ungated"
                failures.append(
                    {
                        "check": "runtime_pet_contract",
                        "reason": "felguard_summon_missing_or_ungated",
                        "spec_target_id": target_id,
                        "identity": f"{key[0]}:{key[1]}:{key[2]}",
                    }
                )
            if not demon_soul or not demon_soul.get("requires_pet"):
                pet_contract_state = "demon_soul_missing_pet_gate"
                failures.append(
                    {
                        "check": "runtime_pet_contract",
                        "reason": "demon_soul_missing_pet_gate",
                        "spec_target_id": target_id,
                        "identity": f"{key[0]}:{key[1]}:{key[2]}",
                    }
                )
        movement_directives = {
            str(profile.get("movement_directive") or ""),
            *(str(action.get("movement_directive") or "") for action in actions),
        } - {""}
        auto_attack_modes = {
            str(profile.get("auto_attack_mode") or ""),
            *(str(action.get("auto_attack_mode") or "") for action in actions),
        } - {""}
        state = pet_contract_state
        if not actions:
            state = "db_rotation_profile_has_no_enabled_actions"
            failures.append(
                {
                    "check": "runtime_rotation_profile",
                    "reason": state,
                    "spec_target_id": target_id,
                    "identity": f"{key[0]}:{key[1]}:{key[2]}",
                }
            )
        elif require_applied and not known_actions:
            state = "db_rotation_profile_has_no_known_spells"
            failures.append(
                {
                    "check": "runtime_rotation_profile",
                    "reason": state,
                    "spec_target_id": target_id,
                    "bot": name,
                    "identity": f"{key[0]}:{key[1]}:{key[2]}",
                }
            )
        if not movement_directives:
            state = "db_rotation_profile_missing_movement_directives"
            failures.append(
                {
                    "check": "runtime_rotation_profile",
                    "reason": state,
                    "spec_target_id": target_id,
                    "identity": f"{key[0]}:{key[1]}:{key[2]}",
                }
            )
        if not auto_attack_modes:
            state = "db_rotation_profile_missing_auto_attack_mode"
            failures.append(
                {
                    "check": "runtime_rotation_profile",
                    "reason": state,
                    "spec_target_id": target_id,
                    "identity": f"{key[0]}:{key[1]}:{key[2]}",
                }
            )
        runtime_profile_report[target_id] = {
            "identity": f"{key[0]}:{key[1]}:{key[2]}",
            "state": state,
            "enabled_action_count": len(actions),
            "known_action_count": len(known_actions),
            "pet_contract_state": pet_contract_state,
            "movement_directives": sorted(movement_directives),
            "auto_attack_modes": sorted(auto_attack_modes),
        }

    evidence = {
        "world_database": sanitize_database_url(world_url) if world_url else None,
        "auth_database": sanitize_database_url(auth_url),
        "character_database": sanitize_database_url(character_url),
        "expected_accounts": len(expected_accounts),
        "existing_accounts": len(existing_accounts),
        "expected_characters": len(expected_characters),
        "existing_characters": len(existing_characters),
        "require_applied": require_applied,
        "runtime_gear": runtime_gear_report,
        "runtime_rotation_profiles": {
            "expected": len(expected_profiles),
            "existing_enabled": sum(1 for profile in runtime_profiles.values() if profile.get("enabled")),
            "ready": sum(1 for row in runtime_profile_report.values() if row.get("state") == "ready"),
            "targets": runtime_profile_report,
        },
    }
    return failures, evidence


def load_or_build_gear_profiles(path: Path, config: dict[str, Any], dbc_dir: Path, hotfix_url: str | None) -> dict[str, Any]:
    profiles = load_gear_profiles(path)
    if profiles:
        return profiles
    items = fetch_items(hotfix_url or "", dbc_dir, min_item_level=1, max_required_level=85)
    enchantments = load_spell_item_enchantments(dbc_dir)
    gems = build_gem_catalog(
        items,
        load_gem_properties(dbc_dir),
        {int(enchantment["id"]): enchantment for enchantment in enchantments},
        load_enchantment_source_items(dbc_dir),
    )
    return build_profiles(config, items, enchantments, gems, item_limit_categories=load_item_limit_categories(dbc_dir))


def validate_generated_artifacts(config: dict[str, Any], provisioning_report_path: Path, dbc_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    output_dir = provisioning_report_path.parent
    expected_report = scenario_report(config)
    expected_payloads = {
        "account_commands.txt": account_commands(config).encode("utf-8"),
        "provision_accounts.sql": build_account_insert_sql(config).encode("utf-8"),
        "provision_characters.sql": build_character_insert_sql(config, gem_mapping=gem_item_enchant_map(dbc_dir)).encode("utf-8"),
        "report.json": (json.dumps(expected_report, indent=2, sort_keys=True, default=str) + "\n").encode("utf-8"),
    }
    manifest = load_json(output_dir / "manifest.json")
    manifest_hashes = manifest.get("output_sha256", {}) if isinstance(manifest, dict) else {}
    failures: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {"output_sha256": {}, "expected_output_sha256": {}}
    if manifest.get("config_hash") != stable_hash(config):
        failures.append({"check": "provisioning_manifest_config_hash"})
    for name, expected in sorted(expected_payloads.items()):
        path = output_dir / name
        expected_hash = hashlib.sha256(expected).hexdigest()
        actual = path.read_bytes() if path.is_file() else None
        actual_hash = hashlib.sha256(actual).hexdigest() if actual is not None else None
        evidence["expected_output_sha256"][name] = expected_hash
        evidence["output_sha256"][name] = actual_hash
        if actual_hash != expected_hash:
            failures.append({"check": "provisioning_output_content", "path": name, "expected_sha256": expected_hash, "actual_sha256": actual_hash})
        if manifest_hashes.get(name) != actual_hash:
            failures.append({"check": "provisioning_manifest_output_hash", "path": name, "manifest_sha256": manifest_hashes.get(name), "actual_sha256": actual_hash})
    evidence["manifest_hashes_complete"] = set(manifest_hashes) == set(expected_payloads)
    if not evidence["manifest_hashes_complete"]:
        failures.append({"check": "provisioning_manifest_output_set", "expected": sorted(expected_payloads), "actual": sorted(manifest_hashes)})
    return failures, evidence


def build_report(
    config: dict[str, Any],
    provisioning_report: dict[str, Any],
    payload_failures: list[dict[str, Any]],
    payload_evidence: dict[str, Any],
    db_failures: list[dict[str, Any]],
    db_evidence: dict[str, Any],
    generated_failures: list[dict[str, Any]] | None = None,
    generated_evidence: dict[str, Any] | None = None,
) -> dict[str, Any]:
    generated_failures = generated_failures or []
    failures = payload_failures + generated_failures + db_failures
    return {
        "schema": "bot_validation_provisioning_verifier_report_v1",
        "config_hash": stable_hash(config),
        "provisioning_all_ready": bool(provisioning_report.get("all_ready")),
        "payload_valid": not payload_failures,
        "database_valid": not db_failures if db_evidence else None,
        "all_passed": bool(provisioning_report.get("all_ready")) and not failures,
        "failure_count": len(failures),
        "failures": failures,
        "payload_evidence": payload_evidence,
        "generated_artifact_evidence": generated_evidence or {},
        "database_evidence": db_evidence,
        "runtime_ml_control": "disabled_teacher_policy_validation_only",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated Stonecore/BWD prepared-character provisioning artifacts without applying them.")
    parser.add_argument("--config", type=Path, default=Path("experiments/configs/validation_provisioning_cata_001.json"))
    parser.add_argument("--gear-profiles", type=Path, default=Path("dataset/validation_gear_profiles/profiles.json"))
    parser.add_argument("--bwd-diagnostic-shard-fixture", type=Path, default=DEFAULT_BWD_DIAGNOSTIC_SHARD_FIXTURE)
    parser.add_argument("--provisioning-report", type=Path, default=Path("dataset/validation_provisioning/report.json"))
    parser.add_argument("--worldserver-conf", type=Path, default=Path("trinity-worldserver-test.conf"))
    parser.add_argument("--dbc-dir", type=Path, default=Path("data/dbc/enUS"))
    parser.add_argument("--output", type=Path, default=Path("dataset/validation_provisioning/verifier_report.json"))
    parser.add_argument("--check-db", action="store_true", help="Check configured auth/characters schema and validation account presence.")
    parser.add_argument("--require-applied", action="store_true", help="Fail if validation characters are not already present in the characters DB.")
    args = parser.parse_args()

    base_config = load_config_with_bwd_diagnostic_shards(args.config, args.bwd_diagnostic_shard_fixture)
    hotfix_url = database_url_from_worldserver_conf(args.worldserver_conf, "HotfixDatabaseInfo") if args.worldserver_conf.exists() else None
    config = apply_gear_profiles(base_config, load_or_build_gear_profiles(args.gear_profiles, base_config, args.dbc_dir, hotfix_url))
    provisioning_report = load_json(args.provisioning_report) or scenario_report(config)
    payload_failures, payload_evidence = validate_payloads(config, args.dbc_dir, hotfix_url)
    generated_failures, generated_evidence = validate_generated_artifacts(config, args.provisioning_report, args.dbc_dir)
    db_failures: list[dict[str, Any]] = []
    db_evidence: dict[str, Any] = {}
    if args.check_db or args.require_applied:
        db_failures, db_evidence = validate_database(config, args.worldserver_conf, require_applied=args.require_applied, dbc_dir=args.dbc_dir)

    report = build_report(config, provisioning_report, payload_failures, payload_evidence, db_failures, db_evidence, generated_failures, generated_evidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
