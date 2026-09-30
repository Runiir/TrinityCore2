"""Validate built content-phase profiles before anything is written (fail closed).

Independent re-checks of the finished output, not of the selection steps:
item level cap and quality, class/armor/weapon-slot legality, complete slots,
the spec's required combat spells castable with the worn weapons (native
equipped-item requirements), native uniqueness (unique-equipped, MaxCount,
item limit categories, gems included), every socket filled with a phase gem
of a fitting colour, an active meta gem, native enchant applicability, reforge
legality, no reforge into a capped rating the loadout exceeds (activated socket
bonuses counted), the tier-set piece count, phase acquisition sources, the
catalog's declared professions, unique items across a character's two specs,
and the native use restrictions of every worn item against every character
wearing the profile (faction, class and race masks, skill, spell, level,
holiday and reputation: Player::CanUseItem, phase_gear_equip_restrictions),
with the skills the profile's own profession setup provisions.
"""

from __future__ import annotations

import math
from collections import Counter, defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Mapping

from tools.bot_ml.build_validation_gear_profiles import (
    INVENTORY_TO_EQUIPMENT_SLOTS,
    armor_allowed,
    class_allowed,
    weapon_slot_allowed,
)
from tools.bot_ml.build_validation_provisioning import gem_item_enchant_map, required_equipment_slots_for
from tools.bot_ml.phase_gear_equip_restrictions import CharacterView, item_use_failures, profession_skills
from tools.bot_ml.phase_gear_item_effects import item_spell_stats, off_spec_families
from tools.bot_ml.phase_gear_oracles import GEM_COLOR_META, RESILIENCE_STAT, EnchantOracle, gem_color_counts, socket_bonus_active
from tools.bot_ml.phase_gear_selection import enchant_allowed, item_equip_limit
from tools.bot_ml.phase_gear_spell_requirements import SpellRequirement, unmet_requirements

EXTRA_SOCKET_SLOTS = {5, 8, 9}


class PhaseValidationError(ValueError):
    pass


def _item_view(row: Mapping[str, Any]) -> dict[str, Any]:
    return {"ClassID": int(row["item_class"]), "SubclassID": int(row["subclass"]), "InventoryType": int(row["inventory_type"]),
            "AllowableClass": int(row.get("allowable_class", -1))}


def uniqueness_failures(key: str, rows: list[Mapping[str, Any]], facts: Mapping[int, Mapping[str, int]],
                        limit_quantities: Mapping[int, int]) -> list[str]:
    """Player::CanEquipUniqueItem over the worn items and, separately, the socketed gems
    (WorldSession::HandleSocketOpcode: a gem's unique-equipped flag and limit category; MaxCount is possession only)."""
    failures: list[str] = []
    for kind, ids in (("item", [int(row["item_id"]) for row in rows]),
                      ("gem", [int(gem) for row in rows for gem in row.get("gem_item_ids") or []])):
        for item_id, count in sorted(Counter(ids).items()):
            fact = facts.get(item_id) or {}
            limit = item_equip_limit(fact if kind == "item" else {"flags": fact.get("flags")})
            if limit is not None and count > limit:
                failures.append(f"{key}:{kind}_unique_equipped_exceeded:{item_id}:{count}>{limit}")
        categories = Counter(int((facts.get(item_id) or {}).get("limit_category") or 0) for item_id in ids)
        for category, count in sorted(categories.items()):
            if category and count > int(limit_quantities.get(category) or 0):
                failures.append(f"{key}:{kind}_limit_category_exceeded:{category}:{count}")
    return failures


