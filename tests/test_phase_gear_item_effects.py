"""Item-spell stats and the primary-stat fit of phase gear (tools.bot_ml.phase_gear_item_effects).

The round-3 v2 Blood DK (a strength tank) wore Fluid Death and License to Slay:
Fluid Death's only primary stat is an agility proc from its item spell, which
the static-stat selector could not see. Item spells (on equip, on use, on proc)
are read from Item-sparse SpellID/SpellTrigger and SpellEffect.dbc.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.bot_ml.phase_gear_extract import item_facts
from tools.bot_ml.phase_gear_item_effects import (
    ItemEffectError,
    claimed_families,
    item_spell_stats,
    load_spell_effects,
    modeled_effect_stats,
    off_spec_families,
    spec_primary_family,
)
from tools.bot_ml.phase_gear_selection import SpecRequest, candidates_by_slot, item_value

ROOT = Path(__file__).resolve().parents[1]
DBC = ROOT / "data/dbc/enUS"
T11 = ROOT / "experiments/configs/raid_gear_phases/cata_t11_v1.json"
FLUID_DEATH, LICENSE_TO_SLAY, STUMP_OF_TIME, VIAL_OF_STOLEN_MEMORIES, SYMBIOTIC_WORM = 58181, 58180, 62470, 59515, 59332


@pytest.fixture(scope="module")
def oracle():
    if not (DBC / "SpellEffect.dbc").is_file() or not (DBC / "Item-sparse.db2").is_file():
        pytest.skip("client DBCs not extracted")
    return item_facts(DBC, {"item_sparse": []}), load_spell_effects(DBC)


def test_item_spells_are_followed_to_their_stat_auras(oracle):
    facts, effects = oracle
    assert item_spell_stats(facts[FLUID_DEATH], effects) == [("proc", "agility", 38)], "equip proc -> stacking agility"
    assert item_spell_stats(facts[LICENSE_TO_SLAY], effects) == [("proc", "strength", 38)]
    assert item_spell_stats(facts[STUMP_OF_TIME], effects) == [("proc", "spell_power", 1926)], "damage+healing aura counted once"
    assert item_spell_stats(facts[VIAL_OF_STOLEN_MEMORIES], effects) == [("use", "dodge", 1605)]
    assert item_spell_stats(facts[SYMBIOTIC_WORM], effects) == [("proc", "mastery", 963)]
    assert modeled_effect_stats([("use", "dodge", 1605), ("equip", "stamina", 10)], {"use": 0.2, "equip": 1.0, "proc": 0.3}) \
        == {"dodge": 321.0, "stamina": 10.0}


def test_an_item_claiming_only_other_primary_families_is_off_spec(oracle):
    facts, effects = oracle
    fluid_death = item_spell_stats(facts[FLUID_DEATH], effects)
    assert off_spec_families({"hit": 321}, fluid_death, "strength") == {"agility"}, "the v2 Blood DK trinket"
    assert off_spec_families({"hit": 321}, fluid_death, "agility") == set()
    assert off_spec_families({"stamina": 482}, item_spell_stats(facts[SYMBIOTIC_WORM], effects), "strength") == set()
    assert off_spec_families({"spirit": 100}, [], "strength") == {"intellect"}
    assert off_spec_families({"agility": 10}, [("proc", "attack_power", 5)], "strength") == set(), "attack power is physical"
    assert claimed_families({}, [("use", "spell_power", 1)]) == {"intellect"}
    with pytest.raises(ItemEffectError, match="family_unknown"):
        off_spec_families({}, [], "stamina")


def test_the_declared_primary_stat_matches_every_specs_weights():
    from tools.bot_ml.build_phase_gear_profiles import spec_weights
    from tools.bot_ml.validation_profile_manifests import DEFAULT_COMBAT_LOOT_PROFILE_MANIFEST, load_combat_loot_profile_manifest

    config = json.loads(T11.read_text(encoding="utf-8"))
    manifest = load_combat_loot_profile_manifest(DEFAULT_COMBAT_LOOT_PROFILE_MANIFEST)
    targets = json.loads((ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json").read_text(encoding="utf-8"))["targets"]
    families = {row["spec_target_id"]: spec_primary_family(config, row["spec_target_id"], spec_weights(row["provisioning_bot"], manifest, config))
                for row in targets}
    assert len(families) == 31
    assert {spec for spec, family in families.items() if family == "strength"} >= {"blood_death_knight", "protection_paladin",
                                                                                     "retribution_paladin"}
    assert {families[spec] for spec in ("feral_druid_tank", "enhancement_shaman", "assassination_rogue", "survival_hunter")} == {"agility"}
    assert {families[spec] for spec in ("holy_paladin", "restoration_shaman", "fire_mage", "balance_druid")} == {"intellect"}
    with pytest.raises(ItemEffectError, match="primary_stat_disagrees_with_weights"):
        spec_primary_family({"primary_stat_by_spec": {"x": "agility"}}, "x", {"strength": 2.0, "agility": 0.5})
    with pytest.raises(ItemEffectError, match="primary_stat_undeclared"):
        spec_primary_family({}, "x", {"strength": 2.0})


def _trinket(item_id: int, stat_type: int, value: int, effect_stats=None) -> dict:
    row = {"ID": item_id, "ClassID": 4, "SubclassID": 0, "InventoryType": 12, "AllowableClass": -1, "ItemLevel": 359, "Quality": 4,
           "ItemStatType1": stat_type, "ItemStatValue1": value}
    return dict(row, effect_stats=effect_stats) if effect_stats else row


def test_item_spell_stats_count_and_tanks_prefer_defensive_trinkets():
    hit, stamina = _trinket(1, 31, 321), _trinket(2, 7, 482, {"dodge": 321.0})
    weights = {"hit": 3.0, "stamina": 1.2, "dodge": 0.6, "strength": 2.0}
    assert item_value(stamina, weights) == 3590 + 482 * 1.2 + 321 * 0.6, "the on-use dodge adds at its uptime"

    def ranked(preferred):
        request = SpecRequest(bot={"class": 6, "class_spec": "blood_death_knight"}, weights=weights, archetype="tank",
                              tier_set_ids=[], donor_equipment={}, profession_setup=None, rating_caps={},
                              preferred_trinket_stats=frozenset(preferred))
        return [int(row["ID"]) for row in candidates_by_slot(request, [hit, stamina])[0][12]]

    assert ranked(()) == [1, 2], "control: by weight alone the hit trinket wins"
    assert ranked(("stamina", "dodge", "parry", "mastery")) == [2, 1]
