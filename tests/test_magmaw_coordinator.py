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

static MagmawRosterMember RosterMember(uint32 counter, char const* role,
    char const* classSpec)
{
    return { PlayerGuid(counter), "slot_" + std::to_string(counter), role,
        classSpec, true, true };
}

static MagmawRosterView Roster(Scope const& scope,
    MagmawRaidMode mode = MagmawRaidMode::Normal10)
{
    MagmawRosterView roster;
    roster.Lifecycle = scope;
    roster.Generation = 3;
    roster.ExpectedSize = mode == MagmawRaidMode::Normal25
        || mode == MagmawRaidMode::Heroic25 ? 25 : 10;
    roster.Mode = mode;
    roster.Authoritative = true;
    roster.Members = {
        RosterMember(100, "tank", "protection_paladin"),
        RosterMember(101, "tank", "blood_death_knight"),
        RosterMember(200, "healer", "restoration_druid"),
        RosterMember(201, "healer", "holy_paladin"),
        RosterMember(300, "dps", "fire_mage"),
        RosterMember(301, "dps", "fire_mage"),
        RosterMember(400, "dps", "marksmanship_hunter"),
        RosterMember(401, "dps", "marksmanship_hunter"),
        RosterMember(500, "dps", "affliction_warlock"),
        RosterMember(600, "dps", "elemental_shaman") };
    for (uint32 counter = 700; roster.Members.size() < roster.ExpectedSize;
        ++counter)
        roster.Members.push_back(RosterMember(counter, "dps",
            "affliction_warlock"));
    return roster;
}

static ActorSnapshot& PlayerState(Blackboard& board, uint32 counter)
{
    auto itr = std::find_if(board.Players.begin(), board.Players.end(),
        [counter](ActorSnapshot const& actor)
        {
            return actor.Guid == PlayerGuid(counter);
        });
    assert(itr != board.Players.end());
    return *itr;
}

static MagmawRosterMember& RosterState(MagmawRosterView& roster,
    uint32 counter)
{
    auto itr = std::find_if(roster.Members.begin(), roster.Members.end(),
        [counter](MagmawRosterMember const& member)
        {
            return member.Guid == PlayerGuid(counter);
        });
    assert(itr != roster.Members.end());
    return *itr;
}

static MagmawFacts FutureAuthoritativeFacts(Blackboard const& board)
{
    MagmawFacts facts = MagmawFactsReducer::Reduce(board);
    facts.EncounterIdentityAuthoritative = true;
    facts.EncounterEpochAuthoritative = board.CurrentScope.EncounterEpoch != 0;
    facts.LifecycleAuthoritative = facts.CacheScopeComplete
        && facts.EncounterIdentityAuthoritative
        && facts.EncounterEpochAuthoritative;
    return facts;
}

static std::shared_ptr<MagmawCoordinator const> Reconcile(
    std::shared_ptr<MagmawCoordinator const> const& current,
    Blackboard const& board, MagmawRosterView const& roster)
{
    MagmawFacts const facts = FutureAuthoritativeFacts(board);
    return MagmawCoordinator::Reconcile(current, facts, board, roster);
}

static MagmawRaidAssignment const& Assignment(MagmawRaidPlan const& plan,
    Slot slot)
{
    MagmawRaidAssignment const* assignment = plan.FindAssignment(slot);
    assert(assignment);
    return *assignment;
}

static ObjectGuid Assigned(MagmawRaidPlan const& plan, Slot slot)
{
    return Assignment(plan, slot).AssigneeGuid;
}

static void AssertProductionLifecycleFailsClosed()
{
    Blackboard board = Board();
    board.CurrentScope.EncounterEpoch = 0;
    MagmawRosterView roster = Roster(board.CurrentScope);
    MagmawFacts const facts = MagmawFactsReducer::Reduce(board);
    auto plan = MagmawCoordinator::Reconcile(nullptr, facts, board, roster);
    assert(!facts.LifecycleAuthoritative && !plan->Plan().Authoritative);
    assert(!plan->Plan().MangleOwnerAuthoritative);
    for (MagmawRaidAssignment const& assignment :
        plan->Plan().AllAssignments())
        assert(assignment.AssigneeGuid.IsEmpty() && assignment.Epoch == 0);
}

