#ifndef TRINITY_BOT_RAID_AREA_AUTHORITY_H
#define TRINITY_BOT_RAID_AREA_AUTHORITY_H

#include "Define.h"
#include <mutex>
#include <unordered_map>
#include <unordered_set>
#include <vector>

namespace BotRaidAreaAuthority
{
inline std::mutex SuppressedOwnersMutex;
inline std::unordered_set<uint64> SuppressedOwners;
inline std::unordered_set<uint64> AllOffenseSuppressedOwners;
inline std::unordered_map<uint64, std::unordered_set<uint32>> ProtectedEncounterEntriesByOwner;
inline std::unordered_map<uint64, std::unordered_set<uint32>> ProtectedEncounterSpawnIdsByOwner;
inline std::unordered_map<uint64, std::unordered_set<uint64>> AllowedEncounterGuidsByOwner;

inline void Set(uint64 ownerGuid, bool suppressed)
{
    if (!ownerGuid)
        return;
    std::lock_guard<std::mutex> guard(SuppressedOwnersMutex);
    if (suppressed)
        SuppressedOwners.insert(ownerGuid);
    else
        SuppressedOwners.erase(ownerGuid);
}

inline bool IsSuppressed(uint64 ownerGuid)
{
    std::lock_guard<std::mutex> guard(SuppressedOwnersMutex);
    return SuppressedOwners.find(ownerGuid) != SuppressedOwners.end();
}

inline void SetAllOffenseSuppressed(uint64 ownerGuid, bool suppressed)
{
    if (!ownerGuid)
        return;
    std::lock_guard<std::mutex> guard(SuppressedOwnersMutex);
    if (suppressed)
        AllOffenseSuppressedOwners.insert(ownerGuid);
    else
        AllOffenseSuppressedOwners.erase(ownerGuid);
}

inline bool IsAllOffenseSuppressed(uint64 ownerGuid)
{
    std::lock_guard<std::mutex> guard(SuppressedOwnersMutex);
    return AllOffenseSuppressedOwners.find(ownerGuid) != AllOffenseSuppressedOwners.end();
}

inline void SetProtectedEncounterEntries(uint64 ownerGuid, std::vector<uint32> const& entries)
{
    if (!ownerGuid)
        return;
    std::lock_guard<std::mutex> guard(SuppressedOwnersMutex);
    if (entries.empty())
    {
        ProtectedEncounterEntriesByOwner.erase(ownerGuid);
        return;
    }
    ProtectedEncounterEntriesByOwner[ownerGuid] =
        std::unordered_set<uint32>(entries.begin(), entries.end());
}

inline bool HasProtectedEncounterEntries(uint64 ownerGuid)
{
    std::lock_guard<std::mutex> guard(SuppressedOwnersMutex);
    auto entryItr = ProtectedEncounterEntriesByOwner.find(ownerGuid);
    if (entryItr != ProtectedEncounterEntriesByOwner.end() && !entryItr->second.empty())
        return true;
    auto spawnItr = ProtectedEncounterSpawnIdsByOwner.find(ownerGuid);
    return spawnItr != ProtectedEncounterSpawnIdsByOwner.end() && !spawnItr->second.empty();
}

inline bool IsProtectedEncounterEntry(uint64 ownerGuid, uint32 entry)
{
    if (!entry)
        return false;
    std::lock_guard<std::mutex> guard(SuppressedOwnersMutex);
    auto itr = ProtectedEncounterEntriesByOwner.find(ownerGuid);
    return itr != ProtectedEncounterEntriesByOwner.end()
        && itr->second.find(entry) != itr->second.end();
}

inline void SetProtectedEncounterSpawnIds(uint64 ownerGuid, std::vector<uint32> const& spawnIds)
{
    if (!ownerGuid)
        return;
    std::lock_guard<std::mutex> guard(SuppressedOwnersMutex);
    if (spawnIds.empty())
    {
        ProtectedEncounterSpawnIdsByOwner.erase(ownerGuid);
        return;
    }
    ProtectedEncounterSpawnIdsByOwner[ownerGuid] =
        std::unordered_set<uint32>(spawnIds.begin(), spawnIds.end());
}

inline void SetAllowedEncounterGuids(uint64 ownerGuid, std::vector<uint64> const& guids)
{
    if (!ownerGuid)
        return;
    std::lock_guard<std::mutex> guard(SuppressedOwnersMutex);
    if (guids.empty())
    {
        AllowedEncounterGuidsByOwner.erase(ownerGuid);
        return;
    }
    AllowedEncounterGuidsByOwner[ownerGuid] =
        std::unordered_set<uint64>(guids.begin(), guids.end());
}

inline bool IsProtectedEncounterTarget(uint64 ownerGuid, uint32 entry, uint32 spawnId, uint64 rawGuid)
{
    if (!ownerGuid)
        return false;
    std::lock_guard<std::mutex> guard(SuppressedOwnersMutex);
    auto allowedItr = AllowedEncounterGuidsByOwner.find(ownerGuid);
    if (allowedItr != AllowedEncounterGuidsByOwner.end()
        && allowedItr->second.find(rawGuid) != allowedItr->second.end())
        return false;

    auto entryItr = ProtectedEncounterEntriesByOwner.find(ownerGuid);
    if (entryItr != ProtectedEncounterEntriesByOwner.end()
        && entryItr->second.find(entry) != entryItr->second.end())
        return true;
    auto spawnItr = ProtectedEncounterSpawnIdsByOwner.find(ownerGuid);
    return spawnItr != ProtectedEncounterSpawnIdsByOwner.end()
        && spawnItr->second.find(spawnId) != spawnItr->second.end();
}

inline void Clear(uint64 ownerGuid)
{
    if (!ownerGuid)
        return;
    std::lock_guard<std::mutex> guard(SuppressedOwnersMutex);
    SuppressedOwners.erase(ownerGuid);
    AllOffenseSuppressedOwners.erase(ownerGuid);
    ProtectedEncounterEntriesByOwner.erase(ownerGuid);
    ProtectedEncounterSpawnIdsByOwner.erase(ownerGuid);
    AllowedEncounterGuidsByOwner.erase(ownerGuid);
}
}

#endif
