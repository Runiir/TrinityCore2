#include "Bots/BotRaidLockoutSeeder.h"

#include "Bots/BotRaidLockoutDefinitionJson.h"
#include "Config.h"
#include "DatabaseEnv.h"
#include "DBCStores.h"
#include "GameObject.h"
#include "GameTime.h"
#include "Group.h"
#include "GroupMgr.h"
#include "InstanceSaveMgr.h"
#include "InstanceScript.h"
#include "Log.h"
#include "Map.h"
#include "MapManager.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"

#include <fstream>
#include <limits>
#include <mutex>
#include <set>
#include <shared_mutex>
#include <sstream>

static_assert(BotRaidLockout::StateNotStarted == NOT_STARTED && BotRaidLockout::StateInProgress == IN_PROGRESS
    && BotRaidLockout::StateFail == FAIL && BotRaidLockout::StateDone == DONE
    && BotRaidLockout::StateSpecial == SPECIAL && BotRaidLockout::StateToBeDecided == TO_BE_DECIDED,
    "BotRaidLockoutPlan.h must mirror InstanceScript EncounterState");
static_assert(BotRaidLockout::MaxRaidDifficulty == MAX_RAID_DIFFICULTY,
    "BotRaidLockoutPlan.h must mirror the raid difficulty range");

