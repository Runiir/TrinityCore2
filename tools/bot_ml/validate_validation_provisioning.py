from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .build_validation_gear_profiles import (
        SOCKET_ENCHANTMENT_FIELD_OFFSETS,
        build_gem_catalog,
        build_profiles,
        fetch_items,
        load_gem_properties,
        load_spell_item_enchantments,
    )
    from .build_validation_provisioning import REQUIRED_EQUIPMENT_SLOTS, apply_gear_profiles, load_config, load_gear_profiles, scenario_report
    from .common import stable_hash, write_json
    from .extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf, sanitize_database_url
except ImportError:
    from build_validation_gear_profiles import (
        SOCKET_ENCHANTMENT_FIELD_OFFSETS,
        build_gem_catalog,
        build_profiles,
        fetch_items,
        load_gem_properties,
        load_spell_item_enchantments,
    )
    from build_validation_provisioning import REQUIRED_EQUIPMENT_SLOTS, apply_gear_profiles, load_config, load_gear_profiles, scenario_report
    from common import stable_hash, write_json
    from extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf, sanitize_database_url


REQUIRED_COLUMNS = {
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


def configured_bots(config: dict[str, Any]) -> list[dict[str, Any]]:
    return [bot for scenario in config.get("scenarios", []) for bot in scenario.get("bots", [])]


def account_names(config: dict[str, Any]) -> set[str]:
    return {str(bot.get("account", "")).upper() for bot in configured_bots(config) if bot.get("account")}


def character_names(config: dict[str, Any]) -> set[str]:
    return {str(bot.get("name", "")) for bot in configured_bots(config) if bot.get("name")}


def validate_payloads(config: dict[str, Any], dbc_dir: Path, hotfix_url: str | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    enchantments = {int(row["id"]): row for row in load_spell_item_enchantments(dbc_dir)}
    gem_properties = load_gem_properties(dbc_dir)
    gem_enchantment_ids = {int(row["enchant_id"]) for row in gem_properties.values()}
    gem_catalog_count = 0
    if hotfix_url:
        try:
            items = fetch_items(hotfix_url, dbc_dir, min_item_level=1, max_required_level=85)
            gem_catalog_count = len(build_gem_catalog(items, gem_properties, enchantments))
        except Exception as exc:  # pragma: no cover - defensive path for unavailable DBs
            failures.append({"check": "gem_catalog", "reason": "unable_to_build_from_items", "detail": str(exc)})

    for scenario in config.get("scenarios", []):
        for bot in scenario.get("bots", []):
            equipment = bot.get("equipment", [])
            covered = {int(item.get("slot", -1)) for item in equipment}
            missing_slots = sorted(set(REQUIRED_EQUIPMENT_SLOTS) - covered)
            if missing_slots:
                failures.append({"check": "equipment_slots", "bot": bot.get("name"), "missing_slots": missing_slots})
            for item in equipment:
                enchant_id = int(item.get("enchant_id") or 0)
                payload = parse_enchantment_payload(item.get("enchantments", ""))
                if enchant_id and enchant_id not in enchantments:
                    failures.append({"check": "permanent_enchant_id", "bot": bot.get("name"), "item_id": item.get("item_id"), "enchant_id": enchant_id})
                if enchant_id and len(payload) != 45:
                    failures.append({"check": "enchantment_payload_length", "bot": bot.get("name"), "item_id": item.get("item_id"), "length": len(payload)})
                if enchant_id and payload and payload[0] != enchant_id:
                    failures.append({"check": "permanent_enchant_payload", "bot": bot.get("name"), "item_id": item.get("item_id"), "payload_enchant_id": payload[0], "enchant_id": enchant_id})
                socket_colors = item.get("socket_colors") or []
                gem_item_ids = item.get("gem_item_ids") or []
                gem_enchant_ids = item.get("gem_enchant_ids") or []
                if socket_colors and len(gem_item_ids) != len(socket_colors):
                    failures.append({"check": "socket_gem_items", "bot": bot.get("name"), "item_id": item.get("item_id"), "sockets": len(socket_colors), "gems": len(gem_item_ids)})
                if socket_colors and len(gem_enchant_ids) != len(socket_colors):
                    failures.append({"check": "socket_gem_enchants", "bot": bot.get("name"), "item_id": item.get("item_id"), "sockets": len(socket_colors), "gem_enchants": len(gem_enchant_ids)})
                for offset, gem_enchant_id in zip(SOCKET_ENCHANTMENT_FIELD_OFFSETS, gem_enchant_ids):
                    if gem_enchant_id not in gem_enchantment_ids:
                        failures.append({"check": "gem_enchant_id", "bot": bot.get("name"), "item_id": item.get("item_id"), "gem_enchant_id": gem_enchant_id})
                    if payload and payload[offset] != int(gem_enchant_id):
                        failures.append({"check": "gem_enchant_payload", "bot": bot.get("name"), "item_id": item.get("item_id"), "offset": offset, "payload_value": payload[offset], "gem_enchant_id": gem_enchant_id})

    evidence = {
        "enchantment_count": len(enchantments),
        "gem_property_count": len(gem_properties),
        "gem_catalog_count": gem_catalog_count,
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


def validate_database(config: dict[str, Any], worldserver_conf: Path, require_applied: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    auth_url = database_url_from_worldserver_conf(worldserver_conf, "LoginDatabaseInfo")
    character_url = database_url_from_worldserver_conf(worldserver_conf, "CharacterDatabaseInfo")

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

    evidence = {
        "auth_database": sanitize_database_url(auth_url),
        "character_database": sanitize_database_url(character_url),
        "expected_accounts": len(expected_accounts),
        "existing_accounts": len(existing_accounts),
        "expected_characters": len(expected_characters),
        "existing_characters": len(existing_characters),
        "require_applied": require_applied,
    }
    return failures, evidence


def load_or_build_gear_profiles(path: Path, config: dict[str, Any], dbc_dir: Path, hotfix_url: str | None) -> dict[str, Any]:
    profiles = load_gear_profiles(path)
    if profiles:
        return profiles
    items = fetch_items(hotfix_url or "", dbc_dir, min_item_level=1, max_required_level=85)
    enchantments = load_spell_item_enchantments(dbc_dir)
    gems = build_gem_catalog(items, load_gem_properties(dbc_dir), {int(enchantment["id"]): enchantment for enchantment in enchantments})
    return build_profiles(config, items, enchantments, gems)


def build_report(
    config: dict[str, Any],
    provisioning_report: dict[str, Any],
    payload_failures: list[dict[str, Any]],
    payload_evidence: dict[str, Any],
    db_failures: list[dict[str, Any]],
    db_evidence: dict[str, Any],
) -> dict[str, Any]:
    failures = payload_failures + db_failures
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
        "database_evidence": db_evidence,
        "runtime_ml_control": "disabled_teacher_policy_validation_only",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate generated Stonecore/BWD prepared-character provisioning artifacts without applying them.")
    parser.add_argument("--config", type=Path, default=Path("experiments/configs/validation_provisioning_cata_001.json"))
    parser.add_argument("--gear-profiles", type=Path, default=Path("dataset/validation_gear_profiles/profiles.json"))
    parser.add_argument("--provisioning-report", type=Path, default=Path("dataset/validation_provisioning/report.json"))
    parser.add_argument("--worldserver-conf", type=Path, default=Path("trinity-worldserver-test.conf"))
    parser.add_argument("--dbc-dir", type=Path, default=Path("data/dbc/enUS"))
    parser.add_argument("--output", type=Path, default=Path("dataset/validation_provisioning/verifier_report.json"))
    parser.add_argument("--check-db", action="store_true", help="Check configured auth/characters schema and validation account presence.")
    parser.add_argument("--require-applied", action="store_true", help="Fail if validation characters are not already present in the characters DB.")
    args = parser.parse_args()

    base_config = load_config(args.config)
    hotfix_url = database_url_from_worldserver_conf(args.worldserver_conf, "HotfixDatabaseInfo") if args.worldserver_conf.exists() else None
    config = apply_gear_profiles(base_config, load_or_build_gear_profiles(args.gear_profiles, base_config, args.dbc_dir, hotfix_url))
    provisioning_report = load_json(args.provisioning_report) or scenario_report(config)
    payload_failures, payload_evidence = validate_payloads(config, args.dbc_dir, hotfix_url)
    db_failures: list[dict[str, Any]] = []
    db_evidence: dict[str, Any] = {}
    if args.check_db or args.require_applied:
        db_failures, db_evidence = validate_database(config, args.worldserver_conf, require_applied=args.require_applied)

    report = build_report(config, provisioning_report, payload_failures, payload_evidence, db_failures, db_evidence)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