def rating_totals(rows: Iterable[Mapping[str, Any]], gems: Mapping[int, Mapping[str, Any]], oracle: EnchantOracle,
                  facts: Mapping[int, Mapping[str, int]]) -> tuple[dict[str, float], set[str]]:
    """(the worn loadout's stat totals, the stats reforged into): items after their native 40% reforge, gems,
    enchants and every activated socket bonus (Item::GemsFitSockets)."""
    totals: dict[str, float] = defaultdict(float)
    reforged_into: set[str] = set()
    for row in rows:
        gem_ids = [int(gem) for gem in row.get("gem_item_ids") or []]
        stat_sources: list[Mapping[str, Any]] = [row.get("stats") or {}, oracle.stats(int(row.get("enchant_id") or 0))]
        stat_sources += [(gems.get(gem) or {}).get("stats") or {} for gem in gem_ids]
        if socket_bonus_active(row.get("native_socket_colors") or [], [int((gems.get(gem) or {}).get("color") or 0) for gem in gem_ids]):
            stat_sources.append(oracle.stats(int((facts.get(int(row["item_id"])) or {}).get("socket_bonus") or 0)))
        for stats in stat_sources:
            for name, value in stats.items():
                totals[name] += value
        reforge = row.get("reforge")
        if reforge:
            amount = math.floor(float((row.get("stats") or {}).get(reforge["from"]) or 0) * 0.4)  # native ItemReforge 40%
            totals[reforge["from"]] -= amount
            totals[reforge["to"]] += amount
            reforged_into.add(str(reforge["to"]))
    return totals, reforged_into


def reforge_cap_failures(key: str, profile: Mapping[str, Any], config: Mapping[str, Any], gems: Mapping[int, Mapping[str, Any]],
                         oracle: EnchantOracle, facts: Mapping[int, Mapping[str, int]]) -> list[str]:
    """A reforge into a capped rating must leave the loadout at or below the cap (socket bonuses counted)."""
    spec = str(profile["class_spec"])
    policy = config["reforge_policy"]
    caps = (policy.get("rating_caps_by_spec") or {}).get(spec) or {}
    contributors = (policy.get("cap_contributors_by_spec") or {}).get(spec) or {}
    totals, reforged_into = rating_totals(profile.get("equipment") or [], gems, oracle, facts)
    failures = []
    for cap, limit in sorted(caps.items()):
        stats = list(contributors.get(cap) or [cap])
        total = sum(totals[name] for name in stats)
        if reforged_into & set(stats) and total > int(limit):
            failures.append(f"{key}:reforge_past_cap:{cap}:{total:g}>{limit}")
    return failures


