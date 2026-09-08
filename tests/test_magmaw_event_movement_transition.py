from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_magmaw_lethal_movement_survives_observation_and_lease_churn(
    tmp_path: Path,
) -> None:
    source = tmp_path / "magmaw_lethal_movement.cpp"
    binary = tmp_path / "magmaw_lethal_movement"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include <cassert>

using namespace BotEncounter;

static ObjectGuid PlayerGuid(uint32 value)
{
    return ObjectGuid(HighGuid::Player, value);
}

static ObjectGuid UnitGuid(uint32 entry, uint32 value)
{
    return ObjectGuid(HighGuid::Unit, entry, value);
}

static BotMovementArbitration::Request RequestFor(Blackboard const& board,
    BotNativeAction::Candidate const& candidate, uint64 expiresAt)
{
    auto const* move = std::get_if<BotNativeAction::Move>(&candidate.Action);
    assert(move);
    return { BotMovementArbitration::Owner::Hazard,
        BotMovementArbitration::Priority::Hazard, expiresAt,
        { board.CurrentScope.AttemptId, board.CurrentScope.WipeGeneration,
            board.CurrentScope.RouteGeneration, board.CurrentScope.MapId,
            board.CurrentScope.InstanceId },
        move->X, move->Y, move->Z, 0 };
}

