#ifndef TRINITY_BOT_RAID_DRUDGE_NATIVE_ANCHOR_H
#define TRINITY_BOT_RAID_DRUDGE_NATIVE_ANCHOR_H

#include "Map.h"

#include <cmath>

class PhaseShift;

namespace BotRaidDrudgeNativeAnchor
{
// Dynamic recovery points are generated in two dimensions. Resolve their
// native floor before strict path admission so the path and MotionMaster
// receive the same three-dimensional endpoint.
inline bool ResolveFloorZ(Map* map, PhaseShift const& phaseShift,
    float x, float y, float hintZ, float* floorZ)
{
    if (!map || !floorZ)
        return false;
    float const resolved = map->GetHeight(phaseShift, x, y, hintZ + 2.0f,
        true, 8.0f);
    if (resolved <= INVALID_HEIGHT || !std::isfinite(resolved))
        return false;
    *floorZ = resolved;
    return true;
}

inline bool ResolveDynamicCandidateZ(Map* map, PhaseShift const& phaseShift,
    float candidateX, float candidateY, float declaredZ, float* candidateZ)
{
    if (!candidateZ)
        return false;
    if (!ResolveFloorZ(map, phaseShift, candidateX, candidateY, declaredZ,
            candidateZ))
        return false;
    return std::fabs(*candidateZ - declaredZ) <= 4.0f;
}
}

#endif
