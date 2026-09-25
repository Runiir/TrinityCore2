"""Provisioning SQL for raid-shard plan characters with two-spec loadouts.

The legacy writer (`build_validation_provisioning.build_character_insert_sql`)
stays byte-identical for the accepted rosters. This writer reuses its cleanup
preamble, account SQL and every value helper, and differs only where a
loadout requires it: two talent groups, two glyph groups, a pre-login active
group, explicit per-character item GUIDs, and a container bag holding the
off-spec gear (character_inventory rows whose `bag` is the bag item GUID).
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
            f"{_select(name)} "
            "ON DUPLICATE KEY UPDATE `entry` = VALUES(`entry`), `owner` = VALUES(`owner`), `modelid` = VALUES(`modelid`), `PetType` = VALUES(`PetType`), `level` = VALUES(`level`), `Reactstate` = VALUES(`Reactstate`), `name` = VALUES(`name`), `active` = VALUES(`active`), `slot` = VALUES(`slot`), `curhealth` = VALUES(`curhealth`), `curmana` = VALUES(`curmana`), `savetime` = VALUES(`savetime`), `abdata` = VALUES(`abdata`);")
        for pet_spell in pet.get("spells", []):
            spell_id, active = ((int(pet_spell["id"]), int(pet_spell.get("active", 1))) if isinstance(pet_spell, dict)
                                else (int(pet_spell), 1))
            lines.append(
                "INSERT INTO `characters`.`pet_spell` (`guid`, `spell`, `active`) "
                f"VALUES ({pet_id}, {spell_id}, {active}) ON DUPLICATE KEY UPDATE `active` = VALUES(`active`);")
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


def build_raid_shard_character_sql(config: dict[str, Any], dbc_dir: Path,
                                   gem_mapping: dict[int, int] | None = None) -> str:
    validate_native_consumable_slots(config)
    gem_mapping = gem_mapping if gem_mapping is not None else gem_item_enchant_map(dbc_dir)
    lines = ["-- Generated by tools.raid_program.raid_loadout_sql (raid-shard two-spec loadouts)."]
    lines += _cleanup_preamble(config)
    for scenario in config["scenarios"]:
        for slot, bot in enumerate(scenario["bots"]):
            lines += bot_rows(config, scenario, slot, bot, gem_mapping, dbc_dir)
    lines.append("UPDATE `characters`.`character_bot_pool` SET `in_use` = 0 WHERE `experiment_tags` IN ("
                 + ", ".join(sql_quote(str(s["id"])) for s in config["scenarios"]) + ");")
    return "\n".join(lines) + "\n"


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
    return {"schema": REPORT_SCHEMA, "composition_id": plan["composition_id"], "shard_count": len(shards),
            "bot_count": sum(len(row["bots"]) for row in shards), "reserved_ranges": plan["reserved_ranges"],
            "gear_coverage": coverage, "provisioning_readiness": scenario_report(config),
            "runtime_profiles": [shard["runtime_profile"] for shard in plan["shards"]], "shards": shards}


def scoped_provisioning_sql(plan_path: Path, scenario_ids: Sequence[str], gear_profiles: Path,
                            dbc_dir: Path) -> dict[str, Any]:
    """Account and character SQL for exactly the selected cohorts of a generated plan.

    Item GUIDs are fixed per character, so a subset never shifts another
    cohort's items; cleanup is scoped to the selected characters' names.
    """
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    config = prepare_config(plan, gear_profiles, dbc_dir, scenario_ids)
    return {"scenario_ids": [row["id"] for row in config["scenarios"]],
            "account_sql": build_account_insert_sql(config),
            "character_sql": build_raid_shard_character_sql(config, dbc_dir)}


def plan_payloads(plan: dict[str, Any], gear_profiles: Path, dbc_dir: Path) -> dict[str, str]:
    config = prepare_config(plan, gear_profiles, dbc_dir)
    return {
        "plan.json": json.dumps(plan, indent=2, sort_keys=True) + "\n",
        "provision_accounts.sql": build_account_insert_sql(config),
        "provision_characters.sql": build_raid_shard_character_sql(config, dbc_dir),
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
