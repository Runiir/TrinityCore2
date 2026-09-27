"""Expand one raid composition into boss shards x N character copies.

Each shard is an isolated diagnostic cohort: its own lockout, pool tag,
runtime profile and characters. Copies of one composition character have
identical specs and gear; only the shard's selected spec (active talent group
and equipped set) differs by boss. Precompleted bosses are the transitive
closure of the package-A prerequisite graph and are diagnostic assistance
that never certifies a predecessor kill.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
from pathlib import Path
from typing import Any, Iterable

from tools.raid_program import raid_shard_identity as ids
from tools.raid_program.raid_composition import (
    COMPOSITION_DIR,
    REPO_ROOT,
    SELECTION_STATUSES,
    catalog_bot,
    load_catalog,
    read_json,
    repo_path,
    role_counts,
    selected_specs,
    sha256_file,
    spec_role,
    validate_composition,
)

PLAN_SCHEMA = "raid_shard_plan_v1"
PREREQUISITE_SCHEMA = "raid_prerequisites_v1"
PREREQUISITES_DIR = REPO_ROOT / "experiments/configs/raid_prerequisites"
PROVISIONING_CONFIG = REPO_ROOT / "experiments/configs/validation_provisioning_cata_001.json"
GEAR_PROFILES = REPO_ROOT / "dataset/validation_gear_profiles/profiles.json"
TRAINERS = REPO_ROOT / "dataset/world_knowledge/trainers.jsonl"
ACTION_PROFILES = REPO_ROOT / "experiments/configs/cata_434_action_profiles.json"
WOWSIMS_GEAR_PROFILES = REPO_ROOT / "experiments/configs/wowsims_cata_p4_gear_profiles.json"
SCENARIO_CONFIG = REPO_ROOT / "experiments/configs/validation_scenarios_cata_001.json"
ACTION_PROFILE_MANIFEST = "experiments/configs/cata_434_action_profiles.json"
LIVE_IDENTITY_FIELDS = ("group_id", "map_instance_id", "save_id", "attempt_id", "strategy_id", "assignment_generation")
PROVISIONING_DEFAULT_KEYS = ("account_password", "default_money", "default_skills", "default_consumables", "max_level")
ROLE_ORDER = {"tank": 0, "healer": 1, "dps": 2}
# The end-to-end cohort of a composition's `full_raid` entry: one more copy of
# the characters in its own identity block. Boss number 99 is never a native
# boss index, so the block cannot collide with a boss shard (it holds the
# plan's highest IDs, which makes it the anchor cohort).
FULL_RAID_KEY = "full"
FULL_RAID_BOSS_NUMBER = ids.MAX_BOSS_NUMBER
FULL_RAID_NAME_CODE = "ful"
FULL_RAID_KIND = "full_raid"
BOSS_SHARD_KIND = "boss"
# The runtime prepull contract (BotWorldPopulationMgrRaidConsumableContracts.cpp)
# needs a flask, food and potion in every roster member's bags and fails the
# whole raid closed on the first member without them. The all-spec catalog
# carries consumables only for its calibrated DPS specs, so every other
# composition spec gets its contract's primary-stat set, as the legacy BWD
# roster provisioned (validation_provisioning_cata_001.json). The item IDs are
# the contract's Strength, Agility and Intellect rows.
CONTRACT_CONSUMABLE_ITEMS = {
    "strength": (58088, 62670, 58146),
    "agility": (58087, 62669, 58145),
    "intellect": (58086, 62671, 58091),
}
CONTRACT_CONSUMABLE_ARCHETYPES = {
    "blood_death_knight": "strength",
    "frost_death_knight": "strength",
    "protection_paladin": "strength",
    "feral_druid_tank": "agility",
    "beast_mastery_hunter": "agility",
    "holy_paladin": "intellect",
    "holy_priest": "intellect",
    "discipline_priest": "intellect",
    "restoration_shaman": "intellect",
    "restoration_druid": "intellect",
}
CONTRACT_CONSUMABLE_SLOTS = (
    (26, ("flask_before_scoring",)),
    (27, ("food_before_scoring",)),
    (28, ("prepot_before_combat", "combat_potion_during_combat")),
)


class ShardPlanError(ValueError):
    pass


def contract_consumables(spec: str) -> list[dict[str, Any]] | None:
    """The prepull contract's flask, food and potion rows for a spec the catalog leaves without any."""
    archetype = CONTRACT_CONSUMABLE_ARCHETYPES.get(spec)
    if archetype is None:
        return None
    return [{"count": 20, "item_id": item, "slot": slot, "uses": list(uses)}
            for item, (slot, uses) in zip(CONTRACT_CONSUMABLE_ITEMS[archetype], CONTRACT_CONSUMABLE_SLOTS)]


def prepull_contract_failure(bot: dict[str, Any]) -> str | None:
    """Why this bot would fail the raid prepull closed at runtime, or None.

    Every roster member needs one flask, food and potion row of one contract
    set (CONTRACT_CONSUMABLE_ITEMS); a spec with a declared archetype needs
    exactly that set. tests/test_raid_shard_roster_setup.py keeps these sets
    equal to the native contracts in BotWorldPopulationMgrRaidConsumableContracts.cpp.
    """
    rows = bot.get("consumables") or []
    by_use: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for use in row.get("uses") or []:
            by_use.setdefault(str(use), []).append(row)
    items = []
    for use in ("flask_before_scoring", "food_before_scoring", "prepot_before_combat"):
        matches = by_use.get(use) or []
        if len(matches) != 1 or int(matches[0].get("count") or 0) < 1:
            return f"prepull_contract_{use}_row"
        items.append(int(matches[0]["item_id"]))
    archetype = CONTRACT_CONSUMABLE_ARCHETYPES.get(str(bot.get("class_spec")))
    if archetype is not None and tuple(items) != CONTRACT_CONSUMABLE_ITEMS[archetype]:
        return "prepull_contract_archetype_items"
    if tuple(items) not in CONTRACT_CONSUMABLE_ITEMS.values():
        return "prepull_contract_unknown_item_set"
    return None


