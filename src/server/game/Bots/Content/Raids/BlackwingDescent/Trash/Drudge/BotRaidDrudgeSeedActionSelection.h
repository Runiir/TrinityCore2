#ifndef TRINITY_BOT_RAID_DRUDGE_SEED_ACTION_SELECTION_H
#define TRINITY_BOT_RAID_DRUDGE_SEED_ACTION_SELECTION_H

#include <cstdint>

namespace BotRaidDrudgeSeedActionSelection
{
// The route records a successful native submission synchronously. Only an
// instant spell can make that result proof that seed threat has landed.
inline bool IsSynchronousSeedAction(std::uint32_t castTimeMs)
{
    return castTimeMs == 0;
}

inline bool HasPositiveThreatDelta(float threatBefore, float threatAfter)
{
    return threatAfter > threatBefore;
}

inline bool PreferSeedAction(bool candidateFound, float maxRange,
    std::uint32_t categoryRank, std::uint16_t sortOrder,
    float selectedMaxRange, std::uint32_t selectedCategoryRank,
    std::uint16_t selectedSortOrder)
{
    if (!candidateFound)
        return true;
    if (maxRange != selectedMaxRange)
        return maxRange > selectedMaxRange;
    if (categoryRank != selectedCategoryRank)
        return categoryRank < selectedCategoryRank;
    return sortOrder < selectedSortOrder;
}
}

#endif