static void AssertModesInitialAndSafeAccess()
{
    for (MagmawRaidMode mode : { MagmawRaidMode::Normal10,
        MagmawRaidMode::Heroic10, MagmawRaidMode::Normal25,
        MagmawRaidMode::Heroic25 })
    {
        Blackboard board = Board();
        MagmawRosterView roster = Roster(board.CurrentScope, mode);
        auto plan = Reconcile(nullptr, board, roster);
        assert(plan->Plan().Authoritative && plan->Plan().Generation == 1);
        assert(Assigned(plan->Plan(), Slot::FireMageBaiter)
            == PlayerGuid(300));
        assert(Assigned(plan->Plan(), Slot::MarksmanshipHunterBaiter)
            == PlayerGuid(400));
        assert(Assigned(plan->Plan(), Slot::HookOne) == PlayerGuid(300));
        assert(Assigned(plan->Plan(), Slot::HookTwo) == PlayerGuid(301));
        assert(Assigned(plan->Plan(), Slot::MainPullTank) == PlayerGuid(100));
        assert(Assigned(plan->Plan(), Slot::SemanticLaneOwner)
            == PlayerGuid(300));
        assert(Assigned(plan->Plan(), Slot::BloodlustOwner)
            == PlayerGuid(600));
        assert(Reconcile(plan, board, roster) == plan);
        assert(!plan->Plan().FindAssignment(Slot::Count));
        assert(!plan->Plan().FindAssignment(static_cast<Slot>(255)));
    }
}

static void AssertRecurringCyclesPermutationAndPartialSnapshot()
{
    Blackboard board = Board();
    MagmawRosterView roster = Roster(board.CurrentScope);
    auto first = Reconcile(nullptr, board, roster);
    std::reverse(board.Players.begin(), board.Players.end());
    std::reverse(roster.Members.begin(), roster.Members.end());
    PlayerState(board, 400).Role = "healer";
    PlayerState(board, 400).ClassSpec = "survival_hunter";
    board.Summons.push_back(Creature(41843, 9));
    board.Summons.push_back(Creature(41620, 10));
    ++board.Revision;
    auto pillar = Reconcile(first, board, roster);
    board.Summons.clear();
    board.Players.erase(board.Players.begin(), board.Players.begin() + 7);
    ++board.Revision;
    auto partial = Reconcile(pillar, board, roster);
    assert(partial->Plan().Generation == first->Plan().Generation);
    for (size_t index = 0; index < MagmawRaidPlan::AssignmentCount; ++index)
    {
        assert(partial->Plan().AllAssignments()[index].AssigneeGuid
            == first->Plan().AllAssignments()[index].AssigneeGuid);
        assert(partial->Plan().AllAssignments()[index].Epoch
            == first->Plan().AllAssignments()[index].Epoch);
    }
}

static void AssertInitialPartialAndTransientObservationLoss()
{
    Blackboard board = Board();
    MagmawRosterView roster = Roster(board.CurrentScope);
    board.Players.erase(std::remove_if(board.Players.begin(),
        board.Players.end(), [](ActorSnapshot const& actor)
        {
            return actor.Guid == PlayerGuid(300)
                || actor.Guid == PlayerGuid(400)
                || actor.Guid == PlayerGuid(401);
        }), board.Players.end());
    auto partial = Reconcile(nullptr, board, roster);
    assert(Assigned(partial->Plan(), Slot::FireMageBaiter)
        == PlayerGuid(301));
    assert(Assigned(partial->Plan(), Slot::MarksmanshipHunterBaiter).IsEmpty());

    board = Board();
    roster = Roster(board.CurrentScope);
    auto initial = Reconcile(nullptr, board, roster);
    uint64 const epoch = Assignment(initial->Plan(),
        Slot::FireMageBaiter).Epoch;
    board.Players.erase(std::remove_if(board.Players.begin(),
        board.Players.end(), [](ActorSnapshot const& actor)
        {
            return actor.Guid == PlayerGuid(300);
        }), board.Players.end());
    ++board.Revision;
    auto unobserved = Reconcile(initial, board, roster);
    assert(Assigned(unobserved->Plan(), Slot::FireMageBaiter)
        == PlayerGuid(300));
    assert(Assignment(unobserved->Plan(), Slot::FireMageBaiter).Epoch
        == epoch);

    board.Players.erase(std::remove_if(board.Players.begin(),
        board.Players.end(), [](ActorSnapshot const& actor)
        {
            return actor.Guid == PlayerGuid(301);
        }), board.Players.end());
    board.Players.push_back(Player(300, "dps", "fire_mage"));
    PlayerState(board, 300).Alive = false;
    ++board.Revision;
    auto noUnobservedReplacement = Reconcile(unobserved, board, roster);
    assert(Assigned(noUnobservedReplacement->Plan(),
        Slot::FireMageBaiter).IsEmpty());
    board.Players.push_back(Player(301, "dps", "fire_mage"));
    ++board.Revision;
    auto observedBackup = Reconcile(noUnobservedReplacement, board, roster);
    assert(Assigned(observedBackup->Plan(), Slot::FireMageBaiter)
        == PlayerGuid(301));
}

