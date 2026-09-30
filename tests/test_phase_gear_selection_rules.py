"""Phase-gear selection rules (tools.bot_ml.phase_gear_selection, phase_gear_spell_requirements).

Spec-aware weapon legality derived from the server's spell data (Spell.dbc +
SpellEquippedItems.dbc + the SPELL_ATTR3 hand attributes), native uniqueness
(unique-equipped flag, MaxCount) instead of one copy per item ID, and cap-aware
reforging that counts activated socket bonuses. Synthetic items; the spell
requirements come from the real client DBCs and spec catalog.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.bot_ml.phase_gear_oracles import EnchantOracle, REFORGE_STAT_NAMES, socket_bonus_active
from tools.bot_ml.phase_gear_selection import (
    ITEM_FLAG_UNIQUE_EQUIPPABLE,
    PhaseSelectionError,
    SpecRequest,
    candidates_by_slot,
    item_equip_limit,
    reforge,
    select_items,
    select_loadout,
)
from tools.bot_ml.phase_gear_spell_requirements import (
    SpellRequirementError,
    apply_spell_exemptions,
    load_spell_requirements,
    requirement_met,
    spec_required_spells,
    unmet_requirements,
)
from tools.bot_ml.phase_gear_validation import reforge_cap_failures, uniqueness_failures

ROOT = Path(__file__).resolve().parents[1]
DBC = ROOT / "data/dbc/enUS"
CATALOG = ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
MUTILATE, BACKSTAB, FAN_OF_KNIVES, SHIELD_SLAM, SHIELD_WALL, STEADY_SHOT = 1329, 53, 51723, 23922, 871, 56641
LAVA_LASH, NERVES_OF_COLD_STEEL, RET_TWO_HANDED_SPEC, AVENGERS_SHIELD, SHIELD_OF_THE_RIGHTEOUS = 60103, 50138, 20113, 31935, 53600
DAGGER, AXE, SWORD, TWO_HANDED_SWORD, BOW, THROWN, STAFF, SHIELD = 15, 0, 7, 8, 2, 16, 10, 6
ARMOR_INVENTORY = {0: 1, 1: 2, 2: 3, 4: 5, 5: 6, 6: 7, 7: 8, 8: 9, 9: 10, 10: 11, 12: 12, 14: 16}


@pytest.fixture(scope="module")
def requirements():
    if not (DBC / "Spell.dbc").is_file():
        pytest.skip("client DBCs not extracted")
    return load_spell_requirements(DBC)


@pytest.fixture(scope="module")
def targets():
    return json.loads(CATALOG.read_text(encoding="utf-8"))["targets"]


def _required(spec: str, requirements, targets):
    target = next(row for row in targets if row["spec_target_id"] == spec)
    return spec_required_spells(target, targets, requirements)


def _weapon(item_id: int, inventory_type: int, subclass: int, stat: int = 100, stat_type: int = 3, level: int = 359) -> dict:
    return {"ID": item_id, "ClassID": 2, "SubclassID": subclass, "InventoryType": inventory_type, "AllowableClass": -1,
            "ItemLevel": level, "Quality": 4, "ItemStatType1": stat_type, "ItemStatValue1": stat}


def _armor(item_id: int, inventory_type: int, subclass: int, stat_type: int = 3) -> dict:
    return {**_weapon(item_id, inventory_type, subclass, 50, stat_type), "ClassID": 4}


def _fill(armor_subclass: int, stat_type: int = 3) -> list[dict]:
    """One item per non-weapon slot (a single non-unique ring and trinket fill both of their slots)."""
    return [_armor(9000 + slot, inventory, armor_subclass if inventory not in (2, 11, 12, 16) else 0, stat_type)
            for slot, inventory in ARMOR_INVENTORY.items()]


def _request(spec: str, class_id: int, required=(), weights=None) -> SpecRequest:
    return SpecRequest(bot={"class": class_id, "class_spec": spec}, weights=weights or {"agility": 2.0, "strength": 2.0},
                       archetype="dps", tier_set_ids=[], donor_equipment={}, profession_setup=None, rating_caps={},
                       required_spells=tuple(required))


def _select(request: SpecRequest, items: list[dict], equip_limits=None) -> dict:
    by_slot, _sockets = candidates_by_slot(request, items)
    return select_loadout(request, by_slot, {}, {}, {}, equip_limits or {})


# --- the requirements come from the server's own spell data -----------------------------------------

def test_native_spell_data_names_each_specs_weapon_requirements(requirements, targets):
    mutilate, backstab = requirements[MUTILATE], requirements[BACKSTAB]
    assert (mutilate.item_class, mutilate.subclass_mask, mutilate.main_hand, mutilate.off_hand) == (2, 1 << DAGGER, True, True)
    assert (backstab.subclass_mask, backstab.main_hand, backstab.off_hand) == (1 << DAGGER, True, False)
    assert requirements[SHIELD_SLAM].item_class == 4 and not requirements[SHIELD_SLAM].aura
    assert requirements[SHIELD_WALL].aura and not requirements[SHIELD_WALL].passive
    assert requirements[LAVA_LASH].off_hand and requirements[FAN_OF_KNIVES].subclass_mask == 1 << THROWN

    def ids(spec):
        return {requirement.spell_id for requirement in _required(spec, requirements, targets)}

    assert {MUTILATE, BACKSTAB, FAN_OF_KNIVES} <= ids("assassination_rogue")
    assert BACKSTAB in ids("subtlety_rogue") and MUTILATE not in ids("subtlety_rogue")
    assert not {BACKSTAB, MUTILATE} & ids("combat_rogue")
    assert SHIELD_SLAM in ids("protection_warrior") and SHIELD_OF_THE_RIGHTEOUS in ids("protection_paladin")
    # Another spec's talents and specialization spells are never required: Holy learns no Avenger's Shield,
    # Retribution no Shield of the Righteous, Elemental no Lava Lash.
    assert not {AVENGERS_SHIELD, SHIELD_OF_THE_RIGHTEOUS} & ids("holy_paladin")
    assert RET_TWO_HANDED_SPEC in ids("retribution_paladin") and AVENGERS_SHIELD not in ids("retribution_paladin")
    assert LAVA_LASH in ids("enhancement_shaman") and LAVA_LASH not in ids("elemental_shaman")
    assert NERVES_OF_COLD_STEEL in ids("frost_death_knight")
    assert all(STEADY_SHOT in ids(spec) for spec in ("beast_mastery_hunter", "marksmanship_hunter", "survival_hunter"))
    assert not ids("fire_mage") and not ids("balance_druid") and not ids("feral_druid_tank")


def test_requirement_checks_mirror_the_core_cast_checks(requirements):
    dagger, axe = _weapon(1, 13, DAGGER), _weapon(2, 22, AXE)
    mutilate = requirements[MUTILATE]
    assert requirement_met(mutilate, {15: dagger, 16: dagger})
    assert not requirement_met(mutilate, {15: dagger, 16: axe}), "the old Assassination loadout: an axe off hand"
    assert not requirement_met(mutilate, {15: axe, 16: dagger}) and not requirement_met(mutilate, {15: dagger})
    shield, sword = _armor(3, 14, SHIELD), _weapon(4, 13, SWORD)
    assert requirement_met(requirements[SHIELD_SLAM], {15: sword, 16: shield})
    assert not requirement_met(requirements[SHIELD_SLAM], {15: sword, 16: sword})
    assert requirement_met(requirements[SHIELD_WALL], {15: sword}), "the core keeps aura spells without the shield"
    assert requirement_met(requirements[STEADY_SHOT], {15: _weapon(5, 17, STAFF), 17: _weapon(6, 15, BOW)})
    assert not requirement_met(requirements[STEADY_SHOT], {15: _weapon(5, 17, STAFF), 17: _weapon(7, 25, THROWN)})
    assert requirement_met(requirements[LAVA_LASH], {15: _weapon(8, 13, AXE), 16: _weapon(9, 13, AXE)})
    assert not requirement_met(requirements[LAVA_LASH], {15: _weapon(10, 17, 1)})
    assert requirement_met(requirements[RET_TWO_HANDED_SPEC], {15: _weapon(11, 17, TWO_HANDED_SWORD)})
    assert not requirement_met(requirements[RET_TWO_HANDED_SPEC], {15: sword})


# --- the selector obeys them --------------------------------------------------------------------------

def _rogue_weapons() -> list[dict]:
    return [_weapon(1001, 13, DAGGER, 100), _weapon(1002, 22, AXE, 200), _weapon(1003, 22, DAGGER, 50),
            _weapon(1004, 25, THROWN, 50), _weapon(1005, 15, BOW, 150)]


def test_assassination_wears_daggers_in_both_hands_even_when_an_axe_scores_higher(requirements, targets):
    items = _fill(2) + _rogue_weapons()
    control = _select(_request("assassination_rogue", 4), items, {1001: 1})
    assert int(control[16]["ID"]) == 1002, "control: without the requirement the axe wins the off hand"
    request = _request("assassination_rogue", 4, _required("assassination_rogue", requirements, targets))
    chosen = _select(request, items, {1001: 1})
    assert (int(chosen[15]["ID"]), int(chosen[16]["ID"])) == (1001, 1003)
    assert int(chosen[17]["ID"]) == 1004, "Fan of Knives needs the thrown weapon although the bow scores higher"


def test_a_requirement_several_slots_can_meet_is_routed_to_a_fitting_slot(requirements, targets):
    subtlety = _select(_request("subtlety_rogue", 4, _required("subtlety_rogue", requirements, targets)), _fill(2) + _rogue_weapons())
    assert int(subtlety[15]["ID"]) == 1001 and int(subtlety[17]["ID"]) == 1004, "Backstab's dagger; Fan of Knives' thrown"
    assert int(subtlety[16]["ID"]) == 1002, "no Subtlety spell needs an off-hand dagger"
    two_hander = _weapon(2001, 17, TWO_HANDED_SWORD, 300, stat_type=4)
    one_handers = [_weapon(2002, 13, SWORD, 140, stat_type=4), _weapon(2003, 13, SWORD, 130, stat_type=4)]
    items = _fill(4, stat_type=4) + [two_hander, *one_handers, {**_armor(2010, 28, 11, 4)}]
    assert int(_select(_request("frost_death_knight", 6), items)[15]["ID"]) == 2001, "control: the two-hander scores higher"
    frost = _select(_request("frost_death_knight", 6, _required("frost_death_knight", requirements, targets)), items, {2002: 1})
    assert (int(frost[15]["ID"]), int(frost[16]["ID"])) == (2002, 2003), "Nerves of Cold Steel: one-handers"


def test_an_unmeetable_requirement_fails_closed(requirements, targets):
    request = _request("assassination_rogue", 4, _required("assassination_rogue", requirements, targets))
    no_offhand_dagger = [item for item in _fill(2) + _rogue_weapons() if int(item["ID"]) != 1003]
    with pytest.raises(PhaseSelectionError, match="phase_slots_unfilled"):
        _select(request, no_offhand_dagger, {1001: 1})
    with pytest.raises(PhaseSelectionError, match="combat_spell_requirement_unmeetable"):
        _select(request, [item for item in no_offhand_dagger if int(item["ID"]) != 1001])


# --- both hand assignments are searched ------------------------------------------------------------------

def test_a_unique_either_hand_dagger_does_not_block_a_feasible_pair(requirements, targets):
    """The review's scenario: the higher-scoring unique one-hand dagger goes to the off hand, the main-hand-only one to the main hand."""
    request = _request("assassination_rogue", 4, _required("assassination_rogue", requirements, targets))
    either, main_only = _weapon(3001, 13, DAGGER, 200), _weapon(3002, 21, DAGGER, 100)
    items = _fill(2) + [either, main_only, _weapon(1004, 25, THROWN, 50)]
    limits = {3001: 1}
    by_slot, _sockets = candidates_by_slot(request, items)
    greedy = select_items(request, by_slot, {}, {}, {}, limits)
    assert int(greedy[15]["ID"]) == 3001 and 16 not in greedy, "control: the main-hand-first fill leaves no off hand"
    chosen = _select(request, items, limits)
    assert (int(chosen[15]["ID"]), int(chosen[16]["ID"])) == (3002, 3001)


