"""Choose one spec's content-phase loadout from phase-admitted items.

Selection per spec: stat-weighted items per slot (armor class, weapon slot and
dual-wield/Titan's Grip rules of build_validation_gear_profiles) under the
native uniqueness rules (unique-equipped flag, MaxCount, item limit category),
weapons that let the spec cast its required combat spells
(phase_gear_spell_requirements), the phase's tier set in the four cheapest
tier slots, permanent enchants in policy order, gems with socket bonus and meta
activation, extra sockets the character's professions add, and one cap-aware
reforge per item that counts the activated socket bonuses.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Mapping

from tools.bot_ml.build_validation_gear_profiles import (
    INVENTORY_TO_EQUIPMENT_SLOTS,
    TITANS_GRIP_CLASS_SPECS,
    armor_allowed,
    class_allowed,
    stat_map,
    weapon_slot_allowed,
)
from tools.bot_ml.build_validation_provisioning import REQUIRED_EQUIPMENT_SLOTS, required_equipment_slots_for
from tools.bot_ml.phase_gear_oracles import GEM_COLOR_META, RESILIENCE_STAT, EnchantOracle, gem_color_counts, socket_bonus_active
from tools.bot_ml.phase_gear_spell_requirements import (
    ITEM_CLASS_WEAPON,
    MAIN_HAND,
    OFF_HAND,
    SpellRequirement,
    item_fits,
    route_slots,
    unmet_requirements,
)

BLACKSMITH_SOCKET_ENCHANTS = {8: 3717, 9: 3723}
BELT_SLOT, BELT_BUCKLE_ENCHANT = 5, 3729
WEAPON_SLOTS = (15, 16, 17)
TRINKET_SLOTS = (12, 13)
MAX_META_SWAPS = 8
ITEM_FLAG_UNIQUE_EQUIPPABLE = 0x00080000
INVTYPE_2HWEAPON = 17


class PhaseSelectionError(ValueError):
    pass


@dataclass
class SpecRequest:
    bot: dict[str, Any]
    weights: dict[str, float]
    archetype: str
    tier_set_ids: list[int]
    donor_equipment: dict[int, dict[str, Any]]
    profession_setup: dict[str, Any] | None
    rating_caps: dict[str, int]
    cap_contributors: dict[str, list[str]] = None  # capped stat -> stats counting toward it (spirit -> spell hit)
    excluded_item_ids: frozenset[int] = frozenset()
    excluded_limit_categories: frozenset[int] = frozenset()
    required_spells: tuple[SpellRequirement, ...] = ()  # combat spells whose equipped-item requirement the loadout must meet
    restricted_item_ids: frozenset[int] = frozenset()  # items Player::CanUseItem refuses the spec's characters
    preferred_trinket_stats: frozenset[str] = frozenset()  # a tank's trinkets: prefer one granting any of these


def weighted(stats: Mapping[str, Any], weights: Mapping[str, float]) -> float:
    return sum(float(value) * float(weights.get(name, 0.0)) for name, value in stats.items())


def item_value(item: Mapping[str, Any], weights: Mapping[str, float]) -> float:
    """Item level x 10 + weighted static stats + weighted modelled item-spell stats (``effect_stats``, phase_gear_item_effects)."""
    return round(int(item.get("ItemLevel") or 0) * 10.0 + weighted(stat_map(item), weights)
                 + weighted(item.get("effect_stats") or {}, weights), 3)


def grants_preferred(item: Mapping[str, Any], preferred: frozenset[str]) -> bool:
    return bool(preferred & ({name for name, value in stat_map(item).items() if value}
                             | {name for name, value in (item.get("effect_stats") or {}).items() if value}))


def native_sockets(item: Mapping[str, Any]) -> list[int]:
    colors = [int(item.get(f"SocketColor{index}") or 0) for index in range(1, 4)]
    return colors[:next((index for index, color in enumerate(colors) if not color), 3)]


def required_socket_slots(request: SpecRequest) -> set[int]:
    creators = {int(row["creator_enchant_id"]) for requirement in (request.profession_setup or {}).get("requirements", [])
                for row in requirement.get("socket_creators") or []}
    return {slot for slot, enchant in BLACKSMITH_SOCKET_ENCHANTS.items() if enchant in creators}


def candidates_by_slot(request: SpecRequest, items: list[dict[str, Any]]) -> tuple[dict[int, list[dict[str, Any]]], set[int]]:
    """(ranked candidates per slot, the Blacksmith socket slots kept).

    A catalog Blacksmith socket (bracers 3717, gloves 3723) needs an item with
    one or two native sockets (resolve_prismatic_socket). It is kept only when
    such an item exists at the slot's best item level; otherwise the phase
    loadout drops that socket rather than wear an out-of-phase item for it.
    """
    bot, class_id = request.bot, int(request.bot["class"])
    by_slot: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        if int(item["ID"]) in request.excluded_item_ids or int(item["ID"]) in request.restricted_item_ids \
                or int(item.get("ItemLimitCategory") or 0) in request.excluded_limit_categories:
            continue
        if not class_allowed(item, class_id) or not armor_allowed(item, class_id):
            continue
        for slot in INVENTORY_TO_EQUIPMENT_SLOTS.get(int(item.get("InventoryType") or 0), []):
            if slot in REQUIRED_EQUIPMENT_SLOTS and weapon_slot_allowed(bot, item, slot):
                by_slot[slot].append(item)
    for slot, rows in by_slot.items():
        preferred = request.preferred_trinket_stats if slot in TRINKET_SLOTS else frozenset()
        rows.sort(key=lambda row: (grants_preferred(row, preferred), item_value(row, request.weights), int(row["ItemLevel"]),
                                   int(row["ID"])), reverse=True)
    kept: set[int] = set()
    for slot in sorted(required_socket_slots(request)):
        rows = by_slot.get(slot) or []
        top_level = max((int(row["ItemLevel"]) for row in rows), default=0)
        socketable = [row for row in rows if len(native_sockets(row)) in (1, 2) and int(row["ItemLevel"]) >= top_level]
        if socketable:
            by_slot[slot] = socketable
            kept.add(slot)
    return by_slot, kept


def tier_slot_plan(request: SpecRequest, by_slot: Mapping[int, list[dict[str, Any]]], tier_slots: list[int],
                   pieces: int, item_sets: Mapping[int, int]) -> dict[int, str]:
    """{slot: 'set'} for the ``pieces`` tier slots where the set piece costs least."""
    if not request.tier_set_ids:
        return {}
    losses = []
    for slot in tier_slots:
        rows = by_slot.get(slot) or []
        best = rows[0] if rows else None
        set_rows = [row for row in rows if item_sets.get(int(row["ID"])) in request.tier_set_ids]
        if best is not None and set_rows:
            losses.append((item_value(best, request.weights) - item_value(set_rows[0], request.weights), slot))
    if len(losses) < pieces:
        raise PhaseSelectionError(f"tier_set_pieces_unavailable:{request.bot['class_spec']}:{len(losses)}<{pieces}")
    return {slot: "set" for _loss, slot in sorted(losses)[:pieces]}


def item_equip_limit(fact: Mapping[str, Any] | None) -> int | None:
    """Most copies of one item a character can wear, or None when unlimited.

    ITEM_FLAG_UNIQUE_EQUIPPABLE allows one equipped copy (Player::CanEquipUniqueItem);
    a positive MaxCount caps the copies a character can hold (CanTakeMoreSimilarItems).
    """
    fact = fact or {}
    limits = [1] if int(fact.get("flags") or 0) & ITEM_FLAG_UNIQUE_EQUIPPABLE else []
    if int(fact.get("max_count") or 0) > 0:
        limits.append(int(fact["max_count"]))
    return min(limits) if limits else None


def slot_order(offhand_first: bool) -> list[int]:
    """REQUIRED_EQUIPMENT_SLOTS, with the off hand filled before the main hand when ``offhand_first``."""
    order = list(REQUIRED_EQUIPMENT_SLOTS)
    if offhand_first and MAIN_HAND in order and OFF_HAND in order:
        order.remove(OFF_HAND)
        order.insert(order.index(MAIN_HAND), OFF_HAND)
    return order


def select_items(request: SpecRequest, by_slot: Mapping[int, list[dict[str, Any]]], plan: Mapping[int, str],
                 item_sets: Mapping[int, int], limit_quantities: Mapping[int, int],
                 equip_limits: Mapping[int, int], offhand_first: bool = False) -> dict[int, dict[str, Any]]:
    """The best item per slot in slot order under the native uniqueness rules (two copies of an unrestricted item are lawful).

    With ``offhand_first`` the off hand picks before the main hand, and a main
    hand beside a filled off hand is one-handed (unless Titan's Grip).
    """
    chosen: dict[int, dict[str, Any]] = {}
    copies: dict[int, int] = defaultdict(int)
    categories: dict[int, int] = defaultdict(int)
    titan_grip = str(request.bot.get("class_spec") or "") in TITANS_GRIP_CLASS_SPECS
    for slot in slot_order(offhand_first):
        if slot == OFF_HAND and not titan_grip and int((chosen.get(MAIN_HAND) or {}).get("InventoryType") or 0) == INVTYPE_2HWEAPON:
            continue
        for item in by_slot.get(slot) or []:
            item_id = int(item["ID"])
            if slot == MAIN_HAND and OFF_HAND in chosen and not titan_grip and int(item.get("InventoryType") or 0) == INVTYPE_2HWEAPON:
                continue
            limit = equip_limits.get(item_id)
            category = int(item.get("ItemLimitCategory") or 0)
            if (limit is not None and copies[item_id] >= limit) \
                    or (category and categories[category] >= int(limit_quantities.get(category) or 0)):
                continue
            if plan.get(slot) == "set" and item_sets.get(item_id) not in request.tier_set_ids:
                continue
            chosen[slot] = item
            copies[item_id] += 1
            if category:
                categories[category] += 1
            break
    return chosen


def _restrict(by_slot: Mapping[int, list[dict[str, Any]]], slot: int, keep) -> dict[int, list[dict[str, Any]]]:
    restricted = dict(by_slot)
    restricted[slot] = [row for row in by_slot.get(slot) or [] if keep(row)]
    return restricted


def _hand_restricted(by_slot: Mapping[int, list[dict[str, Any]]], slot: int, requirement: SpellRequirement,
                     titan_grip: bool, weapon_only: bool) -> dict[int, list[dict[str, Any]]]:
    """Only items fitting the requirement in ``slot``; an off-hand requirement also needs a one-handed main hand."""
    restricted = _restrict(by_slot, slot, lambda row: item_fits(requirement, row)
                           and (not weapon_only or int(row["ClassID"]) == ITEM_CLASS_WEAPON))
    if slot == OFF_HAND and not titan_grip:
        restricted = _restrict(restricted, MAIN_HAND, lambda row: int(row.get("InventoryType") or 0) != INVTYPE_2HWEAPON)
    return restricted


def select_loadout(request: SpecRequest, by_slot: Mapping[int, list[dict[str, Any]]], plan: Mapping[int, str],
                   item_sets: Mapping[int, int], limit_quantities: Mapping[int, int],
                   equip_limits: Mapping[int, int]) -> dict[int, dict[str, Any]]:
    """The best-scoring complete loadout that meets every required combat spell; fails closed when none does.

    SPELL_ATTR3 main/off-hand requirements restrict their hand outright (Mutilate:
    daggers in both hands). A requirement any of several slots can meet (Fan of
    Knives' thrown weapon, a hunter's ranged weapon, Nerves of Cold Steel's
    one-hander) is tried in each such slot when the greedy fill misses it.

    The hands are filled main hand first; when that misses a slot or a
    requirement, the off-hand-first assignment is searched as well, so a unique
    either-hand item the main hand took cannot leave a feasible pair unfound
    (a main-hand-only item then takes the main hand).
    """
    titan_grip = str(request.bot.get("class_spec") or "") in TITANS_GRIP_CLASS_SPECS
    spec = request.bot["class_spec"]
    for requirement in request.required_spells:
        for slot, needed in ((MAIN_HAND, requirement.main_hand), (OFF_HAND, requirement.off_hand)):
            if needed:
                by_slot = _hand_restricted(by_slot, slot, requirement, titan_grip, weapon_only=True)
                if not by_slot[slot]:
                    raise PhaseSelectionError(f"combat_spell_requirement_unmeetable:{spec}:{requirement.spell_id}:slot{slot}")
    found: list[tuple[float, bool, int, dict[int, dict[str, Any]]]] = []
    failures: list[str] = []

    def attempt(slots: Mapping[int, list[dict[str, Any]]], offhand_first: bool) -> list[SpellRequirement] | None:
        """None when the assignment is a complete loadout meeting every requirement (recorded), else what it misses."""
        chosen = select_items(request, slots, plan, item_sets, limit_quantities, equip_limits, offhand_first)
        missing = sorted(set(required_equipment_slots_for([{"slot": slot, "inventory_type": int(item["InventoryType"])}
                                                           for slot, item in chosen.items()])) - set(chosen))
        if missing:
            failures.append(f"phase_slots_unfilled:{spec}:{missing}")
            return []
        unmet = unmet_requirements(request.required_spells, chosen)
        if not unmet:
            score = round(sum(item_value(item, request.weights) for item in chosen.values()), 3)
            found.append((score, not offhand_first, -len(found), chosen))  # ties keep the main-hand-first fill
            return None
        failures.append(f"combat_spell_requirements_unmet:{spec}:{[requirement.spell_id for requirement in unmet]}")
        return unmet

    def search(slots: Mapping[int, list[dict[str, Any]]], depth: int) -> None:
        unmet = attempt(slots, offhand_first=False)
        if unmet is None:
            return
        attempt(slots, offhand_first=True)
        if not unmet or depth >= len(request.required_spells):
            return
        for slot in route_slots(unmet[0]):
            restricted = _hand_restricted(slots, slot, unmet[0], titan_grip, weapon_only=False)
            if restricted[slot]:
                search(restricted, depth + 1)

    search(by_slot, 0)
    if not found:
        raise PhaseSelectionError("; ".join(dict.fromkeys(failures)) or f"phase_loadout_unavailable:{spec}")
    return max(found, key=lambda row: row[:3])[3]


def enchant_allowed(enchant: Mapping[str, Any] | None, policy: Mapping[str, Any]) -> bool:
    if not enchant:
        return False
    extra = {int(value) for value in policy.get("extra_allowed_enchant_ids") or []}
    in_range = int(policy["enchant_id_min"]) <= int(enchant["id"]) <= int(policy["enchant_id_max"])
    return (in_range or int(enchant["id"]) in extra) and RESILIENCE_STAT not in enchant.get("stat_types", []) \
        and int(enchant.get("min_level") or 0) <= 85


def choose_enchants(request: SpecRequest, chosen: Mapping[int, dict[str, Any]], oracle: EnchantOracle,
                    policy: Mapping[str, Any]) -> dict[int, tuple[int, str]]:
    """{slot: (enchant_id, authority)} in the phase policy order."""
    result: dict[int, tuple[int, str]] = {}
    declared_skills = {int(row["native_skill_id"]) for row in (request.profession_setup or {}).get("requirements", [])}
    for requirement in (request.profession_setup or {}).get("requirements", []):
        for enchant_id in requirement.get("source_enchant_ids") or []:
            if int(enchant_id) in BLACKSMITH_SOCKET_ENCHANTS.values():
                continue
            donor_slot = next((slot for slot, row in request.donor_equipment.items() if int(row.get("enchant_id") or 0) == int(enchant_id)), None)
            slots = sorted(chosen, key=lambda slot: (slot != donor_slot, slot))
            slot = next((slot for slot in slots if slot not in result and oracle.applicable(int(enchant_id), chosen[slot])), None)
            if slot is None:
                raise PhaseSelectionError(f"profession_enchant_unplaceable:{request.bot['class_spec']}:{enchant_id}")
            result[slot] = (int(enchant_id), "catalog_profession")
    preferences = [int(value) for value in (policy.get("proc_enchant_preferences_by_archetype") or {}).get(request.archetype, [])]
    pool = [enchant for enchant in oracle.enchants.values() if enchant_allowed(enchant, policy)
            and not int(enchant.get("required_skill_id") or 0) and enchant.get("stats")]
    for slot, item in sorted(chosen.items()):
        if slot in result:
            continue
        donor = request.donor_equipment.get(slot) or {}
        donor_enchant = int(donor.get("enchant_id") or 0)
        enchant = oracle.enchants.get(donor_enchant)
        skill = int((enchant or {}).get("required_skill_id") or 0)
        if (donor_enchant and int(donor.get("inventory_type") or 0) == int(item["InventoryType"])
                and enchant_allowed(enchant, policy) and (not skill or skill == 776 or skill in declared_skills
                                                          or request.profession_setup is None)
                and oracle.applicable(donor_enchant, item)):
            result[slot] = (donor_enchant, "canonical_profile_same_inventory_type")
            continue
        if slot in WEAPON_SLOTS:
            preferred = next((value for value in preferences if enchant_allowed(oracle.enchants.get(value), policy)
                              and oracle.applicable(value, item)), None)
            if preferred:
                result[slot] = (preferred, "archetype_proc_preference")
                continue
        ranked = sorted(((weighted(row["stats"], request.weights), int(row["id"])) for row in pool
                         if oracle.applicable(int(row["id"]), item)), reverse=True)
        if ranked and ranked[0][0] > 0:
            result[slot] = (ranked[0][1], "phase_pool_stat_weight")
    return result


def best_gem(gems: list[dict[str, Any]], weights: Mapping[str, float], socket_color: int | None) -> dict[str, Any] | None:
    fitting = [gem for gem in gems if (socket_color is None and int(gem["color"]) != GEM_COLOR_META)
               or (socket_color is not None and int(gem["color"]) & socket_color)]
    ranked = sorted(fitting, key=lambda gem: (weighted(gem["stats"], weights), int(gem["item_level"]), int(gem["item_id"])), reverse=True)
    return ranked[0] if ranked and weighted(ranked[0]["stats"], weights) > 0 else None


def gem_item(item: Mapping[str, Any], extra_socket: bool, gems: list[dict[str, Any]], weights: Mapping[str, float],
             bonus_stats: Mapping[str, int]) -> list[dict[str, Any]]:
    """Gems of one item: all native sockets colour-matched with the bonus, or best-in-slot without it."""
    colors = native_sockets(item)
    non_meta = [color for color in colors if color != GEM_COLOR_META]
    matched = [best_gem(gems, weights, color) for color in colors]
    free = [best_gem(gems, weights, color if color == GEM_COLOR_META else None) for color in colors]
    if any(gem is None for gem in matched) or any(gem is None for gem in free):
        raise PhaseSelectionError(f"socket_without_phase_gem:{item['ID']}")
    bonus = weighted(bonus_stats, weights)
    matched_score = sum(weighted(gem["stats"], weights) for gem in matched) + bonus
    free_bonus = all(int(gem["color"]) & color for gem, color in zip(free, colors))
    free_score = sum(weighted(gem["stats"], weights) for gem in free) + (bonus if free_bonus else 0.0)
    chosen = matched if non_meta and matched_score >= free_score else free
    if extra_socket:
        chosen = chosen + [best_gem(gems, weights, None)]
    return list(chosen)


def fix_meta(equipment: list[dict[str, Any]], gems: list[dict[str, Any]], weights: Mapping[str, float],
             oracle: EnchantOracle, gem_colors: Mapping[int, int], bonus_by_item: Mapping[int, Mapping[str, int]]) -> dict[str, Any] | None:
    """Swap the cheapest gems until the meta gem's native condition holds; None without a meta socket."""
    head = next((item for item in equipment if GEM_COLOR_META in item["native_socket_colors"]), None)
    if head is None:
        return None
    meta_index = head["native_socket_colors"].index(GEM_COLOR_META)
    metas = sorted((gem for gem in gems if int(gem["color"]) == GEM_COLOR_META),
                   key=lambda gem: (weighted(gem["stats"], weights), int(gem["item_id"])), reverse=True)
    for meta in metas:
        head["gems"][meta_index] = meta
        condition = int(meta.get("condition_id") or 0)
        for _ in range(MAX_META_SWAPS + 1):
            counts = gem_color_counts(_gem_view(equipment), gem_colors)
            deficit = oracle.meta_deficit(condition, counts)
            if not deficit and oracle.meta_active(condition, counts):
                return {"item_id": int(meta["item_id"]), "condition_id": condition, "active": True, "color_counts": counts}
            best = None
            for item in equipment:
                for index, current in enumerate(item["gems"]):
                    if int(current["color"]) == GEM_COLOR_META:
                        continue
                    for candidate in gems:
                        if int(candidate["color"]) == GEM_COLOR_META or candidate is current:
                            continue
                        trial = list(item["gems"])
                        trial[index] = candidate
                        saved, item["gems"] = item["gems"], trial
                        new_deficit = oracle.meta_deficit(condition, gem_color_counts(_gem_view(equipment), gem_colors))
                        item["gems"] = saved
                        if new_deficit >= deficit:
                            continue
                        loss = _gem_score(item, current, candidate, index, weights, bonus_by_item)
                        key = (deficit - new_deficit, -loss, -int(candidate["item_id"]))
                        if best is None or key > best[0]:
                            best = (key, item, index, candidate)
            if best is None:
                break
            _key, item, index, candidate = best
            item["gems"][index] = candidate
    raise PhaseSelectionError("meta_gem_condition_unsatisfiable")


def _gem_view(equipment: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"native_socket_colors": item["native_socket_colors"], "gem_item_ids": [int(gem["item_id"]) for gem in item["gems"]]}
            for item in equipment]


