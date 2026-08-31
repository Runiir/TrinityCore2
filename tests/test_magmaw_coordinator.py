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


def test_magmaw_shadow_coordinator_contract(tmp_path: Path) -> None:
    source = tmp_path / "magmaw_coordinator.cpp"
    binary = tmp_path / "magmaw_coordinator"
    source.write_text(r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawCoordinator.h"

#include <algorithm>
#include <cassert>
#include <functional>
#include <string>
#include <vector>

using namespace BotEncounter;
using Slot = MagmawRaidAssignmentSlot;

std::string ObjectGuid::ToString() const
{
    return std::to_string(GetRawValue());
}

static ObjectGuid PlayerGuid(uint32 counter)
{
    return ObjectGuid(HighGuid::Player, counter);
}

static ActorSnapshot Player(uint32 counter, char const* role,
    char const* classSpec)
{
    ActorSnapshot actor;
    actor.Guid = PlayerGuid(counter);
    actor.Kind = ActorKind::Player;
    actor.Role = role;
    actor.ClassSpec = classSpec;
    actor.Alive = true;
    actor.HealthPct = 100.0f;
    return actor;
}

static ActorSnapshot Creature(uint32 entry, uint32 counter)
{
    ActorSnapshot actor;
    actor.Guid = ObjectGuid(HighGuid::Unit, entry, counter);
    actor.Entry = entry;
    actor.Alive = true;
    actor.Attackable = true;
    actor.Selectable = true;
    return actor;
}

static Blackboard Board()
{
    Blackboard board;
    board.CurrentScope.ServerEpoch = 91;
    board.CurrentScope.CohortId = "magmaw-shadow";
    board.CurrentScope.AttemptId = 7;
    board.CurrentScope.WipeGeneration = 2;
    board.CurrentScope.RouteGeneration = 5;
    board.CurrentScope.NodeId = "bwd.magmaw.encounter";
    board.CurrentScope.MapId = 669;
    board.CurrentScope.InstanceId = 23;
    board.CurrentScope.EncounterId = "magmaw";
    board.CurrentScope.EncounterEpoch = 4;
    board.Revision = 10;
    board.ObservedAtMs = 1000;
    board.NativeBossState = "in_progress";
    board.NativeEncounterPhase = "combat";
    board.NativeWipeState = "engaged";
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Route.NavigationHints = { { 0.0f, 0.0f, 210.0f } };
    board.Players = {
        Player(100, "tank", "protection_paladin"),
        Player(101, "tank", "blood_death_knight"),
        Player(200, "healer", "restoration_druid"),
        Player(201, "healer", "holy_paladin"),
        Player(300, "dps", "fire_mage"),
        Player(301, "dps", "fire_mage"),
        Player(400, "dps", "marksmanship_hunter"),
        Player(401, "dps", "marksmanship_hunter"),
        Player(500, "dps", "affliction_warlock"),
        Player(600, "dps", "elemental_shaman") };
    ActorSnapshot boss = Creature(41570, 1);
    boss.InCombat = true;
    boss.VictimGuid = PlayerGuid(100);
    board.Hostiles.push_back(boss);
    return board;
}

static ActorSnapshot& Member(Blackboard& board, uint32 counter)
{
    auto itr = std::find_if(board.Players.begin(), board.Players.end(),
        [counter](ActorSnapshot const& actor)
        {
            return actor.Guid == PlayerGuid(counter);
        });
    assert(itr != board.Players.end());
    return *itr;
}

static std::shared_ptr<MagmawCoordinator const> Reconcile(
    std::shared_ptr<MagmawCoordinator const> const& current,
    Blackboard const& board,
    std::vector<MagmawAssignmentRetirementInput> const& inputs = {})
{
    MagmawFacts const facts = MagmawFactsReducer::Reduce(board);
    return MagmawCoordinator::Reconcile(current, facts, board, inputs);
}

static ObjectGuid Assigned(MagmawRaidPlan const& plan, Slot slot)
{
    return plan.Assignment(slot).AssigneeGuid;
}

static void AssertInitialAndIdempotent()
{
    Blackboard board = Board();
    auto plan = Reconcile(nullptr, board);
    assert(plan->Plan().Authoritative && plan->Plan().Generation == 1);
    assert(Assigned(plan->Plan(), Slot::FireMageBaiter) == PlayerGuid(300));
    assert(Assigned(plan->Plan(), Slot::MarksmanshipHunterBaiter)
        == PlayerGuid(400));
    assert(Assigned(plan->Plan(), Slot::HookOne) == PlayerGuid(300));
    assert(Assigned(plan->Plan(), Slot::HookTwo) == PlayerGuid(301));
    assert(Assigned(plan->Plan(), Slot::MainPullTank) == PlayerGuid(100));
    assert(Assigned(plan->Plan(), Slot::MangleResponder) == PlayerGuid(200));
    assert(Assigned(plan->Plan(), Slot::SemanticLaneOwner)
        == PlayerGuid(300));
    assert(Assigned(plan->Plan(), Slot::BloodlustOwner) == PlayerGuid(600));
    assert(Reconcile(plan, board) == plan);
}

static void AssertPermutationAndRevisionStability()
{
    Blackboard board = Board();
    auto first = Reconcile(nullptr, board);
    std::reverse(board.Players.begin(), board.Players.end());
    ++board.Revision;
    auto second = Reconcile(first, board);
    assert(second != first && second->Plan().SourceRevision == board.Revision);
    assert(second->Plan().Generation == first->Plan().Generation);
    for (size_t index = 0; index < MagmawRaidPlan::AssignmentCount; ++index)
    {
        assert(second->Plan().Assignments[index].AssigneeGuid
            == first->Plan().Assignments[index].AssigneeGuid);
        assert(second->Plan().Assignments[index].Epoch
            == first->Plan().Assignments[index].Epoch);
    }
}

static void AssertScopeRetirement()
{
    using Change = std::function<void(Scope&)>;
    std::vector<Change> changes = {
        [](Scope& scope) { ++scope.ServerEpoch; },
        [](Scope& scope) { scope.CohortId = "other"; },
        [](Scope& scope) { ++scope.AttemptId; },
        [](Scope& scope) { ++scope.WipeGeneration; },
        [](Scope& scope) { ++scope.RouteGeneration; },
        [](Scope& scope) { scope.NodeId = "bwd.magmaw.encounter.v2"; },
        [](Scope& scope) { ++scope.MapId; },
        [](Scope& scope) { ++scope.InstanceId; },
        [](Scope& scope) { scope.EncounterId = "magmaw-v2"; },
        [](Scope& scope) { ++scope.EncounterEpoch; } };
    for (Change const& change : changes)
    {
        Blackboard board = Board();
        auto first = Reconcile(nullptr, board);
        change(board.CurrentScope);
        ++board.Revision;
        auto retired = Reconcile(first, board);
        assert(retired->Plan().Lifecycle == board.CurrentScope);
        assert(retired->Plan().Generation == first->Plan().Generation + 1);
        for (size_t index = 0; index < MagmawRaidPlan::AssignmentCount;
            ++index)
            assert(retired->Plan().Assignments[index].Epoch
                == first->Plan().Assignments[index].Epoch + 1);
    }
}

static void AssertReplacementAndNoSteal()
{
    Blackboard board = Board();
    auto initial = Reconcile(nullptr, board);
    Member(board, 300).Alive = false;
    ++board.Revision;
    auto replaced = Reconcile(initial, board);
    assert(Assigned(replaced->Plan(), Slot::FireMageBaiter)
        == PlayerGuid(301));
    assert(Assigned(replaced->Plan(), Slot::HookOne) == PlayerGuid(400));
    Member(board, 300).Alive = true;
    ++board.Revision;
    auto resurrected = Reconcile(replaced, board);
    assert(Assigned(resurrected->Plan(), Slot::FireMageBaiter)
        == PlayerGuid(301));
    assert(Assigned(resurrected->Plan(), Slot::HookOne) == PlayerGuid(400));

    board = Board();
    initial = Reconcile(nullptr, board);
    Member(board, 100).Alive = false;
    ++board.Revision;
    replaced = Reconcile(initial, board);
    assert(Assigned(replaced->Plan(), Slot::MainPullTank) == PlayerGuid(101));

    board = Board();
    initial = Reconcile(nullptr, board);
    Member(board, 400).ClassSpec = "survival_hunter";
    ++board.Revision;
    replaced = Reconcile(initial, board);
    assert(Assigned(replaced->Plan(), Slot::MarksmanshipHunterBaiter)
        == PlayerGuid(401));

    board = Board();
    initial = Reconcile(nullptr, board);
    ActorSnapshot duplicate = Member(board, 300);
    board.Players.push_back(duplicate);
    ++board.Revision;
    replaced = Reconcile(initial, board);
    assert(Assigned(replaced->Plan(), Slot::FireMageBaiter)
        == PlayerGuid(301));
}

static void AssertSameSpecBackupOrEmpty()
{
    Blackboard board = Board();
    auto initial = Reconcile(nullptr, board);
    Member(board, 300).Alive = false;
    Member(board, 301).Alive = false;
    Member(board, 400).Alive = false;
    Member(board, 401).ClassSpec = "survival_hunter";
    ++board.Revision;
    auto empty = Reconcile(initial, board);
    assert(Assigned(empty->Plan(), Slot::FireMageBaiter).IsEmpty());
    assert(Assigned(empty->Plan(), Slot::MarksmanshipHunterBaiter).IsEmpty());
    assert(Assigned(empty->Plan(), Slot::SemanticLaneOwner).IsEmpty());
}

static void AssertMangleObservationIsLive()
{
    Blackboard board = Board();
    Member(board, 100).Auras.push_back({ 89773, {}, 1, 0 });
    auto first = Reconcile(nullptr, board);
    MagmawRaidAssignment const responder =
        first->Plan().Assignment(Slot::MangleResponder);
    assert(first->Plan().MangleOwnerGuid == PlayerGuid(100));
    Member(board, 100).Auras.clear();
    Member(board, 101).Auras.push_back({ 78412, {}, 1, 0 });
    ++board.Revision;
    auto second = Reconcile(first, board);
    assert(second->Plan().MangleOwnerGuid == PlayerGuid(101));
    assert(second->Plan().Assignment(Slot::MangleResponder).AssigneeGuid
        == responder.AssigneeGuid);
    assert(second->Plan().Assignment(Slot::MangleResponder).Epoch
        == responder.Epoch);
    assert(second->Plan().Generation == first->Plan().Generation + 1);
}

static void AssertTypedCompletionAndDuplicateReconcile()
{
    Blackboard board = Board();
    auto first = Reconcile(nullptr, board);
    MagmawRaidAssignment const bait =
        first->Plan().Assignment(Slot::FireMageBaiter);
    MagmawAssignmentRetirementInput completed = {
        Slot::FireMageBaiter, bait.AssigneeGuid, bait.Epoch,
        MagmawAssignmentRetirementKind::Completed };
    auto second = Reconcile(first, board, { completed });
    assert(Assigned(second->Plan(), Slot::FireMageBaiter)
        == PlayerGuid(301));
    uint64 const epoch = second->Plan().Assignment(Slot::FireMageBaiter).Epoch;
    uint64 const generation = second->Plan().Generation;
    auto duplicate = Reconcile(second, board, { completed });
    assert(duplicate->Plan().Assignment(Slot::FireMageBaiter).Epoch == epoch);
    assert(duplicate->Plan().Generation == generation);

    ++board.CurrentScope.AttemptId;
    ++board.Revision;
    auto newScope = Reconcile(first, board, { completed });
    assert(Assigned(newScope->Plan(), Slot::FireMageBaiter)
        == PlayerGuid(300));
    assert(newScope->Plan().Assignment(Slot::FireMageBaiter).Epoch
        == bait.Epoch + 1);
}

struct LegacySignature
{
    bool OwnsNode;
    bool SuppressOffense;
    ObjectGuid DamageTarget;
    ObjectGuid HealTarget;
    std::string Movement;
    std::string Interaction;
};

static LegacySignature Signature(AdaptiveMagmawPlan const& plan)
{
    return { plan.OwnsNode, plan.SuppressOffense, plan.DamageTarget,
        plan.PriorityHealTarget,
        plan.Movement ? plan.Movement->Id.Mechanic : "",
        plan.Interaction ? plan.Interaction->Id.Mechanic : "" };
}

static void AssertLegacySignatureUnchanged()
{
    Blackboard board = Board();
    AdaptiveMagmawStrategy strategy;
    LegacySignature before = Signature(strategy.Propose(board,
        PlayerGuid(400), "dps"));
    auto shadow = Reconcile(nullptr, board);
    assert(shadow->Plan().Authoritative);
    LegacySignature after = Signature(strategy.Propose(board,
        PlayerGuid(400), "dps"));
    assert(before.OwnsNode == after.OwnsNode);
    assert(before.SuppressOffense == after.SuppressOffense);
    assert(before.DamageTarget == after.DamageTarget);
    assert(before.HealTarget == after.HealTarget);
    assert(before.Movement == after.Movement);
    assert(before.Interaction == after.Interaction);
}

int main()
{
    AssertInitialAndIdempotent();
    AssertPermutationAndRevisionStability();
    AssertScopeRetirement();
    AssertReplacementAndNoSteal();
    AssertSameSpecBackupOrEmpty();
    AssertMangleObservationIsLive();
    AssertTypedCompletionAndDuplicateReconcile();
    AssertLegacySignatureUnchanged();
}
''', encoding="utf-8")
    subprocess.run([
        "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *INCLUDES,
        str(source),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
            "Encounters/Magmaw/BotMagmawFacts.cpp"),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/"
            "Encounters/Magmaw/BotMagmawCoordinator.cpp"),
        "-o", str(binary),
    ], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_magmaw_coordinator_is_small_and_shadow_only() -> None:
    encounter = (ROOT / "src/server/game/Bots/Content/Raids/"
        "BlackwingDescent/Encounters/Magmaw")
    coordinator = encounter / "BotMagmawCoordinator.cpp"
    assert len(coordinator.read_text(encoding="utf-8").splitlines()) < 300
    assert "BotMagmawCoordinator.cpp" in (
        ROOT / "src/server/game/CMakeLists.txt").read_text(encoding="utf-8")
    runtime = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrRuntimeContracts.h").read_text(encoding="utf-8")
    publisher = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrEncounterBlackboard.cpp").read_text(
            encoding="utf-8")
    assert "MagmawCoordinator" not in runtime
    assert "MagmawCoordinator" not in publisher
