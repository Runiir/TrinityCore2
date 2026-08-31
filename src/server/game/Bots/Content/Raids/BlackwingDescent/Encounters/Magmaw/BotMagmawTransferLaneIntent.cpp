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

void ObserveCandidate(MagmawTransferLaneIntentComparison& result,
    Candidate const& candidate, bool shadow)
{
    BotNativeAction::Move const* move = MoveIntent(candidate);
    if (shadow)
    {
        result.ShadowCandidateKey = candidate.Id.Key();
        result.ShadowActor = candidate.Id.Actor;
        result.ShadowTaskGeneration = candidate.Id.EventGeneration;
        if (move)
        {
            result.ShadowDestination = { move->X, move->Y, move->Z };
            result.ShadowDestinationAvailable = true;
        }
        return;
    }
    result.LegacyCandidateKey = candidate.Id.Key();
    result.LegacyActor = candidate.Id.Actor;
    result.LegacyEventGeneration = candidate.Id.EventGeneration;
    if (move)
    {
        result.LegacyDestination = { move->X, move->Y, move->Z };
        result.LegacyDestinationAvailable = true;
    }
}

bool ValidEpisodeIdentity(MagmawTransferLaneIntentComparison const& value)
{
    return !value.ScopeKey.empty() && !value.ShadowActor.IsEmpty()
        && value.ShadowEpisodeGeneration && value.ShadowTaskGeneration;
}

bool DestinationChanged(Vector3 const& left, Vector3 const& right)
{
    return left.X != right.X || left.Y != right.Y || left.Z != right.Z;
}

void ObserveStableKey(std::string const& observed, std::string& stable,
    std::string& last, uint32& changeCount)
{
    if (observed.empty())
        return;
    if (stable.empty())
        stable = observed;
    if (!last.empty() && last != observed)
        ++changeCount;
    last = observed;
}

void ObserveStableDestination(bool observedAvailable,
    Vector3 const& observed, bool& stableAvailable, Vector3& stable,
    bool& lastAvailable, Vector3& last, uint32& changeCount)
{
    if (!observedAvailable)
        return;
    if (!stableAvailable)
    {
        stableAvailable = true;
        stable = observed;
    }
    if (lastAvailable && DestinationChanged(last, observed))
        ++changeCount;
    lastAvailable = true;
    last = observed;
}

void CountComparisonOutcome(MagmawTransferLaneIntentEpisodeSummary& summary,
    MagmawTransferLaneIntentComparison const& comparison)
{
    using Outcome = MagmawTransferLaneIntentComparisonOutcome;
    ++summary.ObservedCount;
    if (comparison.Outcome == Outcome::Equivalent)
        ++summary.EquivalentCount;
    if (comparison.Outcome == Outcome::Divergent)
        ++summary.DivergentCount;
    if (comparison.Ambiguous())
        ++summary.AmbiguousCount;
    if (comparison.Outcome == Outcome::ShadowOnly)
        ++summary.ShadowOnlyCount;
    if (comparison.Outcome == Outcome::LegacyOnly)
        ++summary.LegacyOnlyCount;
}

bool FailedComparison(MagmawTransferLaneIntentComparison const& comparison)
{
    using Outcome = MagmawTransferLaneIntentComparisonOutcome;
    return comparison.Outcome == Outcome::Divergent
        || comparison.Outcome == Outcome::ShadowOnly
        || comparison.Outcome == Outcome::LegacyOnly;
}

