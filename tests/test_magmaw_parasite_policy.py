from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_magmaw_lane_transition_replays_selection_to_reset(tmp_path: Path) -> None:
    source = tmp_path / "magmaw_lane_transition_replay.cpp"
    binary = tmp_path / "magmaw_lane_transition_replay"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMovementKernelAdapter.h"
#include <algorithm>
#include <cassert>
#include <cmath>

using namespace BotEncounter;
using BotNativeAction::Move;

std::string ObjectGuid::ToString() const
{
    return std::to_string(GetRawValue());
}

static ActorSnapshot Player(uint32 guid, char const* role,
    char const* spec, Vector3 position)
{
    ActorSnapshot player;
    player.Guid = ObjectGuid(HighGuid::Player, guid);
    player.Alive = true;
    player.Role = role;
    player.ClassSpec = spec;
    player.HealthPct = 100.0f;
    player.Position = position;
    return player;
}

static ActorSnapshot Parasite(uint32 guid, Vector3 position)
{
    ActorSnapshot parasite;
    parasite.Guid = ObjectGuid(HighGuid::Unit,
        AdaptiveMagmawStrategy::ParasiteEntry, guid);
    parasite.Entry = AdaptiveMagmawStrategy::ParasiteEntry;
    parasite.Alive = true;
    parasite.Position = position;
    return parasite;
}

static Blackboard BuildBoard()
{
    Blackboard board;
    board.CurrentScope = Scope{
        "lane-replay", 7, 0, 4, "bwd.magmaw.encounter", 669, 1, "magmaw" };
    board.Revision = 21;
    board.ObservedAtMs = 1787940572135;
    board.NativeBossState = "in_progress";
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Route.NavigationHints = { { 0.0f, -1.0f, 210.0f } };
    board.Players = {
        Player(30001, "tank", "protection_paladin", { 0.0f, 0.0f, 210.0f }),
        Player(30006, "dps", "fire_mage", { 12.0f, -30.0f, 210.0f }),
        Player(30009, "dps", "marksmanship_hunter", { 12.0f, -30.0f, 210.0f }),
        Player(30008, "dps", "affliction_warlock", { 0.0f, -22.0f, 210.0f }) };

    ActorSnapshot boss;
    boss.Guid = ObjectGuid(HighGuid::Unit,
        uint32(AdaptiveMagmawStrategy::BossEntry), uint32(39));
    boss.Entry = AdaptiveMagmawStrategy::BossEntry;
    boss.Alive = true;
    boss.Attackable = true;
    boss.Selectable = true;
    boss.InCombat = true;
    boss.VictimGuid = board.Players.front().Guid;
    boss.Position = { 0.0f, 0.0f, 210.0f };
    board.Hostiles = { boss, Parasite(500, { 12.0f, -26.0f, 210.0f }) };
    return board;
}

static BotMovementArbitration::Lease ExpiredLease(Blackboard const& board)
{
    BotMovementArbitration::Lease lease;
    lease.MovementOwner = BotMovementArbitration::Owner::Hazard;
    lease.MovementPriority = BotMovementArbitration::Priority::Hazard;
    lease.ExpiresAtMs = 0;
    lease.MovementScope = {
        board.CurrentScope.AttemptId,
        board.CurrentScope.WipeGeneration,
        board.CurrentScope.RouteGeneration,
        board.CurrentScope.MapId,
        board.CurrentScope.InstanceId };
    return lease;
}

static BotNativeAction::Move const* MoveOf(
    AdaptiveMagmawPlan const& plan)
{
    return plan.Movement
        ? std::get_if<BotNativeAction::Move>(&plan.Movement->Action) : nullptr;
}

static float Distance(Vector3 const& left, Vector3 const& right)
{
    return std::hypot(left.X - right.X, left.Y - right.Y);
}