static void AssertAllScopeFieldsRetire()
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
        MagmawRosterView roster = Roster(board.CurrentScope);
        auto first = Reconcile(nullptr, board, roster);
        change(board.CurrentScope);
        roster.Lifecycle = board.CurrentScope;
        ++board.Revision;
        auto next = Reconcile(first, board, roster);
        assert(next->Plan().Lifecycle == board.CurrentScope);
        assert(next->Plan().Generation == first->Plan().Generation + 1);
        for (size_t index = 0; index < MagmawRaidPlan::AssignmentCount;
            ++index)
            assert(next->Plan().AllAssignments()[index].Epoch
                == first->Plan().AllAssignments()[index].Epoch + 1);
    }
}

static void AssertDeathAndInvalidityReplacementStaySticky()
{
    Blackboard board = Board();
    MagmawRosterView roster = Roster(board.CurrentScope);
    auto initial = Reconcile(nullptr, board, roster);
    PlayerState(board, 300).Alive = false;
    ++board.Revision;
    auto replaced = Reconcile(initial, board, roster);
    assert(Assigned(replaced->Plan(), Slot::FireMageBaiter)
        == PlayerGuid(301));
    assert(Assigned(replaced->Plan(), Slot::HookOne) == PlayerGuid(400));
    PlayerState(board, 300).Alive = true;
    ++board.Revision;
    auto resurrected = Reconcile(replaced, board, roster);
    assert(Assigned(resurrected->Plan(), Slot::FireMageBaiter)
        == PlayerGuid(301));
    assert(Assigned(resurrected->Plan(), Slot::HookOne) == PlayerGuid(400));

    board = Board();
    roster = Roster(board.CurrentScope);
    initial = Reconcile(nullptr, board, roster);
    ActorSnapshot duplicate = PlayerState(board, 400);
    board.Players.push_back(duplicate);
    ++board.Revision;
    replaced = Reconcile(initial, board, roster);
    assert(Assigned(replaced->Plan(), Slot::MarksmanshipHunterBaiter)
        == PlayerGuid(401));
}

static void AssertAuthorityLossDoesNotMutateAssignments()
{
    Blackboard board = Board();
    MagmawRosterView roster = Roster(board.CurrentScope);
    auto initial = Reconcile(nullptr, board, roster);
    auto assignments = initial->Plan().AllAssignments();
    roster.Authoritative = false;
    ++roster.Generation;
    auto lost = Reconcile(initial, board, roster);
    assert(!lost->Plan().Authoritative);
    assert(lost->Plan().AllAssignments() == assignments);
    roster.Authoritative = true;
    ++roster.Generation;
    auto restored = Reconcile(lost, board, roster);
    assert(restored->Plan().Authoritative);
    assert(restored->Plan().AllAssignments() == assignments);

    roster = Roster(board.CurrentScope);
    RosterState(roster, 300).Admitted = false;
    auto unadmitted = Reconcile(nullptr, board, roster);
    assert(!unadmitted->Plan().Authoritative);
    RosterState(roster, 300).Admitted = true;
    RosterState(roster, 300).LeaseOwned = false;
    auto unleased = Reconcile(nullptr, board, roster);
    assert(!unleased->Plan().Authoritative);
}

static void AssertRosterAuthorityAndBloodlustUniqueness()
{
    Blackboard board = Board();
    MagmawRosterView roster = Roster(board.CurrentScope);
    auto exact = Reconcile(nullptr, board, roster);
    assert(Assigned(exact->Plan(), Slot::BloodlustOwner) == PlayerGuid(600));

    RosterState(roster, 600).ClassSpec = "affliction_warlock";
    ++roster.Generation;
    auto missing = Reconcile(exact, board, roster);
    assert(missing->Plan().Authoritative);
    assert(Assigned(missing->Plan(), Slot::BloodlustOwner).IsEmpty());

    roster = Roster(board.CurrentScope);
    RosterState(roster, 500).ClassSpec = "elemental_shaman";
    PlayerState(board, 500).Alive = false;
    ++roster.Generation;
    auto duplicate = Reconcile(exact, board, roster);
    assert(duplicate->Plan().Authoritative);
    assert(Assigned(duplicate->Plan(), Slot::BloodlustOwner).IsEmpty());

    roster = Roster(board.CurrentScope);
    RosterState(roster, 600).LeaseOwned = false;
    ++roster.Generation;
    auto unleased = Reconcile(exact, board, roster);
    assert(!unleased->Plan().Authoritative);
    assert(unleased->Plan().AllAssignments()
        == exact->Plan().AllAssignments());

    for (uint8 failure = 0; failure < 8; ++failure)
    {
        roster = Roster(board.CurrentScope);
        if (failure == 0)
            roster.Authoritative = false;
        else if (failure == 1)
            ++roster.Lifecycle.AttemptId;
        else if (failure == 2)
            roster.Members[1].Guid = roster.Members[0].Guid;
        else if (failure == 3)
            roster.Members[1].RosterSlotId = roster.Members[0].RosterSlotId;
        else if (failure == 4)
            roster.ExpectedSize = 25;
        else if (failure == 5)
        {
            roster.Mode = MagmawRaidMode::Unknown;
            roster.ExpectedSize = 0;
        }
        else if (failure == 6)
            roster.Members[0].Admitted = false;
        else
            roster.Members[0].LeaseOwned = false;
        auto failed = Reconcile(nullptr, board, roster);
        assert(!failed->Plan().Authoritative);
        for (MagmawRaidAssignment const& assignment :
            failed->Plan().AllAssignments())
            assert(assignment.AssigneeGuid.IsEmpty());
    }
}