def _gem_score(item: Mapping[str, Any], current: Mapping[str, Any], candidate: Mapping[str, Any], index: int,
               weights: Mapping[str, float], bonus_by_item: Mapping[int, Mapping[str, int]]) -> float:
    def total(gems):
        colors = item["native_socket_colors"]
        bonus = all(int(gem["color"]) & color for gem, color in zip(gems, colors)) and colors
        return sum(weighted(gem["stats"], weights) for gem in gems) + (weighted(bonus_by_item.get(int(item["item_id"]), {}), weights) if bonus else 0)
    trial = list(item["gems"])
    trial[index] = candidate
    return total(item["gems"]) - total(trial)


def loadout_stat_totals(equipment: list[dict[str, Any]], oracle: EnchantOracle,
                        bonus_by_item: Mapping[int, Mapping[str, int]]) -> dict[str, float]:
    """Item, gem, enchant and activated socket-bonus stats of the loadout (reforges excluded)."""
    totals: dict[str, float] = defaultdict(float)
    for item in equipment:
        for name, value in item["stats"].items():
            totals[name] += value
        for gem in item["gems"]:
            for name, value in gem["stats"].items():
                totals[name] += value
        for name, value in oracle.stats(item["enchant_id"]).items():
            totals[name] += value
        if socket_bonus_active(item["native_socket_colors"], [int(gem["color"]) for gem in item["gems"]]):
            for name, value in (bonus_by_item.get(int(item["item_id"])) or {}).items():
                totals[name] += value
    return totals


