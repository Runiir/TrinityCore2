#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneIntent.h"

#include <cmath>
#include <variant>

namespace BotEncounter
{
namespace
{
using Candidate = BotNativeAction::Candidate;
using Divergence = MagmawTransferLaneIntentDivergence;

bool IsMovementProposal(Candidate const& candidate)
{
    return BotActionArbitration::Conflicts(candidate.Resources(),
        BotActionArbitration::Uses(
            BotActionArbitration::Resource::Movement));
}

BotNativeAction::Move const* MoveIntent(Candidate const& candidate)
{
    return std::get_if<BotNativeAction::Move>(&candidate.Action);
}

uint32 CompareIdentity(Candidate const& shadow, Candidate const& legacy,
    MagmawTransferLaneExecutionContract const& contract)
{
    uint32 divergences = 0;
    if (shadow.Id.Strategy != "adaptive_magmaw"
        || legacy.Id.Strategy != "adaptive_magmaw")
        divergences |= DivergenceMask(Divergence::StrategyIdentity);
    if (shadow.Id.Mechanic != "pillar_bait_switch"
        || legacy.Id.Mechanic != "pillar_bait_switch")
        divergences |= DivergenceMask(Divergence::MechanicIdentity);
    if (shadow.Id.ScopeKey != contract.ScopeKey
        || legacy.Id.ScopeKey != contract.ScopeKey)
        divergences |= DivergenceMask(Divergence::LifecycleScope);
    if (shadow.Id.Actor != contract.Actor || legacy.Id.Actor != contract.Actor)
        divergences |= DivergenceMask(Divergence::Actor);
    if (shadow.Id.EventGeneration != contract.TaskGeneration
        || legacy.Id.EventGeneration != contract.LegacyTransitionGeneration)
        divergences |= DivergenceMask(Divergence::GenerationCorrelation);
    return divergences;
}

uint32 CompareExecutionFields(Candidate const& shadow,
    Candidate const& legacy,
    MagmawTransferLaneExecutionContract const& contract)
{
    uint32 divergences = 0;
    if (shadow.ActionPriority != BotActionArbitration::Priority::Survival
        || legacy.ActionPriority != BotActionArbitration::Priority::Survival)
        divergences |= DivergenceMask(Divergence::ActionPriority);
    if (shadow.Utility != MagmawTransferLaneIntentUtility
        || legacy.Utility != MagmawTransferLaneIntentUtility)
        divergences |= DivergenceMask(Divergence::Utility);
    uint64 const expiry = contract.ObservedAtMs
        + MagmawTransferLaneIntentFreshnessMs;
    if (shadow.ExpiresAtMs != expiry || legacy.ExpiresAtMs != expiry)
        divergences |= DivergenceMask(Divergence::Expiry);
    auto const movement = BotActionArbitration::Uses(
        BotActionArbitration::Resource::Movement);
    if (shadow.Resources() != movement || legacy.Resources() != movement)
        divergences |= DivergenceMask(Divergence::MovementResource);
    return divergences;
}

bool Finite(Vector3 const& destination)
{
    return std::isfinite(destination.X) && std::isfinite(destination.Y)
        && std::isfinite(destination.Z);
}

uint32 CompareDestinations(BotNativeAction::Move const& shadow,
    BotNativeAction::Move const& legacy,
    MagmawTransferLaneExecutionContract const& contract)
{
    Vector3 const shadowPoint{ shadow.X, shadow.Y, shadow.Z };
    Vector3 const legacyPoint{ legacy.X, legacy.Y, legacy.Z };
    if (!Finite(shadowPoint) || !Finite(legacyPoint)
        || !Finite(contract.Destination))
        return DivergenceMask(Divergence::DestinationNonFinite);

    uint32 divergences = 0;
    auto distance2d = [](Vector3 const& left, Vector3 const& right)
    {
        return std::hypot(left.X - right.X, left.Y - right.Y);
    };
    if (distance2d(shadowPoint, contract.Destination)
            > MagmawTransferLaneIntentDestinationTolerance2d
        || distance2d(legacyPoint, contract.Destination)
            > MagmawTransferLaneIntentDestinationTolerance2d
        || distance2d(shadowPoint, legacyPoint)
            > MagmawTransferLaneIntentDestinationTolerance2d)
        divergences |= DivergenceMask(Divergence::Destination2d);
    if (std::fabs(shadow.Z - contract.Destination.Z)
            > MagmawTransferLaneIntentDestinationToleranceZ
        || std::fabs(legacy.Z - contract.Destination.Z)
            > MagmawTransferLaneIntentDestinationToleranceZ
        || std::fabs(shadow.Z - legacy.Z)
            > MagmawTransferLaneIntentDestinationToleranceZ)
        divergences |= DivergenceMask(Divergence::DestinationZ);
    if (shadow.PreemptCasting || legacy.PreemptCasting
        || shadow.PreemptCasting != legacy.PreemptCasting)
        divergences |= DivergenceMask(Divergence::PreemptCasting);
    return divergences;
}

uint32 ComparePresent(Candidate const& shadow, Candidate const& legacy,
    MagmawTransferLaneExecutionContract const& contract)
{
    uint32 divergences = CompareIdentity(shadow, legacy, contract)
        | CompareExecutionFields(shadow, legacy, contract);
    BotNativeAction::Move const* shadowMove = MoveIntent(shadow);
    BotNativeAction::Move const* legacyMove = MoveIntent(legacy);
    if (!shadowMove || !legacyMove)
        return divergences | DivergenceMask(Divergence::ActionKind);
    return divergences | CompareDestinations(*shadowMove, *legacyMove,
        contract);
}
}

void ResetMagmawTransferLaneIntentComparison(
    MagmawTransferLaneIntentComparison& comparison)
{
    comparison = {};
}

MagmawTransferLaneExecutionContract MagmawTransferLaneContract(
    MagmawTransferLaneTask const& task, uint64 legacyTransitionGeneration)
{
    return { task.Id.Episode.Lifecycle.Key(), task.Id.ActorGuid,
        task.Id.TaskGeneration, legacyTransitionGeneration,
        task.LastObservedAtMs, task.Destination };
}

void EmitMagmawTransferLaneTaskIntent(MagmawTransferLaneTask const& task,
    BotDecision::BotIntentSink& sink)
{
    if (task.State != BotDecision::PersistentTaskState::Running)
        return;
    BotNativeAction::Candidate candidate;
    candidate.Id.ScopeKey = task.Id.Episode.Lifecycle.Key();
    candidate.Id.Strategy = "adaptive_magmaw";
    candidate.Id.Mechanic = "pillar_bait_switch";
    candidate.Id.Actor = task.Id.ActorGuid;
    candidate.Id.EventGeneration = task.Id.TaskGeneration;
    candidate.ActionPriority = BotActionArbitration::Priority::Survival;
    candidate.Utility = MagmawTransferLaneIntentUtility;
    candidate.ExpiresAtMs = task.LastObservedAtMs
        + MagmawTransferLaneIntentFreshnessMs;
    candidate.Action = BotNativeAction::Move{ task.Destination.X,
        task.Destination.Y, task.Destination.Z, "pillar_bait_switch", false };
    sink.Propose(std::move(candidate));
}

MagmawTransferLaneIntentComparison CompareMagmawTransferLaneIntents(
    std::vector<BotNativeAction::Candidate> const& shadowProposals,
    std::optional<BotNativeAction::Candidate> const& legacy,
    std::optional<MagmawTransferLaneExecutionContract> const& contract)
{
    MagmawTransferLaneIntentComparison result;
    result.Observed = true;
    result.ProposalCount = shadowProposals.size();
    if (contract)
        result.ExpectedLegacyTransitionGeneration =
            contract->LegacyTransitionGeneration;
    Candidate const* shadowMovement = nullptr;
    for (Candidate const& proposal : shadowProposals)
        if (IsMovementProposal(proposal))
        {
            ++result.MovementProposalCount;
            shadowMovement = result.MovementProposalCount == 1
                ? &proposal : nullptr;
        }
    if (result.Ambiguous())
    {
        result.Outcome = MagmawTransferLaneIntentComparisonOutcome::Divergent;
        result.Divergences = DivergenceMask(
            Divergence::AmbiguousShadowMovement);
        return result;
    }
    if (!shadowMovement && !legacy)
        return result;
    if (shadowMovement && !legacy)
    {
        result.Outcome = MagmawTransferLaneIntentComparisonOutcome::ShadowOnly;
        result.ShadowActor = shadowMovement->Id.Actor;
        result.ShadowTaskGeneration = shadowMovement->Id.EventGeneration;
        return result;
    }
    if (!shadowMovement)
    {
        result.Outcome = MagmawTransferLaneIntentComparisonOutcome::LegacyOnly;
        result.LegacyActor = legacy->Id.Actor;
        result.LegacyEventGeneration = legacy->Id.EventGeneration;
        return result;
    }

    result.ShadowActor = shadowMovement->Id.Actor;
    result.LegacyActor = legacy->Id.Actor;
    result.ShadowTaskGeneration = shadowMovement->Id.EventGeneration;
    result.LegacyEventGeneration = legacy->Id.EventGeneration;
    result.Divergences = contract
        ? ComparePresent(*shadowMovement, *legacy, *contract)
        : DivergenceMask(Divergence::MissingExecutionContract);
    result.Outcome = result.Divergences
        ? MagmawTransferLaneIntentComparisonOutcome::Divergent
        : MagmawTransferLaneIntentComparisonOutcome::Equivalent;
    return result;
}

MagmawTransferLaneIntentComparison ObserveMagmawTransferLaneIntents(
    std::vector<MagmawTransferLaneTask> const& tasks, ObjectGuid actor,
    std::optional<BotNativeAction::Candidate> const& legacy,
    uint64 legacyTransitionGeneration)
{
    BotDecision::BotIntentSink shadowSink;
    MagmawTransferLaneTask const* runningTask = nullptr;
    uint32 runningTaskCount = 0;
    for (MagmawTransferLaneTask const& task : tasks)
        if (task.Id.ActorGuid == actor)
        {
            EmitMagmawTransferLaneTaskIntent(task, shadowSink);
            if (task.State == BotDecision::PersistentTaskState::Running)
            {
                ++runningTaskCount;
                runningTask = runningTaskCount == 1 ? &task : nullptr;
            }
        }
    std::optional<MagmawTransferLaneExecutionContract> contract;
    if (runningTaskCount == 1)
        contract = MagmawTransferLaneContract(*runningTask,
            legacyTransitionGeneration);
    return CompareMagmawTransferLaneIntents(shadowSink.Proposals(), legacy,
        contract);
}

char const* ToString(MagmawTransferLaneIntentComparisonOutcome value)
{
    switch (value)
    {
        case MagmawTransferLaneIntentComparisonOutcome::ShadowOnly:
            return "shadow_only";
        case MagmawTransferLaneIntentComparisonOutcome::LegacyOnly:
            return "legacy_only";
        case MagmawTransferLaneIntentComparisonOutcome::Equivalent:
            return "equivalent";
        case MagmawTransferLaneIntentComparisonOutcome::Divergent:
            return "divergent";
        default: return "neither_present";
    }
}
}
