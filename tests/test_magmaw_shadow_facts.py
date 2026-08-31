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

def test_magmaw_shadow_facts_contract(tmp_path: Path) -> None:
    source = tmp_path / "magmaw_shadow_facts.cpp"
    binary = tmp_path / "magmaw_shadow_facts"
    source.write_text(r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawFacts.h"
#include <algorithm>
#include <cassert>
#include <functional>
#include <string>
#include <vector>

using namespace BotEncounter;
std::string ObjectGuid::ToString() const
{
    return std::to_string(GetRawValue());
}

static ObjectGuid PlayerGuid(uint32 guid)
{
    return ObjectGuid(HighGuid::Player, guid);
}

static ActorSnapshot Creature(uint32 entry, uint32 guid, Vector3 position)
{
    ActorSnapshot actor;
    actor.Guid = ObjectGuid(HighGuid::Unit, entry, guid);
    actor.Entry = entry;
    actor.Alive = true;
    actor.Position = position;
    return actor;
}

static ActorSnapshot Player(uint32 guid, char const* role, Vector3 position)
{
    ActorSnapshot actor;
    actor.Guid = PlayerGuid(guid);
    actor.Kind = ActorKind::Player;
    actor.Role = role;
    actor.Alive = true;
    actor.HealthPct = 100.0f;
    actor.Position = position;
    return actor;
}

static Blackboard Board()
{
    Blackboard board;
    board.CurrentScope.ServerEpoch = 91;
    board.CurrentScope.CohortId = "shadow-cohort";
    board.CurrentScope.AttemptId = 12;
    board.CurrentScope.WipeGeneration = 3;
    board.CurrentScope.RouteGeneration = 14;
    board.CurrentScope.NodeId = "bwd.magmaw.encounter";
    board.CurrentScope.MapId = 669;
    board.CurrentScope.InstanceId = 27;
    board.CurrentScope.EncounterId = "tank_swap_adds_raid_aoe";
    board.CurrentScope.EncounterEpoch = 0;
    board.Revision = 30;
    board.ObservedAtMs = 1000;
    board.NativeBossState = "in_progress";
    board.NativeEncounterPhase = "combat";
    board.NativeWipeState = "engaged";
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Route.NavigationHints = { { 0.0f, -1.0f, 210.0f } };
    board.Players = {
        Player(30001, "tank", { 0.0f, 0.0f, 210.0f }),
        Player(30006, "dps", { 24.0f, -30.0f, 210.0f }),
        Player(30009, "dps", { -24.0f, -30.0f, 210.0f }) };
    board.Players[0].Auras.push_back({ 89773, {}, 1, 0 });
    ActorSnapshot boss = Creature(41570, 1, { 0.0f, 0.0f, 210.0f });
    boss.Attackable = true;
    boss.Selectable = true;
    boss.InCombat = true;
    boss.VictimGuid = board.Players[0].Guid;
    ActorSnapshot head = Creature(42347, 2, { 0.0f, -2.0f, 210.0f });
    head.Attackable = true;
    head.Selectable = true;
    ActorSnapshot crash = Creature(47196, 3, { 0.0f, -30.0f, 210.0f });
    crash.Auras.push_back({ 87949, {}, 1, 0 });
    board.Hostiles = { boss, Creature(41806, 5,
        { 5.0f, -50.0f, 210.0f }), head, crash };
    board.Summons = {
        Creature(41843, 7, { 24.0f, -30.0f, 210.0f }),
        Creature(41620, 8, { 0.0f, -1.0f, 210.0f }) };
    return board;
}

static bool SameActors(std::vector<MagmawActorFact> const& left,
    std::vector<MagmawActorFact> const& right)
{
    return left == right;
}

static void AssertOrderStableAndPure()
{
    Blackboard board = Board();
    std::vector<ObjectGuid> hostileOrder;
    for (ActorSnapshot const& actor : board.Hostiles)
        hostileOrder.push_back(actor.Guid);
    MagmawFacts first = MagmawFactsReducer::Reduce(board);
    assert(board.Revision == 30 && board.Hostiles.size() == 4);
    for (size_t index = 0; index < hostileOrder.size(); ++index)
        assert(board.Hostiles[index].Guid == hostileOrder[index]);

    std::reverse(board.Hostiles.begin(), board.Hostiles.end());
    std::reverse(board.Summons.begin(), board.Summons.end());
    std::reverse(board.Players.begin(), board.Players.end());
    MagmawFacts second = MagmawFactsReducer::Reduce(board);
    assert(first.ObservationRevision == second.ObservationRevision);
    assert(first.CacheScopeComplete);
    assert(!first.LifecycleAuthoritative);
    assert(!first.EncounterIdentityAuthoritative);
    assert(!first.EncounterEpochAuthoritative);
    assert(first.OwnsNode == MagmawTruth::True);
    assert(first.Phase == MagmawPhase::Combat && first.PhaseAuthoritative);
    assert(first.Prepull == MagmawTruth::False);
    assert(first.HeadExposed == MagmawTruth::True);
    assert(first.ExposedHeadIdentityAuthoritative);
    assert(first.MangleOwnerAuthoritative
        && first.MangleOwnerGuid == PlayerGuid(30001));
    assert(first.WipeLocked == MagmawTruth::False);
    assert(SameActors(first.Bosses, second.Bosses));
    assert(SameActors(first.Heads, second.Heads));
    assert(SameActors(first.Pillar.Sources, second.Pillar.Sources));
    assert(SameActors(first.Crash.Sources, second.Crash.Sources));
    assert(SameActors(first.PincerWarning.Sources,
        second.PincerWarning.Sources));
    assert(SameActors(first.PincerVehicles.Sources,
        second.PincerVehicles.Sources));
    assert(SameActors(first.Parasites.Sources, second.Parasites.Sources));
    assert(first.BossInteractable == MagmawTruth::False);
    assert(!first.Pillar.Generation.Authoritative());
    assert(!first.Crash.Generation.Authoritative());
    assert(!first.Parasites.Generation.Authoritative());

    board.Hostiles.push_back(Creature(42321, 9,
        { -5.0f, -50.0f, 210.0f }));
    assert(!MagmawFactsReducer::Reduce(board)
        .Parasites.Generation.Authoritative());
}

static void AssertPartialObservationUnknown()
{
    Blackboard partial = Board();
    partial.Players[0].Auras.clear();
    partial.Hostiles.clear();
    partial.Summons.clear();
    MagmawFacts missing = MagmawFactsReducer::Reduce(partial);
    assert(missing.ProjectionAuthoritative);
    assert(!missing.ArenaObservationAuthoritative);
    assert(missing.Pillar.Active == MagmawTruth::Unknown);
    assert(missing.Crash.Active == MagmawTruth::Unknown);
    assert(missing.PincerWarning.Active == MagmawTruth::Unknown);
    assert(missing.PincerVehicles.Active == MagmawTruth::Unknown);
    assert(missing.Parasites.Active == MagmawTruth::Unknown);
    assert(missing.BossInteractable == MagmawTruth::Unknown);
    assert(missing.HeadExposed == MagmawTruth::Unknown);
    assert(missing.Phase == MagmawPhase::Unknown);
    assert(missing.Prepull == MagmawTruth::Unknown);
    assert(!missing.MangleOwnerAuthoritative);

    partial.Hostiles.push_back(Creature(41806, 55,
        { 5.0f, -50.0f, 210.0f }));
    MagmawFacts positive = MagmawFactsReducer::Reduce(partial);
    assert(positive.Parasites.Active == MagmawTruth::True);
    assert(positive.Parasites.Authoritative);
    assert(positive.Pillar.Active == MagmawTruth::Unknown);
    partial.Hostiles.clear();
    auto partialCache = MagmawFactsCache::ForSnapshot(nullptr, partial);
    partial.Hostiles.push_back(Creature(41806, 56,
        { 5.0f, -50.0f, 210.0f }));
    ++partial.Revision;
    partialCache = MagmawFactsCache::ForSnapshot(partialCache, partial);
    assert(!partialCache->Facts().Parasites.Generation.Authoritative());

    Blackboard unengaged = Board();
    unengaged.Hostiles[0].InCombat = false;
    unengaged.Hostiles[0].VictimGuid.Clear();
    unengaged.NativeBossState = "not_in_progress";
    unengaged.NativeEncounterPhase = "formation";
    MagmawFacts noGlobalInference = MagmawFactsReducer::Reduce(unengaged);
    assert(noGlobalInference.Phase == MagmawPhase::Unknown);
    assert(noGlobalInference.Prepull == MagmawTruth::Unknown);
}

static Blackboard WithoutActiveSignals(Blackboard board)
{
    board.Players[0].Auras.clear();
    board.Hostiles.erase(std::remove_if(board.Hostiles.begin(),
        board.Hostiles.end(), [](ActorSnapshot const& actor)
        {
            return actor.Entry == 41806 || actor.Entry == 42321
                || actor.Entry == 47196;
        }), board.Hostiles.end());
    board.Summons.clear();
    return board;
}

static Blackboard ExactLifecycleBoard()
{
    Blackboard board = Board();
    board.CurrentScope.EncounterId = "magmaw";
    board.CurrentScope.EncounterEpoch = 1;
    board.EncounterIdentityAuthoritative = true;
    board.EncounterEpochAuthoritative = true;
    board.EncounterArenaObservationComplete = true;
    return board;
}

static void AssertGeneration(MagmawSignal const& signal, uint64 value)
{
    assert(signal.Active == MagmawTruth::True);
    assert(signal.Generation.Kind == MagmawGenerationKind::ObservationEdge);
    assert(signal.Generation.Value == value);
}

static void AssertAllGenerations(MagmawFacts const& facts, uint64 value)
{
    AssertGeneration(facts.Pillar, value);
    AssertGeneration(facts.Crash, value);
    AssertGeneration(facts.PincerWarning, value);
    AssertGeneration(facts.PincerVehicles, value);
    AssertGeneration(facts.Parasites, value);
}

static void AssertNoGenerations(MagmawFacts const& facts)
{
    assert(!facts.Pillar.Generation.Authoritative());
    assert(!facts.Crash.Generation.Authoritative());
    assert(!facts.PincerWarning.Generation.Authoritative());
    assert(!facts.PincerVehicles.Generation.Authoritative());
    assert(!facts.Parasites.Generation.Authoritative());
}

static void AssertCacheLifecycle()
{
    Blackboard board = Board();
    auto cache = MagmawFactsCache::ForSnapshot(nullptr, board);
    auto same = MagmawFactsCache::ForSnapshot(cache, board);
    assert(same == cache);
    ++board.Revision;
    auto fresh = MagmawFactsCache::ForSnapshot(cache, board);
    assert(fresh != cache && fresh->Facts().ObservationRevision == 31);

    Blackboard inactive = WithoutActiveSignals(Board());
    auto edgeCache = MagmawFactsCache::ForSnapshot(nullptr, inactive);
    assert(!edgeCache->Facts().Parasites.ObservedPresent);
    Blackboard active = Board();
    ++active.Revision;
    edgeCache = MagmawFactsCache::ForSnapshot(edgeCache, active);
    assert(!edgeCache->Facts().LifecycleAuthoritative);
    assert(edgeCache->Facts().Parasites.ObservedPresent);
    AssertNoGenerations(edgeCache->Facts());

    inactive = WithoutActiveSignals(ExactLifecycleBoard());
    edgeCache = MagmawFactsCache::ForSnapshot(nullptr, inactive);
    assert(edgeCache->Facts().LifecycleAuthoritative);
    assert(edgeCache->Facts().ArenaObservationAuthoritative);
    assert(edgeCache->Facts().Pillar.Active == MagmawTruth::False);
    assert(edgeCache->Facts().Pillar.Authoritative);
    active = ExactLifecycleBoard();
    ++active.Revision;
    edgeCache = MagmawFactsCache::ForSnapshot(edgeCache, active);
    AssertAllGenerations(edgeCache->Facts(), 1);
    active.Revision++;
    active.Hostiles[1].Guid = ObjectGuid(HighGuid::Unit, uint32(41806),
        uint32(105));
    active.Hostiles[3].Guid = ObjectGuid(HighGuid::Unit, uint32(47196),
        uint32(103));
    active.Summons[0].Guid = ObjectGuid(HighGuid::Unit, uint32(41843),
        uint32(107));
    active.Summons[1].Guid = ObjectGuid(HighGuid::Unit, uint32(41620),
        uint32(108));
    edgeCache = MagmawFactsCache::ForSnapshot(edgeCache, active);
    AssertAllGenerations(edgeCache->Facts(), 1);
    inactive.Revision = active.Revision + 1;
    edgeCache = MagmawFactsCache::ForSnapshot(edgeCache, inactive);
    active.Revision = inactive.Revision + 1;
    edgeCache = MagmawFactsCache::ForSnapshot(edgeCache, active);
    AssertAllGenerations(edgeCache->Facts(), 2);

    using Change = std::function<void(Scope&)>;
    std::vector<Change> retire = {
        [](Scope& scope) { ++scope.ServerEpoch; },
        [](Scope& scope) { scope.CohortId = "other"; },
        [](Scope& scope) { ++scope.AttemptId; },
        [](Scope& scope) { ++scope.WipeGeneration; },
        [](Scope& scope) { ++scope.RouteGeneration; },
        [](Scope& scope) { scope.NodeId = "bwd.omnotron.encounter"; },
        [](Scope& scope) { ++scope.MapId; },
        [](Scope& scope) { ++scope.InstanceId; },
        [](Scope& scope) { scope.EncounterId = "other"; },
        [](Scope& scope) { ++scope.EncounterEpoch; } };
    for (Change const& change : retire)
    {
        Blackboard changed = Board();
        change(changed.CurrentScope);
        auto retired = MagmawFactsCache::ForSnapshot(cache, changed);
        assert(retired != cache);
        assert(retired->Facts().Lifecycle == changed.CurrentScope);
    }
}

struct PlanSignature
{
    bool OwnsNode;
    bool SuppressOffense;
    ObjectGuid DamageTarget;
    ObjectGuid HealTarget;
    std::string Movement;
    std::string Interaction;
};

static PlanSignature Signature(AdaptiveMagmawPlan const& plan)
{
    return { plan.OwnsNode, plan.SuppressOffense, plan.DamageTarget,
        plan.PriorityHealTarget,
        plan.Movement ? plan.Movement->Id.Mechanic : "",
        plan.Interaction ? plan.Interaction->Id.Mechanic : "" };
}

static bool Same(PlanSignature const& left, PlanSignature const& right)
{
    return left.OwnsNode == right.OwnsNode
        && left.SuppressOffense == right.SuppressOffense
        && left.DamageTarget == right.DamageTarget
        && left.HealTarget == right.HealTarget
        && left.Movement == right.Movement
        && left.Interaction == right.Interaction;
}

static void AssertLegacyDecisionsUnchanged(Blackboard board)
{
    AdaptiveMagmawStrategy strategy;
    PlanSignature before = Signature(strategy.Propose(board,
        PlayerGuid(30009), "dps"));
    auto cache = MagmawFactsCache::ForSnapshot(nullptr, board);
    assert(cache->Facts().ObservationRevision == board.Revision);
    PlanSignature after = Signature(strategy.Propose(board,
        PlayerGuid(30009), "dps"));
    assert(Same(before, after));
}

int main()
{
    AssertOrderStableAndPure();
    AssertPartialObservationUnknown();
    AssertCacheLifecycle();
    Blackboard combat = Board();
    AssertLegacyDecisionsUnchanged(combat);
    combat.Hostiles.erase(combat.Hostiles.begin() + 2);
    AssertLegacyDecisionsUnchanged(combat);
    Blackboard prepull = Board();
    prepull.NativeBossState = "not_in_progress";
    prepull.NativeEncounterPhase = "formation";
    prepull.NativeWipeState = "ready";
    prepull.Hostiles[0].InCombat = false;
    prepull.Hostiles[0].VictimGuid.Clear();
    prepull.Players[1].HealthPct = 80.0f;
    AssertLegacyDecisionsUnchanged(prepull);
}
''', encoding="utf-8")
    subprocess.run([
        "g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", *INCLUDES,
        str(source), str(ROOT / "src/server/game/Bots/Content/Raids/"
            "BlackwingDescent/Encounters/Magmaw/BotMagmawFacts.cpp"),
        "-o", str(binary),
    ], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)