def reforge(equipment: list[dict[str, Any]], request: SpecRequest, oracle: EnchantOracle, reforgeable: list[str],
            bonus_by_item: Mapping[int, Mapping[str, int]]) -> None:
    """At most one reforge per item, cap-aware (socket bonuses included, after the meta-gem swaps), in slot order."""
    totals = loadout_stat_totals(equipment, oracle, bonus_by_item)

    contributors = {cap: list((request.cap_contributors or {}).get(cap) or [cap]) for cap in request.rating_caps}

    def over_cap(name: str, extra: float = 0.0) -> bool:
        return any(name in stats and sum(totals[stat] for stat in stats) + extra > request.rating_caps[cap]
                   for cap, stats in contributors.items())

    def weight(name: str) -> float:
        return 0.0 if over_cap(name) else float(request.weights.get(name, 0.0))

    for item in sorted(equipment, key=lambda row: row["slot"]):
        present = {name: value for name, value in item["stats"].items() if name in reforgeable and value > 0}
        if not present:
            continue
        source = min(present, key=lambda name: (weight(name), name))
        amount = math.floor(present[source] * 0.4)
        targets = sorted((name for name in reforgeable if name not in present and weight(name) > weight(source)),
                         key=lambda name: (-weight(name), name))
        for target in targets:
            if over_cap(target, amount):
                continue
            reforge_id = oracle.reforges.get((source, target))
            if reforge_id is None:
                raise PhaseSelectionError(f"reforge_missing:{source}:{target}")
            item["reforge"] = {"reforge_id": reforge_id, "from": source, "to": target, "amount": amount}
            totals[source] -= amount
            totals[target] += amount
            break


