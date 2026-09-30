"""The stats an item's spells grant (on equip, on use, on proc) and the primary stats an item claims.

An item's spells are its Item-sparse SpellID/SpellTrigger pairs
(ITEM_SPELLTRIGGER_ON_USE 0, ON_EQUIP 1, CHANCE_ON_HIT 2, ON_NO_DELAY_USE 5;
ItemTemplate.h). Each spell's SpellEffect.dbc rows are read; a proc aura
(SPELL_AURA_PROC_TRIGGER_SPELL 42, ..._WITH_VALUE 231) or SPELL_EFFECT_TRIGGER_SPELL
64 is followed to the spell it triggers. The stat auras recognised
(SpellAuraDefines.h) are:

* SPELL_AURA_MOD_STAT 29 (misc 0 strength, 1 agility, 2 stamina, 3 intellect,
  4 spirit, -1 all);
* SPELL_AURA_MOD_RATING 189 (misc: a CombatRating mask, Unit.h);
* SPELL_AURA_MOD_ATTACK_POWER 99, SPELL_AURA_MOD_RANGED_ATTACK_POWER 124;
* SPELL_AURA_MOD_DAMAGE_DONE 13 on a magic school mask and
  SPELL_AURA_MOD_HEALING_DONE 135 (spell power);
* SPELL_AURA_MOD_INCREASE_HEALTH 34, SPELL_AURA_MOD_RESISTANCE 22 on armor,
  SPELL_AURA_MOD_POWER_REGEN 85 on mana.

A script-only effect (a dummy aura) is not modelled: such an item claims only
what its static stats and recognised auras show.

An item claims a primary stat family when any of its static or spell stats
belongs to it: strength (strength), agility (agility), both physical families
(attack power), intellect (intellect, spirit, spell power, mana regeneration).
An item that claims families but none of the spec's is off-spec.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping

from tools.bot_ml.build_validation_gear_profiles import load_wdbc
from tools.bot_ml.phase_gear_sources import SPELL_EFFECT_FMT

EFFECT_APPLY_AURA, EFFECT_TRIGGER_SPELL = 6, 64
AURA_MOD_DAMAGE_DONE, AURA_MOD_RESISTANCE, AURA_MOD_STAT, AURA_MOD_INCREASE_HEALTH = 13, 22, 29, 34
AURA_PROC_TRIGGER_SPELL, AURA_MOD_POWER_REGEN, AURA_MOD_ATTACK_POWER = 42, 85, 99
AURA_MOD_RANGED_ATTACK_POWER, AURA_MOD_HEALING_DONE, AURA_MOD_RATING = 124, 135, 189
AURA_PROC_TRIGGER_SPELL_WITH_VALUE = 231
PROC_AURAS = frozenset({AURA_PROC_TRIGGER_SPELL, AURA_PROC_TRIGGER_SPELL_WITH_VALUE})
TRIGGER_KINDS = {0: "use", 1: "equip", 2: "proc", 5: "use"}
MOD_STAT_NAMES = {0: "strength", 1: "agility", 2: "stamina", 3: "intellect", 4: "spirit"}
RATING_NAMES = {2: "dodge", 3: "parry", 4: "block", 5: "hit", 6: "hit", 7: "hit", 8: "crit", 9: "crit", 10: "crit",
                17: "haste", 18: "haste", 19: "haste", 23: "expertise", 25: "mastery"}
SPELL_SCHOOL_MASK_MAGIC = 0x7E
SPELL_SCHOOL_MASK_NORMAL = 0x01
MAX_TRIGGER_DEPTH = 3
# Effect fields in SPELL_EFFECT_FMT (SpellEffectEntry): Effect 1, EffectAura 3, EffectBasePoints 5,
# EffectDieSides 9, EffectMiscValue 12, EffectTriggerSpell 21, SpellID 24.
FIELD_EFFECT, FIELD_AURA, FIELD_BASE, FIELD_DIE, FIELD_MISC, FIELD_TRIGGER, FIELD_SPELL = 1, 3, 5, 9, 12, 21, 24

PRIMARY_FAMILIES = ("strength", "agility", "intellect")
FAMILY_STATS = {
    "strength": frozenset({"strength", "attack_power"}),
    "agility": frozenset({"agility", "attack_power", "ranged_attack_power"}),
    "intellect": frozenset({"intellect", "spirit", "spell_power", "mp5"}),
}
ITEM_SPELL_FIELDS = tuple((f"spell_id_{index}", f"spell_trigger_{index}") for index in range(1, 6))


class ItemEffectError(ValueError):
    pass


def load_spell_effects(dbc_dir: Path) -> dict[int, list[tuple[int, int, int, int, int]]]:
    """{spell_id: [(effect, aura, amount, misc, trigger_spell)]} from SpellEffect.dbc."""
    path = Path(dbc_dir) / "SpellEffect.dbc"
    if not path.is_file():
        raise ItemEffectError(f"item_effect_oracle_missing:{path.name}")
    effects: dict[int, list[tuple[int, int, int, int, int]]] = defaultdict(list)
    for row in load_wdbc(path, SPELL_EFFECT_FMT):
        values = row["values"]
        amount = int(values[FIELD_BASE]) + (1 if int(values[FIELD_DIE]) > 0 else 0)
        effects[int(values[FIELD_SPELL])].append((int(values[FIELD_EFFECT]), int(values[FIELD_AURA]), amount,
                                                  int(values[FIELD_MISC]), int(values[FIELD_TRIGGER])))
    return dict(effects)


def _aura_stats(aura: int, amount: int, misc: int) -> list[tuple[str, int]]:
    if aura == AURA_MOD_STAT:
        return [(name, amount) for stat, name in MOD_STAT_NAMES.items() if misc in (stat, -1)]
    if aura == AURA_MOD_RATING:
        return [(name, amount) for name in sorted({name for bit, name in RATING_NAMES.items() if misc & (1 << bit)})]
    if aura == AURA_MOD_ATTACK_POWER:
        return [("attack_power", amount)]
    if aura == AURA_MOD_RANGED_ATTACK_POWER:
        return [("ranged_attack_power", amount)]
    if aura == AURA_MOD_DAMAGE_DONE and misc & SPELL_SCHOOL_MASK_MAGIC and not misc & SPELL_SCHOOL_MASK_NORMAL:
        return [("spell_power", amount)]
    if aura == AURA_MOD_HEALING_DONE:
        return [("spell_power", amount)]
    if aura == AURA_MOD_INCREASE_HEALTH:
        return [("health", amount)]
    if aura == AURA_MOD_RESISTANCE and misc & SPELL_SCHOOL_MASK_NORMAL:
        return [("armor", amount)]
    if aura == AURA_MOD_POWER_REGEN and misc == 0:
        return [("mp5", amount)]
    return []


def spell_stats(spell_id: int, effects: Mapping[int, list[tuple[int, int, int, int, int]]], kind: str,
                depth: int = 0, seen: frozenset[int] = frozenset()) -> list[tuple[str, str, int]]:
    """[(kind, stat, amount)] a spell grants, following procs and triggered spells (a proc makes the kind 'proc')."""
    if depth > MAX_TRIGGER_DEPTH or spell_id in seen or spell_id <= 0:
        return []
    found: list[tuple[str, str, int]] = []
    for effect, aura, amount, misc, trigger in effects.get(spell_id, []):
        if aura in PROC_AURAS or effect == EFFECT_TRIGGER_SPELL:
            next_kind = "proc" if aura in PROC_AURAS else kind
            found += spell_stats(trigger, effects, next_kind, depth + 1, seen | {spell_id})
        elif aura:
            found += [(kind, name, value) for name, value in _aura_stats(aura, amount, misc)]
    return found


def item_spell_stats(fact: Mapping[str, Any] | None, effects: Mapping[int, list]) -> list[tuple[str, str, int]]:
    """[(kind, stat, amount)] of every spell on the item (on use, on equip, on proc).

    Within one item spell a stat counts once at its largest amount: a spell-power
    buff carries both a damage-done and a healing-done aura of the same value.
    """
    found: list[tuple[str, str, int]] = []
    for spell_field, trigger_field in ITEM_SPELL_FIELDS:
        spell_id, trigger = int((fact or {}).get(spell_field) or 0), int((fact or {}).get(trigger_field) or 0)
        if spell_id > 0 and trigger in TRIGGER_KINDS:
            best: dict[tuple[str, str], int] = {}
            for kind, name, amount in spell_stats(spell_id, effects, TRIGGER_KINDS[trigger]):
                best[(kind, name)] = max(amount, best.get((kind, name), amount))
            found += [(kind, name, amount) for (kind, name), amount in sorted(best.items())]
    return found


def modeled_effect_stats(spell_stats_rows: Iterable[tuple[str, str, int]], uptime: Mapping[str, float]) -> dict[str, float]:
    """{stat: amount x uptime of its kind}, the value an item's spells add to its selection score."""
    totals: dict[str, float] = defaultdict(float)
    for kind, name, amount in spell_stats_rows:
        totals[name] += float(amount) * float(uptime[kind])
    return {name: round(value, 3) for name, value in sorted(totals.items()) if value}


