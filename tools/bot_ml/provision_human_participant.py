"""Emit SQL that gives ONE existing human character a bot class_spec loadout.

Play mode (docs/bot_raids/human_play_mode.md) lets humans raid with trained
bots.  For a fair test the human must carry the gear the bots carry.  This tool
reuses the validation bot provisioning path (canonical target catalog, WoWSims
P4 gear profiles, talent builds, glyphs, action-profile spells and profession
skills) and writes SQL that updates one human character *in place*:

* name, account, race, gender, appearance, position and map are never written;
* no ``character_bot_pool`` row is written and no group table is touched;
* every statement is scoped to the one target guid (item rows by owner);
* equipped combat slots are replaced; shirt, tabard, bags and backpack stay;
* item guids come from a dedicated deterministic block, so the SQL is
  idempotent, wrapped in one transaction, and aborts (ERROR 1242 on a named
  ``@abort_*`` variable) when a precondition fails at apply time.

The tool only WRITES the SQL file.  It never applies it; database access is
read-only and used for refusals and gap reporting.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from tools.bot_ml.build_validation_provisioning import (
    DEFAULT_DBC_DIR,
    DEFAULT_WOWSIMS_GEAR_PROFILES,
    ITEM_SPARSE_FMT,
    REQUIRED_EQUIPMENT_SLOTS,
    SPELL_ITEM_ENCHANTMENT_FMT,
    VALIDATION_FULL_STAT_SEED,
    apply_gear_profiles,
    bot_known_spell_ids,
    bot_talent_spell_ids,
    equipment_cache,
    gem_item_enchant_map,
    load_config,
    load_gear_profiles,
    load_wdb2_values,
    load_wdbc_values,
    normalized_glyph_slots,
    runtime_safe_enchantments,
    sql_quote,
    talent_data,
    talent_point_count,
)
from tools.bot_ml.validation_profile_manifests import (
    DEFAULT_ACTION_PROFILE_MANIFEST,
    load_action_profile_manifest,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROVISIONING_CONFIG = REPO_ROOT / "experiments/configs/validation_provisioning_cata_001.json"
DEFAULT_DB_HOST = "172.20.0.2"
# Bots own 9700000+ (config item_guid_base); humans get a disjoint block each.
HUMAN_ITEM_GUID_BASE = 9_800_000
HUMAN_ITEM_GUID_STRIDE = 100
# Combat equipment replaced by the profile (includes the off hand, so a 2H
# profile clears an equipped off hand).  Shirt (3) and tabard (18) are cosmetic.
REPLACED_EQUIPMENT_SLOTS = tuple(REQUIRED_EQUIPMENT_SLOTS)
BACKPACK_SLOTS = range(23, 39)
AT_LOGIN_RESET_SPELLS = 0x002
AT_LOGIN_RESET_TALENTS = 0x004
RIDING_SKILL_ID = 762
# Apprentice, Journeyman, Expert, Artisan Riding, Cold Weather Flying and
# Flight Master's License: every rank the bots' 300 riding skill implies.
RIDING_SPELL_IDS = (33388, 33391, 34090, 34091, 54197, 90267)
PRIMARY_PROFESSION_SKILLS = {164, 165, 171, 182, 186, 197, 202, 333, 393, 755, 773}
REFORGE_STAT_NAMES = {6: "spirit", 13: "dodge", 14: "parry", 31: "hit", 32: "crit",
                      36: "haste", 37: "expertise", 49: "mastery"}
C = "`characters`"


@dataclass(frozen=True)
class HumanTarget:
    guid: int
    name: str
    account: int | None = None


@dataclass
class HumanLoadout:
    class_spec: str
    class_id: int
    template_name: str
    template_race: int
    primary_talent_tree_id: int
    talent_spell_ids: list[int]
    talent_points: int
    glyph_slots: list[int]
    glyph_items: list[int]
    known_spell_ids: list[int]
    specialization_spell_ids: list[int]
    skills: list[dict[str, int]]
    equipment: list[dict[str, Any]]
    consumables: list[dict[str, int]]
    riding_spell_ids: list[int]
    equipment_cache: str
    profession_setup: dict[str, Any]
    sources: dict[str, Any] = field(default_factory=dict)

    def all_item_guids(self) -> list[int]:
        return [int(row["guid"]) for row in self.equipment + self.consumables]


def item_guid_block(guid: int) -> int:
    if guid <= 0:
        raise ValueError("character guid must be positive")
    return HUMAN_ITEM_GUID_BASE + guid * HUMAN_ITEM_GUID_STRIDE


def select_template_bot(config: Mapping[str, Any], class_spec: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Pick the canonical provisioning bot for a class_spec (candidate pool first)."""
    preferred = str(config.get("canonical_candidate_pool_scenario_id") or "")
    scenarios = sorted(config.get("scenarios", []), key=lambda row: str(row.get("id")) != preferred)
    for scenario in scenarios:
        for bot in scenario.get("bots", []):
            if str(bot.get("class_spec") or "") == class_spec:
                return scenario, bot
    raise ValueError(f"no provisioning bot defines class_spec {class_spec!r}")


