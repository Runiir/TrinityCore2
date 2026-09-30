"""Native DBC oracles a phase loadout is checked against: enchant applicability,
enchant stats, socket bonuses, gem colors, meta-gem conditions and reforges.

Applicability mirrors ``Item::IsFitToSpellRequirements`` for the enchant's own
SPELL_EFFECT_ENCHANT_ITEM spells (SpellEffect 53 -> Spell.EquippedItemsID ->
SpellEquippedItems). An enchant no restricted spell creates is never
applicable, so an unknown enchant fails closed instead of landing on any slot.
Meta-gem activation mirrors ``Player::EnchantmentFitsRequirements``.
"""

from __future__ import annotations

import struct
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from tools.bot_ml.build_validation_gear_profiles import (
    SPELL_ITEM_ENCHANTMENT_FMT,
    STAT_NAMES,
    load_wdbc,
)
from tools.bot_ml.phase_gear_sources import SPELL_EFFECT_FMT

SPELL_FMT = "niiiiiiiiiiiiiiifiiiissxxiixxifiiiiiiixiiiiiiiii"  # SpellEntryfmt
SPELL_EQUIPPED_ITEMS_ID_FIELD = 39
SPELL_EQUIPPED_ITEMS_FMT = "diii"
ITEM_REFORGE_FMT = "nifif"
SPELL_EFFECT_ENCHANT_ITEM = 53
ITEM_ENCHANTMENT_TYPE_STAT = 5
ITEM_ENCHANTMENT_TYPE_EQUIP_SPELL = 3
SPELL_EFFECT_APPLY_AURA, SPELL_AURA_MOD_STAT = 6, 29
UNIT_STAT_NAMES = ["strength", "agility", "stamina", "intellect", "spirit"]
INVTYPE_WEAPON, INVTYPE_WEAPONMAINHAND, INVTYPE_WEAPONOFFHAND = 13, 21, 22
GEM_COLOR_META, GEM_COLOR_RED, GEM_COLOR_YELLOW, GEM_COLOR_BLUE = 1, 2, 4, 8
RESILIENCE_STAT = 35
# ItemModType values of ItemReforge.dbc source/target stats.
REFORGE_STAT_NAMES = {6: "spirit", 13: "dodge", 14: "parry", 31: "hit", 32: "crit", 36: "haste", 37: "expertise", 49: "mastery"}


class PhaseOracleError(ValueError):
    pass


def load_enchant_conditions(path: Path) -> dict[int, list[tuple[int, int, int, int]]]:
    """SpellItemEnchantmentCondition.dbc: id -> [(color, comparator, compare color, value)].

    The 4.3.4 record is 72 bytes with 4-byte aligned arrays: id, LT operand
    type[5] (bytes, the colour), LT operand[5] (uint32), operator[5] (bytes),
    RT operand type[5] (bytes, the compare colour), RT operand[5] (uint32, the
    value), logic[5] (bytes). The core reads the first three clauses.
    """
    blob = Path(path).read_bytes()
    if blob[:4] != b"WDBC":
        raise PhaseOracleError(f"{path} is not a WDBC file")
    count, fields, size, _strings = struct.unpack_from("<4I", blob, 4)
    if fields != 31 or size != 72:
        raise PhaseOracleError(f"{path} layout is not the 4.3.4 enchantment condition record")
    conditions = {}
    for index in range(count):
        base = 20 + index * size
        record_id = struct.unpack_from("<I", blob, base)[0]
        colors, comparators, compare_colors = blob[base + 4:base + 7], blob[base + 32:base + 35], blob[base + 37:base + 40]
        values = struct.unpack_from("<3I", blob, base + 44)
        conditions[int(record_id)] = [(colors[i], comparators[i], compare_colors[i], int(values[i])) for i in range(3) if colors[i]]
    return conditions


@dataclass
class EnchantOracle:
    enchants: dict[int, dict[str, Any]]
    restrictions: dict[int, list[tuple[int, int, int]]]
    conditions: dict[int, list[tuple[int, int, int, int]]]
    reforges: dict[tuple[str, str], int] = field(default_factory=dict)

    def applicable(self, enchant_id: int, item: Mapping[str, Any]) -> bool:
        item_class, subclass = int(item["ClassID"]), int(item["SubclassID"])
        inventory_type = int(item["InventoryType"])
        for equipped_class, inventory_mask, subclass_mask in self.restrictions.get(int(enchant_id), []):
            if equipped_class == -1 and not inventory_mask:
                continue  # unrestricted: not an item-slot authority
            if equipped_class != -1:
                if equipped_class != item_class:
                    continue
                if subclass_mask and not subclass_mask & (1 << subclass):
                    continue
            if inventory_mask:
                if inventory_type == INVTYPE_WEAPON and inventory_mask & ((1 << INVTYPE_WEAPONMAINHAND) | (1 << INVTYPE_WEAPONOFFHAND)):
                    return True
                if not inventory_mask & (1 << inventory_type):
                    continue
            return True
        return False

    def stats(self, enchant_id: int) -> dict[str, int]:
        return dict((self.enchants.get(int(enchant_id)) or {}).get("stats") or {})

    def meta_active(self, condition_id: int, color_counts: Mapping[int, int]) -> bool:
        return all(self._clause(clause, color_counts) for clause in self.conditions.get(int(condition_id), []))

    def meta_deficit(self, condition_id: int, color_counts: Mapping[int, int]) -> int:
        deficit = 0
        for color, comparator, compare_color, value in self.conditions.get(int(condition_id), []):
            current = color_counts.get(color, 0)
            target = color_counts.get(compare_color, 0) if compare_color else value
            need = {2: current - target + 1, 3: target + 1 - current, 5: target - current}.get(comparator, 0)
            deficit += max(0, need)
        return deficit

    @staticmethod
    def _clause(clause: tuple[int, int, int, int], counts: Mapping[int, int]) -> bool:
        color, comparator, compare_color, value = clause
        current = counts.get(color, 0)
        target = counts.get(compare_color, 0) if compare_color else value
        if comparator == 2:
            return current < target
        if comparator == 3:
            return current > target
        if comparator == 5:
            return current >= target
        return True


