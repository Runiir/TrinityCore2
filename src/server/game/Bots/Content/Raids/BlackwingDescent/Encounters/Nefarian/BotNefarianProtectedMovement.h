#ifndef TRINITY_BOT_NEFARIAN_PROTECTED_MOVEMENT_H
#define TRINITY_BOT_NEFARIAN_PROTECTED_MOVEMENT_H

// Round 7 (review): on Nefarian's End platform the plan's surface legs and
// escapes (TransportSurfaceMove) are admitted outside the native path
// bookkeeping (ActivePathValid) that the shared heal guard reads, and a
// platform hold clears that bookkeeping. The plan publishes them as a movement
// lease instead (BotWorldPopulationMgrNefarianCandidates.cpp): Mechanic for a
// leg or hold, Hazard for a survival escape. While such a lease stands and a
// spline runs, the movement is protected: a heal selects only instant spells
// and no hard cast stops the spline (patch
// .git/round7_patches/nefarian/R7_protected_movement_heal_guard.patch).

#include "Bots/BotMovementArbiter.h"
#include <string_view>

namespace BotEncounter::Nefarian
{
// BotNefarianFacts.h EncounterNodeId (not included: the shared heal code
// needs only this predicate).
inline constexpr std::string_view ProtectedMovementNodeId = "bwd.nefarian.encounter";

inline bool ProtectedMovementActive(BotMovementArbitration::Lease const& lease,
    bool splineRunning, std::string_view routeNodeId, uint64 nowMs)
{
    return routeNodeId == ProtectedMovementNodeId && splineRunning
        && lease.MovementOwner != BotMovementArbitration::Owner::None
        && lease.ExpiresAtMs > nowMs
        && uint8(lease.MovementPriority)
            >= uint8(BotMovementArbitration::Priority::Mechanic);
}
}

#endif
