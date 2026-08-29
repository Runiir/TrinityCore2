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
#include <algorithm>
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
#include "Bots/BotWorldPopulationMgrNativeFloor.h"
#include "Bots/BotWorldPopulationMgrMovement.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <functional>
#include <string>

using namespace BotEncounter;
using BotNativeAction::Move;

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

static BotActionArbitration::Outcome SubmitNativePath(
    BotMovementArbitration::NativePathReceipt& receipt,
    BotMovementArbitration::Request const& request, uint64 nowMs,
    BotWorldMovement::NativePathProofObservation const& proof)
{
    if (char const* failure = BotWorldMovement::NativePathProofFailureReason(
            proof))
        return BotActionArbitration::Outcome::Retryable(failure);
    if (BotMovementArbitration::Evaluate(receipt.Path, request, nowMs)
            == BotMovementArbitration::Decision::RejectInvalid)
        return BotActionArbitration::Outcome::Unsafe(
            "movement_request_invalid");
    BotMovementArbitration::Apply(receipt.Path, request);
    receipt.Active = true;
    return BotActionArbitration::Outcome::Started(
        "native_movement_submitted");
}

static BotActionArbitration::Candidate NativeCandidate(
    BotNativeAction::Candidate const& native,
    BotMovementArbitration::NativePathReceipt& receipt,
    Blackboard const& board,
    BotWorldMovement::NativePathProofObservation const& proof)
{
    Move const* move = std::get_if<Move>(&native.Action);
    assert(move);
    BotActionArbitration::Candidate candidate;
    candidate.Key = std::string("magmaw_native:")
        + std::to_string(native.Id.Actor.GetCounter()) + ":"
        + std::to_string(native.Id.EventGeneration);
    candidate.Source = native.Id.Strategy;
    candidate.ActionPriority = native.ActionPriority;
    candidate.UtilityScore = native.Utility;
    candidate.RequiredResources = native.Resources();
    candidate.ExpiresAtMs = native.ExpiresAtMs;
    BotMovementArbitration::Request const request = MovementRequest(board,
        *move, native.ExpiresAtMs);
    candidate.Attempt = [&, request, proof]()
    {
        return SubmitNativePath(receipt, request, board.ObservedAtMs, proof);
    };
    return candidate;
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
    AdaptiveMagmawPlan const& plan, ObjectGuid actor,
    MagmawParasiteHazardState& hazardState)
{
    assert(plan.OwnsNode);
    assert(plan.ParasiteCombat.Active);
    assert(plan.ParasiteCombat.FireMageGuid == PlayerGuid(30006));
    assert(plan.ParasiteCombat.MarksmanshipHunterGuid == PlayerGuid(30009));
    assert(!plan.ParasiteCombat.AllowsParasiteTarget(actor));
    assert(plan.ParasiteCombat.TargetAllowed(actor,
        MagmawParasiteCombatContract::BossEntry));
    assert(!plan.ParasiteCombat.TargetAllowed(actor,
        MagmawParasiteCombatContract::ParasiteEntry));
    assert(!plan.ParasiteCombat.AllowsAreaDamageFor(actor));
    assert(!plan.ParasiteCombat.AllowsMultidotFor(actor));
    assert(!plan.ParasiteCombat.AllowsPetAreaDamageFor(actor));
    assert(!plan.ParasiteCombat.AllowsPersistentAreaDamageFor(actor));
    MagmawParasiteCombatContract::ProfileParameters const profile =
        plan.ParasiteCombat.ResolveProfileParameters(actor,
            MagmawParasiteCombatContract::BossEntry,
            hazardState.HasRetainedIntent(), false, false);
    assert(profile.TargetAllowed);
    assert(profile.ForbidAreaDamage);
    assert(!profile.AllowMultidot);
    // Retained survival movement does not suppress an otherwise legal cast.
    // It only wins when profile execution would need range/LOS movement.
    assert(!profile.DeferCombatRange);
    MagmawParasiteCombatContract::ProfileParameters const parasiteProfile =
        plan.ParasiteCombat.ResolveProfileParameters(actor,
            MagmawParasiteCombatContract::ParasiteEntry,
            hazardState.HasRetainedIntent(), false, false);
    assert(!parasiteProfile.TargetAllowed);
    assert(!parasiteProfile.AllowsAction(true, true, true, true, true));
    assert(!MoveOf(plan) || plan.DamageTarget.GetRawValue());

    Move const* move = MoveOf(plan);
    assert(move);
    BotMovementArbitration::NativePathReceipt receipt;
    BotActionArbitration::Kernel kernel;
    kernel.Begin(board.ObservedAtMs);
    BotNativeAction::Candidate const& native = *plan.Movement;
    std::string const movementKey = std::string("magmaw_native:")
        + std::to_string(native.Id.Actor.GetCounter()) + ":"
        + std::to_string(native.Id.EventGeneration);
    Move const containedDestination{ move->X, move->Y, move->Z,
        move->IntentReason };
    kernel.Submit(NativeCandidate(native, receipt, board,
        PathProof({ containedDestination.X, containedDestination.Y,
            containedDestination.Z }, true,
            BotWorldMovement::NativePathFloorFailure::None)));
    kernel.Submit(ProfileCandidate(parasiteProfile, true, true, true, true,
        true, board.ObservedAtMs + 500, "unfiltered_magmaw_area_candidate"));
    std::string const profileKey = std::string("z_magmaw_profile_")
        + std::to_string(actor.GetCounter());
    kernel.Submit(ProfileCandidate(profile, false, false, false, false, false,
        board.ObservedAtMs + 500, profileKey.c_str()));
    BotActionArbitration::Resolution const& resolution = kernel.Resolve();
    assert(Contains(resolution.CommittedCandidates, movementKey));
    assert(Contains(resolution.CommittedCandidates, profileKey));
    assert(receipt.Active);
    assert(hazardState.HasRetainedIntent());
    for (BotActionArbitration::CandidateTrace const& trace : resolution.Trace)
        if (trace.Key == "unfiltered_magmaw_area_candidate")
            assert(trace.Reason == "magmaw_action_contract_forbidden");
}

