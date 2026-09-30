#ifndef TRINITY_BOT_NEFARIAN_PLATFORM_BODY_H
#define TRINITY_BOT_NEFARIAN_PLATFORM_BODY_H

// The inside of the elevator's collision model (round 3).
//
// GO 207834's model (Blackwingv2_Elevator_Onyxia_Transport.wmo.vmo, ported in
// tests/test_nefarian_ledge_drop_floor_query.py) is a closed body: the walk
// surface on top (flat centre, ramp, ring), a bottom at local z -8.666 under
// all of it, and an outer wall at 69.6-71.2 yards from the centre. The three
// pillars are hollow shafts open into that body: under a pillar top the
// first surface below is the bottom, and horizontally the pillar wall (local
// 2.2-9.2) closes the shaft on every heading. tests/test_nefarian_stranded.py
// pins those rays.
//
// Round 2 (every run): the rogue and both tanks sat inside a pillar shaft,
// within 1.5 yards of its centre at local z 3-4, six yards under the magma.
// Only a movement that never proves its path gets there (native chase toward
// the prototype on the top); every lawful exit is refused by the same
// collision the core proves (a swim or a jump through the wall or the top
// from inside is not line of sight, and nothing under the shaft is a floor
// until the bottom). The plan names the state instead of proposing a step
// the executors must refuse every decision, and the pillar hold keeps native
// movement from making it worse. How to recover such a member lawfully is a
// user decision (round 3 handoff, needs_user_decision).

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianMagma.h"
#include <algorithm>

namespace BotEncounter::Nefarian
{
constexpr float PlatformUndersideLocalZ = -8.666f;
constexpr float PlatformBodyRadius = 69.5f;
// Feet this far under a surface are inside the body, not standing on it (the
// surface walk's own floor tolerance).
constexpr float InsideSurfaceMarginYards = 0.6f;
// Inside the pillar wall on every heading at every height (the model's wall
// comes within 4.73 yards of a centre near the skirt; tests pin it).
constexpr float PillarShaftRadius = 4.6f;

// The lowest pillar surface over every slot heading at `radius` yards from
// the pillar's centre (conservative: a member below it is below the surface
// on every heading).
inline float PillarSurfaceLowest(uint8 pillar, float radius)
{
    float lowest = PlatformFrame::PillarTopLocalZ;
    for (uint8 slot = 0; slot < 6; ++slot)
        lowest = std::min(lowest, PillarSurfaceEnvelope(pillar, slot, radius));
    return lowest;
}

// Inside a pillar's hollow shaft: within its wall and clearly under its top
// or rim, above the body's bottom.
inline bool InsidePillarShaft(LocalPoint local, float localZ)
{
    float distance = 0.0f;
    int const pillar = NearestPillar(local, distance);
    if (distance >= PillarShaftRadius || localZ <= PlatformUndersideLocalZ)
        return false;
    return localZ < PillarSurfaceLowest(uint8(pillar), distance) - InsideSurfaceMarginYards;
}

// Under the walk surface, inside the body (away from every pillar skirt).
inline bool InsidePlatformBody(LocalPoint local, float localZ)
{
    float distance = 0.0f;
    NearestPillar(local, distance);
    if (distance <= PillarSkirtRadius + 0.5f || Length(local) >= PlatformBodyRadius
        || localZ <= PlatformUndersideLocalZ)
        return false;
    return localZ < FloorLocalZAt(local) - InsideSurfaceMarginYards;
}
}

#endif
