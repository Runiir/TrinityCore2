"""Native item-use restrictions of phase gear (tools.bot_ml.phase_gear_equip_restrictions).

Loading an inventory equips each item through Player::CanEquipItem ->
Player::CanUseItem, which refuses an item of the other faction, outside the
class/race masks, or without the skill, spell, level, holiday or reputation it
needs. The round-3 Blood DK (Human, Alliance) wore both faction versions of
Stump of Time; the Horde one (62465) never equips.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.bot_ml.phase_gear_equip_restrictions import (
    REPUTATION_POLICY_EXCLUDED,
    CharacterView,
    EquipRestrictionError,
    character_view,
    check_reputation_policy,
    item_use_failures,
    load_race_teams,
    restricted_items,
)
from tools.bot_ml.phase_gear_extract import DEFAULT_EXTRACT_DIR, HOTFIX_COLUMNS, item_facts, load_phase_extract
from tools.bot_ml.phase_gear_profiles import load_phase_config

ROOT = Path(__file__).resolve().parents[1]
DBC = ROOT / "data/dbc/enUS"
T11 = ROOT / "experiments/configs/raid_gear_phases/cata_t11_v1.json"
STUMP_ALLIANCE, STUMP_HORDE = 62470, 62465
SIGNET_OF_THE_ELDER_COUNCIL = 62362
HUMAN_DK = CharacterView(race=1, class_id=6, level=85, team="alliance")
ORC_HUNTER = CharacterView(race=2, class_id=3, level=85, team="horde")


def _dbc():
    if not (DBC / "Item-sparse.db2").is_file() or not (DBC / "ChrRaces.dbc").is_file():
        pytest.skip("client DBCs not extracted")


def _open() -> dict:
    return {"flags2": 0, "allowable_class": -1, "allowable_race": -1, "required_level": 85, "required_skill": 0,
            "required_skill_rank": 0, "required_spell": 0, "required_reputation_faction": 0, "required_reputation_rank": 0,
            "holiday_id": 0}


def test_the_teams_follow_chr_races_base_language():
    _dbc()
    teams = load_race_teams(DBC)
    assert {race: teams[race] for race in (1, 3, 4, 7, 11, 22)} == dict.fromkeys((1, 3, 4, 7, 11, 22), "alliance")
    assert {race: teams[race] for race in (2, 5, 6, 8, 9, 10)} == dict.fromkeys((2, 5, 6, 8, 9, 10), "horde")
    assert character_view({"race": 2, "class": 3}, teams).team == "horde"
    with pytest.raises(EquipRestrictionError, match="race_unknown"):
        character_view({"race": 99, "class": 3}, teams)


def test_the_use_checks_mirror_player_can_use_item():
    assert item_use_failures(_open(), HUMAN_DK) == []
    assert item_use_failures({**_open(), "flags2": 0x2001}, HUMAN_DK) == ["faction_restricted:horde"]
    assert item_use_failures({**_open(), "flags2": 0x2001}, ORC_HUNTER) == []
    assert item_use_failures({**_open(), "flags2": 0x2002}, ORC_HUNTER) == ["faction_restricted:alliance"]
    assert item_use_failures({**_open(), "allowable_class": 32}, HUMAN_DK) == [], "death knight class mask"
    assert item_use_failures({**_open(), "allowable_class": 4}, HUMAN_DK) == ["class_restricted"]
    assert item_use_failures({**_open(), "allowable_class": 0}, HUMAN_DK) == ["class_restricted"], "a zero mask refuses all"
    assert item_use_failures({**_open(), "allowable_race": 2}, HUMAN_DK) == ["race_restricted"]
    assert item_use_failures({**_open(), "allowable_race": 2147483647}, HUMAN_DK) == []
    skilled = {**_open(), "required_skill": 202, "required_skill_rank": 475}
    assert item_use_failures(skilled, HUMAN_DK) == ["skill_required:202:475"]
    assert item_use_failures(skilled, CharacterView(1, 6, 85, "alliance", skills={202: 450})) == ["skill_required:202:475"]
    assert item_use_failures(skilled, CharacterView(1, 6, 85, "alliance", skills={202: 525})) == []
    assert item_use_failures({**_open(), "required_level": 86}, HUMAN_DK) == ["level_required"]
    assert item_use_failures({**_open(), "required_spell": 12345}, HUMAN_DK) == ["spell_required:12345"]
    assert item_use_failures({**_open(), "holiday_id": 181}, HUMAN_DK) == ["holiday_item:181"]
    revered = {**_open(), "required_reputation_faction": 1135, "required_reputation_rank": 7}
    assert item_use_failures(revered, HUMAN_DK) == ["reputation_required:1135:7"], "no provisioned standing"
    assert item_use_failures(revered, CharacterView(1, 6, 85, "alliance", reputation_ranks={1135: 7})) == []
    assert item_use_failures(None, HUMAN_DK) == ["item_template_unknown"]
    both = restricted_items([1, 2], {1: _open(), 2: {**_open(), "flags2": 1}}, [HUMAN_DK, ORC_HUNTER])
    assert both == {2: ["race1/class6/alliance:faction_restricted:horde"]}
    with pytest.raises(EquipRestrictionError, match="characters_missing"):
        restricted_items([1], {1: _open()}, [])


def test_the_pinned_facts_carry_the_restrictions_with_hotfix_rows_over_client_rows():
    _dbc()
    client = item_facts(DBC, {"item_sparse": []})
    assert client[STUMP_ALLIANCE]["flags2"] & 0x2 and client[STUMP_HORDE]["flags2"] & 0x1
    assert (client[STUMP_ALLIANCE]["required_reputation_faction"], client[STUMP_ALLIANCE]["required_reputation_rank"]) == (1177, 7)
    assert (client[STUMP_HORDE]["required_reputation_faction"], client[STUMP_HORDE]["required_reputation_rank"]) == (1178, 7)
    assert client[SIGNET_OF_THE_ELDER_COUNCIL]["required_reputation_faction"] == 1135
    assert client[STUMP_HORDE]["allowable_class"] == -1 and client[STUMP_HORDE]["required_level"] == 85
    hotfix = {column: 0 for column in HOTFIX_COLUMNS["item_sparse"]}
    hotfix.update(ID=STUMP_HORDE, Flags2=0x2002, AllowableClass=-1, AllowableRace=-1, RequiredReputationFaction=0)
    merged = item_facts(DBC, {"item_sparse": [hotfix]})
    assert merged[STUMP_HORDE]["flags2"] == 0x2002 and merged[STUMP_HORDE]["required_reputation_faction"] == 0
    assert item_use_failures(merged[STUMP_HORDE], HUMAN_DK) == []
    assert item_use_failures(client[STUMP_HORDE], HUMAN_DK) == ["faction_restricted:horde", "reputation_required:1178:7"]


def test_the_pinned_extract_holds_the_restriction_columns():
    _dbc()
    config = load_phase_config(T11)
    if not (DEFAULT_EXTRACT_DIR / "cata_t11.json").is_file():
        pytest.skip("raid_phase_gear_db_extract not hydrated")
    hotfix = load_phase_extract(DEFAULT_EXTRACT_DIR, config, DBC)["hotfix"]
    assert {"Flags2", "AllowableRace", "AllowableClass", "RequiredSkillRank", "RequiredSpell", "RequiredReputationFaction",
            "RequiredReputationRank", "HolidayID", "RequiredLevel", "SpellID1", "SpellTrigger5"} <= set(hotfix["item_sparse"][0])


def test_the_phase_config_declares_the_reputation_policy():
    config = json.loads(T11.read_text(encoding="utf-8"))
    assert config["item_policy"]["required_reputation"] == REPUTATION_POLICY_EXCLUDED
    check_reputation_policy(config)
    config["item_policy"]["required_reputation"] = "granted"
    with pytest.raises(EquipRestrictionError, match="required_reputation_policy_unsupported"):
        check_reputation_policy(config)
