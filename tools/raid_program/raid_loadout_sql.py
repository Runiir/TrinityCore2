"""Provisioning SQL for raid-shard plan characters with two-spec loadouts.

The legacy writer (`build_validation_provisioning.build_character_insert_sql`)
stays byte-identical for the accepted rosters. This writer reuses its cleanup
preamble, account rows and every value helper, and differs where a loadout
requires it: two talent groups, two glyph groups, a pre-login active group,
the dual-spec switch spells, explicit per-character item GUIDs, and a
container bag holding the off-spec gear (character_inventory rows whose `bag`
is the bag item GUID).

Each cohort is one transaction: guards that abort before the first write
(ERROR 1242) when a foreign row occupies a cohort identity, a plan character
is online, or (for every cohort but the anchor) the plan's anchor rows are
missing and no row lies above the reservation; then the scoped cleanup,
guarded account rows and plain INSERTs (no upsert can take over a foreign
pet). The anchor cohort is written first. `raid_shard_preflight` runs the same
checks over the whole reservation before any cohort is attempted.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Sequence

from tools.bot_ml.build_validation_provisioning import (
    VALIDATION_FULL_STAT_SEED,
    apply_gear_profiles,
    build_account_insert_sql,
    build_character_insert_sql,
    equipment_cache,
    gem_item_enchant_map,
    load_gear_profiles,
    scenario_report,
    sql_quote,
)
from tools.raid_program.raid_loadout import (
    expected_glyph_rows,
    expected_inventory,
    expected_talent_rows,
    expected_talent_tree,
    materialize_config,
)
from tools.raid_program.raid_shard_contract import validate_native_consumable_slots
from tools.raid_program.raid_shard_preflight import order_cohorts, plan_reservation

CHARACTER_INSERT_MARKER = "INSERT INTO `characters`.`characters` "
REPORT_SCHEMA = "raid_shard_provisioning_report_v1"
MANIFEST_SCHEMA = "raid_shard_provisioning_manifest_v1"


class RaidShardSqlError(ValueError):
    pass


def raid_shard_config(plan: dict[str, Any], scenario_ids: Sequence[str] = ()) -> dict[str, Any]:
    """A provisioning config holding only this plan's (selected) shard scenarios."""
    requested = list(scenario_ids)
    shards = [shard for shard in plan["shards"] if not requested or shard["scenario_id"] in requested]
    if requested and (len(shards) != len(set(requested)) or len(requested) != len(set(requested))):
        raise RaidShardSqlError("raid_shard_scenario_selection_missing_or_duplicated")
    scenarios = []
    for shard in shards:
        if not shard.get("start_position"):
            raise RaidShardSqlError(f"start_position_missing:{shard['scenario_id']}")
        scenarios.append({
            "id": shard["scenario_id"],
            "instance": shard["raid"],
            "map_id": shard["map_id"],
            "difficulty": shard["difficulty"],
            "start_position": copy.deepcopy(shard["start_position"]),
            "required_roles": copy.deepcopy(shard["role_counts"]),
            "diagnostic_only": True,
            "diagnostic_parent_scenario_id": shard["diagnostic_parent_scenario_id"],
            "runtime_profile_id": shard["runtime_profile_id"],
            "pool_tag": shard["pool_tag"],
            "cohort_id": shard["cohort_id"],
            "lockout": copy.deepcopy(shard["lockout"]),
            "live_identity_requirements": copy.deepcopy(shard["live_identity_requirements"]),
            "bots": copy.deepcopy(shard["bots"]),
        })
    return {
        "schema": "raid_shard_provisioning_config_v1",
        **copy.deepcopy(plan.get("provisioning_defaults") or {}),
        "raid_shard_plan": {"composition_id": plan["composition_id"], "raid": plan["raid"], "mode": plan["mode"]},
        "scenarios": scenarios,
    }


