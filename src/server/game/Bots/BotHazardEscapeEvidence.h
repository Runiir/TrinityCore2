#ifndef TRINITY_BOT_HAZARD_ESCAPE_EVIDENCE_H
#define TRINITY_BOT_HAZARD_ESCAPE_EVIDENCE_H

#include <cmath>
#include <cstdint>

namespace BotWorldMovement
{
// A hazard escape must eventually be judged against the hazard that caused the
// intent, not merely against the caller's arbitrary destination. The encounter
// policy captures this immutable snapshot; the native planner currently
// records whether its terrain-resolved endpoint increases planar clearance.
struct HazardEscapeBasis
{
    std::uint64_t HazardGuid = 0;
    float HazardX = 0.0f;
    float HazardY = 0.0f;
    float HazardZ = 0.0f;

    bool Available() const
    {
        return HazardGuid != 0 && std::isfinite(HazardX)
            && std::isfinite(HazardY) && std::isfinite(HazardZ);
    }
};

struct HazardEscapeProgressObservation
{
    bool Available = false;
    std::uint64_t HazardGuid = 0;
    float HazardX = 0.0f;
    float HazardY = 0.0f;
    float HazardZ = 0.0f;
    float ActorClearance = 0.0f;
    float EndpointX = 0.0f;
    float EndpointY = 0.0f;
    float EndpointZ = 0.0f;
    float EndpointClearance = 0.0f;
    float ClearanceProgress = 0.0f;
    float RequiredProgress = 0.0f;
    bool ProofQualified = false;
};
}

#endif