int main()
{
    AdaptiveMagmawStrategy strategy;
    Blackboard board = BuildBoard();
    MagmawLaneTransitionState transition;
    MagmawParasiteHazardState tankHazard;
    MagmawParasiteHazardState mageHazard;

    // (1) Exact ten-roster selection carries the containment contract into
    // action filtering while movement and a legal profile action coexist.
    Blackboard contact = board;
    contact.Hostiles[1] = Parasite(9001, { 0.0f, -10.0f, 210.0f });
    AdaptiveMagmawPlan tankPlan = strategy.Propose(contact, PlayerGuid(30001),
        "tank", nullptr, false, false, &transition, &tankHazard);
    AdaptiveMagmawPlan nonbaitMagePlan = strategy.Propose(contact,
        PlayerGuid(30007), "dps", nullptr, false, false, &transition,
        &mageHazard);
    assert(tankPlan.DamageTarget == contact.Hostiles.front().Guid);
    assert(nonbaitMagePlan.DamageTarget == contact.Hostiles.front().Guid);
    AssertContainedTick(contact, tankPlan, PlayerGuid(30001), tankHazard);
    AssertContainedTick(contact, nonbaitMagePlan, PlayerGuid(30007),
        mageHazard);

    // (2) At the exact generic lease boundary and at +1ms, the typed hazard
    // request is still admissible. A rejected native path keeps its identity
    // and destination; combat-range movement is hard-masked by the contract.
    Blackboard retryBoard = board;
    retryBoard.Players[0].Position = {
        -307.531f, -35.4375f, 211.218f };
    retryBoard.Hostiles[1] = Parasite(9001, {
        -302.1054f, -39.9491f, 211.218f });
    retryBoard.ObservedAtMs = 200000;
    Vector3 const requestedDestination{
        -325.259f, -20.696f, 211.218f };
    float const requestedDistance = std::hypot(
        requestedDestination.X - retryBoard.Players[0].Position.X,
        requestedDestination.Y - retryBoard.Players[0].Position.Y);
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
    retryHazard.ObserveScope(retryBoard, PlayerGuid(30001));
    retryHazard.Begin(retryBoard.Hostiles[1].Guid, requestedDestination);
    BotMovementArbitration::Lease expiredLease;
    expiredLease.MovementOwner = BotMovementArbitration::Owner::Hazard;
    expiredLease.MovementPriority = BotMovementArbitration::Priority::Hazard;
    expiredLease.ExpiresAtMs = retryBoard.ObservedAtMs;
    expiredLease.MovementScope = MovementScope(retryBoard);
    AdaptiveMagmawPlan firstRetry = strategy.Propose(retryBoard,
        PlayerGuid(30001), "tank", &expiredLease, false, false, &transition,
        &retryHazard);
    Move const* firstMove = MoveOf(firstRetry);
    assert(firstMove);
    Vector3 const firstDestination{ firstMove->X, firstMove->Y, firstMove->Z };
    assert(firstDestination.X == requestedDestination.X);
    assert(firstDestination.Y == requestedDestination.Y);
    assert(firstDestination.Z == requestedDestination.Z);
    uint64 const firstEvent = firstRetry.Movement->Id.EventGeneration;
    BotMovementArbitration::Request const firstRequest = MovementRequest(
        retryBoard, *firstMove, firstRetry.Movement->ExpiresAtMs);
    assert(BotMovementArbitration::Evaluate(expiredLease, firstRequest,
        retryBoard.ObservedAtMs) == BotMovementArbitration::Decision::Acquire);
    assert(BotMovementArbitration::Evaluate(expiredLease, firstRequest,
        retryBoard.ObservedAtMs + 1)
        == BotMovementArbitration::Decision::Acquire);

    BotMovementArbitration::NativePathReceipt rejectedReceipt;
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
    rejectedTick.Submit(NativeCandidate(*firstRetry.Movement,
        rejectedReceipt, retryBoard, rejectedProof));
    BotActionArbitration::Candidate combatRange;
    combatRange.Key = "world.profile_combat_range";
    combatRange.Source = "db_class_spec_profile";
    combatRange.ActionPriority = BotActionArbitration::Priority::CombatMovement;
    combatRange.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::Movement);
    combatRange.ExpiresAtMs = retryBoard.ObservedAtMs + 500;
    MagmawParasiteCombatContract::ProfileParameters const retryProfile =
        firstRetry.ParasiteCombat.ResolveProfileParameters(PlayerGuid(30001),
            MagmawParasiteCombatContract::BossEntry,
            retryHazard.HasRetainedIntent(), true, false);
    assert(retryProfile.ForbidAreaDamage);
    assert(!retryProfile.AllowMultidot);
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
    assert(!combatRangeRan);
    assert(retryHazard.HasRetainedIntent());
    assert(HasTrace(rejected,
        "magmaw_native:9001:1", "attempted",
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
        PlayerGuid(30001), "tank", &expiredLease, false, false, &transition,
        &retryHazard);
    Move const* secondMove = MoveOf(secondRetry);
    assert(secondMove);
    assert(secondRetry.Movement->Id.EventGeneration == firstEvent);
    assert(secondRetry.Movement->Id.Actor == firstRetry.Movement->Id.Actor);
    assert(secondMove->X == firstDestination.X);
    assert(secondMove->Y == firstDestination.Y);
    BotMovementArbitration::NativePathReceipt repeatedReceipt;
    BotActionArbitration::Kernel repeatedTick;
    repeatedTick.Begin(retry.ObservedAtMs);
    repeatedTick.Submit(NativeCandidate(*secondRetry.Movement,
        repeatedReceipt, retry, rejectedProof));
    BotActionArbitration::Resolution const& repeated = repeatedTick.Resolve();
    assert(!repeated.AnyCommitted);
    assert(!repeatedReceipt.Active);
    assert(HasTrace(repeated,
        "magmaw_native:9001:1", "attempted",
        "route_destination_endpoint_mismatch"));
    BotMovementArbitration::Request const secondRequest = MovementRequest(
        retry, *secondMove, secondRetry.Movement->ExpiresAtMs);
    assert(!BotMovementArbitration::MatchesNativePath(repeatedReceipt,
        secondRequest));

    // The existing deterministic 12-yard same-floor search is admitted only
    // for this typed bounded hazard. Its verified local alternative is safe,
    // makes progress toward the retained destination, and is not that old
    // endpoint, so safety observation clears the retained intent afterward.
    float const dx = requestedDestination.X
        - retry.Players[0].Position.X;
    float const dy = requestedDestination.Y
        - retry.Players[0].Position.Y;
    Vector3 const localSafe{
        retry.Players[0].Position.X + dx / requestedDistance * 12.0f,
        retry.Players[0].Position.Y + dy / requestedDistance * 12.0f,
        retry.Players[0].Position.Z };
    assert(MagmawParasiteHazardState::Distance2d(localSafe,
        retry.Hostiles[1].Position) >= MagmawParasitePolicy::SafeClearance);
    assert(MagmawParasiteHazardState::Distance2d(localSafe,
        firstDestination) > MagmawParasitePolicy::DestinationTolerance);
    BotNativeAction::Candidate localIntent = *secondRetry.Movement;
    localIntent.Action = Move{ localSafe.X, localSafe.Y, localSafe.Z,
        "parasite_contact_evade" };
    BotMovementArbitration::NativePathReceipt localReceipt;
    BotActionArbitration::Kernel localTick;
    localTick.Begin(retry.ObservedAtMs + 1);
    localTick.Submit(NativeCandidate(localIntent, localReceipt, retry,
        PathProof(localSafe, true,
            BotWorldMovement::NativePathFloorFailure::None)));
    BotActionArbitration::Resolution const& local = localTick.Resolve();
    assert(local.AnyCommitted);
    BotMovementArbitration::Request const localRequest = MovementRequest(
        retry, std::get<Move>(localIntent.Action), localIntent.ExpiresAtMs);
    assert(BotMovementArbitration::MatchesNativePath(localReceipt,
        localRequest));
    assert(localIntent.Id.Actor == firstRetry.Movement->Id.Actor);
    assert(localIntent.Id.EventGeneration == firstEvent);

    Blackboard safe = retry;
    safe.Revision += 1;
    safe.ObservedAtMs += 1;
    safe.Players[0].Position = localSafe;
    AdaptiveMagmawPlan safePlan = strategy.Propose(safe,
        PlayerGuid(30001), "tank", &expiredLease, false, false, &transition,
        &retryHazard);
    assert(!retryHazard.HasRetainedIntent());
    assert(!safePlan.Movement);
    assert(safePlan.DamageTarget == safe.Hostiles.front().Guid);

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

    BotMovementArbitration::NativePathReceipt redirectedReceipt;
    BotActionArbitration::Kernel redirectedTick;
    redirectedTick.Begin(repeatedContact.ObservedAtMs);
    redirectedTick.Submit(NativeCandidate(*redirected.Movement,
        redirectedReceipt, repeatedContact,
        PathProof({ redirectedMove->X, redirectedMove->Y, redirectedMove->Z },
            true, BotWorldMovement::NativePathFloorFailure::None)));
    BotActionArbitration::Resolution const& redirectedResolution =
        redirectedTick.Resolve();
    assert(redirectedResolution.AnyCommitted);
    assert(redirectedReceipt.Active);

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

    // (4) The exact tank -> non-bait mage -> support infection chain remains
    // outside the production profile bridge; only the fixed pair can affect
    // a parasite target.
    MagmawParasiteCombatContract contract = tankPlan.ParasiteCombat;
    MagmawParasiteCombatContract::ProfileParameters const tankProfile =
        contract.ResolveProfileParameters(PlayerGuid(30001),
            MagmawParasiteCombatContract::ParasiteEntry, false, false, false);
    MagmawParasiteCombatContract::ProfileParameters const mageProfile =
        contract.ResolveProfileParameters(PlayerGuid(30007),
            MagmawParasiteCombatContract::ParasiteEntry, false, false, false);
    MagmawParasiteCombatContract::ProfileParameters const supportProfile =
        contract.ResolveProfileParameters(PlayerGuid(30003),
            MagmawParasiteCombatContract::ParasiteEntry, false, false, false);
    MagmawParasiteCombatContract::ProfileParameters const baitMageProfile =
        contract.ResolveProfileParameters(PlayerGuid(30006),
            MagmawParasiteCombatContract::ParasiteEntry, false, false, false);
    MagmawParasiteCombatContract::ProfileParameters const baitHunterProfile =
        contract.ResolveProfileParameters(PlayerGuid(30009),
            MagmawParasiteCombatContract::ParasiteEntry, false, false, false);
    assert(!tankProfile.TargetAllowed && !mageProfile.TargetAllowed
        && !supportProfile.TargetAllowed);
    assert(!tankProfile.AllowsAction(false, false, false, false, false));
    assert(!mageProfile.AllowsAction(false, false, false, false, false));
    assert(!supportProfile.AllowsAction(false, false, false, false, false));
    assert(baitMageProfile.TargetAllowed && !baitMageProfile.ForbidAreaDamage
        && baitMageProfile.AllowMultidot);
    assert(baitHunterProfile.TargetAllowed
        && !baitHunterProfile.ForbidAreaDamage
        && baitHunterProfile.AllowMultidot);
    assert(!contract.TargetAllowed(PlayerGuid(30001),
        MagmawParasiteCombatContract::ParasiteEntry));
    assert(!contract.TargetAllowed(PlayerGuid(30007),
        MagmawParasiteCombatContract::ParasiteEntry));
    assert(!contract.TargetAllowed(PlayerGuid(30003),
        MagmawParasiteCombatContract::ParasiteEntry));
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
