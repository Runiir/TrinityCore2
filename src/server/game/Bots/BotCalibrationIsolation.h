#ifndef TRINITY_BOT_CALIBRATION_ISOLATION_H
#define TRINITY_BOT_CALIBRATION_ISOLATION_H

#include <array>
#include <cstdint>

namespace BotCalibrationIsolation
{
// These IDs are deliberately outside the DB phase range used by the checked
// Cataclysm data.  The runtime still rejects a DBC collision before leasing
// either ID, so a data change fails closed instead of sharing a phase.
inline constexpr std::array<std::uint16_t, 2> ReservedPhaseIds = {
    32512, 32513
};

struct PhaseLease
{
    std::uint16_t PhaseId = 0;
    std::uint64_t AttemptId = 0;
    bool Held = false;
};

struct PhaseAllocation
{
    std::uint16_t PhaseId = 0;
    std::uint8_t Slot = 0xff;
    bool NativeCollision = false;
    bool Exhausted = false;

    explicit operator bool() const { return PhaseId != 0; }
};

template <typename IsOccupied, typename IsNativePhaseDefined>
PhaseAllocation AcquirePhase(IsOccupied&& isOccupied,
    IsNativePhaseDefined&& isNativePhaseDefined)
{
    bool nativeCollision = false;
    bool occupied = false;
    for (std::uint8_t slot = 0; slot < ReservedPhaseIds.size(); ++slot)
    {
        std::uint16_t const phaseId = ReservedPhaseIds[slot];
        if (isNativePhaseDefined(phaseId))
        {
            nativeCollision = true;
            continue;
        }
        if (isOccupied(phaseId))
        {
            occupied = true;
            continue;
        }
        return { phaseId, slot, false, false };
    }

    return { 0, 0xff, nativeCollision, !nativeCollision && occupied };
}

template <typename Lease>
inline void Hold(Lease& lease, PhaseAllocation allocation,
    std::uint64_t attemptId)
{
    lease.PhaseId = allocation.PhaseId;
    lease.AttemptId = attemptId;
    lease.Held = bool(allocation);
}

template <typename Lease>
inline void Release(Lease& lease)
{
    lease = {};
}

template <typename HasPhase>
struct PhaseObservation
{
    std::uint16_t ExpectedPhaseId = 0;
    std::uint16_t ObservedPhaseId = 0;
    bool ForeignPhase = false;
    bool Present = false;

    bool Matches() const
    {
        return ExpectedPhaseId != 0 && Present && !ForeignPhase
            && ObservedPhaseId == ExpectedPhaseId;
    }
};

template <typename HasPhase>
PhaseObservation<HasPhase> Observe(std::uint16_t expectedPhaseId,
    HasPhase&& hasPhase)
{
    PhaseObservation<HasPhase> observation;
    observation.ExpectedPhaseId = expectedPhaseId;
    for (std::uint16_t const phaseId : ReservedPhaseIds)
        if (hasPhase(phaseId))
        {
            if (!observation.ObservedPhaseId)
                observation.ObservedPhaseId = phaseId;
            observation.Present = true;
            if (phaseId != expectedPhaseId)
                observation.ForeignPhase = true;
        }
    return observation;
}
}

#endif
