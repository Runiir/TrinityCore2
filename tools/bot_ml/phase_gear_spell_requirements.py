"""Spec-aware weapon legality from the server's own spell data.

A spec's required combat spells are the spells of its catalog action profile
that carry an equipped-item requirement (Spell.dbc EquippedItemsID ->
SpellEquippedItems.dbc), less the talent and specialization spells that only
another spec of the class learns (Holy never learns Avenger's Shield, an
Elemental shaman never learns Lava Lash). A loadout meets a requirement the way
the core checks a cast:

* ``Spell::CheckItems``: SPELL_ATTR3_REQUIRES_MAIN_HAND_WEAPON and
  SPELL_ATTR3_REQUIRES_OFF_HAND_WEAPON need a weapon in that hand that fits the
  spell (``Item::IsFitToSpellRequirements``): Mutilate needs a dagger in both
  hands, Backstab one in the main hand, Lava Lash an off-hand weapon;
* ``Player::HasItemFitToSpellRequirements``: a weapon requirement needs one
  fitting item in the main hand, off hand or ranged slot (hunter shots, Fan of
  Knives' thrown weapon, Two-Handed Weapon Specialization); a shield
  requirement needs a fitting off hand, except for a non-passive spell with an
  aura effect (Shield Wall, Shield Block), which the core lets through;
* an item-enchanting spell (a weapon imbue) needs a fitting main- or off-hand
  item, its inventory type included.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping

from tools.bot_ml.build_validation_gear_profiles import load_wdbc
from tools.bot_ml.phase_gear_oracles import (
    INVTYPE_WEAPON,
    INVTYPE_WEAPONMAINHAND,
    INVTYPE_WEAPONOFFHAND,
    SPELL_EQUIPPED_ITEMS_FMT,
    SPELL_EQUIPPED_ITEMS_ID_FIELD,
    SPELL_FMT,
)
from tools.bot_ml.phase_gear_sources import SPELL_EFFECT_FMT

SPELL_NAME_FIELD, SPELL_ATTRIBUTES_FIELD, SPELL_ATTRIBUTES_EX3_FIELD = 21, 1, 4
SPELL_ATTR0_PASSIVE = 0x00000040
SPELL_ATTR3_REQUIRES_MAIN_HAND_WEAPON = 0x00000400
SPELL_ATTR3_REQUIRES_OFF_HAND_WEAPON = 0x01000000
# SpellEffectInfo::IsAura: APPLY_AURA, PERSISTENT_AREA_AURA, the area auras and APPLY_AURA_2, with an aura name.
AURA_EFFECTS = frozenset({6, 27, 35, 65, 119, 128, 129, 143, 174})
ENCHANT_EFFECTS = frozenset({53, 54, 156})  # ENCHANT_ITEM, ENCHANT_ITEM_TEMPORARY, ENCHANT_ITEM_PRISMATIC
ITEM_CLASS_WEAPON, ITEM_CLASS_ARMOR = 2, 4
SHIELD_SUBCLASS_MASK = (1 << 5) | (1 << 6)  # ITEM_SUBCLASS_ARMOR_BUCKLER, ITEM_SUBCLASS_ARMOR_SHIELD
MAIN_HAND, OFF_HAND, RANGED = 15, 16, 17
ARMOR_SLOTS = tuple(range(0, 15))  # EQUIPMENT_SLOT_START .. EQUIPMENT_SLOT_MAINHAND


class SpellRequirementError(ValueError):
    pass


@dataclass(frozen=True)
class SpellRequirement:
    spell_id: int
    name: str
    item_class: int
    subclass_mask: int
    inventory_mask: int
    main_hand: bool
    off_hand: bool
    passive: bool
    aura: bool
    enchant: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def load_spell_requirements(dbc_dir: Path) -> dict[int, SpellRequirement]:
    """Every spell with an equipped-item requirement (EquippedItemClass >= 0), by spell ID."""
    dbc_dir = Path(dbc_dir)
    for name in ("Spell.dbc", "SpellEquippedItems.dbc", "SpellEffect.dbc"):
        if not (dbc_dir / name).is_file():
            raise SpellRequirementError(f"spell_requirement_oracle_missing:{name}")
    equipped = {int(row["values"][0]): tuple(int(value) for value in row["values"][1:4])
                for row in load_wdbc(dbc_dir / "SpellEquippedItems.dbc", SPELL_EQUIPPED_ITEMS_FMT)}
    auras: set[int] = set()
    enchants: set[int] = set()
    for row in load_wdbc(dbc_dir / "SpellEffect.dbc", SPELL_EFFECT_FMT):
        values = row["values"]
        effect, spell_id = int(values[1]), int(values[24])
        if effect in AURA_EFFECTS and int(values[3]):
            auras.add(spell_id)
        if effect in ENCHANT_EFFECTS:
            enchants.add(spell_id)
    requirements: dict[int, SpellRequirement] = {}
    for row in load_wdbc(dbc_dir / "Spell.dbc", SPELL_FMT):
        values = row["values"]
        restriction = equipped.get(int(values[SPELL_EQUIPPED_ITEMS_ID_FIELD]))
        if restriction is None or restriction[0] < 0:
            continue
        spell_id = int(values[0])
        attributes, attributes_ex3 = int(values[SPELL_ATTRIBUTES_FIELD]) & 0xFFFFFFFF, int(values[SPELL_ATTRIBUTES_EX3_FIELD]) & 0xFFFFFFFF
        requirements[spell_id] = SpellRequirement(
            spell_id=spell_id, name=str(values[SPELL_NAME_FIELD]), item_class=restriction[0],
            inventory_mask=restriction[1], subclass_mask=restriction[2],
            main_hand=bool(attributes_ex3 & SPELL_ATTR3_REQUIRES_MAIN_HAND_WEAPON),
            off_hand=bool(attributes_ex3 & SPELL_ATTR3_REQUIRES_OFF_HAND_WEAPON),
            passive=bool(attributes & SPELL_ATTR0_PASSIVE), aura=spell_id in auras, enchant=spell_id in enchants)
    if not requirements:
        raise SpellRequirementError("spell_requirement_oracle_empty")
    return requirements


def _own_spells(target: Mapping[str, Any]) -> set[int]:
    build = target.get("talent_build") or {}
    return {int(row["spell_id"]) for row in build.get("talents") or []} | {int(spell) for spell in build.get("primary_tree_spells") or []}


def spec_required_spells(target: Mapping[str, Any], class_targets: Iterable[Mapping[str, Any]],
                         requirements: Mapping[int, SpellRequirement]) -> tuple[SpellRequirement, ...]:
    """The spec's action-profile spells with an equipped-item requirement it can learn, by spell ID."""
    own = _own_spells(target)
    foreign: set[int] = set()
    for other in class_targets:
        if other["spec_target_id"] != target["spec_target_id"] and int(other["class_id"]) == int(target["class_id"]):
            foreign |= _own_spells(other)
    foreign -= own
    spells = sorted({int(spell) for spell in target.get("action_profile_spell_ids") or []} - foreign)
    return tuple(requirements[spell] for spell in spells if spell in requirements)


