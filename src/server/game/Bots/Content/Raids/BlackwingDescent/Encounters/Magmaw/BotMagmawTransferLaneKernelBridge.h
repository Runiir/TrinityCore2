#ifndef TRINITY_BOT_MAGMAW_TRANSFER_LANE_KERNEL_BRIDGE_H
#define TRINITY_BOT_MAGMAW_TRANSFER_LANE_KERNEL_BRIDGE_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneAuthority.h"

#include <functional>
#include <string>

namespace BotEncounter
{
using MagmawTransferLaneNativeExecutor = std::function<
    BotActionArbitration::Outcome(BotNativeAction::Intent const&,
        BotWorldMovement::ExecutionObservation&)>;
using MagmawTransferLaneOutcomeObserver = std::function<void(
    MagmawTransferLaneNativeOutcome const&)>;

// The production bridge between the selected Magmaw task candidate and the
// existing action kernel. It neither selects policy nor bypasses arbitration.
// Returning false means the binding failed closed. The caller must submit the
// proposal as a trace-visible hard mask and must not execute generic movement.
bool SubmitMagmawTransferLaneKernelCandidate(
    BotActionArbitration::Kernel& kernel,
    BotNativeAction::Candidate const& candidate,
    MagmawTransferLaneExecutionBinding const& binding, uint64 observedAtMs,
    MagmawTransferLaneNativeExecutor execute,
    MagmawTransferLaneOutcomeObserver observe,
    std::string arbitrationSource = {});
}

#endif