def prepare_config(plan: dict[str, Any], gear_profiles: Path, dbc_dir: Path,
                   scenario_ids: Sequence[str] = ()) -> dict[str, Any]:
    profiles = load_gear_profiles(gear_profiles, dbc_dir=dbc_dir)
    config = apply_gear_profiles(raid_shard_config(plan, scenario_ids), profiles)
    return materialize_config(config, profiles, dbc_dir)


def _cleanup_preamble(config: dict[str, Any]) -> list[str]:
    """Reuse the legacy writer's exact cleanup for the same character names."""
    stub = {"scenarios": [{"id": scenario["id"], "start_position": scenario["start_position"],
                           "bots": [{key: bot[key] for key in ("name", "account", "role", "race", "class", "legacy_names")
                                     if key in bot} for bot in scenario["bots"]]}
                          for scenario in config["scenarios"]]}
    legacy = build_character_insert_sql(stub)
    head, marker, _rest = legacy.partition("\n" + CHARACTER_INSERT_MARKER)
    if not marker:
        raise RaidShardSqlError("legacy_cleanup_preamble_marker_missing")
    return head.split("\n")


def loadout_equipment_cache(bot: dict[str, Any]) -> str:
    """Visible equipment pairs plus `entry 0` for each bag slot, as Player::SaveToDB writes."""
    bag = bot["loadout"]["bag"]
    bags = []
    for slot in range(19, 23):
        bags += [int(bag["item_id"]) if slot == int(bag["bag_slot"]) else 0, 0]
    return equipment_cache(bot.get("equipment", []), bag_slots=0) + " ".join(map(str, bags)) + " "


def _select(name: str) -> str:
    return f"FROM `characters`.`characters` c WHERE c.`name` = {sql_quote(name)}"


