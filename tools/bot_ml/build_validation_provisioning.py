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
    "combat_calibration": {"tank": 1, "dps": 3},
    "blackwing_descent_10n": {"tank": 2, "healer": 3, "dps": 5},
}

REQUIRED_EQUIPMENT_SLOTS = [0, 1, 2, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
EQUIPMENT_SLOT_END = 19
INVENTORY_BAG_SLOTS = 4
REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DBC_DIR = Path("data/dbc/enUS")
DEFAULT_WOWSIMS_GEAR_PROFILES = REPO_ROOT / "experiments/configs/wowsims_cata_p4_gear_profiles.json"
SPELL_EFFECT_LEARN_GLYPH = 74
ITEM_SPARSE_FMT = "niiiffiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiifiiiiiiiiiiiiiiiiiiiiiiiiiiiiiiisssssiiiiiiiiiiiiiiiiiiiiiifiiifii"
_GLYPH_ITEM_TO_PROPERTY_CACHE: dict[Path, dict[int, int]] = {}
_GLYPH_PROPERTY_TYPE_CACHE: dict[Path, dict[int, int]] = {}
_TALENT_DATA_CACHE: dict[Path, tuple[dict[int, list[Any]], dict[int, list[int]]]] = {}


def required_equipment_slots_for(equipment: list[dict[str, Any]]) -> list[int]:
    slots = set(REQUIRED_EQUIPMENT_SLOTS)
    has_two_handed_mainhand = any(
        int(item.get("slot", -1)) == 15 and int(item.get("inventory_type", 0)) == 17
        for item in equipment
    )
    has_offhand = any(int(item.get("slot", -1)) == 16 for item in equipment)
    if has_two_handed_mainhand and not has_offhand:
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


def glyph_property_type_map(dbc_dir: Path = DEFAULT_DBC_DIR) -> dict[int, int]:
    dbc_dir = dbc_dir.resolve()
    cached = _GLYPH_PROPERTY_TYPE_CACHE.get(dbc_dir)
    if cached is not None:
        return cached
    mapping = {int(row[0]): int(row[2]) for row in load_wdbc_values(dbc_dir / "GlyphProperties.dbc", "niii")}
    _GLYPH_PROPERTY_TYPE_CACHE[dbc_dir] = mapping
    return mapping


def normalized_glyph_slots(
    bot: dict[str, Any],
    glyph_item_map: dict[int, int] | None = None,
    glyph_types: dict[int, int] | None = None,
) -> list[int]:
    glyphs = normalized_glyphs(bot, glyph_item_map)
    glyph_types = glyph_types if glyph_types is not None else glyph_property_type_map()
    slots = [0] * 9
    slot_indices = {0: [0, 3, 5], 1: [1, 2, 4], 2: [6, 7, 8]}
    used = {glyph_type: 0 for glyph_type in slot_indices}
    for glyph in glyphs:
        glyph_type = glyph_types[glyph]
        index = slot_indices[glyph_type][used[glyph_type]]
        slots[index] = glyph
        used[glyph_type] += 1
    return slots


def talent_data(dbc_dir: Path = DEFAULT_DBC_DIR) -> tuple[dict[int, list[Any]], dict[int, list[int]]]:
    dbc_dir = dbc_dir.resolve()
    cached = _TALENT_DATA_CACHE.get(dbc_dir)
    if cached is not None:
        return cached
    talents = {int(row[0]): row for row in load_wdbc_values(dbc_dir / "Talent.dbc", "niiiiiiiiiiiiiixxxx")}
    primary_spells: dict[int, list[int]] = {}
    for row in load_wdbc_values(dbc_dir / "TalentTreePrimarySpells.dbc", "xnii"):
        primary_spells.setdefault(int(row[1]), []).append(int(row[2]))
    result = talents, primary_spells
    _TALENT_DATA_CACHE[dbc_dir] = result
    return result


def validate_talent_manifest(bot: dict[str, Any], dbc_dir: Path = DEFAULT_DBC_DIR) -> None:
    configured = bot.get("talents", [])
    if not configured:
        return
    talents, primary_spells = talent_data(dbc_dir)
    selected: dict[int, tuple[list[Any], int]] = {}
    points_by_tree: dict[int, int] = {}
    for talent in configured:
        talent_id = int(talent["talent_id"])
        spell_id = int(talent["spell_id"])
        row = talents[talent_id]
        ranks = [int(value) for value in row[4:9] if int(value)]
        rank = ranks.index(spell_id) + 1
        selected[talent_id] = row, rank
        points_by_tree[int(row[1])] = points_by_tree.get(int(row[1]), 0) + rank
    primary_tree = int(bot["primary_talent_tree_id"])
    if points_by_tree.get(primary_tree, 0) < 31:
        raise ValueError(f"{bot['name']} primary talent tree requires at least 31 points")
    if sum(points_by_tree.values()) > 41:
        raise ValueError(f"{bot['name']} talent allocation exceeds 41 points")
    for talent_id, (row, rank) in selected.items():
        lower_tier_points = sum(
            selected_rank
            for selected_row, selected_rank in selected.values()
            if int(selected_row[1]) == int(row[1]) and int(selected_row[2]) < int(row[2])
        )
        if lower_tier_points < int(row[2]) * 5:
            raise ValueError(f"{bot['name']} talent {talent_id} does not satisfy its tier")
        for prereq_id, prereq_rank in zip(row[9:12], row[12:15]):
            if int(prereq_id) and (int(prereq_id) not in selected or selected[int(prereq_id)][1] < int(prereq_rank) + 1):
                raise ValueError(f"{bot['name']} talent {talent_id} is missing prerequisite {prereq_id}")
    expected_primary = sorted(primary_spells[primary_tree])
    if sorted(int(spell) for spell in bot.get("primary_tree_spells", [])) != expected_primary:
        raise ValueError(f"{bot['name']} primary tree spells do not match DBC tree {primary_tree}")


def talent_point_count(bot: dict[str, Any], dbc_dir: Path = DEFAULT_DBC_DIR) -> int:
    talents, _primary_spells = talent_data(dbc_dir)
    points = 0
    for selected in bot.get("talents", []):
        row = talents[int(selected["talent_id"])]
        ranks = [int(value) for value in row[4:9] if int(value)]
        points += ranks.index(int(selected["spell_id"])) + 1
    return points


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
    gem_item_ids = [int(value or 0) for value in item.get("gem_item_ids", [])]
    gem_enchant_ids = [int(value or 0) for value in item.get("gem_enchant_ids", [])]
    verified_socket_mapping = bool(gem_item_ids) and len(gem_item_ids) == len(gem_enchant_ids) \
        and all(gem_item_id > 0 and gem_enchant_id > 0
            for gem_item_id, gem_enchant_id in zip(gem_item_ids, gem_enchant_ids))
    if item.get("preserve_socket_enchantments") or verified_socket_mapping:
        for socket_offset, enchant_id in zip((6, 9, 12), gem_enchant_ids):
            values[socket_offset] = int(enchant_id or 0)
    else:
        for socket_offset in (6, 9, 12):
            values[socket_offset] = 0
    if int(item.get("reforge_id") or 0):
        values[24] = int(item["reforge_id"])
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
    catalog_reference = str(config.get("canonical_target_catalog") or "")
    if catalog_reference:
        catalog_path = Path(catalog_reference)
        if not catalog_path.is_absolute():
            catalog_path = REPO_ROOT / catalog_path
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
        catalog_bots = [json.loads(json.dumps(row["provisioning_bot"])) for row in catalog.get("targets", [])]
        scenario_id = str(config.get("canonical_candidate_pool_scenario_id") or catalog.get("candidate_pool_scenario_id") or "")
        if not scenario_id or len(catalog_bots) != int(catalog.get("target_count") or 0):
            raise ValueError("canonical target catalog candidate pool is incomplete")
        existing = next((row for row in config.get("scenarios", []) if str(row.get("id")) == scenario_id), None)
        if existing is None:
            config.setdefault("scenarios", []).append(
                {
                    "id": scenario_id,
                    "description": "Canonical leaseable all-spec candidate pool; not a simultaneous gameplay party.",
                    "start_position": {"map_id": 0, "x": -8962.05, "y": -157.16, "z": 81.5856, "o": 0.0},
                    "bots": catalog_bots,
                }
            )
        elif existing.get("bots") != catalog_bots:
            raise ValueError("canonical candidate pool conflicts with checked-in provisioning scenario")
        talent_builds = config.setdefault("talent_builds_by_spec", {})
        for row in catalog.get("targets", []):
            talent_builds[str(row["spec_target_id"])] = json.loads(json.dumps(row["talent_build"]))
    talent_builds = config.get("talent_builds_by_spec", {})
    for scenario in config.get("scenarios", []):
        for bot in scenario.get("bots", []):
            build = talent_builds.get(str(bot.get("class_spec") or ""), {})
            for key in ("primary_talent_tree_id", "talents", "primary_tree_spells"):
                if key not in bot and key in build:
                    bot[key] = json.loads(json.dumps(build[key]))
            name = str(bot.get("name", ""))
            normalized = normalize_ascii_player_name(name)
            if name != normalized:
                raise ValueError(f"validation bot name {name!r} must use normalized player-name casing {normalized!r}")
            validate_talent_manifest(bot)
    return config


def load_gear_profiles(path: Path | None) -> dict[str, Any]:
    if not path or not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    profiles = dict(payload.get("profiles", {}))
    if path.resolve() != DEFAULT_WOWSIMS_GEAR_PROFILES.resolve() and DEFAULT_WOWSIMS_GEAR_PROFILES.is_file():
        overlay = json.loads(DEFAULT_WOWSIMS_GEAR_PROFILES.read_text(encoding="utf-8"))
        slot_map = [int(slot) for slot in overlay.get("slot_map", [])]
        gem_enchantments = {int(item): int(enchant) for item, enchant in overlay.get("gem_enchantments", {}).items()}
        for name, source_profile in overlay.get("profiles", {}).items():
            equipment = []
            inventory_types = {int(slot): int(value) for slot, value in source_profile.get("inventory_types", {}).items()}
            for index, source_item in enumerate(source_profile.get("items", [])):
                if not source_item or int(source_item.get("id") or 0) <= 0:
                    continue
                slot = slot_map[index]
                gem_items = [int(gem) for gem in source_item.get("gems", [])]
                gem_enchant_ids = [gem_enchantments.get(gem, 0) for gem in gem_items]
                runtime_temp_enchant = int(source_item.get("runtime_temp_enchant") or source_item.get("temp_enchant") or 0)
                runtime_temp_enchant_duration_ms = int(source_item.get("runtime_temp_enchant_duration_ms") or 0)
                enchantment_fields = [0] * 45
                enchantment_fields[0] = int(source_item.get("enchant") or 0)
                enchantment_fields[3] = runtime_temp_enchant
                enchantment_fields[4] = runtime_temp_enchant_duration_ms
                for offset, enchant_id in zip((6, 9, 12), gem_enchant_ids):
                    enchantment_fields[offset] = enchant_id
                enchantment_fields[24] = int(source_item.get("reforging") or 0)
                equipment.append(
                    {
                        "slot": slot,
                        "item_id": int(source_item["id"]),
                        "enchant_id": int(source_item.get("enchant") or 0),
                        "source_temp_enchant_id": int(source_item.get("temp_enchant") or 0),
                        "temp_enchant_id": runtime_temp_enchant,
                        "temp_enchant_duration_ms": runtime_temp_enchant_duration_ms,
                        "gem_item_ids": gem_items,
                        "gem_enchant_ids": gem_enchant_ids,
                        "reforge_id": int(source_item.get("reforging") or 0),
                        "enchantments": " ".join(str(value) for value in enchantment_fields),
                        "inventory_type": inventory_types.get(slot, 0),
                        "preserve_socket_enchantments": True,
                    }
                )
            profiles[name] = {"equipment": equipment, "source": source_profile.get("source", {})}
    return profiles


def apply_gear_profiles(config: dict[str, Any], profiles: dict[str, Any]) -> dict[str, Any]:
    if not profiles:
        return config
    copied = json.loads(json.dumps(config))
    for scenario in copied["scenarios"]:
        for bot in scenario["bots"]:
            if bot.get("equipment"):
                continue
            profile_name = str(bot.get("gear_profile") or bot.get("class_spec") or "")
            profile = profiles.get(profile_name)
            if profile:
                bot["equipment"] = profile.get("equipment", [])
                bot["gear_profile"] = profile_name
                bot["gear_profile_source"] = profile.get("source", {})
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
    spec_profile_spells = profiles.get("action_profile_spells_by_spec", {}).get(str(bot.get("class_spec") or ""), [])
    proficiency_spells = profiles["proficiency_spells_by_class"].get(int(bot.get("class", 0)), [])
    specialization_spells: set[int] = set()
    if int(bot.get("primary_talent_tree_id") or 0) > 0:
        talents, primary_spells = talent_data()
        specialization_spells.update(
            int(spell_id)
            for row in talents.values()
            for spell_id in row[4:9]
            if int(spell_id)
        )
        specialization_spells.update(
            int(spell_id)
            for spell_ids in primary_spells.values()
            for spell_id in spell_ids
            if int(spell_id)
        )
    return sorted({
        spell
        for spell in configured + profile_spells + spec_profile_spells + proficiency_spells
        if spell > 0 and spell not in specialization_spells
    })


def bot_talent_spell_ids(bot: dict[str, Any]) -> list[int]:
    return [int(talent["spell_id"]) for talent in bot.get("talents", [])]


def bot_primary_tree_spell_ids(bot: dict[str, Any], dbc_dir: Path = DEFAULT_DBC_DIR) -> list[int]:
    primary_tree = int(bot.get("primary_talent_tree_id") or 0)
    if primary_tree <= 0:
        return []
    _talents, primary_spells = talent_data(dbc_dir)
    return primary_spells.get(primary_tree, [])


def bot_known_spell_ids(bot: dict[str, Any], action_profiles: dict[str, Any] | None = None) -> list[int]:
    return sorted({
        *bot_spell_ids(bot, action_profiles),
        *bot_talent_spell_ids(bot),
        *bot_primary_tree_spell_ids(bot),
    })


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
    lines.append("DELETE FROM `characters`.`character_talent` WHERE `guid` IN (SELECT `guid` FROM `characters`.`characters` WHERE `name` IN (" + ", ".join(sql_quote(name) for name in cleanup_character_names(config)) + "));")
    lines.append("DELETE FROM `characters`.`character_skills` WHERE `guid` IN (SELECT `guid` FROM `characters`.`characters` WHERE `name` IN (" + ", ".join(sql_quote(name) for name in cleanup_character_names(config)) + "));")
    lines.append("DELETE FROM `characters`.`character_spell` WHERE `guid` IN (SELECT `guid` FROM `characters`.`characters` WHERE `name` IN (" + ", ".join(sql_quote(name) for name in cleanup_character_names(config)) + "));")
    lines.append("DELETE ps FROM `characters`.`pet_spell` ps JOIN `characters`.`character_pet` cp ON cp.`id` = ps.`guid` WHERE cp.`owner` IN (SELECT `guid` FROM `characters`.`characters` WHERE `name` IN (" + ", ".join(sql_quote(name) for name in cleanup_character_names(config)) + "));")
    lines.append("DELETE FROM `characters`.`character_pet` WHERE `owner` IN (SELECT `guid` FROM `characters`.`characters` WHERE `name` IN (" + ", ".join(sql_quote(name) for name in cleanup_character_names(config)) + "));")
    lines.append("DELETE FROM `characters`.`characters` WHERE `name` IN (" + ", ".join(sql_quote(name) for name in cleanup_character_names(config)) + ");")

    item_guid = item_guid_base
    pet_guid_base = int(config.get("pet_guid_base", 8700000))
    for scenario in config["scenarios"]:
        start = scenario["start_position"]
        tag = scenario["id"]
        for slot, bot in enumerate(scenario["bots"]):
            name = str(bot["name"])
            account = str(bot["account"]).upper()
            role = str(bot["role"])
            class_spec = str(bot.get("class_spec") or bot.get("class") or role)
            cache = equipment_cache(bot.get("equipment", []))
            talent_tree = f"{int(bot.get('primary_talent_tree_id', 0))} 0 "
            lines.append(
                "INSERT INTO `characters`.`characters` "
                "(`guid`, `account`, `name`, `slot`, `race`, `class`, `gender`, `level`, `xp`, `money`, `position_x`, `position_y`, `position_z`, `map`, `orientation`, `taximask`, `online`, `cinematic`, `totaltime`, `leveltime`, `logout_time`, `health`, `power1`, `talentGroupsCount`, `activeTalentGroup`, `talentTree`, `equipmentCache`) "
                f"SELECT COALESCE(MAX(c.`guid`), 0) + 1, a.`id`, {sql_quote(name)}, {slot}, {int(bot['race'])}, {int(bot['class'])}, {int(bot.get('gender', 0))}, {int(bot.get('level', 85))}, 0, {int(bot.get('money', config.get('default_money', 10000000)))}, "
                f"{float(start['x'])}, {float(start['y'])}, {float(start['z'])}, {int(start['map_id'])}, {float(start.get('o', 0.0))}, '', 0, 1, 0, 0, 0, 100, 100, 1, 0, {sql_quote(talent_tree)}, {sql_quote(cache)} "
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
            for spell_id in bot_known_spell_ids(bot, action_profiles):
                lines.append(
                    "INSERT INTO `characters`.`character_spell` (`guid`, `spell`, `active`, `disabled`) "
                    f"SELECT c.`guid`, {spell_id}, 1, 0 FROM `characters`.`characters` c WHERE c.`name` = {sql_quote(name)} "
                    "ON DUPLICATE KEY UPDATE `active` = VALUES(`active`), `disabled` = VALUES(`disabled`);"
                )
            for talent_spell_id in bot_talent_spell_ids(bot):
                lines.append(
                    "INSERT INTO `characters`.`character_talent` (`guid`, `spell`, `talentGroup`) "
                    f"SELECT c.`guid`, {talent_spell_id}, 0 FROM `characters`.`characters` c WHERE c.`name` = {sql_quote(name)};"
                )
            pet = bot.get("pet")
            if pet:
                pet_id = pet_guid_base + int(pet.get("id_offset", slot + 1))
                pet_name = str(pet.get("name") or f"{name}pet")
                pet_level = int(pet.get("level", bot.get("level", 85)))
                lines.append(
                    "INSERT INTO `characters`.`character_pet` "
                    "(`id`, `entry`, `owner`, `modelid`, `CreatedBySpell`, `PetType`, `level`, `exp`, `Reactstate`, `name`, `renamed`, `active`, `slot`, `curhealth`, `curmana`, `savetime`, `abdata`) "
                    f"SELECT {pet_id}, {int(pet['entry'])}, c.`guid`, {int(pet.get('modelid', 0))}, {int(pet.get('created_by_spell', 0))}, 1, {pet_level}, 0, {int(pet.get('react_state', 1))}, {sql_quote(pet_name)}, 1, {int(pet.get('active', 1))}, {int(pet.get('slot', 0))}, {int(pet.get('health', 100000))}, {int(pet.get('mana', 0))}, UNIX_TIMESTAMP(), '' "
                    f"FROM `characters`.`characters` c WHERE c.`name` = {sql_quote(name)} "
                    "ON DUPLICATE KEY UPDATE `entry` = VALUES(`entry`), `owner` = VALUES(`owner`), `modelid` = VALUES(`modelid`), `PetType` = VALUES(`PetType`), `level` = VALUES(`level`), `Reactstate` = VALUES(`Reactstate`), `name` = VALUES(`name`), `active` = VALUES(`active`), `slot` = VALUES(`slot`), `curhealth` = VALUES(`curhealth`), `curmana` = VALUES(`curmana`), `savetime` = VALUES(`savetime`);"
                )
                for pet_spell in pet.get("spells", []):
                    if isinstance(pet_spell, dict):
                        pet_spell_id = int(pet_spell["id"])
                        pet_spell_active = int(pet_spell.get("active", 1))
                    else:
                        pet_spell_id = int(pet_spell)
                        pet_spell_active = 1
                    lines.append(
                        "INSERT INTO `characters`.`pet_spell` (`guid`, `spell`, `active`) "
                        f"VALUES ({pet_id}, {pet_spell_id}, {pet_spell_active}) "
                        "ON DUPLICATE KEY UPDATE `active` = VALUES(`active`);"
                    )
            glyph_values = normalized_glyph_slots(bot)
            if any(glyph_values):
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
        enchants_ok = all(
            all(
                int(item.get("enchant_id") or 0)
                for item in bot.get("equipment", [])
                if int(item.get("slot", -1)) in {0, 2, 4, 6, 7, 8, 9, 14, 15, 16}
                or (int(bot.get("class") or 0) == 3 and int(item.get("slot", -1)) == 17)
            )
            for bot in bots
        )
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
