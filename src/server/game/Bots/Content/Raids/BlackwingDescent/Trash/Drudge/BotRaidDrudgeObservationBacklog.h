#ifndef TRINITY_BOT_RAID_DRUDGE_OBSERVATION_BACKLOG_H
#define TRINITY_BOT_RAID_DRUDGE_OBSERVATION_BACKLOG_H

#include "Define.h"

#include <cstddef>

namespace BotRaidDrudgeObservationBacklog
{
template <typename Observations, typename CloseObservation>
std::size_t CloseLandedThroughProof(Observations& observations,
    uint64 attemptId, uint32 wipeGeneration, uint64 routeGeneration,
    uint64 proofAtMs, CloseObservation&& closeObservation)
{
    std::size_t closed = 0;
    for (auto& observation : observations)
    {
        if (observation.ReseparationRecorded || !observation.Landed
            || observation.AttemptId != attemptId
            || observation.WipeGeneration != wipeGeneration
            || observation.RouteGeneration != routeGeneration
            || observation.ObservedAtMs > proofAtMs)
            continue;

        closeObservation(observation);
        ++closed;
    }
    return closed;
}
}

#endif
