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
}

#endif
