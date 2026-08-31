#ifndef TRINITY_BOT_MAGMAW_MOBILITY_RESERVATION_H
#define TRINITY_BOT_MAGMAW_MOBILITY_RESERVATION_H

#include "Bots/BotEncounterBlackboard.h"

namespace BotEncounter
{
enum class MagmawMobilityDecision : uint8
{
    AllowRoutine,
    AllowEmergency,
    ReserveForMassiveCrash,
    ReserveMissingNativeTimer
};

inline MagmawMobilityDecision EvaluateMagmawMobilityReservation(
    MechanicTimerSnapshot const* timer, uint32 nativeReuseCooldownMs,
    bool emergencyParasiteClearance)
{
    if (emergencyParasiteClearance)
        return MagmawMobilityDecision::AllowEmergency;
    if (!timer || timer->RemainingMs == std::numeric_limits<uint32>::max())
        return MagmawMobilityDecision::ReserveMissingNativeTimer;
    if (timer->SequenceActive || timer->RemainingMs < nativeReuseCooldownMs)
        return MagmawMobilityDecision::ReserveForMassiveCrash;
    return MagmawMobilityDecision::AllowRoutine;
}
}

#endif
