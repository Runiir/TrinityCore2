#ifndef TRINITY_BOT_RAID_DRUDGE_HEALTH_SYNC_H
#define TRINITY_BOT_RAID_DRUDGE_HEALTH_SYNC_H

namespace BotRaidDrudgeHealthSync
{
// UnitHealthPct is a normalized ratio, not a 0..100 percentage.  Keep the
// normal lane tolerance wide enough for ordinary asynchronous damage updates,
// while tightening it when either source is near death.
constexpr float NormalTolerance = 0.05f;
constexpr float NearDeathTolerance = 0.01f;
constexpr float NearDeathCutoff = 0.10f;
constexpr float ComparisonEpsilon = 0.000001f;

inline bool ShouldHoldLowerLane(float lowerHealthRatio, float peerHealthRatio)
{
    if (lowerHealthRatio >= peerHealthRatio)
        return false;

    bool const nearDeath = lowerHealthRatio <= NearDeathCutoff
        || peerHealthRatio <= NearDeathCutoff;
    float const tolerance = nearDeath ? NearDeathTolerance : NormalTolerance;
    return peerHealthRatio - lowerHealthRatio > tolerance + ComparisonEpsilon;
}
}

#endif
