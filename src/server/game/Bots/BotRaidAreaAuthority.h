#ifndef TRINITY_BOT_RAID_AREA_AUTHORITY_H
#define TRINITY_BOT_RAID_AREA_AUTHORITY_H

#include "Define.h"
#include <mutex>
#include <unordered_set>

namespace BotRaidAreaAuthority
{
inline std::mutex SuppressedOwnersMutex;
inline std::unordered_set<uint64> SuppressedOwners;

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
}

#endif