def bot_rows(config: dict[str, Any], scenario: dict[str, Any], slot: int, bot: dict[str, Any],
             gem_mapping: dict[int, int], dbc_dir: Path) -> list[str]:
    loadout = bot.get("loadout")
    if not loadout or "physical_items" not in loadout:
        raise RaidShardSqlError(f"loadout_not_materialized:{bot.get('name')}")
    start = scenario["start_position"]
    name, account = str(bot["name"]), str(bot["account"]).upper()
    guid = int(bot["expected_character_guid"])
    lines = [
        "INSERT INTO `characters`.`characters` "
        "(`guid`, `account`, `name`, `slot`, `race`, `class`, `gender`, `level`, `xp`, `money`, `position_x`, `position_y`, `position_z`, `map`, `orientation`, `taximask`, `online`, `cinematic`, `totaltime`, `leveltime`, `logout_time`, `health`, `power1`, `talentGroupsCount`, `activeTalentGroup`, `talentTree`, `equipmentCache`) "
        f"SELECT {guid}, a.`id`, {sql_quote(name)}, {slot}, {int(bot['race'])}, {int(bot['class'])}, {int(bot.get('gender', 0))}, {int(bot.get('level', 85))}, 0, {int(bot.get('money', config.get('default_money', 10000000)))}, "
        f"{float(start['x'])}, {float(start['y'])}, {float(start['z'])}, {int(start['map_id'])}, {float(start.get('o', 0.0))}, '', 0, 1, 0, 0, 0, {VALIDATION_FULL_STAT_SEED}, {VALIDATION_FULL_STAT_SEED}, "
        f"{int(loadout['talent_groups_count'])}, {int(loadout['active_talent_group'])}, {sql_quote(expected_talent_tree(bot))}, {sql_quote(loadout_equipment_cache(bot))} "
        f"FROM `auth`.`account` a WHERE a.`username` = {sql_quote(account)};",
        "INSERT INTO `characters`.`character_bot_pool` (`guid`, `role`, `class_spec`, `enabled`, `in_use`, `experiment_tags`, `notes`) "
        f"SELECT c.`guid`, {sql_quote(str(bot['role']))}, {sql_quote(str(bot['class_spec']))}, 1, 0, {sql_quote(scenario['id'])}, {sql_quote('raid_shard_provisioning')} {_select(name)} "
        "ON DUPLICATE KEY UPDATE `role` = VALUES(`role`), `class_spec` = VALUES(`class_spec`), `enabled` = 1, `in_use` = 0, `experiment_tags` = VALUES(`experiment_tags`), `notes` = VALUES(`notes`);",
    ]
    for skill in bot.get("skills", config.get("default_skills", [])):
        lines.append(
            "INSERT INTO `characters`.`character_skills` (`guid`, `skill`, `value`, `max`) "
            f"SELECT c.`guid`, {int(skill['id'])}, {int(skill.get('value', 525))}, {int(skill.get('max', 525))} {_select(name)} "
            "ON DUPLICATE KEY UPDATE `value` = VALUES(`value`), `max` = VALUES(`max`);")
    for spell_id in loadout["known_spell_ids"]:
        lines.append(
            "INSERT INTO `characters`.`character_spell` (`guid`, `spell`, `active`, `disabled`) "
            f"SELECT c.`guid`, {int(spell_id)}, 1, 0 {_select(name)} "
            "ON DUPLICATE KEY UPDATE `active` = VALUES(`active`), `disabled` = VALUES(`disabled`);")
    for group, spells in sorted(expected_talent_rows(bot).items()):
        for spell_id in spells:
            lines.append(
                "INSERT INTO `characters`.`character_talent` (`guid`, `spell`, `talentGroup`) "
                f"SELECT c.`guid`, {spell_id}, {group} {_select(name)};")
    pet = bot.get("pet")
    if pet:
        pet_id = int(bot["expected_pet_id"])
        actionbar = str(pet.get("actionbar") or "")
        if actionbar and len(actionbar.split()) != 20:
            raise RaidShardSqlError(f"{name} pet actionbar must contain 20 space-separated values")
        lines.append(
            "INSERT INTO `characters`.`character_pet` "
            "(`id`, `entry`, `owner`, `modelid`, `CreatedBySpell`, `PetType`, `level`, `exp`, `Reactstate`, `name`, `renamed`, `active`, `slot`, `curhealth`, `curmana`, `savetime`, `abdata`) "
            f"SELECT {pet_id}, {int(pet['entry'])}, c.`guid`, {int(pet.get('modelid', 0))}, {int(pet.get('created_by_spell', 0))}, 1, {int(pet.get('level', bot.get('level', 85)))}, 0, {int(pet.get('react_state', 1))}, {sql_quote(str(pet['name']))}, 1, {int(pet.get('active', 1))}, {int(pet.get('slot', 0))}, {int(pet.get('health', 100000))}, {int(pet.get('mana', 0))}, UNIX_TIMESTAMP(), {sql_quote(actionbar)} "
            f"{_select(name)};")
        for pet_spell in pet.get("spells", []):
            spell_id, active = ((int(pet_spell["id"]), int(pet_spell.get("active", 1))) if isinstance(pet_spell, dict)
                                else (int(pet_spell), 1))
            lines.append(
                "INSERT INTO `characters`.`pet_spell` (`guid`, `spell`, `active`) "
                f"VALUES ({pet_id}, {spell_id}, {active});")
    for group, glyphs in sorted(expected_glyph_rows(bot).items()):
        if not any(glyphs):
            continue
        lines.append(
            "INSERT INTO `characters`.`character_glyphs` (`guid`, `talentGroup`, `glyph1`, `glyph2`, `glyph3`, `glyph4`, `glyph5`, `glyph6`, `glyph7`, `glyph8`, `glyph9`) "
            f"SELECT c.`guid`, {group}, {', '.join(str(int(value)) for value in glyphs)} {_select(name)} "
            "ON DUPLICATE KEY UPDATE `glyph1` = VALUES(`glyph1`), `glyph2` = VALUES(`glyph2`), `glyph3` = VALUES(`glyph3`), `glyph4` = VALUES(`glyph4`), `glyph5` = VALUES(`glyph5`), `glyph6` = VALUES(`glyph6`), `glyph7` = VALUES(`glyph7`), `glyph8` = VALUES(`glyph8`), `glyph9` = VALUES(`glyph9`);")
    for row in expected_inventory(bot, config.get("default_consumables", []), gem_mapping, dbc_dir):
        lines.append(
            "INSERT INTO `characters`.`item_instance` (`guid`, `itemEntry`, `owner_guid`, `creatorGuid`, `giftCreatorGuid`, `count`, `duration`, `charges`, `flags`, `enchantments`, `randomPropertyType`, `randomPropertyId`, `durability`, `creationTime`, `text`) "
            f"SELECT {row['item_guid']}, {row['item_id']}, c.`guid`, 0, 0, {row['count']}, 0, '', 0, {sql_quote(row['enchantments'])}, 0, 0, {row['durability']}, UNIX_TIMESTAMP(), '' {_select(name)};")
        lines.append(
            "INSERT INTO `characters`.`character_inventory` (`guid`, `bag`, `slot`, `item`) "
            f"SELECT c.`guid`, {row['bag']}, {row['slot']}, {row['item_guid']} {_select(name)};")
    return lines


