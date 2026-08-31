#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawCoordinator.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneTask.h"

#include <algorithm>
#include <initializer_list>
#include <sstream>

namespace
{
bool AllTrue(std::initializer_list<bool> values)
{
    return std::all_of(values.begin(), values.end(),
        [](bool value) { return value; });
}

BotEncounter::MagmawRaidMode MagmawMode(uint8 difficulty)
{
    using Mode = BotEncounter::MagmawRaidMode;
    switch (difficulty)
    {
        case 0: return Mode::Normal10;
        case 1: return Mode::Normal25;
        case 2: return Mode::Heroic10;
        case 3: return Mode::Heroic25;
        default: return Mode::Unknown;
    }
}

}

BotEncounter::MagmawRosterView
BotWorldPopulationMgr::BuildMagmawShadowRoster(
    BotEncounter::Scope const& lifecycle) const
{
    RaidRuntime const& raid = Cohort().Raid;
    BotEncounter::MagmawRosterView view;
    view.Lifecycle = lifecycle;
    view.Generation = raid.AssignmentGeneration;
    view.ExpectedSize = raid.ExpectedSize;
    view.Mode = MagmawMode(raid.ExpectedDifficulty);
    view.Authoritative = AllTrue({ raid.Active, raid.RaidInstance,
        raid.ServerProvisioningComplete, raid.BotActionsEnabled,
        raid.RosterComplete, raid.DifficultyMatches, raid.UniqueLeases,
        Cohort().ValidationRaidAdmissionComplete,
        raid.AdmissionAttemptId == lifecycle.AttemptId,
        raid.ServerEpoch == lifecycle.ServerEpoch,
        raid.MapId == lifecycle.MapId,
        raid.InstanceId == lifecycle.InstanceId,
        raid.AssignmentGeneration != 0,
        raid.AdmissionReceiptByGuid.size() == raid.ExpectedSize,
        Cohort().RosterLeases.size() == raid.ExpectedSize });
    for (auto const& [guid, slot] : raid.RosterByGuid)
    {
        auto receipt = raid.AdmissionReceiptByGuid.find(guid);
        bool const admitted = receipt != raid.AdmissionReceiptByGuid.end()
            && AllTrue({ raid.AdmissionCommittedAtMs != 0,
                raid.AdmissionActionGateEnabled,
                receipt->second.Guid == slot.Guid,
                receipt->second.RosterSlotId == slot.RosterSlotId,
                receipt->second.Role == slot.Role,
                receipt->second.ClassSpec == slot.ClassSpec,
                receipt->second.MapId == lifecycle.MapId,
                receipt->second.InstanceId == lifecycle.InstanceId });
        bool const leased = AllTrue({
            Cohort().RosterLeases.count(guid) == 1,
            LeaseOwnedByCurrentCohort(guid, slot.LeaseRoleSlot) });
        view.Members.push_back({ slot.Guid, slot.RosterSlotId, slot.Role,
            slot.ClassSpec, admitted, leased });
    }
    return view;
}

std::vector<BotEncounter::MagmawTransferLaneActorObservation>
BotWorldPopulationMgr::BuildMagmawShadowActorObservations(
    BotEncounter::Blackboard const& snapshot) const
{
    std::vector<BotEncounter::MagmawTransferLaneActorObservation> result;
    RaidRuntime const& raid = Cohort().Raid;
    for (auto const& [guid, slot] : raid.RosterByGuid)
    {
        BotEncounter::MagmawTransferLaneActorObservation observation;
        observation.Guid = slot.Guid;
        auto signal = raid.NativeSignalsByGuid.find(guid);
        if (signal != raid.NativeSignalsByGuid.end())
        {
            bool const lifeAuthoritative = AllTrue({
                signal->second.Initialized,
                signal->second.WipeGeneration
                    == snapshot.CurrentScope.WipeGeneration,
                signal->second.MapId == snapshot.CurrentScope.MapId,
                signal->second.InstanceId
                    == snapshot.CurrentScope.InstanceId });
            observation.Life = { signal->second.WipeGeneration,
                signal->second.DeathSequence,
                signal->second.ResurrectionSequence,
                lifeAuthoritative };
            observation.Alive = signal->second.Alive;
        }
        if (BotEncounter::ActorSnapshot const* actor = snapshot.FindActor(
                slot.Guid); actor && actor->Kind == BotEncounter::ActorKind::Player)
        {
            observation.Position = actor->Position;
            observation.PositionObserved = true;
            observation.Alive = actor->Alive;
        }
        auto state = std::find_if(Party().Bots.begin(), Party().Bots.end(),
            [guid](WorldBotState const& candidate)
            {
                return candidate.Guid.GetCounter() == guid;
            });
        if (state != Party().Bots.end())
            observation.Movement.CurrentLease = state->MovementLease;
        result.push_back(std::move(observation));
    }
    return result;
}