def build_spec_loadout(request: SpecRequest, items: list[dict[str, Any]], gems: list[dict[str, Any]], oracle: EnchantOracle,
                       config: Mapping[str, Any], item_sets: Mapping[int, int], limit_quantities: Mapping[int, int],
                       gem_colors: Mapping[int, int], socket_bonus: Mapping[int, int],
                       equip_limits: Mapping[int, int]) -> list[dict[str, Any]]:
    by_slot, socket_slots = candidates_by_slot(request, items)
    plan = tier_slot_plan(request, by_slot, [int(slot) for slot in config["tier_set_slots"]], int(config["tier_set_pieces"]), item_sets)
    chosen = select_loadout(request, by_slot, plan, item_sets, limit_quantities, equip_limits)
    enchants = choose_enchants(request, chosen, oracle, config["enchant_policy"])
    bonus_by_item = {int(item["ID"]): oracle.stats(int(socket_bonus.get(int(item["ID"])) or 0)) for item in chosen.values()}
    equipment = []
    for slot, item in sorted(chosen.items()):
        natives = native_sockets(item)
        extra = slot in socket_slots or (slot == BELT_SLOT and config["extra_sockets"].get("belt_buckle") and len(natives) in (1, 2))
        enchant_id, authority = enchants.get(slot, (0, ""))
        equipment.append({"slot": slot, "item": item, "item_id": int(item["ID"]), "native_socket_colors": natives,
                          "extra_socket": bool(extra), "gems": gem_item(item, bool(extra), gems, request.weights, bonus_by_item[int(item["ID"])]),
                          "stats": stat_map(item), "enchant_id": enchant_id, "enchant_authority": authority,
                          "tier_piece": item_sets.get(int(item["ID"])) in request.tier_set_ids})
    meta = fix_meta(equipment, gems, request.weights, oracle, gem_colors, bonus_by_item)
    reforge(equipment, request, oracle, list(config["reforge_policy"]["reforgeable_stats"]), bonus_by_item)
    for row in equipment:
        row["meta_gem"] = meta if meta and GEM_COLOR_META in row["native_socket_colors"] else None
    missing = sorted(set(required_equipment_slots_for([{"slot": row["slot"], "inventory_type": int(row["item"]["InventoryType"])}
                                                       for row in equipment])) - {row["slot"] for row in equipment})
    if missing:
        raise PhaseSelectionError(f"phase_slots_unfilled:{request.bot['class_spec']}:{missing}")
    return equipment
