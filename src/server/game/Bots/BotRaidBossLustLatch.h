#ifndef TRINITY_BOT_RAID_BOSS_LUST_LATCH_H
#define TRINITY_BOT_RAID_BOSS_LUST_LATCH_H

#include "ObjectGuid.h"

// The raid latch of the canonical boss lust fallback (BotRaidBossLust.h),
// kept in RaidRuntime. One native cast per attempt, wipe and route node; the
// native spell, GCD and lockout gates stay authoritative.
namespace BotRaidBossLust
{
// The main tank has held the boss this long before the lust is cast.
constexpr uint64 TankHoldMs = 5000;

struct Latch
{
    uint64 AttemptId = 0;
    uint64 WipeGeneration = 0;
    uint64 RouteGeneration = 0;
    bool Holding = false;
    ObjectGuid HoldBossGuid;
    ObjectGuid HoldTankGuid;
    uint64 HoldSinceMs = 0;
    bool Submitted = false;
    uint64 SubmittedAtMs = 0;
    uint32 SubmittedSpellId = 0;
};

// A new attempt, wipe or route node starts a fresh latch.
inline void Rebind(Latch& latch, uint64 attemptId, uint64 wipeGeneration,
    uint64 routeGeneration)
{
    if (latch.AttemptId == attemptId && latch.WipeGeneration == wipeGeneration
        && latch.RouteGeneration == routeGeneration)
        return;
    latch = Latch();
    latch.AttemptId = attemptId;
    latch.WipeGeneration = wipeGeneration;
    latch.RouteGeneration = routeGeneration;
}

// The same boss on the same living tank, observed continuously. Any other
// pair (a tank swap, a new construct) restarts the hold; no pair ends it.
inline void ObserveTankHold(Latch& latch, ObjectGuid bossGuid,
    ObjectGuid tankGuid, uint64 nowMs)
{
    if (bossGuid.IsEmpty() || tankGuid.IsEmpty())
    {
        latch.Holding = false;
        latch.HoldBossGuid = ObjectGuid();
        latch.HoldTankGuid = ObjectGuid();
        latch.HoldSinceMs = 0;
        return;
    }
    if (latch.Holding && latch.HoldBossGuid == bossGuid
        && latch.HoldTankGuid == tankGuid)
        return;
    latch.Holding = true;
    latch.HoldBossGuid = bossGuid;
    latch.HoldTankGuid = tankGuid;
    latch.HoldSinceMs = nowMs;
}

inline bool TankHeld(Latch const& latch, uint64 nowMs)
{
    return latch.Holding && nowMs >= latch.HoldSinceMs
        && nowMs - latch.HoldSinceMs >= TankHoldMs;
}
}

#endif
