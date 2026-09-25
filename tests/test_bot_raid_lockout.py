"""Header-only g++ tests for the seeded raid lockout planner (package A).

Covers BotRaidLockoutPlan.h (request parsing, predecessor closure, the exact
InstanceScript save bytes including the raw extra byte, load-side parsing) and
BotRaidLockoutDefinitionJson.h, whose output on the real prerequisite files is
compared with tools/raid_program/raid_prerequisites.py.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest

from tools.raid_program import raid_prerequisites

ROOT = Path(__file__).resolve().parents[1]
INCLUDES = ["src/server/game"]
SYSTEM_INCLUDES = ["dep/rapidjson"]


def _compile_and_run(tmp_path: Path, source: str, args: list[str] | None = None) -> str:
    program = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    program.write_text(source)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-DRAPIDJSON_HAS_STDSTRING"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    for include in SYSTEM_INCLUDES:
        command += ["-isystem", str(ROOT / include)]
    subprocess.run(command + [str(program), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary), *(args or [])], check=True, cwd=ROOT, capture_output=True, text=True)
    return result.stdout


UNIT_PROGRAM = r'''
#include "Bots/BotRaidLockoutPlan.h"
#include <cstdio>
#include <string>
#include <vector>

using namespace BotRaidLockout;

static int failures = 0;
#define EXPECT(cond) do { if (!(cond)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #cond); ++failures; } } while (0)

static RaidDefinition Bwd()
{
    RaidDefinition def;
    def.Schema = SchemaVersion;
    def.Raid = "blackwing_descent";
    def.MapId = 669;
    def.ScriptName = "instance_blackwing_descent";
    def.ScriptHeader = "BWD";
    def.Difficulties = { 0, 1, 2, 3 };
    def.EncounterCount = { { 0, 6 }, { 1, 6 }, { 2, 6 }, { 3, 6 } };
    auto boss = [](std::string key, uint32_t index, int32_t bit, std::vector<std::string> predecessors,
        std::vector<uint32_t> dead, std::vector<uint32_t> summoned)
    {
        BossDefinition row;
        row.Key = key;
        row.BossIndex = index;
        row.DungeonEncounterId = 1000 + index;
        row.DungeonEncounterBit = bit;
        row.Predecessors = predecessors;
        row.DeadDbSpawnEntriesKnown = true;
        row.DeadDbSpawnEntries = dead;
        row.SummonedEntries = summoned;
        return row;
    };
    def.Bosses = {
        boss("magmaw", 0, 2, {}, { 41570 }, {}),
        boss("omnotron", 1, 5, {}, {}, { 42178, 42179, 42180, 42166 }),
        boss("chimaeron", 2, 1, { "magmaw", "omnotron" }, { 43296 }, {}),
        boss("atramedes", 3, 0, { "magmaw", "omnotron" }, {}, { 41442 }),
        boss("maloriak", 4, 3, { "magmaw", "omnotron" }, { 41378 }, {}),
        boss("nefarian", 5, 4, { "magmaw", "omnotron", "chimaeron", "atramedes", "maloriak" }, {}, { 41376, 41270 }),
    };
    def.Bosses[3].ExtraSaveValues["atramedes_intro_state"] = 3;
    def.SaveExtras = { { "atramedes_intro_state", SaveExtraEncoding::RawUint8, 0 } };
    def.ReadbackDoors = { { 205830, { "magmaw", "omnotron" } } };
    return def;
}

int main()
{
    uint8_t difficulty = 9;
    EXPECT(ParseDifficulty("10n", difficulty) && difficulty == 0);
    EXPECT(ParseDifficulty("25H", difficulty) && difficulty == 3);
    EXPECT(ParseDifficulty("2", difficulty) && difficulty == 2);
    EXPECT(!ParseDifficulty("40n", difficulty));
    EXPECT(DifficultyToken(1) == "25n" && DifficultyToken(7).empty());

    EXPECT(IsValidCohortId("blackwing_descent_10n_maloriak_c1"));
    EXPECT(!IsValidCohortId("") && !IsValidCohortId("a b") && !IsValidCohortId(std::string(65, 'a')));

    std::vector<std::string> keys;
    std::string failure;
    EXPECT(ParseBossList("none", keys, failure) && keys.empty());
    EXPECT(ParseBossList("magmaw,omnotron", keys, failure) && keys.size() == 2 && keys[1] == "omnotron");
    EXPECT(!ParseBossList("magmaw,,omnotron", keys, failure) && failure == "invalid_boss_key:");
    EXPECT(!ParseBossList("magmaw,", keys, failure));
    EXPECT(!ParseBossList("magmaw,magmaw", keys, failure) && failure == "duplicate_boss:magmaw");
    EXPECT(!ParseBossList("", keys, failure) && failure == "boss_list_required");
    EXPECT(!ParseBossList("Magmaw", keys, failure));

    RaidDefinition const def = Bwd();
    std::vector<uint8_t> states;
    std::vector<std::pair<std::string, uint32_t>> extras;
    EXPECT(ValidateDefinition(def).empty());
    std::set<std::string> const closure = PredecessorClosure(def, "nefarian");
    EXPECT(closure.size() == 5 && !closure.count("nefarian"));
    EXPECT(PredecessorClosure(def, "maloriak") == (std::set<std::string>{ "magmaw", "omnotron" }));

    // Maloriak shard: Magmaw and Omnotron done, intro byte NOT_STARTED (NUL).
    SeedPlan plan;
    EXPECT(BuildSeedPlan(def, 0, { "omnotron", "magmaw" }, plan).empty());
    EXPECT((plan.BossStates == std::vector<uint8_t>{ 3, 3, 0, 0, 0, 0 }));
    EXPECT((plan.BossesDone == std::vector<std::string>{ "magmaw", "omnotron" }));
    EXPECT(plan.CompletedEncounterMask == ((1u << 2) | (1u << 5)));
    EXPECT(plan.SaveData == std::string("B W D 3 3 0 0 0 0 \0", 19));
    EXPECT(ToHex(plan.SaveData) == "42205720442033203320302030203020302000");
    EXPECT((plan.DeadDbSpawns == std::vector<std::pair<std::string, uint32_t>>{ { "magmaw", 41570 } }));
    EXPECT((plan.SummonedEntries.size() == 4 && plan.SummonedEntries[0].first == "omnotron"));

    // Dead spawns against the map's creature spawns (spawn mask bit = difficulty).
    std::vector<SpawnFact> spawns = {
        { 900, 41570, 0x0F, false },  // Magmaw on every difficulty
        { 901, 41570, 0x0C, false },  // a heroic-only copy
        { 950, 42178, 0x0F, true },   // a golem inside a manual spawn group
        { 990, 12345, 0x0F, false },
    };
    std::vector<RespawnRow> rows;
    EXPECT(ResolveDeadSpawns(plan, spawns, rows).empty());
    EXPECT(rows.size() == 1 && rows[0].SpawnId == 900 && rows[0].Entry == 41570);
    SeedPlan heroic;
    EXPECT(BuildSeedPlan(def, 2, { "magmaw", "omnotron" }, heroic).empty());
    EXPECT(ResolveDeadSpawns(heroic, spawns, rows).empty() && rows.size() == 2 && rows[1].SpawnId == 901);
    std::vector<SpawnFact> const noMagmaw = { { 990, 12345, 0x0F, false } };
    EXPECT(ResolveDeadSpawns(plan, noMagmaw, rows) == "dead_spawn_missing:magmaw:41570" && rows.empty());
    std::vector<SpawnFact> const wrongDifficulty = { { 901, 41570, 0x0C, false } };
    EXPECT(ResolveDeadSpawns(plan, wrongDifficulty, rows) == "dead_spawn_missing:magmaw:41570");
    std::vector<SpawnFact> ungatedGolem = spawns;
    ungatedGolem.push_back({ 951, 42166, 0x01, false });
    EXPECT(ResolveDeadSpawns(plan, ungatedGolem, rows) == "summoned_entry_has_database_spawn:omnotron:42166");
    ungatedGolem.back().SpawnMask = 0x02; // not spawned on 10n
    EXPECT(ResolveDeadSpawns(plan, ungatedGolem, rows).empty());

    // Nefarian shard: Atramedes done forces the intro byte to DONE (0x03).
    EXPECT(BuildSeedPlan(def, 0, { "magmaw", "omnotron", "chimaeron", "atramedes", "maloriak" }, plan).empty());
    EXPECT(plan.SaveData == std::string("B W D 3 3 3 3 3 0 \x03", 19));
    EXPECT(plan.CompletedEncounterMask == 47u);
    EXPECT(plan.ExtraValues.size() == 1 && plan.ExtraValues[0].second == 3);

    // A script whose Create() skips the base keeps untouched bosses
    // TO_BE_DECIDED; the native save writes 5 and its load skips it.
    RaidDefinition skipsBase = def;
    skipsBase.InitialBossState = StateToBeDecided;
    EXPECT(BuildSeedPlan(skipsBase, 0, { "magmaw", "omnotron" }, plan).empty());
    EXPECT(plan.SaveData == std::string("B W D 3 3 5 5 5 5 \0", 19));
    EXPECT(ParseSaveData(plan.SaveData, skipsBase, 6, states, extras));
    EXPECT((states == std::vector<uint8_t>{ 3, 3, 5, 5, 5, 5 }));
    RaidDefinition badInitial = def;
    badInitial.InitialBossState = StateDone;
    EXPECT(ValidateDefinition(badInitial) == "invalid_initial_boss_state");

    // Fresh-equivalent lockout.
    EXPECT(BuildSeedPlan(def, 2, {}, plan).empty());
    EXPECT(plan.SaveData == std::string("B W D 0 0 0 0 0 0 \0", 19) && plan.CompletedEncounterMask == 0);

    // Refusals.
    EXPECT(BuildSeedPlan(def, 0, { "maloriak" }, plan) == "bosses_done_not_predecessor_closed:maloriak:magmaw");
    EXPECT(BuildSeedPlan(def, 0, { "onyxia" }, plan) == "unknown_boss:onyxia");
    EXPECT(BuildSeedPlan(def, 0, { "magmaw", "magmaw" }, plan) == "duplicate_boss:magmaw");
    RaidDefinition unverified = def;
    unverified.Bosses[0].DeadDbSpawnEntriesKnown = false;
    EXPECT(BuildSeedPlan(unverified, 0, { "magmaw" }, plan) == "boss_dead_spawns_unverified:magmaw");
    RaidDefinition noBit = def;
    noBit.Bosses[1].DungeonEncounterBit = -1;
    EXPECT(BuildSeedPlan(noBit, 0, { "omnotron" }, plan) == "boss_encounter_bit_unknown:omnotron");
    RaidDefinition normalOnly = def;
    normalOnly.Difficulties = { 0 };
    normalOnly.EncounterCount = { { 0, 6 } };
    EXPECT(BuildSeedPlan(normalOnly, 3, {}, plan) == "difficulty_not_supported:25h");
    RaidDefinition conflict = def;
    conflict.Bosses[4].ExtraSaveValues["atramedes_intro_state"] = 1;
    EXPECT(BuildSeedPlan(conflict, 0, { "magmaw", "omnotron", "atramedes", "maloriak" }, plan)
        == "extra_save_value_conflict:atramedes_intro_state");

    // Definition validation.
    RaidDefinition cycle = def;
    cycle.Bosses[0].Predecessors = { "nefarian" };
    EXPECT(ValidateDefinition(cycle).rfind("predecessor_cycle:", 0) == 0);
    RaidDefinition missing = def;
    missing.Bosses.pop_back();
    EXPECT(ValidateDefinition(missing) == "missing_boss_index:5:10n");
    RaidDefinition duplicateIndex = def;
    duplicateIndex.Bosses[5].BossIndex = 4;
    EXPECT(ValidateDefinition(duplicateIndex) == "duplicate_boss_index:nefarian");
    RaidDefinition whitespace = def;
    whitespace.Bosses[3].ExtraSaveValues["atramedes_intro_state"] = 32;
    EXPECT(ValidateDefinition(whitespace) == "extra_save_value_not_round_trip:atramedes:atramedes_intro_state");
    RaidDefinition badPredecessor = def;
    badPredecessor.Bosses[2].Predecessors = { "onyxia" };
    EXPECT(ValidateDefinition(badPredecessor) == "invalid_predecessor:chimaeron:onyxia");
    RaidDefinition heroicOnly = def;
    heroicOnly.Bosses[0].Difficulties = { 2, 3 };
    EXPECT(ValidateDefinition(heroicOnly) == "missing_boss_index:0:10n");
    RaidDefinition bothLists = def;
    bothLists.Bosses[5].SummonedEntries.push_back(41378);
    EXPECT(ValidateDefinition(bothLists) == "entry_both_dead_spawn_and_summoned:41378");
    RaidDefinition zeroSummon = def;
    zeroSummon.Bosses[3].SummonedEntries = { 0 };
    EXPECT(ValidateDefinition(zeroSummon) == "invalid_summoned_entry:atramedes");
    RaidDefinition badDoor = def;
    badDoor.ReadbackDoors[0].OpenWhenDone = { "onyxia" };
    EXPECT(ValidateDefinition(badDoor) == "invalid_readback_door_boss:onyxia");

    // Load side mirrors InstanceScript::Load on data.c_str().
    EXPECT(ParseSaveData(std::string("B W D 3 3 0 0 0 0 \0", 19), def, 6, states, extras));
    EXPECT((states == std::vector<uint8_t>{ 3, 3, 0, 0, 0, 0 }) && extras.size() == 1 && extras[0].second == 0);
    EXPECT(ParseSaveData(std::string("B W D 3 3 3 3 3 0 \x03", 19), def, 6, states, extras));
    EXPECT(extras[0].second == 3 && states[4] == 3);
    EXPECT(ParseSaveData("B W D 1 2 4 5 3 0 ", def, 6, states, extras));
    EXPECT((states == std::vector<uint8_t>{ 0, 0, 0, 5, 3, 0 }));
    EXPECT(!ParseSaveData("B o T 0 0 0 0 ", def, 6, states, extras));
    EXPECT(!ParseSaveData("B W D 3 3 ", def, 6, states, extras));

    // Readback comparison: the Maloriak lockout as BWD saves it (untouched
    // bosses TO_BE_DECIDED).
    RaidDefinition tbd = def;
    tbd.InitialBossState = StateToBeDecided;
    SeedPlan seeded;
    EXPECT(BuildSeedPlan(tbd, 0, { "magmaw", "omnotron" }, seeded).empty());
    LockoutExpectation expected;
    expected.ScriptHeader = "BWD";
    expected.EncounterCount = 6;
    expected.States = seeded.BossStates;
    expected.BossesDone = seeded.BossesDone;
    for (BossDefinition const& row : def.Bosses)
        expected.BossIndexByKey[row.Key] = row.BossIndex;
    expected.CompletedEncounterMask = seeded.CompletedEncounterMask;
    expected.SaveData = seeded.SaveData;
    expected.ExtraCount = 1;

    ReadbackComparison same = CompareReadback(expected, 6, { 3, 3, 5, 5, 5, 5 }, 36, seeded.SaveData);
    EXPECT(same.SeedMatch && same.SaveDataMatches && same.LockoutIntact && same.MaskMatches);
    // InstanceMapLoadAllGrids: a boss AI's Reset turns 5 into 0 at load.
    std::string const reset = std::string("B W D 3 3 0 5 0 0 \0", 19);
    ReadbackComparison grids = CompareReadback(expected, 6, { 3, 3, 0, 5, 0, 0 }, 36, reset);
    EXPECT(grids.SeedMatch && !grids.SaveDataMatches && grids.SaveDataEquivalent && grids.StatesEquivalent);
    // A pulled boss is not untouched.
    ReadbackComparison pulled = CompareReadback(expected, 6, { 3, 3, 1, 5, 5, 5 }, 36,
        std::string("B W D 3 3 1 5 5 5 \0", 19));
    EXPECT(!pulled.SeedMatch && !pulled.StatesEquivalent && pulled.LockoutIntact);
    // A DONE boss that was not seeded: the lockout progressed.
    ReadbackComparison progressed = CompareReadback(expected, 6, { 3, 3, 5, 5, 3, 5 }, 44,
        std::string("B W D 3 3 5 5 3 5 \0", 19));
    EXPECT(!progressed.LockoutIntact && (progressed.ExtraDone == std::vector<std::string>{ "maloriak" }));
    // A seeded boss missing, a wrong mask, different extras, a short state list.
    ReadbackComparison lost = CompareReadback(expected, 6, { 3, 5, 5, 5, 5, 5 }, 36,
        std::string("B W D 3 5 5 5 5 5 \0", 19));
    EXPECT(!lost.SeedMatch && (lost.MissingDone == std::vector<std::string>{ "omnotron" }));
    EXPECT(!CompareReadback(expected, 6, { 3, 3, 5, 5, 5, 5 }, 4, seeded.SaveData).SeedMatch);
    ReadbackComparison extraByte = CompareReadback(expected, 6, { 3, 3, 5, 5, 5, 5 }, 36,
        std::string("B W D 3 3 5 5 5 5 \x03", 19));
    EXPECT(!extraByte.SaveDataEquivalent && !extraByte.SeedMatch && extraByte.StatesEquivalent);
    EXPECT(!CompareReadback(expected, 5, { 3, 3, 5, 5, 5 }, 36, seeded.SaveData).LockoutIntact);
    EXPECT(!CompareReadback(expected, 6, { 3, 3, 5, 5, 5, 5 }, 36, "B W D 3 3 5 5 5 ").SaveDataEquivalent);

    std::vector<uint32_t> written;
    std::string rawExtras;
    EXPECT(ParseSaveDataWritten(seeded.SaveData, "BWD", 6, 1, written, rawExtras)
        && (written == std::vector<uint32_t>{ 3, 3, 5, 5, 5, 5 }) && rawExtras == std::string("\0", 1));
    EXPECT(!ParseSaveDataWritten("B o T 0 0 0 0 ", "BWD", 4, 0, written, rawExtras));
    EXPECT(!ParseSaveDataWritten("B W D 3 3 0 0 0 0 ", "BWD", 6, 1, written, rawExtras));

    // Door expectation: PASSAGE semantics over the listed bosses.
    DoorReadback const inner = def.ReadbackDoors[0];
    EXPECT(DoorExpectedOpen(inner, expected.BossIndexByKey, { 3, 3, 5, 5, 5, 5 }));
    EXPECT(!DoorExpectedOpen(inner, expected.BossIndexByKey, { 3, 0, 5, 5, 5, 5 }));
    EXPECT(!DoorExpectedOpen(inner, expected.BossIndexByKey, {}));
    EXPECT(!DoorExpectedOpen({ 205830, { "onyxia" } }, expected.BossIndexByKey, { 3, 3, 5, 5, 5, 5 }));
    EXPECT(DoorObservedState(0, 0) == "not_loaded" && DoorObservedState(1, 0) == "open"
        && DoorObservedState(1, 1) == "closed");
    EXPECT(!DoorMismatch(true, "open") && !DoorMismatch(false, "closed") && !DoorMismatch(true, "not_loaded"));
    EXPECT(DoorMismatch(true, "closed") && DoorMismatch(false, "open"));

    std::string bytes;
    EXPECT(FromHex("420003ff", bytes) && bytes == std::string("B\0\x03\xff", 4));
    EXPECT(!FromHex("4", bytes) && !FromHex("zz", bytes));
    EXPECT(JsonEscape(std::string("a\"b\\c\x01", 6)) == "a\\\"b\\\\c\\u0001");
    EXPECT(JsonStringArray({ "a", "b" }) == "[\"a\",\"b\"]" && JsonNumberArray(std::vector<uint8_t>{ 3, 0 }) == "[3,0]");
    return failures == 0 ? 0 : 1;
}
'''


def test_plan_header_builds_exact_lockouts(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, UNIT_PROGRAM)


PARITY_PROGRAM = r'''
#include "Bots/BotRaidLockoutDefinitionJson.h"
#include <cstdio>
#include <fstream>
#include <sstream>

using namespace BotRaidLockout;

static std::string PairsJson(std::vector<std::pair<std::string, uint32_t>> const& pairs)
{
    std::string json = "[";
    for (size_t index = 0; index < pairs.size(); ++index)
        json += (index ? ",[\"" : "[\"") + pairs[index].first + "\"," + std::to_string(pairs[index].second) + "]";
    return json + "]";
}

// One JSON line per file: identity, per-difficulty counts and, for every boss
// on every difficulty, the closure and the plan of its shard.
int main(int argc, char** argv)
{
    for (int index = 1; index < argc; ++index)
    {
        std::ifstream input(argv[index]);
        std::stringstream text;
        text << input.rdbuf();
        RaidDefinition def;
        std::string failure;
        if (!ParseRaidDefinitionJson(text.str(), def, failure))
        {
            std::printf("{\"file\":\"%s\",\"failure\":\"%s\"}\n", argv[index], failure.c_str());
            continue;
        }
        std::ostringstream line;
        line << "{\"raid\":\"" << def.Raid << "\",\"map_id\":" << def.MapId
             << ",\"script_header\":\"" << def.ScriptHeader << "\",\"shards\":[";
        bool first = true;
        for (uint8_t difficulty : def.Difficulties)
            for (BossDefinition const& boss : def.Bosses)
            {
                if (!BossAvailableOn(boss, difficulty))
                    continue;
                std::set<std::string> const closure = PredecessorClosure(def, boss.Key);
                std::vector<std::string> keys(closure.begin(), closure.end());
                SeedPlan plan;
                std::string const refusal = BuildSeedPlan(def, difficulty, keys, plan);
                line << (first ? "" : ",") << "{\"boss\":\"" << boss.Key << "\",\"difficulty\":\""
                     << DifficultyToken(difficulty) << "\",\"refusal\":\"" << refusal << "\""
                     << ",\"bosses_done\":" << JsonStringArray(plan.BossesDone)
                     << ",\"boss_states\":" << JsonNumberArray(plan.BossStates)
                     << ",\"mask\":" << plan.CompletedEncounterMask
                     << ",\"save_hex\":\"" << ToHex(plan.SaveData) << "\""
                     << ",\"dead\":" << PairsJson(plan.DeadDbSpawns)
                     << ",\"summoned\":" << PairsJson(plan.SummonedEntries) << "}";
                first = false;
            }
        line << "]}";
        std::printf("%s\n", line.str().c_str());
    }
    return 0;
}
'''


def _python_shards(doc: dict) -> list[dict]:
    shards = []
    for difficulty in doc["difficulties"]:
        for row in doc["bosses"]:
            if difficulty not in raid_prerequisites.boss_difficulties(doc, row):
                continue
            done = raid_prerequisites.predecessor_closure(doc, row["key"])
            try:
                plan = raid_prerequisites.seed_plan(doc, difficulty, done)
                refusal = ""
            except raid_prerequisites.PrerequisiteError as error:
                plan = {"bosses_done": [], "boss_states": [], "completed_encounters_mask": 0,
                        "save_data": b"", "dead_db_spawns": [], "summoned_entries": []}
                refusal = str(error)
            shards.append({
                "boss": row["key"],
                "difficulty": difficulty,
                "refusal": refusal,
                "bosses_done": plan["bosses_done"],
                "boss_states": plan["boss_states"],
                "mask": plan["completed_encounters_mask"],
                "save_hex": plan["save_data"].hex().upper(),
                "dead": [list(pair) for pair in plan["dead_db_spawns"]],
                "summoned": [list(pair) for pair in plan["summoned_entries"]],
            })
    return shards


def test_cpp_reader_matches_python_reader_on_every_raid_file(tmp_path: Path) -> None:
    files = sorted(raid_prerequisites.PREREQUISITES_DIR.glob("*.json"))
    assert files, "no prerequisite files"
    output = _compile_and_run(tmp_path, PARITY_PROGRAM, [str(path) for path in files])
    lines = [json.loads(line) for line in output.splitlines()]
    assert len(lines) == len(files)
    for path, line in zip(files, lines):
        assert "failure" not in line, (path.name, line)
        doc = raid_prerequisites.load(path.stem)
        assert line["raid"] == doc["raid"] and line["map_id"] == doc["map_id"]
        assert line["script_header"] == doc["script_header"]
        assert line["shards"] == _python_shards(doc), path.name


@pytest.mark.parametrize(
    "mutation, expected",
    [
        (lambda doc: doc.__setitem__("schema", "raid_prerequisites_v0"), "schema_mismatch"),
        (lambda doc: doc["bosses"][0].__setitem__("predecessors", ["nefarian"]), "predecessor_cycle:"),
        (lambda doc: doc["bosses"].pop(), "missing_boss_index:5:10n"),
        (lambda doc: doc["bosses"][3]["extra_save_values"].__setitem__("atramedes_intro_state", 9), "extra_save_value_not_round_trip:atramedes:atramedes_intro_state"),
        (lambda doc: doc["bosses"][2].__setitem__("predecessors", ["onyxia"]), "invalid_predecessor:chimaeron:onyxia"),
        (lambda doc: doc["bosses"][1].pop("dead_db_spawn_entries"), "dead_db_spawn_entries_required:omnotron"),
        (lambda doc: doc["bosses"][1].pop("summoned_entries"), "summoned_entries_required:omnotron"),
        (lambda doc: doc["bosses"][5]["summoned_entries"].append(41378), "entry_both_dead_spawn_and_summoned:41378"),
        (lambda doc: doc["save_extras"][0].__setitem__("encoding", "uint32"), "invalid_save_extra"),
        (lambda doc: doc.__setitem__("initial_boss_state", "done"), "invalid_initial_boss_state"),
    ],
)
def test_cpp_and_python_reject_the_same_broken_files(tmp_path: Path, mutation, expected: str) -> None:
    doc = json.loads((raid_prerequisites.PREREQUISITES_DIR / "blackwing_descent.json").read_text())
    mutation(doc)
    broken = tmp_path / "blackwing_descent.json"
    broken.write_text(json.dumps(doc))
    output = _compile_and_run(tmp_path, PARITY_PROGRAM, [str(broken)])
    cpp_failure = json.loads(output.splitlines()[0])["failure"]
    python_failure = raid_prerequisites.validate(doc)
    assert cpp_failure.startswith(expected) and python_failure.startswith(expected)
    assert cpp_failure == python_failure


PROFILE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationProfile.cpp"
SEEDER = ROOT / "src/server/game/Bots/BotRaidLockoutSeeder.cpp"
BOT_MGR_LOADING = ROOT / "src/server/game/Bots/BotMgrLoading.cpp"

# The two pool-reset statements exactly as they were before package A
# (BotWorldPopulationMgrValidationProfile.cpp:421-422 at 0e793b9943).
ORIGINAL_RESET_DELETES = [
    'CharacterDatabase.DirectExecute(("DELETE FROM `character_instance` WHERE `guid` IN (" + guidSelect + ")").c_str());',
    'CharacterDatabase.DirectExecute(("DELETE gi FROM `group_instance` gi JOIN `groups` g ON g.`guid` = gi.`guid` '
    'WHERE g.`leaderGuid` IN (" + guidSelect + ") OR g.`guid` IN (SELECT gm.`guid` FROM `group_member` gm '
    'WHERE gm.`memberGuid` IN (" + guidSelect + "))").c_str());',
]


def _reset_body() -> str:
    source = PROFILE.read_text()
    start = source.index("bool BotWorldPopulationMgr::ResetValidationBotPool(")
    return source[start:source.index("\n}\n", start)]


def test_reset_without_a_lockout_runs_the_original_delete_sql() -> None:
    body = _reset_body()
    no_lockout = body.index("if (!keepSeededInstanceId)")
    keep = body.index("else", no_lockout)
    statements = [line.strip() for line in body[no_lockout:keep].splitlines() if "DirectExecute" in line]
    assert statements == ORIGINAL_RESET_DELETES
    # Only the keep branch filters by instance, and nothing else deletes binds.
    kept = [line.strip() for line in body[keep:].splitlines()
            if "DirectExecute" in line and "_instance`" in line]
    assert len(kept) == 2 and all("`instance` <> \" + keep" in line for line in kept)
    everywhere = [line.strip() for line in body.splitlines() if "DirectExecute" in line and "_instance`" in line]
    assert everywhere == ORIGINAL_RESET_DELETES + kept


def test_lockout_ids_are_never_freed_and_clear_refuses_before_unbinding() -> None:
    seeder = SEEDER.read_text()
    assert "FreeInstanceId(" not in seeder
    clear = seeder[seeder.index("std::string ClearLockout("):seeder.index("std::string ReadbackJson(")]
    first_change = min(clear.index("UnloadEmptyInstance("), clear.index("UnbindInstance("))
    for refusal in ("lockout_map_has_players", "lockout_bound_by_foreign_group", "lockout_bound_by_online_player",
                    "lockout_bound_by_unlisted_player"):
        assert clear.index(refusal) < first_change, refusal
    # Permanent online binds refuse; solo non-permanent ones are released in
    # the change phase so a clear works once the cohort stopped.
    refusal = clear.index('"lockout_bound_by_online_player:"')
    assert "if (bind->perm)" in clear[clear.rindex("\n", 0, refusal - 80):refusal]
    release = clear.index("for (ObjectGuid const& guid : transientBinds)")
    assert first_change < release and "UnbindInstance(record.MapId, difficulty, true)" in clear[release:release + 250]
    assert clear.index("UnloadEmptyInstance(") < clear.index("UnbindInstance(")
    # Refusals after the first unbind would leave a half-cleared lockout.
    assert not re.search(r'return "[^"]', clear[clear.index("UnbindInstance("):])


def test_seed_leader_placement_failures_release_the_seed_group_bind() -> None:
    loading = BOT_MGR_LOADING.read_text()
    function = loading[loading.index("Player* BotMgr::LoadCharacterAsBotSession("):]
    bind = function.index("BotRaidLockout::BindArmedSeedGroup(")
    for stage in ("stage=player_cannot_enter", "stage=destination_map_rejected", "stage=add_player_to_map"):
        branch = function[function.index(stage):]
        branch = branch[:branch.index("return nullptr;")]
        assert function.index(stage) > bind
        assert "if (seedRaidLeader)\n" in branch and "BotRaidLockout::ReleaseArmedSeedGroup(guid.GetCounter());" in branch
