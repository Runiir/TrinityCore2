#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneDiagnostics.h"

#include <iomanip>
#include <limits>
#include <sstream>

namespace BotEncounter
{
namespace
{
std::string JsonEscape(std::string const& value)
{
    std::ostringstream escaped;
    for (char character : value)
    {
        switch (character)
        {
            case '\\': escaped << "\\\\"; break;
            case '"': escaped << "\\\""; break;
            case '\n': escaped << "\\n"; break;
            case '\r': escaped << "\\r"; break;
            case '\t': escaped << "\\t"; break;
            default: escaped << character; break;
        }
    }
    return escaped.str();
}

void AppendDestination(std::ostringstream& json, char const* name,
    bool available, Vector3 const& destination)
{
    json << ",\"" << name << "\":{\"available\":"
         << (available ? "true" : "false") << ",\"x\":";
    if (available)
        json << destination.X;
    else
        json << "null";
    json << ",\"y\":";
    if (available)
        json << destination.Y;
    else
        json << "null";
    json << ",\"z\":";
    if (available)
        json << destination.Z;
    else
        json << "null";
    json << '}';
}

void AppendDivergences(std::ostringstream& json,
    MagmawTransferLaneIntentComparison const& comparison)
{
    using Divergence = MagmawTransferLaneIntentDivergence;
    bool first = true;
    auto append = [&](Divergence reason, char const* name)
    {
        if (!comparison.Has(reason))
            return;
        json << (first ? "" : ",") << '"' << name << '"';
        first = false;
    };
    append(Divergence::AmbiguousShadowMovement, "ambiguous_shadow_movement");
    append(Divergence::MissingExecutionContract, "missing_execution_contract");
    append(Divergence::StrategyIdentity, "strategy_identity");
    append(Divergence::MechanicIdentity, "mechanic_identity");
    append(Divergence::LifecycleScope, "lifecycle_scope");
    append(Divergence::ActionKind, "action_kind");
    append(Divergence::Actor, "actor");
    append(Divergence::GenerationCorrelation, "generation_correlation");
    append(Divergence::MovementResource, "movement_resource");
    append(Divergence::DestinationNonFinite, "destination_non_finite");
    append(Divergence::Destination2d, "destination_2d");
    append(Divergence::DestinationZ, "destination_z");
    append(Divergence::PreemptCasting, "preempt_casting");
    append(Divergence::ActionPriority, "action_priority");
    append(Divergence::Utility, "utility");
    append(Divergence::Expiry, "expiry");
}
}

std::string BuildMagmawTransferLaneIntentComparisonDiagnosticsJson(
    MagmawTransferLaneIntentComparison const& comparison)
{
    std::ostringstream json;
    json << std::setprecision(std::numeric_limits<float>::max_digits10)
         << "{\"observed\":" << (comparison.Observed ? "true" : "false")
         << ",\"outcome\":\"" << ToString(comparison.Outcome) << "\""
         << ",\"proposal_count\":" << comparison.ProposalCount
         << ",\"movement_proposal_count\":"
         << comparison.MovementProposalCount
         << ",\"ambiguous\":"
         << (comparison.Ambiguous() ? "true" : "false")
         << ",\"scope_key\":\"" << JsonEscape(comparison.ScopeKey) << "\""
         << ",\"shadow_candidate_key\":\""
         << JsonEscape(comparison.ShadowCandidateKey) << "\""
         << ",\"legacy_candidate_key\":\""
         << JsonEscape(comparison.LegacyCandidateKey) << "\""
         << ",\"shadow_actor_guid\":"
         << comparison.ShadowActor.GetCounter()
         << ",\"legacy_actor_guid\":"
         << comparison.LegacyActor.GetCounter()
         << ",\"shadow_episode_generation\":"
         << comparison.ShadowEpisodeGeneration
         << ",\"shadow_task_generation\":"
         << comparison.ShadowTaskGeneration
         << ",\"legacy_event_generation\":"
         << comparison.LegacyEventGeneration
         << ",\"expected_legacy_transition_generation\":"
         << comparison.ExpectedLegacyTransitionGeneration;
    AppendDestination(json, "shadow_destination",
        comparison.ShadowDestinationAvailable, comparison.ShadowDestination);
    AppendDestination(json, "legacy_destination",
        comparison.LegacyDestinationAvailable, comparison.LegacyDestination);
    json << ",\"divergences\":[";
    AppendDivergences(json, comparison);
    json << "]}";
    return json.str();
}

std::string BuildMagmawTransferLaneIntentEpisodeSummaryDiagnosticsJson(
    MagmawTransferLaneIntentEpisodeSummary const& summary)
{
    std::ostringstream json;
    json << std::setprecision(std::numeric_limits<float>::max_digits10)
         << "{\"scope_key\":\"" << JsonEscape(summary.Id.ScopeKey) << "\""
         << ",\"actor_guid\":" << summary.Id.Actor.GetCounter()
         << ",\"episode_generation\":" << summary.Id.EpisodeGeneration
         << ",\"task_generation\":" << summary.Id.TaskGeneration
         << ",\"counts\":{\"observed\":" << summary.ObservedCount
         << ",\"equivalent\":" << summary.EquivalentCount
         << ",\"divergent\":" << summary.DivergentCount
         << ",\"ambiguous\":" << summary.AmbiguousCount
         << ",\"shadow_only\":" << summary.ShadowOnlyCount
         << ",\"legacy_only\":" << summary.LegacyOnlyCount << "}"
         << ",\"first_observed_at_ms\":" << summary.FirstObservedAtMs
         << ",\"last_observed_at_ms\":" << summary.LastObservedAtMs
         << ",\"stable_shadow_candidate_key\":\""
         << JsonEscape(summary.StableShadowCandidateKey) << "\""
         << ",\"stable_legacy_candidate_key\":\""
         << JsonEscape(summary.StableLegacyCandidateKey) << "\""
         << ",\"shadow_key_change_count\":"
         << summary.ShadowKeyChangeCount
         << ",\"legacy_key_change_count\":"
         << summary.LegacyKeyChangeCount
         << ",\"shadow_destination_change_count\":"
         << summary.ShadowDestinationChangeCount
         << ",\"legacy_destination_change_count\":"
         << summary.LegacyDestinationChangeCount;
    AppendDestination(json, "stable_shadow_destination",
        summary.StableShadowDestinationAvailable,
        summary.StableShadowDestination);
    AppendDestination(json, "stable_legacy_destination",
        summary.StableLegacyDestinationAvailable,
        summary.StableLegacyDestination);
    json << ",\"first_failing_comparison\":";
    if (summary.FirstFailingComparison)
        json << BuildMagmawTransferLaneIntentComparisonDiagnosticsJson(
            *summary.FirstFailingComparison);
    else
        json << "null";
    json << '}';
    return json.str();
}

std::string BuildMagmawTransferLaneIntentEpisodeAccumulatorDiagnosticsJson(
    MagmawTransferLaneIntentEpisodeAccumulator const& accumulator)
{
    std::ostringstream json;
    json << "{\"active\":";
    if (accumulator.Active)
        json << BuildMagmawTransferLaneIntentEpisodeSummaryDiagnosticsJson(
            *accumulator.Active);
    else
        json << "null";
    json << ",\"retired\":[";
    for (size_t index = 0; index < accumulator.Retired.size(); ++index)
    {
        if (index)
            json << ',';
        json << BuildMagmawTransferLaneIntentEpisodeSummaryDiagnosticsJson(
            accumulator.Retired[index]);
    }
    json << "],\"retired_count\":" << accumulator.Retired.size()
         << ",\"retired_capacity\":"
         << MagmawTransferLaneIntentEpisodeAccumulator::MaxRetiredSummaries
         << '}';
    return json.str();
}

std::string BuildMagmawTransferLaneTaskDiagnosticsJson(
    MagmawTransferLaneTask const& task)
{
    std::ostringstream json;
    json << std::setprecision(std::numeric_limits<float>::max_digits10)
         << "{\"lifecycle_scope\":\""
         << JsonEscape(task.Id.Episode.Lifecycle.Key()) << "\""
         << ",\"episode_generation\":"
         << task.Id.Episode.EpisodeGeneration
         << ",\"mechanic_generation\":"
         << task.Id.Episode.MechanicGeneration
         << ",\"fire_mage_assignment_nonce\":"
         << task.Id.Episode.FireMageAssignmentNonce
         << ",\"hunter_assignment_nonce\":"
         << task.Id.Episode.HunterAssignmentNonce
         << ",\"actor_guid\":" << task.Id.ActorGuid.GetCounter()
         << ",\"task_generation\":" << task.Id.TaskGeneration
         << ",\"destination\":{\"x\":" << task.Destination.X
         << ",\"y\":" << task.Destination.Y
         << ",\"z\":" << task.Destination.Z << "}"
         << ",\"state\":\"" << ToString(task.State) << "\""
         << ",\"suspension\":\"" << ToString(task.Suspension) << "\""
         << ",\"failure\":\"" << ToString(task.Failure) << "\""
         << ",\"movement_observation\":\""
         << ToString(task.MovementDisposition) << "\""
         << ",\"native_disposition\":\""
         << ToString(task.NativeDisposition) << "\""
         << ",\"last_native_receipt_id\":" << task.LastNativeReceiptId
         << ",\"last_native_observed_at_ms\":"
         << task.LastNativeObservedAtMs
         << ",\"native_evidence_revision\":"
         << task.NativeEvidenceRevision
         << ",\"native_outcome_samples\":" << task.NativeOutcomeSamples
         << ",\"projected_endpoint_evidence_samples\":"
         << task.ProjectedEndpointEvidenceSamples
         << ",\"last_native_candidate_key\":\""
         << JsonEscape(task.LastNativeCandidateKey) << "\""
         << ",\"started_at_ms\":" << task.StartedAtMs
         << ",\"last_progress_at_ms\":" << task.LastProgressAtMs
         << ",\"last_observed_at_ms\":" << task.LastObservedAtMs
         << ",\"suspended_at_ms\":" << task.SuspendedAtMs
         << ",\"progress_revision\":" << task.ProgressRevision
         << ",\"initial_distance\":" << task.InitialDistance
         << ",\"best_distance\":" << task.BestDistance
         << ",\"last_distance\":" << task.LastDistance
         << ",\"observation_samples\":" << task.ObservationSamples
         << ",\"progress_samples\":" << task.ProgressSamples << '}';
    return json.str();
}

std::string BuildMagmawTransferLaneTaskCollectionDiagnosticsJson(
    std::vector<MagmawTransferLaneTask> const& tasks)
{
    std::ostringstream json;
    json << '[';
    for (size_t index = 0; index < tasks.size(); ++index)
    {
        if (index)
            json << ',';
        json << BuildMagmawTransferLaneTaskDiagnosticsJson(tasks[index]);
    }
    json << ']';
    return json.str();
}

std::string BuildMagmawRetiredTransferLaneTaskDiagnosticsJson(
    MagmawRetiredTransferLaneTask const& retired)
{
    std::ostringstream json;
    json << "{\"retirement_reason\":\"" << ToString(retired.Reason)
         << "\",\"retired_at_revision\":" << retired.RetiredAtRevision
         << ",\"task\":"
         << BuildMagmawTransferLaneTaskDiagnosticsJson(retired.Task) << '}';
    return json.str();
}

std::string BuildMagmawRetiredTransferLaneTaskCollectionDiagnosticsJson(
    std::vector<MagmawRetiredTransferLaneTask> const& retired)
{
    std::ostringstream json;
    json << '[';
    for (size_t index = 0; index < retired.size(); ++index)
    {
        if (index)
            json << ',';
        json << BuildMagmawRetiredTransferLaneTaskDiagnosticsJson(
            retired[index]);
    }
    json << ']';
    return json.str();
}

std::string BuildMagmawTransferLaneTaskShadowDiagnosticsJson(
    MagmawTransferLaneTaskShadow const* shadow,
    std::vector<MagmawTransferLaneActorIntentDiagnostics> const& actors)
{
    std::ostringstream json;
    json << "{\"active\":"
         << (shadow && shadow->Episode() ? "true" : "false")
         << ",\"source_revision\":"
         << (shadow ? shadow->SourceRevision() : 0);
    if (shadow && shadow->Episode())
    {
        MagmawTransferLaneEpisode const& episode = *shadow->Episode();
        json << ",\"lifecycle_scope\":\""
             << JsonEscape(episode.Id.Lifecycle.Key()) << "\""
             << ",\"episode_generation\":" << episode.Id.EpisodeGeneration
             << ",\"mechanic_generation\":" << episode.Id.MechanicGeneration
             << ",\"raid_plan_generation\":" << episode.Id.RaidPlanGeneration
             << ",\"roster_generation\":" << episode.Id.RosterGeneration
             << ",\"fire_mage_assignment_nonce\":"
             << episode.Id.FireMageAssignmentNonce
             << ",\"hunter_assignment_nonce\":"
             << episode.Id.HunterAssignmentNonce
             << ",\"direction\":\"" << ToString(episode.Direction) << "\""
             << ",\"fire_mage_guid\":" << episode.FireMageGuid.GetCounter()
             << ",\"hunter_guid\":" << episode.HunterGuid.GetCounter()
             << ",\"immutable_destination\":{\"x\":"
             << episode.Destination.X << ",\"y\":"
             << episode.Destination.Y << ",\"z\":"
             << episode.Destination.Z << '}';
    }
    static std::vector<MagmawTransferLaneTask> const noTasks;
    static std::vector<MagmawRetiredTransferLaneTask> const noRetired;
    auto const& tasks = shadow ? shadow->Tasks() : noTasks;
    auto const& retired = shadow ? shadow->Retired() : noRetired;
    json << ",\"tasks\":"
         << BuildMagmawTransferLaneTaskCollectionDiagnosticsJson(tasks)
         << ",\"retired_tasks\":"
         << BuildMagmawRetiredTransferLaneTaskCollectionDiagnosticsJson(
                retired)
         << ",\"retired_task_count\":" << retired.size()
         << ",\"intent_comparisons\":[";
    for (size_t index = 0; index < actors.size(); ++index)
    {
        if (index)
            json << ',';
        auto const& actor = actors[index];
        json << "{\"actor_guid\":" << actor.Actor.GetCounter()
             << ",\"comparison\":"
             << BuildMagmawTransferLaneIntentComparisonDiagnosticsJson(
                    actor.Comparison)
             << ",\"episode_accumulator\":"
             << BuildMagmawTransferLaneIntentEpisodeAccumulatorDiagnosticsJson(
                    actor.EpisodeAccumulator)
             << '}';
    }
    json << "]}";
    return json.str();
}
}
