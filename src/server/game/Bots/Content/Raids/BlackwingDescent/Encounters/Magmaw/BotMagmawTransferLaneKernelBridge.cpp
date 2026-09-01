#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneKernelBridge.h"

#include <cmath>
#include <utility>

namespace BotEncounter
{
namespace
{
bool DestinationMatches(BotNativeAction::Move const& move,
    Vector3 const& destination)
{
    return std::hypot(move.X - destination.X, move.Y - destination.Y)
            <= MagmawTransferLaneIntentDestinationTolerance2d
        && std::fabs(move.Z - destination.Z)
            <= MagmawTransferLaneIntentDestinationToleranceZ;
}

bool Correlates(BotNativeAction::Candidate const& candidate,
    MagmawTransferLaneExecutionBinding const& binding)
{
    BotNativeAction::Move const* move =
        std::get_if<BotNativeAction::Move>(&candidate.Action);
    uint64 const expectedGeneration = binding.Source
            == MagmawTransferLaneAuthoritySource::Task
        ? binding.TaskGeneration : binding.LegacyTransitionGeneration;
    return move && !binding.ScopeKey.empty() && !binding.Actor.IsEmpty()
        && binding.EpisodeGeneration && binding.TaskGeneration
        && binding.LegacyTransitionGeneration
        && candidate.Id.ScopeKey == binding.ScopeKey
        && candidate.Id.Strategy == "adaptive_magmaw"
        && candidate.Id.Mechanic == "pillar_bait_switch"
        && candidate.Id.Actor == binding.Actor
        && candidate.Id.EventGeneration == expectedGeneration
        && candidate.Id.Key() == binding.CandidateKey
        && candidate.Resources() == BotActionArbitration::Uses(
            BotActionArbitration::Resource::Movement)
        && DestinationMatches(*move, binding.Destination);
}
}

bool SubmitMagmawTransferLaneKernelCandidate(
    BotActionArbitration::Kernel& kernel,
    BotNativeAction::Candidate const& candidate,
    MagmawTransferLaneExecutionBinding const& binding, uint64 observedAtMs,
    MagmawTransferLaneNativeExecutor execute,
    MagmawTransferLaneOutcomeObserver observe,
    std::string arbitrationSource)
{
    if (!Correlates(candidate, binding) || !execute || !observe)
        return false;

    BotNativeAction::Intent nativeIntent =
        BotNativeAction::WithMovementDiagnosticCandidateKey(
            BotNativeAction::WithMovementReason(candidate.Action,
                candidate.Id.Mechanic),
            LegacyMagmawMovementDiagnosticCandidateKey(candidate));

    BotActionArbitration::Candidate queued;
    queued.Key = candidate.Id.Key();
    queued.Source = arbitrationSource.empty()
        ? candidate.Id.Strategy : std::move(arbitrationSource);
    queued.ActionPriority = candidate.ActionPriority;
    queued.UtilityScore = candidate.Utility;
    queued.RequiredResources = candidate.Resources();
    queued.ExpiresAtMs = candidate.ExpiresAtMs;
    queued.RetryBaseMs = 250;
    queued.RetryMaxMs = 2000;
    queued.EscalateAfter = 4;
    queued.Attempt = [binding, observedAtMs,
        nativeIntent = std::move(nativeIntent), execute = std::move(execute),
        observe = std::move(observe)]()
    {
        BotNativeAction::Move const& move =
            std::get<BotNativeAction::Move>(nativeIntent);
        BotWorldMovement::ExecutionObservation movement =
            BotWorldMovement::BeginUnavailableExecutionObservation(
                move.X, move.Y, move.Z);
        BotActionArbitration::Outcome outcome = execute(nativeIntent,
            movement);
        observe(BindMagmawTransferLaneNativeOutcome(binding,
            movement, observedAtMs));
        return outcome;
    };
    return kernel.Submit(std::move(queued));
}
}
