"""Round 5: the canonical Survival hunter's pet is a Ravager, for the +4% physical damage taken debuff.

The family, template, talents and spellbook are checked against the client DBCs and the TDB world dump
(tools/raid_program/raid_loadout_pet.py); the shard plan provisions the declared pet for the canonical
roster only.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from tools.raid_program import raid_loadout_pet as lp
from tools.raid_program import raid_shard_plan as rsp

ROOT = Path(__file__).resolve().parents[1]
COMPOSITION = ROOT / "experiments/configs/raid_compositions/blackwing_descent_10n.json"
CATALOG = ROOT / "experiments/configs/all_spec_targets_cata_p4_v1.json"
RAVAGER, WORM, RHINO, WOLF = 31, 42, 43, 1
RAVAGE, ACID_SPIT = 50518, 55749
PHYSICAL_TAKEN_4PCT = (87, 1, 4)  # SPELL_AURA_MOD_DAMAGE_PERCENT_TAKEN, SPELL_SCHOOL_MASK_NORMAL, +4

needs_dbc = pytest.mark.skipif(not (lp.DEFAULT_DBC_DIR / "Talent.dbc").is_file(), reason="client DBCs not hydrated")
needs_tdb = pytest.mark.skipif(not lp.TDB_WORLD.is_file(), reason="TDB world dump not hydrated")


def _hunter() -> dict:
    composition = json.loads(COMPOSITION.read_text())
    return next(row for row in composition["characters"] if row["character_key"] == "hunter")


@pytest.fixture(scope="module")
def plan() -> dict:
    from tools.raid_program.raid_shard_scenarios import build_plan
    return build_plan(COMPOSITION)


@pytest.fixture(scope="module")
def templates() -> dict:
    return lp.creature_templates([26030, 8959])


@needs_dbc
def test_ravage_is_the_non_exotic_provider_of_the_physical_damage_taken_debuff():
    assert lp.spell_auras(ACID_SPIT) == lp.spell_auras(RAVAGE) == {PHYSICAL_TAKEN_4PCT}
    providers = {family for family, facts in lp.families().items() if facts["talent_type"] >= 0
                 and any(PHYSICAL_TAKEN_4PCT in lp.spell_auras(spell) for spell in lp.family_spells(family))}
    assert providers == {RAVAGER, WORM}
    assert lp.families()[RAVAGER]["name"] == "Ravager" and RAVAGE in lp.levelup_spells(RAVAGER, 85)


@needs_dbc
@needs_tdb
def test_the_ravager_template_is_tameable_by_a_survival_hunter_and_the_worm_is_not(templates):
    assert templates[26030] == {"name": "Tamable Ravager", "family": RAVAGER, "type": 1, "type_flags": 1,
                                "modelid1": 23519}
    by_family = lp.creature_templates(families=[RAVAGER, WORM, RHINO])
    tameable = {family: [row for row in by_family.values() if row["family"] == family and row["type_flags"] & 1]
                for family in (RAVAGER, WORM, RHINO)}
    # Every tameable Worm and Rhino is exotic (type_flags 0x10000): only Beast Mastery tames them.
    assert tameable[WORM] and tameable[RHINO] and all(row["type_flags"] & lp.TYPE_FLAG_EXOTIC
                                                      for family in (WORM, RHINO) for row in tameable[family])
    assert tameable[RAVAGER] and not any(row["type_flags"] & lp.TYPE_FLAG_EXOTIC for row in tameable[RAVAGER])


@needs_dbc
@needs_tdb
def test_the_declared_ravager_is_lawful(templates):
    pet = _hunter()["pet"]
    result = lp.validate_hunter_pet(pet, pet["family_id"], template=templates[pet["entry"]])
    assert result["failures"] == []
    assert (result["family"], result["talent_tab"], pet["talent_tab"]) == ("Ravager", 411, 411)
    assert result["talent_points"] == result["max_talent_points"] == 17
    rows = dict(lp.pet_spell_rows(pet))
    assert lp.levelup_spells(RAVAGER, 85) <= set(rows) and rows[RAVAGE] == lp.ACT_ENABLED  # autocast


@needs_dbc
@needs_tdb
def test_the_validator_refuses_unlawful_pets(templates):
    pet = _hunter()["pet"]
    wrong_family = lp.validate_hunter_pet(pet, WOLF, template=templates[pet["entry"]])["failures"]
    assert "template_family" in wrong_family and f"spell_not_auto_acquired:{RAVAGE}" in wrong_family
    exotic = lp.validate_hunter_pet(pet, RAVAGER, template={**templates[pet["entry"]], "type_flags": 0x10001})
    assert "template_exotic" in exotic["failures"]
    over = copy.deepcopy(pet)
    over["spells"].append(61690)  # Natural Armor 2/2: 19 points
    assert any(failure.startswith("talent_points:") for failure in lp.validate_hunter_pet(over, RAVAGER)["failures"])
    locked = copy.deepcopy(pet)
    locked["spells"] = [row for row in locked["spells"] if row not in (53516, 19596)]  # 3 tier-1 points gone
    refused = lp.validate_hunter_pet(locked, RAVAGER)["failures"]
    assert {"talent_tier_locked:2183", "talent_tier_locked:2168"} <= set(refused)  # Feeding Frenzy, Great Resistance
    dive = copy.deepcopy(pet)
    dive["spells"] = [{"id": 23145, "active": 129} if isinstance(row, dict) and row["id"] == 61684 else row
                      for row in dive["spells"]]
    assert "talent_not_for_family:23145" in lp.validate_hunter_pet(dive, RAVAGER)["failures"]
    passive = copy.deepcopy(pet)
    passive["spells"] = [{"id": 53184, "active": 193} if row == 53184 else row for row in passive["spells"]]
    assert "active_state:53184:193" in lp.validate_hunter_pet(passive, RAVAGER)["failures"]


@needs_dbc
def test_another_trees_talents_are_refused_even_though_skill_line_270_lists_them():
    """Review round 5: skill line 270 is shared by every family and lists all three pet trees' talents."""
    pet = copy.deepcopy(_hunter()["pet"])
    assert {53205, 62760, 53434} <= lp.family_spells(RAVAGER)  # the shared skill line lists Ferocity talents
    pet["spells"] += [53205, 62760, {"id": 53434, "active": 193}]  # Spider's Bite, Shark Attack, Call of the Wild
    failures = lp.validate_hunter_pet(pet, RAVAGER)["failures"]
    assert {"talent_of_other_tree:53205", "talent_of_other_tree:62760", "talent_of_other_tree:53434"} <= set(failures)
    trained = copy.deepcopy(_hunter()["pet"])
    trained["spells"].append({"id": 24394, "active": 193})  # Intimidation: a trained skill-line 270 spell (method 0)
    assert "spell_not_auto_acquired:24394" in lp.validate_hunter_pet(trained, RAVAGER)["failures"]


