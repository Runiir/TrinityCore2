#ifndef TRINITY_BOT_RAID_FIRE_COMBUSTION_PATIENCE_H
#define TRINITY_BOT_RAID_FIRE_COMBUSTION_PATIENCE_H

#include "Bots/BotCanonicalRaidScope.h"
#include "Define.h"

#include <chrono>
#include <mutex>
#include <string>
#include <string_view>
#include <unordered_map>

// Canonical-composition raid Fire mages only (the admission's
// canonicalRaidScope): when Combustion may spend its two-minute cooldown.
//
// The Phase 8 gate casts at the first decision with a 10k Ignite tick, Living
// Bomb and a Pyroblast DoT. In BWD round 1 that was both too eager and too
// strict. Magmaw cast at the first pass with a 27-30k Ignite (431-469k
// Combustion per kill; the accepted Magmaw verdict b5-d1898555 cast on a
// 62-69k Ignite for 0.94-1.43M). Maloriak cast 3-4 Hot Streak Pyroblasts per
// kill, so the three-DoT window never opened (no Combustion in 185 s).
//
// In a canonical raid the Pyroblast DoT is optional, and once the rest of the
// window is open Combustion waits for a strong Ignite tick, for at most the
// patience budget. The clock starts the first time a bot reaches this gate
// with the cooldown ready and restarts after a gap longer than any cast or
// channel, i.e. after Combustion went on cooldown or the window was lost.
namespace BotRaidFireCombustionPatience
{
inline constexpr int32 StrongIgniteTick = 40000;
inline constexpr uint64 PatienceMs = 15000;
inline constexpr uint64 StaleGapMs = 10000;
inline constexpr char const* WaitReason = "combustion_ignite_patience";

struct Window
{
    uint64 FirstMs = 0;
    uint64 LastMs = 0;
};

inline std::mutex Mutex;
// Owner raw GUID -> the open-window clock.
inline std::unordered_map<uint64, Window> Windows;

inline uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
}

// The admission's scope: a raid-map cohort of a canonical composition. The
// legacy accepted Magmaw Fire mages 30006/30007 keep every Phase 8 gate.
inline bool CanonicalScope(bool raidRotationScope, std::string_view scenarioId)
{
    return raidRotationScope && BotCanonicalRaidScope::IsCanonicalCompositionScenario(scenarioId);
}

// Called only when every other part of the window is open. True admits the
// cast; false keeps waiting for a stronger Ignite.
inline bool Ready(uint64 ownerGuid, int32 igniteTick, uint64 nowMs)
{
    std::lock_guard<std::mutex> guard(Mutex);
    Window& window = Windows[ownerGuid];
    if (!window.FirstMs || nowMs < window.LastMs || nowMs - window.LastMs > StaleGapMs)
        window.FirstMs = nowMs;
    window.LastMs = nowMs;
    return igniteTick >= StrongIgniteTick || nowMs - window.FirstMs >= PatienceMs;
}

// The admission gate: true (and the rejection) while the open window waits.
inline bool Waits(uint64 ownerGuid, int32 igniteTick, std::string& rejectReason)
{
    if (Ready(ownerGuid, igniteTick, NowMs()))
        return false;
    rejectReason = WaitReason;
    return true;
}
}

#endif