def test_the_off_hand_first_fill_keeps_a_one_handed_main_hand():
    request = _request("frost_death_knight", 6)
    items = [_weapon(4001, 17, TWO_HANDED_SWORD, 300), _weapon(4002, 13, SWORD, 100), _weapon(4003, 13, SWORD, 90)]
    by_slot, _sockets = candidates_by_slot(request, items)
    assert int(select_items(request, by_slot, {}, {}, {}, {})[15]["ID"]) == 4001
    offhand_first = select_items(request, by_slot, {}, {}, {}, {4002: 1}, offhand_first=True)
    assert (int(offhand_first[15]["ID"]), int(offhand_first[16]["ID"])) == (4003, 4002), "no two-hander beside an off hand"


# --- configured exemptions (Assassination never uses Fan of Knives) ---------------------------------------

def test_an_exempt_spell_no_longer_constrains_the_loadout(requirements, targets):
    config = json.loads((ROOT / "experiments/configs/raid_gear_phases/cata_t11_v1.json").read_text(encoding="utf-8"))
    required = _required("assassination_rogue", requirements, targets)
    kept, exempted = apply_spell_exemptions("assassination_rogue", required, config)
    assert FAN_OF_KNIVES in {row.spell_id for row in required} and FAN_OF_KNIVES not in {row.spell_id for row in kept}
    assert [row["spell_id"] for row in exempted] == [FAN_OF_KNIVES] and exempted[0]["decision"]
    assert {MUTILATE, BACKSTAB} <= {row.spell_id for row in kept}
    assert apply_spell_exemptions("subtlety_rogue", _required("subtlety_rogue", requirements, targets), config)[1] == ()
    daggers = {15: _weapon(1001, 13, DAGGER), 16: _weapon(1003, 22, DAGGER)}
    assert [row.spell_id for row in unmet_requirements(required, daggers)] == [FAN_OF_KNIVES], "control: no thrown weapon"
    assert unmet_requirements(kept, daggers) == [], "the exemption: only Fan of Knives wanted the thrown weapon"
    assert [row.spell_id for row in unmet_requirements(kept, {15: daggers[15], 16: _weapon(1002, 22, AXE)})] == [MUTILATE]
    stale = {"combat_spell_requirement_exemptions_by_spec": {"fire_mage": [{"spell_id": FAN_OF_KNIVES, "decision": "x"}]}}
    with pytest.raises(SpellRequirementError, match="combat_spell_exemption_not_required"):
        apply_spell_exemptions("fire_mage", _required("fire_mage", requirements, targets), stale)
    undecided = {"combat_spell_requirement_exemptions_by_spec": {"assassination_rogue": [{"spell_id": FAN_OF_KNIVES}]}}
    with pytest.raises(SpellRequirementError, match="combat_spell_exemption_without_decision"):
        apply_spell_exemptions("assassination_rogue", required, undecided)


