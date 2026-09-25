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
from pathlib import Path
from typing import Any, Iterable

from tools.raid_program import raid_shard_identity as ids
from tools.raid_program.raid_composition import (
    COMPOSITION_DIR,
    REPO_ROOT,
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
SCENARIO_CONFIG = REPO_ROOT / "experiments/configs/validation_scenarios_cata_001.json"
ACTION_PROFILE_MANIFEST = "experiments/configs/cata_434_action_profiles.json"
LIVE_IDENTITY_FIELDS = ("group_id", "map_instance_id", "save_id", "attempt_id", "strategy_id", "assignment_generation")
PROVISIONING_DEFAULT_KEYS = ("account_password", "default_money", "default_skills", "default_consumables", "max_level")
ROLE_ORDER = {"tank": 0, "healer": 1, "dps": 2}


class ShardPlanError(ValueError):
    pass


def relative(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


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
    return row


def character_loadout_groups(catalog: dict[str, dict[str, Any]], character: dict[str, Any]) -> list[dict[str, Any]]:
    specs = [str(spec) for spec in character["specs"]]
    groups = [_spec_group(catalog, spec, index) for index, spec in enumerate(specs)]
    if len(groups) == 1:
        # A single-spec character mirrors its only build into talent group 1,
        # so every composition character has the same two-group shape.
        groups.append(_spec_group(catalog, specs[0], 1, mirrors=0))
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
    if source.get("pet"):
        pet = {k: v for k, v in copy.deepcopy(source["pet"]).items() if k != "id_offset"}
        pet["name"] = (bot["name"].lower() + "pet")[:12]
        bot["pet"] = pet
        bot["expected_pet_id"] = ids.pet_id(packed)
    return bot


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
    wanted = set(boss_keys or [row["boss_key"] for row in composition["bosses"]])
    unknown = wanted - {row["boss_key"] for row in composition["bosses"]}
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
        tag = ids.pool_tag(cohort)
        if any(shard.get(field) != tag for field in ("scenario_id", "pool_tag", "runtime_profile_id")):
            failures.append({"check": "shard_pool_binding", "cohort_id": cohort})
        if cohort != ids.cohort_id(str(shard.get("raid")), str(shard.get("mode")), str(shard.get("boss_key")), int(shard.get("copy", -1))):
            failures.append({"check": "cohort_naming_contract", "cohort_id": cohort})
        lockout = shard.get("lockout") or {}
        if (lockout.get("certifies_predecessors") is not False or lockout.get("diagnostic_only_assistance") is not True
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
                     scenario_config: Path = SCENARIO_CONFIG) -> tuple[dict, dict, dict, dict, dict]:
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
    return composition, prerequisites, defaults, scenario_starts(scenario_config), sources


def main() -> int:
    parser = argparse.ArgumentParser(description="Expand raid compositions into boss shard copies and provisioning SQL.")
    parser.add_argument("--composition", type=Path, action="append",
                        help="Composition JSON; defaults to every file in experiments/configs/raid_compositions.")
    parser.add_argument("--prerequisites-dir", type=Path, default=PREREQUISITES_DIR)
    parser.add_argument("--provisioning-config", type=Path, default=PROVISIONING_CONFIG)
    parser.add_argument("--scenario-config", type=Path, default=SCENARIO_CONFIG)
    parser.add_argument("--gear-profiles", type=Path, default=REPO_ROOT / "dataset/validation_gear_profiles/profiles.json")
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
            path, args.prerequisites_dir, args.provisioning_config, args.scenario_config)
        plan = build_shard_plan(composition, prerequisites, copies=args.copies, starts=starts,
                                provisioning_defaults=defaults, sources=sources)
        validate_shard_plan(plan, ids.load_name_validators(args.dbc_dir))
        summaries.append(write_plan_outputs(plan, args.gear_profiles, args.dbc_dir,
                                            None if args.check else args.output_dir / plan["composition_id"]))
    print(json.dumps(summaries, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