def _view(item: Mapping[str, Any]) -> tuple[int, int, int]:
    if "ClassID" in item:
        return int(item["ClassID"]), int(item["SubclassID"]), int(item["InventoryType"])
    return int(item["item_class"]), int(item["subclass"]), int(item["inventory_type"])


def item_fits(requirement: SpellRequirement, item: Mapping[str, Any] | None) -> bool:
    """Item::IsFitToSpellRequirements (the enchanting-vellum exception aside)."""
    if item is None:
        return False
    item_class, subclass, inventory_type = _view(item)
    if requirement.item_class != -1:
        if requirement.item_class != item_class:
            return False
        if requirement.subclass_mask and not requirement.subclass_mask & (1 << subclass):
            return False
    if requirement.enchant and requirement.inventory_mask:
        if inventory_type == INVTYPE_WEAPON and requirement.inventory_mask & ((1 << INVTYPE_WEAPONMAINHAND) | (1 << INVTYPE_WEAPONOFFHAND)):
            return True
        if not requirement.inventory_mask & (1 << inventory_type):
            return False
    return True


def _weapon(item: Mapping[str, Any] | None) -> bool:
    return item is not None and _view(item)[0] == ITEM_CLASS_WEAPON


def requirement_met(requirement: SpellRequirement, loadout: Mapping[int, Mapping[str, Any]]) -> bool:
    """Whether a cast of the spell passes the core's equipped-item checks with this loadout ({slot: item})."""
    if requirement.main_hand and not (_weapon(loadout.get(MAIN_HAND)) and item_fits(requirement, loadout.get(MAIN_HAND))):
        return False
    if requirement.off_hand and not (_weapon(loadout.get(OFF_HAND)) and item_fits(requirement, loadout.get(OFF_HAND))):
        return False
    if requirement.enchant:
        return any(item_fits(requirement, loadout.get(slot)) for slot in (MAIN_HAND, OFF_HAND))
    return _has_item_fit(requirement, loadout)