def class_specialization_spell_ids(class_id: int, dbc_dir: Path = DEFAULT_DBC_DIR) -> list[int]:
    """Every talent-rank and primary-tree spell of the class's talent tabs."""
    talents, primary_spells = talent_data(dbc_dir)
    tabs = {int(row[0]) for row in load_wdbc_values(Path(dbc_dir) / "TalentTab.dbc", "nxxiiixxxii")
            if int(row[3]) & (1 << (class_id - 1))}
    spells = {int(spell) for row in talents.values() if int(row[1]) in tabs for spell in row[4:9] if int(spell)}
    spells.update(int(spell) for tab in tabs for spell in primary_spells.get(tab, []) if int(spell))
    return sorted(spells)


def resolve_loadout(
    class_spec: str,
    target: HumanTarget,
    *,
    config_path: Path = DEFAULT_PROVISIONING_CONFIG,
    gear_profiles_path: Path = DEFAULT_WOWSIMS_GEAR_PROFILES,
    action_profile_manifest: Path = DEFAULT_ACTION_PROFILE_MANIFEST,
    dbc_dir: Path = DEFAULT_DBC_DIR,
    include_consumables: bool = True,
    include_riding_spells: bool = True,
) -> HumanLoadout:
    config = load_config(config_path)
    scenario, bot = select_template_bot(config, class_spec)
    single = {**config, "scenarios": [{**scenario, "bots": [bot]}]}
    profile_id = str(bot.get("gear_profile_id") or bot.get("gear_profile") or class_spec)
    profiles = load_gear_profiles(gear_profiles_path, profile_ids={profile_id}, dbc_dir=dbc_dir)
    if profile_id not in profiles:
        raise ValueError(f"gear profile {profile_id!r} missing from {gear_profiles_path}")
    applied = apply_gear_profiles(single, profiles)
    bot = applied["scenarios"][0]["bots"][0]
    if not bot.get("equipment"):
        raise ValueError(f"{class_spec}: resolved template has no equipment")
    action_profiles = load_action_profile_manifest(action_profile_manifest)
    gem_mapping = gem_item_enchant_map(dbc_dir)
    block = item_guid_block(target.guid)
    consumables = bot.get("consumables", applied.get("default_consumables", [])) if include_consumables else []
    if len(bot["equipment"]) + len(consumables) >= HUMAN_ITEM_GUID_STRIDE:
        raise ValueError("loadout does not fit the dedicated item guid block")
    equipment = []
    for index, item in enumerate(bot["equipment"], start=1):
        equipment.append({
            "guid": block + index,
            "slot": int(item["slot"]),
            "item_id": int(item["item_id"]),
            "enchant_id": int(item.get("enchant_id") or 0),
            "gem_item_ids": [int(v or 0) for v in item.get("gem_item_ids", [])],
            "gem_enchant_ids": [int(v or 0) for v in item.get("gem_enchant_ids", [])],
            "reforge_id": int(item.get("reforge_id") or 0),
            "durability": int(item.get("durability", 100)),
            # Identical call to build_character_insert_sql's item_instance emitter.
            "enchantments": runtime_safe_enchantments(item, gem_mapping, dbc_dir),
        })
    consumable_rows = [
        {"guid": block + len(equipment) + index, "slot": int(row["slot"]),
         "item_id": int(row["item_id"]), "count": int(row.get("count", 20))}
        for index, row in enumerate(consumables, start=1)
    ]
    for row in consumable_rows:
        if row["slot"] not in BACKPACK_SLOTS:
            raise ValueError(f"consumable slot {row['slot']} is not a backpack slot")
    class_id = int(bot["class"])
    return HumanLoadout(
        class_spec=class_spec,
        class_id=class_id,
        template_name=str(bot["name"]),
        template_race=int(bot.get("race", 0)),
        primary_talent_tree_id=int(bot.get("primary_talent_tree_id") or 0),
        talent_spell_ids=bot_talent_spell_ids(bot),
        talent_points=talent_point_count(bot, dbc_dir),
        glyph_slots=[int(v) for v in normalized_glyph_slots(bot)],
        glyph_items=[int(v) for v in bot.get("glyphs", [])],
        known_spell_ids=bot_known_spell_ids(bot, action_profiles),
        specialization_spell_ids=class_specialization_spell_ids(class_id, dbc_dir),
        skills=[{"id": int(s["id"]), "value": int(s.get("value", 525)), "max": int(s.get("max", 525))}
                for s in bot.get("skills", applied.get("default_skills", []))],
        equipment=equipment,
        consumables=consumable_rows,
        riding_spell_ids=list(RIDING_SPELL_IDS) if include_riding_spells else [],
        equipment_cache=equipment_cache(bot["equipment"]),
        profession_setup=bot.get("profession_setup") or {},
        sources={
            "provisioning_config": _rel(config_path),
            "canonical_target_catalog": str(config.get("canonical_target_catalog") or ""),
            "template_scenario": str(scenario.get("id")),
            "template_bot": str(bot["name"]),
            "gear_profiles": _rel(gear_profiles_path),
            "gear_profile_id": profile_id,
            "gear_profile_source": bot.get("gear_profile_source") or {},
            "action_profile_manifest": {"path": action_profiles["path"], "hash": action_profiles["hash"]},
            "dbc_dir": str(dbc_dir),
        },
    )