def _abort_guard(name: str, violation_sql: str) -> str:
    # SET forces evaluation; a two-row subquery raises ERROR 1242 exactly when
    # the violation holds, which stops the batch before the cohort's writes.
    return (f"SET @raid_shard_abort_{name} = (SELECT 1 FROM (SELECT 1 AS `a` UNION ALL SELECT 2) `abort_guard` "
            f"WHERE {violation_sql});")


def _pairs(rows: Sequence[Sequence[Any]]) -> str:
    return ", ".join(f"({int(key)}, {sql_quote(value) if isinstance(value, str) else int(value)})" for key, value in rows)


def _ints(values: Sequence[int]) -> str:
    return ", ".join(str(int(value)) for value in values)


def cohort_guards(reservation: dict[str, Any], scenario_id: str) -> list[str]:
    """Abort the cohort transaction before any write when a collision is possible."""
    cohort = reservation["cohorts"][scenario_id]
    guids = [guid for guid, _name in cohort["characters"]]
    names = [name for _guid, name in cohort["characters"]]
    accounts = [account for account, _username in cohort["accounts"]]
    usernames = [username for _account, username in cohort["accounts"]]
    blocks = cohort["item_blocks"]
    span = [min(block[1] for block in blocks), max(block[2] for block in blocks)]
    in_blocks = lambda column, owner: " OR ".join(
        f"(`{column}` BETWEEN {lo} AND {hi} AND `{owner}` <> {guid})" for guid, lo, hi in blocks)
    guards = [
        _abort_guard("foreign_character", "EXISTS (SELECT 1 FROM `characters`.`characters` WHERE "
                     f"(`guid` IN ({_ints(guids)}) OR `name` IN ({', '.join(map(sql_quote, names))})) "
                     f"AND (`guid`, `name`) NOT IN ({_pairs(cohort['characters'])}))"),
        _abort_guard("character_online", "EXISTS (SELECT 1 FROM `characters`.`characters` WHERE "
                     f"`guid` IN ({_ints(guids)}) AND `online` <> 0)"),
        _abort_guard("foreign_account", "EXISTS (SELECT 1 FROM `auth`.`account` WHERE "
                     f"(`id` IN ({_ints(accounts)}) OR `username` IN ({', '.join(map(sql_quote, usernames))})) "
                     f"AND (`id`, `username`) NOT IN ({_pairs(cohort['accounts'])}))"),
        _abort_guard("foreign_item", f"EXISTS (SELECT 1 FROM `characters`.`item_instance` WHERE {in_blocks('guid', 'owner_guid')})"),
        _abort_guard("foreign_inventory", f"EXISTS (SELECT 1 FROM `characters`.`character_inventory` WHERE {in_blocks('item', 'guid')})"),
    ]
    guards += [_abort_guard(f"item_in_{table}", f"EXISTS (SELECT 1 FROM `characters`.`{table}` WHERE "
                            f"`{column}` BETWEEN {span[0]} AND {span[1]})")
               for table, column in (("mail_items", "item_guid"), ("auctionhouse", "itemguid"),
                                     ("guild_bank_item", "item_guid"))]
    if cohort["pets"]:
        pet_ids = [pet for pet, _owner in cohort["pets"]]
        guards += [
            _abort_guard("foreign_pet", "EXISTS (SELECT 1 FROM `characters`.`character_pet` WHERE "
                         f"`id` IN ({_ints(pet_ids)}) AND (`id`, `owner`) NOT IN ({_pairs(cohort['pets'])}))"),
            _abort_guard("orphan_pet_spell", "EXISTS (SELECT 1 FROM `characters`.`pet_spell` ps LEFT JOIN "
                         "`characters`.`character_pet` cp ON cp.`id` = ps.`guid` "
                         f"WHERE ps.`guid` IN ({_ints(pet_ids)}) AND cp.`id` IS NULL)"),
        ]
    if scenario_id != reservation["anchor_scenario_id"]:
        spans, anchors = reservation["spans"], reservation["anchors"]
        tables = {"characters": ("`characters`.`characters`", "guid", "name"),
                  "accounts": ("`auth`.`account`", "id", "username"),
                  "items": ("`characters`.`item_instance`", "guid", "owner_guid"),
                  "pets": ("`characters`.`character_pet`", "id", "owner")}
        anchored = []
        for table, (qualified, column, owner) in tables.items():
            if table not in anchors:
                continue
            anchor = anchors[table]
            value = sql_quote(anchor["owner"]) if isinstance(anchor["owner"], str) else int(anchor["owner"])
            anchored.append(f"(EXISTS (SELECT 1 FROM {qualified} WHERE `{column}` = {anchor['id']} AND `{owner}` = {value}) "
                            f"OR EXISTS (SELECT 1 FROM {qualified} WHERE `{column}` > {spans[table][1]}))")
        guards.append(_abort_guard("allocator_can_enter_reservation", "NOT (" + " AND ".join(anchored) + ")"))
    return guards


