from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
INCLUDES = [
    "-I", str(ROOT / "src/server/game"),
    "-I", str(ROOT / "src/server/game/Entities/Object"),
    "-I", str(ROOT / "src/common"),
    "-I", str(ROOT / "src/common/Utilities"),
    "-I", str(ROOT / "src/common/Logging"),
    "-I", str(ROOT / "src/common/Debugging"),
]


def test_magmaw_persistent_task_shadow_multitick_fixture(tmp_path: Path) -> None:
    source = tmp_path / "magmaw_persistent_task_shadow.cpp"
    binary = tmp_path / "magmaw_persistent_task_shadow"
    source.write_text(r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawCoordinator.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneTask.h"

#include <algorithm>
#include <cassert>
#include <string>
#include <vector>

using namespace BotEncounter;
using TaskState = BotDecision::PersistentTaskState;
using Suspension = BotDecision::PersistentTaskSuspension;

std::string ObjectGuid::ToString() const
{
    return std::to_string(GetRawValue());
}

static ObjectGuid PlayerGuid(uint32 counter)
{
    return ObjectGuid(HighGuid::Player, counter);
}

static ActorSnapshot Player(uint32 counter, char const* role,
    char const* spec, Vector3 position)
{
    ActorSnapshot actor;
    actor.Guid = PlayerGuid(counter);
    actor.Kind = ActorKind::Player;
    actor.Role = role;
    actor.ClassSpec = spec;
    actor.Position = position;
    actor.Alive = true;
    return actor;
}

static ActorSnapshot Unit(uint32 entry, uint32 counter, Vector3 position)
{
    ActorSnapshot actor;
    actor.Guid = ObjectGuid(HighGuid::Unit, entry, counter);
    actor.Entry = entry;
    actor.Position = position;
    actor.Alive = true;
    actor.Attackable = true;
    actor.Selectable = true;
    return actor;
}

static Blackboard Board()
{
    Blackboard board;
    board.CurrentScope = { "magmaw-shadow", 7, 2, 5,
        "bwd.magmaw.encounter", 669, 23, "magmaw", 91, 4 };
    board.Revision = 10;
    board.ObservedAtMs = 1000;
    board.NativeBossState = "in_progress";
    board.NativeEncounterPhase = "combat";
    board.NativeWipeState = "engaged";
    board.EncounterIdentityAuthoritative = true;
    board.EncounterEpochAuthoritative = true;
    board.EncounterArenaObservationComplete = true;
    NativeEncounterLifecycle native;
    native.Id = "blackwing_descent.magmaw";
    native.BossId = 0;
    native.BossEntry = 41570;
    native.BossGuid = ObjectGuid(HighGuid::Unit, uint32(41570), uint32(1));
    native.State = NativeEncounterState::InProgress;
    native.ServerEpoch = 91;
    native.InstanceLifecycleEpoch = 3;
    native.AttemptEpoch = 4;
    native.EncounterEpoch = 4;
    native.Authoritative = true;
    board.NativeEncounter = native;
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Route.NavigationHints = { { 0.0f, -60.0f, 210.0f } };
    board.Players = {
        Player(100, "tank", "protection_paladin", { 0, -4, 210 }),
        Player(101, "tank", "blood_death_knight", { 0, -4, 210 }),
        Player(200, "healer", "restoration_druid", { 0, -8, 210 }),
        Player(201, "healer", "holy_paladin", { 0, -8, 210 }),
        Player(300, "dps", "fire_mage", { 24, -30, 210 }),
        Player(301, "dps", "fire_mage", { 20, -30, 210 }),
        Player(400, "dps", "marksmanship_hunter", { 24, -30, 210 }),
        Player(401, "dps", "marksmanship_hunter", { 20, -30, 210 }),
        Player(500, "dps", "affliction_warlock", { 0, -8, 210 }),
        Player(600, "dps", "elemental_shaman", { 0, -8, 210 }) };
    ActorSnapshot boss = Unit(41570, 1, { 0, 0, 210 });
    boss.InCombat = true;
    boss.VictimGuid = PlayerGuid(100);
    board.Hostiles.push_back(boss);
    return board;
}

static MagmawRosterView Roster(Scope const& scope)
{
    MagmawRosterView roster;
    roster.Lifecycle = scope;
    roster.Generation = 9;
    roster.ExpectedSize = 10;
    roster.Mode = MagmawRaidMode::Normal10;
    roster.Authoritative = true;
    for (ActorSnapshot const& actor : Board().Players)
        roster.Members.push_back({ actor.Guid,
            "slot_" + std::to_string(actor.Guid.GetCounter()), actor.Role,
            actor.ClassSpec, true, true });
    return roster;
}

static ActorSnapshot& Actor(Blackboard& board, uint32 counter)
{
    auto itr = std::find_if(board.Players.begin(), board.Players.end(),
        [counter](ActorSnapshot const& actor)
        {
            return actor.Guid == PlayerGuid(counter);
        });
    assert(itr != board.Players.end());
    return *itr;
}

static std::vector<MagmawTransferLaneActorObservation> Observations(
    Blackboard const& board, uint64 mageLife = 0, uint64 hunterLife = 0)
{
    std::vector<MagmawTransferLaneActorObservation> result;
    for (ActorSnapshot const& actor : board.Players)
        result.push_back({ actor.Guid,
            { board.CurrentScope.WipeGeneration,
                actor.Alive ? 0u : mageLife + 1,
                actor.Guid == PlayerGuid(400) ? hunterLife : mageLife, true },
            actor.Position, true, actor.Alive, {}, std::nullopt });
    return result;
}

static MagmawTransferLaneTask const& Task(
    MagmawTransferLaneTaskShadow const& shadow, uint32 counter)
{
    auto itr = std::find_if(shadow.Tasks().begin(), shadow.Tasks().end(),
        [counter](MagmawTransferLaneTask const& task)
        {
            return task.Id.ActorGuid == PlayerGuid(counter);
        });
    assert(itr != shadow.Tasks().end());
    return *itr;
}

int main()
{
    Blackboard board = Board();
    MagmawRosterView roster = Roster(board.CurrentScope);
    auto facts = MagmawFactsCache::ForSnapshot(nullptr, board);
    auto coordinator = MagmawCoordinator::Reconcile(nullptr,
        facts->Facts(), board, roster);
    auto shadow = MagmawTransferLaneTaskShadow::Reconcile(nullptr,
        facts->Facts(), board, coordinator->Plan(), Observations(board));
    assert(!shadow->Episode() && shadow->Tasks().empty());

    board.Summons.push_back(Unit(41843, 70, { 10, -20, 210 }));
    ++board.Revision;
    board.ObservedAtMs += 100;
    facts = MagmawFactsCache::ForSnapshot(facts, board);
    coordinator = MagmawCoordinator::Reconcile(coordinator,
        facts->Facts(), board, roster);
    shadow = MagmawTransferLaneTaskShadow::Reconcile(shadow,
        facts->Facts(), board, coordinator->Plan(), Observations(board));
    assert(shadow->Episode() && shadow->Tasks().size() == 2);
    assert(shadow->Episode()->Direction == MagmawTransferLaneDirection::Right);
    assert(shadow->Episode()->FireMageGuid == PlayerGuid(300));
    assert(shadow->Episode()->HunterGuid == PlayerGuid(400));
    assert(Task(*shadow, 300).Id.TaskGeneration
        != Task(*shadow, 400).Id.TaskGeneration);
    assert(Task(*shadow, 300).Id.ActorGuid != Task(*shadow, 400).Id.ActorGuid);
    auto sameRevision = MagmawTransferLaneTaskShadow::Reconcile(shadow,
        facts->Facts(), board, coordinator->Plan(), Observations(board));
    assert(sameRevision == shadow);

    // Arrival cannot terminate a task while typed safety owns movement.
    // Recovery preempts even at the immutable destination; a same-scope
    // Hazard aimed elsewhere does too. Clearing safety completes the same
    // task identities and destinations on the next observation.
    {
        Blackboard arrivalBoard = board;
        Actor(arrivalBoard, 300).Position =
            Task(*shadow, 300).Destination;
        Actor(arrivalBoard, 400).Position =
            Task(*shadow, 400).Destination;
        ++arrivalBoard.Revision;
        arrivalBoard.ObservedAtMs += 10;
        auto arrivalFacts = MagmawFactsCache::ForSnapshot(
            facts, arrivalBoard);
        auto arrivalCoordinator = MagmawCoordinator::Reconcile(
            coordinator, arrivalFacts->Facts(), arrivalBoard, roster);
        auto arrivalObservations = Observations(arrivalBoard);

        BotMovementArbitration::Lease arrivalRecovery;
        arrivalRecovery.MovementOwner =
            BotMovementArbitration::Owner::Recovery;
        arrivalRecovery.MovementPriority =
            BotMovementArbitration::Priority::Recovery;
        arrivalRecovery.ExpiresAtMs = arrivalBoard.ObservedAtMs + 1000;
        arrivalRecovery.MovementScope = MagmawTransferLaneMovementScope(
            arrivalBoard.CurrentScope);
        arrivalRecovery.X = Task(*shadow, 300).Destination.X;
        arrivalRecovery.Y = Task(*shadow, 300).Destination.Y;
        arrivalRecovery.Z = Task(*shadow, 300).Destination.Z;
        arrivalObservations[4].Movement.CurrentLease = arrivalRecovery;

        BotMovementArbitration::Lease arrivalHazard = arrivalRecovery;
        arrivalHazard.MovementOwner =
            BotMovementArbitration::Owner::Hazard;
        arrivalHazard.MovementPriority =
            BotMovementArbitration::Priority::Hazard;
        arrivalHazard.X += 10.0f;
        arrivalObservations[6].Movement.CurrentLease = arrivalHazard;

        auto arrivalShadow = MagmawTransferLaneTaskShadow::Reconcile(
            shadow, arrivalFacts->Facts(), arrivalBoard,
            arrivalCoordinator->Plan(), arrivalObservations);
        assert(Task(*arrivalShadow, 300).State == TaskState::Suspended);
        assert(Task(*arrivalShadow, 300).Suspension
            == Suspension::SafetyPreempted);
        assert(Task(*arrivalShadow, 400).State == TaskState::Suspended);
        assert(Task(*arrivalShadow, 400).Suspension
            == Suspension::SafetyPreempted);
        uint64 const arrivalMageGeneration =
            Task(*arrivalShadow, 300).Id.TaskGeneration;
        uint64 const arrivalHunterGeneration =
            Task(*arrivalShadow, 400).Id.TaskGeneration;
        Vector3 const arrivalMageDestination =
            Task(*arrivalShadow, 300).Destination;
        Vector3 const arrivalHunterDestination =
            Task(*arrivalShadow, 400).Destination;

        ++arrivalBoard.Revision;
        arrivalBoard.ObservedAtMs += 10;
        arrivalFacts = MagmawFactsCache::ForSnapshot(
            arrivalFacts, arrivalBoard);
        arrivalCoordinator = MagmawCoordinator::Reconcile(
            arrivalCoordinator, arrivalFacts->Facts(), arrivalBoard, roster);
        arrivalShadow = MagmawTransferLaneTaskShadow::Reconcile(
            arrivalShadow, arrivalFacts->Facts(), arrivalBoard,
            arrivalCoordinator->Plan(), Observations(arrivalBoard));
        assert(Task(*arrivalShadow, 300).State == TaskState::Succeeded);
        assert(Task(*arrivalShadow, 400).State == TaskState::Succeeded);
        assert(Task(*arrivalShadow, 300).Id.TaskGeneration
            == arrivalMageGeneration);
        assert(Task(*arrivalShadow, 400).Id.TaskGeneration
            == arrivalHunterGeneration);
        assert(Task(*arrivalShadow, 300).Destination.X
                == arrivalMageDestination.X
            && Task(*arrivalShadow, 300).Destination.Y
                == arrivalMageDestination.Y
            && Task(*arrivalShadow, 300).Destination.Z
                == arrivalMageDestination.Z);
        assert(Task(*arrivalShadow, 400).Destination.X
                == arrivalHunterDestination.X
            && Task(*arrivalShadow, 400).Destination.Y
                == arrivalHunterDestination.Y
            && Task(*arrivalShadow, 400).Destination.Z
                == arrivalHunterDestination.Z);
    }
    uint64 const episodeGeneration = shadow->Episode()->Id.EpisodeGeneration;
    uint64 const mageTaskGeneration = Task(*shadow, 300).Id.TaskGeneration;
    uint64 const hunterTaskGeneration = Task(*shadow, 400).Id.TaskGeneration;

    // Hazard GUID churn is not a new episode. Position is semantic progress.
    board.Summons[0] = Unit(41843, 71, { 12, -21, 210 });
    Actor(board, 300).Position = { 10, -30, 210 };
    ++board.Revision;
    board.ObservedAtMs += 100;
    facts = MagmawFactsCache::ForSnapshot(facts, board);
    coordinator = MagmawCoordinator::Reconcile(coordinator,
        facts->Facts(), board, roster);
    auto observations = Observations(board);
    BotMovementArbitration::Lease recovery;
    recovery.MovementOwner = BotMovementArbitration::Owner::Recovery;
    recovery.MovementPriority = BotMovementArbitration::Priority::Recovery;
    recovery.ExpiresAtMs = board.ObservedAtMs + 1000;
    recovery.MovementScope = MagmawTransferLaneMovementScope(
        board.CurrentScope);
    recovery.X = shadow->Episode()->Destination.X;
    recovery.Y = shadow->Episode()->Destination.Y;
    recovery.Z = shadow->Episode()->Destination.Z;
    observations[4].Movement.CurrentLease = recovery;
    shadow = MagmawTransferLaneTaskShadow::Reconcile(shadow,
        facts->Facts(), board, coordinator->Plan(), observations);
    assert(shadow->Episode()->Id.EpisodeGeneration == episodeGeneration);
    assert(Task(*shadow, 300).Id.TaskGeneration == mageTaskGeneration);
    assert(Task(*shadow, 400).Id.TaskGeneration == hunterTaskGeneration);
    assert(Task(*shadow, 300).BestDistance
        < Task(*shadow, 300).InitialDistance);
    assert(Task(*shadow, 300).State == TaskState::Suspended);
    assert(Task(*shadow, 300).Suspension == Suspension::SafetyPreempted);

    // Observation loss suspends. Lease absence does not.
    board.Players.erase(std::remove_if(board.Players.begin(),
        board.Players.end(), [](ActorSnapshot const& actor)
        {
            return actor.Guid == PlayerGuid(400);
        }), board.Players.end());
    ++board.Revision;
    board.ObservedAtMs += 100;
    facts = MagmawFactsCache::ForSnapshot(facts, board);
    coordinator = MagmawCoordinator::Reconcile(coordinator,
        facts->Facts(), board, roster);
    observations = Observations(board);
    shadow = MagmawTransferLaneTaskShadow::Reconcile(shadow,
        facts->Facts(), board, coordinator->Plan(), observations);
    assert(Task(*shadow, 400).State == TaskState::Suspended);
    assert(Task(*shadow, 400).Suspension
        == Suspension::ObservationUnavailable);
    uint32 const hunterProgressSamples = Task(*shadow, 400).ProgressSamples;

    board.Players.push_back(Player(400, "dps", "marksmanship_hunter",
        { 24, -30, 210 }));
    ++board.Revision;
    board.ObservedAtMs += 100;
    facts = MagmawFactsCache::ForSnapshot(facts, board);
    coordinator = MagmawCoordinator::Reconcile(coordinator,
        facts->Facts(), board, roster);
    observations = Observations(board);
    auto hunter = std::find_if(observations.begin(), observations.end(),
        [](MagmawTransferLaneActorObservation const& actor)
        {
            return actor.Guid == PlayerGuid(400);
        });
    shadow = MagmawTransferLaneTaskShadow::Reconcile(shadow,
        facts->Facts(), board, coordinator->Plan(), observations);
    assert(Task(*shadow, 400).State == TaskState::Running);
    assert(Task(*shadow, 400).Suspension == Suspension::None);
    assert(Task(*shadow, 400).MovementDisposition
        == MagmawTransferLaneMovementDisposition::NoLease);
    assert(Task(*shadow, 400).ProgressSamples == hunterProgressSamples);

    // Matching legacy movement stays owned; a mismatched current Hazard then
    // suspends. Clearing it resumes the exact same task identity and
    // destination and pauses the no-progress clock.
    uint64 const retainedHunterGeneration =
        Task(*shadow, 400).Id.TaskGeneration;
    Vector3 const retainedHunterDestination = Task(*shadow, 400).Destination;
    uint32 const progressBeforeLease = Task(*shadow, 400).ProgressSamples;

    BotMovementArbitration::Lease expired = recovery;
    expired.MovementOwner = BotMovementArbitration::Owner::Hazard;
    expired.MovementPriority = BotMovementArbitration::Priority::Hazard;
    expired.ExpiresAtMs = board.ObservedAtMs;
    ++board.Revision;
    facts = MagmawFactsCache::ForSnapshot(facts, board);
    coordinator = MagmawCoordinator::Reconcile(coordinator,
        facts->Facts(), board, roster);
    observations = Observations(board);
    hunter = std::find_if(observations.begin(), observations.end(),
        [](MagmawTransferLaneActorObservation const& actor)
        {
            return actor.Guid == PlayerGuid(400);
        });
    hunter->Movement.CurrentLease = expired;
    shadow = MagmawTransferLaneTaskShadow::Reconcile(shadow,
        facts->Facts(), board, coordinator->Plan(), observations);
    assert(Task(*shadow, 400).State == TaskState::Running);
    assert(Task(*shadow, 400).MovementDisposition
        == MagmawTransferLaneMovementDisposition::ExpiredLease);

    ++board.Revision;
    ++board.ObservedAtMs;
    facts = MagmawFactsCache::ForSnapshot(facts, board);
    coordinator = MagmawCoordinator::Reconcile(coordinator,
        facts->Facts(), board, roster);
    observations = Observations(board);
    hunter = std::find_if(observations.begin(), observations.end(),
        [](MagmawTransferLaneActorObservation const& actor)
        {
            return actor.Guid == PlayerGuid(400);
        });
    hunter->Movement.CurrentLease = expired;
    shadow = MagmawTransferLaneTaskShadow::Reconcile(shadow,
        facts->Facts(), board, coordinator->Plan(), observations);
    assert(Task(*shadow, 400).State == TaskState::Running);
    assert(Task(*shadow, 400).MovementDisposition
        == MagmawTransferLaneMovementDisposition::ExpiredLease);
    assert(Task(*shadow, 400).ProgressSamples == progressBeforeLease);

    // The legacy transfer is a Hazard lease. Matching the immutable task
    // destination is its own movement, and refreshing only that short lease
    // is neither safety preemption nor semantic progress.
    BotMovementArbitration::Lease hazard = recovery;
    hazard.MovementOwner = BotMovementArbitration::Owner::Hazard;
    hazard.MovementPriority = BotMovementArbitration::Priority::Hazard;
    hazard.X = retainedHunterDestination.X;
    hazard.Y = retainedHunterDestination.Y;
    hazard.Z = retainedHunterDestination.Z;
    ++board.Revision;
    board.ObservedAtMs += 100;
    facts = MagmawFactsCache::ForSnapshot(facts, board);
    coordinator = MagmawCoordinator::Reconcile(coordinator,
        facts->Facts(), board, roster);
    observations = Observations(board);
    hunter = std::find_if(observations.begin(), observations.end(),
        [](MagmawTransferLaneActorObservation const& actor)
        {
            return actor.Guid == PlayerGuid(400);
        });
    hazard.ExpiresAtMs = board.ObservedAtMs + 1000;
    hunter->Movement.CurrentLease = hazard;
    shadow = MagmawTransferLaneTaskShadow::Reconcile(shadow,
        facts->Facts(), board, coordinator->Plan(), observations);
    assert(Task(*shadow, 400).State == TaskState::Running);
    assert(Task(*shadow, 400).MovementDisposition
        == MagmawTransferLaneMovementDisposition::OwnHazardTransfer);
    assert(Task(*shadow, 400).ProgressSamples == progressBeforeLease);

    ++board.Revision;
    board.ObservedAtMs += 100;
    facts = MagmawFactsCache::ForSnapshot(facts, board);
    coordinator = MagmawCoordinator::Reconcile(coordinator,
        facts->Facts(), board, roster);
    observations = Observations(board);
    hunter = std::find_if(observations.begin(), observations.end(),
        [](MagmawTransferLaneActorObservation const& actor)
        {
            return actor.Guid == PlayerGuid(400);
        });
    hazard.ExpiresAtMs = board.ObservedAtMs + 1000;
    hunter->Movement.CurrentLease = hazard;
    shadow = MagmawTransferLaneTaskShadow::Reconcile(shadow,
        facts->Facts(), board, coordinator->Plan(), observations);
    assert(Task(*shadow, 400).State == TaskState::Running);
    assert(Task(*shadow, 400).ProgressSamples == progressBeforeLease);

    ++board.Revision;
    board.ObservedAtMs += 100;
    facts = MagmawFactsCache::ForSnapshot(facts, board);
    coordinator = MagmawCoordinator::Reconcile(coordinator,
        facts->Facts(), board, roster);
    observations = Observations(board);
    hunter = std::find_if(observations.begin(), observations.end(),
        [](MagmawTransferLaneActorObservation const& actor)
        {
            return actor.Guid == PlayerGuid(400);
        });
    hazard.ExpiresAtMs = board.ObservedAtMs
        + MagmawTransferLaneTaskShadow::NoProgressFailureMs + 1000;
    hazard.X += 10.0f;
    hunter->Movement.CurrentLease = hazard;
    shadow = MagmawTransferLaneTaskShadow::Reconcile(shadow,
        facts->Facts(), board, coordinator->Plan(), observations);
    assert(Task(*shadow, 400).State == TaskState::Suspended);
    assert(Task(*shadow, 400).Suspension == Suspension::SafetyPreempted);

    Actor(board, 300).Position = shadow->Episode()->Destination;
    board.ObservedAtMs += MagmawTransferLaneTaskShadow::NoProgressFailureMs;
    ++board.Revision;
    facts = MagmawFactsCache::ForSnapshot(facts, board);
    coordinator = MagmawCoordinator::Reconcile(coordinator,
        facts->Facts(), board, roster);
    observations = Observations(board);
    hunter = std::find_if(observations.begin(), observations.end(),
        [](MagmawTransferLaneActorObservation const& actor)
        {
            return actor.Guid == PlayerGuid(400);
        });
    hazard.ExpiresAtMs = board.ObservedAtMs + 1000;
    hunter->Movement.CurrentLease = hazard;
    shadow = MagmawTransferLaneTaskShadow::Reconcile(shadow,
        facts->Facts(), board, coordinator->Plan(), observations);
    assert(Task(*shadow, 400).State == TaskState::Suspended);

    ++board.Revision;
    board.ObservedAtMs += 100;
    facts = MagmawFactsCache::ForSnapshot(facts, board);
    coordinator = MagmawCoordinator::Reconcile(coordinator,
        facts->Facts(), board, roster);
    shadow = MagmawTransferLaneTaskShadow::Reconcile(shadow,
        facts->Facts(), board, coordinator->Plan(), Observations(board));
    assert(Task(*shadow, 400).State == TaskState::Running);
    assert(Task(*shadow, 400).Id.TaskGeneration == retainedHunterGeneration);
    assert(Task(*shadow, 400).Destination.X == retainedHunterDestination.X
        && Task(*shadow, 400).Destination.Y == retainedHunterDestination.Y
        && Task(*shadow, 400).Destination.Z == retainedHunterDestination.Z);

    // Succeed one actor and fail the other only after a full active
    // no-position-progress window following safety clearance.
    board.ObservedAtMs += MagmawTransferLaneTaskShadow::NoProgressFailureMs;
    ++board.Revision;
    facts = MagmawFactsCache::ForSnapshot(facts, board);
    coordinator = MagmawCoordinator::Reconcile(coordinator,
        facts->Facts(), board, roster);
    shadow = MagmawTransferLaneTaskShadow::Reconcile(shadow,
        facts->Facts(), board, coordinator->Plan(), Observations(board));
    assert(Task(*shadow, 300).State == TaskState::Succeeded);
    assert(Task(*shadow, 400).State == TaskState::Failed);
    assert(Task(*shadow, 400).Failure
        == MagmawTransferLaneFailure::NoSemanticProgress);

    // Death replaces the coordinator assignment and therefore the episode.
    Actor(board, 300).Alive = false;
    ++board.Revision;
    board.ObservedAtMs += 100;
    facts = MagmawFactsCache::ForSnapshot(facts, board);
    coordinator = MagmawCoordinator::Reconcile(coordinator,
        facts->Facts(), board, roster);
    shadow = MagmawTransferLaneTaskShadow::Reconcile(shadow,
        facts->Facts(), board, coordinator->Plan(), Observations(board, 10));
    assert(shadow->Episode()->FireMageGuid == PlayerGuid(301));
    assert(shadow->Episode()->Id.EpisodeGeneration > episodeGeneration);
    assert(Task(*shadow, 301).Id.ActorGuid == PlayerGuid(301));

    // An actor-life change replaces only that bot's task in the same episode.
    uint64 const replacementEpisode = shadow->Episode()->Id.EpisodeGeneration;
    uint64 const oldHunterTask = Task(*shadow, 400).Id.TaskGeneration;
    ++board.Revision;
    board.ObservedAtMs += 100;
    facts = MagmawFactsCache::ForSnapshot(facts, board);
    coordinator = MagmawCoordinator::Reconcile(coordinator,
        facts->Facts(), board, roster);
    observations = Observations(board, 10, 22);
    hunter = std::find_if(observations.begin(), observations.end(),
        [](MagmawTransferLaneActorObservation const& actor)
        {
            return actor.Guid == PlayerGuid(400);
        });
    // The raw stale life values remain visible, but an inexact wipe/map/
    // instance observation is not authoritative and cannot replace a task.
    hunter->Life.WipeGeneration = 99;
    hunter->Life.DeathSequence = 88;
    hunter->Life.ResurrectionSequence = 77;
    hunter->Life.Authoritative = false;
    shadow = MagmawTransferLaneTaskShadow::Reconcile(shadow,
        facts->Facts(), board, coordinator->Plan(), observations);
    assert(shadow->Episode()->Id.EpisodeGeneration == replacementEpisode);
    assert(Task(*shadow, 400).Id.TaskGeneration == oldHunterTask);

    ++board.Revision;
    board.ObservedAtMs += 100;
    facts = MagmawFactsCache::ForSnapshot(facts, board);
    coordinator = MagmawCoordinator::Reconcile(coordinator,
        facts->Facts(), board, roster);
    shadow = MagmawTransferLaneTaskShadow::Reconcile(shadow,
        facts->Facts(), board, coordinator->Plan(), Observations(board, 10, 22));
    assert(Task(*shadow, 400).Id.TaskGeneration != oldHunterTask);
    assert(std::any_of(shadow->Retired().begin(), shadow->Retired().end(),
        [oldHunterTask](MagmawRetiredTransferLaneTask const& retired)
        {
            return retired.Task.Id.TaskGeneration == oldHunterTask
                && retired.Task.State == TaskState::Aborted
                && retired.Reason
                    == MagmawTransferLaneRetirement::ActorLifeChanged;
        }));

    // Exact route identity change retires running tasks as aborted.
    ++board.CurrentScope.RouteGeneration;
    roster.Lifecycle = board.CurrentScope;
    ++board.Revision;
    board.ObservedAtMs += 100;
    facts = MagmawFactsCache::ForSnapshot(facts, board);
    coordinator = MagmawCoordinator::Reconcile(coordinator,
        facts->Facts(), board, roster);
    shadow = MagmawTransferLaneTaskShadow::Reconcile(shadow,
        facts->Facts(), board, coordinator->Plan(), Observations(board, 10, 22));
    assert(!shadow->Episode());
    assert(std::any_of(shadow->Retired().begin(), shadow->Retired().end(),
        [](MagmawRetiredTransferLaneTask const& retired)
        {
            return retired.Task.State == TaskState::Aborted
                && retired.Reason == MagmawTransferLaneRetirement::
                    EncounterLifecycleChanged;
        }));
}
''', encoding="utf-8")
    subprocess.run([
        "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *INCLUDES,
        str(source),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
            "Encounters/Magmaw/BotMagmawFacts.cpp"),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
            "Encounters/Magmaw/BotMagmawCoordinator.cpp"),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
            "Encounters/Magmaw/BotMagmawCoordinatorAssignments.cpp"),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
            "Encounters/Magmaw/BotMagmawTransferLaneTask.cpp"),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
            "Encounters/Magmaw/BotMagmawTransferLaneTaskRunner.cpp"),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
            "Encounters/Magmaw/BotMagmawTransferLaneMovementObservation.cpp"),
        "-o", str(binary),
    ], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_magmaw_task_shadow_is_production_wired_with_default_off_authority() -> None:
    bots = ROOT / "src/server/game/Bots"
    publisher = (bots / "BotWorldPopulationMgrEncounterBlackboard.cpp").read_text()
    runtime = (bots / "BotWorldPopulationMgrRuntimeContracts.h").read_text()
    adapter = (bots / "BotWorldPopulationMgrMagmawTaskShadow.cpp").read_text()
    preparation = (bots / "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp").read_text()
    config = (bots / "BotWorldPopulationMgrConfig.h").read_text()
    task = (bots / "Content/Raids/BlackwingDescent/Encounters/Magmaw/"
        "BotMagmawTransferLaneTask.cpp").read_text()

    assert "ReconcileMagmawTransferLaneTaskShadow(*snapshot);" in publisher
    assert "MagmawCoordinatorShadow" in runtime
    assert "MagmawTransferLaneTaskShadow" in runtime
    assert "RaidRuntime const& raid = Cohort().Raid;" in adapter
    assert "Cohort().RosterLeases" in adapter
    assert "raid.AdmissionReceiptByGuid" in adapter
    assert "LeaseOwnedByCurrentCohort" in adapter
    assert "signal->second.Initialized" in adapter
    assert ("signal->second.WipeGeneration\n"
        "                    == snapshot.CurrentScope.WipeGeneration") in adapter
    assert "signal->second.MapId == snapshot.CurrentScope.MapId" in adapter
    assert ("signal->second.InstanceId\n"
        "                    == snapshot.CurrentScope.InstanceId") in adapter
    assert "MagmawRaidMode" in adapter
    assert "BuildMagmawTransferLaneTaskShadowJson" in adapter
    assert "SelectMagmawTransferLaneAuthority(" in preparation
    assert "bool MagmawTransferLaneTaskAuthority = false;" in config
    assert "MagmawCoordinatorShadow" not in preparation
    assert "BotAdaptiveMagmawStrategy" not in task
    assert "MagmawLaneTransitionState" not in task
    assert "BotActionArbitration::Kernel" not in adapter + task
    assert "MotionMaster" not in adapter + task
    assert "PathGenerator" not in adapter + task