def character_spells(character: dict[str, Any]) -> list[int]:
    """Class spells a composition character declares beyond its action profile (e.g. Heroism 32182).

    The legacy roster declares them per bot (validation_provisioning_cata_001.json
    `spells`); raid_loadout_spells refuses one that the race and class could not
    learn natively.
    """
    spells = character.get("spells") or []
    if not isinstance(spells, list) or any(isinstance(spell, bool) or not isinstance(spell, int) or spell <= 0
                                           for spell in spells) or len(set(spells)) != len(spells):
        raise ShardPlanError(f"character_spells_invalid:{character.get('character_key')}")
    return sorted(spells)


# Runtime keys of a hunter pet row (character_pet / pet_spell); a composition pet may carry documentation
# keys too (family, talent tab, notes), which never reach the plan.
PET_RUNTIME_KEYS = ("entry", "modelid", "created_by_spell", "level", "slot", "active", "actionbar", "spells")
PET_SPELL_ACTIVE_STATES = (1, 0x81, 0xC1)  # ACT_PASSIVE, ACT_DISABLED, ACT_ENABLED (UnitDefines.h ActiveStates)


def character_pet(character: dict[str, Any]) -> dict[str, Any] | None:
    """The hunter pet a composition character declares instead of its catalog pet, or None.

    Only the runtime keys are kept. The shape is checked here; the lawfulness of the family, talents and
    spellbook against the client DBCs and the world dump is raid_loadout_pet's (tests and the audit).
    """
    pet = character.get("pet")
    if pet is None:
        return None
    key = character.get("character_key")

    def fail(reason: str) -> ShardPlanError:
        return ShardPlanError(f"character_pet_invalid:{key}:{reason}")

    if not isinstance(pet, dict):
        raise fail("not_an_object")
    if not all(str(spec).endswith("_hunter") for spec in character.get("specs") or [None]):
        raise fail("not_a_hunter")
    for field in ("entry", "modelid", "level"):
        if isinstance(pet.get(field), bool) or not isinstance(pet.get(field), int) or pet[field] <= 0:
            raise fail(field)
    if pet["level"] > 85 or pet.get("slot", 0) != 0 or pet.get("active", 1) != 1:
        raise fail("level_slot_or_active")
    actionbar = str(pet.get("actionbar") or "").split()
    if len(actionbar) != 20 or not all(value.isdigit() for value in actionbar):
        raise fail("actionbar")
    spells: list[int] = []
    for row in pet.get("spells") or []:
        spell, active = (row.get("id"), row.get("active", 1)) if isinstance(row, dict) else (row, 1)
        if isinstance(spell, bool) or not isinstance(spell, int) or spell <= 0 or active not in PET_SPELL_ACTIVE_STATES:
            raise fail(f"spell:{row}")
        spells.append(spell)
    if not spells or len(set(spells)) != len(spells):
        raise fail("spells")
    return {field: copy.deepcopy(pet[field]) for field in PET_RUNTIME_KEYS if field in pet}


def relative(path: Path) -> str:
    """Repository-relative path, computed lexically.

    Symlinks are not followed, so a DVC cache link or a linked dataset/ keeps
    its repository path instead of becoming the absolute cache path.
    """
    text = os.path.relpath(os.path.abspath(path), REPO_ROOT)
    if text == ".." or text.startswith("../") or os.path.isabs(text):
        return str(path)
    return Path(text).as_posix()


def prerequisites_path(raid: str, directory: Path = PREREQUISITES_DIR) -> Path:
    return Path(directory) / f"{raid}.json"


def _mode_tokens(mode: str) -> set[str]:
    info = ids.mode_info(mode)
    return {mode.lower(), info["token"], info["difficulty"], str(info["raid_difficulty"])}


def validate_prerequisites(prerequisites: dict[str, Any], raid: str, mode: str, map_id: int) -> dict[str, dict[str, Any]]:
    """Validate the package-A graph and return bosses by key."""
    failures: list[dict[str, Any]] = []
    if prerequisites.get("schema") != PREREQUISITE_SCHEMA:
        failures.append({"check": "prerequisite_schema", "actual": prerequisites.get("schema")})
    if prerequisites.get("raid") != raid:
        failures.append({"check": "prerequisite_raid", "actual": prerequisites.get("raid")})
    if int(prerequisites.get("map_id") or 0) != int(map_id):
        failures.append({"check": "prerequisite_map_id", "actual": prerequisites.get("map_id")})
    difficulties = {str(value).lower() for value in prerequisites.get("difficulties") or []}
    if not difficulties & _mode_tokens(mode):
        failures.append({"check": "prerequisite_difficulty", "mode": mode, "declared": sorted(difficulties)})
    bosses = prerequisites.get("bosses") if isinstance(prerequisites.get("bosses"), list) else []
    by_key = {str(row.get("key")): row for row in bosses}
    if len(by_key) != len(bosses) or len({row.get("boss_index") for row in bosses}) != len(bosses):
        failures.append({"check": "prerequisite_boss_identity_not_unique"})
    for row in bosses:
        unknown = [key for key in row.get("predecessors") or [] if key not in by_key]
        if unknown:
            failures.append({"check": "prerequisite_unknown_predecessor", "boss": row.get("key"), "unknown": unknown})
    if not failures:
        for key in by_key:
            try:
                precompleted_closure(by_key, key)
            except ShardPlanError as exc:
                failures.append({"check": "prerequisite_cycle", "boss": key, "reason": str(exc)})
    if failures:
        raise ShardPlanError(json.dumps({"prerequisites": raid, "failures": failures}, sort_keys=True))
    return by_key