def load_enchant_oracle(dbc_dir: Path) -> EnchantOracle:
    dbc_dir = Path(dbc_dir)
    for name in ("SpellItemEnchantment.dbc", "SpellEffect.dbc", "Spell.dbc", "SpellEquippedItems.dbc",
                 "SpellItemEnchantmentCondition.dbc", "ItemReforge.dbc"):
        if not (dbc_dir / name).is_file():
            raise PhaseOracleError(f"phase_enchant_oracle_missing:{name}")
    effects = [row["values"] for row in load_wdbc(dbc_dir / "SpellEffect.dbc", SPELL_EFFECT_FMT)]
    # Equip-spell enchants (e.g. 4102 "+20 All Stats" = spell 74249) grant
    # SPELL_AURA_MOD_STAT (29); misc -1 is every primary stat.
    aura_stats: dict[int, dict[str, int]] = defaultdict(dict)
    for values in effects:
        if int(values[1]) == SPELL_EFFECT_APPLY_AURA and int(values[3]) == SPELL_AURA_MOD_STAT and int(values[5]) > 0:
            misc = int(values[12])
            for name in (UNIT_STAT_NAMES if misc == -1 else [UNIT_STAT_NAMES[misc]] if 0 <= misc < 5 else []):
                aura_stats[int(values[24])][name] = aura_stats[int(values[24])].get(name, 0) + int(values[5])
    enchants: dict[int, dict[str, Any]] = {}
    for row in load_wdbc(dbc_dir / "SpellItemEnchantment.dbc", SPELL_ITEM_ENCHANTMENT_FMT):
        values = row["values"]
        stats: dict[str, int] = {}
        stat_types: set[int] = set()
        for effect, points, arg in zip(values[2:5], values[5:8], values[11:14]):
            if int(effect) == ITEM_ENCHANTMENT_TYPE_STAT and int(points) > 0:
                stat_types.add(int(arg))
                name = STAT_NAMES.get(int(arg))
                if name:
                    stats[name] = stats.get(name, 0) + int(points)
            elif int(effect) == ITEM_ENCHANTMENT_TYPE_EQUIP_SPELL:
                for name, amount in aura_stats.get(int(arg), {}).items():
                    stats[name] = stats.get(name, 0) + amount
        enchants[int(values[0])] = {"id": int(values[0]), "name": values[14], "stats": stats, "stat_types": sorted(stat_types),
                                    "source_item_id": int(values[17]), "condition_id": int(values[18]),
                                    "required_skill_id": int(values[19]), "required_skill_rank": int(values[20]),
                                    "min_level": int(values[21])}
    equipped = {int(row["values"][0]): tuple(int(value) for value in row["values"][1:4])
                for row in load_wdbc(dbc_dir / "SpellEquippedItems.dbc", SPELL_EQUIPPED_ITEMS_FMT)}
    spell_restriction = {}
    for row in load_wdbc(dbc_dir / "Spell.dbc", SPELL_FMT):
        values = row["values"]
        equipped_id = int(values[SPELL_EQUIPPED_ITEMS_ID_FIELD])
        if equipped_id in equipped:
            spell_restriction[int(values[0])] = equipped[equipped_id]
    restrictions: dict[int, list[tuple[int, int, int]]] = defaultdict(list)
    for values in effects:
        if int(values[1]) == SPELL_EFFECT_ENCHANT_ITEM and int(values[24]) in spell_restriction:
            restriction = spell_restriction[int(values[24])]
            if restriction not in restrictions[int(values[12])]:
                restrictions[int(values[12])].append(restriction)
    conditions = load_enchant_conditions(dbc_dir / "SpellItemEnchantmentCondition.dbc")
    reforges = {}
    for row in load_wdbc(dbc_dir / "ItemReforge.dbc", ITEM_REFORGE_FMT):
        values = row["values"]
        source, target = REFORGE_STAT_NAMES.get(int(values[1])), REFORGE_STAT_NAMES.get(int(values[3]))
        if source and target and abs(float(values[2]) - 0.4) < 1e-6:
            reforges[(source, target)] = int(values[0])
    if not restrictions or not conditions or len(reforges) != 56:
        raise PhaseOracleError("phase_enchant_oracle_incomplete")
    return EnchantOracle(enchants, dict(restrictions), conditions, reforges)


def socket_bonus_active(native_colors: Iterable[int], gem_colors: Iterable[int]) -> bool:
    """Item::GemsFitSockets: every native socket holds a gem whose colour matches it (the extra socket does not count)."""
    natives, gems = [int(color) for color in native_colors], [int(color) for color in gem_colors]
    return bool(natives) and len(gems) >= len(natives) and all(gem & native for gem, native in zip(gems, natives))


def gem_color_counts(equipment: Iterable[Mapping[str, Any]], gem_colors: Mapping[int, int]) -> dict[int, int]:
    """Condition color index (1 meta, 2 red, 3 yellow, 4 blue) -> equipped gem count, as the core counts them."""
    counts = {1: 0, 2: 0, 3: 0, 4: 0}
    for item in equipment:
        if not item.get("native_socket_colors"):
            continue
        for gem in list(item.get("gem_item_ids") or [])[:3]:
            color = int(gem_colors.get(int(gem or 0), 0))
            for bit in range(4):
                if color & (1 << bit):
                    counts[bit + 1] += 1
    return counts
