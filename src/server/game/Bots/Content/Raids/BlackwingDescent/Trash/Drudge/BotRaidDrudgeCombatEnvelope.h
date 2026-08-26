#ifndef TRINITY_BOT_RAID_DRUDGE_COMBAT_ENVELOPE_H
#define TRINITY_BOT_RAID_DRUDGE_COMBAT_ENVELOPE_H

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <vector>

namespace BotRaidDrudgeCombatEnvelope
{
struct Point2d
{
    float X = 0.0f;
    float Y = 0.0f;
};

struct Assignment
{
    bool ConfiguredSeedMember = false;
    Point2d AssignedLiveSource;
    float MaxRangeYards = 0.0f;
};

inline bool Accepts(Assignment const& assignment, Point2d const& member)
{
    if (!assignment.ConfiguredSeedMember)
        return true;
    if (!std::isfinite(assignment.MaxRangeYards)
        || assignment.MaxRangeYards <= 0.0f
        || !std::isfinite(member.X) || !std::isfinite(member.Y)
        || !std::isfinite(assignment.AssignedLiveSource.X)
        || !std::isfinite(assignment.AssignedLiveSource.Y))
        return false;
    float const dx = member.X - assignment.AssignedLiveSource.X;
    float const dy = member.Y - assignment.AssignedLiveSource.Y;
    return dx * dx + dy * dy
        <= assignment.MaxRangeYards * assignment.MaxRangeYards;
}

inline bool ContainsSlot(std::vector<std::uint32_t> const& slots,
    std::uint32_t slot)
{
    return std::find(slots.begin(), slots.end(), slot) != slots.end();
}

inline bool AcceptsConfiguredSeed(
    std::uint32_t slot,
    std::vector<std::uint32_t> const& seedSlots,
    std::vector<std::uint32_t> const& laneASlots,
    std::vector<std::uint32_t> const& laneBSlots,
    Point2d const& source0, Point2d const& source1, float maxRangeYards,
    Point2d const& member)
{
    if (!ContainsSlot(seedSlots, slot))
        return true;
    bool const laneA = ContainsSlot(laneASlots, slot);
    bool const laneB = ContainsSlot(laneBSlots, slot);
    if (laneA == laneB)
        return false;
    return Accepts({ true, laneA ? source0 : source1, maxRangeYards }, member);
}

inline char const* RejectionReason()
{
    return "drudge_anchor_combat_range_unsafe";
}
}

#endif