void RetireActiveSummary(
    MagmawTransferLaneIntentEpisodeAccumulator& accumulator)
{
    if (!accumulator.Active)
        return;
    accumulator.Retired.push_back(std::move(*accumulator.Active));
    accumulator.Active.reset();
    if (accumulator.Retired.size()
        > MagmawTransferLaneIntentEpisodeAccumulator::MaxRetiredSummaries)
        accumulator.Retired.erase(accumulator.Retired.begin());
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
        task.Id.Episode.EpisodeGeneration, task.Id.TaskGeneration,
        legacyTransitionGeneration,
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
    {
        result.ScopeKey = contract->ScopeKey;
        result.ShadowActor = contract->Actor;
        result.ShadowEpisodeGeneration = contract->EpisodeGeneration;
        result.ShadowTaskGeneration = contract->TaskGeneration;
        result.ObservedAtMs = contract->ObservedAtMs;
        result.ExpectedLegacyTransitionGeneration =
            contract->LegacyTransitionGeneration;
    }
    if (legacy)
        ObserveCandidate(result, *legacy, false);
    Candidate const* shadowMovement = nullptr;
    for (Candidate const& proposal : shadowProposals)
        if (IsMovementProposal(proposal))
        {
            ++result.MovementProposalCount;
            shadowMovement = result.MovementProposalCount == 1
                ? &proposal : nullptr;
        }
    if (shadowMovement)
        ObserveCandidate(result, *shadowMovement, true);
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
        return result;
    }
    if (!shadowMovement)
    {
        result.Outcome = MagmawTransferLaneIntentComparisonOutcome::LegacyOnly;
        return result;
    }

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
    MagmawTransferLaneTask const* matchingTask = nullptr;
    uint32 runningTaskCount = 0;
    uint32 matchingTaskCount = 0;
    for (MagmawTransferLaneTask const& task : tasks)
        if (task.Id.ActorGuid == actor)
        {
            ++matchingTaskCount;
            matchingTask = matchingTaskCount == 1 ? &task : nullptr;
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
    MagmawTransferLaneIntentComparison result =
        CompareMagmawTransferLaneIntents(shadowSink.Proposals(), legacy,
            contract);
    if (matchingTaskCount == 1 && matchingTask)
    {
        result.ScopeKey = matchingTask->Id.Episode.Lifecycle.Key();
        result.ShadowActor = matchingTask->Id.ActorGuid;
        result.ShadowEpisodeGeneration =
            matchingTask->Id.Episode.EpisodeGeneration;
        result.ShadowTaskGeneration = matchingTask->Id.TaskGeneration;
        result.ObservedAtMs = matchingTask->LastObservedAtMs;
    }
    return result;
}

std::string LegacyMagmawMovementDiagnosticCandidateKey(
    BotNativeAction::Candidate const& candidate)
{
    if (candidate.Id.Strategy != "adaptive_magmaw"
        || candidate.Id.Mechanic != "pillar_bait_switch"
        || !MoveIntent(candidate))
        return {};
    return candidate.Id.Key();
}

void ObserveMagmawTransferLaneIntentEpisode(
    MagmawTransferLaneIntentEpisodeAccumulator& accumulator,
    MagmawTransferLaneIntentComparison const& comparison)
{
    if (!comparison.Observed)
        return;
    if (!ValidEpisodeIdentity(comparison))
    {
        RetireActiveSummary(accumulator);
        return;
    }
    MagmawTransferLaneIntentEpisodeIdentity const identity{
        comparison.ScopeKey, comparison.ShadowActor,
        comparison.ShadowEpisodeGeneration, comparison.ShadowTaskGeneration };
    if (accumulator.Active && !(accumulator.Active->Id == identity))
        RetireActiveSummary(accumulator);
    if (!accumulator.Active)
    {
        accumulator.Active.emplace();
        accumulator.Active->Id = identity;
        accumulator.Active->FirstObservedAtMs = comparison.ObservedAtMs;
    }
    MagmawTransferLaneIntentEpisodeSummary& summary = *accumulator.Active;
    summary.LastObservedAtMs = comparison.ObservedAtMs;
    CountComparisonOutcome(summary, comparison);
    ObserveStableKey(comparison.ShadowCandidateKey,
        summary.StableShadowCandidateKey, summary.LastShadowCandidateKey,
        summary.ShadowKeyChangeCount);
    ObserveStableKey(comparison.LegacyCandidateKey,
        summary.StableLegacyCandidateKey, summary.LastLegacyCandidateKey,
        summary.LegacyKeyChangeCount);
    ObserveStableDestination(comparison.ShadowDestinationAvailable,
        comparison.ShadowDestination,
        summary.StableShadowDestinationAvailable,
        summary.StableShadowDestination,
        summary.LastShadowDestinationAvailable,
        summary.LastShadowDestination, summary.ShadowDestinationChangeCount);
    ObserveStableDestination(comparison.LegacyDestinationAvailable,
        comparison.LegacyDestination,
        summary.StableLegacyDestinationAvailable,
        summary.StableLegacyDestination,
        summary.LastLegacyDestinationAvailable,
        summary.LastLegacyDestination, summary.LegacyDestinationChangeCount);
    if (!summary.FirstFailingComparison && FailedComparison(comparison))
        summary.FirstFailingComparison = comparison;
}

void ResetMagmawTransferLaneIntentEpisodeAccumulator(
    MagmawTransferLaneIntentEpisodeAccumulator& accumulator)
{
    accumulator = {};
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
