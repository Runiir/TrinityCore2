"""Header-only g++ tests for the seeded raid lockout planner (package A).

Covers BotRaidLockoutPlan.h (request parsing, predecessor closure, the exact
InstanceScript save bytes including the raw extra byte, load-side parsing) and
BotRaidLockoutDefinitionJson.h, whose output on the real prerequisite files is
compared with tools/raid_program/raid_prerequisites.py.
"""

from __future__ import annotations

import json
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
        std::vector<uint32_t> dead)
    {
        BossDefinition row;
        row.Key = key;
        row.BossIndex = index;
        row.DungeonEncounterId = 1000 + index;
        row.DungeonEncounterBit = bit;
        row.Predecessors = predecessors;
        row.DeadSpawnEntriesKnown = true;
        row.DeadSpawnEntries = dead;
        return row;
    };
    def.Bosses = {
        boss("magmaw", 0, 2, {}, { 41570 }),
        boss("omnotron", 1, 5, {}, {}),
        boss("chimaeron", 2, 1, { "magmaw", "omnotron" }, { 43296 }),
        boss("atramedes", 3, 0, { "magmaw", "omnotron" }, { 41442 }),
        boss("maloriak", 4, 3, { "magmaw", "omnotron" }, { 41378 }),
        boss("nefarian", 5, 4, { "magmaw", "omnotron", "chimaeron", "atramedes", "maloriak" }, { 41376, 41270 }),
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
    EXPECT((plan.DeadSpawnEntries == std::vector<uint32_t>{ 41570 }));

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
    unverified.Bosses[0].DeadSpawnEntriesKnown = false;
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
                     << ",\"dead\":" << JsonNumberArray(plan.DeadSpawnEntries) << "}";
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
                        "save_data": b"", "dead_spawn_entries": []}
                refusal = str(error)
            shards.append({
                "boss": row["key"],
                "difficulty": difficulty,
                "refusal": refusal,
                "bosses_done": plan["bosses_done"],
                "boss_states": plan["boss_states"],
                "mask": plan["completed_encounters_mask"],
                "save_hex": plan["save_data"].hex().upper(),
                "dead": plan["dead_spawn_entries"],
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
        (lambda doc: doc["bosses"][1].pop("dead_spawn_entries"), "dead_spawn_entries_required:omnotron"),
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
