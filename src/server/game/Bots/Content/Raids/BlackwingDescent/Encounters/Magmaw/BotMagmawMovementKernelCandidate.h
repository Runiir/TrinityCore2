#ifndef TRINITY_BOT_MAGMAW_MOVEMENT_KERNEL_CANDIDATE_H
#define TRINITY_BOT_MAGMAW_MOVEMENT_KERNEL_CANDIDATE_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMovementIntents.h"

#include <functional>
#include <utility>

namespace BotEncounter
{
inline bool HasPendingMagmawSurvivalMovement(
    MagmawMovementIntentCollection const& movements, uint64 nowMs)
{
    for (BotNativeAction::Candidate const& proposal : movements.Proposals())
        if (proposal.ExpiresAtMs > nowMs
            && proposal.ActionPriority
                == BotActionArbitration::Priority::Survival)
            return true;
    return false;
}

inline BotActionArbitration::Candidate BuildMagmawMovementKernelCandidate(
    BotNativeAction::Candidate const& intent,
    MagmawMovementProposalOrigin origin, bool mechanicMapped,
    bool transferBindingRequired, bool safetyMovementPending,
    std::function<BotActionArbitration::Outcome()> attempt)
{
    BotActionArbitration::Candidate movement;
    movement.Key = intent.Id.Key();
    movement.Source = ToString(origin);
    movement.ActionPriority = intent.ActionPriority;
    movement.UtilityScore = intent.Utility;
    movement.RequiredResources = intent.Resources();
    movement.ExpiresAtMs = intent.ExpiresAtMs;
    MagmawMovementKernelAdmission const admission =
        EvaluateMagmawMovementKernelAdmission(mechanicMapped,
            transferBindingRequired, safetyMovementPending,
            intent.ActionPriority);
    movement.Allowed = admission == MagmawMovementKernelAdmission::Admitted;
    movement.RejectReason = RejectionReason(admission);
    movement.Attempt = std::move(attempt);
    return movement;
}
}

#endif
