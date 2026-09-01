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
    assert(!MagmawPersonalParasiteEscapeTask::SamePoint(
        primaryDestination, task.Destination));

    RejectThroughProductionAdapter(*alternateCandidate, board.ObservedAtMs,
        task, "route_destination_unreachable");
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
    assert "actor.Z" in task
    assert "Destination.X +=" not in task
    assert "Destination.Z +=" not in task
