#ifndef TRINITY_BOT_MAGMAW_TRANSFER_LANE_AUTHORITY_H
#define TRINITY_BOT_MAGMAW_TRANSFER_LANE_AUTHORITY_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMovementIntents.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneNativeOutcome.h"

namespace BotEncounter
{
struct MagmawTransferLaneAuthoritySelection
{
    MagmawMovementIntentCollection Movements;
    std::optional<BotNativeAction::Candidate> Movement;
    MagmawTransferLaneIntentComparison Comparison;
    std::optional<MagmawTransferLaneExecutionBinding> Binding;
    bool TaskAuthorityRequested = false;
    bool TaskAuthoritySelected = false;
};

MagmawTransferLaneAuthoritySelection SelectMagmawTransferLaneAuthority(
    bool taskAuthorityEnabled,
    std::vector<MagmawTransferLaneTask> const& tasks, ObjectGuid actor,
    MagmawMovementIntentCollection const& legacyMovements,
    uint64 legacyTransitionGeneration);

MagmawTransferLaneAuthoritySelection SelectMagmawTransferLaneAuthority(
    bool taskAuthorityEnabled,
    std::vector<MagmawTransferLaneTask> const& tasks, ObjectGuid actor,
    std::optional<BotNativeAction::Candidate> const& legacy,
    uint64 legacyTransitionGeneration);

MagmawTransferLaneNativeOutcome BindMagmawTransferLaneNativeOutcome(
    MagmawTransferLaneExecutionBinding const& binding,
    BotWorldMovement::ExecutionObservation const& movement,
    uint64 observedAtMs);
}

#endif