void BotWorldPopulationMgr::ReconcileMagmawTransferLaneTaskShadow(
    BotEncounter::Blackboard const& snapshot)
{
    if (!Cohort().MagmawFacts)
        return;
    BotEncounter::MagmawRosterView const roster = BuildMagmawShadowRoster(
        snapshot.CurrentScope);
    Cohort().MagmawCoordinatorShadow = BotEncounter::MagmawCoordinator::
        Reconcile(Cohort().MagmawCoordinatorShadow,
            Cohort().MagmawFacts->Facts(), snapshot, roster);
    auto const actors = BuildMagmawShadowActorObservations(snapshot);
    Cohort().MagmawTransferLaneTaskShadow =
        BotEncounter::MagmawTransferLaneTaskShadow::Reconcile(
            Cohort().MagmawTransferLaneTaskShadow,
            Cohort().MagmawFacts->Facts(), snapshot,
            Cohort().MagmawCoordinatorShadow->Plan(), actors);
}

void BotWorldPopulationMgr::ObserveMagmawTransferLaneIntentComparison(
    WorldBotState& state, ObjectGuid actor,
    std::optional<BotNativeAction::Candidate> const& legacyMovement,
    uint64 legacyTransitionGeneration)
{
    auto const& shadow = Cohort().MagmawTransferLaneTaskShadow;
    static std::vector<BotEncounter::MagmawTransferLaneTask> const noTasks;
    auto const& tasks = shadow ? shadow->Tasks() : noTasks;
    state.MagmawTransferLaneIntentComparison =
        BotEncounter::ObserveMagmawTransferLaneIntents(tasks, actor,
            legacyMovement, legacyTransitionGeneration);
}