def precompleted_closure(bosses_by_key: dict[str, dict[str, Any]], boss_key: str) -> list[dict[str, Any]]:
    """Every transitive predecessor of `boss_key`, ordered by native boss index."""
    seen: set[str] = set()

    def visit(key: str, stack: tuple[str, ...]) -> None:
        for predecessor in bosses_by_key[key].get("predecessors") or []:
            if predecessor in stack:
                raise ShardPlanError(f"predecessor_cycle:{'>'.join(stack + (predecessor,))}")
            if predecessor not in seen:
                seen.add(predecessor)
                visit(predecessor, stack + (predecessor,))

    if boss_key not in bosses_by_key:
        raise ShardPlanError(f"unknown_prerequisite_boss:{boss_key}")
    visit(boss_key, (boss_key,))
    return sorted((bosses_by_key[key] for key in seen), key=lambda row: int(row["boss_index"]))


def join_bosses(composition: dict[str, Any], bosses_by_key: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Bind every composition boss to exactly one native prerequisite boss."""
    joined: dict[str, dict[str, Any]] = {}
    failures = []
    for boss in composition["bosses"]:
        candidates = [boss["boss_key"], *(boss.get("aliases") or [])]
        matches = [key for key in candidates if key in bosses_by_key]
        if len(matches) != 1:
            failures.append({"check": "composition_boss_prerequisite_binding", "boss_key": boss["boss_key"], "matches": matches})
            continue
        native = bosses_by_key[matches[0]]
        if int(native["boss_index"]) != int(boss["boss_number"]):
            failures.append({"check": "composition_boss_number_differs_from_native_index",
                             "boss_key": boss["boss_key"], "boss_number": boss["boss_number"],
                             "native_boss_index": native["boss_index"]})
            continue
        joined[boss["boss_key"]] = native
    if failures:
        raise ShardPlanError(json.dumps({"failures": failures}, sort_keys=True))
    return joined


def scenario_starts(path: Path = SCENARIO_CONFIG) -> dict[str, dict[str, Any]]:
    if not Path(path).is_file():
        return {}
    payload = read_json(path)
    rows = list(payload.get("scenarios") or []) + list(payload.get("diagnostic_scenarios") or [])
    return {str(row["id"]): copy.deepcopy(row.get("start_position") or {}) for row in rows if row.get("start_position")}


def _spec_group(catalog: dict[str, dict[str, Any]], spec: str, group: int, mirrors: int | None = None) -> dict[str, Any]:
    bot = catalog_bot(catalog, spec)
    row = {
        "talent_group": group,
        "class_spec": spec,
        "role": spec_role(catalog, spec),
        "primary_talent_tree_id": int(bot["primary_talent_tree_id"]),
        "talents": copy.deepcopy(bot["talents"]),
        "primary_tree_spells": copy.deepcopy(bot.get("primary_tree_spells") or []),
        "glyphs": copy.deepcopy(bot.get("glyphs") or []),
        "gear_profile_id": str(bot["gear_profile_id"]),
        "mirrors_talent_group": mirrors,
    }
    for key in ("consumables", "profession_setup"):
        if bot.get(key) is not None:
            row[key] = copy.deepcopy(bot[key])
    if not row.get("consumables") and (fallback := contract_consumables(spec)) is not None:
        row["consumables"] = fallback
    return row


def character_group_spells(character: dict[str, Any]) -> dict[str, list[int]]:
    """Class spells a composition character declares for one of its specs only, by spec.

    Like `spells`, but the spell is provisioned only while that spec's talent group is active
    (raid_loadout_spells.loadout_known_spells), e.g. Faerie Fire 770 for Balance and Faerie Fire (Feral)
    16857 for the Feral tank.
    """
    declared = character.get("group_spells")
    if declared is None:
        return {}
    key = character.get("character_key")
    specs = [str(spec) for spec in character.get("specs") or []]
    if not isinstance(declared, dict) or not set(declared) <= set(specs):
        raise ShardPlanError(f"character_group_spells_invalid:{key}")
    result = {}
    for spec, spells in declared.items():
        if (not isinstance(spells, list) or not spells or len(set(spells)) != len(spells)
                or any(isinstance(spell, bool) or not isinstance(spell, int) or spell <= 0 for spell in spells)):
            raise ShardPlanError(f"character_group_spells_invalid:{key}:{spec}")
        result[spec] = sorted(spells)
    return result


def character_loadout_groups(catalog: dict[str, dict[str, Any]], character: dict[str, Any]) -> list[dict[str, Any]]:
    specs = [str(spec) for spec in character["specs"]]
    groups = [_spec_group(catalog, spec, index) for index, spec in enumerate(specs)]
    if len(groups) == 1:
        # A single-spec character mirrors its only build into talent group 1,
        # so every composition character has the same two-group shape.
        groups.append(_spec_group(catalog, specs[0], 1, mirrors=0))
    for group in groups:
        if group["mirrors_talent_group"] is None and (spells := character_group_spells(character).get(group["class_spec"])):
            group["spells"] = spells
    return groups


def _bot(composition: dict[str, Any], catalog: dict[str, dict[str, Any]], character: dict[str, Any],
         boss: dict[str, Any], native_key: str, copy_index: int, scenario_id: str, spec: str) -> dict[str, Any]:
    raid, mode = composition["raid"], composition["mode"]
    slot = int(character["slot"])
    key = str(character["character_key"])
    packed = ids.packed_index(raid, mode, int(boss["boss_number"]), copy_index, slot)
    groups = character_loadout_groups(catalog, character)
    active = next(group for group in groups if group["class_spec"] == spec and group["mirrors_talent_group"] is None)
    source = catalog_bot(catalog, spec)
    namespace = f"cata_raid/{raid}/{ids.mode_info(mode)['token']}/{native_key}/c{copy_index}"
    guid, account = ids.character_guid(packed), ids.account_id(packed)
    bot: dict[str, Any] = {
        "character_key": key,
        "composition_slot": slot,
        "canonical_roster_slot_id": key,
        "roster_slot_id": f"{scenario_id}:{key}",
        "name": ids.character_name(raid, boss["name_code"], mode, copy_index, slot),
        "account": ids.account_name(packed),
        "account_id": account,
        "expected_account_id": account,
        "character_guid": guid,
        "expected_character_guid": guid,
        "pool_tag": scenario_id,
        "runtime_profile_id": scenario_id,
        "class": int(source["class"]),
        "race": int(source["race"]),
        "gender": int(source.get("gender", 0)),
        "level": int(source.get("level", 85)),
        "role": active["role"],
        "class_spec": spec,
        "gear_profile": active["gear_profile_id"],
        "gear_profile_id": active["gear_profile_id"],
        "primary_talent_tree_id": active["primary_talent_tree_id"],
        "talents": copy.deepcopy(active["talents"]),
        "primary_tree_spells": copy.deepcopy(active["primary_tree_spells"]),
        "glyphs": copy.deepcopy(active["glyphs"]),
        "action_profile_id": spec,
        "canonical_setup": {
            "class_spec": spec,
            "talent_build_id": spec,
            "gear_profile_id": active["gear_profile_id"],
            "glyph_ids": copy.deepcopy(active["glyphs"]),
            "action_profile_id": spec,
            "source_config": composition["spec_source"],
            "action_profile_manifest": ACTION_PROFILE_MANIFEST,
        },
        "loadout": {
            "schema": "raid_character_loadout_v1",
            "talent_groups_count": len(groups),
            "active_talent_group": int(active["talent_group"]),
            "groups": groups,
            "bag": copy.deepcopy(composition["off_spec_bag"]),
            "item_guid_base": ids.item_guid_base(packed),
            "packed_index": packed,
        },
        "evidence_namespace": f"{namespace}/roster/{key}",
    }
    for field in ("consumables", "profession_setup"):
        if active.get(field) is not None:
            bot[field] = copy.deepcopy(active[field])
    if spells := character_spells(character):
        bot["spells"] = spells
    declared_pet = character_pet(character)
    if declared_pet is not None or source.get("pet"):
        pet = declared_pet if declared_pet is not None else {
            k: v for k, v in copy.deepcopy(source["pet"]).items() if k != "id_offset"}
        pet["name"] = (bot["name"].lower() + "pet")[:12]
        bot["pet"] = pet
        bot["expected_pet_id"] = ids.pet_id(packed)
    return bot


def validate_full_raid(composition: dict[str, Any], catalog: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    """The composition's end-to-end cohort entry, or None when it declares none.

    Its cohort, pool tag and runtime profile are one non-diagnostic ID
    (`<raid>_<size><diff>_full_c0`), never the legacy full-raid tag, which is
    a substring of every shard tag. `scenario_id` names the full-raid route
    the cohort's own scenario row is cloned from.
    """
    full = composition.get("full_raid")
    if full is None:
        return None
    raid, mode = str(composition["raid"]), str(composition["mode"])
    cohort = ids.cohort_id(raid, mode, FULL_RAID_KEY, 0)
    failures: list[dict[str, Any]] = []
    if not isinstance(full, dict):
        raise ShardPlanError(json.dumps({"check": "full_raid_not_an_object"}))
    for field in ("cohort_id", "runtime_profile_id", "pool_tag"):
        if full.get(field) != cohort:
            failures.append({"check": f"full_raid_{field}", "expected": cohort, "actual": full.get(field)})
    if not str(full.get("scenario_id") or "") or full.get("scenario_id") == cohort:
        failures.append({"check": "full_raid_route_template_scenario", "actual": full.get("scenario_id")})
    if full.get("route_scenario_id", cohort) != cohort:
        failures.append({"check": "full_raid_route_scenario_id", "expected": cohort, "actual": full.get("route_scenario_id")})
    if full.get("selection_status") not in SELECTION_STATUSES:
        failures.append({"check": "full_raid_selection_status"})
    multi = {str(row["character_key"]): [str(spec) for spec in row["specs"]]
             for row in composition["characters"] if len(row["specs"]) > 1}
    selection = full.get("spec_selection") if isinstance(full.get("spec_selection"), dict) else {}
    if set(selection) != set(multi) or any(spec not in multi.get(key, []) for key, spec in selection.items()):
        failures.append({"check": "full_raid_spec_selection", "expected": sorted(multi), "actual": selection})
    if any(int(row["boss_number"]) == FULL_RAID_BOSS_NUMBER or row["boss_key"] == FULL_RAID_KEY
           for row in composition["bosses"]):
        failures.append({"check": "full_raid_identity_block_taken_by_a_boss"})
    if not failures:
        counts = role_counts(composition, catalog, full)
        if counts["tank"] < 1 or counts["healer"] < 1 or sum(counts.values()) != int(composition["raid_size"]):
            failures.append({"check": "full_raid_role_counts", "role_counts": counts})
    if failures:
        raise ShardPlanError(json.dumps({"full_raid": cohort, "failures": failures}, sort_keys=True))
    return full


def full_raid_shard(composition: dict[str, Any], catalog: dict[str, dict[str, Any]], full: dict[str, Any],
                    starts: dict[str, dict[str, Any]]) -> dict[str, Any]:
    raid, mode = str(composition["raid"]), str(composition["mode"])
    info = ids.mode_info(mode)
    cohort = ids.cohort_id(raid, mode, FULL_RAID_KEY, 0)
    identity_boss = {"boss_number": FULL_RAID_BOSS_NUMBER, "name_code": FULL_RAID_NAME_CODE}
    specs = selected_specs(composition, full)
    bots = [_bot(composition, catalog, character, identity_boss, FULL_RAID_KEY, 0, cohort,
                 specs[str(character["character_key"])]) for character in composition["characters"]]
    bots.sort(key=lambda bot: (ROLE_ORDER[bot["role"]], bot["composition_slot"]))
    for bot in bots:
        # The full raid switches talent groups per boss at runtime (raid_full_route_mirror.py):
        # every group's own spells are known and each group's gear is a native equipment set.
        bot["loadout"]["runtime_spec_switch"] = True
    template = str(full["scenario_id"])
    start_source = cohort if cohort in starts else template
    return {
        "shard_id": cohort,
        "shard_kind": FULL_RAID_KIND,
        "cohort_id": cohort,
        "scenario_id": cohort,
        "pool_tag": cohort,
        "runtime_profile_id": cohort,
        "raid": raid,
        "mode": mode,
        "map_id": int(composition["map_id"]),
        "difficulty": info["difficulty"],
        "boss_key": FULL_RAID_KEY,
        "composition_boss_key": FULL_RAID_KIND,
        "boss_number": FULL_RAID_BOSS_NUMBER,
        "copy": 0,
        "evidence_namespace": f"cata_raid/{raid}/{info['token']}/{FULL_RAID_KEY}/c0",
        "required_bot_count": int(composition["raid_size"]),
        "role_counts": role_counts(composition, catalog, full),
        "spec_selection": {"specs": specs, "status": full["selection_status"], "rationale": full.get("rationale", "")},
        "start_position": copy.deepcopy(starts.get(start_source)) if start_source in starts else None,
        "start_position_source": start_source if start_source in starts else None,
        "route_template_scenario_id": template,
        "acceptance_scenario_id": template,
        "diagnostic_only": False,
        "diagnostic_parent_scenario_id": None,
        "lockout": {
            "schema": "raid_shard_lockout_request_v1",
            "raid": raid,
            "difficulty": mode,
            "map_id": int(composition["map_id"]),
            "precompleted_boss_keys": [],
            "precompleted_boss_indices": [],
            "precompleted_creature_entries": [],
            "seed_boss_argument": "none",
            "state_source": "fresh_instance",
            "diagnostic_only_assistance": False,
            "certifies_predecessors": False,
        },
        "live_identity_requirements": {
            "fields": list(LIVE_IDENTITY_FIELDS),
            "must_be_positive": True,
            "must_be_distinct_across_shards": True,
            "assigned_at": "live_setup_only",
            "fixture_values": None,
        },
        "runtime_profile": full_raid_runtime_profile_row(composition, cohort),
        "bots": bots,
    }


def full_raid_runtime_profile_row(composition: dict[str, Any], cohort: str) -> dict[str, Any]:
    """The end-to-end cohort's profile (mirrors the legacy full-raid profile; natural kills only)."""
    info = ids.mode_info(composition["mode"])
    return {
        "name": cohort,
        "description": "Canonical-composition end-to-end cohort on the full raid route; every kill is natural.",
        "target_population": int(composition["raid_size"]),
        "pool_tag_filter": cohort,
        "spawn_mode": "resume_or_race_start",
        "allow_configured_center_fallback": False,
        "use_saved_position": True,
        "allow_questing": False,
        "allow_dungeons": True,
        "allow_raids": True,
        "raid_size": int(composition["raid_size"]),
        "raid_difficulty": int(info["raid_difficulty"]),
        "track_heroic_raid_progression": False,
        "enable_progression": True,
        "auto_start_recording": False,
        "validation_route": {
            "enable": True,
            "manifest_path": "dataset/validation_scenarios/validation_routes.jsonl",
            "advance_mode": "terminal",
            "scenario_id": cohort,
        },
    }


def build_shard_plan(
    composition: dict[str, Any],
    prerequisites: dict[str, Any],
    *,
    copies: int | None = None,
    boss_keys: Iterable[str] | None = None,
    starts: dict[str, dict[str, Any]] | None = None,
    provisioning_defaults: dict[str, Any] | None = None,
    sources: dict[str, Any] | None = None,
) -> dict[str, Any]:
    catalog = load_catalog(composition)
    validate_composition(composition, catalog)
    raid, mode = str(composition["raid"]), str(composition["mode"])
    info = ids.mode_info(mode)
    bosses_by_key = validate_prerequisites(prerequisites, raid, mode, int(composition["map_id"]))
    joined = join_bosses(composition, bosses_by_key)
    copies = int(copies if copies is not None else composition.get("default_copies", 1))
    if not 1 <= copies <= ids.MAX_COPIES:
        raise ShardPlanError(f"copies_out_of_range:{copies}")
    full = validate_full_raid(composition, catalog)
    wanted = set(boss_keys or [row["boss_key"] for row in composition["bosses"]] + ([FULL_RAID_KEY] if full else []))
    unknown = wanted - {row["boss_key"] for row in composition["bosses"]} - ({FULL_RAID_KEY} if full else set())
    if unknown:
        raise ShardPlanError(f"unknown_composition_bosses:{sorted(unknown)}")
    starts = starts if starts is not None else scenario_starts()
    parent = f"{raid}_{info['token']}"
    shards = []
    for boss in sorted(composition["bosses"], key=lambda row: int(row["boss_number"])):
        if boss["boss_key"] not in wanted:
            continue
        native = joined[boss["boss_key"]]
        native_key = str(native["key"])
        closure = precompleted_closure(bosses_by_key, native_key)
        specs = selected_specs(composition, boss)
        for copy_index in range(copies):
            cohort = ids.cohort_id(raid, mode, native_key, copy_index)
            scenario_id = ids.pool_tag(cohort)
            start_source = scenario_id if scenario_id in starts else str(boss.get("route_template_scenario_id") or "")
            bots = [_bot(composition, catalog, character, boss, native_key, copy_index, scenario_id,
                         specs[str(character["character_key"])])
                    for character in composition["characters"]]
            bots.sort(key=lambda bot: (ROLE_ORDER[bot["role"]], bot["composition_slot"]))
            keys = [str(row["key"]) for row in closure]
            shards.append({
                "shard_id": cohort,
                "shard_kind": BOSS_SHARD_KIND,
                "cohort_id": cohort,
                "scenario_id": scenario_id,
                "pool_tag": scenario_id,
                "runtime_profile_id": scenario_id,
                "raid": raid,
                "mode": mode,
                "map_id": int(composition["map_id"]),
                "difficulty": info["difficulty"],
                "boss_key": native_key,
                "composition_boss_key": boss["boss_key"],
                "boss_number": int(boss["boss_number"]),
                "copy": copy_index,
                "evidence_namespace": f"cata_raid/{raid}/{info['token']}/{native_key}/c{copy_index}",
                "required_bot_count": int(composition["raid_size"]),
                "role_counts": role_counts(composition, catalog, boss),
                "spec_selection": {"specs": specs, "status": boss["selection_status"],
                                   "rationale": boss.get("rationale", "")},
                "start_position": copy.deepcopy(starts.get(start_source)) if start_source in starts else None,
                "start_position_source": start_source if start_source in starts else None,
                "route_template_scenario_id": boss.get("route_template_scenario_id"),
                "diagnostic_only": True,
                "diagnostic_parent_scenario_id": parent,
                "lockout": {
                    "schema": "raid_shard_lockout_request_v1",
                    "raid": raid,
                    "difficulty": mode,
                    "map_id": int(composition["map_id"]),
                    "precompleted_boss_keys": keys,
                    "precompleted_boss_indices": [int(row["boss_index"]) for row in closure],
                    "precompleted_creature_entries": [int(row.get("creature_entry") or 0) for row in closure],
                    "seed_boss_argument": ",".join(keys) if keys else "none",
                    "state_source": PREREQUISITE_SCHEMA,
                    "diagnostic_only_assistance": True,
                    "certifies_predecessors": False,
                },
                "live_identity_requirements": {
                    "fields": list(LIVE_IDENTITY_FIELDS),
                    "must_be_positive": True,
                    "must_be_distinct_across_shards": True,
                    "assigned_at": "live_setup_only",
                    "fixture_values": None,
                },
                "runtime_profile": runtime_profile_row(composition, scenario_id, parent, keys, closure),
                "bots": bots,
            })
    if full and FULL_RAID_KEY in wanted:
        shards.append(full_raid_shard(composition, catalog, full, starts))
    plan = {
        "schema": PLAN_SCHEMA,
        "composition_id": composition["composition_id"],
        "raid": raid,
        "mode": mode,
        "map_id": int(composition["map_id"]),
        "difficulty": info["difficulty"],
        "raid_size": int(composition["raid_size"]),
        "copies": copies,
        "shard_count": len(shards),
        "bot_count": sum(len(shard["bots"]) for shard in shards),
        "identity_scheme": ids.scheme_description(),
        "reserved_ranges": ids.reserved_ranges(raid, mode),
        "provisioning_defaults": copy.deepcopy(provisioning_defaults or {}),
        "sources": copy.deepcopy(sources or {}),
        "shards": shards,
    }
    validate_shard_plan(plan)
    return plan


def runtime_profile_row(composition: dict[str, Any], scenario_id: str, parent: str,
                        keys: list[str], closure: list[dict[str, Any]]) -> dict[str, Any]:
    """Runtime profile the coordinator adds for this cohort (mirrors the legacy shard rows)."""
    info = ids.mode_info(composition["mode"])
    return {
        "name": scenario_id,
        "description": "Diagnostic-only raid boss shard; seeded predecessors are assistance and never certify kills.",
        "target_population": int(composition["raid_size"]),
        "pool_tag_filter": scenario_id,
        "spawn_mode": "resume_or_race_start",
        "allow_configured_center_fallback": False,
        "use_saved_position": True,
        "allow_questing": False,
        "allow_dungeons": True,
        "allow_raids": True,
        "raid_size": int(composition["raid_size"]),
        "raid_difficulty": int(info["raid_difficulty"]),
        "track_heroic_raid_progression": False,
        "enable_progression": True,
        "diagnostic_only": True,
        "diagnostic_parent_scenario_id": parent,
        "prerequisite_contract": {
            "certifies_predecessors": False,
            "precompleted_boss_keys": list(keys),
            "precompleted_boss_entries": [int(row.get("creature_entry") or 0) for row in closure],
        },
        "validation_route": {
            "enable": True,
            "manifest_path": "dataset/validation_scenarios/validation_routes.jsonl",
            "advance_mode": "terminal",
            "scenario_id": scenario_id,
        },
    }


def _duplicates(values: Iterable[Any]) -> list[Any]:
    seen: set[Any] = set()
    duplicates = []
    for value in values:
        if value in seen and value not in duplicates:
            duplicates.append(value)
        seen.add(value)
    return duplicates


def validate_shard_plan(plan: dict[str, Any], name_validators: ids.NameValidators | None = None) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    if plan.get("schema") != PLAN_SCHEMA:
        failures.append({"check": "schema"})
    shards = plan.get("shards") if isinstance(plan.get("shards"), list) else []
    if int(plan.get("shard_count") or -1) != len(shards) or not shards:
        failures.append({"check": "shard_count"})
    bots = [bot for shard in shards for bot in shard.get("bots", [])]
    if int(plan.get("bot_count") or -1) != len(bots):
        failures.append({"check": "bot_count"})
    for field in ("account_id", "account", "character_guid", "name", "roster_slot_id", "evidence_namespace", "expected_pet_id"):
        values = [bot.get(field) for bot in bots if bot.get(field) is not None]
        if _duplicates(values):
            failures.append({"check": f"duplicate_{field}"})
    item_bases = [bot.get("loadout", {}).get("item_guid_base") for bot in bots]
    if _duplicates(item_bases) or any(not isinstance(base, int) for base in item_bases):
        failures.append({"check": "item_guid_ranges"})
    for field in ("cohort_id", "pool_tag", "scenario_id", "evidence_namespace"):
        if _duplicates(shard.get(field) for shard in shards):
            failures.append({"check": f"duplicate_shard_{field}"})
    for shard in shards:
        cohort = str(shard.get("cohort_id") or "")
        full = shard.get("shard_kind") == FULL_RAID_KIND
        # Boss shards are diagnostic (`_diagnostic` tag); the end-to-end cohort's tag is its cohort ID.
        tag = cohort if full else ids.pool_tag(cohort)
        if any(shard.get(field) != tag for field in ("scenario_id", "pool_tag", "runtime_profile_id")):
            failures.append({"check": "shard_pool_binding", "cohort_id": cohort})
        if cohort != ids.cohort_id(str(shard.get("raid")), str(shard.get("mode")), str(shard.get("boss_key")), int(shard.get("copy", -1))):
            failures.append({"check": "cohort_naming_contract", "cohort_id": cohort})
        if full and (shard.get("boss_key") != FULL_RAID_KEY or shard.get("diagnostic_only") is not False
                     or int(shard.get("copy", -1)) != 0):
            failures.append({"check": "full_raid_cohort_contract", "cohort_id": cohort})
        lockout = shard.get("lockout") or {}
        if (lockout.get("certifies_predecessors") is not False
                or lockout.get("diagnostic_only_assistance") is not (not full)
                or (full and lockout.get("precompleted_boss_keys"))
                or str(shard.get("boss_key")) in (lockout.get("precompleted_boss_keys") or [])):
            failures.append({"check": "lockout_contract", "cohort_id": cohort})
        if (shard.get("live_identity_requirements") or {}).get("fixture_values") is not None:
            failures.append({"check": "live_identity_must_be_runtime_only", "cohort_id": cohort})
        shard_bots = shard.get("bots") or []
        if len(shard_bots) != int(shard.get("required_bot_count") or -1):
            failures.append({"check": "shard_bot_count", "cohort_id": cohort})
        counts = {role: sum(bot.get("role") == role for bot in shard_bots) for role in ROLE_ORDER}
        if counts != shard.get("role_counts"):
            failures.append({"check": "shard_role_counts", "cohort_id": cohort})
        for bot in shard_bots:
            name = str(bot.get("name") or "")
            reasons = ids.name_rule_failures(name, name_validators)
            if reasons:
                failures.append({"check": "character_name", "name": name, "reasons": reasons})
            if bot.get("pool_tag") != tag or bot.get("runtime_profile_id") != tag:
                failures.append({"check": "bot_pool_binding", "name": name})
            if bot.get("expected_account_id") != bot.get("account_id") or bot.get("expected_character_guid") != bot.get("character_guid"):
                failures.append({"check": "identity_expectation_drift", "name": name})
            # A missing contract set fails the whole raid's prepull minutes into a
            # live run (round 2: raid_prepull_unknown_spec_contract_beast_mastery_hunter).
            if (reason := prepull_contract_failure(bot)) is not None:
                failures.append({"check": "prepull_consumable_contract", "name": name,
                                 "class_spec": bot.get("class_spec"), "reason": reason})
            overlaps = ids.legacy_overlaps({"character_guid": bot.get("character_guid"), "account_id": bot.get("account_id"),
                                            "pet_id": bot.get("expected_pet_id"),
                                            "item_guid": (bot.get("loadout") or {}).get("item_guid_base")})
            if overlaps:
                failures.append({"check": "legacy_identity_overlap", "name": name, "fields": overlaps})
            loadout = bot.get("loadout") or {}
            groups = loadout.get("groups") or []
            active = int(loadout.get("active_talent_group", -1))
            if (int(loadout.get("talent_groups_count") or 0) != 2 or len(groups) != 2
                    or not 0 <= active < len(groups) or groups[active].get("class_spec") != bot.get("class_spec")
                    or groups[active].get("mirrors_talent_group") is not None
                    or groups[active].get("role") != bot.get("role")
                    or groups[active].get("talents") != bot.get("talents")
                    or groups[active].get("glyphs") != bot.get("glyphs")):
                failures.append({"check": "loadout_active_group", "name": name})
    if failures:
        raise ShardPlanError(json.dumps({"schema": plan.get("schema"), "failures": failures}, sort_keys=True))
    return {"all_passed": True, "shard_count": len(shards), "bot_count": len(bots)}


def load_plan_inputs(composition_path: Path, prerequisites_dir: Path = PREREQUISITES_DIR,
                     provisioning_config: Path = PROVISIONING_CONFIG,
                     scenario_config: Path = SCENARIO_CONFIG,
                     gear_profiles: Path = GEAR_PROFILES,
                     trainers: Path = TRAINERS) -> tuple[dict, dict, dict, dict, dict]:
    composition = read_json(composition_path)
    prerequisite_file = prerequisites_path(str(composition["raid"]), prerequisites_dir)
    if not prerequisite_file.is_file():
        raise ShardPlanError(f"prerequisite_file_missing:{relative(prerequisite_file)}")
    prerequisites = read_json(prerequisite_file)
    provisioning = read_json(provisioning_config)
    defaults = {key: copy.deepcopy(provisioning[key]) for key in PROVISIONING_DEFAULT_KEYS if key in provisioning}
    catalog_path = repo_path(str(composition["spec_source"]))
    sources = {
        "composition": {"path": relative(composition_path), "sha256": sha256_file(composition_path)},
        "prerequisites": {"path": relative(prerequisite_file), "sha256": sha256_file(prerequisite_file)},
        "spec_catalog": {"path": relative(catalog_path), "sha256": sha256_file(catalog_path)},
        "provisioning_defaults": {"path": relative(provisioning_config), "sha256": sha256_file(provisioning_config)},
    }
    if Path(scenario_config).is_file():
        sources["scenario_starts"] = {"path": relative(scenario_config), "sha256": sha256_file(scenario_config)}
    # Materialization inputs: the spellbook baseline (class trainers), the
    # action-profile spells and both gear layers. A plan is later refused if
    # any of them drifted (raid_loadout_sql.check_plan_sources).
    for name, path in (("trainers", trainers), ("action_profiles", ACTION_PROFILES),
                       ("gear_profiles", gear_profiles), ("wowsims_gear_profiles", WOWSIMS_GEAR_PROFILES)):
        if not Path(path).is_file():
            raise ShardPlanError(f"plan_source_missing:{name}:{relative(Path(path))}")
        sources[name] = {"path": relative(Path(path)), "sha256": sha256_file(Path(path))}
    return composition, prerequisites, defaults, scenario_starts(scenario_config), sources


def main() -> int:
    parser = argparse.ArgumentParser(description="Expand raid compositions into boss shard copies and provisioning SQL.")
    parser.add_argument("--composition", type=Path, action="append",
                        help="Composition JSON; defaults to every file in experiments/configs/raid_compositions.")
    parser.add_argument("--prerequisites-dir", type=Path, default=PREREQUISITES_DIR)
    parser.add_argument("--provisioning-config", type=Path, default=PROVISIONING_CONFIG)
    parser.add_argument("--scenario-config", type=Path, default=SCENARIO_CONFIG)
    parser.add_argument("--gear-profiles", type=Path, default=GEAR_PROFILES)
    parser.add_argument("--trainers", type=Path, default=TRAINERS)
    parser.add_argument("--dbc-dir", type=Path, default=REPO_ROOT / "data/dbc/enUS")
    parser.add_argument("--copies", type=int)
    parser.add_argument("--output-dir", type=Path, default=REPO_ROOT / "dataset/raid_shard_provisioning")
    parser.add_argument("--check", action="store_true", help="Build and verify in memory; write nothing.")
    args = parser.parse_args()

    from tools.raid_program.raid_loadout_sql import write_plan_outputs

    paths = args.composition or sorted(COMPOSITION_DIR.glob("*.json"))
    summaries = []
    for path in paths:
        composition, prerequisites, defaults, starts, sources = load_plan_inputs(
            path, args.prerequisites_dir, args.provisioning_config, args.scenario_config,
            args.gear_profiles, args.trainers)
        plan = build_shard_plan(composition, prerequisites, copies=args.copies, starts=starts,
                                provisioning_defaults=defaults, sources=sources)
        validate_shard_plan(plan, ids.load_name_validators(args.dbc_dir))
        summaries.append(write_plan_outputs(plan, args.gear_profiles, args.dbc_dir,
                                            None if args.check else args.output_dir / plan["composition_id"],
                                            trainers_path=args.trainers))
    print(json.dumps(summaries, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