def _account_rows(config: dict[str, Any], scenario: dict[str, Any]) -> list[str]:
    """The legacy account rows; the foreign_account guard admits only the plan's own duplicates."""
    stub = {"account_password": config.get("account_password", "validation"), "scenarios": [scenario]}
    return [line for line in build_account_insert_sql(stub).split("\n") if line.startswith("INSERT INTO")]


def cohort_sql(config: dict[str, Any], scenario: dict[str, Any], reservation: dict[str, Any],
               gem_mapping: dict[int, int], dbc_dir: Path) -> list[str]:
    lines = ["START TRANSACTION;"]
    lines += cohort_guards(reservation, scenario["id"])
    lines += _cleanup_preamble({"scenarios": [scenario]})
    lines += _account_rows(config, scenario)
    for slot, bot in enumerate(scenario["bots"]):
        lines += bot_rows(config, scenario, slot, bot, gem_mapping, dbc_dir)
    lines.append(f"UPDATE `characters`.`character_bot_pool` SET `in_use` = 0 WHERE `experiment_tags` = {sql_quote(scenario['id'])};")
    lines.append("COMMIT;")
    return lines


def build_raid_shard_character_sql(config: dict[str, Any], dbc_dir: Path, plan: dict[str, Any],
                                   gem_mapping: dict[int, int] | None = None) -> str:
    """Self-contained SQL: one guarded transaction per cohort, the anchor cohort first."""
    validate_native_consumable_slots(config)
    gem_mapping = gem_mapping if gem_mapping is not None else gem_item_enchant_map(dbc_dir)
    reservation = plan_reservation(plan)
    by_id = {scenario["id"]: scenario for scenario in config["scenarios"]}
    lines = ["-- Generated by tools.raid_program.raid_loadout_sql (raid-shard two-spec loadouts).",
             "-- Run tools.raid_program.raid_shard_preflight first, with no worldserver running.",
             "-- Each cohort is one transaction; its guards abort (ERROR 1242) before any write."]
    for scenario_id in order_cohorts(reservation, list(by_id)):
        lines += cohort_sql(config, by_id[scenario_id], reservation, gem_mapping, dbc_dir)
    return "\n".join(lines) + "\n"


