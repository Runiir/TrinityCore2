#ifndef TRINITY_BOT_NATIVE_MOVEMENT_OUTCOME_H
#define TRINITY_BOT_NATIVE_MOVEMENT_OUTCOME_H

#include "Bots/BotActionArbiter.h"
#include "Bots/BotWorldPopulationMgrMovement.h"

namespace BotNativeAction
{
inline BotActionArbitration::Outcome NativeMoveOutcome(bool moved,
    BotWorldMovement::ExecutionObservation const& execution)
{
    if (moved)
        return BotActionArbitration::Outcome::Submitted(
            "native_move_submitted");
    if (execution.Available
        && execution.Disposition
            == BotWorldMovement::ExecutionDisposition::Rejected
        && !execution.RejectionReason.empty())
        return BotActionArbitration::Outcome::Retryable(
            execution.RejectionReason);
    return BotActionArbitration::Outcome::Retryable(
        "native_move_retryable");
}
}

#endif
