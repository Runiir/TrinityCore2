"""Build content-phase gear profiles for the canonical raid compositions bound to a phase.

    python -m tools.bot_ml.build_phase_gear_profiles --output-dir dataset/raid_phase_gear_profiles

Every phase config in ``experiments/configs/raid_gear_phases`` that a raid
composition declares (``gear_phase``) produces one profile per spec its
characters use, keyed ``<phase_id>/<class_spec>``. The shared validation gear
profiles are read (as enchant donors) and never written. The output is
validated before it is written; any violation raises and writes nothing.

The builder never reads the database: world loot/vendor rows and hotfix item
rows come from the phase's pinned extract (``extract_phase_gear_db``,
``dataset/raid_phase_gear_db_extract``), a declared stage dependency.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping

from tools.bot_ml.build_validation_gear_profiles import (
    item_definition_compatible,
    load_gem_properties,
    load_item_limit_categories,
    role_archetype,
    stat_map,
    stat_weights_for_bot,
)
from tools.bot_ml.build_validation_provisioning import gem_item_enchant_map, load_gear_profiles, runtime_safe_enchantments
from tools.bot_ml.common import stable_hash, write_json
from tools.bot_ml.player_gear_acquisition import DEFAULT_ITEM_SOURCE_INDEX
from tools.bot_ml.phase_gear_equip_restrictions import (
    character_view,
    check_reputation_policy,
    load_race_teams,
    restricted_items,
)
from tools.bot_ml.phase_gear_item_effects import (
    item_spell_stats,
    load_spell_effects,
    modeled_effect_stats,
    off_spec_families,
    spec_primary_family,
)
from tools.bot_ml.phase_gear_extract import DEFAULT_EXTRACT_DIR, item_facts, load_phase_extract, phase_items
from tools.bot_ml.phase_gear_oracles import GEM_COLOR_META, RESILIENCE_STAT, load_enchant_oracle
from tools.bot_ml.phase_gear_profiles import (
    PHASE_CONFIG_DIR,
    PHASE_PROFILES_SCHEMA,
    REPO_ROOT,
    composition_gear_phase,
    phase_profile_id,
)
from tools.bot_ml.phase_gear_selection import SpecRequest, build_spec_loadout, item_equip_limit, item_value
from tools.bot_ml.phase_gear_sources import (
    DEFAULT_RECIPE_SOURCE_INDEX,
    admit_sources,
    crafted_sources,
    encounter_maps,
    item_set_names,
    load_extended_costs,
    world_sources_from_rows,
)
from tools.bot_ml.phase_gear_spell_requirements import apply_spell_exemptions, load_spell_requirements, spec_required_spells
from tools.bot_ml.phase_gear_validation import validate_phase_profiles
from tools.bot_ml.validation_profile_manifests import DEFAULT_COMBAT_LOOT_PROFILE_MANIFEST, load_combat_loot_profile_manifest

COMPOSITION_DIR = REPO_ROOT / "experiments/configs/raid_compositions"
SHARED_GEAR_PROFILES = REPO_ROOT / "dataset/validation_gear_profiles/profiles.json"


class PhaseBuildError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def relative(path: Path) -> str:
    try:
        return Path(path).resolve().relative_to(REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def bound_compositions(phase_id: str, composition_dir: Path) -> list[dict[str, Any]]:
    bound = []
    for path in sorted(Path(composition_dir).glob("*.json")):
        composition = json.loads(path.read_text(encoding="utf-8"))
        phase = composition_gear_phase(composition)
        if phase and phase["phase_id"] == phase_id:
            bound.append({"path": path, "composition": composition})
    return bound


def spec_characters(compositions: list[Mapping[str, Any]], teams: Mapping[int, str]) -> dict[str, list[Any]]:
    """{spec: the characters that wear its profile}: race, class and level of the catalog build the shard
    plan provisions (raid_shard_plan._bot reads them from catalog_bot), one per distinct build."""
    result: dict[str, dict[str, Any]] = defaultdict(dict)
    for entry in compositions:
        composition = entry["composition"]
        catalog = {row["spec_target_id"]: row for row in
                   json.loads((REPO_ROOT / str(composition["spec_source"])).read_text(encoding="utf-8"))["targets"]}
        for character in composition["characters"]:
            for spec in (str(value) for value in character["specs"]):
                view = character_view(catalog[spec]["provisioning_bot"], teams)
                result[spec][view.key()] = view
    return {spec: [views[key] for key in sorted(views)] for spec, views in result.items()}


def character_row(view) -> dict[str, Any]:
    return {"race": view.race, "class": view.class_id, "level": view.level, "team": view.team}


def spec_weights(bot: Mapping[str, Any], manifest: Mapping[str, Any], config: Mapping[str, Any]) -> dict[str, float]:
    weights = stat_weights_for_bot(dict(bot), dict(manifest))
    weights.update({name: float(value) for name, value in
                    (config.get("stat_weight_overrides_by_spec") or {}).get(str(bot["class_spec"]), {}).items()})
    return weights


def gear_items(items: list[dict[str, Any]], config: Mapping[str, Any], world: Mapping[str, Any], crafted, costs,
               facts: Mapping[int, Mapping[str, int]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    policy = config["item_policy"]
    loot_items = set(world["loot"])
    admitted, rejected = [], defaultdict(int)
    for item in items:
        if int(item.get("ClassID") or 0) not in (2, 4):
            continue
        level = int(item.get("ItemLevel") or 0)
        if level > int(policy["max_item_level"]):
            rejected["above_phase_item_level"] += 1
            continue
        if level < int(policy["min_item_level"]):
            continue
        if not int(policy["min_quality"]) <= int(item.get("Quality") or 0) <= int(policy["max_quality"]) \
                or int(item.get("RequiredLevel") or 0) > int(policy["max_required_level"]) or not item_definition_compatible(item):
            continue
        if any(int(item.get(f"ItemStatType{index}") or 0) == RESILIENCE_STAT and int(item.get(f"ItemStatValue{index}") or 0)
               for index in range(1, 11)):
            rejected["pvp_resilience"] += 1
            continue
        sources, reasons = admit_sources(item, world, crafted, costs, config, loot_items,
                                         int((facts.get(int(item["ID"])) or {}).get("bonding") or 0))
        if not sources:
            for reason in reasons:
                rejected[reason] += 1
            continue
        admitted.append(dict(item, player_acquisition={"phase_id": config["phase_id"], "sources": sources}))
    return admitted, dict(sorted(rejected.items()))


def gem_catalog(items: list[dict[str, Any]], config: Mapping[str, Any], world, crafted, costs, facts, dbc_dir: Path,
                oracle) -> list[dict[str, Any]]:
    policy = config["gem_policy"]
    properties = load_gem_properties(dbc_dir)
    mapping = gem_item_enchant_map(Path(dbc_dir))
    loot_items = set(world["loot"])
    gems = []
    for item in items:
        gem_property = properties.get(int(item.get("GemProperties") or 0))
        if not gem_property or int(item["ID"]) not in mapping:
            continue
        fact = facts.get(int(item["ID"])) or {}
        if int(item.get("Quality") or 0) > int(policy["max_quality"]) \
                or not int(policy["min_item_level"]) <= int(item.get("ItemLevel") or 0) <= int(policy["max_item_level"]):
            continue
        if (policy.get("exclude_item_limit_category") and int(item.get("ItemLimitCategory") or 0)) \
                or (policy.get("exclude_required_skill") and int(fact.get("required_skill") or 0)):
            continue
        enchant = oracle.enchants.get(int(mapping[int(item["ID"])])) or {}
        if not enchant.get("stats") or RESILIENCE_STAT in enchant.get("stat_types", []):
            continue
        sources, _reasons = admit_sources(item, world, crafted, costs, config, loot_items, int(fact.get("bonding") or 0))
        if not sources:
            continue
        gems.append({"item_id": int(item["ID"]), "name": item.get("Display") or "", "quality": int(item["Quality"]),
                     "item_level": int(item["ItemLevel"]), "color": int(gem_property["color"]),
                     "enchant_id": int(mapping[int(item["ID"])]), "stats": dict(enchant["stats"]),
                     "condition_id": int(enchant.get("condition_id") or 0), "sources": sources[:3]})
    if not any(gem["color"] == GEM_COLOR_META for gem in gems) or not any(gem["color"] != GEM_COLOR_META for gem in gems):
        raise PhaseBuildError(f"phase_gem_catalog_incomplete:{config['phase_id']}")
    return sorted(gems, key=lambda gem: gem["item_id"])


def profile_row(row: Mapping[str, Any], gem_mapping: Mapping[int, int], oracle, dbc_dir: Path,
                weights: Mapping[str, float]) -> dict[str, Any]:
    item = row["item"]
    gems = [int(gem["item_id"]) for gem in row["gems"]]
    reforge = row.get("reforge")
    enchant = oracle.enchants.get(int(row["enchant_id"])) or {}
    base = {"slot": int(row["slot"]), "item_id": int(item["ID"]), "enchant_id": int(row["enchant_id"]),
            "gem_item_ids": gems, "gem_enchant_ids": [int(gem_mapping[gem]) for gem in gems],
            "reforge_id": int(reforge["reforge_id"]) if reforge else 0, "inventory_type": int(item["InventoryType"])}
    base["enchantments"] = runtime_safe_enchantments(base, dict(gem_mapping), Path(dbc_dir))
    return {**base, "name": item.get("Display") or "", "item_level": int(item["ItemLevel"]), "quality": int(item["Quality"]),
            "item_class": int(item["ClassID"]), "subclass": int(item["SubclassID"]),
            "allowable_class": int(item.get("AllowableClass") or -1), "stats": stat_map(item),
            "native_socket_colors": list(row["native_socket_colors"]), "extra_socket": bool(row["extra_socket"]),
            "gem_names": [gem["name"] for gem in row["gems"]], "tier_piece": bool(row["tier_piece"]),
            "enchant_name": enchant.get("name", ""), "enchant_stats": dict(enchant.get("stats") or {}),
            "enchant_authority": row["enchant_authority"], "reforge": reforge, "meta_gem": row.get("meta_gem"),
            "source": "phase_scoped_acquisition", "player_accessible": True,
            "player_acquisition": item["player_acquisition"], "selection_score": item_value(item, weights)}


def build_phase(config_path: Path, args) -> dict[str, Any]:
    from tools.bot_ml.phase_gear_profiles import load_phase_config
    from tools.bot_ml.wowsims_gear_binding import resolve_profession_setup

    config = load_phase_config(config_path)
    check_reputation_policy(config)
    phase_id = config["phase_id"]
    compositions = bound_compositions(phase_id, args.compositions_dir)
    if not compositions:
        return {"phase_id": phase_id, "profiles": {}, "compositions": [], "report": {"skipped": "no_bound_composition"}}
    dbc_dir = Path(args.dbc_dir)
    oracle = load_enchant_oracle(dbc_dir)
    characters_by_spec = spec_characters(compositions, load_race_teams(dbc_dir))
    extract = load_phase_extract(args.db_extract_dir, config, dbc_dir)
    facts = item_facts(dbc_dir, extract["hotfix"])
    items = phase_items(dbc_dir, extract["hotfix"], facts, int(config["item_policy"]["max_required_level"]))
    world = world_sources_from_rows(extract["world"], config, encounter_maps(dbc_dir))
    spell_requirements = load_spell_requirements(dbc_dir)
    costs = load_extended_costs(dbc_dir)
    crafted = crafted_sources(dbc_dir, args.recipe_index, config["sources"]["crafted"]["profession_skill_ids"],
                              args.item_source_index)
    candidates, rejected = gear_items(items, config, world, crafted, costs, facts)
    effects = load_spell_effects(dbc_dir)
    effect_policy = config["item_effect_policy"]
    spell_rows = {int(item["ID"]): item_spell_stats(facts.get(int(item["ID"])), effects) for item in candidates}
    candidates = [dict(item, effect_stats=modeled_effect_stats(spell_rows[int(item["ID"])], effect_policy["uptime_by_kind"]))
                  if spell_rows[int(item["ID"])] else item for item in candidates]
    families_by_spec: dict[str, str] = {}
    gems = gem_catalog(items, config, world, crafted, costs, facts, dbc_dir, oracle)
    manifest = load_combat_loot_profile_manifest(args.profile_manifest)
    donors = load_gear_profiles(Path(args.shared_gear_profiles), dbc_dir=dbc_dir)
    set_names = item_set_names(dbc_dir)
    item_sets = {item_id: fact["item_set"] for item_id, fact in facts.items() if fact["item_set"]}
    limits = {category: int(row["quantity"]) for category, row in load_item_limit_categories(dbc_dir).items()}
    gem_mapping = gem_item_enchant_map(dbc_dir)
    gem_colors = {int(gem["item_id"]): int(gem["color"]) for gem in gems}
    socket_bonus = {item_id: fact["socket_bonus"] for item_id, fact in facts.items() if fact["socket_bonus"]}
    equip_limits = {item_id: limit for item_id, fact in facts.items() if (limit := item_equip_limit(fact)) is not None}
    profiles: dict[str, Any] = {}
    requirements_by_spec: dict[str, Any] = {}
    restricted_by_spec: dict[str, dict[str, int]] = {}
    built_items: dict[str, set[int]] = {}
    pairings: dict[str, set[str]] = defaultdict(set)
    for entry in compositions:
        composition = entry["composition"]
        catalog_path = REPO_ROOT / str(composition["spec_source"])
        targets = json.loads(catalog_path.read_text(encoding="utf-8"))["targets"]
        catalog = {row["spec_target_id"]: row for row in targets}
        for character in composition["characters"]:
            specs = [str(spec) for spec in character["specs"]]
            for spec in specs:
                pairings[spec] |= set(specs) - {spec}
            for spec in specs:
                profile_id = phase_profile_id(phase_id, spec)
                if profile_id in profiles:
                    continue
                target = catalog[spec]
                bot = dict(target["provisioning_bot"])
                required, exempted = apply_spell_exemptions(spec, spec_required_spells(target, targets, spell_requirements), config)
                # Professions follow the phase gear's own enchants, so no profession skill is certain
                # before the gear is chosen: a skill-gated item is refused here (fail closed).
                restricted = restricted_items((int(item["ID"]) for item in candidates), facts, characters_by_spec[spec])
                restricted_by_spec[spec] = dict(sorted(Counter(reason.split(":", 2)[1] for reasons in restricted.values()
                                                               for reason in reasons).items()))
                requirements_by_spec[spec] = required
                set_name = (config.get("tier_sets_by_spec") or {}).get(spec)
                set_ids = [value for value in set_names.get(str(set_name), []) if value] if set_name else []
                if set_name and not set_ids:
                    raise PhaseBuildError(f"tier_set_unknown:{spec}:{set_name}")
                excluded_items: set[int] = set()
                excluded_categories: set[int] = set()
                for partner in pairings[spec]:
                    for item_id in built_items.get(partner, set()):
                        if facts.get(item_id, {}).get("max_count"):
                            excluded_items.add(item_id)
                        category = next((int(item.get("ItemLimitCategory") or 0) for item in candidates if int(item["ID"]) == item_id), 0)
                        if category:
                            excluded_categories.add(category)
                donor = {int(row["slot"]): row for row in (donors.get(str(target["gear_profile_id"])) or {}).get("equipment", [])}
                weights = spec_weights(bot, manifest, config)
                family = spec_primary_family(config, spec, weights)
                families_by_spec[spec] = family
                off_spec = {int(item["ID"]) for item in candidates
                            if off_spec_families(stat_map(item), spell_rows[int(item["ID"])], family)}
                restricted_by_spec[spec]["off_spec_primary_stat"] = len(off_spec)
                archetype = role_archetype(bot, manifest)
                preferred = frozenset(effect_policy["tank_trinket_preferred_stats"]) if archetype == "tank" else frozenset()
                request = SpecRequest(bot=bot, weights=weights, archetype=archetype, tier_set_ids=set_ids,
                                      donor_equipment=donor, profession_setup=bot.get("profession_setup"),
                                      rating_caps=dict((config["reforge_policy"].get("rating_caps_by_spec") or {}).get(spec, {})),
                                      cap_contributors=dict((config["reforge_policy"].get("cap_contributors_by_spec") or {}).get(spec, {})),
                                      excluded_item_ids=frozenset(excluded_items), excluded_limit_categories=frozenset(excluded_categories),
                                      required_spells=required, restricted_item_ids=frozenset(set(restricted) | off_spec),
                                      preferred_trinket_stats=preferred)
                equipment = build_spec_loadout(request, candidates, gems, oracle, config, item_sets, limits, gem_colors, socket_bonus,
                                               equip_limits)
                rows = [profile_row(row, gem_mapping, oracle, dbc_dir, weights) for row in equipment]
                built_items[spec] = {int(row["item_id"]) for row in rows}
                setup = resolve_profession_setup(rows)
                tier_rows = [row for row in rows if row["tier_piece"]]
                profiles[profile_id] = {
                    "phase_id": phase_id, "class_spec": spec, "class_id": int(bot["class"]), "role": bot["role"],
                    "archetype": request.archetype, "stat_weights": weights, "catalog_gear_profile_id": str(target["gear_profile_id"]),
                    "equipment": rows, "profession_setup": setup,
                    "source": {"phase_id": phase_id, "config": relative(config_path), "config_sha256": sha256_file(config_path)},
                    "tier_set": {"name": set_name, "item_set_ids": set_ids, "pieces": len(tier_rows),
                                 "slots": [row["slot"] for row in tier_rows]},
                    "meta_gem": next((row["meta_gem"] for row in rows if row.get("meta_gem")), None),
                    "average_item_level": round(sum(row["item_level"] for row in rows) / len(rows), 2),
                    "max_item_level": max(row["item_level"] for row in rows),
                    "complete_equipment_slots": True, "all_selected_items_player_accessible": True,
                    "enchant_authorities": dict(sorted(Counter(row["enchant_authority"] or "none" for row in rows).items())),
                    "reforged_items": sum(1 for row in rows if row["reforge"]),
                    "required_combat_spells": [{"spell_id": requirement.spell_id, "name": requirement.name}
                                               for requirement in required],
                    "exempt_combat_spells": list(exempted),
                    "primary_stat": family,
                    "equip_restriction_characters": [character_row(view) for view in characters_by_spec[spec]],
                }
    catalog_setups = {}
    for entry in compositions:
        catalog_path = REPO_ROOT / str(entry["composition"]["spec_source"])
        for row in json.loads(catalog_path.read_text(encoding="utf-8"))["targets"]:
            catalog_setups[row["spec_target_id"]] = row["provisioning_bot"].get("profession_setup")
    validation = validate_phase_profiles(profiles, config, gems, oracle, facts, catalog_setups, pairings, dbc_dir,
                                         requirements_by_spec, limits, characters_by_spec, families_by_spec, effects)
    return {
        "phase_id": phase_id, "config": relative(config_path), "config_sha256": sha256_file(config_path),
        "compositions": [{"path": relative(entry["path"]), "composition_id": entry["composition"]["composition_id"],
                          "sha256": sha256_file(entry["path"])} for entry in compositions],
        "profiles": profiles, "gems": gems, "validation": validation,
        "sources_summary": {"admitted_gear_items": len(candidates), "rejected": rejected, "gem_count": len(gems),
                            "loot_item_count": len(world["loot"]), "row_digests": extract["row_digests"],
                            "db_extract": {"path": relative(extract["path"]), "sha256": extract["sha256"]},
                            "admitted_item_ids": sorted(int(item["ID"]) for item in candidates),
                            "equip_restricted_by_spec": dict(sorted(restricted_by_spec.items()))},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build content-phase gear profiles for raid compositions.")
    parser.add_argument("--phase-config", type=Path, action="append",
                        help="Phase config JSON; defaults to every file in experiments/configs/raid_gear_phases.")
    parser.add_argument("--compositions-dir", type=Path, default=COMPOSITION_DIR)
    parser.add_argument("--db-extract-dir", type=Path, default=DEFAULT_EXTRACT_DIR,
                        help="Pinned world/hotfix rows (extract_phase_gear_db); the builder never reads the database.")
    parser.add_argument("--dbc-dir", type=Path, default=Path("data/dbc/enUS"))
    parser.add_argument("--shared-gear-profiles", type=Path, default=SHARED_GEAR_PROFILES)
    parser.add_argument("--profile-manifest", type=Path, default=DEFAULT_COMBAT_LOOT_PROFILE_MANIFEST)
    parser.add_argument("--recipe-index", type=Path, default=DEFAULT_RECIPE_SOURCE_INDEX)
    parser.add_argument("--item-source-index", type=Path, default=DEFAULT_ITEM_SOURCE_INDEX)
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/raid_phase_gear_profiles"))
    args = parser.parse_args()
    phases = [build_phase(path, args) for path in (args.phase_config or sorted(PHASE_CONFIG_DIR.glob("*.json")))]
    profiles = {key: value for phase in phases for key, value in phase["profiles"].items()}
    if not profiles:
        raise PhaseBuildError("no_phase_profiles_built")
    phase_rows = {phase["phase_id"]: {key: phase[key] for key in ("config", "config_sha256", "compositions", "validation")}
                  for phase in phases if phase["profiles"]}
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "profiles.json", {"schema": PHASE_PROFILES_SCHEMA, "phases": phase_rows, "profiles": profiles})
    write_json(args.output_dir / "sources.json", {"schema": "raid_phase_gear_sources_v1",
                                                   "phases": {phase["phase_id"]: {"gems": phase["gems"], **phase["sources_summary"]}
                                                              for phase in phases if phase["profiles"]}})
    report = {"schema": "raid_phase_gear_report_v1", "phases": {}}
    for phase in phases:
        if not phase["profiles"]:
            continue
        report["phases"][phase["phase_id"]] = {
            "validation": phase["validation"],
            "average_item_level_by_spec": {key: profile["average_item_level"] for key, profile in phase["profiles"].items()},
            "max_item_level_by_spec": {key: profile["max_item_level"] for key, profile in phase["profiles"].items()},
            "tier_set_by_spec": {key: profile["tier_set"] for key, profile in phase["profiles"].items()},
            "meta_gem_by_spec": {key: profile["meta_gem"] for key, profile in phase["profiles"].items()},
            "rejected": phase["sources_summary"]["rejected"],
            "equip_restricted_by_spec": phase["sources_summary"]["equip_restricted_by_spec"],
        }
    write_json(args.output_dir / "report.json", report)
    write_json(args.output_dir / "manifest.json", {
        "schema": "raid_phase_gear_manifest_v1", "profile_count": len(profiles), "profile_hash": stable_hash(profiles),
        "phases": sorted(phase_rows), "outputs": {"profiles": "profiles.json", "report": "report.json", "sources": "sources.json"},
        "runtime_ml_control": "disabled_teacher_policy_validation_only"})
    print(json.dumps({"profiles": len(profiles), "average_item_level_by_spec": {
        key: profile["average_item_level"] for key, profile in profiles.items()}}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