def claimed_families(static_stats: Mapping[str, Any], spell_stats_rows: Iterable[tuple[str, str, int]]) -> set[str]:
    names = {name for name, value in static_stats.items() if value} | {name for _kind, name, amount in spell_stats_rows if amount}
    return {family for family, stats in FAMILY_STATS.items() if names & stats}


def off_spec_families(static_stats: Mapping[str, Any], spell_stats_rows: Iterable[tuple[str, str, int]],
                      family: str) -> set[str]:
    """The families an item claims when none is the spec's; empty when it fits or claims none."""
    if family not in FAMILY_STATS:
        raise ItemEffectError(f"primary_stat_family_unknown:{family}")
    claimed = claimed_families(static_stats, spell_stats_rows)
    return claimed if claimed and family not in claimed else set()


def spec_primary_family(config: Mapping[str, Any], spec: str, weights: Mapping[str, float]) -> str:
    """The spec's primary stat from the phase config, cross-checked against its highest-weighted primary stat."""
    family = str((config.get("primary_stat_by_spec") or {}).get(spec) or "")
    if family not in PRIMARY_FAMILIES:
        raise ItemEffectError(f"primary_stat_undeclared:{spec}")
    heaviest = max(PRIMARY_FAMILIES, key=lambda name: (float(weights.get(name, 0.0)), name == family))
    if float(weights.get(family, 0.0)) <= 0 or heaviest != family:
        raise ItemEffectError(f"primary_stat_disagrees_with_weights:{spec}:{family}:{heaviest}")
    return family
