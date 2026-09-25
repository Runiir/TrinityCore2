"""The two-spec spellbook never removes a spell the core teaches every character of the race/class."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.raid_program.raid_composition import COMPOSITION_DIR, catalog_bot, load_catalog, read_json
from tools.raid_program.raid_loadout_spells import (
    LoadoutSpellError,
    auto_learned_spells,
    loadout_known_spells,
    native_baseline,
    spell_learn_map,
    trainer_classes,
    trainers_sha256,
)
from tools.raid_program.raid_shard_plan import character_loadout_groups

ROOT = Path(__file__).resolve().parents[1]
DBC = ROOT / "data/dbc/enUS"
TRAINERS = ROOT / "dataset/world_knowledge/trainers.jsonl"

pytestmark = pytest.mark.skipif(not TRAINERS.is_file() or not (DBC / "SkillLineAbility.dbc").is_file(),
                                reason="world_knowledge trainers or client DBCs not hydrated")


@pytest.fixture(scope="module")
def catalog() -> dict:
    return load_catalog(read_json(COMPOSITION_DIR / "blackwing_descent_10n.json"))


def loadout_bot(catalog: dict, specs: list[str], active_spec: str, race: int | None = None) -> dict:
    groups = character_loadout_groups(catalog, {"specs": specs})
    active = next(group["talent_group"] for group in groups if group["class_spec"] == active_spec)
    source = catalog_bot(catalog, active_spec)
    return {"name": "Probe", "class": int(source["class"]), "race": int(race or source["race"]),
            "loadout": {"talent_groups_count": 2, "active_talent_group": active, "groups": groups}}


def spells(catalog: dict, specs: list[str], active_spec: str, race: int | None = None) -> dict:
    return loadout_known_spells(loadout_bot(catalog, specs, active_spec, race), DBC, trainers_path=TRAINERS)


def test_auto_learned_skill_spells_follow_race_and_class_masks():
    assert 88684 in auto_learned_spells(DBC, race=1, class_id=5)       # Holy Word: Serenity, Holy skill, AcquireMethod 2
    assert 2457 in auto_learned_spells(DBC, race=1, class_id=1)        # Battle Stance, Arms skill
    assert 20572 in auto_learned_spells(DBC, race=2, class_id=3)       # orc Blood Fury (warrior/hunter/rogue/DK)
    assert 20572 not in auto_learned_spells(DBC, race=1, class_id=3)
    assert 26297 in auto_learned_spells(DBC, race=8, class_id=5)       # troll Berserking
    assert 33697 not in auto_learned_spells(DBC, race=2, class_id=9)   # shaman-only Blood Fury variant
    assert 33702 in auto_learned_spells(DBC, race=2, class_id=9)       # the orc warlock's Blood Fury
    assert 93402 not in auto_learned_spells(DBC, race=4, class_id=11)  # Sunfire: AcquireMethod 0


def test_class_trainers_are_found_by_taught_spells_not_subname():
    classes = trainer_classes(TRAINERS, DBC)["classes"]
    assert classes[55] == 6  # Death Knight trainers (e.g. 28471) have an empty subname
    assert {classes[39], classes[3], classes[16], classes[124]} == {11, 5, 1, 7}
    assert 46 not in classes  # riding trainer teaches no class spells
    assert native_baseline(6, 1, DBC, spell_learn_map(DBC), TRAINERS)
    assert trainers_sha256(TRAINERS) and len(trainers_sha256(TRAINERS)) == 64


def test_disc_active_priest_keeps_holy_word_serenity(catalog):
    result = spells(catalog, ["discipline_priest", "holy_priest"], "discipline_priest")
    assert 88684 in result["known_spell_ids"] and 88684 not in result["inactive_only_spell_ids"]


def test_fury_active_warrior_keeps_battle_stance(catalog):
    result = spells(catalog, ["arms_warrior", "fury_warrior"], "fury_warrior")
    assert 2457 in result["known_spell_ids"] and 2457 not in result["inactive_only_spell_ids"]


def test_blood_unholy_death_knight_builds_without_a_trainer_subname(catalog):
    blood = spells(catalog, ["blood_death_knight", "unholy_death_knight"], "blood_death_knight")
    unholy = spells(catalog, ["blood_death_knight", "unholy_death_knight"], "unholy_death_knight")
    for result in (blood, unholy):
        assert result["inactive_only_spell_ids"]
        assert not set(result["known_spell_ids"]) & set(result["inactive_only_spell_ids"])
        assert {63644, 63645} <= set(result["known_spell_ids"])
    baseline = native_baseline(6, 1, DBC, spell_learn_map(DBC), TRAINERS)
    assert not set(blood["inactive_only_spell_ids"]) & baseline


@pytest.mark.parametrize("specs,active,race,racial", [
    (["marksmanship_hunter", "survival_hunter"], "marksmanship_hunter", 2, 20572),  # orc Blood Fury
    (["discipline_priest", "shadow_priest"], "discipline_priest", 8, 26297),       # troll Berserking
])
def test_racials_of_the_inactive_spec_profile_stay_known(catalog, specs, active, race, racial):
    result = spells(catalog, specs, active, race)
    assert racial in result["known_spell_ids"] and racial not in result["inactive_only_spell_ids"]


def test_a_racial_of_another_class_is_not_native(catalog):
    # The Demonology profile lists 33697, the shaman variant of Blood Fury; an orc
    # warlock natively learns 33702, so 33697 stays out while Demonology is inactive.
    result = spells(catalog, ["affliction_warlock", "demonology_warlock"], "affliction_warlock", race=2)
    assert 33697 in result["inactive_only_spell_ids"] and 33697 not in result["known_spell_ids"]


def test_mangle_bear_and_sunfire_stay_excluded(catalog):
    balance = spells(catalog, ["balance_druid", "feral_druid_tank"], "balance_druid")
    feral = spells(catalog, ["balance_druid", "feral_druid_tank"], "feral_druid_tank")
    assert 33878 in balance["inactive_only_spell_ids"] and 33878 not in balance["known_spell_ids"]
    assert 93402 in feral["inactive_only_spell_ids"] and 93402 not in feral["known_spell_ids"]
    assert {6807, 779} <= set(balance["known_spell_ids"])  # trainable Maul and Swipe (Bear)


def test_missing_trainer_data_fails_closed(catalog, tmp_path):
    empty = tmp_path / "trainers.jsonl"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(LoadoutSpellError, match="class_trainer_baseline_missing:11"):
        loadout_known_spells(loadout_bot(catalog, ["balance_druid", "feral_druid_tank"], "balance_druid"),
                             DBC, trainers_path=empty)