# --- native uniqueness ---------------------------------------------------------------------------------

def test_one_nonunique_weapon_fills_both_hands_and_a_unique_one_does_not(requirements, targets):
    request = _request("assassination_rogue", 4, _required("assassination_rogue", requirements, targets))
    items = _fill(2) + _rogue_weapons()
    assert [int(_select(request, items)[slot]["ID"]) for slot in (15, 16)] == [1001, 1001], "two copies are lawful"
    assert [int(_select(request, items, {1001: 1})[slot]["ID"]) for slot in (15, 16)] == [1001, 1003]
    assert item_equip_limit({"flags": ITEM_FLAG_UNIQUE_EQUIPPABLE, "max_count": 0}) == 1
    assert item_equip_limit({"flags": 0, "max_count": 2}) == 2 and item_equip_limit({"flags": 0, "max_count": 0}) is None
    assert item_equip_limit({"flags": ITEM_FLAG_UNIQUE_EQUIPPABLE | 1, "max_count": 3}) == 1


def test_revalidation_counts_native_uniqueness():
    rows = [{"slot": 10, "item_id": 7, "gem_item_ids": [70, 70]}, {"slot": 11, "item_id": 7, "gem_item_ids": []}]
    facts = {7: {"flags": 0, "max_count": 0}, 70: {"flags": 0, "max_count": 1}}
    assert uniqueness_failures("k", rows, facts, {}) == [], "a socketed gem's MaxCount limits possession, not sockets"
    facts[7]["flags"] = ITEM_FLAG_UNIQUE_EQUIPPABLE
    facts[70]["flags"] = ITEM_FLAG_UNIQUE_EQUIPPABLE
    failures = uniqueness_failures("k", rows, facts, {})
    assert "k:item_unique_equipped_exceeded:7:2>1" in failures and "k:gem_unique_equipped_exceeded:70:2>1" in failures
    facts = {7: {"flags": 0, "max_count": 0, "limit_category": 5}, 70: {}}
    assert uniqueness_failures("k", rows, facts, {5: 1}) == ["k:item_limit_category_exceeded:5:2"]