def cohort_statements(plan: dict[str, Any], scenario_ids: Sequence[str], gear_profiles: Path,
                      dbc_dir: Path) -> list[tuple[str, list[str]]]:
    """(scenario_id, statements) per cohort in the given order, for execute_cohort_transactions."""
    config = prepare_config(plan, gear_profiles, dbc_dir, scenario_ids)
    gem_mapping = gem_item_enchant_map(dbc_dir)
    reservation = plan_reservation(plan)
    by_id = {scenario["id"]: scenario for scenario in config["scenarios"]}
    return [(scenario_id, [line.rstrip(";") for line in cohort_sql(config, by_id[scenario_id], reservation,
                                                                    gem_mapping, dbc_dir)
                           if line and not line.startswith("--")])
            for scenario_id in scenario_ids]


def _report(plan: dict[str, Any], config: dict[str, Any], gear_profiles: Path) -> dict[str, Any]:
    from tools.raid_program.raid_composition import (
        REFERENCE_REQUESTS, WOWSIMS_GEAR_PROFILES, gear_coverage_report, read_json, repo_path)

    specs = sorted({group["class_spec"] for shard in plan["shards"] for bot in shard["bots"]
                    for group in bot["loadout"]["groups"]})
    catalog_payload = read_json(repo_path(plan["sources"]["spec_catalog"]["path"])) if plan.get("sources") else {"targets": []}
    catalog = {row["spec_target_id"]: row for row in catalog_payload.get("targets", [])}
    coverage = gear_coverage_report(specs, catalog, read_json(WOWSIMS_GEAR_PROFILES),
                                    read_json(gear_profiles) if Path(gear_profiles).is_file() else None,
                                    read_json(REFERENCE_REQUESTS) if REFERENCE_REQUESTS.is_file() else None)
    shards = []
    for shard, scenario in zip([s for s in plan["shards"] if s["scenario_id"] in {c["id"] for c in config["scenarios"]}],
                               config["scenarios"]):
        shards.append({
            "scenario_id": shard["scenario_id"], "cohort_id": shard["cohort_id"], "boss_key": shard["boss_key"],
            "copy": shard["copy"], "role_counts": shard["role_counts"], "spec_selection": shard["spec_selection"],
            "precompleted_boss_keys": shard["lockout"]["precompleted_boss_keys"],
            "start_position_source": shard["start_position_source"],
            "bots": [{"name": bot["name"], "character_guid": bot["character_guid"], "class_spec": bot["class_spec"],
                      "active_talent_group": bot["loadout"]["active_talent_group"],
                      "physical_gear_items": len(bot["loadout"]["physical_items"]),
                      "equipped_items": len(bot["loadout"]["equipped_offsets"]),
                      "bagged_items": len(bot["loadout"]["bag_contents"])} for bot in scenario["bots"]],
        })
    reservation = plan_reservation(plan)
    return {"schema": REPORT_SCHEMA, "composition_id": plan["composition_id"], "shard_count": len(shards),
            "bot_count": sum(len(row["bots"]) for row in shards), "reserved_ranges": plan["reserved_ranges"],
            "apply_reservation": {"spans": reservation["spans"], "anchors": reservation["anchors"],
                                  "anchor_scenario_id": reservation["anchor_scenario_id"]},
            "gear_coverage": coverage, "provisioning_readiness": scenario_report(config),
            "runtime_profiles": [shard["runtime_profile"] for shard in plan["shards"]], "shards": shards}