int main()
{
    Blackboard board;
    board.CurrentScope = Scope{ "canary121", 11, 0, 4,
        "bwd.magmaw.encounter", 669, 2, "magmaw" };
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Route.NavigationHints = { { -329.0f, -20.0f, 211.815f } };
    board.NativeBossState = "in_progress";
    board.ObservedAtMs = 1000;
    ObjectGuid const actor = PlayerGuid(30009);

    MagmawEventMovementTransitionState state;
    ActorSnapshot bot;
    bot.Guid = actor;
    bot.Alive = true;
    bot.Role = "dps";
    bot.Position = { -330.936f, -27.3621f, 211.313f };
    ActorSnapshot boss;
    boss.Guid = UnitGuid(41570, 700);
    boss.Entry = AdaptiveMagmawStrategy::BossEntry;
    boss.Alive = true;
    boss.Attackable = true;
    boss.Selectable = true;
    boss.InCombat = true;
    boss.Position = { -324.0f, -20.0f, 211.313f };
    ActorSnapshot crash;
    crash.Guid = UnitGuid(47196, 800);
    crash.Entry = AdaptiveMagmawStrategy::RoomStalkerEntry;
    crash.Alive = true;
    crash.Position = { -331.0f, -20.0f, 211.313f };
    crash.Auras.push_back({ 87949, ObjectGuid{}, 1, 0 });
    board.Players = { bot };
    board.Hostiles = { boss, crash };
    AdaptiveMagmawStrategy strategy;
    auto firstPlan = strategy.Propose(board, actor, "dps", nullptr, false,
        false, nullptr, nullptr, &state);
    auto first = firstPlan.Movement;
    assert(first && first->ActionPriority
        == BotActionArbitration::Priority::Survival);
    assert(firstPlan.DamageTarget == boss.Guid);
    auto const* firstPoint = std::get_if<BotNativeAction::Move>(&first->Action);
    assert(firstPoint && state.ActiveLethal());
    uint64 const firstIntent = first->Id.EventGeneration;

    BotMovementArbitration::Lease lease;
    auto firstRequest = RequestFor(board, *first, 2500);
    assert(BotMovementArbitration::Evaluate(lease, firstRequest, 1000)
        == BotMovementArbitration::Decision::Acquire);
    BotMovementArbitration::Apply(lease, firstRequest);

    // Snapshot geometry may move and the short lease may expire. One lethal
    // event still retains one safe point and one candidate identity.
    board.Revision += 1;
    board.ObservedAtMs = 3000;
    bot.Position = { -339.0f, -26.0f, 211.17f };
    crash.Position = { -335.0f, -24.0f, 211.17f };
    board.Players = { bot };
    board.Hostiles = { boss, crash };
    auto retainedPlan = strategy.Propose(board, actor, "dps", nullptr,
        false, false, nullptr, nullptr, &state);
    auto retained = retainedPlan.Movement;
    assert(retained && retained->Id.EventGeneration == firstIntent);
    auto const* retainedPoint = std::get_if<BotNativeAction::Move>(
        &retained->Action);
    assert(retainedPoint && retainedPoint->X == firstPoint->X
        && retainedPoint->Y == firstPoint->Y
        && retainedPoint->Z == firstPoint->Z);
    auto expiredRequest = RequestFor(board, *retained, 4500);
    assert(BotMovementArbitration::Evaluate(lease, expiredRequest, 3000)
        == BotMovementArbitration::Decision::Acquire);

    // The exact survival movement owns only Movement, so stationary trained
    // damage remains eligible in the same priority-queue tick.
    BotActionArbitration::Kernel kernel;
    kernel.Begin(board.ObservedAtMs);
    bool moved = false;
    bool damaged = false;
    kernel.Submit(BotActionArbitration::Candidate{
        "stable_lethal_movement", "adaptive_magmaw",
        retained->ActionPriority, retained->Utility, 0.0f, 0.0f,
        retained->Resources(), retained->ExpiresAtMs, 100, 3000, 5, true, "",
        [&] { moved = true; return BotActionArbitration::Outcome::Submitted(
            "lethal_move_submitted"); }});
    kernel.Submit(BotActionArbitration::Candidate{
        "trained_damage", "db_class_spec_profile",
        BotActionArbitration::Priority::TrainedDamage, 1.0f, 0.0f, 0.0f,
        BotActionArbitration::Uses(BotActionArbitration::Resource::Cast,
            BotActionArbitration::Resource::Target),
        retained->ExpiresAtMs, 100, 3000, 5, true, "",
        [&] { damaged = true; return BotActionArbitration::Outcome::Submitted(
            "damage_submitted"); }});
    auto const& resolution = kernel.Resolve();
    assert(moved && damaged && resolution.CommittedCandidates.size() == 2);

    // Matching X/Y on another floor is not arrival.
    state.ObserveArrival({ firstPoint->X, firstPoint->Y,
        firstPoint->Z - 20.0f });
    assert(state.ActiveLethal());
    state.ObserveArrival({ firstPoint->X, firstPoint->Y, firstPoint->Z });
    assert(!state.ActiveLethal());

    // Re-entry into the same persistent hazard source is a new escape, not
    // a permanently retired match on the old source GUID.
    bot.Position = { -330.936f, -27.3621f, 211.313f };
    crash.Position = { -331.0f, -20.0f, 211.313f };
    auto reentered = RetainMagmawRadialLethalMovement(
        board, bot, crash, "massive_crash_evade", 16.0f, state, 450.0f);
    assert(reentered && reentered->Id.EventGeneration != firstIntent);

    Blackboard reset = board;
    reset.CurrentScope.AttemptId += 1;
    reset.CurrentScope.WipeGeneration += 1;
    state.ObserveScope(reset, actor);
    assert(!state.ActiveLethal());
    auto resetMove = RetainMagmawRadialLethalMovement(
        reset, bot, crash, "massive_crash_evade", 16.0f, state, 450.0f);
    assert(resetMove && resetMove->Id.ScopeKey != first->Id.ScopeKey);

    // a5062ba7 actor 30007, trace sequence 626 and receipt 509: the original
    // 16-yard Crash request was retained
    // after native movement reached this shorter same-floor bounded endpoint.
    // The later tick then retried the original request from off navmesh.
    Blackboard captured = board;
    captured.CurrentScope.AttemptId = 12;
    captured.CurrentScope.InstanceId = 8;
    captured.Revision = 626;
    captured.ObservedAtMs = 20000;
    captured.Route.NavigationHints = {
        { -307.531f, -35.4375f, 211.815f } };
    ObjectGuid const capturedActor = PlayerGuid(30007);
    Vector3 const requested{
        -302.921356f, -26.0047035f, 210.521393f };
    Vector3 const boundedEndpoint{
        -308.800049f, -29.3334656f, 209.980377f };
    Vector3 const actorAtLaunch{
        -305.600037f, -34.9334412f, 210.521393f };
    float const requestedDx = requested.X - actorAtLaunch.X;
    float const requestedDy = requested.Y - actorAtLaunch.Y;
    float const requestedDirectionLength = std::hypot(requestedDx, requestedDy);
    ActorSnapshot capturedCrash = crash;
    capturedCrash.Guid = UnitGuid(47196, 801);
    capturedCrash.Position = {
        requested.X - requestedDx / requestedDirectionLength * 16.0f,
        requested.Y - requestedDy / requestedDirectionLength * 16.0f,
        requested.Z };
    ActorSnapshot capturedBot = bot;
    capturedBot.Guid = capturedActor;
    capturedBot.Position = actorAtLaunch;
    ActorSnapshot capturedBoss = boss;
    capturedBoss.Position = { -302.467f, -31.7101f, 210.8483f };
    captured.Players = { capturedBot };
    captured.Hostiles = { capturedBoss, capturedCrash };
    MagmawEventMovementTransitionState capturedState;
    auto capturedFirstPlan = strategy.Propose(captured, capturedActor, "dps",
        nullptr, false, false, nullptr, nullptr, &capturedState);
    assert(capturedFirstPlan.Movement);
    auto const* capturedRequest = std::get_if<BotNativeAction::Move>(
        &capturedFirstPlan.Movement->Action);
    assert(capturedRequest);
    float roomDx = captured.Route.NavigationHints.front().X
        - capturedBoss.Position.X;
    float roomDy = captured.Route.NavigationHints.front().Y
        - capturedBoss.Position.Y;
    float const roomLength = std::hypot(roomDx, roomDy);
    roomDx /= roomLength;
    roomDy /= roomLength;
    Vector3 const expectedRightSupport{
        capturedBoss.Position.X
            + roomDx * AdaptiveMagmawStrategy::SupportStackDistance
            + roomDy * AdaptiveMagmawStrategy::SupportStackDistance,
        capturedBoss.Position.Y
            + roomDy * AdaptiveMagmawStrategy::SupportStackDistance
            - roomDx * AdaptiveMagmawStrategy::SupportStackDistance,
        captured.Route.NavigationHints.front().Z };
    assert(std::hypot(capturedRequest->X - expectedRightSupport.X,
        capturedRequest->Y - expectedRightSupport.Y) < 0.001f);
    assert(capturedRequest->Z == expectedRightSupport.Z);
    assert(std::hypot(capturedRequest->X - capturedBoss.Position.X,
        capturedRequest->Y - capturedBoss.Position.Y) < 12.0f);
    uint64 const capturedIntent =
        capturedFirstPlan.Movement->Id.EventGeneration;

    captured.Revision += 1;
    captured.ObservedAtMs += 1;
    capturedBot.Position = { -306.0f, -35.0f, requested.Z };
    captured.Players = { capturedBot };
    auto unsafePartial = strategy.Propose(captured, capturedActor, "dps",
        nullptr, false, false, nullptr, nullptr, &capturedState);
    assert(unsafePartial.Movement);
    assert(unsafePartial.Movement->Id.EventGeneration == capturedIntent);
    auto const* unsafeRequest = std::get_if<BotNativeAction::Move>(
        &unsafePartial.Movement->Action);
    assert(unsafeRequest && unsafeRequest->X == capturedRequest->X
        && unsafeRequest->Y == capturedRequest->Y
        && unsafeRequest->Z == capturedRequest->Z);

    assert(std::hypot(boundedEndpoint.X - capturedCrash.Position.X,
        boundedEndpoint.Y - capturedCrash.Position.Y) > 12.0f);
    assert(std::fabs(boundedEndpoint.Z - capturedCrash.Position.Z) < 1.5f);
    captured.Revision += 1;
    captured.ObservedAtMs += 1;
    capturedBot.Position = boundedEndpoint;
    captured.Players = { capturedBot };
    auto safeBounded = strategy.Propose(captured, capturedActor, "dps",
        nullptr, false, false, nullptr, nullptr, &capturedState);
    // The recorded point is horizontally safe but below the destination
    // anchor floor; it must not retire the retained movement task.
    assert(capturedState.ActiveLethal());
    assert(safeBounded.Movement);
    assert(safeBounded.Movement->Id.EventGeneration == capturedIntent);
    captured.Revision += 1;
    captured.ObservedAtMs += 1;
    capturedBot.Position.Z = expectedRightSupport.Z;
    captured.Players = { capturedBot };
    auto safeAnchorFloor = strategy.Propose(captured, capturedActor, "dps",
        nullptr, false, false, nullptr, nullptr, &capturedState);
    assert(!capturedState.ActiveLethal());
    assert(!safeAnchorFloor.Movement);

    captured.Revision = 636;
    captured.ObservedAtMs += 10;
    capturedBot.Position = {
        -302.471405f, -31.8600292f, 210.098007f };
    captured.Players = { capturedBot };
    auto laterOffNavmesh = strategy.Propose(captured, capturedActor, "dps",
        nullptr, false, false, nullptr, nullptr, &capturedState);
    assert(laterOffNavmesh.Movement);
    uint64 const reentryIntent =
        laterOffNavmesh.Movement->Id.EventGeneration;
    assert(reentryIntent != capturedIntent);
    auto const* reentryRequest = std::get_if<BotNativeAction::Move>(
        &laterOffNavmesh.Movement->Action);
    assert(reentryRequest);
    assert(reentryRequest->X == capturedRequest->X
        && reentryRequest->Y == capturedRequest->Y
        && reentryRequest->Z == expectedRightSupport.Z);

    captured.Revision += 1;
    capturedBot.Position = { -306.0f, -35.0f, requested.Z };
    captured.Players = { capturedBot };
    auto capturedReentryContinuation = strategy.Propose(captured,
        capturedActor, "dps",
        nullptr, false, false, nullptr, nullptr, &capturedState);
    assert(capturedReentryContinuation.Movement);
    assert(capturedReentryContinuation.Movement->Id.EventGeneration
        == reentryIntent);

    // Pillar uses the same transition helper. It retains one request while
    // the actor remains inside 12 yards, completes on same-floor safe
    // progress, and allocates a new identity on re-entry.
    Blackboard pillarBoard = captured;
    pillarBoard.CurrentScope.AttemptId = 13;
    pillarBoard.Revision = 700;
    pillarBoard.Route.NavigationHints.clear();
    ActorSnapshot capturedPillar = capturedCrash;
    capturedPillar.Guid = UnitGuid(41843, 802);
    capturedPillar.Entry = AdaptiveMagmawStrategy::PillarEntry;
    capturedPillar.Auras.clear();
    capturedPillar.Position = { -310.0f, -20.0f, 210.5f };
    capturedBot.Position = { -302.0f, -20.0f, 210.5f };
    pillarBoard.Players = { capturedBot };
    pillarBoard.Hostiles = { boss };
    pillarBoard.Summons = { capturedPillar };
    MagmawEventMovementTransitionState pillarState;
    auto pillarFirst = strategy.Propose(pillarBoard, capturedActor, "dps",
        nullptr, false, false, nullptr, nullptr, &pillarState);
    assert(pillarFirst.Movement);
    assert(pillarFirst.Movement->Id.Mechanic == "pillar_evade");
    uint64 const pillarIntent = pillarFirst.Movement->Id.EventGeneration;
    auto const* pillarRequest = std::get_if<BotNativeAction::Move>(
        &pillarFirst.Movement->Action);
    assert(pillarRequest);

    pillarBoard.Revision += 1;
    capturedBot.Position = { -300.0f, -20.0f, 210.5f };
    pillarBoard.Players = { capturedBot };
    auto pillarUnsafe = strategy.Propose(pillarBoard, capturedActor, "dps",
        nullptr, false, false, nullptr, nullptr, &pillarState);
    assert(pillarUnsafe.Movement);
    assert(pillarUnsafe.Movement->Id.EventGeneration == pillarIntent);
    auto const* retainedPillarRequest = std::get_if<BotNativeAction::Move>(
        &pillarUnsafe.Movement->Action);
    assert(retainedPillarRequest
        && retainedPillarRequest->X == pillarRequest->X
        && retainedPillarRequest->Y == pillarRequest->Y
        && retainedPillarRequest->Z == pillarRequest->Z);

    pillarBoard.Revision += 1;
    capturedBot.Position = { -297.0f, -20.0f, 210.0f };
    pillarBoard.Players = { capturedBot };
    auto pillarSafe = strategy.Propose(pillarBoard, capturedActor, "dps",
        nullptr, false, false, nullptr, nullptr, &pillarState);
    assert(!pillarState.ActiveLethal());
    assert(!pillarSafe.Movement);

    pillarBoard.Revision += 1;
    capturedBot.Position = { -302.0f, -20.0f, 210.5f };
    pillarBoard.Players = { capturedBot };
    auto pillarReentry = strategy.Propose(pillarBoard, capturedActor, "dps",
        nullptr, false, false, nullptr, nullptr, &pillarState);
    assert(pillarReentry.Movement);
    assert(pillarReentry.Movement->Id.EventGeneration != pillarIntent);
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            "-I",
            str(ROOT / "src/common"),
            "-I",
            str(ROOT / "src/common/Utilities"),
            "-I",
            str(ROOT / "src/common/Logging"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)
