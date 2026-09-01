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
    "-I", str(ROOT / "dep/g3dlite/include"),
]


def test_personal_parasite_escape_task_crosses_production_adapter(
    tmp_path: Path,
) -> None:
    source = tmp_path / "personal_parasite_escape_task.cpp"
    binary = tmp_path / "personal_parasite_escape_task"
    source.write_text(r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMovementKernelAdapter.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawPersonalParasiteEscapeDiagnostics.h"

#include <cassert>
#include <string>

using namespace BotEncounter;
using TaskState = BotDecision::PersistentTaskState;

std::string ObjectGuid::ToString() const
{
    return std::to_string(GetRawValue());
}

static ObjectGuid PlayerGuid(uint32 counter)
{
    return ObjectGuid(HighGuid::Player, counter);
}

static ActorSnapshot Player(uint32 counter, char const* spec,
    Vector3 position)
{
    ActorSnapshot actor;
    actor.Guid = PlayerGuid(counter);
    actor.Kind = ActorKind::Player;
    actor.Role = "dps";
    actor.ClassSpec = spec;
    actor.Position = position;
    actor.Alive = true;
    actor.HealthPct = 100.0f;
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
    board.CurrentScope = { "personal-escape", 7, 0, 4,
        "bwd.magmaw.encounter", 669, 1, "magmaw", 91, 4 };
    board.Revision = 10;
    board.ObservedAtMs = 1000;
    board.NativeBossState = "in_progress";
    board.NativeWipeState = "engaged";
    board.EncounterIdentityAuthoritative = true;
    board.EncounterEpochAuthoritative = true;
    board.EncounterArenaObservationComplete = true;
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Route.NavigationHints = { { 0.0f, -60.0f, 210.0f } };
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
    board.Players = {
        Player(30006, "fire_mage", { 24.0f, -30.0f, 210.0f }),
        Player(30009, "marksmanship_hunter", { -24.0f, -30.0f, 210.0f }),
        Player(30008, "affliction_warlock", { 0.0f, -20.0f, 210.0f }),
        Player(30010, "elemental_shaman", { 2.0f, -20.0f, 210.0f }) };
    ActorSnapshot boss = Unit(41570, 1, { 0.0f, 0.0f, 210.0f });
    boss.InCombat = true;
    boss.VictimGuid = PlayerGuid(30006);
    ActorSnapshot parasite = Unit(41806, 101,
        { 0.0f, -12.0f, 210.0f });
    parasite.VictimGuid = PlayerGuid(30008);
    board.Hostiles = { boss, parasite };
    return board;
}

static BotNativeAction::Candidate const* Escape(
    AdaptiveMagmawPlan const& plan)
{
    for (BotNativeAction::Candidate const& candidate :
        plan.Movement.Proposals())
        if (candidate.Id.Mechanic == "parasite_contact_evade"
            && candidate.Id.Actor == PlayerGuid(30008))
            return &candidate;
    return nullptr;
}

static BotNativeAction::Candidate const* EscapeFor(
    AdaptiveMagmawPlan const& plan, ObjectGuid actor)
{
    for (BotNativeAction::Candidate const& candidate :
        plan.Movement.Proposals())
        if (candidate.Id.Mechanic == "parasite_contact_evade"
            && candidate.Id.Actor == actor)
            return &candidate;
    return nullptr;
}

static void SubmitThroughProductionAdapter(
    BotNativeAction::Candidate const& candidate, uint64 now,
    MagmawPersonalParasiteEscapeTask& task)
{
    MagmawMovementIntentCollection movements;
    movements.Propose(MagmawMovementProposalOrigin::Hazard, candidate);
    MagmawMovementKernelAdapterContext context;
    context.ObservedAtMs = now;
    context.Execute = [](BotNativeAction::Intent const&,
        MagmawMovementNativeLease,
        BotWorldMovement::ExecutionObservation*)
    {
        return BotActionArbitration::Outcome::Submitted(
            "native_move_submitted");
    };
    context.ObserveNativeOutcome = [&task](
        MagmawMovementNativeOutcome const& outcome)
    {
        ObserveMagmawPersonalParasiteEscapeNativeOutcome(task, outcome);
    };
    BotActionArbitration::Kernel kernel;
    kernel.Begin(now);
    assert(SubmitMagmawMovementKernelCandidates(kernel, movements,
        std::move(context)) == 1);
    kernel.Resolve();
}

static void RejectThroughProductionAdapter(
    BotNativeAction::Candidate const& candidate, uint64 now,
    MagmawPersonalParasiteEscapeTask& task, char const* reason)
{
    MagmawMovementIntentCollection movements;
    movements.Propose(MagmawMovementProposalOrigin::Hazard, candidate);
    MagmawMovementKernelAdapterContext context;
    context.ObservedAtMs = now;
    context.Execute = [reason](BotNativeAction::Intent const&,
        MagmawMovementNativeLease,
        BotWorldMovement::ExecutionObservation*)
    {
        return BotActionArbitration::Outcome::Retryable(reason);
    };
    context.ObserveNativeOutcome = [&task](
        MagmawMovementNativeOutcome const& outcome)
    {
        ObserveMagmawPersonalParasiteEscapeNativeOutcome(task, outcome);
    };
    BotActionArbitration::Kernel kernel;
    kernel.Begin(now);
    assert(SubmitMagmawMovementKernelCandidates(kernel, movements,
        std::move(context)) == 1);
    kernel.Resolve();
}

int main()
{
    Blackboard board = Board();
    auto cache = MagmawFactsCache::ForSnapshot(nullptr, board);
    assert(!cache->Facts().Parasites.Generation.Authoritative());

    // A visible first contact creates an actor-local task even when the facts
    // projection is partial or stale. The task waits without producing a
    // candidate until the same revision becomes authoritative.
    MagmawFacts partial = cache->Facts();
    partial.ProjectionAuthoritative = false;
    MagmawPersonalParasiteEscapeTask partialTask;
    assert(!partialTask.Tick(board, partial, board.Players[2],
        &board.Hostiles[1], 16.0f, 4.0f, false));
    assert(partialTask.Started);
    assert(partialTask.State == TaskState::Suspended);
    uint64 const pendingWave = partialTask.WaveGeneration;
    assert(pendingWave != 0);
    MagmawFacts stale = cache->Facts();
    --stale.ObservationRevision;
    assert(!partialTask.Tick(board, stale, board.Players[2],
        &board.Hostiles[1], 16.0f, 4.0f, false));
    assert(partialTask.Started);
    assert(partialTask.State == TaskState::Suspended);
    assert(partialTask.WaveGeneration == pendingWave);
    auto resumedFromStaleFacts = partialTask.Tick(board, cache->Facts(),
        board.Players[2], &board.Hostiles[1], 16.0f, 4.0f, false);
    assert(resumedFromStaleFacts);
    assert(partialTask.State == TaskState::Running);
    assert(partialTask.WaveGeneration == pendingWave);

    // Reproduce the live 30010 edge through the production strategy and
    // kernel adapter. The cohort wave and actor child survive one stale fact
    // tick, then produce one stable actor candidate before Infection.
    board.Hostiles[1].VictimGuid = PlayerGuid(30010);
    MagmawFacts staleContact = cache->Facts();
    --staleContact.ObservationRevision;
    MagmawParasiteWaveTask sharedWave;
    MagmawPersonalParasiteEscapeTask actor30010Task;
    AdaptiveMagmawStrategy contactStrategy;
    MagmawLaneTransitionState contactLane;
    MagmawParasiteHazardState contactLegacy;
    AdaptiveMagmawPlan awaiting = contactStrategy.Propose(board,
        PlayerGuid(30010), "dps", nullptr, false, false, &contactLane,
        &contactLegacy, nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder,
        &staleContact, &actor30010Task, &sharedWave);
    assert(!EscapeFor(awaiting, PlayerGuid(30010)));
    assert(sharedWave.Active && sharedWave.AwaitingAuthoritativeFacts);
    assert(actor30010Task.Started);
    assert(actor30010Task.State == TaskState::Suspended);
    assert(actor30010Task.Diagnostics.Lifecycle ==
        MagmawPersonalParasiteEscapeLifecycle::AwaitingAuthoritativeFacts);
    uint64 const actor30010TaskGeneration = actor30010Task.TaskGeneration;
    uint64 const actor30010WaveGeneration = actor30010Task.WaveGeneration;

    AdaptiveMagmawPlan authoritative = contactStrategy.Propose(board,
        PlayerGuid(30010), "dps", nullptr, false, false, &contactLane,
        &contactLegacy, nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder,
        &cache->Facts(), &actor30010Task, &sharedWave);
    BotNativeAction::Candidate const* actor30010Candidate = EscapeFor(
        authoritative, PlayerGuid(30010));
    assert(actor30010Candidate);
    assert(actor30010Task.TaskGeneration == actor30010TaskGeneration);
    assert(actor30010Task.WaveGeneration == actor30010WaveGeneration);
    assert(actor30010Task.Diagnostics.Lifecycle ==
        MagmawPersonalParasiteEscapeLifecycle::CandidateBuilt);
    std::string const actor30010CandidateKey = actor30010Candidate->Id.Key();
    assert(actor30010Task.CandidateGeneration
        == actor30010Candidate->Id.EventGeneration);
    assert(BuildMagmawPersonalParasiteEscapeDiagnosticsJson(actor30010Task,
        &sharedWave).find(actor30010CandidateKey) != std::string::npos);

    // A later partial snapshot suspends the already-built child without
    // changing its actor, wave, task, candidate, destination, or deadline.
    uint64 const actor30010CandidateGeneration =
        actor30010Task.CandidateGeneration;
    uint64 const actor30010CandidateExpiresAtMs =
        actor30010Candidate->ExpiresAtMs;
    assert(actor30010Task.CandidateExpiresAtMs
        == actor30010CandidateExpiresAtMs);
    assert(BuildMagmawPersonalParasiteEscapeDiagnosticsJson(actor30010Task,
        &sharedWave).find("\"candidate_expires_at_ms\":"
            + std::to_string(actor30010CandidateExpiresAtMs))
        != std::string::npos);
    uint64 const actor30010StartedAtMs = actor30010Task.StartedAtMs;
    uint64 const actor30010LastProgressAtMs =
        actor30010Task.LastProgressAtMs;
    Vector3 const actor30010InitialDestination =
        actor30010Task.Destination;
    ++board.Revision;
    board.ObservedAtMs += 100;
    AdaptiveMagmawPlan authorityLost = contactStrategy.Propose(board,
        PlayerGuid(30010), "dps", nullptr, false, false, &contactLane,
        &contactLegacy, nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder,
        &cache->Facts(), &actor30010Task, &sharedWave);
    assert(!EscapeFor(authorityLost, PlayerGuid(30010)));
    assert(actor30010Task.State == TaskState::Suspended);
    assert(actor30010Task.TaskGeneration == actor30010TaskGeneration);
    assert(actor30010Task.CandidateGeneration
        == actor30010CandidateGeneration);
    assert(actor30010Task.CandidateExpiresAtMs
        == actor30010CandidateExpiresAtMs);
    assert(actor30010Task.StartedAtMs == actor30010StartedAtMs);
    assert(actor30010Task.LastProgressAtMs
        == actor30010LastProgressAtMs);
    assert(MagmawPersonalParasiteEscapeTask::SamePoint(
        actor30010Task.Destination, actor30010InitialDestination));

    cache = MagmawFactsCache::ForSnapshot(cache, board);
    AdaptiveMagmawPlan authorityRestored = contactStrategy.Propose(board,
        PlayerGuid(30010), "dps", nullptr, false, false, &contactLane,
        &contactLegacy, nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder,
        &cache->Facts(), &actor30010Task, &sharedWave);
    actor30010Candidate = EscapeFor(authorityRestored, PlayerGuid(30010));
    assert(actor30010Candidate);
    assert(actor30010Candidate->Id.Key() == actor30010CandidateKey);
    assert(actor30010Candidate->ExpiresAtMs
        == actor30010CandidateExpiresAtMs);
    assert(actor30010Task.CandidateExpiresAtMs
        == actor30010CandidateExpiresAtMs);

    SubmitThroughProductionAdapter(*actor30010Candidate,
        board.ObservedAtMs, actor30010Task);
    assert(actor30010Task.Diagnostics.Lifecycle ==
        MagmawPersonalParasiteEscapeLifecycle::Submitted);
    assert(actor30010Task.Diagnostics.CandidateKey == actor30010CandidateKey);
    assert(actor30010Task.Diagnostics.SubmittedAtMs == board.ObservedAtMs);

    Vector3 const actor30010Destination = actor30010Task.Destination;
    board.Players[3].Position.X +=
        (actor30010Destination.X - board.Players[3].Position.X) * 0.25f;
    board.Players[3].Position.Y +=
        (actor30010Destination.Y - board.Players[3].Position.Y) * 0.25f;
    ++board.Revision;
    board.ObservedAtMs += 100;
    cache = MagmawFactsCache::ForSnapshot(cache, board);
    auto progressing = actor30010Task.Tick(board, cache->Facts(),
        board.Players[3], &board.Hostiles[1], 16.0f, 4.0f, false,
        &sharedWave);
    assert(progressing);
    assert(progressing->Id.Key() == actor30010CandidateKey);
    assert(actor30010Task.Diagnostics.Lifecycle ==
        MagmawPersonalParasiteEscapeLifecycle::NativeProgress);

    board.Players[3].Position = actor30010Destination;
    ++board.Revision;
    board.ObservedAtMs += 100;
    cache = MagmawFactsCache::ForSnapshot(cache, board);
    assert(!actor30010Task.Tick(board, cache->Facts(), board.Players[3],
        &board.Hostiles[1], 16.0f, 4.0f, false, &sharedWave));
    assert(actor30010Task.Diagnostics.Lifecycle ==
        MagmawPersonalParasiteEscapeLifecycle::SafeClearance);
    std::string lifecycleJson =
        BuildMagmawPersonalParasiteEscapeDiagnosticsJson(actor30010Task,
            &sharedWave);
    for (char const* field : { "task_created", "awaiting_facts",
        "candidate_built", "submitted", "native_progress",
        "safe_clearance", "candidate_key", "actor_guid",
        "wave_generation" })
        assert(lifecycleJson.find(field) != std::string::npos);

    // The shared provisional wave can outlive more than one actor-local
    // contact episode. Continuous personal threat after terminal clearance
    // is still the same episode and must not rearm.
    uint64 const clearedTaskGeneration = actor30010Task.TaskGeneration;
    uint64 const clearedCandidateGeneration =
        actor30010Task.CandidateGeneration;
    uint64 const provisionalWaveGeneration = sharedWave.Generation;
    assert(sharedWave.Active && !sharedWave.GenerationAuthoritative);
    ++board.Revision;
    board.ObservedAtMs += 100;
    cache = MagmawFactsCache::ForSnapshot(cache, board);
    AdaptiveMagmawPlan continuousContact = contactStrategy.Propose(board,
        PlayerGuid(30010), "dps", nullptr, false, false, &contactLane,
        &contactLegacy, nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder,
        &cache->Facts(), &actor30010Task, &sharedWave);
    assert(!EscapeFor(continuousContact, PlayerGuid(30010)));
    assert(actor30010Task.TaskGeneration == clearedTaskGeneration);

    // An authoritative actor-local absence is the falling edge. It does not
    // close or replace the still-provisional cohort wave.
    board.Hostiles[1].VictimGuid = PlayerGuid(30008);
    ++board.Revision;
    board.ObservedAtMs += 100;
    cache = MagmawFactsCache::ForSnapshot(cache, board);
    AdaptiveMagmawPlan contactAbsent = contactStrategy.Propose(board,
        PlayerGuid(30010), "dps", nullptr, false, false, &contactLane,
        &contactLegacy, nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder,
        &cache->Facts(), &actor30010Task, &sharedWave);
    assert(!EscapeFor(contactAbsent, PlayerGuid(30010)));
    assert(actor30010Task.TaskGeneration == clearedTaskGeneration);
    assert(sharedWave.Active
        && sharedWave.Generation == provisionalWaveGeneration
        && !sharedWave.GenerationAuthoritative);

    // A later personal-contact rising edge rearms exactly once. Stable
    // presence, including hazard GUID churn, retains the task and its sticky
    // destination instead of creating per-tick or per-GUID generations.
    board.Players[3].Position = { 2.0f, -20.0f, 210.0f };
    board.Hostiles[1].VictimGuid = PlayerGuid(30010);
    board.Hostiles[1].Guid = ObjectGuid(HighGuid::Unit, uint32(41806),
        uint32(102));
    ++board.Revision;
    board.ObservedAtMs += 100;
    cache = MagmawFactsCache::ForSnapshot(cache, board);
    AdaptiveMagmawPlan nextContact = contactStrategy.Propose(board,
        PlayerGuid(30010), "dps", nullptr, false, false, &contactLane,
        &contactLegacy, nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder,
        &cache->Facts(), &actor30010Task, &sharedWave);
    BotNativeAction::Candidate const* nextContactCandidate = EscapeFor(
        nextContact, PlayerGuid(30010));
    assert(nextContactCandidate);
    assert(actor30010Task.TaskGeneration == clearedTaskGeneration + 1);
    assert(actor30010Task.CandidateGeneration
        != clearedCandidateGeneration);
    assert(actor30010Task.WaveGeneration == provisionalWaveGeneration);
    uint64 const nextContactTaskGeneration = actor30010Task.TaskGeneration;
    uint64 const nextContactCandidateGeneration =
        actor30010Task.CandidateGeneration;
    uint64 const nextContactExpiresAtMs = nextContactCandidate->ExpiresAtMs;
    std::string const nextContactKey = nextContactCandidate->Id.Key();
    Vector3 const nextContactDestination = actor30010Task.Destination;

    board.Hostiles[1].Guid = ObjectGuid(HighGuid::Unit, uint32(41806),
        uint32(103));
    ++board.Revision;
    board.ObservedAtMs += 100;
    cache = MagmawFactsCache::ForSnapshot(cache, board);
    AdaptiveMagmawPlan stableNextContact = contactStrategy.Propose(board,
        PlayerGuid(30010), "dps", nullptr, false, false, &contactLane,
        &contactLegacy, nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder,
        &cache->Facts(), &actor30010Task, &sharedWave);
    BotNativeAction::Candidate const* stableNextContactCandidate = EscapeFor(
        stableNextContact, PlayerGuid(30010));
    assert(stableNextContactCandidate);
    assert(actor30010Task.TaskGeneration == nextContactTaskGeneration);
    assert(actor30010Task.CandidateGeneration
        == nextContactCandidateGeneration);
    assert(stableNextContactCandidate->Id.Key() == nextContactKey);
    assert(stableNextContactCandidate->ExpiresAtMs
        == nextContactExpiresAtMs);
    assert(MagmawPersonalParasiteEscapeTask::SamePoint(
        actor30010Task.Destination, nextContactDestination));

    // Infection while authority is still missing is an explicit terminal
    // child outcome. It cannot masquerade as another dropped intent.
    MagmawPersonalParasiteEscapeTask infectedTask;
    board.Players[3].Position = { 2.0f, -20.0f, 210.0f };
    board.Players[3].Auras.clear();
    ++board.Revision;
    board.ObservedAtMs += 100;
    cache = MagmawFactsCache::ForSnapshot(cache, board);
    MagmawFacts infectedStale = cache->Facts();
    --infectedStale.ObservationRevision;
    assert(!infectedTask.Tick(board, infectedStale, board.Players[3],
        &board.Hostiles[1], 16.0f, 4.0f, false, &sharedWave));
    board.Players[3].Auras.push_back({ 78941, {}, 1, 0 });
    assert(!infectedTask.Tick(board, infectedStale, board.Players[3],
        &board.Hostiles[1], 16.0f, 4.0f, false, &sharedWave));
    assert(infectedTask.Diagnostics.Lifecycle ==
        MagmawPersonalParasiteEscapeLifecycle::Infected);
    assert(infectedTask.Failure ==
        MagmawPersonalParasiteEscapeFailure::InfectedBeforeClearance);
    board.Players[3].Auras.clear();
    board.Hostiles[1].VictimGuid = PlayerGuid(30008);

    // Exact overlap uses the actor's facing, matching the legacy move-away
    // formula instead of inventing a fixed axis.
    Blackboard overlapBoard = board;
    overlapBoard.Players[2].Facing = 1.25f;
    overlapBoard.Hostiles[1].Position = overlapBoard.Players[2].Position;
    ++overlapBoard.Revision;
    auto overlapFacts = MagmawFactsCache::ForSnapshot(nullptr, overlapBoard);
    MagmawPersonalParasiteEscapeTask overlapTask;
    auto overlapIntent = overlapTask.Tick(overlapBoard,
        overlapFacts->Facts(), overlapBoard.Players[2],
        &overlapBoard.Hostiles[1], 16.0f, 4.0f, true);
    Vector3 const overlapExpected = MagmawMoveAwayDestination(
        overlapBoard.Players[2].Position, overlapBoard.Players[2].Facing,
        overlapBoard.Hostiles[1].Position, 16.0f);
    assert(overlapIntent);
    assert(MagmawPersonalParasiteEscapeTask::SamePoint(
        overlapTask.Destination, overlapExpected));

    AdaptiveMagmawStrategy strategy;
    MagmawLaneTransitionState lane;
    MagmawParasiteHazardState legacy;
    MagmawPersonalParasiteEscapeTask task;
    AdaptiveMagmawPlan first = strategy.Propose(board, PlayerGuid(30008),
        "dps", nullptr, false, false, &lane, &legacy, nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder,
        &cache->Facts(), &task);
    BotNativeAction::Candidate const* primary = Escape(first);
    assert(primary && task.OwnsMovement());
    uint64 const wave = task.WaveGeneration;
    uint64 const primaryGeneration = task.CandidateGeneration;
    uint64 const primaryExpiresAtMs = primary->ExpiresAtMs;
    Vector3 const primaryDestination = task.Destination;
    assert(HasRetainedMagmawHazardOwnership(first.Movement, task,
        PlayerGuid(30008)));

    RejectThroughProductionAdapter(*primary, board.ObservedAtMs, task,
        "route_destination_endpoint_mismatch");
    assert(task.AlternatePending && !task.OwnsMovement());

    // Sub-yard actor/hazard drift recomputes at most one straight move-away
    // destination. It never changes the semantic wave.
    board.Players[2].Position.X += 0.20f;
    board.Hostiles[1].Position.X += 0.10f;
    board.Hostiles[1].Guid = ObjectGuid(HighGuid::Unit, uint32(41806),
        uint32(202));
    ++board.Revision;
    board.ObservedAtMs += 100;
    cache = MagmawFactsCache::ForSnapshot(cache, board);
    AdaptiveMagmawPlan alternate = strategy.Propose(board,
        PlayerGuid(30008), "dps", nullptr, false, false, &lane, &legacy,
        nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder,
        &cache->Facts(), &task);
    BotNativeAction::Candidate const* alternateCandidate = Escape(alternate);
    assert(alternateCandidate && task.AlternateUsed);
    assert(task.WaveGeneration == wave);
    assert(task.CandidateGeneration != primaryGeneration);
    assert(alternateCandidate->ExpiresAtMs == task.CandidateExpiresAtMs);
    assert(alternateCandidate->ExpiresAtMs != primaryExpiresAtMs);
    assert(task.Diagnostics.CandidateKey.empty());
    std::string const alternateKey = alternateCandidate->Id.Key();
    uint64 const alternateGeneration = task.CandidateGeneration;
    uint64 const alternateExpiresAtMs = alternateCandidate->ExpiresAtMs;
    std::string const alternateJson =
        BuildMagmawPersonalParasiteEscapeDiagnosticsJson(task);
    assert(alternateJson.find("\"candidate_key\":\"" + alternateKey
        + "\"") != std::string::npos);
    assert(alternateJson.find("\"candidate_generation\":"
        + std::to_string(task.CandidateGeneration)) != std::string::npos);
    assert(!MagmawPersonalParasiteEscapeTask::SamePoint(
        primaryDestination, task.Destination));

    // Re-emitting the same alternate on a later authoritative tick retains
    // both its candidate generation and its fixed expiry.
    ++board.Revision;
    board.ObservedAtMs += 100;
    cache = MagmawFactsCache::ForSnapshot(cache, board);
    AdaptiveMagmawPlan retainedAlternate = strategy.Propose(board,
        PlayerGuid(30008), "dps", nullptr, false, false, &lane, &legacy,
        nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder,
        &cache->Facts(), &task);
    BotNativeAction::Candidate const* retainedAlternateCandidate =
        Escape(retainedAlternate);
    assert(retainedAlternateCandidate);
    assert(task.CandidateGeneration == alternateGeneration);
    assert(retainedAlternateCandidate->Id.Key() == alternateKey);
    assert(retainedAlternateCandidate->ExpiresAtMs == alternateExpiresAtMs);
    assert(task.CandidateExpiresAtMs == alternateExpiresAtMs);

    RejectThroughProductionAdapter(*retainedAlternateCandidate,
        board.ObservedAtMs, task, "route_destination_unreachable");
    assert(task.State == TaskState::Failed);
    assert(task.Failure == MagmawPersonalParasiteEscapeFailure::
        AlternateNativeRouteRejected);

    // More drift and another hazard GUID in the same continuous wave cannot
    // rearm a terminal task; combat movement ownership is released.
    board.Players[2].Position.X += 0.20f;
    board.Hostiles[1].Position.X += 0.20f;
    board.Hostiles[1].Guid = ObjectGuid(HighGuid::Unit, uint32(41806),
        uint32(303));
    ++board.Revision;
    board.ObservedAtMs += 100;
    cache = MagmawFactsCache::ForSnapshot(cache, board);
    AdaptiveMagmawPlan sameWave = strategy.Propose(board,
        PlayerGuid(30008), "dps", nullptr, false, false, &lane, &legacy,
        nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder,
        &cache->Facts(), &task);
    assert(!Escape(sameWave));
    assert(!HasRetainedMagmawHazardOwnership(sameWave.Movement, task,
        PlayerGuid(30008)));

    // An actor-local peer owns a distinct task in the same wave.
    board.Hostiles[1].VictimGuid = PlayerGuid(30010);
    MagmawPersonalParasiteEscapeTask peer;
    ActorSnapshot const* peerActor = board.FindActor(PlayerGuid(30010));
    assert(peerActor);
    auto peerIntent = peer.Tick(board, cache->Facts(), *peerActor,
        &board.Hostiles[1], 16.0f, 4.0f, true);
    assert(peerIntent && peer.ActorGuid != task.ActorGuid);

    // Death and resurrection in the same wave abort the old actor-life task.
    // The resurrected actor receives a fresh candidate rather than resuming
    // the stale destination or generation.
    MagmawPersonalParasiteEscapeTask lifeTask;
    board.Hostiles[1].VictimGuid = PlayerGuid(30008);
    auto lifeFirst = lifeTask.Tick(board, cache->Facts(), board.Players[2],
        &board.Hostiles[1], 16.0f, 4.0f, false);
    assert(lifeFirst);
    uint64 const oldLifeCandidate = lifeTask.CandidateGeneration;
    Vector3 const oldLifeDestination = lifeTask.Destination;
    board.Players[2].Alive = false;
    ++board.Revision;
    board.ObservedAtMs += 100;
    cache = MagmawFactsCache::ForSnapshot(cache, board);
    strategy.Propose(board, PlayerGuid(30008), "dps", nullptr, false,
        false, &lane, &legacy, nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder,
        &cache->Facts(), &lifeTask);
    assert(!lifeTask.Started && lifeTask.State == TaskState::Aborted);
    assert(lifeTask.ActorLifeGeneration == 1);
    board.Players[2].Alive = true;
    board.Players[2].Position.X += 0.25f;
    ++board.Revision;
    board.ObservedAtMs += 100;
    cache = MagmawFactsCache::ForSnapshot(cache, board);
    AdaptiveMagmawPlan resurrected = strategy.Propose(board,
        PlayerGuid(30008), "dps", nullptr, false, false, &lane, &legacy,
        nullptr, std::nullopt,
        AdaptiveMagmawStrategy::DefaultMovementProducerOrder,
        &cache->Facts(), &lifeTask);
    BotNativeAction::Candidate const* resurrectedEscape = Escape(resurrected);
    assert(resurrectedEscape && lifeTask.ActorLifeGeneration == 2);
    assert(lifeTask.CandidateGeneration != oldLifeCandidate);
    assert(!MagmawPersonalParasiteEscapeTask::SamePoint(
        lifeTask.Destination, oldLifeDestination));

    // Authoritative absence closes the tombstone; a later edge rearms once.
    board.Hostiles.resize(1);
    ++board.Revision;
    board.ObservedAtMs += 100;
    cache = MagmawFactsCache::ForSnapshot(cache, board);
    task.Tick(board, cache->Facts(), board.Players[2], nullptr,
        16.0f, 4.0f, false);
    assert(task.WaveEnded);
    ActorSnapshot nextParasite = Unit(41806, 404,
        { 0.0f, -12.0f, 210.0f });
    nextParasite.VictimGuid = PlayerGuid(30008);
    board.Hostiles.push_back(nextParasite);
    ++board.Revision;
    board.ObservedAtMs += 100;
    cache = MagmawFactsCache::ForSnapshot(cache, board);
    assert(cache->Facts().Parasites.Generation.Authoritative());
    assert(cache->Facts().Parasites.Generation.Value == 1);
    auto nextWave = task.Tick(board, cache->Facts(), board.Players[2],
        &board.Hostiles[1], 16.0f, 4.0f, false);
    assert(nextWave && task.State == TaskState::Running);
    assert(task.WaveGeneration != wave);

    // Submission is not progress. Ownership persists until measured arrival.
    Vector3 const destination = task.Destination;
    uint64 const retainedGeneration = task.CandidateGeneration;
    ++board.Revision;
    board.ObservedAtMs += 100;
    cache = MagmawFactsCache::ForSnapshot(cache, board);
    auto retained = task.Tick(board, cache->Facts(), board.Players[2],
        &board.Hostiles[1], 16.0f, 4.0f, false);
    assert(retained && task.CandidateGeneration == retainedGeneration);
    board.Players[2].Position = destination;
    ++board.Revision;
    board.ObservedAtMs += 100;
    cache = MagmawFactsCache::ForSnapshot(cache, board);
    assert(!task.Tick(board, cache->Facts(), board.Players[2],
        &board.Hostiles[1], 16.0f, 4.0f, false));
    assert(task.State == TaskState::Succeeded && !task.OwnsMovement());

    // Unknown first-active generation latches locally. A later authoritative
    // generation during continuous presence cannot silently rearm it.
    MagmawFacts unknown = cache->Facts();
    unknown.Parasites.Generation = {};
    board.Players[2].Position = { 0.0f, -20.0f, 210.0f };
    MagmawPersonalParasiteEscapeTask unknownTask;
    auto unknownIntent = unknownTask.Tick(board, unknown, board.Players[2],
        &board.Hostiles[1], 16.0f, 4.0f, false);
    assert(unknownIntent && !unknownTask.WaveGenerationAuthoritative);
    uint64 const latchedUnknownWave = unknownTask.WaveGeneration;
    ++board.Revision;
    board.ObservedAtMs += 100;
    cache = MagmawFactsCache::ForSnapshot(cache, board);
    auto authoritativeSamePresence = unknownTask.Tick(board, cache->Facts(),
        board.Players[2], &board.Hostiles[1], 16.0f, 4.0f, false);
    assert(authoritativeSamePresence);
    assert(unknownTask.WaveGeneration == latchedUnknownWave);

    // Measured non-progress is terminal and releases movement ownership.
    board.ObservedAtMs += 5001;
    assert(!unknownTask.Tick(board, cache->Facts(), board.Players[2],
        &board.Hostiles[1], 16.0f, 4.0f, false));
    assert(unknownTask.State == TaskState::Failed);
    assert(unknownTask.Failure == MagmawPersonalParasiteEscapeFailure::
        NoSemanticProgress);
}
''', encoding="utf-8")
    subprocess.run([
        "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *INCLUDES,
        str(source),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
            "Encounters/Magmaw/BotMagmawFacts.cpp"),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
            "Encounters/Magmaw/BotMagmawMovementKernelAdapter.cpp"),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
            "Encounters/Magmaw/"
            "BotMagmawPersonalParasiteEscapeDiagnostics.cpp"),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
            "Encounters/Magmaw/BotMagmawTransferLaneKernelBridge.cpp"),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
            "Encounters/Magmaw/BotMagmawTransferLaneIntent.cpp"),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
            "Encounters/Magmaw/BotMagmawTransferLaneAuthority.cpp"),
        str(ROOT / "src/server/game/Bots/"
            "BotWorldPopulationMgrMovementExecution.cpp"),
        str(ROOT / "src/server/game/Bots/"
            "BotWorldPopulationMgrMovementPlannerDiagnostics.cpp"),
        str(ROOT / "src/server/game/Bots/"
            "BotWorldPopulationMgrMovementPlannerDiagnosticsJson.cpp"),
        str(ROOT / "src/server/game/Bots/"
            "BotWorldPopulationMgrMovementReceiptRetention.cpp"),
        str(ROOT / "src/server/game/Bots/"
            "BotWorldPopulationMgrMovementProgressDiagnostics.cpp"),
        "-o", str(binary),
    ], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_personal_escape_wiring_has_no_vertical_or_path_changes() -> None:
    encounter = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw"
    task = (encounter / "BotMagmawPersonalParasiteEscapeTask.inl").read_text()
    preparation = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrUpdateBotKernelPreparation.cpp").read_text()
    candidates = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp").read_text()

    assert "MagmawPersonalParasiteEscape" in preparation
    assert "MagmawPersonalParasiteEscape" in candidates
    assert "PathGenerator" not in task
    assert "MotionMaster" not in task
    assert "NativeFloorTolerance" not in task
    assert "Destination.X +=" not in task
    assert "Destination.Z +=" not in task
    assert "dx = 1.0f" not in task
    geometry = (encounter / "BotMagmawMoveAwayGeometry.h").read_text()
    assert "actor.Z" in geometry
    assert "std::cos(actorFacing)" in geometry
    assert "std::sin(actorFacing)" in geometry
    legacy = (encounter / "BotAdaptiveMagmawParasitePolicy.h").read_text()
    assert "MagmawMoveAwayDestination(bot.Position" in legacy