def _has_item_fit(requirement: SpellRequirement, loadout: Mapping[int, Mapping[str, Any]]) -> bool:
    """Player::HasItemFitToSpellRequirements."""
    if requirement.item_class < 0:
        return True
    if requirement.item_class == ITEM_CLASS_WEAPON:
        return any(item_fits(requirement, loadout.get(slot)) for slot in (MAIN_HAND, OFF_HAND, RANGED))
    if requirement.item_class == ITEM_CLASS_ARMOR:
        if requirement.subclass_mask & SHIELD_SUBCLASS_MASK:
            if item_fits(requirement, loadout.get(OFF_HAND)):
                return True
            if not requirement.passive and requirement.aura:
                return True  # the core keeps Shield Wall-like auras without the shield
        return any(item_fits(requirement, loadout.get(slot)) for slot in (*ARMOR_SLOTS, RANGED))
    return False


def unmet_requirements(requirements: Iterable[SpellRequirement],
                       loadout: Mapping[int, Mapping[str, Any]]) -> list[SpellRequirement]:
    return [requirement for requirement in requirements if not requirement_met(requirement, loadout)]


def route_slots(requirement: SpellRequirement) -> tuple[int, ...]:
    """The slots one fitting item can occupy to meet the requirement, in preference order."""
    if requirement.main_hand or requirement.off_hand:
        return tuple(slot for slot, needed in ((MAIN_HAND, requirement.main_hand), (OFF_HAND, requirement.off_hand)) if needed)
    if requirement.enchant:
        return (MAIN_HAND, OFF_HAND)
    if requirement.item_class == ITEM_CLASS_WEAPON:
        return (MAIN_HAND, OFF_HAND, RANGED)
    if requirement.item_class == ITEM_CLASS_ARMOR:
        return (OFF_HAND,) if requirement.subclass_mask & SHIELD_SUBCLASS_MASK else (*ARMOR_SLOTS, RANGED)
    return ()


def apply_spell_exemptions(spec: str, required: Iterable[SpellRequirement], config: Mapping[str, Any]
                           ) -> tuple[tuple[SpellRequirement, ...], tuple[dict[str, Any], ...]]:
    """(the requirements the loadout must meet, the exempted ones) under the phase config's
    ``combat_spell_requirement_exemptions_by_spec``: spells the spec's approved rotation never casts
    (Assassination never uses Fan of Knives). An exemption naming a spell the spec does not require fails closed."""
    required = tuple(required)
    rows = (config.get("combat_spell_requirement_exemptions_by_spec") or {}).get(spec) or []
    exempt = {int(row["spell_id"]): row for row in rows}
    unknown = sorted(set(exempt) - {requirement.spell_id for requirement in required})
    if unknown or len(exempt) != len(rows):
        raise SpellRequirementError(f"combat_spell_exemption_not_required:{spec}:{unknown}")
    if not all(str(row.get("decision") or "").strip() for row in rows):
        raise SpellRequirementError(f"combat_spell_exemption_without_decision:{spec}")
    kept = tuple(requirement for requirement in required if requirement.spell_id not in exempt)
    exempted = tuple({"spell_id": requirement.spell_id, "name": requirement.name,
                      "decision": str(exempt[requirement.spell_id].get("decision") or "")}
                     for requirement in required if requirement.spell_id in exempt)
    return kept, exempted