# --- socket bonuses count toward rating caps -------------------------------------------------------------

def _oracle() -> EnchantOracle:
    names = sorted(set(REFORGE_STAT_NAMES.values()))
    reforges = {(source, target): index for index, (source, target) in enumerate(
        (a, b) for a in names for b in names if a != b)}
    return EnchantOracle(enchants={}, restrictions={}, conditions={}, reforges=reforges)


def _equipment():
    red_gem = {"item_id": 52206, "color": 2, "stats": {"strength": 40}}
    return [{"slot": 2, "item_id": 60348, "stats": {"haste": 100, "strength": 100}, "gems": [red_gem],
             "native_socket_colors": [2], "enchant_id": 0},
            {"slot": 10, "item_id": 59518, "stats": {"crit": 100}, "gems": [], "native_socket_colors": [], "enchant_id": 0}]


def test_cap_aware_reforging_counts_the_activated_socket_bonus():
    request = _request("retribution_paladin", 2, weights={"hit": 3.0, "mastery": 2.0, "haste": 1.0, "crit": 1.0})
    request.rating_caps = {"hit": 45}
    without_bonus = _equipment()
    reforge(without_bonus, request, _oracle(), ["hit", "haste", "crit", "mastery"], {})
    assert without_bonus[0]["reforge"]["to"] == "hit", "control: 40 hit fits the 45 cap"
    with_bonus = _equipment()
    reforge(with_bonus, request, _oracle(), ["hit", "haste", "crit", "mastery"], {60348: {"hit": 10}})
    assert all((row.get("reforge") or {}).get("to") != "hit" for row in with_bonus), "10 bonus hit + 40 would pass 45"