def profile_failures(key: str, profile: Mapping[str, Any], config: Mapping[str, Any], gems: Mapping[int, Mapping[str, Any]],
                     oracle: EnchantOracle, catalog_setup: Mapping[str, Any] | None, gem_mapping: Mapping[int, int],
                     requirements: Iterable[SpellRequirement], facts: Mapping[int, Mapping[str, int]],
                     limit_quantities: Mapping[int, int], characters: Iterable[CharacterView],
                     primary_family: str | None, effects: Mapping[int, list]) -> list[str]:
    failures: list[str] = []
    if not primary_family:
        failures.append(f"{key}:primary_stat_undetermined")
    skills = profession_skills(profile.get("profession_setup"))
    wearers = [replace(character, skills=skills) for character in characters]
    if not wearers:
        failures.append(f"{key}:equip_restriction_characters_missing")
    for character in wearers:
        if character.class_id != int(profile["class_id"]):
            failures.append(f"{key}:{character.key()}:class_mismatch")
    policy = config["item_policy"]
    cap = int(policy["max_item_level"])
    bot = {"class": int(profile["class_id"]), "class_spec": str(profile["class_spec"])}
    rows = profile.get("equipment") or []
    slots = [int(row["slot"]) for row in rows]
    if len(set(slots)) != len(slots):
        failures.append(f"{key}:duplicate_slot")
    missing = sorted(set(required_equipment_slots_for(rows)) - set(slots))
    if missing:
        failures.append(f"{key}:missing_slots:{missing}")
    for row in rows:
        slot, item_id = int(row["slot"]), int(row["item_id"])
        where = f"{key}:slot{slot}:{item_id}"
        if int(row["item_level"]) > cap:
            failures.append(f"{where}:above_phase_cap:{row['item_level']}>{cap}")
        if int(row["item_level"]) < int(policy.get("min_item_level") or 0):
            failures.append(f"{where}:below_phase_floor:{row['item_level']}")
        if not int(policy["min_quality"]) <= int(row["quality"]) <= int(policy["max_quality"]):
            failures.append(f"{where}:quality")
        if "resilience" in (row.get("stats") or {}):
            failures.append(f"{where}:pvp_item")
        view = _item_view(row)
        if not class_allowed(view, bot["class"]) or not armor_allowed(view, bot["class"]) or slot not in INVENTORY_TO_EQUIPMENT_SLOTS.get(view["InventoryType"], []) \
                or not weapon_slot_allowed(bot, view, slot):
            failures.append(f"{where}:armor_or_slot_illegal")
        if primary_family:
            claimed = off_spec_families(row.get("stats") or {}, item_spell_stats(facts.get(item_id), effects), primary_family)
            if claimed:
                failures.append(f"{where}:off_spec_primary_stat:{'+'.join(sorted(claimed))}!={primary_family}")
        for character in wearers:
            for reason in item_use_failures(facts.get(item_id), character):
                failures.append(f"{where}:{character.key()}:cannot_use:{reason}")
        if not (row.get("player_acquisition") or {}).get("sources"):
            failures.append(f"{where}:no_phase_source")
        natives = [int(color) for color in row.get("native_socket_colors") or []]
        gem_ids = [int(gem) for gem in row.get("gem_item_ids") or []]
        expected = len(natives) + (1 if row.get("extra_socket") else 0)
        if len(gem_ids) != expected or any(gem not in gems for gem in gem_ids):
            failures.append(f"{where}:gems_not_phase_or_unfilled")
        for gem, color in zip(gem_ids, natives):
            gem_color = int((gems.get(gem) or {}).get("color") or 0)
            if (color == GEM_COLOR_META) != (gem_color == GEM_COLOR_META):
                failures.append(f"{where}:meta_socket_mismatch")
        if row.get("extra_socket") and (slot not in EXTRA_SOCKET_SLOTS or len(natives) not in (1, 2)
                                        or int((gems.get(gem_ids[-1]) or {}).get("color") or 0) == GEM_COLOR_META):
            failures.append(f"{where}:extra_socket_topology")
        if [int(value) for value in row.get("gem_enchant_ids") or []] != [int(gem_mapping.get(gem, -1)) for gem in gem_ids]:
            failures.append(f"{where}:gem_enchant_mapping")
        enchant_id = int(row.get("enchant_id") or 0)
        if enchant_id:
            enchant = oracle.enchants.get(enchant_id)
            if not enchant_allowed(enchant, config["enchant_policy"]) or not oracle.applicable(enchant_id, view):
                failures.append(f"{where}:enchant_not_applicable:{enchant_id}")
            if RESILIENCE_STAT in (enchant or {}).get("stat_types", []):
                failures.append(f"{where}:pvp_enchant")
        if str(row.get("enchantments") or "").split()[:1] != [str(enchant_id)]:
            failures.append(f"{where}:enchantment_field_0")
        reforge = row.get("reforge")
        if reforge:
            stats = row.get("stats") or {}
            if not stats.get(reforge["from"]) or stats.get(reforge["to"]) \
                    or oracle.reforges.get((reforge["from"], reforge["to"])) != int(row.get("reforge_id") or 0):
                failures.append(f"{where}:reforge_illegal")
        elif int(row.get("reforge_id") or 0):
            failures.append(f"{where}:reforge_unexplained")
    worn = {int(row["slot"]): row for row in rows}
    for requirement in unmet_requirements(requirements, worn):
        failures.append(f"{key}:combat_spell_requirement_unmet:{requirement.spell_id}:{requirement.name}")
    failures += uniqueness_failures(key, rows, facts, limit_quantities)
    failures += reforge_cap_failures(key, profile, config, gems, oracle, facts)
    meta_rows = [row for row in rows if GEM_COLOR_META in (row.get("native_socket_colors") or [])]
    if meta_rows:
        meta_gem = next(gem for gem, color in zip(meta_rows[0]["gem_item_ids"], meta_rows[0]["native_socket_colors"]) if color == GEM_COLOR_META)
        counts = gem_color_counts(rows, {gem: int(row["color"]) for gem, row in gems.items()})
        if not oracle.meta_active(int(gems[int(meta_gem)].get("condition_id") or 0), counts):
            failures.append(f"{key}:meta_gem_inactive")
    tier = profile.get("tier_set") or {}
    if tier.get("name"):
        pieces = sum(1 for row in rows if row.get("tier_piece"))
        if pieces < int(config["tier_set_pieces"]) or pieces != int(tier.get("pieces") or -1):
            failures.append(f"{key}:tier_set_pieces:{pieces}")
    # The phase gear may need fewer profession items than the catalog gear (no
    # socketable Tier 11 bracer), never a profession the character lacks.
    phase_skills = {int(row["native_skill_id"]) for row in (profile.get("profession_setup") or {}).get("requirements", [])}
    if catalog_setup is not None:
        catalog_skills = {int(row["native_skill_id"]) for row in catalog_setup.get("requirements", [])}
        if not phase_skills <= catalog_skills:
            failures.append(f"{key}:profession_outside_catalog:{sorted(phase_skills - catalog_skills)}")
    if len(phase_skills) > 2:
        failures.append(f"{key}:more_than_two_professions")
    return failures


