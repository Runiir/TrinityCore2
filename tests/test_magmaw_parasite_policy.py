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
#include <cassert>
#include <cmath>

using namespace BotEncounter;
using BotNativeAction::Move;

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

    // A non-baiter may perform local contact evasion, but cannot mutate the
    // shared bait transition identity or destination.
    uint64 const stableId = transition.TransitionId;
    Vector3 const stableDestination = transition.Destination;
    Blackboard ordinaryBoard = reset;
    ordinaryBoard.Revision += 1;
    ordinaryBoard.Hostiles[1].Position = ordinaryBoard.Players[3].Position;
    AdaptiveMagmawPlan ordinaryPlan = strategy.Propose(ordinaryBoard, ordinary,
        "dps", nullptr, false, false, &transition);
    assert(ordinaryPlan.Movement);
    assert(ordinaryPlan.Movement->Id.Mechanic == "parasite_contact_evade");
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
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)