@needs_dbc
def test_the_ravager_build_skips_scriptless_talents_and_keeps_its_gcd_wasters_off_autocast():
    pet = _hunter()["pet"]
    rows = dict(lp.pet_spell_rows(pet))
    assert 62762 not in rows and 62758 not in rows  # Wild Hunt: dummy effects, no script
    assert not {61680, 61681, 52858} & set(rows)  # Culling the Herd: its spell_proc mask never matches here
    assert 53508 not in rows  # Wolverine Bite: about 1 damage for a pet GCD
    assert rows[53430] == rows[53450] == 1  # Great Resistance 3/3 and Grace of the Mantis 1/2: passives
    assert rows[61684] == lp.ACT_DISABLED  # Dash
    bar = [int(value) for value in pet["actionbar"].split()]
    assert dict(zip(bar[1::2], bar[0::2]))[61684] == lp.ACT_DISABLED  # the action bar overrides pet_spell


@needs_dbc
@needs_tdb
def test_the_catalog_wolf_findings_are_reported_not_fixed(templates):
    """The qualified catalog wolf (legacy baiter 30009, calibration) loads natively but is not a talent-UI
    build: Dive is the flying families' variant and Shark Attack sits above 14 lower-tier points."""
    catalog = json.loads(CATALOG.read_text())
    wolf = next(row for row in catalog["targets"] if row["spec_target_id"] == "survival_hunter")["provisioning_bot"]["pet"]
    assert wolf["entry"] == 8959
    result = lp.validate_hunter_pet(wolf, WOLF, template=templates[8959])
    assert result["failures"] == ["talent_not_for_family:23145", "talent_tier_locked:2254"]


def test_every_canonical_hunter_gets_the_declared_ravager(plan):
    declared = _hunter()["pet"]
    for shard in plan["shards"]:
        hunter = next(bot for bot in shard["bots"] if bot["character_key"] == "hunter")
        pet = hunter["pet"]
        assert {key: pet[key] for key in rsp.PET_RUNTIME_KEYS} == {key: declared[key] for key in rsp.PET_RUNTIME_KEYS}
        assert pet["name"] == (hunter["name"].lower() + "pet")[:12] and set(pet) == set(rsp.PET_RUNTIME_KEYS) | {"name"}
        assert hunter["expected_pet_id"] == 30_000_000 + hunter["character_guid"] - 10_000_000


@pytest.mark.parametrize("mutate,reason", [
    (lambda row: row.update(specs=["fire_mage"]), "not_a_hunter"),
    (lambda row: row["pet"].update(actionbar="7 2"), "actionbar"),
    (lambda row: row["pet"].update(entry=0), "entry"),
    (lambda row: row["pet"]["spells"].append({"id": 50518, "active": 2}), "spell"),
    (lambda row: row["pet"]["spells"].append(50518), "spells"),
    (lambda row: row["pet"].update(level=86), "level_slot_or_active"),
])
def test_a_malformed_declared_pet_is_refused(mutate, reason):
    row = copy.deepcopy(_hunter())
    mutate(row)
    with pytest.raises(rsp.ShardPlanError, match=f"character_pet_invalid:hunter:{reason}"):
        rsp.character_pet(row)
    assert rsp.character_pet({"character_key": "hunter", "specs": ["survival_hunter"]}) is None