def _rel(path: Path) -> str:
    try:
        return str(Path(path).resolve().relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _abort_guard(name: str, violation_sql: str) -> str:
    # SET forces evaluation (DO is optimised away); a 2-row subquery raises
    # ERROR 1242 exactly when the violation holds, which stops the batch.
    return (f"SET @abort_{name} = (SELECT 1 FROM (SELECT 1 AS `a` UNION ALL SELECT 2) `abort_guard` "
            f"WHERE {violation_sql});")


def _ints(values: Sequence[int]) -> str:
    return ", ".join(str(int(v)) for v in values)


def build_human_participant_sql(target: HumanTarget, loadout: HumanLoadout, *, online_guard: bool = True) -> str:
    g = int(target.guid)
    block_guids = loadout.all_item_guids()
    tree = loadout.primary_talent_tree_id
    lines = [
        "-- Generated by tools.bot_ml.provision_human_participant (play mode).",
        f"-- Target: human character guid={g} name={target.name!r} account={target.account if target.account is not None else 'unchecked'}; "
        "NOT a bot, NOT a pool character.",
        f"-- Loadout: class_spec={loadout.class_spec} (template bot {loadout.template_name}, "
        f"scenario {loadout.sources.get('template_scenario')}), talent tree {tree}, {loadout.talent_points} points.",
        f"-- Sources: {json.dumps(loadout.sources, sort_keys=True)}",
        f"-- Item guid block: {', '.join(str(v) for v in block_guids)} (owner guid {g} only).",
        "-- Apply ONLY while the character is offline, e.g.:",
        "--   docker exec -i trinity-cata-db mariadb -utrinity -ptrinity < this.sql",
        "-- A failed precondition stops the batch with ERROR 1242 on the named @abort_* variable;",
        "-- the open transaction then rolls back on disconnect.  Re-running yields the same state.",
        "-- WARNING: the character's currently equipped combat items are deleted, not mailed.",
        "-- MariaDB resolves multi-table DELETE aliases only with a default database.",
        "USE `characters`;",
        "START TRANSACTION;",
    ]
    account_clause = f" AND `account` = {int(target.account)}" if target.account is not None else ""
    lines.append(_abort_guard("unless_target_character_matches",
        f"NOT EXISTS (SELECT 1 FROM {C}.`characters` WHERE `guid` = {g} AND `name` = {sql_quote(target.name)}"
        f" AND `class` = {loadout.class_id}{account_clause})"))
    lines.append(_abort_guard("if_bot_pool_character",
        f"EXISTS (SELECT 1 FROM {C}.`character_bot_pool` WHERE `guid` = {g})"))
    if online_guard:
        lines.append(_abort_guard("if_character_online",
            f"EXISTS (SELECT 1 FROM {C}.`characters` WHERE `guid` = {g} AND `online` <> 0)"))
    guid_list = _ints(block_guids)
    lines.append(_abort_guard("if_item_guid_block_foreign",
        f"EXISTS (SELECT 1 FROM {C}.`item_instance` WHERE `guid` IN ({guid_list}) AND `owner_guid` <> {g})"
        f" OR EXISTS (SELECT 1 FROM {C}.`character_inventory` WHERE `item` IN ({guid_list}) AND `guid` <> {g})"
        f" OR EXISTS (SELECT 1 FROM {C}.`mail_items` WHERE `item_guid` IN ({guid_list}))"
        f" OR EXISTS (SELECT 1 FROM {C}.`auctionhouse` WHERE `itemguid` IN ({guid_list}))"
        f" OR EXISTS (SELECT 1 FROM {C}.`guild_bank_item` WHERE `item_guid` IN ({guid_list}))"))

    # Level-85 basics.  Only progression/state columns; identity and appearance stay.
    second_tree = ("IF(`talentGroupsCount` > 1 AND LOCATE(' ', TRIM(`talentTree`)) > 0, "
                   "SUBSTRING_INDEX(SUBSTRING_INDEX(TRIM(`talentTree`), ' ', 2), ' ', -1), '0')")
    lines.append(
        f"UPDATE {C}.`characters` SET `level` = 85, `xp` = 0, "
        f"`health` = {VALIDATION_FULL_STAT_SEED}, `power1` = {VALIDATION_FULL_STAT_SEED}, "
        f"`talentTree` = CONCAT('{tree} ', {second_tree}, ' '), "
        "`talentGroupsCount` = GREATEST(`talentGroupsCount`, 1), `activeTalentGroup` = 0, "
        f"`at_login` = `at_login` & ~{AT_LOGIN_RESET_SPELLS | AT_LOGIN_RESET_TALENTS}, "
        f"`equipmentCache` = {sql_quote(loadout.equipment_cache)} WHERE `guid` = {g};")

    # Items: first this tool's own previous rows, then the equipped combat slots.
    lines.append(f"DELETE FROM {C}.`character_inventory` WHERE `guid` = {g} AND `item` IN ({guid_list});")
    lines.append(f"DELETE FROM {C}.`item_instance` WHERE `owner_guid` = {g} AND `guid` IN ({guid_list});")
    lines.append(
        f"DELETE ci, ii FROM {C}.`character_inventory` ci LEFT JOIN {C}.`item_instance` ii "
        f"ON ii.`guid` = ci.`item` AND ii.`owner_guid` = {g} "
        f"WHERE ci.`guid` = {g} AND ci.`bag` = 0 AND ci.`slot` IN ({_ints(REPLACED_EQUIPMENT_SLOTS)});")

    # Talents (active group 0, as bots) and class specialization spells.
    lines.append(f"DELETE FROM {C}.`character_talent` WHERE `guid` = {g} AND `talentGroup` = 0;")
    if loadout.talent_spell_ids:
        lines.append(f"INSERT INTO {C}.`character_talent` (`guid`, `spell`, `talentGroup`) VALUES "
                     + ", ".join(f"({g}, {int(s)}, 0)" for s in loadout.talent_spell_ids) + ";")
    lines.append(f"DELETE FROM {C}.`character_spell` WHERE `guid` = {g} "
                 f"AND `spell` IN ({_ints(loadout.specialization_spell_ids)});")
    spells = sorted(set(loadout.known_spell_ids) | set(loadout.riding_spell_ids))
    lines.append(f"INSERT INTO {C}.`character_spell` (`guid`, `spell`, `active`, `disabled`) VALUES "
                 + ", ".join(f"({g}, {s}, 1, 0)" for s in spells)
                 + " ON DUPLICATE KEY UPDATE `active` = VALUES(`active`), `disabled` = VALUES(`disabled`);")
    lines.append(f"INSERT INTO {C}.`character_skills` (`guid`, `skill`, `value`, `max`) VALUES "
                 + ", ".join(f"({g}, {s['id']}, {s['value']}, {s['max']})" for s in loadout.skills)
                 + " ON DUPLICATE KEY UPDATE `value` = VALUES(`value`), `max` = VALUES(`max`);")
    if any(loadout.glyph_slots):
        columns = ", ".join(f"`glyph{i}`" for i in range(1, 10))
        updates = ", ".join(f"`glyph{i}` = VALUES(`glyph{i}`)" for i in range(1, 10))
        lines.append(f"INSERT INTO {C}.`character_glyphs` (`guid`, `talentGroup`, {columns}) "
                     f"VALUES ({g}, 0, {_ints(loadout.glyph_slots)}) ON DUPLICATE KEY UPDATE {updates};")

    item_columns = ("(`guid`, `itemEntry`, `owner_guid`, `creatorGuid`, `giftCreatorGuid`, `count`, `duration`, "
                    "`charges`, `flags`, `enchantments`, `randomPropertyType`, `randomPropertyId`, `durability`, "
                    "`creationTime`, `text`)")
    for item in loadout.equipment:
        lines.append(f"INSERT INTO {C}.`item_instance` {item_columns} VALUES ({item['guid']}, {item['item_id']}, {g}, "
                     f"0, 0, 1, 0, '', 0, {sql_quote(item['enchantments'])}, 0, 0, {item['durability']}, "
                     "UNIX_TIMESTAMP(), '');")
        lines.append(f"INSERT INTO {C}.`character_inventory` (`guid`, `bag`, `slot`, `item`) "
                     f"VALUES ({g}, 0, {item['slot']}, {item['guid']});")
    for row in loadout.consumables:
        free = (f"NOT EXISTS (SELECT 1 FROM {C}.`character_inventory` "
                f"WHERE `guid` = {g} AND `bag` = 0 AND `slot` = {row['slot']})")
        lines.append(f"INSERT INTO {C}.`item_instance` {item_columns} SELECT {row['guid']}, {row['item_id']}, {g}, "
                     f"0, 0, {row['count']}, 0, '', 0, '', 0, 0, 1, UNIX_TIMESTAMP(), '' FROM DUAL WHERE {free};")
        lines.append(f"INSERT INTO {C}.`character_inventory` (`guid`, `bag`, `slot`, `item`) "
                     f"SELECT {g}, 0, {row['slot']}, {row['guid']} FROM DUAL WHERE {free} AND EXISTS "
                     f"(SELECT 1 FROM {C}.`item_instance` WHERE `guid` = {row['guid']} AND `owner_guid` = {g});")
    lines.append("COMMIT;")
    lines.append(
        f"SELECT c.`guid`, c.`name`, c.`level`, c.`talentTree`, "
        f"(SELECT COUNT(*) FROM {C}.`character_inventory` WHERE `guid` = {g} AND `item` IN ({guid_list})) AS `provisioned_items`, "
        f"(SELECT COUNT(*) FROM {C}.`character_talent` WHERE `guid` = {g} AND `talentGroup` = 0) AS `talent_ranks`, "
        f"(SELECT COUNT(*) FROM {C}.`character_spell` WHERE `guid` = {g}) AS `spells` "
        f"FROM {C}.`characters` c WHERE c.`guid` = {g};")
    return "\n".join(lines) + "\n"


# --- read-only database checks --------------------------------------------------------------

Query = Callable[[str, Sequence[Any]], list[dict[str, Any]]]


def read_database_facts(host: str, port: int, user: str, password: str, guid: int,
                        item_guids: Sequence[int]) -> dict[str, Any]:
    """Collect facts through a READ ONLY transaction (same pymysql path as other tools)."""
    from tools.bot_ml.extract_world_knowledge import connect_mysql

    conn = connect_mysql(f"mysql://{user}:{password}@{host}:{port}/characters")
    try:
        with conn.cursor() as cursor:
            cursor.execute("SET SESSION TRANSACTION READ ONLY")
            cursor.execute("START TRANSACTION READ ONLY")

        def query(sql: str, params: Sequence[Any] = ()) -> list[dict[str, Any]]:
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                return [dict(row) for row in cursor.fetchall()]
        return fetch_database_facts(query, guid, item_guids)
    finally:
        conn.rollback()
        conn.close()


def fetch_database_facts(query: Query, guid: int, item_guids: Sequence[int]) -> dict[str, Any]:
    marks = ", ".join(["%s"] * len(item_guids))
    rows = query("SELECT `guid`, `account`, `name`, `race`, `class`, `gender`, `level`, `online`, "
                 "`talentGroupsCount`, `activeTalentGroup`, `talentTree`, `at_login` "
                 "FROM `characters` WHERE `guid` = %s", (guid,))
    return {
        "character": rows[0] if rows else None,
        "bot_pool_rows": query("SELECT `guid`, `class_spec` FROM `character_bot_pool` WHERE `guid` = %s", (guid,)),
        "inventory": query("SELECT ci.`bag`, ci.`slot`, ci.`item`, ii.`itemEntry`, ii.`owner_guid` "
                           "FROM `character_inventory` ci LEFT JOIN `item_instance` ii ON ii.`guid` = ci.`item` "
                           "WHERE ci.`guid` = %s AND ci.`bag` = 0 AND ci.`slot` < 39 ORDER BY ci.`slot`", (guid,)),
        "skills": query("SELECT `skill`, `value`, `max` FROM `character_skills` WHERE `guid` = %s", (guid,)),
        "block_items": query(f"SELECT `guid`, `owner_guid` FROM `item_instance` WHERE `guid` IN ({marks})",
                             tuple(item_guids)),
        "block_inventory": query(f"SELECT `guid`, `item` FROM `character_inventory` WHERE `item` IN ({marks})",
                                 tuple(item_guids)),
        "max_foreign_item_guid": int((query("SELECT COALESCE(MAX(`guid`), 0) AS `m` FROM `item_instance` "
                                            "WHERE `owner_guid` <> %s", (guid,)) or [{"m": 0}])[0]["m"] or 0),
    }


def evaluate_database_facts(facts: Mapping[str, Any], target: HumanTarget, loadout: HumanLoadout, *,
                            check_offline: bool) -> tuple[list[str], list[str]]:
    """Return (refusals, gaps/warnings) for a target character."""
    refusals: list[str] = []
    notes: list[str] = []
    row = facts.get("character")
    if not row:
        return [f"character guid {target.guid} does not exist"], notes
    if str(row["name"]) != target.name:
        refusals.append(f"guid {target.guid} is named {row['name']!r}, not {target.name!r}")
    if target.account is not None and int(row["account"]) != target.account:
        refusals.append(f"guid {target.guid} belongs to account {row['account']}, not {target.account}")
    if facts.get("bot_pool_rows"):
        refusals.append(f"guid {target.guid} is a character_bot_pool character; humans are never provisioned into pool rows")
    if int(row["class"]) != loadout.class_id:
        refusals.append(f"guid {target.guid} is class {row['class']}, {loadout.class_spec} needs class {loadout.class_id}")
    if int(row.get("online") or 0):
        (refusals if check_offline else notes).append(
            f"guid {target.guid} is online=1; apply the SQL only after logout")
    foreign = [r for r in facts.get("block_items", []) if int(r["owner_guid"]) != target.guid]
    foreign += [r for r in facts.get("block_inventory", []) if int(r["guid"]) != target.guid]
    if foreign:
        refusals.append(f"dedicated item guids already used by other characters: {foreign}")
    if int(row.get("race") or 0) != loadout.template_race:
        notes.append(f"race {row['race']} differs from template bot race {loadout.template_race}; "
                     "racial passives differ (gear/reforges are the template's)")
    if int(row.get("level") or 0) != 85:
        notes.append(f"DB level is {row['level']}; the SQL sets 85")
    required = {int(s["id"]) for s in loadout.skills} & PRIMARY_PROFESSION_SKILLS
    existing = {int(s["skill"]) for s in facts.get("skills", [])} & PRIMARY_PROFESSION_SKILLS
    if len(required | existing) > 2:
        notes.append(f"primary professions would become {sorted(required | existing)} (>2); "
                     f"required by gear: {sorted(required)}")
    occupied = {int(r["slot"]) for r in facts.get("inventory", []) if int(r["item"]) not in loadout.all_item_guids()}
    skipped = [c for c in loadout.consumables if c["slot"] in occupied]
    if skipped:
        notes.append(f"backpack slots {[c['slot'] for c in skipped]} are occupied; those consumables are skipped")
    first_guid = min(loadout.all_item_guids())
    if int(facts.get("max_foreign_item_guid") or 0) >= first_guid:
        notes.append(f"item guids of other characters reach {facts['max_foreign_item_guid']} >= block start "
                     f"{first_guid}; a running worldserver may allocate into the block")
    return refusals, notes


# --- reporting -------------------------------------------------------------------------------

def loadout_summary(loadout: HumanLoadout, dbc_dir: Path = DEFAULT_DBC_DIR) -> dict[str, Any]:
    name_index = ITEM_SPARSE_FMT.index("s")
    wanted = {i["item_id"] for i in loadout.equipment} | {c["item_id"] for c in loadout.consumables}
    wanted |= {gem for i in loadout.equipment for gem in i["gem_item_ids"]}
    names = {int(r[0]): r[name_index] for r in load_wdb2_values(Path(dbc_dir) / "Item-sparse.db2", ITEM_SPARSE_FMT)
             if int(r[0]) in wanted}
    enchant_names = {int(r[0]): r[14] for r in load_wdbc_values(Path(dbc_dir) / "SpellItemEnchantment.dbc",
                                                                SPELL_ITEM_ENCHANTMENT_FMT)}
    reforges = {int(r[0]): (int(r[1]), int(r[3])) for r in load_wdbc_values(Path(dbc_dir) / "ItemReforge.dbc", "nifif")}

    def reforge_text(reforge_id: int) -> str:
        if not reforge_id:
            return ""
        src, dst = reforges.get(reforge_id, (0, 0))
        return f"{reforge_id} ({REFORGE_STAT_NAMES.get(src, src)}->{REFORGE_STAT_NAMES.get(dst, dst)})"

    items = []
    for item in sorted(loadout.equipment, key=lambda row: row["slot"]):
        fields = [int(v) for v in item["enchantments"].split()]
        items.append({
            "slot": item["slot"], "item_guid": item["guid"], "item_id": item["item_id"],
            "name": names.get(item["item_id"], ""),
            "enchant": f"{fields[0]} {enchant_names.get(fields[0], '')}".strip() if fields[0] else "",
            "gems": [f"{gem} {names.get(gem, '')}".strip() for gem in item["gem_item_ids"] if gem],
            "socket_bonus": f"{fields[15]} {enchant_names.get(fields[15], '')}".strip() if fields[15] else "",
            "extra_socket": f"{fields[18]} {enchant_names.get(fields[18], '')}".strip() if fields[18] else "",
            "reforge": reforge_text(fields[24]),
            "enchantments": item["enchantments"],
        })
    return {
        "class_spec": loadout.class_spec,
        "template_bot": loadout.template_name,
        "item_count": len(items),
        "items": items,
        "talents": {"primary_talent_tree_id": loadout.primary_talent_tree_id, "points": loadout.talent_points,
                    "talent_ranks": len(loadout.talent_spell_ids), "spell_ids": loadout.talent_spell_ids},
        "glyph_items": loadout.glyph_items,
        "glyph_property_slots": loadout.glyph_slots,
        "known_spell_count": len(loadout.known_spell_ids),
        "riding_spell_ids": loadout.riding_spell_ids,
        "skills": loadout.skills,
        "profession_setup": loadout.profession_setup,
        "consumables": [{**c, "name": names.get(c["item_id"], "")} for c in loadout.consumables],
        "sources": loadout.sources,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--guid", type=int, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--class-spec", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--account", type=int, help="expected account id (also enforced by the SQL guard)")
    parser.add_argument("--config", type=Path, default=DEFAULT_PROVISIONING_CONFIG)
    parser.add_argument("--gear-profiles", type=Path, default=DEFAULT_WOWSIMS_GEAR_PROFILES)
    parser.add_argument("--action-profile-manifest", type=Path, default=DEFAULT_ACTION_PROFILE_MANIFEST)
    parser.add_argument("--db-host", default=DEFAULT_DB_HOST)
    parser.add_argument("--db-port", type=int, default=3306)
    parser.add_argument("--db-user", default="trinity")
    parser.add_argument("--db-password", default="trinity")
    parser.add_argument("--no-db", action="store_true", help="skip the read-only DB checks (SQL guards still apply)")
    parser.add_argument("--check-offline", action="store_true", help="refuse unless characters.online = 0")
    parser.add_argument("--no-consumables", action="store_true")
    parser.add_argument("--no-riding-spells", action="store_true")
    parser.add_argument("--no-online-guard", action="store_true",
                        help="omit the apply-time online guard (only for a stale flag with the server stopped)")
    args = parser.parse_args(argv)
    if args.no_db and args.check_offline:
        parser.error("--check-offline needs database access")
    output = args.output.resolve()
    paths = {key: getattr(args, key).resolve() for key in ("config", "gear_profiles", "action_profile_manifest")}
    os.chdir(REPO_ROOT)  # provisioning helpers resolve data/dbc/enUS relative to the checkout

    target = HumanTarget(guid=args.guid, name=args.name, account=args.account)
    loadout = resolve_loadout(
        args.class_spec, target, config_path=paths["config"], gear_profiles_path=paths["gear_profiles"],
        action_profile_manifest=paths["action_profile_manifest"],
        include_consumables=not args.no_consumables, include_riding_spells=not args.no_riding_spells)
    refusals: list[str] = []
    notes: list[str] = []
    database: dict[str, Any] = {"checked": False}
    if not args.no_db:
        try:
            facts = read_database_facts(args.db_host, args.db_port, args.db_user, args.db_password,
                                        target.guid, loadout.all_item_guids())
        except Exception as exc:  # noqa: BLE001 - report and fall back to apply-time guards
            if args.check_offline:
                print(f"refused: database unavailable for --check-offline: {exc}", file=sys.stderr)
                return 2
            notes.append(f"database unavailable ({exc}); only apply-time SQL guards protect the target")
        else:
            refusals, notes = evaluate_database_facts(facts, target, loadout, check_offline=args.check_offline)
            database = {"checked": True, "character": facts["character"], "bag0_slots_now": facts["inventory"]}
            if target.account is None and facts["character"]:
                target = HumanTarget(guid=target.guid, name=target.name, account=int(facts["character"]["account"]))
    if refusals:
        for reason in refusals:
            print(f"refused: {reason}", file=sys.stderr)
        return 2
    sql = build_human_participant_sql(target, loadout, online_guard=not args.no_online_guard)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(sql, encoding="utf-8")
    summary = {"output": str(output), "target": target.__dict__, "database": database,
               "gaps": notes, **loadout_summary(loadout)}
    print(json.dumps(summary, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
