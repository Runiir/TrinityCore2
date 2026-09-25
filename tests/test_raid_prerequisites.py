"""Tests for experiments/configs/raid_prerequisites and their Python reader.

Every file is checked against the native instance script it describes (header,
script name, map id, boss indices and entries), and against
DungeonEncounter.dbc when the extracted client data is present.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import struct

import pytest

from tools.raid_program import raid_prerequisites as rp

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src/server/scripts"
DUNGEON_ENCOUNTER_DBC = ROOT / "data/dbc/enUS/DungeonEncounter.dbc"
DIFFICULTY_IDS = {"10n": 0, "25n": 1, "10h": 2, "25h": 3}

# raid key -> (instance script, script header)
NATIVE_SCRIPTS = {
    "blackwing_descent": ("EasternKingdoms/BlackrockMountain/BlackwingDescent/instance_blackwing_descent.cpp",
                          "EasternKingdoms/BlackrockMountain/BlackwingDescent/blackwing_descent.h"),
    "bastion_of_twilight": ("EasternKingdoms/BastionOfTwilight/instance_bastion_of_twilight.cpp",
                            "EasternKingdoms/BastionOfTwilight/bastion_of_twilight.h"),
    "throne_of_the_four_winds": ("Kalimdor/ThroneOfTheFourWinds/instance_throne_of_the_four_winds.cpp",
                                 "Kalimdor/ThroneOfTheFourWinds/throne_of_the_four_winds.h"),
    "firelands": ("Kalimdor/Firelands/instance_firelands.cpp", "Kalimdor/Firelands/firelands.h"),
    "dragon_soul": ("Kalimdor/CavernsOfTime/DragonSoul/instance_dragon_soul.cpp",
                    "Kalimdor/CavernsOfTime/DragonSoul/dragon_soul.h"),
    "baradin_hold": ("EasternKingdoms/BaradinHold/instance_baradin_hold.cpp", "EasternKingdoms/BaradinHold/baradin_hold.h"),
}


def _bwd() -> dict:
    return rp.load("blackwing_descent")


def test_every_file_validates_and_matches_its_file_name() -> None:
    docs = rp.load_all()
    assert set(docs) == set(NATIVE_SCRIPTS)
    for key, doc in docs.items():
        assert doc["raid"] == key
        assert rp.validate(doc) == ""


@pytest.mark.parametrize("raid", sorted(NATIVE_SCRIPTS))
def test_file_matches_the_native_instance_script(raid: str) -> None:
    doc = rp.load(raid)
    instance_source = (SCRIPTS / NATIVE_SCRIPTS[raid][0]).read_text()
    header_source = (SCRIPTS / NATIVE_SCRIPTS[raid][1]).read_text()
    header = re.search(r'DataHeader\s*=\s*"([^"]+)"', header_source)
    assert header and header.group(1) == doc["script_header"]
    script_name = re.search(r'#define\s+\w+ScriptName\s+"([^"]+)"', header_source)
    assert script_name and script_name.group(1) == doc["script_name"]
    map_id = re.search(r"InstanceMapScript\(\w+ScriptName,\s*(\d+)\)", instance_source)
    assert map_id and int(map_id.group(1)) == doc["map_id"]
    counts = {name: int(value) for name, value in re.findall(r"uint32 const (EncounterCount\w*)\s*=\s*(\d+);", header_source)}
    for difficulty, count in doc["encounter_count"].items():
        if "EncounterCount" in counts:
            assert count == counts["EncounterCount"], difficulty
        else:
            heroic = difficulty.endswith("h")
            assert count == counts["EncounterCountHeroic" if heroic else "EncounterCountNormal"], difficulty
    data_enum = header_source.split("enum", 2)[1]
    indices = {name: int(value) for name, value in re.findall(r"(DATA_\w+)\s*=\s*(\d+)", data_enum)}
    entries = {name: int(value) for name, value in re.findall(r"(BOSS_\w+)\s*=\s*(\d+)", header_source)}
    boss_indices = sorted(value for value in indices.values() if value < max(doc["encounter_count"].values()))
    assert sorted({row["boss_index"] for row in doc["bosses"]}) == boss_indices
    for row in doc["bosses"]:
        if row["creature_entry"] is not None and raid != "dragon_soul":
            assert row["creature_entry"] in entries.values() or row["key"] == "ascendant_council", row["key"]


def test_bwd_matches_the_native_script_exactly() -> None:
    doc = _bwd()
    header = (SCRIPTS / NATIVE_SCRIPTS["blackwing_descent"][1]).read_text()
    source = (SCRIPTS / NATIVE_SCRIPTS["blackwing_descent"][0]).read_text()
    expected = {
        "magmaw": ("DATA_MAGMAW", "BOSS_MAGMAW"),
        "omnotron": ("DATA_OMNOTRON_DEFENSE_SYSTEM", "BOSS_OMNOTRON"),
        "chimaeron": ("DATA_CHIMAERON", "BOSS_CHIMAERON"),
        "atramedes": ("DATA_ATRAMEDES", "BOSS_ATRAMEDES"),
        "maloriak": ("DATA_MALORIAK", "BOSS_MALORIAK"),
        "nefarian": ("DATA_NEFARIANS_END", "BOSS_NEFARIAN"),
    }
    for key, (data_name, boss_name) in expected.items():
        row = rp.boss(doc, key)
        assert row["boss_index"] == int(re.search(rf"{data_name}\s*=\s*(\d+)", header).group(1))
        assert row["creature_entry"] == int(re.search(rf"{boss_name}\s*=\s*(\d+)", header).group(1))
    # Omnotron is the controller 42186; 42166 is Arcanotron, one of its golems.
    assert rp.boss(doc, "omnotron")["creature_entry"] == 42186
    assert re.search(r"\bNPC_ARCANOTRON\s*=\s*42166\s*,", header)
    # The inner chamber door is a PASSAGE door of both wing bosses, and of nothing else.
    door_rows = re.findall(r"\{\s*GO_INNER_CHAMBER_DOOR\s*,\s*(\w+)\s*,\s*(\w+)\s*\}", source)
    assert sorted(door_rows) == [("DATA_MAGMAW", "DOOR_TYPE_PASSAGE"), ("DATA_OMNOTRON_DEFENSE_SYSTEM", "DOOR_TYPE_PASSAGE")]
    assert re.search(r"\bGO_INNER_CHAMBER_DOOR\s*=\s*205830\s*,", header)
    assert doc["readback_doors"] == [dict(doc["readback_doors"][0], entry=205830, open_when_done=["magmaw", "omnotron"])]
    # Nefarian needs the other five (IsNefarianAvailable).
    available = re.search(r"for \(BWDDataTypes data : \{([^}]*)\}\)", source).group(1)
    listed = [name.strip() for name in available.split(",")]
    assert listed == ["DATA_MAGMAW", "DATA_OMNOTRON_DEFENSE_SYSTEM", "DATA_CHIMAERON", "DATA_ATRAMEDES", "DATA_MALORIAK"]
    assert sorted(rp.boss(doc, "nefarian")["predecessors"]) == sorted(
        {"DATA_MAGMAW": "magmaw", "DATA_OMNOTRON_DEFENSE_SYSTEM": "omnotron", "DATA_CHIMAERON": "chimaeron",
         "DATA_ATRAMEDES": "atramedes", "DATA_MALORIAK": "maloriak"}[name] for name in listed)
    # The only save extra is the raw uint8 Atramedes intro state.
    assert re.search(r"\buint8\s+_atramedesIntroState\s*;", source)
    assert re.search(r"\bdata\s*<<\s*_atramedesIntroState\s*;", source)
    assert doc["save_extras"] == [dict(doc["save_extras"][0], name="atramedes_intro_state", encoding="raw_uint8", default=0)]


@pytest.mark.parametrize(
    "target, expected",
    [
        ("magmaw", []),
        ("omnotron", []),
        ("chimaeron", ["magmaw", "omnotron"]),
        ("atramedes", ["magmaw", "omnotron"]),
        ("maloriak", ["magmaw", "omnotron"]),
        ("nefarian", ["magmaw", "omnotron", "chimaeron", "atramedes", "maloriak"]),
    ],
)
def test_bwd_shard_precompleted_sets_have_no_linear_chain(target: str, expected: list[str]) -> None:
    assert rp.precompleted_bosses(_bwd(), target, "10n") == expected


def test_seed_argument_and_plans_for_bwd_shards() -> None:
    doc = _bwd()
    maloriak = rp.precompleted_bosses(doc, "maloriak", "10n")
    assert rp.seed_argument(maloriak) == "magmaw,omnotron"
    assert rp.seed_argument([]) == "none"
    plan = rp.seed_plan(doc, "10n", maloriak)
    # Untouched BWD bosses stay TO_BE_DECIDED (5): Create() skips the base.
    assert plan["boss_states"] == [3, 3, 5, 5, 5, 5]
    assert plan["completed_encounters_mask"] == (1 << 2) | (1 << 5)
    assert plan["save_data"] == b"B W D 3 3 5 5 5 5 \x00"
    assert plan["dead_db_spawns"] == [("magmaw", 41570)]
    assert plan["summoned_entries"] == [("omnotron", entry) for entry in (42178, 42179, 42180, 42166)]
    nefarian = rp.seed_plan(doc, "10n", rp.precompleted_bosses(doc, "nefarian", "10n"))
    assert nefarian["save_data"] == b"B W D 3 3 3 3 3 5 \x03"
    assert rp.seed_plan(doc, "25h", [])["save_data"] == b"B W D 5 5 5 5 5 5 \x00"
    assert nefarian["extra_values"] == [("atramedes_intro_state", 3)]
    assert nefarian["completed_encounters_mask"] == 47


def test_seed_plan_refusals() -> None:
    doc = _bwd()
    with pytest.raises(rp.PrerequisiteError, match="bosses_done_not_predecessor_closed:maloriak:magmaw"):
        rp.seed_plan(doc, "10n", ["maloriak"])
    with pytest.raises(rp.PrerequisiteError, match="unknown_boss:onyxia"):
        rp.seed_plan(doc, "10n", ["onyxia"])
    with pytest.raises(rp.PrerequisiteError, match="boss_dead_spawns_unverified:morchok"):
        rp.seed_plan(rp.load("dragon_soul"), "10n", ["morchok"])
    bot = rp.load("bastion_of_twilight")
    with pytest.raises(rp.PrerequisiteError, match="boss_not_available_on_difficulty:sinestra"):
        rp.precompleted_bosses(bot, "sinestra", "10n")
    assert rp.precompleted_bosses(bot, "sinestra", "10h") == [
        "halfus_wyrmbreaker", "theralion_and_valiona", "ascendant_council", "chogall"]
    assert rp.seed_plan(bot, "10n", [])["boss_states"] == [0, 0, 0, 0]
    assert rp.seed_plan(bot, "10n", ["halfus_wyrmbreaker"])["save_data"] == b"B o T 3 0 0 0 "
    assert rp.seed_plan(bot, "25h", [])["boss_states"] == [0, 0, 0, 0, 0]


def test_initial_boss_state_mirrors_each_scripts_create() -> None:
    for raid, (instance_path, _header) in NATIVE_SCRIPTS.items():
        source = (SCRIPTS / instance_path).read_text()
        create = re.search(r"void Create\(\) override\s*\{(.*?)\n\s*\}", source, re.S)
        calls_base = create is None or "InstanceScript::Create();" in create.group(1)
        assert rp.load(raid)["initial_boss_state"] == ("not_started" if calls_base else "to_be_decided"), raid


def test_spawn_split_matches_the_native_scripts() -> None:
    doc = _bwd()
    source_dir = SCRIPTS / "EasternKingdoms/BlackrockMountain/BlackwingDescent"
    instance = (source_dir / "instance_blackwing_descent.cpp").read_text()
    nefarians_end = (source_dir / "boss_nefarians_end.cpp").read_text()
    omnotron = (source_dir / "boss_omnotron_defense_system.cpp").read_text()
    # Summoned by the scripts, so a DONE state alone keeps them away.
    assert re.search(r"SummonCreature\(\s*BOSS_ATRAMEDES\b", instance)
    assert re.search(r"DoSummon\(\s*BOSS_NEFARIAN\b", nefarians_end)
    assert re.search(r"SummonCreatureGroup\(\s*SUMMON_GROUP_GOLEMS\s*\)", omnotron)
    assert 41442 in rp.boss(doc, "atramedes")["summoned_entries"]
    assert 41376 in rp.boss(doc, "nefarian")["summoned_entries"]
    assert rp.boss(doc, "omnotron")["dead_db_spawn_entries"] == []
    for raid in NATIVE_SCRIPTS:
        for row in rp.load(raid)["bosses"]:
            assert not set(row["dead_db_spawn_entries"] or []) & set(row["summoned_entries"]), (raid, row["key"])


def test_other_raid_gates_follow_their_scripts() -> None:
    assert rp.precompleted_bosses(rp.load("throne_of_the_four_winds"), "alakir", "10n") == ["conclave_of_wind"]
    assert rp.precompleted_bosses(rp.load("firelands"), "ragnaros", "25n") == ["majordomo_staghelm"]
    assert rp.precompleted_bosses(rp.load("firelands"), "baleroc", "10n") == []
    assert rp.precompleted_bosses(rp.load("baradin_hold"), "alizabal", "10n") == []


@pytest.mark.parametrize(
    "mutate, failure",
    [
        (lambda doc: doc["bosses"][0].__setitem__("predecessors", ["nefarian"]), "predecessor_cycle:magmaw"),
        (lambda doc: doc["bosses"][2].__setitem__("predecessors", ["onyxia"]), "invalid_predecessor:chimaeron:onyxia"),
        (lambda doc: doc["bosses"][5].__setitem__("boss_index", 4), "duplicate_boss_index:nefarian"),
        (lambda doc: doc["bosses"].pop(), "missing_boss_index:5:10n"),
        (lambda doc: doc["bosses"][3]["extra_save_values"].__setitem__("atramedes_intro_state", 32),
         "extra_save_value_not_round_trip:atramedes:atramedes_intro_state"),
        (lambda doc: doc["bosses"][3]["extra_save_values"].__setitem__("unknown", 1),
         "unknown_extra_save_value:atramedes:unknown"),
        (lambda doc: doc["bosses"][0].__setitem__("difficulties", ["10h", "25h"]), "missing_boss_index:0:10n"),
        (lambda doc: doc.__setitem__("encounter_count", {"10n": 6}), "encounter_count_difficulty_mismatch"),
        (lambda doc: doc["readback_doors"][0].__setitem__("open_when_done", ["onyxia"]),
         "invalid_readback_door_boss:onyxia"),
        (lambda doc: doc["bosses"][0].__setitem__("dungeon_encounter_bit", 40), "invalid_dungeon_encounter_bit:magmaw"),
        (lambda doc: doc["bosses"][0].__setitem__("key", "Magmaw"), "invalid_boss_key:Magmaw"),
        (lambda doc: doc.__setitem__("initial_boss_state", "done"), "invalid_initial_boss_state"),
        (lambda doc: doc["bosses"][0].pop("summoned_entries"), "summoned_entries_required:magmaw"),
        (lambda doc: doc["bosses"][0].__setitem__("dead_db_spawn_entries", [0]), "invalid_dead_db_spawn_entry:magmaw"),
        (lambda doc: doc["bosses"][3]["summoned_entries"].append(41570),
         "entry_both_dead_spawn_and_summoned:41570"),
    ],
)
def test_validation_rejects_broken_graphs(mutate, failure: str) -> None:
    doc = copy.deepcopy(_bwd())
    mutate(doc)
    assert rp.validate(doc) == failure


def _dungeon_encounters() -> dict[int, tuple[int, int, int, str]]:
    data = DUNGEON_ENCOUNTER_DBC.read_bytes()
    magic, records, fields, record_size, _ = struct.unpack("<4s4I", data[:20])
    assert magic == b"WDBC" and fields == 8
    strings = data[20 + records * record_size:]
    rows = {}
    for index in range(records):
        row = struct.unpack("<8i", data[20 + index * record_size:20 + (index + 1) * record_size])
        name = strings[row[5]:strings.index(b"\0", row[5])].decode()
        rows[row[0]] = (row[1], row[2], row[4], name)  # map, difficulty, bit, name
    return rows


@pytest.mark.skipif(not DUNGEON_ENCOUNTER_DBC.is_file(), reason="extracted client DBC not present")
@pytest.mark.parametrize("raid", sorted(NATIVE_SCRIPTS))
def test_encounter_ids_and_bits_match_dungeon_encounter_dbc(raid: str) -> None:
    doc = rp.load(raid)
    encounters = _dungeon_encounters()
    for row in doc["bosses"]:
        for difficulty in rp.boss_difficulties(doc, row):
            encounter_id = row.get("dungeon_encounter_id_by_difficulty", {}).get(difficulty, row["dungeon_encounter_id"])
            map_id, dbc_difficulty, bit, _name = encounters[encounter_id]
            assert map_id == doc["map_id"], (row["key"], difficulty)
            assert dbc_difficulty in (-1, DIFFICULTY_IDS[difficulty]), (row["key"], difficulty)
            assert bit == row["dungeon_encounter_bit"], (row["key"], difficulty)
    # Every DBC encounter of the map is described by exactly one boss.
    described = {row.get("dungeon_encounter_id") for row in doc["bosses"]}
    for row in doc["bosses"]:
        described.update(row.get("dungeon_encounter_id_by_difficulty", {}).values())
    assert {key for key, value in encounters.items() if value[0] == doc["map_id"]} <= described


def test_cli_prints_the_seed_argument(capsys) -> None:
    assert rp.main(["closure", "blackwing_descent", "maloriak"]) == 0
    result = json.loads(capsys.readouterr().out)
    assert result["seed_argument"] == "magmaw,omnotron" and result["completed_encounters_mask"] == 36
    assert rp.main(["closure", "blackwing_descent", "onyxia"]) == 1
    assert json.loads(capsys.readouterr().out)["failure_reason"] == "unknown_boss:onyxia"
    assert rp.main(["validate"]) == 0