namespace BotRaidLockout
{
namespace
{
constexpr size_t MaxDefinitionBytes = 1024 * 1024;
// Creature::setDeathState stores this for a dungeon boss without respawn
// delay: "never respawn in this instance". A seeded lockout uses it for every
// dead boss spawn; the weekly raid reset deletes it with the instance.
constexpr uint64 NeverRespawn = uint64(std::numeric_limits<time_t>::max());

struct DbRow
{
    uint32 MapId = 0;
    uint32 Difficulty = 0;
    uint32 CompletedEncounterMask = 0;
    std::string SaveDataHex;
};

bool ReadDbRow(uint32 instanceId, DbRow& row)
{
    QueryResult result = CharacterDatabase.PQuery(
        "SELECT `map`, `difficulty`, `completedEncounters`, HEX(`data`) FROM `instance` WHERE `id` = %u",
        instanceId);
    if (!result)
        return false;
    Field* fields = result->Fetch();
    row.MapId = fields[0].GetUInt16();
    row.Difficulty = fields[1].GetUInt8();
    row.CompletedEncounterMask = fields[2].GetUInt32();
    row.SaveDataHex = fields[3].GetString();
    return true;
}

// Synchronous so the native load that follows cannot race an async queue.
void DeleteRowsSync(uint32 instanceId)
{
    CharacterDatabase.DirectPExecute("DELETE FROM `instance` WHERE `id` = %u", instanceId);
    CharacterDatabase.DirectPExecute("DELETE FROM `character_instance` WHERE `instance` = %u", instanceId);
    CharacterDatabase.DirectPExecute("DELETE FROM `group_instance` WHERE `instance` = %u", instanceId);
    CharacterDatabase.DirectPExecute("DELETE FROM `respawn` WHERE `instanceId` = %u", instanceId);
}

// The same columns InstanceSave::SaveToDB and Creature::SaveRespawnTime
// write. The save data goes through UNHEX so its raw extra bytes (a NUL for
// an extra still NOT_STARTED) are stored exactly as the native prepared
// statement stores them.
void WriteRowsSync(LockoutRecord const& record)
{
    DeleteRowsSync(record.InstanceId);
    for (RespawnRow const& row : record.RespawnRows)
        CharacterDatabase.DirectPExecute(
            "REPLACE INTO `respawn` (`type`, `spawnId`, `respawnTime`, `mapId`, `instanceId`) VALUES (%u, %u, %llu, %u, %u)",
            uint32(SPAWN_TYPE_CREATURE), row.SpawnId, static_cast<unsigned long long>(NeverRespawn),
            record.MapId, record.InstanceId);
    CharacterDatabase.DirectPExecute(
        "INSERT INTO `instance` (`id`, `map`, `resettime`, `difficulty`, `completedEncounters`, `data`) "
        "VALUES (%u, %u, 0, %u, %u, CONVERT(UNHEX('%s') USING utf8mb4))",
        record.InstanceId, record.MapId, uint32(record.Difficulty), record.CompletedEncounterMask,
        ToHex(record.SaveData).c_str());
}

std::string VerifyOnServer(RaidDefinition const& def, uint8 difficulty, SeedPlan const& plan,
    std::vector<std::string>& creditMismatches)
{
    MapEntry const* entry = sMapStore.LookupEntry(def.MapId);
    if (!entry || !entry->IsRaid())
        return "map_not_a_raid";
    InstanceTemplate const* instanceTemplate = sObjectMgr->GetInstanceTemplate(def.MapId);
    if (!instanceTemplate || sObjectMgr->GetScriptName(instanceTemplate->ScriptId) != def.ScriptName)
        return "instance_script_mismatch";
    // Exact difficulty only: CreateInstance would otherwise downscale it.
    if (!sDBCManager.GetMapDifficultyData(def.MapId, Difficulty(difficulty)))
        return "map_difficulty_unavailable";

    DungeonEncounterList const* live = sObjectMgr->GetDungeonEncounterList(def.MapId, Difficulty(difficulty));
    for (BossDefinition const& boss : def.Bosses)
    {
        if (!BossAvailableOn(boss, difficulty))
            continue;
        bool const done = std::find(plan.BossesDone.begin(), plan.BossesDone.end(), boss.Key)
            != plan.BossesDone.end();
        uint32 const encounterId = DungeonEncounterIdFor(boss, difficulty);
        if (!encounterId)
        {
            if (done)
                return "dungeon_encounter_id_unknown:" + boss.Key;
            continue;
        }
        DungeonEncounterEntry const* dbc = sDungeonEncounterStore.LookupEntry(encounterId);
        if (!dbc || dbc->MapID != def.MapId || int32(dbc->Bit) != boss.DungeonEncounterBit
            || (dbc->DifficultyID != -1 && dbc->DifficultyID != int32(difficulty)))
            return "dungeon_encounter_mismatch:" + boss.Key;
        if (live)
            for (DungeonEncounter const* encounter : *live)
                if (encounter && encounter->dbcEntry && encounter->dbcEntry->ID == encounterId
                    && encounter->creditEntry != boss.CreditEntry)
                    creditMismatches.push_back(boss.Key + ":" + std::to_string(encounter->creditEntry));
    }
    return "";
}

// Database spawns of the dead entries on this map and difficulty. Summons
// (Atramedes, Nefarian, Majordomo) have none and contribute no row.
std::vector<RespawnRow> ScanDeadSpawns(uint32 mapId, uint8 difficulty, std::vector<uint32> const& entries)
{
    std::vector<RespawnRow> rows;
    if (entries.empty())
        return rows;
    std::set<uint32> const wanted(entries.begin(), entries.end());
    for (auto const& [spawnId, data] : sObjectMgr->GetAllCreatureData())
        if (data.mapId == mapId && data.dbData && wanted.count(data.id)
            && (data.spawnMask & (1u << difficulty)))
            rows.push_back({ spawnId, data.id });
    std::sort(rows.begin(), rows.end(),
        [](RespawnRow const& a, RespawnRow const& b) { return a.SpawnId < b.SpawnId; });
    return rows;
}

void RollbackSeed(LockoutRecord const& record)
{
    sMapMgr->UnloadEmptyInstance(record.MapId, record.InstanceId);
    if (InstanceSave* save = sInstanceSaveMgr->GetInstanceSave(record.InstanceId))
        if (!save->GetPlayerCount() && !save->GetGroupCount())
            sInstanceSaveMgr->UnloadInstanceSave(record.InstanceId);
    DeleteRowsSync(record.InstanceId);
    if (!sInstanceSaveMgr->GetInstanceSave(record.InstanceId)
        && !sMapMgr->FindMap(record.MapId, record.InstanceId))
        sMapMgr->FreeInstanceId(record.InstanceId);
}

void ObserveDoors(LockoutRecord const& record, InstanceMap* map, Readback& readback)
{
    for (DoorReadback const& door : record.Doors)
    {
        DoorObservation observation;
        observation.Entry = door.Entry;
        observation.ExpectedOpen = !readback.BossStates.empty();
        for (std::string const& key : door.OpenWhenDone)
        {
            auto const index = record.BossIndexByKey.find(key);
            if (index == record.BossIndexByKey.end() || index->second >= readback.BossStates.size()
                || readback.BossStates[index->second] != StateDone)
                observation.ExpectedOpen = false;
        }
        uint32 open = 0;
        uint32 closed = 0;
        if (map)
            for (auto const& [spawnId, gameObject] : map->GetGameObjectBySpawnIdStore())
                if (gameObject && gameObject->GetEntry() == door.Entry)
                    ++(gameObject->GetGoState() == GO_STATE_ACTIVE ? open : closed);
        observation.Observed = !open && !closed ? "not_loaded" : (closed ? "closed" : "open");
        readback.Doors.push_back(observation);
    }
}
}

std::string LoadDefinition(std::string const& raid, RaidDefinition& def)
{
    if (!IsValidKey(raid))
        return "invalid_raid_key";
    std::string const directory = sConfigMgr->GetStringDefault("BotWorld.RaidPrerequisitesDir",
        "experiments/configs/raid_prerequisites");
    std::string const path = directory + "/" + raid + ".json";
    std::ifstream input(path.c_str(), std::ios::in | std::ios::binary);
    if (!input)
        return "prerequisite_file_unreadable:" + path;
    std::ostringstream text;
    text << input.rdbuf();
    if (text.str().size() > MaxDefinitionBytes)
        return "prerequisite_file_too_large";
    std::string failure;
    if (!ParseRaidDefinitionJson(text.str(), def, failure))
        return "invalid_prerequisite_file:" + failure;
    if (def.Raid != raid)
        return "raid_key_file_name_mismatch";
    return "";
}

Readback ReadbackLockout(LockoutRecord const& record)
{
    Readback readback;
    if (InstanceSave* save = sInstanceSaveMgr->GetInstanceSave(record.InstanceId))
    {
        readback.SaveLoaded = true;
        readback.SavePlayerBinds = save->GetPlayerCount();
        readback.SaveGroupBinds = save->GetGroupCount();
    }

    DbRow row;
    readback.DbRowPresent = ReadDbRow(record.InstanceId, row);
    if (readback.DbRowPresent)
    {
        readback.DbIdentityMatches = row.MapId == record.MapId && row.Difficulty == record.Difficulty;
        readback.DbSaveDataHex = row.SaveDataHex;
        readback.DbCompletedEncounterMask = row.CompletedEncounterMask;
    }

    std::string saveData;
    Map* map = sMapMgr->FindMap(record.MapId, record.InstanceId);
    InstanceMap* instanceMap = map ? map->ToInstanceMap() : nullptr;
    InstanceScript* script = instanceMap ? instanceMap->GetInstanceScript() : nullptr;
    readback.MapLoaded = map != nullptr;
    if (script)
    {
        readback.Source = "live_instance_script";
        readback.ScriptName = instanceMap->GetScriptName();
        readback.EncounterCount = script->GetEncounterCount();
        for (uint32 index = 0; index < readback.EncounterCount; ++index)
            readback.BossStates.push_back(uint8(script->GetBossState(index)));
        readback.CompletedEncounterMask = script->GetCompletedEncounterMask();
        saveData = script->GetSaveData();
        readback.MapPlayers = instanceMap->GetPlayersCountExceptGMs();
        for (RespawnRow const& respawn : record.RespawnRows)
            if (instanceMap->GetCreatureRespawnTime(respawn.SpawnId))
                ++readback.RespawnRowsLoaded;
    }
    else if (readback.DbRowPresent && readback.DbIdentityMatches)
    {
        readback.Source = "database";
        readback.ScriptName = record.ScriptName;
        readback.EncounterCount = record.EncounterCount;
        readback.CompletedEncounterMask = row.CompletedEncounterMask;
        RaidDefinition shape;
        shape.ScriptHeader = record.ScriptHeader;
        for (auto const& [name, value] : record.ExtraValues)
            shape.SaveExtras.push_back({ name, SaveExtraEncoding::RawUint8, 0 });
        std::vector<std::pair<std::string, uint32_t>> extras;
        if (!FromHex(row.SaveDataHex, saveData)
            || !ParseSaveData(saveData, shape, record.EncounterCount, readback.BossStates, extras))
            readback.Failure = "seeded_lockout_db_save_data_unreadable";
    }

    readback.SaveDataHex = ToHex(saveData);
    readback.SaveDataMatches = saveData == record.SaveData;
    std::vector<std::pair<uint32, std::string>> byIndex;
    for (auto const& [key, index] : record.BossIndexByKey)
        byIndex.emplace_back(index, key);
    std::sort(byIndex.begin(), byIndex.end());
    for (auto const& [index, key] : byIndex)
    {
        bool const expected = std::find(record.BossesDone.begin(), record.BossesDone.end(), key)
            != record.BossesDone.end();
        bool const observed = index < readback.BossStates.size() && readback.BossStates[index] == StateDone;
        if (observed && !expected)
            readback.ExtraDone.push_back(key);
        if (!observed && expected)
            readback.MissingDone.push_back(key);
    }
    readback.LockoutIntact = readback.EncounterCount == record.EncounterCount
        && readback.BossStates.size() == record.EncounterCount
        && readback.ExtraDone.empty() && readback.MissingDone.empty();
    readback.ExactMatch = readback.LockoutIntact && readback.BossStates == record.ExpectedStates
        && readback.CompletedEncounterMask == record.CompletedEncounterMask && readback.SaveDataMatches;
    ObserveDoors(record, instanceMap, readback);

    if (!readback.Failure.empty())
        return readback;
    if (!readback.DbRowPresent)
        readback.Failure = "seeded_lockout_db_row_missing";
    else if (!readback.DbIdentityMatches)
        readback.Failure = "seeded_lockout_db_identity_mismatch";
    else if (script && readback.ScriptName != record.ScriptName)
        readback.Failure = "instance_script_mismatch";
    else if (readback.EncounterCount != record.EncounterCount)
        readback.Failure = "encounter_count_mismatch";
    else if (!readback.MissingDone.empty())
        readback.Failure = "seeded_boss_not_done:" + readback.MissingDone.front();
    else
        for (DoorObservation const& door : readback.Doors)
            if (door.Observed != "not_loaded" && (door.Observed == "open") != door.ExpectedOpen)
            {
                readback.Failure = "door_state_mismatch:" + std::to_string(door.Entry);
                break;
            }
    return readback;
}

bool EnsureSaveLoaded(LockoutRecord const& record)
{
    InstanceSave* save = sInstanceSaveMgr->GetInstanceSave(record.InstanceId);
    if (!save)
        save = sInstanceSaveMgr->AddInstanceSave(record.MapId, record.InstanceId,
            Difficulty(record.Difficulty), 0, false, true);
    return save && save->GetMapId() == record.MapId
        && uint8(save->GetDifficulty()) == record.Difficulty;
}

std::string SeedLockout(std::string const& cohortId, std::string const& raid,
    std::string const& difficultyToken, std::string const& bossList,
    LockoutRecord& record, Readback& readback)
{
    record = LockoutRecord();
    readback = Readback();
    if (!IsValidCohortId(cohortId))
        return "invalid_cohort_id";
    uint8_t difficulty = 0;
    if (!ParseDifficulty(difficultyToken, difficulty))
        return "invalid_difficulty";
    std::vector<std::string> keys;
    std::string failure;
    if (!ParseBossList(bossList, keys, failure))
        return failure;
    RaidDefinition def;
    failure = LoadDefinition(raid, def);
    if (!failure.empty())
        return failure;
    SeedPlan plan;
    failure = BuildSeedPlan(def, difficulty, keys, plan);
    if (!failure.empty())
        return failure;
    failure = VerifyOnServer(def, difficulty, plan, record.CreditEntryMismatches);
    if (!failure.empty())
        return failure;

    record.CohortId = cohortId;
    record.Raid = def.Raid;
    record.ScriptName = def.ScriptName;
    record.ScriptHeader = def.ScriptHeader;
    record.MapId = def.MapId;
    record.Difficulty = difficulty;
    record.EncounterCount = plan.EncounterCount;
    record.BossesDone = plan.BossesDone;
    record.BossIndicesDone = plan.BossIndicesDone;
    record.ExpectedStates = plan.BossStates;
    for (BossDefinition const& boss : def.Bosses)
        if (BossAvailableOn(boss, difficulty))
            record.BossIndexByKey[boss.Key] = boss.BossIndex;
    record.CompletedEncounterMask = plan.CompletedEncounterMask;
    record.SaveData = plan.SaveData;
    record.ExtraValues = plan.ExtraValues;
    record.RespawnRows = ScanDeadSpawns(def.MapId, difficulty, plan.DeadSpawnEntries);
    record.Doors = def.ReadbackDoors;
    record.SeededAtUnix = uint64(GameTime::GetGameTime());

    // The core's own allocator: ids are never inserted by SQL while running.
    record.InstanceId = sMapMgr->GenerateInstanceId();
    if (!record.InstanceId || sMapMgr->FindMap(record.MapId, record.InstanceId)
        || sInstanceSaveMgr->GetInstanceSave(record.InstanceId) || Registry::HasInstance(record.InstanceId))
    {
        uint32 const collided = record.InstanceId;
        record.InstanceId = 0;
        return "instance_id_in_use:" + std::to_string(collided);
    }

    WriteRowsSync(record);
    DbRow row;
    if (!ReadDbRow(record.InstanceId, row) || row.MapId != record.MapId || row.Difficulty != record.Difficulty
        || row.CompletedEncounterMask != record.CompletedEncounterMask
        || row.SaveDataHex != ToHex(record.SaveData))
    {
        RollbackSeed(record);
        return "seeded_lockout_db_write_mismatch";
    }

    // A permanent-lock save (canReset = false) loaded without a database
    // write, as Player::_LoadBoundInstances does for a permanent bind.
    InstanceSave* save = sInstanceSaveMgr->AddInstanceSave(record.MapId, record.InstanceId,
        Difficulty(record.Difficulty), 0, false, true);
    if (!save || save->GetMapId() != record.MapId || uint8(save->GetDifficulty()) != record.Difficulty)
    {
        RollbackSeed(record);
        return "instance_save_create_failed";
    }
    if (!sMapMgr->LoadInstanceForSave(save, TEAM_NEUTRAL))
    {
        RollbackSeed(record);
        return "instance_map_load_failed";
    }

    readback = ReadbackLockout(record);
    std::string readbackFailure = readback.Failure;
    if (readbackFailure.empty() && readback.Source != "live_instance_script")
        readbackFailure = "seeded_lockout_live_readback_missing";
    if (readbackFailure.empty() && !readback.ExactMatch)
        readbackFailure = "seeded_lockout_readback_mismatch";
    if (readbackFailure.empty() && readback.RespawnRowsLoaded != record.RespawnRows.size())
        readbackFailure = "seeded_lockout_respawn_rows_not_loaded";

    // Admission re-creates the map through CreateMap with the leader's team.
    if (!sMapMgr->UnloadEmptyInstance(record.MapId, record.InstanceId) && readbackFailure.empty())
        readbackFailure = "seeding_map_unload_refused";
    if (!readbackFailure.empty())
    {
        RollbackSeed(record);
        return readbackFailure;
    }
    if (!Registry::Insert(record))
    {
        RollbackSeed(record);
        return "lockout_exists";
    }
    TC_LOG_INFO("server", "BotRaidLockout seeded cohort=%s raid=%s map=%u instance=%u difficulty=%s bosses_done=%zu mask=%u respawn_rows=%zu diagnostic_only_assistance=1",
        cohortId.c_str(), record.Raid.c_str(), record.MapId, record.InstanceId,
        DifficultyToken(record.Difficulty).c_str(), record.BossesDone.size(),
        record.CompletedEncounterMask, record.RespawnRows.size());
    return "";
}

std::string ClearLockout(LockoutRecord const& record)
{
    Map* map = sMapMgr->FindMap(record.MapId, record.InstanceId);
    if (map && map->HavePlayers())
        return "lockout_map_has_players";

    Difficulty const difficulty = Difficulty(record.Difficulty);
    if (record.BoundGroupGuid)
        if (Group* group = sGroupMgr->GetGroupByGUID(record.BoundGroupGuid))
            if (InstanceGroupBind* bind = group->GetBoundInstance(difficulty, record.MapId))
                if (bind->save && bind->save->GetInstanceId() == record.InstanceId)
                    group->UnbindInstance(record.MapId, record.Difficulty, true);

    // Offline binds are rows only and are deleted below.
    std::vector<ObjectGuid> boundPlayers;
    {
        std::shared_lock<std::shared_mutex> lock(*HashMapHolder<Player>::GetLock());
        for (auto const& [guid, player] : ObjectAccessor::GetPlayers())
            if (player)
                if (InstancePlayerBind* bind = player->GetBoundInstance(record.MapId, difficulty, true))
                    if (bind->save && bind->save->GetInstanceId() == record.InstanceId)
                        boundPlayers.push_back(guid);
    }
    for (ObjectGuid const& guid : boundPlayers)
        if (Player* player = ObjectAccessor::FindConnectedPlayer(guid))
            player->UnbindInstance(record.MapId, difficulty, true);

    if (InstanceSave* save = sInstanceSaveMgr->GetInstanceSave(record.InstanceId))
        if (save->GetPlayerCount() || save->GetGroupCount())
            return "lockout_still_bound";
    if (!sMapMgr->UnloadEmptyInstance(record.MapId, record.InstanceId))
        return "lockout_map_unload_refused";
    if (sInstanceSaveMgr->GetInstanceSave(record.InstanceId))
        sInstanceSaveMgr->UnloadInstanceSave(record.InstanceId);
    if (sInstanceSaveMgr->GetInstanceSave(record.InstanceId))
        return "lockout_save_unload_refused";

    DeleteRowsSync(record.InstanceId);
    sMapMgr->FreeInstanceId(record.InstanceId);
    TC_LOG_INFO("server", "BotRaidLockout cleared cohort=%s raid=%s map=%u instance=%u",
        record.CohortId.c_str(), record.Raid.c_str(), record.MapId, record.InstanceId);
    return "";
}

std::string ReadbackJson(Readback const& readback)
{
    std::ostringstream json;
    json << "{\"source\":\"" << readback.Source << "\""
         << ",\"map_loaded\":" << (readback.MapLoaded ? "true" : "false")
         << ",\"save_loaded\":" << (readback.SaveLoaded ? "true" : "false")
         << ",\"save_player_binds\":" << readback.SavePlayerBinds
         << ",\"save_group_binds\":" << readback.SaveGroupBinds
         << ",\"db_row_present\":" << (readback.DbRowPresent ? "true" : "false")
         << ",\"db_identity_matches\":" << (readback.DbIdentityMatches ? "true" : "false")
         << ",\"db_completed_encounters_mask\":" << readback.DbCompletedEncounterMask
         << ",\"db_save_data_hex\":\"" << JsonEscape(readback.DbSaveDataHex) << "\""
         << ",\"script_name\":\"" << JsonEscape(readback.ScriptName) << "\""
         << ",\"encounter_count\":" << readback.EncounterCount
         << ",\"boss_states\":" << JsonNumberArray(readback.BossStates)
         << ",\"completed_encounters_mask\":" << readback.CompletedEncounterMask
         << ",\"save_data_hex\":\"" << readback.SaveDataHex << "\""
         << ",\"save_data_matches\":" << (readback.SaveDataMatches ? "true" : "false")
         << ",\"exact_match\":" << (readback.ExactMatch ? "true" : "false")
         << ",\"lockout_intact\":" << (readback.LockoutIntact ? "true" : "false")
         << ",\"extra_done\":" << JsonStringArray(readback.ExtraDone)
         << ",\"missing_done\":" << JsonStringArray(readback.MissingDone)
         << ",\"respawn_rows_loaded\":" << readback.RespawnRowsLoaded
         << ",\"map_players\":" << readback.MapPlayers
         << ",\"doors\":[";
    for (size_t index = 0; index < readback.Doors.size(); ++index)
    {
        DoorObservation const& door = readback.Doors[index];
        json << (index ? "," : "") << "{\"entry\":" << door.Entry
             << ",\"expected_open\":" << (door.ExpectedOpen ? "true" : "false")
             << ",\"observed\":\"" << door.Observed << "\"}";
    }
    json << "],\"failure\":" << (readback.Failure.empty() ? std::string("null")
        : "\"" + JsonEscape(readback.Failure) + "\"") << "}";
    return json.str();
}

std::string RecordFieldsJson(LockoutRecord const& record)
{
    std::ostringstream json;
    json << ",\"raid\":\"" << JsonEscape(record.Raid) << "\""
         << ",\"difficulty\":\"" << DifficultyToken(record.Difficulty) << "\""
         << ",\"difficulty_id\":" << uint32(record.Difficulty)
         << ",\"instance_id\":" << record.InstanceId
         << ",\"map_id\":" << record.MapId
         << ",\"bosses_done\":" << JsonStringArray(record.BossesDone)
         << ",\"boss_indices_done\":" << JsonNumberArray(record.BossIndicesDone)
         << ",\"expected_boss_states\":" << JsonNumberArray(record.ExpectedStates)
         << ",\"completed_encounters_mask\":" << record.CompletedEncounterMask
         << ",\"save_data_hex\":\"" << ToHex(record.SaveData) << "\""
         << ",\"diagnostic_only_assistance\":true"
         << ",\"seeded_at_unix\":" << record.SeededAtUnix
         << ",\"armed_leader_guid\":" << record.ArmedLeaderGuid
         << ",\"bound_group_guid\":" << record.BoundGroupGuid
         << ",\"respawn_rows\":[";
    for (size_t index = 0; index < record.RespawnRows.size(); ++index)
        json << (index ? "," : "") << "{\"spawn_id\":" << record.RespawnRows[index].SpawnId
             << ",\"entry\":" << record.RespawnRows[index].Entry << "}";
    json << "],\"credit_entry_mismatches\":" << JsonStringArray(record.CreditEntryMismatches);
    return json.str();
}
}
