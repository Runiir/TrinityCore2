#ifndef TRINITY_BOT_RAID_LOCKOUT_PLAN_H
#define TRINITY_BOT_RAID_LOCKOUT_PLAN_H

// Seeded raid lockouts (docs/bot_raids/full_raid_parallel_shards.md, package A).
// Pure data and planning only: no core types, so the header compiles alone and
// is covered by tests/test_bot_raid_lockout.py. The in-server seeder
// (BotRaidLockoutSeeder.cpp) turns a plan into an instance save that the
// native InstanceScript loads exactly like a saved lockout after a restart.

#include <algorithm>
#include <cctype>
#include <cstdint>
#include <functional>
#include <iomanip>
#include <map>
#include <set>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

namespace BotRaidLockout
{
// Mirrors InstanceScript.h EncounterState; BotRaidLockoutSeeder.cpp
// static_asserts the equality against the core enum.
constexpr uint8_t StateNotStarted = 0;
constexpr uint8_t StateInProgress = 1;
constexpr uint8_t StateFail = 2;
constexpr uint8_t StateDone = 3;
constexpr uint8_t StateSpecial = 4;
constexpr uint8_t StateToBeDecided = 5;

constexpr char const* SchemaVersion = "raid_prerequisites_v1";
constexpr uint8_t MaxRaidDifficulty = 4;   // RAID_DIFFICULTY_10MAN_NORMAL..25MAN_HEROIC
constexpr uint32_t MaxEncounterCount = 32; // completedEncounters is a uint32 bit mask

enum class SaveExtraEncoding : uint8_t
{
    // `data << uint8Member` in WriteSaveDataMore: one raw byte, no separator,
    // read back with `data >> uint8Member` (skips whitespace first).
    RawUint8
};

struct SaveExtraDefinition
{
    std::string Name;
    SaveExtraEncoding Encoding = SaveExtraEncoding::RawUint8;
    uint32_t Default = 0;
};

struct BossDefinition
{
    std::string Key;
    std::string Name;
    uint32_t BossIndex = 0;
    uint32_t CreatureEntry = 0;       // 0 = unknown
    uint32_t CreditEntry = 0;         // 0 = unknown (informational)
    uint32_t DungeonEncounterId = 0;  // DungeonEncounter.dbc ID for all difficulties; 0 = unknown
    std::map<uint8_t, uint32_t> DungeonEncounterIdByDifficulty;
    int32_t DungeonEncounterBit = -1; // -1 = unknown
    std::vector<std::string> Predecessors;
    std::map<std::string, uint32_t> ExtraSaveValues;
    // Creature entries whose database spawns a natural kill leaves dead for
    // the lockout. Unknown (null in JSON) refuses seeding the boss as done.
    bool DeadSpawnEntriesKnown = false;
    std::vector<uint32_t> DeadSpawnEntries;
    std::vector<uint8_t> Difficulties; // empty = every raid difficulty
};

struct DoorReadback
{
    uint32_t Entry = 0;
    std::vector<std::string> OpenWhenDone;
};

struct RaidDefinition
{
    std::string Schema;
    std::string Raid;
    uint32_t MapId = 0;
    std::string ScriptName;
    std::string ScriptHeader;
    // State of a boss nobody touched yet, as the native script leaves it:
    // NOT_STARTED after InstanceScript::Create(), TO_BE_DECIDED when the
    // script's Create() skips the base (Blackwing Descent). The native save
    // writes TO_BE_DECIDED as 5 and its load skips it, so a seeded lockout
    // reproduces a natural one byte for byte.
    uint8_t InitialBossState = StateNotStarted;
    std::vector<uint8_t> Difficulties;
    std::map<uint8_t, uint32_t> EncounterCount;
    std::vector<BossDefinition> Bosses;
    std::vector<SaveExtraDefinition> SaveExtras;
    std::vector<DoorReadback> ReadbackDoors;
};

struct SeedPlan
{
    uint8_t Difficulty = 0;
    uint32_t EncounterCount = 0;
    std::vector<uint8_t> BossStates;
    std::vector<std::string> BossesDone;   // ordered by boss index
    std::vector<uint32_t> BossIndicesDone; // same order
    uint32_t CompletedEncounterMask = 0;
    std::vector<std::pair<std::string, uint32_t>> ExtraValues; // save order
    std::string SaveData;                  // canonical GetSaveData() bytes
    std::vector<uint32_t> DeadSpawnEntries; // sorted, unique
};

inline bool ParseDifficulty(std::string const& token, uint8_t& difficulty)
{
    static std::map<std::string, uint8_t> const tokens = {
        { "10n", 0 }, { "25n", 1 }, { "10h", 2 }, { "25h", 3 },
        { "0", 0 }, { "1", 1 }, { "2", 2 }, { "3", 3 },
    };
    std::string lowered = token;
    std::transform(lowered.begin(), lowered.end(), lowered.begin(),
        [](unsigned char c) { return char(std::tolower(c)); });
    auto const itr = tokens.find(lowered);
    if (itr == tokens.end())
        return false;
    difficulty = itr->second;
    return true;
}

inline std::string DifficultyToken(uint8_t difficulty)
{
    switch (difficulty)
    {
        case 0: return "10n";
        case 1: return "25n";
        case 2: return "10h";
        case 3: return "25h";
        default: return "";
    }
}

// Same charset and length as BotWorldPopulationMgr::CreateCohort.
inline bool IsValidCohortId(std::string const& cohortId)
{
    return !cohortId.empty() && cohortId.size() <= 64
        && cohortId.find_first_not_of(
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
            == std::string::npos;
}

// Raid and boss keys: lower-case file-name-safe identifiers.
inline bool IsValidKey(std::string const& key)
{
    return !key.empty() && key.size() <= 64
        && key.find_first_not_of("abcdefghijklmnopqrstuvwxyz0123456789_") == std::string::npos;
}

// "none" or a comma list of boss keys; duplicates and empty items fail.
inline bool ParseBossList(std::string const& text, std::vector<std::string>& keys,
    std::string& failure)
{
    keys.clear();
    if (text == "none")
        return true;
    if (text.empty())
    {
        failure = "boss_list_required";
        return false;
    }
    std::set<std::string> seen;
    std::string item;
    std::istringstream stream(text);
    while (std::getline(stream, item, ','))
    {
        if (!IsValidKey(item))
        {
            failure = "invalid_boss_key:" + item;
            return false;
        }
        if (!seen.insert(item).second)
        {
            failure = "duplicate_boss:" + item;
            return false;
        }
        keys.push_back(item);
    }
    if (text.back() == ',')
    {
        failure = "invalid_boss_key:";
        return false;
    }
    return true;
}

inline BossDefinition const* FindBoss(RaidDefinition const& def, std::string const& key)
{
    for (BossDefinition const& boss : def.Bosses)
        if (boss.Key == key)
            return &boss;
    return nullptr;
}

inline bool BossAvailableOn(BossDefinition const& boss, uint8_t difficulty)
{
    return boss.Difficulties.empty()
        || std::find(boss.Difficulties.begin(), boss.Difficulties.end(), difficulty)
            != boss.Difficulties.end();
}

inline uint32_t DungeonEncounterIdFor(BossDefinition const& boss, uint8_t difficulty)
{
    auto const itr = boss.DungeonEncounterIdByDifficulty.find(difficulty);
    return itr != boss.DungeonEncounterIdByDifficulty.end() ? itr->second : boss.DungeonEncounterId;
}

// Transitive predecessors of `key`, excluding `key`. Unknown keys contribute
// nothing; ValidateDefinition rejects them separately.
inline std::set<std::string> PredecessorClosure(RaidDefinition const& def, std::string const& key)
{
    std::set<std::string> closure;
    std::vector<std::string> pending;
    if (BossDefinition const* boss = FindBoss(def, key))
        pending = boss->Predecessors;
    while (!pending.empty())
    {
        std::string const next = pending.back();
        pending.pop_back();
        if (next == key || !closure.insert(next).second)
            continue;
        if (BossDefinition const* boss = FindBoss(def, next))
            pending.insert(pending.end(), boss->Predecessors.begin(), boss->Predecessors.end());
    }
    return closure;
}

// Depth-first search over predecessor edges; true when any boss can reach itself.
inline bool HasPredecessorCycle(RaidDefinition const& def, std::string& cycleKey)
{
    std::map<std::string, int> color; // 0 unvisited, 1 on stack, 2 finished
    std::function<bool(std::string const&)> visit = [&](std::string const& key) -> bool
    {
        int& mark = color[key];
        if (mark == 1)
        {
            cycleKey = key;
            return true;
        }
        if (mark == 2)
            return false;
        mark = 1;
        if (BossDefinition const* boss = FindBoss(def, key))
            for (std::string const& predecessor : boss->Predecessors)
                if (visit(predecessor))
                    return true;
        color[key] = 2;
        return false;
    };
    for (BossDefinition const& boss : def.Bosses)
        if (visit(boss.Key))
            return true;
    return false;
}

// A raw byte read back with `>>` must not be whitespace, or the reader would
// skip it and consume the next field instead.
inline bool RawByteRoundTrips(uint32_t value)
{
    return value <= 255 && !(value == ' ' || (value >= '\t' && value <= '\r'));
}

inline std::string ValidateDefinition(RaidDefinition const& def)
{
    if (def.Schema != SchemaVersion)
        return "schema_mismatch";
    if (!IsValidKey(def.Raid))
        return "invalid_raid_key";
    if (!def.MapId)
        return "invalid_map_id";
    if (def.ScriptName.empty())
        return "script_name_required";
    if (std::none_of(def.ScriptHeader.begin(), def.ScriptHeader.end(),
        [](unsigned char c) { return std::isalpha(c) != 0; }))
        return "script_header_required";
    if (def.InitialBossState != StateNotStarted && def.InitialBossState != StateToBeDecided)
        return "invalid_initial_boss_state";
    if (def.Difficulties.empty())
        return "difficulties_required";
    std::set<uint8_t> difficulties;
    for (uint8_t difficulty : def.Difficulties)
        if (difficulty >= MaxRaidDifficulty || !difficulties.insert(difficulty).second)
            return "invalid_difficulty";
    if (def.EncounterCount.size() != difficulties.size())
        return "encounter_count_difficulty_mismatch";
    for (auto const& [difficulty, count] : def.EncounterCount)
        if (!difficulties.count(difficulty) || !count || count > MaxEncounterCount)
            return "invalid_encounter_count";

    std::set<std::string> extraNames;
    for (SaveExtraDefinition const& extra : def.SaveExtras)
    {
        if (!IsValidKey(extra.Name) || !extraNames.insert(extra.Name).second)
            return "invalid_save_extra:" + extra.Name;
        if (extra.Encoding == SaveExtraEncoding::RawUint8 && extra.Default > 255)
            return "invalid_save_extra_default:" + extra.Name;
    }

    std::set<std::string> keys;
    for (BossDefinition const& boss : def.Bosses)
        if (!IsValidKey(boss.Key) || !keys.insert(boss.Key).second)
            return "invalid_boss_key:" + boss.Key;

    for (uint8_t difficulty : def.Difficulties)
    {
        uint32_t const count = def.EncounterCount.at(difficulty);
        std::vector<int> seen(count, 0);
        for (BossDefinition const& boss : def.Bosses)
        {
            if (!BossAvailableOn(boss, difficulty))
                continue;
            if (boss.BossIndex >= count)
                return "boss_index_out_of_range:" + boss.Key;
            if (seen[boss.BossIndex]++)
                return "duplicate_boss_index:" + boss.Key;
        }
        for (uint32_t index = 0; index < count; ++index)
            if (!seen[index])
                return "missing_boss_index:" + std::to_string(index) + ":" + DifficultyToken(difficulty);
    }

    for (BossDefinition const& boss : def.Bosses)
    {
        for (uint8_t difficulty : boss.Difficulties)
            if (!difficulties.count(difficulty))
                return "boss_difficulty_not_in_raid:" + boss.Key;
        for (auto const& [difficulty, encounterId] : boss.DungeonEncounterIdByDifficulty)
            if (!difficulties.count(difficulty) || !encounterId)
                return "invalid_dungeon_encounter_id:" + boss.Key;
        if (boss.DungeonEncounterBit < -1 || boss.DungeonEncounterBit >= int32_t(MaxEncounterCount))
            return "invalid_dungeon_encounter_bit:" + boss.Key;
        std::set<std::string> direct;
        for (std::string const& predecessor : boss.Predecessors)
        {
            BossDefinition const* other = FindBoss(def, predecessor);
            if (!other || predecessor == boss.Key || !direct.insert(predecessor).second)
                return "invalid_predecessor:" + boss.Key + ":" + predecessor;
            for (uint8_t difficulty : def.Difficulties)
                if (BossAvailableOn(boss, difficulty) && !BossAvailableOn(*other, difficulty))
                    return "predecessor_unavailable:" + boss.Key + ":" + predecessor;
        }
        for (auto const& [name, value] : boss.ExtraSaveValues)
        {
            if (!extraNames.count(name))
                return "unknown_extra_save_value:" + boss.Key + ":" + name;
            if (!RawByteRoundTrips(value))
                return "extra_save_value_not_round_trip:" + boss.Key + ":" + name;
        }
        for (uint32_t entry : boss.DeadSpawnEntries)
            if (!entry)
                return "invalid_dead_spawn_entry:" + boss.Key;
    }
    std::string cycleKey;
    if (HasPredecessorCycle(def, cycleKey))
        return "predecessor_cycle:" + cycleKey;

    for (DoorReadback const& door : def.ReadbackDoors)
    {
        if (!door.Entry || door.OpenWhenDone.empty())
            return "invalid_readback_door";
        for (std::string const& key : door.OpenWhenDone)
            if (!keys.count(key))
                return "invalid_readback_door_boss:" + key;
    }
    return "";
}

// InstanceScript::GetSaveData: each alphabetic header char and a space, each
// boss state as an integer and a space, then WriteSaveDataMore.
inline std::string BuildSaveData(std::string const& header, std::vector<uint8_t> const& states,
    std::vector<std::pair<SaveExtraEncoding, uint32_t>> const& extras)
{
    std::string data;
    for (char c : header)
        if (std::isalpha(static_cast<unsigned char>(c)))
        {
            data += c;
            data += ' ';
        }
    for (uint8_t state : states)
    {
        data += std::to_string(uint32_t(state));
        data += ' ';
    }
    for (auto const& [encoding, value] : extras)
        if (encoding == SaveExtraEncoding::RawUint8)
            data += char(uint8_t(value));
    return data;
}

// Plans the exact lockout for `bossKeys` done. Returns "" or a failure reason.
inline std::string BuildSeedPlan(RaidDefinition const& def, uint8_t difficulty,
    std::vector<std::string> const& bossKeys, SeedPlan& plan)
{
    plan = SeedPlan();
    std::string const invalid = ValidateDefinition(def);
    if (!invalid.empty())
        return "invalid_definition:" + invalid;
    auto const count = def.EncounterCount.find(difficulty);
    if (count == def.EncounterCount.end())
        return "difficulty_not_supported:" + DifficultyToken(difficulty);

    plan.Difficulty = difficulty;
    plan.EncounterCount = count->second;
    plan.BossStates.assign(plan.EncounterCount, def.InitialBossState);

    std::set<std::string> done;
    for (std::string const& key : bossKeys)
    {
        BossDefinition const* boss = FindBoss(def, key);
        if (!boss)
            return "unknown_boss:" + key;
        if (!BossAvailableOn(*boss, difficulty))
            return "boss_not_available_on_difficulty:" + key;
        if (!done.insert(key).second)
            return "duplicate_boss:" + key;
    }

    std::vector<BossDefinition const*> ordered;
    for (std::string const& key : done)
        ordered.push_back(FindBoss(def, key));
    std::sort(ordered.begin(), ordered.end(),
        [](BossDefinition const* a, BossDefinition const* b) { return a->BossIndex < b->BossIndex; });

    std::map<std::string, uint32_t> extraValues;
    for (SaveExtraDefinition const& extra : def.SaveExtras)
        extraValues[extra.Name] = extra.Default;
    std::map<std::string, std::string> extraOwner;
    std::set<uint32_t> deadEntries;
    for (BossDefinition const* boss : ordered)
    {
        for (std::string const& predecessor : boss->Predecessors)
            if (!done.count(predecessor))
                return "bosses_done_not_predecessor_closed:" + boss->Key + ":" + predecessor;
        if (boss->DungeonEncounterBit < 0)
            return "boss_encounter_bit_unknown:" + boss->Key;
        if (!boss->DeadSpawnEntriesKnown)
            return "boss_dead_spawns_unverified:" + boss->Key;
        plan.BossStates[boss->BossIndex] = StateDone;
        plan.BossesDone.push_back(boss->Key);
        plan.BossIndicesDone.push_back(boss->BossIndex);
        plan.CompletedEncounterMask |= uint32_t(1) << uint32_t(boss->DungeonEncounterBit);
        for (auto const& [name, value] : boss->ExtraSaveValues)
        {
            auto const owner = extraOwner.find(name);
            if (owner != extraOwner.end() && extraValues[name] != value)
                return "extra_save_value_conflict:" + name;
            extraValues[name] = value;
            extraOwner[name] = boss->Key;
        }
        deadEntries.insert(boss->DeadSpawnEntries.begin(), boss->DeadSpawnEntries.end());
    }

    std::vector<std::pair<SaveExtraEncoding, uint32_t>> extras;
    for (SaveExtraDefinition const& extra : def.SaveExtras)
    {
        plan.ExtraValues.emplace_back(extra.Name, extraValues[extra.Name]);
        extras.emplace_back(extra.Encoding, extraValues[extra.Name]);
    }
    plan.SaveData = BuildSaveData(def.ScriptHeader, plan.BossStates, extras);
    plan.DeadSpawnEntries.assign(deadEntries.begin(), deadEntries.end());
    return "";
}

// Mirrors InstanceScript::Load on `data.c_str()`: the string ends at the first
// NUL, IN_PROGRESS/FAIL/SPECIAL load as NOT_STARTED, and a raw byte extra that
// cannot be read keeps its default. Returns false on a header or state error.
inline bool ParseSaveData(std::string const& data, RaidDefinition const& def, uint32_t encounterCount,
    std::vector<uint8_t>& states, std::vector<std::pair<std::string, uint32_t>>& extras)
{
    states.clear();
    extras.clear();
    std::istringstream stream(std::string(data.c_str()));
    for (char header : def.ScriptHeader)
    {
        if (!std::isalpha(static_cast<unsigned char>(header)))
            continue;
        char observed = 0;
        if (!(stream >> observed) || observed != header)
            return false;
    }
    for (uint32_t index = 0; index < encounterCount; ++index)
    {
        uint32_t value = 0;
        if (!(stream >> value))
            return false;
        if (value == StateInProgress || value == StateFail || value == StateSpecial)
            value = StateNotStarted;
        states.push_back(uint8_t(value < StateToBeDecided ? value : StateToBeDecided));
    }
    for (SaveExtraDefinition const& extra : def.SaveExtras)
    {
        uint32_t value = extra.Default;
        unsigned char raw = 0;
        if (stream >> raw)
            value = raw;
        extras.emplace_back(extra.Name, value);
    }
    return true;
}

inline std::string ToHex(std::string const& bytes)
{
    std::ostringstream hex;
    hex << std::uppercase << std::hex << std::setfill('0');
    for (unsigned char c : bytes)
        hex << std::setw(2) << uint32_t(c);
    return hex.str();
}

inline bool FromHex(std::string const& hex, std::string& bytes)
{
    bytes.clear();
    if (hex.size() % 2)
        return false;
    auto nibble = [](char c) -> int
    {
        if (c >= '0' && c <= '9') return c - '0';
        if (c >= 'a' && c <= 'f') return c - 'a' + 10;
        if (c >= 'A' && c <= 'F') return c - 'A' + 10;
        return -1;
    };
    for (size_t index = 0; index < hex.size(); index += 2)
    {
        int const high = nibble(hex[index]);
        int const low = nibble(hex[index + 1]);
        if (high < 0 || low < 0)
            return false;
        bytes += char((high << 4) | low);
    }
    return true;
}

inline std::string JsonEscape(std::string const& value)
{
    std::ostringstream escaped;
    for (unsigned char c : value)
    {
        if (c == '"' || c == '\\')
            escaped << '\\' << char(c);
        else if (c < 0x20)
            escaped << "\\u" << std::hex << std::setw(4) << std::setfill('0') << uint32_t(c) << std::dec;
        else
            escaped << char(c);
    }
    return escaped.str();
}

inline std::string JsonStringArray(std::vector<std::string> const& values)
{
    std::string json = "[";
    for (size_t index = 0; index < values.size(); ++index)
    {
        if (index)
            json += ',';
        json += "\"" + JsonEscape(values[index]) + "\"";
    }
    return json + "]";
}

template <typename T>
inline std::string JsonNumberArray(std::vector<T> const& values)
{
    std::string json = "[";
    for (size_t index = 0; index < values.size(); ++index)
    {
        if (index)
            json += ',';
        json += std::to_string(uint64_t(values[index]));
    }
    return json + "]";
}
}

#endif
