#include "Bots/BotRaidLockoutRegistry.h"

#include "Group.h"
#include "InstanceSaveMgr.h"
#include "Log.h"

#include <algorithm>
#include <map>
#include <mutex>

namespace BotRaidLockout
{
namespace
{
std::mutex RegistryLock;
std::map<std::string, LockoutRecord> Records;
}

bool Registry::Find(std::string const& cohortId, LockoutRecord& record)
{
    std::lock_guard<std::mutex> guard(RegistryLock);
    auto const itr = Records.find(cohortId);
    if (itr == Records.end())
        return false;
    record = itr->second;
    return true;
}

bool Registry::Insert(LockoutRecord const& record)
{
    std::lock_guard<std::mutex> guard(RegistryLock);
    return Records.emplace(record.CohortId, record).second;
}

void Registry::Erase(std::string const& cohortId)
{
    std::lock_guard<std::mutex> guard(RegistryLock);
    Records.erase(cohortId);
}

bool Registry::Arm(std::string const& cohortId, uint32 leaderGuid)
{
    std::lock_guard<std::mutex> guard(RegistryLock);
    auto const itr = Records.find(cohortId);
    if (itr == Records.end() || !leaderGuid)
        return false;
    for (auto const& [id, record] : Records)
        if (id != cohortId && record.ArmedLeaderGuid == leaderGuid)
            return false;
    itr->second.ArmedLeaderGuid = leaderGuid;
    itr->second.BoundGroupGuid = 0;
    return true;
}

void Registry::Disarm(std::string const& cohortId)
{
    std::lock_guard<std::mutex> guard(RegistryLock);
    auto const itr = Records.find(cohortId);
    if (itr != Records.end())
        itr->second.ArmedLeaderGuid = 0;
}

void Registry::SetBoundGroup(std::string const& cohortId, uint32 groupGuid)
{
    std::lock_guard<std::mutex> guard(RegistryLock);
    auto const itr = Records.find(cohortId);
    if (itr != Records.end())
        itr->second.BoundGroupGuid = groupGuid;
}

bool Registry::HasInstance(uint32 instanceId)
{
    std::lock_guard<std::mutex> guard(RegistryLock);
    for (auto const& [id, record] : Records)
        if (record.InstanceId == instanceId)
            return true;
    return false;
}

void BindArmedSeedGroup(uint32 leaderGuid, Group* seed, uint32 placementMapId)
{
    if (!leaderGuid || !seed)
        return;

    LockoutRecord record;
    {
        std::lock_guard<std::mutex> guard(RegistryLock);
        auto const itr = std::find_if(Records.begin(), Records.end(),
            [leaderGuid](std::pair<std::string const, LockoutRecord> const& entry)
            {
                return entry.second.ArmedLeaderGuid == leaderGuid;
            });
        if (itr == Records.end())
            return;
        record = itr->second;
    }

    // The save normally exists: the seeder and admission both (re)load it.
    // Re-adding from the persisted identity mirrors Player::_LoadBoundInstances
    // for a permanent bind (canReset = false, no database write).
    InstanceSave* save = sInstanceSaveMgr->GetInstanceSave(record.InstanceId);
    if (!save)
        save = sInstanceSaveMgr->AddInstanceSave(record.MapId, record.InstanceId,
            Difficulty(record.Difficulty), 0, false, true);
    if (!save || save->GetMapId() != placementMapId || save->GetMapId() != record.MapId
        || uint8(save->GetDifficulty()) != record.Difficulty
        || uint8(seed->GetDifficulty(true)) != record.Difficulty)
    {
        // Admission's readback rejects the resulting fresh instance and rolls
        // the cohort back; nothing here may silently substitute another save.
        TC_LOG_ERROR("server", "BotRaidLockout seed group bind rejected cohort=%s leader=%u group=%s instance=%u map=%u placement_map=%u difficulty=%u group_difficulty=%u save=%u",
            record.CohortId.c_str(), leaderGuid, seed->GetGUID().ToString().c_str(), record.InstanceId,
            record.MapId, placementMapId, uint32(record.Difficulty), uint32(seed->GetDifficulty(true)),
            save ? 1u : 0u);
        return;
    }

    seed->BindToInstance(save, true);
    Registry::SetBoundGroup(record.CohortId, seed->GetGUID().GetCounter());
    TC_LOG_INFO("server", "BotRaidLockout seed group bound cohort=%s leader=%u group=%s instance=%u map=%u difficulty=%u permanent=1",
        record.CohortId.c_str(), leaderGuid, seed->GetGUID().ToString().c_str(), record.InstanceId,
        record.MapId, uint32(record.Difficulty));
}
}
