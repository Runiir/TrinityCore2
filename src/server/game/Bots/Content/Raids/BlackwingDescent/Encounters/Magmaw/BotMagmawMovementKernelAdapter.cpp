#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMovementKernelAdapter.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawLaneTransition.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawPersonalParasiteEscapeTask.h"

#include <utility>

namespace BotEncounter
{
std::optional<MagmawMovementNativeLease> MagmawMovementNativeLeaseFor(
    std::string_view mechanic)
{
    if (mechanic == "prepull_ranged_stage"
        || mechanic == "ranged_formation_restore"
        || mechanic == "pincer_preposition"
        || mechanic == "pincer_approach")
        return MagmawMovementNativeLease{
            BotMovementArbitration::Owner::Mechanic,
            BotMovementArbitration::Priority::Mechanic };
    if (mechanic == "pillar_evade"
        || mechanic == "pillar_bait_switch"
        || mechanic == "massive_crash_evade"
        || mechanic == "mangle_safe_side"
        || mechanic == "mangle_midpoint_stage"
        || mechanic == "parasite_contact_evade"
        || mechanic == "parasite_directional_mobility")
        return MagmawMovementNativeLease{
            BotMovementArbitration::Owner::Hazard,
            BotMovementArbitration::Priority::Hazard };
    return std::nullopt;
}

namespace
{
BotNativeAction::Intent NativeIntent(
    BotNativeAction::Candidate const& candidate)
{
    std::string diagnosticKey =
        LegacyMagmawMovementDiagnosticCandidateKey(candidate);
    if (diagnosticKey.empty()
        && std::get_if<BotNativeAction::Move>(&candidate.Action))
        diagnosticKey = candidate.Id.Key();
    return BotNativeAction::WithMovementDiagnosticCandidateKey(
        BotNativeAction::WithMovementReason(candidate.Action,
            candidate.Id.Mechanic),
        diagnosticKey);
}

void ApplyRetryPolicy(BotActionArbitration::Candidate& candidate,
    std::string const& mechanic)
{
    if (mechanic != "pillar_bait_switch"
        && mechanic != "parasite_contact_evade")
        return;
    candidate.RetryBaseMs = 250;
    candidate.RetryMaxMs = 2000;
    candidate.EscalateAfter = 4;
}

bool SubmitGeneric(BotActionArbitration::Kernel& kernel,
    BotNativeAction::Candidate const& intent,
    MagmawMovementProposalOrigin origin,
    std::optional<MagmawMovementNativeLease> lease,
    bool transferBindingRequired, bool safetyPending,
    MagmawMovementKernelAdapterContext const& context)
{
    MagmawMovementNativeLease const selectedLease = lease.value_or(
        MagmawMovementNativeLease{});
    std::optional<MagmawMovementNativeOutcome> nativeOutcome;
    if (BotNativeAction::Move const* move =
            std::get_if<BotNativeAction::Move>(&intent.Action))
        nativeOutcome = MagmawMovementNativeOutcome{
            intent.Id.Key(), intent.Id.Mechanic, intent.Id.Actor,
            intent.Id.EventGeneration, { move->X, move->Y, move->Z }, {} };
    BotActionArbitration::Candidate candidate =
        BuildMagmawMovementKernelCandidate(intent, origin, lease.has_value(),
            transferBindingRequired, safetyPending,
            [nativeIntent = NativeIntent(intent), selectedLease,
                execute = context.Execute,
                observe = context.ObserveNativeOutcome,
                nativeOutcome = std::move(nativeOutcome)]() mutable
            {
                if (!execute)
                    return BotActionArbitration::Outcome::Retryable(
                        "magmaw_movement_executor_unavailable");
                BotActionArbitration::Outcome outcome = execute(nativeIntent,
                    selectedLease, nullptr);
                if (observe && nativeOutcome)
                {
                    nativeOutcome->Result = outcome;
                    observe(*nativeOutcome);
                }
                return outcome;
            });
    ApplyRetryPolicy(candidate, intent.Id.Mechanic);
    if (context.BeforeSubmit)
        context.BeforeSubmit(kernel, candidate, intent);
    return kernel.Submit(std::move(candidate));
}
}

bool HasRetainedMagmawHazardOwnership(
    MagmawMovementIntentCollection const& movements,
    MagmawParasiteHazardState const& hazardState, ObjectGuid actor)
{
    for (size_t index = 0; index < movements.Size(); ++index)
    {
        MagmawMovementProposalOrigin const origin = movements.Origin(index);
        if (origin != MagmawMovementProposalOrigin::Hazard
            && origin != MagmawMovementProposalOrigin::TransferLaneTask)
            continue;
        BotNativeAction::Candidate const& intent = movements.Proposals()[index];
        if (origin == MagmawMovementProposalOrigin::Hazard
            && intent.Id.Mechanic == "parasite_contact_evade")
        {
            BotNativeAction::Move const* move =
                std::get_if<BotNativeAction::Move>(&intent.Action);
            if (move && hazardState.HasRetainedIntent()
                && hazardState.ActorGuid == actor && intent.Id.Actor == actor
                && hazardState.IntentId == intent.Id.EventGeneration
                && MagmawParasiteHazardState::SamePoint(
                    hazardState.Destination,
                    { move->X, move->Y, move->Z }))
                return true;
            continue;
        }
        return true;
    }
    return false;
}

bool HasRetainedMagmawHazardOwnership(
    MagmawMovementIntentCollection const& movements,
    MagmawPersonalParasiteEscapeTask const& task, ObjectGuid actor)
{
    if (!task.OwnsMovement() || task.ActorGuid != actor)
        return false;
    for (size_t index = 0; index < movements.Size(); ++index)
    {
        BotNativeAction::Candidate const& intent = movements.Proposals()[index];
        if (movements.Origin(index) != MagmawMovementProposalOrigin::Hazard
            || intent.Id.Mechanic != "parasite_contact_evade"
            || intent.Id.Actor != actor
            || intent.Id.EventGeneration != task.CandidateGeneration)
            continue;
        BotNativeAction::Move const* move =
            std::get_if<BotNativeAction::Move>(&intent.Action);
        return move && MagmawPersonalParasiteEscapeTask::SamePoint(
            task.Destination, { move->X, move->Y, move->Z });
    }
    return false;
}

size_t SubmitMagmawMovementKernelCandidates(
    BotActionArbitration::Kernel& kernel,
    MagmawMovementIntentCollection const& movements,
    MagmawMovementKernelAdapterContext context)
{
    bool const safetyPending = HasPendingMagmawSurvivalMovement(movements,
        context.ObservedAtMs);
    size_t submitted = 0;
    for (size_t index = 0; index < movements.Size(); ++index)
    {
        BotNativeAction::Candidate const& intent = movements.Proposals()[index];
        if (context.AlreadyQueued && context.AlreadyQueued(intent))
            continue;
        MagmawMovementProposalOrigin const origin = movements.Origin(index);
        std::optional<MagmawMovementNativeLease> const lease =
            MagmawMovementNativeLeaseFor(intent.Id.Mechanic);
        bool const transferBindingRequired = lease
            && intent.Id.Mechanic == "pillar_bait_switch"
            && context.TransferBinding.has_value();
        bool accepted = false;
        if (transferBindingRequired && context.Execute
            && context.ObserveTransferOutcome)
        {
            accepted = SubmitMagmawTransferLaneKernelCandidate(kernel, intent,
                *context.TransferBinding, context.ObservedAtMs,
                [execute = context.Execute, selectedLease = *lease](
                    BotNativeAction::Intent const& nativeIntent,
                    BotWorldMovement::ExecutionObservation& movement)
                {
                    return execute(nativeIntent, selectedLease, &movement);
                }, context.ObserveTransferOutcome, ToString(origin));
        }
        if (!accepted)
            accepted = SubmitGeneric(kernel, intent, origin, lease,
                transferBindingRequired, safetyPending, context);
        if (accepted)
            ++submitted;
    }
    return submitted;
}
}
