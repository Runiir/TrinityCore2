#ifndef BOT_RAID_DRUDGE_NATIVE_RUSH_STATE_H
#define BOT_RAID_DRUDGE_NATIVE_RUSH_STATE_H

#include <algorithm>
#include <cstdint>

namespace BotRaidDrudgeNativeRush
{
struct SourceInput
{
    bool ExactTankVictim = false;
    bool IntendedSeedPresent = false;
    bool FarthestIsIntendedSeed = false;
    float TankThreat = 0.0f;
    float HighestOtherThreat = 0.0f;
    float SeedDistance = 0.0f;
    float SecondFarthestDistance = 0.0f;
    float ThreatHeadroomMultiplier = 0.0f;
    float FarthestDistanceMargin = 0.0f;
    std::uint32_t FarthestGuid = 0;
};

struct SourceResult
{
    bool ExactTankVictim = false;
    bool TankThreatSecure = false;
    bool SeedIsUniqueFarthest = false;
    bool Ready = false;
    float TankThreat = 0.0f;
    float HighestOtherThreat = 0.0f;
    float SeedDistance = 0.0f;
    float SecondFarthestDistance = 0.0f;
    std::uint32_t FarthestGuid = 0;
};

inline SourceResult Evaluate(SourceInput const& input)
{
    SourceResult result;
    result.ExactTankVictim = input.ExactTankVictim;
    result.TankThreat = input.TankThreat;
    result.HighestOtherThreat = input.HighestOtherThreat;
    result.SeedDistance = input.SeedDistance;
    result.SecondFarthestDistance = input.SecondFarthestDistance;
    result.FarthestGuid = input.FarthestGuid;
    result.TankThreatSecure = input.ExactTankVictim
        && input.ThreatHeadroomMultiplier >= 1.3f
        && input.TankThreat > 0.0f
        && input.TankThreat >= input.HighestOtherThreat
            * input.ThreatHeadroomMultiplier;
    result.SeedIsUniqueFarthest = input.IntendedSeedPresent
        && input.FarthestIsIntendedSeed && input.SeedDistance > 0.0f
        && input.SeedDistance >= input.SecondFarthestDistance
            + std::max(0.0f, input.FarthestDistanceMargin);
    result.Ready = result.ExactTankVictim && result.TankThreatSecure
        && result.SeedIsUniqueFarthest;
    return result;
}

// Seed DoTs and required friendly support continue to create native threat
// after a single readiness snapshot.  Until the first scoped Rush is actually
// observed, authority requires the exact tank victim, secure threat headroom,
// and the unique intended seed.  After that native proof, exact live tank
// ownership is sufficient to release the global offense barrier; the normal
// lane ownership gate remains authoritative if the victim changes.
inline bool ShouldBuildTankThreat(bool currentScopeHasNativeRush,
    SourceResult const& readiness)
{
    return !currentScopeHasNativeRush || !readiness.TankThreatSecure;
}

// The configured seed establishes one attributable native Rush. The boolean
// is supplied only by the caller's exact attempt/wipe/route observation scan.
// Before that observation, retain all seed and threat predicates. After it,
// retain only exact native tank ownership so a low-headroom snapshot cannot
// suppress every safe lane action, while a wrong victim still blocks.
inline bool AuthorityReady(bool currentScopeHasNativeRush,
    SourceResult const& readiness)
{
    return readiness.ExactTankVictim
        && (currentScopeHasNativeRush
            || (readiness.TankThreatSecure && readiness.SeedIsUniqueFarthest));
}

// Before the first scoped Rush, both live lanes must retain their assigned
// native victims.  After that proof, admission is lane-local: a wrong victim
// suppresses only that lane while an exact peer lane may continue.  A dead
// peer remains acceptable because the existing one-source rage/evidence path
// owns that terminal transition.
inline bool LaneOwnershipSafe(bool currentScopeHasNativeRush,
    bool currentExactTankVictim, bool otherSourceAlive,
    bool otherExactTankVictim)
{
    return currentExactTankVictim
        && (!otherSourceAlive || currentScopeHasNativeRush
            || otherExactTankVictim);
}
}

#endif
