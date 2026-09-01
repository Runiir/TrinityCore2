#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawCoordinator.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneDiagnostics.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneTask.h"

#include <algorithm>
#include <initializer_list>

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
        {
            observation.Movement.CurrentLease = state->MovementLease;
            observation.NativeOutcome = state->MagmawTransferLaneNativeOutcome;
        }
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
    BotEncounter::ObserveMagmawTransferLaneIntentEpisode(
        state.MagmawTransferLaneIntentEpisodeAccumulator,
        state.MagmawTransferLaneIntentComparison);
}

std::string BotWorldPopulationMgr::BuildMagmawTransferLaneIntentComparisonJson(
    WorldBotState const& state) const
{
    return BotEncounter::BuildMagmawTransferLaneIntentComparisonDiagnosticsJson(
        state.MagmawTransferLaneIntentComparison);
}

std::string BotWorldPopulationMgr::BuildMagmawTransferLaneTaskShadowJson()
    const
{
    using namespace BotEncounter;
    auto const& shadow = Cohort().MagmawTransferLaneTaskShadow;
    std::vector<MagmawTransferLaneActorIntentDiagnostics> actors;
    actors.reserve(Party().Bots.size());
    for (WorldBotState const& state : Party().Bots)
    {
        actors.push_back({ state.Guid,
            state.MagmawTransferLaneIntentComparison,
            state.MagmawTransferLaneIntentEpisodeAccumulator });
    }
    return BuildMagmawTransferLaneTaskShadowDiagnosticsJson(
        shadow.get(), actors);
}
