#ifndef TRINITY_BOT_MAGMAW_TRANSFER_LANE_NATIVE_OUTCOME_H
#define TRINITY_BOT_MAGMAW_TRANSFER_LANE_NATIVE_OUTCOME_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotWorldPopulationMgrMovement.h"

#include <string>

namespace BotEncounter
{
enum class MagmawTransferLaneAuthoritySource : uint8
{
    Legacy,
    Task
};

// Immutable join between one persistent task and the exact candidate selected
// for native execution. Legacy authority can still carry this binding after
// equivalence has been proven; enabling task authority changes only Source and
// the selected candidate generation.
struct MagmawTransferLaneExecutionBinding
{
    std::string ScopeKey;
    ObjectGuid Actor;
    uint64 EpisodeGeneration = 0;
    uint64 TaskGeneration = 0;
    uint64 LegacyTransitionGeneration = 0;
    MagmawTransferLaneAuthoritySource Source =
        MagmawTransferLaneAuthoritySource::Legacy;
    std::string CandidateKey;
    Vector3 Destination;
};

struct MagmawTransferLaneNativeOutcome
{
    MagmawTransferLaneExecutionBinding Binding;
    BotWorldMovement::ExecutionObservation Movement;
    uint64 ObservedAtMs = 0;
};
}

#endif
