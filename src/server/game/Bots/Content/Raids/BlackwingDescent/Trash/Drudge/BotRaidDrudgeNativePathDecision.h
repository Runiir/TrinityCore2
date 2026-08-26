#ifndef TRINITY_BOT_RAID_DRUDGE_NATIVE_PATH_DECISION_H
#define TRINITY_BOT_RAID_DRUDGE_NATIVE_PATH_DECISION_H

#include <cstdint>

namespace BotRaidDrudgeNativePath
{
constexpr float ExactEndpointTolerance2dYards = 0.25f;
constexpr float ExactEndpointToleranceZYards = 1.0f;

enum class PostFloorDecision : std::uint8_t
{
    Accepted,
    NativeEndpointRejected,
    SourceUnionRejected,
};

// Completeness and floor admission are evaluated by the native path caller
// first. This seam keeps the exact-end diagnostic ahead of source-union path
// safety without changing either safety predicate. The source-union callback
// is deliberately lazy so an endpoint miss never evaluates that predicate.
template <typename SourceUnionPredicate>
inline PostFloorDecision EvaluatePostFloor(
    bool requireExactEnd, bool requireSourceUnionSafety,
    float end2d, float endZ, SourceUnionPredicate&& sourceUnionSafe)
{
    if (requireExactEnd
        && (end2d > ExactEndpointTolerance2dYards
            || endZ > ExactEndpointToleranceZYards))
        return PostFloorDecision::NativeEndpointRejected;
    if (requireSourceUnionSafety && !sourceUnionSafe())
        return PostFloorDecision::SourceUnionRejected;
    return PostFloorDecision::Accepted;
}
}

#endif
