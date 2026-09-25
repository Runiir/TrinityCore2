#ifndef TRINITY_BOT_RAID_LOCKOUT_DEFINITION_JSON_H
#define TRINITY_BOT_RAID_LOCKOUT_DEFINITION_JSON_H

// Reads experiments/configs/raid_prerequisites/<raid>.json
// (schema raid_prerequisites_v1) into a RaidDefinition. Header-only so the
// Python reader (tools/raid_program/raid_prerequisites.py) and this parser are
// compared on the real files by tests/test_bot_raid_lockout.py. Documentation
// keys (name, sources, notes, verification) are ignored here.

#include "Bots/BotRaidLockoutPlan.h"

#ifdef RAPIDJSON_ASSERT
#include "Errors.h" // the game target maps RAPIDJSON_ASSERT to WPAssert
#endif
#include <rapidjson/document.h>

#include <string>

namespace BotRaidLockout
{
namespace DefinitionJsonDetail
{
inline bool ReadUInt(rapidjson::Value const& object, char const* name, uint32_t& value,
    bool nullable, bool& isNull)
{
    isNull = false;
    auto const member = object.FindMember(name);
    if (member == object.MemberEnd())
        return false;
    if (member->value.IsNull())
    {
        isNull = true;
        return nullable;
    }
    if (!member->value.IsUint())
        return false;
    value = member->value.GetUint();
    return true;
}

inline bool ReadString(rapidjson::Value const& object, char const* name, std::string& value)
{
    auto const member = object.FindMember(name);
    if (member == object.MemberEnd() || !member->value.IsString())
        return false;
    value.assign(member->value.GetString(), member->value.GetStringLength());
    return true;
}

inline bool ReadStringArray(rapidjson::Value const& value, std::vector<std::string>& out)
{
    if (!value.IsArray())
        return false;
    for (rapidjson::Value const& item : value.GetArray())
    {
        if (!item.IsString())
            return false;
        out.emplace_back(item.GetString(), item.GetStringLength());
    }
    return true;
}

inline bool ReadUIntArray(rapidjson::Value const& value, std::vector<uint32_t>& out)
{
    if (!value.IsArray())
        return false;
    for (rapidjson::Value const& item : value.GetArray())
    {
        if (!item.IsUint())
            return false;
        out.push_back(item.GetUint());
    }
    return true;
}

inline bool ReadDifficultyArray(rapidjson::Value const& value, std::vector<uint8_t>& out)
{
    std::vector<std::string> tokens;
    if (!ReadStringArray(value, tokens))
        return false;
    for (std::string const& token : tokens)
    {
        uint8_t difficulty = 0;
        if (!ParseDifficulty(token, difficulty) || DifficultyToken(difficulty) != token)
            return false;
        out.push_back(difficulty);
    }
    return true;
}

inline bool ReadBoss(rapidjson::Value const& value, BossDefinition& boss, std::string& failure)
{
    if (!value.IsObject() || !ReadString(value, "key", boss.Key))
    {
        failure = "boss_key_required";
        return false;
    }
    std::string const context = ":" + boss.Key;
    bool isNull = false;
    ReadString(value, "name", boss.Name);
    if (!ReadUInt(value, "boss_index", boss.BossIndex, false, isNull))
    {
        failure = "boss_index_required" + context;
        return false;
    }
    if (!ReadUInt(value, "creature_entry", boss.CreatureEntry, true, isNull))
    {
        failure = "creature_entry_required" + context;
        return false;
    }
    if (!ReadUInt(value, "credit_entry", boss.CreditEntry, true, isNull))
    {
        failure = "credit_entry_required" + context;
        return false;
    }
    uint32_t bit = 0;
    if (!ReadUInt(value, "dungeon_encounter_bit", bit, true, isNull))
    {
        failure = "dungeon_encounter_bit_required" + context;
        return false;
    }
    boss.DungeonEncounterBit = isNull ? -1 : int32_t(bit);
    if (!ReadUInt(value, "dungeon_encounter_id", boss.DungeonEncounterId, true, isNull))
    {
        failure = "dungeon_encounter_id_required" + context;
        return false;
    }
    auto const byDifficulty = value.FindMember("dungeon_encounter_id_by_difficulty");
    if (byDifficulty != value.MemberEnd())
    {
        if (!byDifficulty->value.IsObject())
        {
            failure = "invalid_dungeon_encounter_id_by_difficulty" + context;
            return false;
        }
        for (auto const& pair : byDifficulty->value.GetObject())
        {
            uint8_t difficulty = 0;
            std::string const token(pair.name.GetString(), pair.name.GetStringLength());
            if (!ParseDifficulty(token, difficulty) || DifficultyToken(difficulty) != token
                || !pair.value.IsUint())
            {
                failure = "invalid_dungeon_encounter_id_by_difficulty" + context;
                return false;
            }
            boss.DungeonEncounterIdByDifficulty[difficulty] = pair.value.GetUint();
        }
    }
    auto const predecessors = value.FindMember("predecessors");
    if (predecessors == value.MemberEnd() || !ReadStringArray(predecessors->value, boss.Predecessors))
    {
        failure = "predecessors_required" + context;
        return false;
    }
    auto const extras = value.FindMember("extra_save_values");
    if (extras == value.MemberEnd() || !extras->value.IsObject())
    {
        failure = "extra_save_values_required" + context;
        return false;
    }
    for (auto const& pair : extras->value.GetObject())
    {
        if (!pair.value.IsUint())
        {
            failure = "invalid_extra_save_value" + context;
            return false;
        }
        boss.ExtraSaveValues[std::string(pair.name.GetString(), pair.name.GetStringLength())]
            = pair.value.GetUint();
    }
    auto const dead = value.FindMember("dead_db_spawn_entries");
    if (dead == value.MemberEnd())
    {
        failure = "dead_db_spawn_entries_required" + context;
        return false;
    }
    if (!dead->value.IsNull())
    {
        if (!ReadUIntArray(dead->value, boss.DeadDbSpawnEntries))
        {
            failure = "invalid_dead_db_spawn_entries" + context;
            return false;
        }
        boss.DeadDbSpawnEntriesKnown = true;
    }
    auto const summoned = value.FindMember("summoned_entries");
    if (summoned == value.MemberEnd() || !ReadUIntArray(summoned->value, boss.SummonedEntries))
    {
        failure = "summoned_entries_required" + context;
        return false;
    }
    auto const difficulties = value.FindMember("difficulties");
    if (difficulties != value.MemberEnd()
        && !ReadDifficultyArray(difficulties->value, boss.Difficulties))
    {
        failure = "invalid_boss_difficulties" + context;
        return false;
    }
    return true;
}
}

inline bool ParseRaidDefinitionJson(std::string const& text, RaidDefinition& def, std::string& failure)
{
    using namespace DefinitionJsonDetail;
    def = RaidDefinition();
    rapidjson::Document document;
    document.Parse(text.c_str(), text.size());
    if (document.HasParseError() || !document.IsObject())
    {
        failure = "json_parse_error";
        return false;
    }
    bool isNull = false;
    if (!ReadString(document, "schema", def.Schema) || !ReadString(document, "raid", def.Raid)
        || !ReadUInt(document, "map_id", def.MapId, false, isNull)
        || !ReadString(document, "script_name", def.ScriptName)
        || !ReadString(document, "script_header", def.ScriptHeader))
    {
        failure = "raid_identity_required";
        return false;
    }
    std::string initialState;
    if (!ReadString(document, "initial_boss_state", initialState)
        || (initialState != "not_started" && initialState != "to_be_decided"))
    {
        failure = "invalid_initial_boss_state";
        return false;
    }
    def.InitialBossState = initialState == "to_be_decided" ? StateToBeDecided : StateNotStarted;
    auto const difficulties = document.FindMember("difficulties");
    if (difficulties == document.MemberEnd() || !ReadDifficultyArray(difficulties->value, def.Difficulties))
    {
        failure = "invalid_difficulties";
        return false;
    }
    auto const counts = document.FindMember("encounter_count");
    if (counts == document.MemberEnd() || !counts->value.IsObject())
    {
        failure = "encounter_count_required";
        return false;
    }
    for (auto const& pair : counts->value.GetObject())
    {
        uint8_t difficulty = 0;
        std::string const token(pair.name.GetString(), pair.name.GetStringLength());
        if (!ParseDifficulty(token, difficulty) || DifficultyToken(difficulty) != token
            || !pair.value.IsUint())
        {
            failure = "invalid_encounter_count";
            return false;
        }
        def.EncounterCount[difficulty] = pair.value.GetUint();
    }
    auto const bosses = document.FindMember("bosses");
    if (bosses == document.MemberEnd() || !bosses->value.IsArray() || bosses->value.Empty())
    {
        failure = "bosses_required";
        return false;
    }
    for (rapidjson::Value const& value : bosses->value.GetArray())
    {
        BossDefinition boss;
        if (!ReadBoss(value, boss, failure))
            return false;
        def.Bosses.push_back(std::move(boss));
    }
    auto const extras = document.FindMember("save_extras");
    if (extras == document.MemberEnd() || !extras->value.IsArray())
    {
        failure = "save_extras_required";
        return false;
    }
    for (rapidjson::Value const& value : extras->value.GetArray())
    {
        SaveExtraDefinition extra;
        std::string encoding;
        if (!value.IsObject() || !ReadString(value, "name", extra.Name)
            || !ReadString(value, "encoding", encoding) || encoding != "raw_uint8"
            || !ReadUInt(value, "default", extra.Default, false, isNull))
        {
            failure = "invalid_save_extra";
            return false;
        }
        extra.Encoding = SaveExtraEncoding::RawUint8;
        def.SaveExtras.push_back(std::move(extra));
    }
    auto const doors = document.FindMember("readback_doors");
    if (doors != document.MemberEnd())
    {
        if (!doors->value.IsArray())
        {
            failure = "invalid_readback_doors";
            return false;
        }
        for (rapidjson::Value const& value : doors->value.GetArray())
        {
            DoorReadback door;
            if (!value.IsObject() || !ReadUInt(value, "entry", door.Entry, false, isNull))
            {
                failure = "invalid_readback_doors";
                return false;
            }
            auto const open = value.FindMember("open_when_done");
            if (open == value.MemberEnd() || !ReadStringArray(open->value, door.OpenWhenDone))
            {
                failure = "invalid_readback_doors";
                return false;
            }
            def.ReadbackDoors.push_back(std::move(door));
        }
    }
    failure = ValidateDefinition(def);
    return failure.empty();
}
}

#endif
