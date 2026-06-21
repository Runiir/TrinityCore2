from __future__ import annotations

import argparse
import hashlib
import json
import struct
from pathlib import Path
from typing import Any

try:
    from .common import stable_hash, write_json
    from .validation_profile_manifests import DEFAULT_ACTION_PROFILE_MANIFEST, load_action_profile_manifest
except ImportError:
    from common import stable_hash, write_json
    from validation_profile_manifests import DEFAULT_ACTION_PROFILE_MANIFEST, load_action_profile_manifest


ROLE_REQUIREMENTS = {
    "stonecore_5n": {"tank": 1, "healer": 1, "dps": 3},
    "blackwing_descent_10n": {"tank": 2, "healer": 3, "dps": 5},
}

REQUIRED_EQUIPMENT_SLOTS = [0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
EQUIPMENT_SLOT_END = 19
INVENTORY_BAG_SLOTS = 4
DEFAULT_DBC_DIR = Path("data/dbc/enUS")
SPELL_EFFECT_LEARN_GLYPH = 74
ITEM_SPARSE_FMT = "niiiffiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiifiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiisssssiiiiiiiiiiiiiiiiiiiiiifiiifii"
_GLYPH_ITEM_TO_PROPERTY_CACHE: dict[Path, dict[int, int]] = {}


def required_equipment_slots_for(equipment: list[dict[str, Any]]) -> list[int]:
    slots = set(REQUIRED_EQUIPMENT_SLOTS)
    if any(int(item.get("slot", -1)) == 15 and int(item.get("inventory_type", 0)) == 17 for item in equipment):
        slots.discard(16)
    return sorted(slots)


def read_dbc_string(data: bytes, offset: int) -> str:
    if offset <= 0 or offset >= len(data):
        return ""
    end = data.find(b"\0", offset)
    if end == -1:
        end = len(data)
    return data[offset:end].decode("utf-8", errors="replace")


def load_wdb2_values(path: Path, fmt: str) -> list[list[Any]]:
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
    return parse_dbc_records(records_blob, string_blob, record_count, record_size, fmt)


def load_wdbc_values(path: Path, fmt: str) -> list[list[Any]]:
    blob = path.read_bytes()
    if len(blob) < 20 or blob[:4] != b"WDBC":
        raise ValueError(f"{path} is not a WDBC file")
    record_count, field_count, record_size, string_size = struct.unpack_from("<4I", blob, 4)
    if field_count != len(fmt):
        raise ValueError(f"{path} field count {field_count} does not match format length {len(fmt)}")
    records_offset = 20
    records_blob = blob[records_offset:records_offset + (record_count * record_size)]
    string_blob = blob[records_offset + (record_count * record_size):records_offset + (record_count * record_size) + string_size]
    return parse_dbc_records(records_blob, string_blob, record_count, record_size, fmt)


def parse_dbc_records(records_blob: bytes, string_blob: bytes, record_count: int, record_size: int, fmt: str) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for row_index in range(record_count):
        row_offset = row_index * record_size
        values: list[Any] = []
        field_offset = 0
        for field_type in fmt:
            if field_type == "f":
                values.append(struct.unpack_from("<f", records_blob, row_offset + field_offset)[0])
            elif field_type == "s":
                values.append(read_dbc_string(string_blob, struct.unpack_from("<I", records_blob, row_offset + field_offset)[0]))
            else:
                raw = struct.unpack_from("<I", records_blob, row_offset + field_offset)[0]
                if field_type == "i" and raw >= 0x80000000:
                    raw -= 0x100000000
                values.append(raw)
            field_offset += 4
        rows.append(values)
    return rows


def glyph_item_to_property_map(dbc_dir: Path = DEFAULT_DBC_DIR) -> dict[int, int]:
    dbc_dir = dbc_dir.resolve()
    cached = _GLYPH_ITEM_TO_PROPERTY_CACHE.get(dbc_dir)
    if cached is not None:
        return cached
    if not (dbc_dir / "Item-sparse.db2").exists() or not (dbc_dir / "SpellEffect.dbc").exists():
        _GLYPH_ITEM_TO_PROPERTY_CACHE[dbc_dir] = {}
        return {}

    glyph_property_by_teach_spell: dict[int, int] = {}
    for values in load_wdbc_values(dbc_dir / "SpellEffect.dbc", "nifiiiffiiiiiifiifiiiiiiiix"):
        if int(values[1]) == SPELL_EFFECT_LEARN_GLYPH and int(values[12]) > 0 and int(values[24]) > 0:
            glyph_property_by_teach_spell[int(values[24])] = int(values[12])

    mapping: dict[int, int] = {}
    for values in load_wdb2_values(dbc_dir / "Item-sparse.db2", ITEM_SPARSE_FMT):
        teach_spell = int(values[69]) if len(values) > 69 else 0
        glyph_property = glyph_property_by_teach_spell.get(teach_spell)
        if glyph_property:
            mapping[int(values[0])] = glyph_property
    _GLYPH_ITEM_TO_PROPERTY_CACHE[dbc_dir] = mapping
    return mapping


def normalized_glyphs(bot: dict[str, Any], glyph_item_map: dict[int, int] | None = None) -> list[int]:
    glyph_item_map = glyph_item_map if glyph_item_map is not None else glyph_item_to_property_map()
    glyphs: list[int] = []
    for value in bot.get("glyphs", []):
        raw_glyph_id = int(value or 0)
        glyph_id = glyph_item_map.get(raw_glyph_id, raw_glyph_id)
        if glyph_id > 0 and glyph_id not in glyphs:
            glyphs.append(glyph_id)
        if len(glyphs) >= 9:
            break
    return glyphs


def equipment_cache(equipment: list[dict[str, Any]], bag_slots: int = INVENTORY_BAG_SLOTS) -> str:
    visible = [0] * (EQUIPMENT_SLOT_END * 2)
    for item in equipment:
        slot = int(item.get("slot", -1))
        if 0 <= slot < EQUIPMENT_SLOT_END:
            visible[slot * 2] = int(item.get("item_id") or 0)
            visible[slot * 2 + 1] = int(item.get("enchant_id") or 0)
    values = visible + [0 for _ in range(max(0, bag_slots) * 2)]
    return " ".join(str(value) for value in values) + " "


def runtime_safe_enchantments(item: dict[str, Any]) -> str:
    values = [0] * 45
    raw = str(item.get("enchantments") or "").split()
    for index, token in enumerate(raw[:45]):
        if token.lstrip("-").isdigit():
            values[index] = int(token)
    if not raw and int(item.get("enchant_id") or 0):
        values[0] = int(item.get("enchant_id") or 0)
    for socket_offset in (6, 9, 12):
        values[socket_offset] = 0
    return " ".join(str(value) for value in values)

DEFAULT_ACTION_PROFILES = load_action_profile_manifest(DEFAULT_ACTION_PROFILE_MANIFEST)
ACTION_PROFILE_SPELLS_BY_CLASS = DEFAULT_ACTION_PROFILES["action_profile_spells_by_class"]
PROFICIENCY_SPELLS_BY_CLASS = DEFAULT_ACTION_PROFILES["proficiency_spells_by_class"]


def sql_quote(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "''") + "'"


def normalize_ascii_player_name(name: str) -> str:
    if not name:
        return name
    return name[0].upper() + name[1:].lower()


def load_config(path: Path) -> dict[str, Any]:
    config = json.loads(path.read_text(encoding="utf-8"))
    for scenario in config.get("scenarios", []):
        for bot in scenario.get("bots", []):
            name = str(bot.get("name", ""))
            normalized = normalize_ascii_player_name(name)
            if name != normalized:
                raise ValueError(f"validation bot name {name!r} must use normalized player-name casing {normalized!r}")
    return config


def load_gear_profiles(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload.get("profiles", {})


def apply_gear_profiles(config: dict[str, Any], profiles: dict[str, Any]) -> dict[str, Any]:
    if not profiles:
        return config
    copied = json.loads(json.dumps(config))
    for scenario in copied["scenarios"]:
        for bot in scenario["bots"]:
            if bot.get("equipment"):
                continue
            profile = profiles.get(str(bot.get("class_spec") or ""))
            if profile:
                bot["equipment"] = profile.get("equipment", [])
                bot["gear_profile"] = str(bot.get("class_spec") or "")
    return copied


def character_names(config: dict[str, Any]) -> list[str]:
    return [str(bot["name"]) for scenario in config["scenarios"] for bot in scenario["bots"]]


def cleanup_character_names(config: dict[str, Any]) -> list[str]:
    names = []
    for scenario in config["scenarios"]:
        for bot in scenario["bots"]:
            names.append(str(bot["name"]))
            names.extend(str(name) for name in bot.get("legacy_names", []))
    return names


def account_commands(config: dict[str, Any]) -> str:
    password = config.get("account_password", "validation")
    lines = [
        "# Apply these in worldserver console before provision_characters.sql if accounts do not exist.",
        "# The SQL uses account usernames as stable selectors and does not store account password hashes.",
    ]
    for name in sorted({str(bot["account"]).upper() for scenario in config["scenarios"] for bot in scenario["bots"]}):
        lines.append(f"account create {name} {password}")
        lines.append(f"account set addon {name} 3")
    return "\n".join(lines) + "\n"


def srp6_registration_data(username: str, password: str) -> tuple[bytes, bytes]:
    normalized_username = username.upper()
    normalized_password = password.upper()
    salt = hashlib.sha256(f"trinity-cata-validation-account:{normalized_username}:{normalized_password}".encode("utf-8")).digest()
    inner = hashlib.sha1(f"{normalized_username}:{normalized_password}".encode("utf-8")).digest()
    exponent = int.from_bytes(hashlib.sha1(salt + inner).digest(), "little")
    modulus = int("894B645E89E1535BBDAD5B8B290650530801B18EBFBF5E8FAB3C82872A3E9BB7", 16)
    verifier = pow(7, exponent, modulus).to_bytes(32, "little")
    return salt, verifier


def sql_binary_literal(value: bytes) -> str:
    return "X'" + value.hex() + "'"


def build_account_insert_sql(config: dict[str, Any]) -> str:
    password = config.get("account_password", "validation")
    lines = [
        "-- Generated by tools.bot_ml.build_validation_provisioning.",
        "-- Creates only missing validation accounts with deterministic SRP6 credentials for reproducible local validation.",
        "-- Existing account passwords are not overwritten; expansion is kept at Cataclysm or higher.",
    ]
    for username in sorted({str(bot["account"]).upper() for scenario in config["scenarios"] for bot in scenario["bots"]}):
        salt, verifier = srp6_registration_data(username, password)
        lines.append(
            "INSERT INTO `auth`.`account` (`username`, `salt`, `verifier`, `reg_mail`, `email`, `joindate`, `expansion`) "
            f"VALUES ({sql_quote(username)}, {sql_binary_literal(salt)}, {sql_binary_literal(verifier)}, '', '', NOW(), 3) "
            "ON DUPLICATE KEY UPDATE `expansion` = GREATEST(`expansion`, VALUES(`expansion`));"
        )
    return "\n".join(lines) + "\n"


def bot_guid_expression(name: str) -> str:
    return f"(SELECT `guid` FROM `characters`.`characters` WHERE `name` = {sql_quote(name)} LIMIT 1)"


def bot_spell_ids(bot: dict[str, Any], action_profiles: dict[str, Any] | None = None) -> list[int]:
    profiles = action_profiles or DEFAULT_ACTION_PROFILES
    configured = [int(spell) for spell in bot.get("spells", [])]
    profile_spells = profiles["action_profile_spells_by_class"].get(int(bot.get("class", 0)), [])
    proficiency_spells = profiles["proficiency_spells_by_class"].get(int(bot.get("class", 0)), [])
    return sorted({spell for spell in configured + profile_spells + proficiency_spells if spell > 0})


def build_character_insert_sql(config: dict[str, Any], action_profiles: dict[str, Any] | None = None) -> str:
    action_profiles = action_profiles or DEFAULT_ACTION_PROFILES
    lines = [
        "-- Generated by tools.bot_ml.build_validation_provisioning.",
        "-- Review before applying. This resets only configured validation character names and deterministic item GUID ranges.",
        "UPDATE `characters`.`characters` SET `online` = 0 WHERE `name` IN (" + ", ".join(sql_quote(name) for name in cleanup_character_names(config)) + ");",
    ]
    item_guid_base = int(config.get("item_guid_base", 9700000))
    item_guid_limit = item_guid_base + 100000
    lines.append(f"DELETE FROM `characters`.`character_inventory` WHERE `item` >= {item_guid_base} AND `item` < {item_guid_limit};")
    lines.append(f"DELETE FROM `characters`.`item_instance` WHERE `guid` >= {item_guid_base} AND `guid` < {item_guid_limit};")
    lines.append("DELETE FROM `characters`.`character_bot_pool` WHERE `guid` IN (SELECT `guid` FROM `characters`.`characters` WHERE `name` IN (" + ", ".join(sql_quote(name) for name in cleanup_character_names(config)) + "));")
    lines.append("DELETE FROM `characters`.`character_glyphs` WHERE `guid` IN (SELECT `guid` FROM `characters`.`characters` WHERE `name` IN (" + ", ".join(sql_quote(name) for name in cleanup_character_names(config)) + "));")
    lines.append("DELETE FROM `characters`.`character_skills` WHERE `guid` IN (SELECT `guid` FROM `characters`.`characters` WHERE `name` IN (" + ", ".join(sql_quote(name) for name in cleanup_character_names(config)) + "));")
    lines.append("DELETE FROM `characters`.`character_spell` WHERE `guid` IN (SELECT `guid` FROM `characters`.`characters` WHERE `name` IN (" + ", ".join(sql_quote(name) for name in cleanup_character_names(config)) + "));")
    lines.append("DELETE FROM `characters`.`characters` WHERE `name` IN (" + ", ".join(sql_quote(name) for name in cleanup_character_names(config)) + ");")

    item_guid = item_guid_base
    for scenario in config["scenarios"]:
        start = scenario["start_position"]
        tag = scenario["id"]
        for slot, bot in enumerate(scenario["bots"]):
            name = str(bot["name"])
            account = str(bot["account"]).upper()
            role = str(bot["role"])
            class_spec = str(bot.get("class_spec") or bot.get("class") or role)
            cache = equipment_cache(bot.get("equipment", []))
            lines.append(
                "INSERT INTO `characters`.`characters` "
                "(`guid`, `account`, `name`, `slot`, `race`, `class`, `gender`, `level`, `xp`, `money`, `position_x`, `position_y`, `position_z`, `map`, `orientation`, `taximask`, `online`, `cinematic`, `totaltime`, `leveltime`, `logout_time`, `health`, `power1`, `talentGroupsCount`, `activeTalentGroup`, `equipmentCache`) "
                f"SELECT COALESCE(MAX(c.`guid`), 0) + 1, a.`id`, {sql_quote(name)}, {slot}, {int(bot['race'])}, {int(bot['class'])}, {int(bot.get('gender', 0))}, {int(bot.get('level', 85))}, 0, {int(bot.get('money', config.get('default_money', 10000000)))}, "
                f"{float(start['x'])}, {float(start['y'])}, {float(start['z'])}, {int(start['map_id'])}, {float(start.get('o', 0.0))}, '', 0, 1, 0, 0, 0, 100, 100, 1, 0, {sql_quote(cache)} "
                f"FROM `auth`.`account` a LEFT JOIN `characters`.`characters` c ON 1 = 1 WHERE a.`username` = {sql_quote(account)} GROUP BY a.`id`;"
            )
            lines.append(
                "INSERT INTO `characters`.`character_bot_pool` (`guid`, `role`, `class_spec`, `enabled`, `in_use`, `experiment_tags`, `notes`) "
                f"SELECT c.`guid`, {sql_quote(role)}, {sql_quote(class_spec)}, 1, 0, {sql_quote(tag)}, {sql_quote('validation_provisioning')} FROM `characters`.`characters` c WHERE c.`name` = {sql_quote(name)} "
                "ON DUPLICATE KEY UPDATE `role` = VALUES(`role`), `class_spec` = VALUES(`class_spec`), `enabled` = 1, `in_use` = 0, `experiment_tags` = VALUES(`experiment_tags`), `notes` = VALUES(`notes`);"
            )
            for skill in bot.get("skills", config.get("default_skills", [])):
                lines.append(
                    "INSERT INTO `characters`.`character_skills` (`guid`, `skill`, `value`, `max`) "
                    f"SELECT c.`guid`, {int(skill['id'])}, {int(skill.get('value', 525))}, {int(skill.get('max', 525))} FROM `characters`.`characters` c WHERE c.`name` = {sql_quote(name)} "
                    "ON DUPLICATE KEY UPDATE `value` = VALUES(`value`), `max` = VALUES(`max`);"
                )
            for spell_id in bot_spell_ids(bot, action_profiles):
                lines.append(
                    "INSERT INTO `characters`.`character_spell` (`guid`, `spell`, `active`, `disabled`) "
                    f"SELECT c.`guid`, {spell_id}, 1, 0 FROM `characters`.`characters` c WHERE c.`name` = {sql_quote(name)} "
                    "ON DUPLICATE KEY UPDATE `active` = VALUES(`active`), `disabled` = VALUES(`disabled`);"
                )
            glyphs = normalized_glyphs(bot)
            if glyphs:
                glyph_values = glyphs + [0] * (9 - len(glyphs))
                lines.append(
                    "INSERT INTO `characters`.`character_glyphs` (`guid`, `talentGroup`, `glyph1`, `glyph2`, `glyph3`, `glyph4`, `glyph5`, `glyph6`, `glyph7`, `glyph8`, `glyph9`) "
                    f"SELECT c.`guid`, 0, {', '.join(str(int(value)) for value in glyph_values)} FROM `characters`.`characters` c WHERE c.`name` = {sql_quote(name)} "
                    "ON DUPLICATE KEY UPDATE `glyph1` = VALUES(`glyph1`), `glyph2` = VALUES(`glyph2`), `glyph3` = VALUES(`glyph3`), `glyph4` = VALUES(`glyph4`), `glyph5` = VALUES(`glyph5`), `glyph6` = VALUES(`glyph6`), `glyph7` = VALUES(`glyph7`), `glyph8` = VALUES(`glyph8`), `glyph9` = VALUES(`glyph9`);"
                )
            for item in bot.get("equipment", []):
                item_guid += 1
                enchantments = runtime_safe_enchantments(item)
                lines.append(
                    "INSERT INTO `characters`.`item_instance` (`guid`, `itemEntry`, `owner_guid`, `creatorGuid`, `giftCreatorGuid`, `count`, `duration`, `charges`, `flags`, `enchantments`, `randomPropertyType`, `randomPropertyId`, `durability`, `creationTime`, `text`) "
                    f"SELECT {item_guid}, {int(item['item_id'])}, c.`guid`, 0, 0, 1, 0, '', 0, {sql_quote(enchantments)}, 0, 0, {int(item.get('durability', 100))}, UNIX_TIMESTAMP(), '' FROM `characters`.`characters` c WHERE c.`name` = {sql_quote(name)};"
                )
                lines.append(
                    "INSERT INTO `characters`.`character_inventory` (`guid`, `bag`, `slot`, `item`) "
                    f"SELECT c.`guid`, 0, {int(item['slot'])}, {item_guid} FROM `characters`.`characters` c WHERE c.`name` = {sql_quote(name)};"
                )
            for consumable in bot.get("consumables", config.get("default_consumables", [])):
                item_guid += 1
                lines.append(
                    "INSERT INTO `characters`.`item_instance` (`guid`, `itemEntry`, `owner_guid`, `creatorGuid`, `giftCreatorGuid`, `count`, `duration`, `charges`, `flags`, `enchantments`, `randomPropertyType`, `randomPropertyId`, `durability`, `creationTime`, `text`) "
                    f"SELECT {item_guid}, {int(consumable['item_id'])}, c.`guid`, 0, 0, {int(consumable.get('count', 20))}, 0, '', 0, '', 0, 0, 1, UNIX_TIMESTAMP(), '' FROM `characters`.`characters` c WHERE c.`name` = {sql_quote(name)};"
                )
                lines.append(
                    "INSERT INTO `characters`.`character_inventory` (`guid`, `bag`, `slot`, `item`) "
                    f"SELECT c.`guid`, 0, {int(consumable['slot'])}, {item_guid} FROM `characters`.`characters` c WHERE c.`name` = {sql_quote(name)};"
                )
    lines.append("UPDATE `characters`.`character_bot_pool` SET `in_use` = 0 WHERE `experiment_tags` IN (" + ", ".join(sql_quote(str(s["id"])) for s in config["scenarios"]) + ");")
    return "\n".join(lines) + "\n"


def role_counts(bots: list[dict[str, Any]]) -> dict[str, int]:
    counts = {"tank": 0, "healer": 0, "dps": 0}
    for bot in bots:
        role = str(bot.get("role", "dps"))
        counts[role] = counts.get(role, 0) + 1
    return counts


def scenario_report(config: dict[str, Any], action_profiles: dict[str, Any] | None = None) -> dict[str, Any]:
    action_profiles = action_profiles or DEFAULT_ACTION_PROFILES
    scenarios = []
    for scenario in config["scenarios"]:
        bots = scenario["bots"]
        required_roles = ROLE_REQUIREMENTS.get(str(scenario["id"]), {})
        counts = role_counts(bots)
        role_ok = all(counts.get(role, 0) >= count for role, count in required_roles.items())
        max_level_ok = all(int(bot.get("level", 0)) >= int(config.get("max_level", 85)) for bot in bots)
        skills_ok = all(bool(bot.get("skills") or config.get("default_skills")) for bot in bots)
        spells_ok = all(bool(bot_spell_ids(bot, action_profiles)) for bot in bots)
        glyphs_ok = all(len(bot.get("glyphs", [])) >= 3 for bot in bots)
        consumables_ok = all(bool(bot.get("consumables") or config.get("default_consumables")) for bot in bots)
        gear_missing = {
            bot["name"]: sorted(set(required_equipment_slots_for(bot.get("equipment", []))) - {int(item.get("slot", -1)) for item in bot.get("equipment", [])})
            for bot in bots
        }
        gear_ok = all(not missing for missing in gear_missing.values())
        gems_ok = all(all(not item.get("socket_colors") or item.get("gem_item_ids") for item in bot.get("equipment", [])) for bot in bots)
        enchants_ok = all(all(int(item.get("enchant_id") or 0) for item in bot.get("equipment", [])) for bot in bots)
        missing = []
        if not role_ok:
            missing.append("role_coverage")
        if not max_level_ok:
            missing.append("max_level")
        if not skills_ok:
            missing.append("full_skills")
        if not spells_ok:
            missing.append("class_spec_spells")
        if not glyphs_ok:
            missing.append("glyphs")
        if not consumables_ok:
            missing.append("consumables")
        if not gear_ok:
            missing.append("complete_equipment_slots")
        if gear_ok and not gems_ok:
            missing.append("gems")
        if gear_ok and not enchants_ok:
            missing.append("enchants")
        scenarios.append(
            {
                "scenario_id": scenario["id"],
                "bot_count": len(bots),
                "role_counts": counts,
                "required_roles": required_roles,
                "ready": not missing,
                "missing": missing,
                "gear_missing_slots": gear_missing,
                "gear_profiles": {bot["name"]: bot.get("gear_profile", "") for bot in bots},
                "action_profile_manifest": {
                    "path": action_profiles["path"],
                    "schema": action_profiles["schema"],
                    "hash": action_profiles["hash"],
                },
                "start_position": scenario["start_position"],
            }
        )
    return {
        "schema": "bot_validation_provisioning_report_v1",
        "all_ready": all(row["ready"] for row in scenarios),
        "scenario_count": len(scenarios),
        "scenarios": scenarios,
        "action_profile_manifest": {
            "path": action_profiles["path"],
            "schema": action_profiles["schema"],
            "hash": action_profiles["hash"],
        },
        "runtime_ml_control": "disabled_teacher_policy_validation_only",
    }


def build_manifest(config: dict[str, Any], report: dict[str, Any], action_profiles: dict[str, Any] | None = None) -> dict[str, Any]:
    action_profiles = action_profiles or DEFAULT_ACTION_PROFILES
    return {
        "schema": "bot_validation_provisioning_manifest_v1",
        "config_hash": stable_hash(config),
        "scenario_count": len(config["scenarios"]),
        "bot_count": sum(len(scenario["bots"]) for scenario in config["scenarios"]),
        "outputs": {
            "account_commands": "account_commands.txt",
            "account_sql": "provision_accounts.sql",
            "provision_sql": "provision_characters.sql",
            "readiness_report": "report.json",
        },
        "all_ready": report["all_ready"],
        "action_profile_manifest": {
            "path": action_profiles["path"],
            "schema": action_profiles["schema"],
            "hash": action_profiles["hash"],
        },
        "runtime_ml_control": "disabled_teacher_policy_validation_only",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build reproducible prepared-character provisioning artifacts for bot validation scenarios.")
    parser.add_argument("--config", type=Path, default=Path("experiments/configs/validation_provisioning_cata_001.json"))
    parser.add_argument("--gear-profiles", type=Path, default=Path("dataset/validation_gear_profiles/profiles.json"))
    parser.add_argument("--action-profile-manifest", type=Path, default=DEFAULT_ACTION_PROFILE_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/validation_provisioning"))
    args = parser.parse_args()

    action_profiles = load_action_profile_manifest(args.action_profile_manifest)
    config = apply_gear_profiles(load_config(args.config), load_gear_profiles(args.gear_profiles))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "account_commands.txt").write_text(account_commands(config), encoding="utf-8")
    (args.output_dir / "provision_accounts.sql").write_text(build_account_insert_sql(config), encoding="utf-8")
    (args.output_dir / "provision_characters.sql").write_text(build_character_insert_sql(config, action_profiles), encoding="utf-8")
    report = scenario_report(config, action_profiles)
    write_json(args.output_dir / "report.json", report)
    write_json(args.output_dir / "manifest.json", build_manifest(config, report, action_profiles))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