def test_a_socket_bonus_that_puts_the_gear_over_the_cap_makes_the_capped_rating_the_reforge_source():
    """The round-3 Retribution case: 958 modeled hit + 10 hit from a socket bonus = 968 > 961."""
    request = _request("retribution_paladin", 2, weights={"hit": 3.0, "expertise": 2.5, "haste": 1.0, "mastery": 2.0})
    request.rating_caps = {"hit": 961}
    reforgeable = ["hit", "haste", "crit", "mastery", "expertise"]

    def pauldrons():
        return [{"slot": 2, "item_id": 60348, "stats": {"hit": 958, "haste": 100}, "enchant_id": 0, "native_socket_colors": [2],
                 "gems": [{"item_id": 52206, "color": 2, "stats": {"strength": 40}}]}]

    control = pauldrons()
    reforge(control, request, _oracle(), reforgeable, {})
    assert control[0]["reforge"]["from"] == "haste", "control: 958 hit looks under the cap"
    capped = pauldrons()
    reforge(capped, request, _oracle(), reforgeable, {60348: {"hit": 10}})
    assert (capped[0]["reforge"]["from"], capped[0]["reforge"]["to"]) == ("hit", "expertise")


def test_revalidation_rejects_a_reforge_past_the_cap_through_a_socket_bonus():
    assert socket_bonus_active([2, 4], [2, 6]) and not socket_bonus_active([2, 4], [2, 2]) and not socket_bonus_active([], [])
    gems = {52206: {"item_id": 52206, "color": 2, "stats": {"strength": 40}}}
    profile = {"class_spec": "retribution_paladin", "equipment": [
        {"slot": 2, "item_id": 60348, "stats": {"haste": 100}, "gem_item_ids": [52206], "native_socket_colors": [2], "enchant_id": 0,
         "reforge": {"from": "haste", "to": "hit", "amount": 40}}]}
    config = {"reforge_policy": {"rating_caps_by_spec": {"retribution_paladin": {"hit": 45}}}}
    oracle = EnchantOracle(enchants={77: {"id": 77, "stats": {"hit": 10}}}, restrictions={}, conditions={})
    assert reforge_cap_failures("k", profile, config, gems, oracle, {60348: {"socket_bonus": 0}}) == []
    assert reforge_cap_failures("k", profile, config, gems, oracle, {60348: {"socket_bonus": 77}}) == ["k:reforge_past_cap:hit:50>45"]