def scoped_provisioning_sql(plan_path: Path, scenario_ids: Sequence[str], gear_profiles: Path,
                            dbc_dir: Path) -> dict[str, Any]:
    """Self-contained SQL (accounts included) for exactly the selected cohorts.

    Item GUIDs are fixed per character, so a subset never shifts another
    cohort's items; cleanup is scoped to each cohort's names. Run
    raid_shard_preflight over the same selection before applying it.
    """
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    config = prepare_config(plan, gear_profiles, dbc_dir, scenario_ids)
    reservation = plan_reservation(plan)
    return {"scenario_ids": order_cohorts(reservation, [row["id"] for row in config["scenarios"]]),
            "anchor_scenario_id": reservation["anchor_scenario_id"],
            "requires_preflight": "tools.raid_program.raid_shard_preflight",
            "character_sql": build_raid_shard_character_sql(config, dbc_dir, plan)}


def plan_payloads(plan: dict[str, Any], gear_profiles: Path, dbc_dir: Path) -> dict[str, str]:
    config = prepare_config(plan, gear_profiles, dbc_dir)
    return {
        "plan.json": json.dumps(plan, indent=2, sort_keys=True) + "\n",
        "provision_characters.sql": build_raid_shard_character_sql(config, dbc_dir, plan),
        "report.json": json.dumps(_report(plan, config, gear_profiles), indent=2, sort_keys=True, default=str) + "\n",
    }


def verify_plan_outputs(plan: dict[str, Any], output_dir: Path, gear_profiles: Path,
                        dbc_dir: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Regenerate a plan's outputs and require the written files and manifest to match."""
    payloads = plan_payloads(plan, gear_profiles, dbc_dir)
    manifest_path = Path(output_dir) / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.is_file() else {}
    recorded = manifest.get("output_sha256", {})
    failures: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {"output_sha256": {}, "expected_output_sha256": {}}
    for name, text in sorted(payloads.items()):
        path = Path(output_dir) / name
        expected = hashlib.sha256(text.encode("utf-8")).hexdigest()
        actual = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        evidence["expected_output_sha256"][name] = expected
        evidence["output_sha256"][name] = actual
        if actual != expected:
            failures.append({"check": "raid_shard_output_content", "path": name, "expected_sha256": expected, "actual_sha256": actual})
        if recorded.get(name) != actual:
            failures.append({"check": "raid_shard_manifest_output_hash", "path": name})
    if set(recorded) != set(payloads):
        failures.append({"check": "raid_shard_manifest_output_set", "expected": sorted(payloads), "actual": sorted(recorded)})
    return failures, evidence


def write_plan_outputs(plan: dict[str, Any], gear_profiles: Path, dbc_dir: Path,
                       output_dir: Path | None) -> dict[str, Any]:
    payloads = plan_payloads(plan, gear_profiles, dbc_dir)
    hashes = {name: hashlib.sha256(text.encode("utf-8")).hexdigest() for name, text in sorted(payloads.items())}
    manifest = {"schema": MANIFEST_SCHEMA, "composition_id": plan["composition_id"],
                "shard_count": plan["shard_count"], "bot_count": plan["bot_count"],
                "sources": plan.get("sources", {}), "output_sha256": hashes}
    if output_dir is not None:
        output_dir.mkdir(parents=True, exist_ok=True)
        for name, text in payloads.items():
            (output_dir / name).write_text(text, encoding="utf-8")
        (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"composition_id": plan["composition_id"], "output_dir": str(output_dir) if output_dir else None,
            "shard_count": plan["shard_count"], "bot_count": plan["bot_count"], "output_sha256": hashes}