static void AssertMangleOwnerIsObservationOnly()
{
    Blackboard board = Board();
    MagmawRosterView roster = Roster(board.CurrentScope);
    PlayerState(board, 100).Auras.push_back({ 89773, {}, 1, 0 });
    auto first = Reconcile(nullptr, board, roster);
    auto assignments = first->Plan().AllAssignments();
    assert(first->Plan().MangleOwnerAuthoritative);
    assert(first->Plan().MangleOwnerGuid == PlayerGuid(100));
    PlayerState(board, 100).Auras.clear();
    PlayerState(board, 101).Auras.push_back({ 78412, {}, 1, 0 });
    ++board.Revision;
    auto second = Reconcile(first, board, roster);
    assert(second->Plan().MangleOwnerGuid == PlayerGuid(101));
    assert(second->Plan().AllAssignments() == assignments);

    roster.Authoritative = false;
    ++roster.Generation;
    auto closed = Reconcile(second, board, roster);
    assert(!closed->Plan().MangleOwnerAuthoritative);
    assert(closed->Plan().MangleOwnerGuid.IsEmpty());
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
    MagmawRosterView roster = Roster(board.CurrentScope);
    PlayerState(board, 100).Auras.push_back({ 89773, {}, 1, 0 });
    AdaptiveMagmawStrategy strategy;
    for (auto const& [guid, role] : std::vector<std::pair<uint32,
        char const*>>{ { 400, "dps" }, { 200, "healer" },
            { 201, "healer" } })
    {
        LegacySignature before = Signature(strategy.Propose(board,
            PlayerGuid(guid), role));
        auto shadow = Reconcile(nullptr, board, roster);
        assert(shadow->Plan().Authoritative);
        LegacySignature after = Signature(strategy.Propose(board,
            PlayerGuid(guid), role));
        assert(before.OwnsNode == after.OwnsNode);
        assert(before.SuppressOffense == after.SuppressOffense);
        assert(before.DamageTarget == after.DamageTarget);
        assert(before.HealTarget == after.HealTarget);
        assert(before.Movement == after.Movement);
        assert(before.Interaction == after.Interaction);
    }
}

int main()
{
    AssertProductionLifecycleFailsClosed();
    AssertModesInitialAndSafeAccess();
    AssertRecurringCyclesPermutationAndPartialSnapshot();
    AssertInitialPartialAndTransientObservationLoss();
    AssertAllScopeFieldsRetire();
    AssertDeathAndInvalidityReplacementStaySticky();
    AssertAuthorityLossDoesNotMutateAssignments();
    AssertRosterAuthorityAndBloodlustUniqueness();
    AssertMangleOwnerIsObservationOnly();
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


def test_magmaw_coordinator_is_small_safe_and_shadow_only() -> None:
    encounter = (ROOT / "src/server/game/Bots/Content/Raids/"
        "BlackwingDescent/Encounters/Magmaw")
    coordinator = encounter / "BotMagmawCoordinator.cpp"
    plan = encounter / "BotMagmawRaidPlan.h"
    source = coordinator.read_text(encoding="utf-8")
    contract = plan.read_text(encoding="utf-8")
    assert len(source.splitlines()) < 300
    assert "BotMagmawCoordinator.cpp" in (
        ROOT / "src/server/game/CMakeLists.txt").read_text(encoding="utf-8")
    assert "ExactRoster(Blackboard" not in source
    assert "Retirement" not in source + contract
    assert "MangleResponder" not in source + contract
    assert "MagmawLaneTransition" not in source + contract
    runtime = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrRuntimeContracts.h").read_text(encoding="utf-8")
    publisher = (ROOT / "src/server/game/Bots/"
        "BotWorldPopulationMgrEncounterBlackboard.cpp").read_text(
            encoding="utf-8")
    assert "MagmawCoordinator" not in runtime
    assert "MagmawCoordinator" not in publisher