def validate_phase_profiles(profiles: Mapping[str, Any], config: Mapping[str, Any], gems: list[Mapping[str, Any]],
                            oracle: EnchantOracle, facts: Mapping[int, Mapping[str, int]],
                            catalog_setups: Mapping[str, Any], pairings: Mapping[str, set[str]], dbc_dir: Path,
                            requirements_by_spec: Mapping[str, Iterable[SpellRequirement]],
                            limit_quantities: Mapping[int, int],
                            characters_by_spec: Mapping[str, Iterable[CharacterView]],
                            families_by_spec: Mapping[str, str], effects: Mapping[int, list]) -> dict[str, Any]:
    gem_rows = {int(gem["item_id"]): gem for gem in gems}
    gem_mapping = gem_item_enchant_map(Path(dbc_dir))
    failures: list[str] = []
    for key, profile in sorted(profiles.items()):
        spec = profile["class_spec"]
        if spec not in requirements_by_spec:
            failures.append(f"{key}:combat_spell_requirements_undetermined")
        failures += profile_failures(key, profile, config, gem_rows, oracle, catalog_setups.get(spec), gem_mapping,
                                     requirements_by_spec.get(spec, ()), facts, limit_quantities,
                                     characters_by_spec.get(spec, ()), families_by_spec.get(spec), effects)
    by_spec = {profile["class_spec"]: profile for profile in profiles.values()}
    for spec, partners in sorted(pairings.items()):
        for partner in sorted(partners):
            if spec < partner and spec in by_spec and partner in by_spec:
                ours = {int(row["item_id"]) for row in by_spec[spec]["equipment"]}
                theirs = {int(row["item_id"]) for row in by_spec[partner]["equipment"]}
                shared_unique = sorted(item for item in ours & theirs if (facts.get(item) or {}).get("max_count"))
                if shared_unique:
                    failures.append(f"{spec}+{partner}:unique_item_in_both_specs:{shared_unique}")
    if failures:
        raise PhaseValidationError("; ".join(failures[:40]))
    return {"all_passed": True, "profile_count": len(profiles),
            "checks": ["item_level_cap", "quality", "no_pvp", "armor_and_weapon_slot", "complete_slots",
                       "required_combat_spells_castable", "native_uniqueness", "native_use_restrictions", "primary_stat_fit", "phase_sources",
                       "sockets_filled_with_phase_gems", "meta_gem_active", "enchant_native_applicability",
                       "reforge_legality", "reforge_within_rating_caps", "tier_set_pieces", "professions_within_catalog",
                       "unique_items_across_specs"]}