std::string BotWorldPopulationMgr::BuildMagmawTransferLaneIntentComparisonJson(
    WorldBotState const& state) const
{
    using namespace BotEncounter;
    MagmawTransferLaneIntentComparison const& comparison =
        state.MagmawTransferLaneIntentComparison;
    std::ostringstream json;
    json << "{\"observed\":" << (comparison.Observed ? "true" : "false")
         << ",\"outcome\":\"" << ToString(comparison.Outcome) << "\""
         << ",\"proposal_count\":" << comparison.ProposalCount
         << ",\"movement_proposal_count\":"
         << comparison.MovementProposalCount
         << ",\"ambiguous\":"
         << (comparison.Ambiguous() ? "true" : "false")
         << ",\"shadow_actor_guid\":"
         << comparison.ShadowActor.GetCounter()
         << ",\"legacy_actor_guid\":"
         << comparison.LegacyActor.GetCounter()
         << ",\"shadow_task_generation\":"
         << comparison.ShadowTaskGeneration
         << ",\"legacy_event_generation\":"
         << comparison.LegacyEventGeneration
         << ",\"expected_legacy_transition_generation\":"
         << comparison.ExpectedLegacyTransitionGeneration
         << ",\"divergences\":[";
    bool first = true;
    auto append = [&](MagmawTransferLaneIntentDivergence reason,
        char const* name)
    {
        if (!comparison.Has(reason))
            return;
        json << (first ? "" : ",") << '"' << name << '"';
        first = false;
    };
    append(MagmawTransferLaneIntentDivergence::AmbiguousShadowMovement,
        "ambiguous_shadow_movement");
    append(MagmawTransferLaneIntentDivergence::MissingExecutionContract,
        "missing_execution_contract");
    append(MagmawTransferLaneIntentDivergence::StrategyIdentity,
        "strategy_identity");
    append(MagmawTransferLaneIntentDivergence::MechanicIdentity,
        "mechanic_identity");
    append(MagmawTransferLaneIntentDivergence::LifecycleScope,
        "lifecycle_scope");
    append(MagmawTransferLaneIntentDivergence::ActionKind, "action_kind");
    append(MagmawTransferLaneIntentDivergence::Actor, "actor");
    append(MagmawTransferLaneIntentDivergence::GenerationCorrelation,
        "generation_correlation");
    append(MagmawTransferLaneIntentDivergence::MovementResource,
        "movement_resource");
    append(MagmawTransferLaneIntentDivergence::DestinationNonFinite,
        "destination_non_finite");
    append(MagmawTransferLaneIntentDivergence::Destination2d,
        "destination_2d");
    append(MagmawTransferLaneIntentDivergence::DestinationZ,
        "destination_z");
    append(MagmawTransferLaneIntentDivergence::PreemptCasting,
        "preempt_casting");
    append(MagmawTransferLaneIntentDivergence::ActionPriority,
        "action_priority");
    append(MagmawTransferLaneIntentDivergence::Utility, "utility");
    append(MagmawTransferLaneIntentDivergence::Expiry, "expiry");
    json << "]}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildMagmawTransferLaneTaskShadowJson()
    const
{
    using namespace BotEncounter;
    auto const& shadow = Cohort().MagmawTransferLaneTaskShadow;
    if (!shadow)
        return "{\"active\":false}";
    std::ostringstream json;
    json << "{\"active\":" << (shadow->Episode() ? "true" : "false")
         << ",\"source_revision\":" << shadow->SourceRevision();
    if (shadow->Episode())
    {
        MagmawTransferLaneEpisode const& episode = *shadow->Episode();
        json << ",\"episode_generation\":"
             << episode.Id.EpisodeGeneration
             << ",\"mechanic_generation\":"
             << episode.Id.MechanicGeneration
             << ",\"raid_plan_generation\":"
             << episode.Id.RaidPlanGeneration
             << ",\"roster_generation\":"
             << episode.Id.RosterGeneration
             << ",\"direction\":\"" << ToString(episode.Direction)
             << "\",\"fire_mage_guid\":"
             << episode.FireMageGuid.GetCounter()
             << ",\"hunter_guid\":" << episode.HunterGuid.GetCounter();
    }
    json << ",\"tasks\":[";
    for (size_t index = 0; index < shadow->Tasks().size(); ++index)
    {
        if (index)
            json << ',';
        MagmawTransferLaneTask const& task = shadow->Tasks()[index];
        json << "{\"actor_guid\":" << task.Id.ActorGuid.GetCounter()
             << ",\"task_generation\":" << task.Id.TaskGeneration
             << ",\"state\":\"" << ToString(task.State)
             << "\",\"suspension\":\"" << ToString(task.Suspension)
             << "\",\"failure\":\"" << ToString(task.Failure)
             << "\",\"movement_observation\":\""
             << ToString(task.MovementDisposition)
             << "\",\"best_distance\":" << task.BestDistance
             << ",\"observation_samples\":" << task.ObservationSamples
             << ",\"progress_samples\":" << task.ProgressSamples << '}';
    }
    json << "],\"retired_task_count\":" << shadow->Retired().size()
         << ",\"intent_comparisons\":[";
    for (size_t index = 0; index < Party().Bots.size(); ++index)
    {
        if (index)
            json << ',';
        WorldBotState const& state = Party().Bots[index];
        json << "{\"actor_guid\":" << state.Guid.GetCounter()
             << ",\"comparison\":"
             << BuildMagmawTransferLaneIntentComparisonJson(state) << '}';
    }
    json << "]}";
    return json.str();
}
