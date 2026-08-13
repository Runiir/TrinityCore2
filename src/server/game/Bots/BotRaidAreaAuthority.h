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
    auto itr = ProtectedEncounterEntriesByOwner.find(ownerGuid);
    return itr != ProtectedEncounterEntriesByOwner.end() && !itr->second.empty();
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

inline void Clear(uint64 ownerGuid)
{
    if (!ownerGuid)
        return;
    std::lock_guard<std::mutex> guard(SuppressedOwnersMutex);
    SuppressedOwners.erase(ownerGuid);
    AllOffenseSuppressedOwners.erase(ownerGuid);
    ProtectedEncounterEntriesByOwner.erase(ownerGuid);
}
}

#endif