int main()
{
    AdaptiveMagmawStrategy strategy;
    MagmawLaneTransitionState transition;
    Blackboard board = BuildBoard();
    ObjectGuid const mage = board.Players[1].Guid;
    ObjectGuid const hunter = board.Players[2].Guid;
    ObjectGuid const ordinary = board.Players[3].Guid;

    // Selection and admission: exactly the fixed fire mage/hunter pair owns
    // the cohort transition, and the full lane corridor is safe.
    // Preserve the historical endpoint-only counterexample: the former
    // 22-yard support anchor cuts through the same 30/24 lane chord.
    assert(!MagmawParasitePolicy::FullLaneCorridorSafe(
        { { 0.0f, -22.0f, 210.0f }, { 24.0f, -30.0f, 210.0f },
            { -24.0f, -30.0f, 210.0f } }));
    assert(MagmawParasitePolicy::FullLaneCorridorSafe(
        { { 0.0f, -8.0f, 210.0f }, { 24.0f, -30.0f, 210.0f },
            { -24.0f, -30.0f, 210.0f } }));
    AdaptiveMagmawPlan first = strategy.Propose(board, mage, "dps", nullptr,
        false, false, &transition);
    Move const* firstMove = MoveOf(first);
    assert(firstMove);
    assert(transition.Committed);
    assert(transition.MageGuid == mage);
    assert(transition.HunterGuid == hunter);
    uint64 const firstId = transition.TransitionId;
    Vector3 const firstDestination{ firstMove->X, firstMove->Y, firstMove->Z };
    auto const firstDirection = transition.Lane;

    AdaptiveMagmawPlan hunterPlan = strategy.Propose(board, hunter, "dps",
        nullptr, false, false, &transition);
    Move const* hunterMove = MoveOf(hunterPlan);
    assert(hunterMove);
    assert(transition.TransitionId == firstId);
    assert(hunterMove->X == firstDestination.X);
    assert(hunterMove->Y == firstDestination.Y);

    // Multi-tick observation churn crosses the midpoint and changes the
    // parasite GUID. The expired generic lease cannot replace the semantic
    // transition or its destination.
    Blackboard churn = board;
    churn.Revision += 1;
    churn.ObservedAtMs += 1000;
    churn.Hostiles[1] = Parasite(1, { 0.0f, -30.0f, 210.0f });
    churn.Players[1].Position = { -6.0f, -30.0f, 210.0f };
    churn.Players[2].Position = { -6.0f, -30.0f, 210.0f };
    BotMovementArbitration::Lease expiredChurn = ExpiredLease(churn);
    AdaptiveMagmawPlan churnPlan = strategy.Propose(churn, mage, "dps",
        &expiredChurn, false, true, &transition);
    Move const* churnMove = MoveOf(churnPlan);
    assert(churnMove);
    assert(transition.TransitionId == firstId);
    assert(churnMove->X == firstDestination.X);
    assert(churnMove->Y == firstDestination.Y);
    assert(transition.Lane == firstDirection);

    // Native rejection/lease expiry is a retry of the same semantic
    // transition, not a replan. The old synthetic lease case is intentionally
    // preserved here: its expiry is irrelevant to the retained destination.
    AdaptiveMagmawPlan retry = strategy.Propose(churn, mage, "dps",
        &expiredChurn, false, false, &transition);
    Move const* retryMove = MoveOf(retry);
    assert(retryMove);
    assert(transition.TransitionId == firstId);
    assert(retryMove->X == firstDestination.X);
    assert(retryMove->Y == firstDestination.Y);

    // A lethal pillar preempts the lane, but cannot rewrite it. The typed
    // safety movement is temporary and uses the same transition on resume.
    Blackboard preempt = churn;
    preempt.Revision += 1;
    preempt.Players[1].Position = { firstDestination.X - 8.0f,
        firstDestination.Y, firstDestination.Z };
    ActorSnapshot pillar;
    pillar.Guid = ObjectGuid(HighGuid::Unit,
        AdaptiveMagmawStrategy::PillarEntry, uint32(800));
    pillar.Entry = AdaptiveMagmawStrategy::PillarEntry;
    pillar.Alive = true;
    pillar.Position = firstDestination;
    preempt.Summons = { pillar };
    AdaptiveMagmawPlan preemptPlan = strategy.Propose(preempt, mage, "dps",
        nullptr, false, false, &transition);
    assert(preemptPlan.Movement);
    assert(preemptPlan.Movement->Id.Mechanic == "pillar_evade");
    assert(transition.Preempted);
    assert(transition.TransitionId == firstId);
    assert(transition.Destination.X == firstDestination.X);
    assert(transition.Destination.Y == firstDestination.Y);
    BotActionArbitration::Kernel preemptKernel;
    preemptKernel.Begin(preempt.ObservedAtMs);
    MagmawMovementKernelAdapterContext preemptAdapter;
    preemptAdapter.ObservedAtMs = preempt.ObservedAtMs;
    uint32 preemptNativeAttempts = 0;
    preemptAdapter.Execute = [&preemptNativeAttempts](
        BotNativeAction::Intent const& intent, MagmawMovementNativeLease lease,
        BotWorldMovement::ExecutionObservation* movement)
    {
        assert(!movement);
        auto const* move = std::get_if<Move>(&intent);
        assert(move && move->IntentReason == "pillar_evade");
        assert(lease.Owner == BotMovementArbitration::Owner::Hazard);
        ++preemptNativeAttempts;
        return BotActionArbitration::Outcome::Submitted(
            "native_movement_submitted");
    };
    assert(SubmitMagmawMovementKernelCandidates(preemptKernel,
        preemptPlan.Movement, std::move(preemptAdapter))
        == preemptPlan.Movement.Size());
    assert(preemptKernel.Resolve().AnyCommitted);
    assert(preemptNativeAttempts == 1);

    Blackboard resume = churn;
    resume.Revision += 2;
    BotMovementArbitration::Lease expiredResume = ExpiredLease(resume);
    AdaptiveMagmawPlan resumedPlan = strategy.Propose(resume, mage, "dps",
        &expiredResume, false, true, &transition);
    Move const* resumedMove = MoveOf(resumedPlan);
    assert(resumedMove);
    assert(!transition.Preempted);
    assert(transition.TransitionId == firstId);
    assert(resumedMove->X == firstDestination.X);
    assert(resumedMove->Y == firstDestination.Y);

    // Canary117: repeat contact inside one living parasite wave is a shared
    // lane transition, not a new radial destination for one baiter.  Preserve
    // the first retained local escape, then require the next contact after a
    // temporary clearance to move both fixed baiters to the other endpoint.
    MagmawLaneTransitionState repeatedLane = transition;
    MagmawParasiteHazardState repeatedHazard;
    Blackboard endpointThreat = resume;
    endpointThreat.Revision += 1;
    endpointThreat.Players[1].Position = {
        firstDestination.X + 4.0f, firstDestination.Y, firstDestination.Z };
    endpointThreat.Hostiles[1] = Parasite(1, firstDestination);
    AdaptiveMagmawPlan localEscape = strategy.Propose(endpointThreat, mage,
        "dps", nullptr, false, false, &repeatedLane, &repeatedHazard);
    Move const* localEscapeMove = MoveOf(localEscape);
    assert(localEscapeMove);
    assert(repeatedHazard.HasRetainedIntent());
    assert(repeatedLane.TransitionId == firstId);

    Blackboard temporaryClear = endpointThreat;
    temporaryClear.Revision += 1;
    temporaryClear.Hostiles[1] = Parasite(1, { 0.0f, -80.0f, 210.0f });
    AdaptiveMagmawPlan cleared = strategy.Propose(temporaryClear, mage,
        "dps", nullptr, false, false, &repeatedLane, &repeatedHazard);
    assert(!repeatedHazard.HasRetainedIntent());
    assert(!cleared.Movement);

    Blackboard repeatedContact = temporaryClear;
    repeatedContact.Revision += 1;
    repeatedContact.Hostiles[1] = Parasite(
        1, repeatedContact.Players[1].Position);
    AdaptiveMagmawPlan redirected = strategy.Propose(repeatedContact, mage,
        "dps", nullptr, false, false, &repeatedLane, &repeatedHazard);
    Move const* redirectedMove = MoveOf(redirected);
    assert(redirectedMove);
    assert(repeatedLane.TransitionId != firstId);
    assert(repeatedLane.Lane != firstDirection);
    assert(redirectedMove->X == -firstDestination.X);
    assert(redirectedMove->Y == firstDestination.Y);
    assert(redirected.Movement->Id.EventGeneration
        == repeatedLane.TransitionId);
    AdaptiveMagmawPlan redirectedHunter = strategy.Propose(repeatedContact,
        hunter, "dps", nullptr, false, false, &repeatedLane);
    assert(MoveOf(redirectedHunter));
    assert(MoveOf(redirectedHunter)->X == redirectedMove->X);
    assert(MoveOf(redirectedHunter)->Y == redirectedMove->Y);

    // Both native paths arrive after event A despawns. GUID churn observed
    // before arrival remains inside the admitted transition, while the empty
    // mechanic boundary is explicitly sealed as generation/kind (0, 0).
    Blackboard arrived = resume;
    arrived.Revision += 1;
    arrived.Players[1].Position = firstDestination;
    arrived.Players[2].Position = firstDestination;
    arrived.Hostiles.resize(1);
    AdaptiveMagmawPlan mageArrived = strategy.Propose(arrived, mage, "dps",
        nullptr, false, false, &transition);
    AdaptiveMagmawPlan hunterArrived = strategy.Propose(arrived, hunter, "dps",
        nullptr, false, false, &transition);
    // Formation restoration may independently offer a return-to-stack move
    // after the lane path arrives; it must not alter the semantic arrival
    // boundary or make event B look like the first captured generation.
    assert(mageArrived.OwnsNode);
    assert(hunterArrived.OwnsNode);
    assert(transition.IsArrived());
    assert(transition.ArrivedGeneration == 0);
    assert(transition.ArrivedMechanicKind == 0);
    assert(transition.ArrivalGenerationCaptured);
    uint64 const arrivedId = transition.TransitionId;

    Blackboard sameEvent = arrived;
    sameEvent.Revision += 1;
    AdaptiveMagmawPlan sameEventPlan = strategy.Propose(sameEvent, mage, "dps",
        nullptr, false, false, &transition);
    assert(sameEventPlan.OwnsNode);
    assert(transition.TransitionId == arrivedId);

    // A later mechanic generation after native arrival is the only event
    // allowed to retire the transition and select the opposite lane.
    Blackboard nextEvent = sameEvent;
    nextEvent.Revision += 1;
    nextEvent.Hostiles.push_back(Parasite(2, { 0.0f, -80.0f, 210.0f }));
    AdaptiveMagmawPlan nextPlan = strategy.Propose(nextEvent, mage, "dps",
        nullptr, false, false, &transition);
    Move const* nextMove = MoveOf(nextPlan);
    assert(nextMove);
    assert(transition.TransitionId != arrivedId);
    assert(transition.Lane != firstDirection);
    assert(nextMove->X != firstDestination.X
        || nextMove->Y != firstDestination.Y);

    // An exact wipe/attempt scope reset clears the old transition before a
    // new event is admitted.
    Blackboard reset = nextEvent;
    reset.CurrentScope.WipeGeneration += 1;
    reset.Revision += 1;
    reset.Hostiles[1] = Parasite(3, { 12.0f, -26.0f, 210.0f });
    reset.Players[1].Position = { 12.0f, -30.0f, 210.0f };
    AdaptiveMagmawPlan resetPlan = strategy.Propose(reset, mage, "dps",
        nullptr, false, false, &transition);
    assert(MoveOf(resetPlan));
    assert(transition.WipeGeneration == reset.CurrentScope.WipeGeneration);
    assert(transition.TransitionId == 1);

    // A non-baiter never owns parasite movement and restores the boss-side
    // support position without mutating the shared bait transition.
    uint64 const stableId = transition.TransitionId;
    Vector3 const stableDestination = transition.Destination;
    Blackboard ordinaryBoard = reset;
    ordinaryBoard.Revision += 1;
    ordinaryBoard.Hostiles[1].Position = ordinaryBoard.Players[3].Position;
    AdaptiveMagmawPlan ordinaryPlan = strategy.Propose(ordinaryBoard, ordinary,
        "dps", nullptr, false, false, &transition);
    assert(ordinaryPlan.Movement);
    assert(ordinaryPlan.Movement->Id.Mechanic
        == "ranged_formation_restore");
    assert(transition.TransitionId == stableId);
    assert(Distance(transition.Destination, stableDestination) < 0.01f);
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
            "-I",
            str(ROOT / "src/common/Debugging"),
            str(source),
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
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_magmaw_parasite_route_retains_safe_direct_and_crash_arc(
    tmp_path: Path,
) -> None:
    source = tmp_path / "magmaw_parasite_route_replay.cpp"
    binary = tmp_path / "magmaw_parasite_route_replay"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawParasitePolicy.h"
#include <cassert>
#include <cmath>

using namespace BotEncounter;

static ActorSnapshot Player(uint32 guid, char const* spec, Vector3 position)
{
    ActorSnapshot player;
    player.Guid = ObjectGuid(HighGuid::Player, guid);
    player.Alive = true;
    player.Role = "dps";
    player.ClassSpec = spec;
    player.Position = position;
    return player;
}

static ActorSnapshot Parasite(uint32 guid, Vector3 position)
{
    ActorSnapshot parasite;
    parasite.Guid = ObjectGuid(HighGuid::Unit, 41806, guid);
    parasite.Entry = 41806;
    parasite.Alive = true;
    parasite.Position = position;
    return parasite;
}

static Blackboard Board()
{
    Blackboard board;
    board.CurrentScope = Scope{
        "parasite-route", 17, 0, 8, "bwd.magmaw.encounter", 669, 3,
        "magmaw" };
    board.Revision = 4;
    board.ObservedAtMs = 1000;
    board.Players = {
        Player(30, "fire_mage", { 0.0f, -8.0f, 210.0f }),
        Player(20, "fire_mage", { -24.0f, -30.0f, 211.313324f }),
        Player(40, "marksmanship_hunter", { 0.0f, -8.0f, 210.0f }),
        Player(10, "marksmanship_hunter", { -24.0f, -30.0f, 211.581f }),
        Player(5, "affliction_warlock", { 0.0f, -8.0f, 210.0f }) };
    board.Hostiles = { Parasite(900, { 0.0f, -60.0f, 211.815f }) };
    return board;
}

static void AssertSafeRoute(Vector3 actor, Vector3 support,
    MagmawParasiteRoutePlan const& route,
    std::vector<Vector3> const& parasites, float declaredZ)
{
    Vector3 previous = actor;
    for (uint8 index = 0; index < route.PointCount; ++index)
    {
        Vector3 const& point = route.Points[index];
        assert(point.Z == declaredZ);
        assert(MagmawParasiteRoute::PointClearance(point, parasites) >= 10.0f);
        assert(MagmawParasiteRoute::SegmentClearance(previous, point,
            parasites) >= 10.0f);
        assert(MagmawParasiteRoute::DistanceToSegment(support, previous,
            point) >= 20.0f);
        previous = point;
    }
}

int main()
{
    Blackboard board = Board();
    auto const baiters = MagmawParasitePolicy::ResolveFixedBaiters(board);
    assert(baiters.first == board.Players[1].Guid);
    assert(baiters.second == board.Players[3].Guid);

    // Liveness is execution state, not assignment identity. The frozen
    // lowest-GUID Mage and Hunter remain the baiters after death instead of
    // splitting combat ownership from the retained lane transition.
    board.Players[1].Alive = false;
    board.Players[3].Alive = false;
    auto const deadBaiters = MagmawParasitePolicy::ResolveFixedBaiters(board);
    assert(deadBaiters.first == baiters.first);
    assert(deadBaiters.second == baiters.second);
    board.Players[1].Alive = true;
    board.Players[3].Alive = true;

    Vector3 const actor = board.Players[1].Position;
    Vector3 const support{ 0.0f, -8.0f, 211.815f };
    Vector3 const destination{ 24.0f, -30.0f, 211.815f };
    std::vector<Vector3> parasites{ board.Hostiles[0].Position };

    // A route keeps the declared navigation-floor Z. It may tolerate the
    // actor's small on-terrain offset, but invalid and cross-floor anchors do
    // not become same-level merely by inheriting the actor's transient Z.
    Vector3 invalidDestination = destination;
    invalidDestination.Z = std::numeric_limits<float>::quiet_NaN();
    assert(!MagmawParasiteRoute::Build(actor, support, invalidDestination,
        parasites));
    Vector3 crossFloorDestination = destination;
    crossFloorDestination.Z = actor.Z
        + BotWorldMovement::NativeFloorTolerance + 0.01f;
    assert(!MagmawParasiteRoute::Build(actor, support, crossFloorDestination,
        parasites));
    Vector3 crossFloorSupport = support;
    crossFloorSupport.Z = actor.Z
        - BotWorldMovement::NativeFloorTolerance - 0.01f;
    assert(!MagmawParasiteRoute::Build(actor, crossFloorSupport, destination,
        parasites));

    // Fail-before counterexample: endpoint clearance alone accepted this
    // chord. Production admission now proves every point and full segment.
    auto direct = MagmawParasiteRoute::Build(actor, support, destination,
        parasites);
    assert(direct && direct->PointCount == 1);
    assert(!direct->UsesFarPerimeterArc);
    assert(direct->AdmittedClearance == 16.0f);
    AssertSafeRoute(actor, support, *direct, parasites, destination.Z);

    MagmawParasiteCrashObstacle crash;
    crash.Active = true;
    crash.Center = { 0.0f, -30.0f, -500.0f };
    crash.UnsafeSideAnchor = actor;
    crash.SafeSideAnchor = destination;
    crash.Radius = 6.0f;
    auto arc = MagmawParasiteRoute::Build(actor, support, destination,
        parasites, crash);
    assert(arc && arc->UsesFarPerimeterArc && arc->PointCount == 3);
    assert(MagmawParasiteRoute::DistanceToSegment(crash.Center, actor,
        destination) < crash.Radius);
    AssertSafeRoute(actor, support, *arc, parasites, destination.Z);
    Vector3 previous = actor;
    for (uint8 index = 0; index < arc->PointCount; ++index)
    {
        assert(MagmawParasiteRoute::DistanceToSegment(crash.Center, previous,
            arc->Points[index]) >= crash.Radius);
        previous = arc->Points[index];
    }

    MagmawParasitePolicy::FormationAnchors const anchors{
        support, actor, destination };
    MagmawLaneTransitionState retained;
    auto firstPoint = MagmawParasitePolicy::EnsureSafeParasiteRoute(board,
        board.Players[1], anchors, retained, 900, 2, crash);
    assert(firstPoint && retained.MageParasiteRoute.UsesFarPerimeterArc);
    MagmawParasiteRoutePlan const retainedArc = retained.MageParasiteRoute;
    auto hunterPoint = MagmawParasitePolicy::EnsureSafeParasiteRoute(board,
        board.Players[3], anchors, retained, 900, 2, crash);
    assert(hunterPoint && !retained.HunterParasiteRoute.Empty());
    assert(retained.Destination.Z == destination.Z);
    for (uint8 index = 0; index < retained.MageParasiteRoute.PointCount;
        ++index)
        assert(retained.MageParasiteRoute.Points[index].Z == destination.Z);
    for (uint8 index = 0; index < retained.HunterParasiteRoute.PointCount;
        ++index)
        assert(retained.HunterParasiteRoute.Points[index].Z == destination.Z);

    // Retained semantic state must not turn identical X/Y on another floor
    // into native progress. Build and attach the direct route for both fixed
    // baiters, then cross the post-retention actor boundary causally.
    MagmawLaneTransitionState floorRetained;
    auto floorMagePoint = MagmawParasitePolicy::EnsureSafeParasiteRoute(board,
        board.Players[1], anchors, floorRetained, 900, 2);
    auto floorHunterPoint = MagmawParasitePolicy::EnsureSafeParasiteRoute(
        board, board.Players[3], anchors, floorRetained, 900, 2);
    assert(floorMagePoint && floorHunterPoint);
    assert(floorRetained.MageParasiteRoute.PointCount == 1);
    assert(floorRetained.HunterParasiteRoute.PointCount == 1);
    MagmawParasiteRoutePlan const* floorMageRoute =
        floorRetained.RouteFor(board.Players[1].Guid);
    assert(floorMageRoute && floorRetained.NextRoutePoint(
        board.Players[1].Guid) == 0);

    Vector3 crossFloorActor = floorMageRoute->Destination();
    crossFloorActor.Z += BotWorldMovement::NativeFloorTolerance + 0.01f;
    assert(!MagmawParasiteRoute::RemainingRouteSafe(crossFloorActor,
        *floorMageRoute, 0, parasites));
    floorRetained.ObserveArrival(board.Players[1].Guid, crossFloorActor,
        MagmawParasitePolicy::DestinationTolerance, board.Revision);
    assert(floorRetained.NextRoutePoint(board.Players[1].Guid) == 0);
    assert(!floorRetained.MageArrived);

    Vector3 sameFloorActor = floorMageRoute->Destination();
    sameFloorActor.Z -= 1.0f;
    assert(MagmawParasiteRoute::RemainingRouteSafe(sameFloorActor,
        *floorMageRoute, 0, parasites));
    floorRetained.ObserveArrival(board.Players[1].Guid, sameFloorActor,
        MagmawParasitePolicy::DestinationTolerance, board.Revision);
    assert(floorRetained.NextRoutePoint(board.Players[1].Guid)
        == floorMageRoute->PointCount);
    assert(floorRetained.MageArrived);
    assert(!floorRetained.HunterArrived);

    // GUID churn is not a route generation: direction, destination, and all
    // retained arc points remain byte-for-byte stable.
    board.Hostiles[0] = Parasite(1, { 0.0f, -60.0f, 210.0f });
    ++board.Revision;
    auto churnPoint = MagmawParasitePolicy::EnsureSafeParasiteRoute(board,
        board.Players[1], anchors, retained, 1, 2, crash);
    assert(churnPoint && retained.Destination.X == destination.X
        && retained.Destination.Y == destination.Y);
    assert(retained.MageParasiteRoute.PointCount == retainedArc.PointCount);
    for (uint8 index = 0; index < retainedArc.PointCount; ++index)
    {
        assert(retained.MageParasiteRoute.Points[index].X
            == retainedArc.Points[index].X);
        assert(retained.MageParasiteRoute.Points[index].Y
            == retainedArc.Points[index].Y);
        assert(retained.MageParasiteRoute.Points[index].Z == destination.Z);
    }
    assert(!MagmawParasitePolicy::EnsureSafeParasiteRoute(board,
        board.Players[4], anchors, retained, 1, 2, crash));

    MagmawParasiteRouteFacts routine = MagmawParasiteRoute::ObserveFacts(
        actor, parasites);
    MagmawParasiteMobilityWindow soonCrash{ 5000, 8000 };
    assert(routine.ReserveDirectionalMobility(soonCrash));
    assert(!routine.MayUseBlinkOrDisengage(soonCrash));

    Blackboard emergencyBoard = board;
    emergencyBoard.Hostiles[0] = Parasite(2,
        { actor.X + 5.0f, actor.Y, actor.Z });
    MagmawParasiteRouteFacts emergency =
        MagmawParasitePolicy::ObserveRouteFacts(emergencyBoard,
            emergencyBoard.Players[1]);
    assert(emergency.EmergencyClearance);
    assert(!emergency.ReserveDirectionalMobility(soonCrash));
    assert(emergency.MayUseBlinkOrDisengage(soonCrash));

    MagmawLaneTransitionState urgentLane;
    MagmawParasiteHazardState urgentHazard;
    auto urgent = MagmawParasitePolicy::Propose(emergencyBoard,
        emergencyBoard.Players[1], emergencyBoard.Hostiles[0], true, anchors,
        nullptr, &urgentLane, &urgentHazard);
    assert(urgent);
    auto const* move = std::get_if<BotNativeAction::Move>(&urgent->Action);
    assert(move && move->PreemptCasting);
    assert(BotActionArbitration::Conflicts(urgent->Resources(),
        BotActionArbitration::Uses(BotActionArbitration::Resource::Movement)));
    assert(BotActionArbitration::Conflicts(urgent->Resources(),
        BotActionArbitration::Uses(BotActionArbitration::Resource::Cast)));
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
            "-I",
            str(ROOT / "src/common/Debugging"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_magmaw_pillar_lane_promotes_to_retained_parasite_route(
    tmp_path: Path,
) -> None:
    source = tmp_path / "magmaw_pillar_parasite_transition.cpp"
    binary = tmp_path / "magmaw_pillar_parasite_transition"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawParasitePolicy.h"
#include <cassert>

using namespace BotEncounter;

static ActorSnapshot Player(uint32 guid, char const* spec, Vector3 position)
{
    ActorSnapshot player;
    player.Guid = ObjectGuid(HighGuid::Player, guid);
    player.Alive = true;
    player.Role = "dps";
    player.ClassSpec = spec;
    player.Position = position;
    return player;
}

static ActorSnapshot Parasite(uint32 guid, Vector3 position)
{
    ActorSnapshot parasite;
    parasite.Guid = ObjectGuid(HighGuid::Unit, 41806, guid);
    parasite.Entry = 41806;
    parasite.Alive = true;
    parasite.Position = position;
    return parasite;
}

static Blackboard Board(Vector3 parasitePosition)
{
    Blackboard board;
    board.CurrentScope = Scope{
        "pillar-parasite", 18, 0, 9, "bwd.magmaw.encounter", 669, 3,
        "magmaw" };
    board.Revision = 10;
    board.Players = {
        Player(20, "fire_mage", { -24.0f, -30.0f, 210.0f }),
        Player(10, "marksmanship_hunter", { -24.0f, -30.0f, 210.0f }) };
    board.Hostiles = { Parasite(900, parasitePosition) };
    return board;
}

static void AdmitPillar(Blackboard const& board,
    MagmawParasitePolicy::FormationAnchors const& anchors,
    MagmawLaneTransitionState& transition)
{
    transition.ObserveScope(board);
    auto const baiters = MagmawParasitePolicy::ResolveFixedBaiters(board);
    transition.AssignBaiters(baiters.first, baiters.second);
    auto pillar = MagmawParasitePolicy::EnsureLaneDestination(board,
        board.Players[0], anchors, transition, 700, 1);
    assert(pillar && transition.Committed);
    assert(transition.MechanicKind == 1);
    assert(transition.MageParasiteRoute.Empty());
}

int main()
{
    MagmawParasitePolicy::FormationAnchors const anchors{
        { 0.0f, -8.0f, 210.0f },
        { -24.0f, -30.0f, 210.0f },
        { 24.0f, -30.0f, 210.0f } };
    Blackboard board = Board({ 0.0f, -60.0f, 210.0f });
    MagmawLaneTransitionState transition;
    AdmitPillar(board, anchors, transition);
    auto const lane = transition.Lane;
    Vector3 const destination = transition.Destination;
    ObjectGuid const mage = transition.MageGuid;
    ObjectGuid const hunter = transition.HunterGuid;
    uint64 const pillarTransitionId = transition.TransitionId;

    // Fail-before: the committed kind-1 lane made the kind-2 call return null
    // forever because its route was empty. Promotion retains lane ownership
    // and endpoint while installing the first safe parasite waypoint.
    auto parasite = MagmawParasitePolicy::EnsureSafeParasiteRoute(board,
        board.Players[0], anchors, transition,
        board.Hostiles[0].Guid.GetRawValue(), 2);
    assert(parasite);
    assert(transition.MechanicKind == 2);
    assert(!transition.MageParasiteRoute.Empty());
    assert(transition.Lane == lane);
    assert(transition.Destination.X == destination.X
        && transition.Destination.Y == destination.Y);
    assert(transition.MageGuid == mage && transition.HunterGuid == hunter);
    assert(transition.TransitionId != pillarTransitionId);

    auto hunterPoint = MagmawParasitePolicy::EnsureSafeParasiteRoute(board,
        board.Players[1], anchors, transition, 1, 2);
    assert(hunterPoint);
    assert(hunterPoint->X == parasite->X && hunterPoint->Y == parasite->Y);
    assert(transition.Lane == lane && transition.MageGuid == mage
        && transition.HunterGuid == hunter);

    // A promotion that cannot prove the hard 10-yard segment clearance fails
    // closed and leaves the committed Pillar transition untouched.
    Blackboard blocked = Board({ -19.0f, -30.0f, 210.0f });
    blocked.CurrentScope.AttemptId += 1;
    MagmawLaneTransitionState blockedTransition;
    AdmitPillar(blocked, anchors, blockedTransition);
    auto const blockedLane = blockedTransition.Lane;
    Vector3 const blockedDestination = blockedTransition.Destination;
    uint64 const blockedId = blockedTransition.TransitionId;
    assert(!MagmawParasitePolicy::EnsureSafeParasiteRoute(blocked,
        blocked.Players[0], anchors, blockedTransition,
        blocked.Hostiles[0].Guid.GetRawValue(), 2));
    assert(blockedTransition.MechanicKind == 1);
    assert(blockedTransition.MageParasiteRoute.Empty());
    assert(blockedTransition.TransitionId == blockedId);
    assert(blockedTransition.Lane == blockedLane);
    assert(blockedTransition.Destination.X == blockedDestination.X
        && blockedTransition.Destination.Y == blockedDestination.Y);
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
            "-I",
            str(ROOT / "src/common/Debugging"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_magmaw_arrived_endpoint_replans_same_living_wave(tmp_path: Path) -> None:
    source = tmp_path / "magmaw_arrived_endpoint_replay.cpp"
    binary = tmp_path / "magmaw_arrived_endpoint_replay"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include <cassert>

using namespace BotEncounter;
using BotNativeAction::Move;

static ActorSnapshot Player(uint32 guid, char const* spec,
    Vector3 position)
{
    ActorSnapshot player;
    player.Guid = ObjectGuid(HighGuid::Player, guid);
    player.Alive = true;
    player.Role = "dps";
    player.ClassSpec = spec;
    player.HealthPct = 100.0f;
    player.Position = position;
    return player;
}

static ActorSnapshot Parasite(uint32 guid, Vector3 position)
{
    ActorSnapshot parasite;
    parasite.Guid = ObjectGuid(HighGuid::Unit,
        AdaptiveMagmawStrategy::ParasiteEntry, guid);
    parasite.Entry = AdaptiveMagmawStrategy::ParasiteEntry;
    parasite.Alive = true;
    parasite.Position = position;
    return parasite;
}

static Blackboard BuildBoard()
{
    Blackboard board;
    board.CurrentScope = Scope{
        "arrived-endpoint", 7, 0, 4, "bwd.magmaw.encounter", 669, 1,
        "magmaw" };
    board.Revision = 21;
    board.ObservedAtMs = 1787991388799;
    board.NativeBossState = "in_progress";
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Route.NavigationHints = { { 0.0f, -1.0f, 210.0f } };
    board.Players = {
        Player(30006, "fire_mage", { 12.0f, -30.0f, 210.0f }),
        Player(30009, "marksmanship_hunter", { 12.0f, -30.0f, 210.0f }) };

    ActorSnapshot boss;
    boss.Guid = ObjectGuid(HighGuid::Unit,
        uint32(AdaptiveMagmawStrategy::BossEntry), uint32(39));
    boss.Entry = AdaptiveMagmawStrategy::BossEntry;
    boss.Alive = true;
    boss.Attackable = true;
    boss.Selectable = true;
    boss.InCombat = true;
    boss.Position = { 0.0f, 0.0f, 210.0f };
    board.Hostiles = { boss, Parasite(500, { 12.0f, -26.0f, 210.0f }) };
    return board;
}

static Move const* MoveOf(AdaptiveMagmawPlan const& plan)
{
    return plan.Movement
        ? std::get_if<Move>(&plan.Movement->Action) : nullptr;
}

int main()
{
    AdaptiveMagmawStrategy strategy;
    MagmawLaneTransitionState transition;
    Blackboard board = BuildBoard();
    ObjectGuid const mage = board.Players[0].Guid;
    ObjectGuid const hunter = board.Players[1].Guid;

    // Admit the fixed lane and carry both native paths to the same endpoint.
    AdaptiveMagmawPlan first = strategy.Propose(board, mage, "dps", nullptr,
        false, false, &transition);
    Move const* firstMove = MoveOf(first);
    assert(firstMove);
    Vector3 const arrivedEndpoint{ firstMove->X, firstMove->Y, firstMove->Z };
    uint64 const firstId = transition.TransitionId;
    auto const firstLane = transition.Lane;

    Blackboard arrived = board;
    arrived.Revision += 1;
    arrived.Players[0].Position = arrivedEndpoint;
    arrived.Players[1].Position = arrivedEndpoint;
    arrived.Hostiles[1] = Parasite(500, { 0.0f, -80.0f, 210.0f });
    assert(MoveOf(strategy.Propose(arrived, mage, "dps", nullptr, false,
        false, &transition)) == nullptr);
    assert(MoveOf(strategy.Propose(arrived, hunter, "dps", nullptr, false,
        false, &transition)) == nullptr);
    assert(transition.IsArrived());
    assert(transition.MechanicGeneration
        == Parasite(500, arrivedEndpoint).Guid.GetRawValue());
    assert(transition.MechanicKind == 2);

    // Revision-4 counterexample: the same living wave makes the arrived
    // endpoint unsafe. The old EnsureLaneTransition null result caused this
    // assertion to fail, leaving both baiters at the infected endpoint.
    Blackboard unsafe = arrived;
    unsafe.Revision += 1;
    unsafe.Hostiles[1] = Parasite(500, arrivedEndpoint);
    AdaptiveMagmawPlan unsafeMage = strategy.Propose(unsafe, mage, "dps",
        nullptr, false, false, &transition);
    Move const* escapeMage = MoveOf(unsafeMage);
    assert(escapeMage && "arrived living-wave endpoint must redirect");
    assert(transition.TransitionId != firstId);
    assert(transition.Lane != firstLane);
    assert(escapeMage->X != arrivedEndpoint.X
        || escapeMage->Y != arrivedEndpoint.Y);
    assert(unsafeMage.Movement->Id.Actor == mage);
    assert(unsafeMage.Movement->Id.EventGeneration == transition.TransitionId);
    uint64 const redirectedId = transition.TransitionId;
    Vector3 const redirectedEndpoint{ escapeMage->X, escapeMage->Y,
        escapeMage->Z };

    // The second fixed baiter receives the same opposite endpoint and
    // transition identity; it cannot fall back to local radial movement.
    AdaptiveMagmawPlan unsafeHunter = strategy.Propose(unsafe, hunter, "dps",
        nullptr, false, false, &transition);
    Move const* escapeHunter = MoveOf(unsafeHunter);
    assert(escapeHunter);
    assert(escapeHunter->X == redirectedEndpoint.X);
    assert(escapeHunter->Y == redirectedEndpoint.Y);
    assert(escapeHunter->Z == redirectedEndpoint.Z);
    assert(unsafeHunter.Movement->Id.Actor == hunter);
    assert(unsafeHunter.Movement->Id.EventGeneration == redirectedId);
    assert(transition.TransitionId == redirectedId);
    assert(transition.Lane != firstLane);
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
            "-I",
            str(ROOT / "src/common/Debugging"),
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_magmaw_containment_replays_full_runtime_contract(tmp_path: Path) -> None:
    source = tmp_path / "magmaw_containment_runtime_replay.cpp"
    binary = tmp_path / "magmaw_containment_runtime_replay"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMovementKernelAdapter.h"
#include "Bots/BotWorldPopulationMgrNativeFloor.h"
#include "Bots/BotWorldPopulationMgrMovement.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <functional>
#include <string>

using namespace BotEncounter;
using BotNativeAction::Move;

std::string ObjectGuid::ToString() const
{
    return std::to_string(GetRawValue());
}

static ObjectGuid PlayerGuid(uint32 guid)
{
    return ObjectGuid(HighGuid::Player, guid);
}

static ActorSnapshot Player(uint32 guid, char const* role,
    char const* spec, Vector3 position)
{
    ActorSnapshot player;
    player.Guid = PlayerGuid(guid);
    player.Kind = ActorKind::Player;
    player.Alive = true;
    player.Role = role;
    player.ClassSpec = spec;
    player.HealthPct = 100.0f;
    player.Position = position;
    return player;
}

static ActorSnapshot Creature(uint32 entry, uint32 guid, Vector3 position)
{
    ActorSnapshot creature;
    creature.Guid = ObjectGuid(HighGuid::Unit, entry, guid);
    creature.Entry = entry;
    creature.Alive = true;
    creature.Attackable = true;
    creature.Selectable = true;
    creature.InCombat = true;
    creature.Position = position;
    return creature;
}

static ActorSnapshot Parasite(uint32 guid, Vector3 position)
{
    return Creature(AdaptiveMagmawStrategy::ParasiteEntry, guid, position);
}

static Blackboard BuildBoard()
{
    Blackboard board;
    board.CurrentScope = Scope{
        "containment-replay", 110, 0, 6, "bwd.magmaw.encounter", 669, 1,
        "magmaw" };
    board.Revision = 1;
    board.ObservedAtMs = 100000;
    board.NativeBossState = "in_progress";
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Route.NavigationHints = { { 0.0f, -1.0f, 210.0f } };
    board.Players = {
        Player(30001, "tank", "protection_paladin", { 0.0f, 0.0f, 210.0f }),
        Player(30002, "tank", "blood_death_knight", { 0.0f, -2.0f, 210.0f }),
        Player(30003, "healer", "restoration_druid", { 0.0f, -4.0f, 210.0f }),
        Player(30004, "healer", "holy_paladin", { 0.0f, -6.0f, 210.0f }),
        Player(30005, "healer", "discipline_priest", { 0.0f, -8.0f, 210.0f }),
        Player(30006, "dps", "fire_mage", { 12.0f, -30.0f, 210.0f }),
        Player(30007, "dps", "fire_mage", { 0.0f, -10.0f, 210.0f }),
        Player(30008, "dps", "affliction_warlock", { 0.0f, -12.0f, 210.0f }),
        Player(30009, "dps", "marksmanship_hunter", { 12.0f, -30.0f, 210.0f }),
        Player(30010, "dps", "elemental_shaman", { 0.0f, -14.0f, 210.0f }) };

    ActorSnapshot boss = Creature(AdaptiveMagmawStrategy::BossEntry, 39,
        { 0.0f, 0.0f, 210.0f });
    boss.VictimGuid = PlayerGuid(30001);
    board.Hostiles = { boss, Parasite(9001, { 12.0f, -26.0f, 210.0f }) };
    return board;
}

static BotNativeAction::Move const* MoveOf(AdaptiveMagmawPlan const& plan)
{
    return plan.Movement
        ? std::get_if<Move>(&plan.Movement->Action) : nullptr;
}

static BotMovementArbitration::Scope MovementScope(Blackboard const& board)
{
    return {
        board.CurrentScope.AttemptId,
        board.CurrentScope.WipeGeneration,
        board.CurrentScope.RouteGeneration,
        board.CurrentScope.MapId,
        board.CurrentScope.InstanceId };
}

static BotMovementArbitration::Request MovementRequest(
    Blackboard const& board, Move const& move, uint64 expiresAtMs)
{
    return {
        BotMovementArbitration::Owner::Hazard,
        BotMovementArbitration::Priority::Hazard,
        expiresAtMs,
        MovementScope(board),
        move.X, move.Y, move.Z, 0 };
}

static BotWorldMovement::NativePathProofObservation PathProof(
    Vector3 const& requested, bool endpointMatched,
    BotWorldMovement::NativePathFloorFailure floorFailure)
{
    BotWorldMovement::NativePathProofObservation proof;
    proof.Available = true;
    proof.Calculated = true;
    proof.PathType = 1;
    proof.Complete = true;
    proof.EndpointX = requested.X;
    proof.EndpointY = requested.Y;
    proof.EndpointZ = endpointMatched ? requested.Z : -86.0458f;
    proof.EndpointHorizontalDistance = 0.0f;
    proof.EndpointVerticalDistance = endpointMatched ? 0.0f
        : std::fabs(-86.0458f - requested.Z);
    proof.EndpointDistance = proof.EndpointVerticalDistance;
    proof.EndpointMatched = BotWorldMovement::NativePathEndpointComponentsMatch(
        0.0f, endpointMatched ? 0.0f
                              : std::fabs(-86.0458f - requested.Z));
    proof.EndpointFloorValid = true;
    proof.FloorObservation = BotWorldMovement::MakeNativePathFloorObservation(
        floorFailure, 0, 1, requested.X, requested.Y, requested.Z,
        endpointMatched ? requested.Z : -86.0458f, requested.Z);
    proof.FloorObservationConflict = floorFailure
        == BotWorldMovement::NativePathFloorFailure::SampleFloorGap
        || floorFailure
            == BotWorldMovement::NativePathFloorFailure::SampleFloorUnavailable;
    proof.Accepted = BotWorldMovement::NativePathProofPassesAdmission(proof);
    return proof;
}

static BotActionArbitration::Outcome ObserveNativePathAttempt(
    BotWorldMovement::NativePathProofObservation const& proof)
{
    if (char const* failure = BotWorldMovement::NativePathProofFailureReason(
            proof))
        return BotActionArbitration::Outcome::Retryable(failure);
    return BotActionArbitration::Outcome::Started(
        "native_movement_submitted");
}

static void SubmitMovementThroughProductionAdapter(
    BotActionArbitration::Kernel& kernel,
    BotNativeAction::Candidate const& native,
    Blackboard const& board,
    BotWorldMovement::NativePathProofObservation const& proof,
    bool& nativeAttempted)
{
    MagmawMovementIntentCollection movements;
    movements.Propose(MagmawMovementProposalOrigin::Hazard, native);
    MagmawMovementKernelAdapterContext context;
    context.ObservedAtMs = board.ObservedAtMs;
    context.Execute = [&nativeAttempted, proof](
        BotNativeAction::Intent const& intent, MagmawMovementNativeLease lease,
        BotWorldMovement::ExecutionObservation* movement)
    {
        assert(std::get_if<Move>(&intent));
        assert(lease.Owner == BotMovementArbitration::Owner::Hazard);
        assert(!movement);
        nativeAttempted = true;
        return ObserveNativePathAttempt(proof);
    };
    assert(SubmitMagmawMovementKernelCandidates(kernel, movements,
        std::move(context)) == 1);
}

static BotActionArbitration::Candidate ProfileCandidate(
    MagmawParasiteCombatContract::ProfileParameters const& parameters,
    bool areaDamage, bool multidot, bool chained,
    bool petAreaDamage, bool persistentAreaDamage, uint64 expiresAtMs,
    char const* key)
{
    BotActionArbitration::Candidate candidate;
    candidate.Key = key;
    candidate.Source = "db_class_spec_profile";
    candidate.ActionPriority = BotActionArbitration::Priority::TrainedDamage;
    candidate.UtilityScore = 1.0f;
    candidate.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::GlobalCooldown,
        BotActionArbitration::Resource::Cast,
        BotActionArbitration::Resource::Target);
    candidate.ExpiresAtMs = expiresAtMs;
    candidate.Attempt = [parameters, areaDamage, multidot, chained,
        petAreaDamage, persistentAreaDamage]()
    {
        return parameters.AllowsAction(areaDamage, multidot, chained,
                petAreaDamage, persistentAreaDamage)
            ? BotActionArbitration::Outcome::Committed(
                "native_profile_action")
            : BotActionArbitration::Outcome::Unsafe(
                "magmaw_action_contract_forbidden");
    };
    return candidate;
}

static bool Contains(std::vector<std::string> const& values,
    std::string const& value)
{
    return std::find(values.begin(), values.end(), value) != values.end();
}

static bool HasTrace(BotActionArbitration::Resolution const& resolution,
    std::string const& key, std::string const& status,
    std::string const& reason)
{
    for (BotActionArbitration::CandidateTrace const& trace : resolution.Trace)
        if (trace.Key == key && trace.Status == status
            && trace.Reason == reason)
            return true;
    return false;
}

static void AssertContainedTick(Blackboard const& board,
    AdaptiveMagmawPlan const& plan, ObjectGuid actor)
{
    assert(plan.OwnsNode);
    assert(plan.ParasiteCombat.Active);
    assert(plan.ParasiteCombat.FireMageGuid == PlayerGuid(30006));
    assert(plan.ParasiteCombat.MarksmanshipHunterGuid == PlayerGuid(30009));
    assert(!plan.ParasiteCombat.AllowsParasiteTarget(actor,
        ObjectGuid{}));
    assert(plan.ParasiteCombat.TargetAllowed(actor, ObjectGuid{},
        MagmawParasiteCombatContract::BossEntry));
    assert(!plan.ParasiteCombat.TargetAllowed(actor, ObjectGuid{},
        MagmawParasiteCombatContract::ParasiteEntry));
    assert(!plan.ParasiteCombat.AllowsAreaDamageFor(actor));
    assert(!plan.ParasiteCombat.AllowsMultidotFor(actor));
    assert(!plan.ParasiteCombat.AllowsPetAreaDamageFor(actor));
    assert(!plan.ParasiteCombat.AllowsPersistentAreaDamageFor(actor));
    MagmawParasiteCombatContract::ProfileParameters const profile =
        plan.ParasiteCombat.ResolveProfileParameters(actor, ObjectGuid{},
            MagmawParasiteCombatContract::BossEntry,
            false, false, false);
    assert(profile.TargetAllowed);
    assert(profile.ForbidAreaDamage);
    assert(!profile.AllowMultidot);
    // Retained survival movement does not suppress an otherwise legal cast.
    // It only wins when profile execution would need range/LOS movement.
    assert(!profile.DeferCombatRange);
    MagmawParasiteCombatContract::ProfileParameters const parasiteProfile =
        plan.ParasiteCombat.ResolveProfileParameters(actor, ObjectGuid{},
            MagmawParasiteCombatContract::ParasiteEntry,
            false, false, false);
    assert(!parasiteProfile.TargetAllowed);
    assert(!parasiteProfile.AllowsAction(true, true, true, true, true));
    assert(!MoveOf(plan)
        || plan.Movement->Id.Mechanic != "parasite_contact_evade");
    BotActionArbitration::Kernel kernel;
    kernel.Begin(board.ObservedAtMs);
    kernel.Submit(ProfileCandidate(parasiteProfile, true, true, true, true,
        true, board.ObservedAtMs + 500, "unfiltered_magmaw_area_candidate"));
    std::string const profileKey = std::string("z_magmaw_profile_")
        + std::to_string(actor.GetCounter());
    kernel.Submit(ProfileCandidate(profile, false, false, false, false, false,
        board.ObservedAtMs + 500, profileKey.c_str()));
    BotActionArbitration::Resolution const& resolution = kernel.Resolve();
    assert(Contains(resolution.CommittedCandidates, profileKey));
    for (BotActionArbitration::CandidateTrace const& trace : resolution.Trace)
        if (trace.Key == "unfiltered_magmaw_area_candidate")
            assert(trace.Reason == "magmaw_action_contract_forbidden");
}

int main()
{
    AdaptiveMagmawStrategy strategy;
    Blackboard board = BuildBoard();
    MagmawLaneTransitionState transition;

    // (1) Exact ten-roster selection carries the containment contract into
    // action filtering while movement and a legal profile action coexist.
    Blackboard contact = board;
    contact.Hostiles[1] = Parasite(9001, { 12.0f, -26.0f, 210.0f });
    AdaptiveMagmawPlan tankPlan = strategy.Propose(contact, PlayerGuid(30001),
        "tank", nullptr, false, false, &transition);
    AdaptiveMagmawPlan nonbaitMagePlan = strategy.Propose(contact,
        PlayerGuid(30007), "dps", nullptr, false, false, &transition);
    assert(tankPlan.DamageTarget == contact.Hostiles.front().Guid);
    assert(nonbaitMagePlan.DamageTarget == contact.Hostiles.front().Guid);
    AssertContainedTick(contact, tankPlan, PlayerGuid(30001));
    AssertContainedTick(contact, nonbaitMagePlan, PlayerGuid(30007));

    // (2) At the exact generic lease boundary and at +1ms, the typed hazard
    // request is still admissible. A rejected native path keeps its identity
    // and destination; combat-range movement is hard-masked by the contract.
    Blackboard retryBoard = board;
    retryBoard.Players[5].Position = {
        -307.531f, -35.4375f, 211.218f };
    retryBoard.Hostiles[1] = Parasite(9001, {
        -302.1054f, -39.9491f, 211.218f });
    retryBoard.ObservedAtMs = 200000;
    Vector3 const requestedDestination{
        -325.259f, -20.696f, 211.218f };
    float const requestedDistance = std::hypot(
        requestedDestination.X - retryBoard.Players[5].Position.X,
        requestedDestination.Y - retryBoard.Players[5].Position.Y);
    assert(requestedDistance > 23.05f && requestedDistance < 23.06f);
    assert(!BotWorldMovement::AllowsSameLevelLocalMechanicProgress(
        BotMovementArbitration::Owner::Hazard, true, 23.05f, false, false));
    assert(BotWorldMovement::AllowsSameLevelLocalMechanicProgress(
        BotMovementArbitration::Owner::Hazard, true, 23.05f, false, false,
        true));
    assert(!BotWorldMovement::AllowsSameLevelLocalMechanicProgress(
        BotMovementArbitration::Owner::Hazard, true, 25.01f, false, false,
        true));
    MagmawParasiteHazardState retryHazard;
    // seq536 already retained this exact native destination before the
    // seq537 proof. Seed the production value state as that observation
    // boundary; the following strategy ticks must not replan it.
    retryHazard.ObserveScope(retryBoard, PlayerGuid(30006));
    retryHazard.Begin(retryBoard.Hostiles[1].Guid, requestedDestination);
    BotMovementArbitration::Lease expiredLease;
    expiredLease.MovementOwner = BotMovementArbitration::Owner::Hazard;
    expiredLease.MovementPriority = BotMovementArbitration::Priority::Hazard;
    expiredLease.ExpiresAtMs = retryBoard.ObservedAtMs;
    expiredLease.MovementScope = MovementScope(retryBoard);
    AdaptiveMagmawPlan firstRetry = strategy.Propose(retryBoard,
        PlayerGuid(30006), "dps", &expiredLease, false, false, &transition,
        &retryHazard);
    Move const* firstMove = MoveOf(firstRetry);
    assert(firstMove);
    Vector3 const firstDestination{ firstMove->X, firstMove->Y, firstMove->Z };
    assert(firstDestination.X == requestedDestination.X);
    assert(firstDestination.Y == requestedDestination.Y);
    assert(firstDestination.Z == requestedDestination.Z);
    uint64 const firstEvent = firstRetry.Movement->Id.EventGeneration;
    assert(firstRetry.Movement->Id.Actor == PlayerGuid(30006));
    BotMovementArbitration::Request const firstRequest = MovementRequest(
        retryBoard, *firstMove, firstRetry.Movement->ExpiresAtMs);
    assert(BotMovementArbitration::Evaluate(expiredLease, firstRequest,
        retryBoard.ObservedAtMs) == BotMovementArbitration::Decision::Acquire);
    assert(BotMovementArbitration::Evaluate(expiredLease, firstRequest,
        retryBoard.ObservedAtMs + 1)
        == BotMovementArbitration::Decision::Acquire);

    BotActionArbitration::Kernel rejectedTick;
    rejectedTick.Begin(retryBoard.ObservedAtMs);
    BotWorldMovement::NativePathProofObservation const rejectedProof =
        PathProof(requestedDestination, false,
            BotWorldMovement::NativePathFloorFailure::SampleFloorGap);
    assert(rejectedProof.EndpointZ == -86.0458f);
    assert(rejectedProof.EndpointVerticalDistance > 297.2f);
    assert(rejectedProof.FloorObservation.Failure
        == BotWorldMovement::NativePathFloorFailure::SampleFloorGap);
    assert(rejectedProof.FloorObservationConflict);
    assert(!BotWorldMovement::NativePathFloorObservationBlocksCompleteProof(
        rejectedProof.FloorObservation));
    bool rejectedNativeAttempted = false;
    SubmitMovementThroughProductionAdapter(rejectedTick, *firstRetry.Movement,
        retryBoard, rejectedProof, rejectedNativeAttempted);
    BotActionArbitration::Candidate combatRange;
    combatRange.Key = "world.profile_combat_range";
    combatRange.Source = "db_class_spec_profile";
    combatRange.ActionPriority = BotActionArbitration::Priority::CombatMovement;
    combatRange.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::Movement);
    combatRange.ExpiresAtMs = retryBoard.ObservedAtMs + 500;
    MagmawParasiteCombatContract::ProfileParameters const retryProfile =
        firstRetry.ParasiteCombat.ResolveProfileParameters(PlayerGuid(30006),
            ObjectGuid{},
            MagmawParasiteCombatContract::BossEntry,
            retryHazard.HasRetainedIntent(), true, false);
    assert(!retryProfile.ForbidAreaDamage);
    assert(retryProfile.AllowMultidot);
    assert(retryProfile.TargetAllowed);
    assert(retryProfile.DeferCombatRange);
    combatRange.Allowed = !retryProfile.DeferCombatRange;
    combatRange.RejectReason = "magmaw_hazard_movement_retry";
    bool combatRangeRan = false;
    combatRange.Attempt = [&combatRangeRan]()
    {
        combatRangeRan = true;
        return BotActionArbitration::Outcome::Started(
            "profile_combat_range_reconciled");
    };
    rejectedTick.Submit(std::move(combatRange));
    BotActionArbitration::Resolution const& rejected = rejectedTick.Resolve();
    assert(!rejected.AnyCommitted);
    assert(rejectedNativeAttempted);
    assert(!combatRangeRan);
    assert(retryHazard.HasRetainedIntent());
    assert(HasTrace(rejected,
        firstRetry.Movement->Id.Key(), "attempted",
        "route_destination_endpoint_mismatch"));
    assert(HasTrace(rejected, "world.profile_combat_range", "hard_masked",
        "magmaw_hazard_movement_retry"));

    Blackboard retry = retryBoard;
    retry.Revision += 1;
    retry.ObservedAtMs += 1;
    // The same danger remains present: a repeated wrong-floor proof must not
    // be treated as progress merely because the observation revision moved.
    retry.Hostiles[1] = Parasite(9001, retryBoard.Hostiles[1].Position);
    AdaptiveMagmawPlan secondRetry = strategy.Propose(retry,
        PlayerGuid(30006), "dps", &expiredLease, false, false, &transition,
        &retryHazard);
    Move const* secondMove = MoveOf(secondRetry);
    assert(secondMove);
    assert(secondRetry.Movement->Id.EventGeneration == firstEvent);
    assert(secondRetry.Movement->Id.Actor == firstRetry.Movement->Id.Actor);
    assert(secondMove->X == firstDestination.X);
    assert(secondMove->Y == firstDestination.Y);
    BotActionArbitration::Kernel repeatedTick;
    repeatedTick.Begin(retry.ObservedAtMs);
    bool repeatedNativeAttempted = false;
    SubmitMovementThroughProductionAdapter(repeatedTick,
        *secondRetry.Movement, retry, rejectedProof,
        repeatedNativeAttempted);
    BotActionArbitration::Resolution const& repeated = repeatedTick.Resolve();
    assert(!repeated.AnyCommitted);
    assert(repeatedNativeAttempted);
    assert(HasTrace(repeated,
        secondRetry.Movement->Id.Key(), "attempted",
        "route_destination_endpoint_mismatch"));

    // The existing deterministic 12-yard same-floor search is admitted only
    // for this typed bounded hazard. Its verified local alternative is safe,
    // makes progress toward the retained destination, and is not that old
    // endpoint, so safety observation clears the retained intent afterward.
    float const dx = requestedDestination.X
        - retry.Players[5].Position.X;
    float const dy = requestedDestination.Y
        - retry.Players[5].Position.Y;
    Vector3 const localSafe{
        retry.Players[5].Position.X + dx / requestedDistance * 12.0f,
        retry.Players[5].Position.Y + dy / requestedDistance * 12.0f,
        retry.Players[5].Position.Z };
    assert(MagmawParasiteHazardState::Distance2d(localSafe,
        retry.Hostiles[1].Position) >= MagmawParasitePolicy::SafeClearance);
    assert(MagmawParasiteHazardState::Distance2d(localSafe,
        firstDestination) > MagmawParasitePolicy::DestinationTolerance);
    BotNativeAction::Candidate localIntent = *secondRetry.Movement;
    localIntent.Action = Move{ localSafe.X, localSafe.Y, localSafe.Z,
        "parasite_contact_evade" };
    BotActionArbitration::Kernel localTick;
    localTick.Begin(retry.ObservedAtMs + 1);
    bool localNativeAttempted = false;
    SubmitMovementThroughProductionAdapter(localTick, localIntent, retry,
        PathProof(localSafe, true,
            BotWorldMovement::NativePathFloorFailure::None),
        localNativeAttempted);
    BotActionArbitration::Resolution const& local = localTick.Resolve();
    assert(local.AnyCommitted);
    assert(localNativeAttempted);
    assert(localIntent.Id.Actor == firstRetry.Movement->Id.Actor);
    assert(localIntent.Id.EventGeneration == firstEvent);

    Blackboard safe = retry;
    safe.Revision += 1;
    safe.ObservedAtMs += 1;
    safe.Players[5].Position = localSafe;
    AdaptiveMagmawPlan safePlan = strategy.Propose(safe,
        PlayerGuid(30006), "dps", &expiredLease, false, false, &transition,
        &retryHazard);
    assert(!retryHazard.HasRetainedIntent());
    assert(safePlan.OwnsNode);

    // (3) The fixed 30006/30009 lane remains one identity across GUID churn,
    // midpoint observation, pillar preemption/resume, arrival, next event,
    // and wipe reset. The old lane fixture remains a separate replay.
    Blackboard laneBoard = board;
    MagmawLaneTransitionState lane;
    AdaptiveMagmawPlan laneMage = strategy.Propose(laneBoard,
        PlayerGuid(30006), "dps", &expiredLease, false, false, &lane);
    AdaptiveMagmawPlan laneHunter = strategy.Propose(laneBoard,
        PlayerGuid(30009), "dps", &expiredLease, false, false, &lane);
    Move const* laneMove = MoveOf(laneMage);
    assert(laneMove);
    Vector3 const laneDestination{ laneMove->X, laneMove->Y, laneMove->Z };
    uint64 const laneId = lane.TransitionId;
    MagmawLaneTransitionState::Direction const laneDirection = lane.Lane;
    assert(lane.MageGuid == PlayerGuid(30006));
    assert(lane.HunterGuid == PlayerGuid(30009));
    assert(laneHunter.Movement);

    Blackboard midpoint = laneBoard;
    midpoint.Revision += 1;
    midpoint.ObservedAtMs += 1000;
    midpoint.Hostiles[1] = Parasite(9010, { 0.0f, -30.0f, 210.0f });
    midpoint.Players[5].Position = { 0.0f, -30.0f, 210.0f };
    midpoint.Players[8].Position = { 0.0f, -30.0f, 210.0f };
    AdaptiveMagmawPlan midpointMage = strategy.Propose(midpoint,
        PlayerGuid(30006), "dps", &expiredLease, false, true, &lane);
    assert(MoveOf(midpointMage));
    assert(lane.TransitionId == laneId);
    assert(lane.Lane == laneDirection);
    assert(MoveOf(midpointMage)->X == laneDestination.X);
    assert(MoveOf(midpointMage)->Y == laneDestination.Y);

    Blackboard pillar = midpoint;
    pillar.Revision += 1;
    pillar.Players[5].Position = { laneDestination.X - 8.0f,
        laneDestination.Y, laneDestination.Z };
    pillar.Summons = { Creature(AdaptiveMagmawStrategy::PillarEntry, 800,
        laneDestination) };
    AdaptiveMagmawPlan pillarPlan = strategy.Propose(pillar,
        PlayerGuid(30006), "dps", nullptr, false, false, &lane);
    assert(pillarPlan.Movement);
    assert(pillarPlan.Movement->Id.Mechanic == "pillar_evade");
    assert(lane.Preempted);
    assert(lane.TransitionId == laneId);
    assert(lane.Destination.X == laneDestination.X);
    assert(lane.Destination.Y == laneDestination.Y);

    Blackboard resumed = midpoint;
    resumed.Revision += 2;
    AdaptiveMagmawPlan resumedPlan = strategy.Propose(resumed,
        PlayerGuid(30006), "dps", &expiredLease, false, true, &lane);
    assert(MoveOf(resumedPlan));
    assert(!lane.Preempted);
    assert(lane.TransitionId == laneId);
    assert(MoveOf(resumedPlan)->X == laneDestination.X);
    assert(MoveOf(resumedPlan)->Y == laneDestination.Y);

    // Canary117's repeated-contact boundary must survive the complete native
    // admission bridge.  After one retained local preemption clears, the same
    // wave redirects both baiters to one opposite lane endpoint and submits
    // that endpoint under the shared transition identity.
    MagmawLaneTransitionState repeatedLane = lane;
    MagmawParasiteHazardState repeatedHazard;
    Blackboard endpointThreat = resumed;
    endpointThreat.Revision += 1;
    endpointThreat.Players[5].Position = {
        laneDestination.X + 4.0f, laneDestination.Y, laneDestination.Z };
    endpointThreat.Hostiles[1] = Parasite(9010, laneDestination);
    AdaptiveMagmawPlan localEscape = strategy.Propose(endpointThreat,
        PlayerGuid(30006), "dps", &expiredLease, false, false,
        &repeatedLane, &repeatedHazard);
    assert(MoveOf(localEscape));
    assert(repeatedHazard.HasRetainedIntent());

    Blackboard temporaryClear = endpointThreat;
    temporaryClear.Revision += 1;
    temporaryClear.Hostiles[1] = Parasite(
        9010, { 0.0f, -80.0f, 210.0f });
    AdaptiveMagmawPlan cleared = strategy.Propose(temporaryClear,
        PlayerGuid(30006), "dps", &expiredLease, false, false,
        &repeatedLane, &repeatedHazard);
    assert(!repeatedHazard.HasRetainedIntent());
    assert(!cleared.Movement);

    Blackboard repeatedContact = temporaryClear;
    repeatedContact.Revision += 1;
    repeatedContact.Hostiles[1] = Parasite(
        9010, repeatedContact.Players[5].Position);
    AdaptiveMagmawPlan redirected = strategy.Propose(repeatedContact,
        PlayerGuid(30006), "dps", &expiredLease, false, false,
        &repeatedLane, &repeatedHazard);
    Move const* redirectedMove = MoveOf(redirected);
    assert(redirectedMove);
    assert(repeatedLane.TransitionId != laneId);
    assert(repeatedLane.Lane != laneDirection);
    assert(redirectedMove->X == -laneDestination.X);
    assert(redirectedMove->Y == laneDestination.Y);
    assert(redirected.Movement->Id.EventGeneration
        == repeatedLane.TransitionId);

    BotActionArbitration::Kernel redirectedTick;
    redirectedTick.Begin(repeatedContact.ObservedAtMs);
    bool redirectedNativeAttempted = false;
    SubmitMovementThroughProductionAdapter(redirectedTick,
        *redirected.Movement, repeatedContact,
        PathProof({ redirectedMove->X, redirectedMove->Y, redirectedMove->Z },
            true, BotWorldMovement::NativePathFloorFailure::None),
        redirectedNativeAttempted);
    BotActionArbitration::Resolution const& redirectedResolution =
        redirectedTick.Resolve();
    assert(redirectedResolution.AnyCommitted);
    assert(redirectedNativeAttempted);

    AdaptiveMagmawPlan redirectedHunter = strategy.Propose(repeatedContact,
        PlayerGuid(30009), "dps", &expiredLease, false, false,
        &repeatedLane);
    assert(MoveOf(redirectedHunter));
    assert(MoveOf(redirectedHunter)->X == redirectedMove->X);
    assert(MoveOf(redirectedHunter)->Y == redirectedMove->Y);

    Blackboard arrived = resumed;
    arrived.Revision += 1;
    arrived.Hostiles.resize(1);
    arrived.Players[5].Position = laneDestination;
    arrived.Players[8].Position = laneDestination;
    strategy.Propose(arrived, PlayerGuid(30006), "dps", nullptr, false,
        false, &lane);
    strategy.Propose(arrived, PlayerGuid(30009), "dps", nullptr, false,
        false, &lane);
    assert(lane.IsArrived());
    assert(lane.ArrivalGenerationCaptured);
    assert(lane.ArrivedGeneration == 0);
    assert(lane.ArrivedMechanicKind == 0);
    uint64 const arrivedId = lane.TransitionId;

    Blackboard nextEvent = arrived;
    nextEvent.Revision += 1;
    nextEvent.Hostiles.push_back(Parasite(9011, { 0.0f, -80.0f, 210.0f }));
    AdaptiveMagmawPlan nextLane = strategy.Propose(nextEvent,
        PlayerGuid(30006), "dps", nullptr, false, false, &lane);
    assert(MoveOf(nextLane));
    assert(lane.TransitionId != arrivedId);
    assert(lane.Lane != laneDirection);
    assert(MoveOf(nextLane)->X != laneDestination.X
        || MoveOf(nextLane)->Y != laneDestination.Y);

    Blackboard wiped = nextEvent;
    wiped.CurrentScope.WipeGeneration += 1;
    wiped.Revision += 1;
    wiped.Hostiles[1] = Parasite(9012, { 12.0f, -26.0f, 210.0f });
    wiped.Players[5].Position = { 12.0f, -30.0f, 210.0f };
    AdaptiveMagmawPlan wipedLane = strategy.Propose(wiped,
        PlayerGuid(30006), "dps", nullptr, false, false, &lane);
    assert(MoveOf(wipedLane));
    assert(lane.WipeGeneration == wiped.CurrentScope.WipeGeneration);
    assert(lane.TransitionId == 1);

    // (4) A non-bait DPS stays on Magmaw for a remote parasite, but may
    // attack its exact pursuer and emit one actor-owned local Survival move.
    Blackboard threatened = board;
    threatened.Revision += 20;
    threatened.ObservedAtMs += 20000;
    threatened.Hostiles[1] = Parasite(9100,
        { 0.0f, -23.0f, 210.0f });
    threatened.Hostiles[1].VictimGuid = PlayerGuid(30008);
    MagmawLaneTransitionState nonownerLane;
    MagmawParasiteHazardState nonownerHazard;
    AdaptiveMagmawPlan threatenedPlan = strategy.Propose(threatened,
        PlayerGuid(30008), "dps", nullptr, false, false, &nonownerLane,
        &nonownerHazard);
    assert(threatenedPlan.DamageTarget == threatened.Hostiles[1].Guid);
    assert(threatenedPlan.ParasiteCombat.PersonalThreatGuid
        == threatened.Hostiles[1].Guid);
    assert(MoveOf(threatenedPlan));
    assert(threatenedPlan.Movement->Id.Mechanic
        == "parasite_contact_evade");
    assert(threatenedPlan.Movement->Id.Actor == PlayerGuid(30008));
    assert(!nonownerLane.Committed);
    assert(!nonownerLane.IsBaiter(PlayerGuid(30008)));
    MagmawParasiteCombatContract::ProfileParameters const threatProfile =
        threatenedPlan.ParasiteCombat.ResolveProfileParameters(
            PlayerGuid(30008), threatened.Hostiles[1].Guid,
            MagmawParasiteCombatContract::ParasiteEntry, true, false, false);
    assert(threatProfile.TargetAllowed);
    assert(threatProfile.AllowsAction(false, false, false, false, false));
    assert(!threatenedPlan.ParasiteCombat.TargetAllowed(PlayerGuid(30008),
        ObjectGuid(HighGuid::Unit,
            MagmawParasiteCombatContract::ParasiteEntry, uint32(9199)),
        MagmawParasiteCombatContract::ParasiteEntry));
    assert(!threatenedPlan.ParasiteCombat.TargetAllowed(PlayerGuid(30007),
        threatened.Hostiles[1].Guid,
        MagmawParasiteCombatContract::ParasiteEntry));

    BotActionArbitration::Kernel threatenedTick;
    threatenedTick.Begin(threatened.ObservedAtMs);
    bool threatenedNativeAttempted = false;
    SubmitMovementThroughProductionAdapter(threatenedTick,
        *threatenedPlan.Movement, threatened,
        PathProof({ MoveOf(threatenedPlan)->X, MoveOf(threatenedPlan)->Y,
            MoveOf(threatenedPlan)->Z }, true,
            BotWorldMovement::NativePathFloorFailure::None),
        threatenedNativeAttempted);
    threatenedTick.Submit(ProfileCandidate(threatProfile, false, false,
        false, false, false, threatened.ObservedAtMs + 500,
        "personally_threatened_profile"));
    BotActionArbitration::Resolution const& threatenedResolution =
        threatenedTick.Resolve();
    assert(threatenedNativeAttempted);
    assert(Contains(threatenedResolution.CommittedCandidates,
        threatenedPlan.Movement->Id.Key()));
    assert(Contains(threatenedResolution.CommittedCandidates,
        "personally_threatened_profile"));

    // Replacing the parasite GUID inside the same unsafe episode neither
    // changes the actor-owned key nor replans the local destination.
    Blackboard guidChurn = threatened;
    guidChurn.Revision += 1;
    guidChurn.ObservedAtMs += 100;
    guidChurn.Hostiles[1] = Parasite(9101,
        threatened.Hostiles[1].Position);
    guidChurn.Hostiles[1].VictimGuid = PlayerGuid(30008);
    AdaptiveMagmawPlan churnPlan = strategy.Propose(guidChurn,
        PlayerGuid(30008), "dps", nullptr, false, false, &nonownerLane,
        &nonownerHazard);
    assert(MoveOf(churnPlan));
    assert(churnPlan.Movement->Id.Key()
        == threatenedPlan.Movement->Id.Key());
    assert(MoveOf(churnPlan)->X == MoveOf(threatenedPlan)->X);
    assert(MoveOf(churnPlan)->Y == MoveOf(threatenedPlan)->Y);
    assert(!nonownerLane.Committed);

    // A rejected native result fails closed while retaining the same episode.
    BotActionArbitration::Kernel failedThreatTick;
    failedThreatTick.Begin(guidChurn.ObservedAtMs);
    bool failedThreatAttempted = false;
    SubmitMovementThroughProductionAdapter(failedThreatTick,
        *churnPlan.Movement, guidChurn,
        PathProof({ MoveOf(churnPlan)->X, MoveOf(churnPlan)->Y,
            MoveOf(churnPlan)->Z }, false,
            BotWorldMovement::NativePathFloorFailure::SampleFloorGap),
        failedThreatAttempted);
    BotActionArbitration::Resolution const& failedThreatResolution =
        failedThreatTick.Resolve();
    assert(failedThreatAttempted);
    assert(!failedThreatResolution.AnyCommitted);
    assert(nonownerHazard.HasRetainedIntent());
    assert(HasTrace(failedThreatResolution, churnPlan.Movement->Id.Key(),
        "attempted", "route_destination_endpoint_mismatch"));

    // The exposed head remains first even while a parasite pursues the actor.
    Blackboard exposed = threatened;
    exposed.Revision += 2;
    exposed.Hostiles.push_back(Creature(
        AdaptiveMagmawStrategy::HeadEntry, 9200,
        { 0.0f, -2.0f, 210.0f }));
    MagmawParasiteHazardState exposedHazard;
    AdaptiveMagmawPlan exposedPlan = strategy.Propose(exposed,
        PlayerGuid(30008), "dps", nullptr, false, false, &nonownerLane,
        &exposedHazard);
    assert(exposedPlan.DamageTarget == exposed.Hostiles.back().Guid);

    // Fixed baiters retain their broader parasite contract; safe nonowners
    // retain boss targeting and never acquire a bait-lane transition.
    MagmawParasiteCombatContract const contract = tankPlan.ParasiteCombat;
    MagmawParasiteCombatContract::ProfileParameters const baitMageProfile =
        contract.ResolveProfileParameters(PlayerGuid(30006),
            board.Hostiles[1].Guid,
            MagmawParasiteCombatContract::ParasiteEntry, false, false, false);
    MagmawParasiteCombatContract::ProfileParameters const baitHunterProfile =
        contract.ResolveProfileParameters(PlayerGuid(30009),
            board.Hostiles[1].Guid,
            MagmawParasiteCombatContract::ParasiteEntry, false, false, false);
    assert(baitMageProfile.TargetAllowed && !baitMageProfile.ForbidAreaDamage
        && baitMageProfile.AllowMultidot);
    assert(baitHunterProfile.TargetAllowed
        && !baitHunterProfile.ForbidAreaDamage
        && baitHunterProfile.AllowMultidot);
    MagmawLaneTransitionState safeNonownerLane;
    MagmawParasiteHazardState safeNonownerHazard;
    AdaptiveMagmawPlan safeNonowner = strategy.Propose(board,
        PlayerGuid(30008), "dps", nullptr, false, false,
        &safeNonownerLane, &safeNonownerHazard);
    assert(safeNonowner.DamageTarget == board.Hostiles.front().Guid);
    assert(!safeNonownerLane.Committed);
    assert(!MoveOf(safeNonowner)
        || safeNonowner.Movement->Id.Mechanic
            != "parasite_contact_evade");
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
            "-I",
            str(ROOT / "src/common/Debugging"),
            str(source),
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
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)
