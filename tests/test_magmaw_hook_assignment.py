from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _compile_and_run(source: Path, binary: Path) -> None:
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


def test_magmaw_hook_ownership_excludes_fixed_baiters(tmp_path: Path) -> None:
    source = tmp_path / "magmaw_hook_assignment.cpp"
    binary = tmp_path / "magmaw_hook_assignment"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/BotWorldPopulationMgrNativePathAdmission.h"
#include <algorithm>
#include <cmath>
#include <limits>
#include <cassert>
#include <string>

using namespace BotEncounter;
using BotNativeAction::SpellClick;
using BotNativeAction::VehicleAction;

std::string ObjectGuid::ToString() const
{
    return std::to_string(GetRawValue());
}

static ActorSnapshot Player(uint32 guid, char const* role,
    char const* spec, Vector3 position)
{
    ActorSnapshot player;
    player.Guid = ObjectGuid(HighGuid::Player, guid);
    player.Kind = ActorKind::Player;
    player.Role = role;
    player.ClassSpec = spec;
    player.Position = position;
    player.HealthPct = 100.0f;
    player.Alive = true;
    return player;
}

static ActorSnapshot Boss()
{
    ActorSnapshot boss;
    boss.Guid = ObjectGuid(HighGuid::Unit,
        AdaptiveMagmawStrategy::BossEntry, uint32(39));
    boss.Entry = AdaptiveMagmawStrategy::BossEntry;
    boss.Alive = true;
    boss.Attackable = true;
    boss.Selectable = true;
    boss.InCombat = true;
    boss.Position = { 0.0f, 0.0f, 210.0f };
    return boss;
}

static Blackboard Board()
{
    Blackboard board;
    board.CurrentScope = Scope{
        "hook-ownership", 7, 0, 4, "bwd.magmaw.encounter", 669, 1,
        "magmaw" };
    board.Revision = 21;
    board.ObservedAtMs = 1788793560680;
    board.NativeBossState = "in_progress";
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Route.NavigationHints = { { 0.0f, -1.0f, 210.0f } };
    ActorSnapshot tank = Player(30001, "tank", "protection_paladin",
        { 0.0f, 0.0f, 210.0f });
    tank.HealthPct = 100.0f;
    ActorSnapshot healer = Player(30003, "healer", "restoration_druid",
        { 0.0f, -8.0f, 210.0f });
    ActorSnapshot fixedMage = Player(30006, "dps", "fire_mage",
        { 30.0f, 0.0f, 210.0f });
    ActorSnapshot ordinaryMage = Player(30007, "dps", "fire_mage",
        { 30.0f, 0.0f, 210.0f });
    ActorSnapshot ordinaryWarlock = Player(30008, "dps",
        "affliction_warlock", { 30.0f, 0.0f, 210.0f });
    ActorSnapshot fixedHunter = Player(30009, "dps",
        "marksmanship_hunter", { 30.0f, 0.0f, 210.0f });
    ActorSnapshot ordinaryElemental = Player(30010, "dps",
        "elemental_shaman", { 30.0f, 0.0f, 210.0f });
    board.Players = { tank, healer, fixedMage, ordinaryMage,
        ordinaryWarlock, fixedHunter, ordinaryElemental };
    ActorSnapshot boss = Boss();
    boss.VictimGuid = tank.Guid;
    board.Hostiles = { boss };
    return board;
}

static bool HasMechanic(AdaptiveMagmawPlan const& plan,
    char const* mechanic)
{
    for (BotNativeAction::Candidate const& candidate : plan.Movement.Proposals())
        if (candidate.Id.Mechanic == mechanic)
            return true;
    return plan.Interaction && plan.Interaction->Id.Mechanic == mechanic;
}

static ActorSnapshot const& PlayerByGuid(Blackboard const& board, uint32 guid)
{
    ObjectGuid const wanted(HighGuid::Player, guid);
    auto const itr = std::find_if(board.Players.begin(), board.Players.end(),
        [wanted](ActorSnapshot const& player)
        {
            return player.Guid == wanted;
        });
    assert(itr != board.Players.end());
    return *itr;
}

static void AddPincerWindow(Blackboard& board, bool interactable)
{
    board.Hostiles.front().Interactable = interactable;
    ActorSnapshot leftPincer = board.Hostiles.front();
    leftPincer.Guid = ObjectGuid(HighGuid::Unit,
        AdaptiveMagmawStrategy::PincerLeftEntry, uint32(700));
    leftPincer.Entry = AdaptiveMagmawStrategy::PincerLeftEntry;
    ActorSnapshot rightPincer = board.Hostiles.front();
    rightPincer.Guid = ObjectGuid(HighGuid::Unit,
        AdaptiveMagmawStrategy::PincerRightEntry, uint32(702));
    rightPincer.Entry = AdaptiveMagmawStrategy::PincerRightEntry;
    ActorSnapshot spike = board.Hostiles.front();
    spike.Guid = ObjectGuid(HighGuid::Unit,
        AdaptiveMagmawStrategy::SpikeEntry, uint32(701));
    spike.Entry = AdaptiveMagmawStrategy::SpikeEntry;
    board.Summons = { leftPincer, rightPincer, spike };
}

static void AddPincerWarning(Blackboard& board)
{
    board.Hostiles.front().Interactable = false;
    board.Players.front().Auras = {
        AuraSnapshot{ 89773u, board.Hostiles.front().Guid, 1, 0 } };
    board.Summons.clear();
}

static char const* InteractionMechanic(AdaptiveMagmawPlan const& plan)
{
    return plan.Interaction ? plan.Interaction->Id.Mechanic.c_str() : "";
}

static char const* MovementMechanic(AdaptiveMagmawPlan const& plan)
{
    return plan.Movement ? plan.Movement->Id.Mechanic.c_str() : "";
}

int main()
{
    AdaptiveMagmawStrategy strategy;
    // Reproduce receipt449's actor/endpoint evidence. The synthetic boss-room
    // ray is aligned to its recorded request XY; no native geometry is changed.
    Blackboard airborne = Board();
    airborne.Hostiles.front().Position = { -305.688446f, -30.0812607f, 210.0f };
    airborne.Route.NavigationHints = { { -305.688446f, -40.0812607f, 211.815002f } };
    airborne.Players[3].Position = { -311.464996f, -48.5971985f, 214.838013f };
    AddPincerWarning(airborne);
    auto const fireGuid = airborne.Players[3].Guid;
    auto admission = [&](BotNativeAction::Move const& move)
    {
        using namespace BotWorldMovement;
        auto const& actor = airborne.Players[3].Position;
        NativePathProofObservation proof;
        proof.Available = proof.Calculated = proof.Complete = true;
        proof.EndpointFloorValid = true;
        proof.EndpointX = -305.848938f;
        proof.EndpointY = -34.8836632f;
        proof.EndpointZ = 210.517456f;
        proof.EndpointHorizontalDistance = std::hypot(move.X - proof.EndpointX,
            move.Y - proof.EndpointY);
        proof.EndpointVerticalDistance = std::fabs(move.Z - proof.EndpointZ);
        proof.EndpointDistance = std::hypot(proof.EndpointHorizontalDistance,
            proof.EndpointVerticalDistance);
        float const goal = std::hypot(std::hypot(actor.X - move.X,
            actor.Y - move.Y), actor.Z - move.Z);
        float const endpointGoal = proof.EndpointDistance;
        float const travel = std::hypot(std::hypot(actor.X - proof.EndpointX,
            actor.Y - proof.EndpointY), actor.Z - proof.EndpointZ);
        bool const fallback = AdmitSameLevelDeclaredFloorFallback(
            actor.Z, move.Z, -106.229317f);
        auto const owner = BotMovementArbitration::Owner::Mechanic;
        bool const bounded = AllowsSameLevelLocalMechanicProgress(
            owner, fallback, goal, false, false);
        return NativePathAllowsBoundedSameLevelMechanicProgress(owner,
            fallback, bounded, true, false, proof, travel, goal, endpointGoal,
            std::fabs(actor.Z - move.Z) <= NativeFloorTolerance);
    };
    for (bool warning : { true, false })
    {
        if (!warning)
            AddPincerWindow(airborne, true);
        auto const plan = strategy.Propose(airborne, fireGuid, "dps");
        bool found = false;
        for (auto const& candidate : plan.Movement.Proposals())
            if (candidate.Id.Mechanic == (warning ? "pincer_preposition" : "pincer_approach"))
            {
                auto const& move = std::get<BotNativeAction::Move>(candidate.Action);
                assert(std::fabs(move.X + 305.688446f) < 0.001f);
                assert(std::fabs(move.Y + 34.0812607f) < 0.001f);
                // Behavioral red before producer correction: elevated declared
                // endpoint fails the unchanged native admission envelope.
                assert(admission(move));
                assert(move.Z == 211.815002f);
                auto elevated = move;
                elevated.Z = airborne.Players[3].Position.Z;
                assert(!admission(elevated));
                found = true;
            }
        assert(found);
    }
    for (bool nonfinite : { false, true })
    {
        if (nonfinite)
            airborne.Route.NavigationHints = { { 0.0f, -1.0f,
                std::numeric_limits<float>::quiet_NaN() } };
        else
            airborne.Route.NavigationHints.clear();
        auto const plan = strategy.Propose(airborne, fireGuid, "dps");
        assert(!HasMechanic(plan, "pincer_approach"));
        AddPincerWarning(airborne);
        assert(!HasMechanic(strategy.Propose(airborne, fireGuid, "dps"),
            "pincer_preposition"));
        AddPincerWindow(airborne, true);
    }
    Blackboard base = Board();
    ObjectGuid const fixedMage = PlayerByGuid(base, 30006).Guid;
    ObjectGuid const ordinaryMage = PlayerByGuid(base, 30007).Guid;
    ObjectGuid const ordinaryWarlock = PlayerByGuid(base, 30008).Guid;
    ObjectGuid const fixedHunter = PlayerByGuid(base, 30009).Guid;
    ObjectGuid const ordinaryElemental = PlayerByGuid(base, 30010).Guid;
    ObjectGuid const healer = PlayerByGuid(base, 30003).Guid;
    ObjectGuid const tank = PlayerByGuid(base, 30001).Guid;

    // The live failure was fixedmage30006 selected for pincer_approach while
    // the fixed bait lane remained active. Both fixed baiters stay out of all
    // hook ownership paths, including the open interaction window.
    Blackboard approach = base;
    AddPincerWindow(approach, true);
    for (ObjectGuid guid : { fixedMage, fixedHunter })
    {
        AdaptiveMagmawPlan plan = strategy.Propose(approach, guid, "dps");
        assert(!plan.Interaction.has_value());
        assert(!HasMechanic(plan, "mount_free_pincer"));
        assert(!HasMechanic(plan, "pincer_approach"));
        assert(!HasMechanic(plan, "pincer_preposition"));
    }

    // One mounted actor cannot launch alone. The right pincer holds its
    // native hook while ordinary30007 remains able to mount and approach.
    Blackboard loneMounted = approach;
    loneMounted.Players[4].VehicleGuid = loneMounted.Summons[1].Guid;
    AdaptiveMagmawPlan loneRight = strategy.Propose(
        loneMounted, ordinaryWarlock, "dps");
    AdaptiveMagmawPlan loneLeft = strategy.Propose(
        loneMounted, ordinaryMage, "dps");
    assert(!HasMechanic(loneRight, "launch_native_hook"));
    assert(loneLeft.Interaction.has_value());
    assert(loneLeft.Interaction->Id.Mechanic == "mount_free_pincer");
    assert(HasMechanic(loneLeft, "pincer_approach"));

    // Once both assigned actors occupy distinct left/right pincers, each
    // submits its existing native spell against the same spike.
    Blackboard pairReady = loneMounted;
    pairReady.Players[3].VehicleGuid = pairReady.Summons[0].Guid;
    AdaptiveMagmawPlan leftHook = strategy.Propose(
        pairReady, ordinaryMage, "dps");
    AdaptiveMagmawPlan rightHook = strategy.Propose(
        pairReady, ordinaryWarlock, "dps");
    assert(leftHook.Interaction.has_value());
    assert(rightHook.Interaction.has_value());
    assert(leftHook.Interaction->Id.Mechanic == "launch_native_hook");
    assert(rightHook.Interaction->Id.Mechanic == "launch_native_hook");
    auto const* leftVehicleHook = std::get_if<VehicleAction>(
        &leftHook.Interaction->Action);
    auto const* rightVehicleHook = std::get_if<VehicleAction>(
        &rightHook.Interaction->Action);
    assert(leftVehicleHook && rightVehicleHook);
    assert(leftVehicleHook->SpellId == 77917u);
    assert(rightVehicleHook->SpellId == 77941u);
    assert(leftVehicleHook->Target == pairReady.Summons.back().Guid);
    assert(rightVehicleHook->Target == leftVehicleHook->Target);

    // A shared pincer, an unresolved vehicle, or a dead peer cannot satisfy
    // the native two-aura requirement and therefore emits no hook.
    Blackboard samePincer = pairReady;
    samePincer.Players[4].VehicleGuid = samePincer.Summons[0].Guid;
    assert(!HasMechanic(strategy.Propose(
        samePincer, ordinaryMage, "dps"), "launch_native_hook"));
    assert(!HasMechanic(strategy.Propose(
        samePincer, ordinaryWarlock, "dps"), "launch_native_hook"));

    Blackboard unresolvedVehicle = pairReady;
    unresolvedVehicle.Players[3].VehicleGuid = ObjectGuid(
        HighGuid::Unit, AdaptiveMagmawStrategy::PincerLeftEntry, uint32(999));
    assert(!HasMechanic(strategy.Propose(
        unresolvedVehicle, ordinaryMage, "dps"), "launch_native_hook"));
    assert(!HasMechanic(strategy.Propose(
        unresolvedVehicle, ordinaryWarlock, "dps"), "launch_native_hook"));

    Blackboard deadPeer = pairReady;
    deadPeer.Players[3].Alive = false;
    deadPeer.Players[6].Alive = false;
    deadPeer.Players[1].Alive = false;
    assert(!HasMechanic(strategy.Propose(
        deadPeer, ordinaryWarlock, "dps"), "launch_native_hook"));

    Blackboard openApproach = base;
    AddPincerWindow(openApproach, true);
    for (ObjectGuid guid : { ordinaryMage, ordinaryWarlock })
    {
        AdaptiveMagmawPlan plan = strategy.Propose(openApproach, guid, "dps");
        assert(plan.Interaction.has_value());
        assert(plan.Interaction->Id.Mechanic == "mount_free_pincer");
        auto const* mount = std::get_if<SpellClick>(
            &plan.Interaction->Action);
        assert(mount && mount->Target == openApproach.Hostiles.front().Guid);
        assert(HasMechanic(plan, "pincer_approach"));
    }
    AdaptiveMagmawPlan thirdEligible = strategy.Propose(
        openApproach, ordinaryElemental, "dps");
    assert(!HasMechanic(thirdEligible, "mount_free_pincer"));
    assert(!HasMechanic(thirdEligible, "pincer_approach"));

    // A warning before the click window gives the same eligible pair the
    // existing preposition path. The fixed baiters remain ordinary support.
    Blackboard warning = base;
    AddPincerWarning(warning);
    for (ObjectGuid guid : { ordinaryMage, ordinaryWarlock })
    {
        AdaptiveMagmawPlan plan = strategy.Propose(warning, guid, "dps");
        assert(HasMechanic(plan, "pincer_preposition"));
    }
    for (ObjectGuid guid : { fixedMage, fixedHunter })
    {
        AdaptiveMagmawPlan plan = strategy.Propose(warning, guid, "dps");
        assert(!HasMechanic(plan, "pincer_preposition"));
        assert(!HasMechanic(plan, "pincer_approach"));
    }

    // With only one ordinary DPS, the non-tank fallback fills the second
    // slot with the healer. It still skips both fixed baiters and never
    // admits the tank. The healer approaches but mounts only after the DPS
    // holds a pincer, so its no-cast seat always completes the pair.
    Blackboard fallback = base;
    fallback.Players = { base.Players[0], base.Players[1], base.Players[2],
        base.Players[3], base.Players[5] };
    AddPincerWindow(fallback, true);
    AdaptiveMagmawPlan fallbackDps = strategy.Propose(
        fallback, ordinaryMage, "dps");
    AdaptiveMagmawPlan fallbackHealer = strategy.Propose(
        fallback, healer, "healer");
    AdaptiveMagmawPlan fallbackFixedMage = strategy.Propose(
        fallback, fixedMage, "dps");
    AdaptiveMagmawPlan fallbackFixedHunter = strategy.Propose(
        fallback, fixedHunter, "dps");
    AdaptiveMagmawPlan fallbackTank = strategy.Propose(
        fallback, tank, "tank");
    assert(fallbackDps.Interaction.has_value());
    assert(fallbackDps.Interaction->Id.Mechanic == "mount_free_pincer");
    assert(!fallbackHealer.Interaction.has_value());
    assert(HasMechanic(fallbackHealer, "pincer_approach"));
    Blackboard fallbackDpsSeated = fallback;
    fallbackDpsSeated.Players[3].VehicleGuid = fallbackDpsSeated.Summons[0].Guid;
    AdaptiveMagmawPlan seatedPartnerHealer = strategy.Propose(
        fallbackDpsSeated, healer, "healer");
    assert(seatedPartnerHealer.Interaction.has_value());
    assert(seatedPartnerHealer.Interaction->Id.Mechanic
        == "mount_free_pincer");
    assert(!HasMechanic(fallbackFixedMage, "mount_free_pincer"));
    assert(!HasMechanic(fallbackFixedHunter, "mount_free_pincer"));
    assert(!HasMechanic(fallbackTank, "mount_free_pincer"));

    // Reordering observations cannot change the raw-GUID DPS preference or
    // the fixed-baiter exclusion.
    Blackboard reordered = openApproach;
    std::reverse(reordered.Players.begin(), reordered.Players.end());
    for (ObjectGuid guid : { fixedMage, fixedHunter, ordinaryMage,
            ordinaryWarlock, ordinaryElemental })
    {
        AdaptiveMagmawPlan orderedPlan = strategy.Propose(
            openApproach, guid, "dps");
        AdaptiveMagmawPlan reorderedPlan = strategy.Propose(
            reordered, guid, "dps");
        assert(std::string(InteractionMechanic(orderedPlan))
            == InteractionMechanic(reorderedPlan));
        assert(std::string(MovementMechanic(orderedPlan))
            == MovementMechanic(reorderedPlan));
    }
}
''',
        encoding="utf-8",
    )
    _compile_and_run(source, binary)


def test_magmaw_hook_riders_prefer_lowest_load_healer(tmp_path: Path) -> None:
    source = tmp_path / "magmaw_hook_riders.cpp"
    binary = tmp_path / "magmaw_hook_riders"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include <algorithm>
#include <cassert>
#include <set>
#include <string>

using namespace BotEncounter;
using RiderSet = std::set<uint32>;

std::string ObjectGuid::ToString() const
{
    return std::to_string(GetRawValue());
}

static char const* const HookMechanics[] = { "pincer_preposition",
    "pincer_approach", "mount_free_pincer", "launch_native_hook",
    "release_pincer_seat" };

static ActorSnapshot Player(uint32 guid, char const* role, char const* spec)
{
    ActorSnapshot player;
    player.Guid = ObjectGuid(HighGuid::Player, guid);
    player.Kind = ActorKind::Player;
    player.Role = role;
    player.ClassSpec = spec;
    player.Position = { 30.0f, 0.0f, 210.0f };
    player.HealthPct = 100.0f;
    player.Alive = true;
    return player;
}

// The 10N baseline roster: Balance holds the lowest DPS GUID, Fire A and
// Survival are the fixed pillar baiters, and three healers are present.
static Blackboard LiveRoster()
{
    Blackboard board;
    board.CurrentScope = Scope{
        "hook-riders", 7, 0, 4, "bwd.magmaw.encounter", 669, 1, "magmaw" };
    board.Revision = 33;
    board.ObservedAtMs = 1788793560680;
    board.NativeBossState = "in_progress";
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Route.NavigationHints = { { 0.0f, -1.0f, 210.0f } };
    ActorSnapshot tank = Player(30002, "tank", "blood_death_knight");
    tank.Position = { 0.0f, 0.0f, 210.0f };
    board.Players = { tank,
        Player(30001, "dps", "balance_druid"),
        Player(30003, "healer", "restoration_druid"),
        Player(30004, "healer", "holy_paladin"),
        Player(30005, "healer", "discipline_priest"),
        Player(30006, "dps", "fire_mage"),
        Player(30007, "dps", "fire_mage"),
        Player(30008, "dps", "affliction_warlock"),
        Player(30009, "dps", "survival_hunter"),
        Player(30010, "dps", "elemental_shaman") };
    ActorSnapshot boss;
    boss.Guid = ObjectGuid(HighGuid::Unit, AdaptiveMagmawStrategy::BossEntry,
        uint32(39));
    boss.Entry = AdaptiveMagmawStrategy::BossEntry;
    boss.Alive = boss.Attackable = boss.Selectable = boss.InCombat = true;
    boss.Position = { 0.0f, 0.0f, 210.0f };
    boss.VictimGuid = tank.Guid;
    board.Hostiles = { boss };
    return board;
}

static ActorSnapshot& Member(Blackboard& board, uint32 guid)
{
    auto itr = std::find_if(board.Players.begin(), board.Players.end(),
        [guid](ActorSnapshot const& player)
        {
            return player.Guid.GetCounter() == guid;
        });
    assert(itr != board.Players.end());
    return *itr;
}

static void Remove(Blackboard& board, std::initializer_list<uint32> guids)
{
    for (uint32 guid : guids)
        board.Players.erase(std::remove_if(board.Players.begin(),
            board.Players.end(), [guid](ActorSnapshot const& player)
            {
                return player.Guid.GetCounter() == guid;
            }), board.Players.end());
}

static void OpenWindow(Blackboard& board)
{
    board.Hostiles.front().Interactable = true;
    ActorSnapshot left = board.Hostiles.front();
    left.Guid = ObjectGuid(HighGuid::Unit,
        AdaptiveMagmawStrategy::PincerLeftEntry, uint32(700));
    left.Entry = AdaptiveMagmawStrategy::PincerLeftEntry;
    left.Interactable = false;
    ActorSnapshot right = left;
    right.Guid = ObjectGuid(HighGuid::Unit,
        AdaptiveMagmawStrategy::PincerRightEntry, uint32(702));
    right.Entry = AdaptiveMagmawStrategy::PincerRightEntry;
    ActorSnapshot spike = left;
    spike.Guid = ObjectGuid(HighGuid::Unit, AdaptiveMagmawStrategy::SpikeEntry,
        uint32(701));
    spike.Entry = AdaptiveMagmawStrategy::SpikeEntry;
    board.Summons = { left, right, spike };
}

static void Warn(Blackboard& board)
{
    board.Hostiles.front().Interactable = false;
    board.Summons.clear();
    Member(board, 30002).Auras = {
        AuraSnapshot{ 89773u, board.Hostiles.front().Guid, 1, 0 } };
}

static void Seat(Blackboard& board, uint32 guid, std::size_t pincer)
{
    Member(board, guid).VehicleGuid = board.Summons.at(pincer).Guid;
}

static bool HasMechanic(AdaptiveMagmawPlan const& plan, char const* mechanic)
{
    for (BotNativeAction::Candidate const& candidate : plan.Movement.Proposals())
        if (candidate.Id.Mechanic == mechanic)
            return true;
    return plan.Interaction && plan.Interaction->Id.Mechanic == mechanic;
}

static RiderSet Holders(Blackboard const& board, char const* mechanic)
{
    AdaptiveMagmawStrategy strategy;
    RiderSet holders;
    for (ActorSnapshot const& player : board.Players)
        if (HasMechanic(strategy.Propose(board, player.Guid, player.Role),
                mechanic))
            holders.insert(player.Guid.GetCounter());
    return holders;
}

// Preposition, approach, mount and launch are separate callers of the one
// rider list. Each must name the same pair, independent of board order.
static void AssertRiders(Blackboard const& board, char const* mechanic,
    RiderSet const& expected)
{
    assert(Holders(board, mechanic) == expected);
    Blackboard reversed = board;
    std::reverse(reversed.Players.begin(), reversed.Players.end());
    assert(Holders(reversed, mechanic) == expected);
}

static RiderSet AnyHookHolders(Blackboard const& board)
{
    RiderSet holders;
    for (char const* mechanic : HookMechanics)
    {
        RiderSet const next = Holders(board, mechanic);
        holders.insert(next.begin(), next.end());
    }
    return holders;
}

static AdaptiveMagmawPlan PlanFor(Blackboard const& board, uint32 guid)
{
    AdaptiveMagmawStrategy strategy;
    ActorSnapshot const* bot = board.FindActor(ObjectGuid(HighGuid::Player,
        guid));
    assert(bot);
    return strategy.Propose(board, bot->Guid, bot->Role);
}

static void Mangle(Blackboard& board, float tankHealthPct)
{
    ActorSnapshot& tank = Member(board, 30002);
    tank.Auras = { AuraSnapshot{ 89773u, board.Hostiles.front().Guid, 1, 0 } };
    tank.HealthPct = tankHealthPct;
}

int main()
{
    RiderSet const discAndFire{ 30005, 30007 };
    RiderSet const twoDps{ 30007, 30008 };
    RiderSet const priest{ 30005 };
    RiderSet const fireB{ 30007 };

    // Three living healers: Discipline replaces Balance and Fire B keeps the
    // DPS seat. Every caller agrees, from the warning to the native launch.
    Blackboard warning = LiveRoster();
    Warn(warning);
    AssertRiders(warning, "pincer_preposition", discAndFire);
    Blackboard open = LiveRoster();
    OpenWindow(open);
    AssertRiders(open, "pincer_approach", discAndFire);
    assert(AnyHookHolders(open) == discAndFire);

    // Partner late: the priest mounts last. While Fire B is still on its way
    // the priest waits at the approach point with no interaction, so the
    // heal candidate keeps its cast lane.
    AssertRiders(open, "mount_free_pincer", fireB);
    Blackboard waiting = open;
    Member(waiting, 30005).Position = { 0.0f, -4.0f, 210.0f };
    AdaptiveMagmawPlan const waitingPriest = PlanFor(waiting, 30005);
    assert(!waitingPriest.Interaction.has_value());
    assert(waitingPriest.Movement.Empty());
    Blackboard partnerSeated = open;
    Seat(partnerSeated, 30007, 1);
    AssertRiders(partnerSeated, "mount_free_pincer", priest);
    Blackboard seated = partnerSeated;
    Seat(seated, 30005, 0);
    AssertRiders(seated, "launch_native_hook", discAndFire);
    assert(PlanFor(seated, 30005).Movement.Empty());
    assert(Holders(seated, "release_pincer_seat").empty());

    // Partner dead before the priest mounts: the next DPS partners it and
    // the priest again waits for that seat.
    Blackboard partnerDead = open;
    Member(partnerDead, 30007).Alive = false;
    AssertRiders(partnerDead, "pincer_approach", RiderSet{ 30005, 30008 });
    AssertRiders(partnerDead, "mount_free_pincer", RiderSet{ 30008 });

    // Partner dies after the priest mounted. With healers and tank healthy
    // the priest keeps its seat for the replacement while the window lasts.
    Blackboard brokenPair = seated;
    Member(brokenPair, 30007).Alive = false;
    Member(brokenPair, 30007).VehicleGuid = ObjectGuid();
    AssertRiders(brokenPair, "mount_free_pincer", RiderSet{ 30008 });
    assert(Holders(brokenPair, "launch_native_hook").empty());
    assert(Holders(brokenPair, "release_pincer_seat").empty());
    // The window closes first: the seat can never pair, so the priest leaves.
    Blackboard brokenClosed = brokenPair;
    brokenClosed.Hostiles.front().Interactable = false;
    AssertRiders(brokenClosed, "release_pincer_seat", priest);
    assert(Holders(brokenClosed, "mount_free_pincer").empty());

    // Healer death while seated in a complete pair: the launch goes out.
    Blackboard seatedHealerLoss = seated;
    Member(seatedHealerLoss, 30003).Alive = false;
    AssertRiders(seatedHealerLoss, "launch_native_hook", discAndFire);
    assert(Holders(seatedHealerLoss, "release_pincer_seat").empty());
    // Healer death with the pair broken: the priest leaves at once, even in
    // an open window, and two DPS take the hook.
    Blackboard brokenHealerLoss = brokenPair;
    Member(brokenHealerLoss, 30003).Alive = false;
    AssertRiders(brokenHealerLoss, "release_pincer_seat", priest);
    AssertRiders(brokenHealerLoss, "mount_free_pincer",
        RiderSet{ 30008, 30010 });
    AdaptiveMagmawPlan const releasedPriest = PlanFor(brokenHealerLoss, 30005);
    assert(releasedPriest.Movement.Empty());
    assert(std::holds_alternative<BotNativeAction::VehicleExit>(
        releasedPriest.Interaction->Action));
    assert(releasedPriest.Interaction->ActionPriority
        == BotActionArbitration::Priority::Mechanic);

    // Mangled tank below 35% with the pair broken: the priest leaves, and no
    // other healer is conscripted in its place.
    Blackboard brokenTankCritical = brokenPair;
    Mangle(brokenTankCritical, 34.0f);
    AssertRiders(brokenTankCritical, "release_pincer_seat", priest);
    AssertRiders(brokenTankCritical, "mount_free_pincer",
        RiderSet{ 30008, 30010 });
    Blackboard brokenTankLow = brokenPair;
    Mangle(brokenTankLow, 36.0f);
    assert(Holders(brokenTankLow, "release_pincer_seat").empty());
    AssertRiders(brokenTankLow, "mount_free_pincer", RiderSet{ 30008 });
    // A complete pair launches even with the tank critical: the impale is
    // what frees the tank from Mangle.
    Blackboard pairTankCritical = seated;
    Mangle(pairTankCritical, 20.0f);
    AssertRiders(pairTankCritical, "launch_native_hook", discAndFire);
    assert(Holders(pairTankCritical, "release_pincer_seat").empty());
    // An unseated priest still completes a waiting pair when the tank is
    // critical; its mount triggers the launch.
    Blackboard mountTankCritical = partnerSeated;
    Mangle(mountTankCritical, 20.0f);
    AssertRiders(mountTankCritical, "mount_free_pincer", priest);

    // After the impale the window closes: the priest leaves without waiting
    // for the 3.5 s native eject, then the unpaired DPS leaves too.
    Blackboard impaled = seated;
    impaled.Hostiles.front().Interactable = false;
    AssertRiders(impaled, "release_pincer_seat", priest);
    assert(Holders(impaled, "launch_native_hook").empty());
    Blackboard impaledPriestOut = impaled;
    Member(impaledPriestOut, 30005).VehicleGuid = ObjectGuid();
    AssertRiders(impaledPriestOut, "release_pincer_seat", fireB);
    // A lone DPS inside the open window keeps waiting for its partner.
    assert(Holders(partnerSeated, "release_pincer_seat").empty());

    // After the ride the priest holds no hook duty and is an ordinary healer.
    Blackboard afterRide = LiveRoster();
    assert(AnyHookHolders(afterRide).empty());

    // Balance is excluded while two other DPS are eligible, even when no
    // healer may ride and Balance holds the lowest DPS GUID.
    Blackboard oneHealer = LiveRoster();
    Remove(oneHealer, { 30004, 30005 });
    OpenWindow(oneHealer);
    AssertRiders(oneHealer, "mount_free_pincer", twoDps);

    // Fallback: fewer than three living healers keeps every healer healing.
    Blackboard twoHealers = LiveRoster();
    Remove(twoHealers, { 30004 });
    OpenWindow(twoHealers);
    AssertRiders(twoHealers, "mount_free_pincer", twoDps);
    Blackboard deadHealer = LiveRoster();
    Member(deadHealer, 30003).Alive = false;
    OpenWindow(deadHealer);
    AssertRiders(deadHealer, "mount_free_pincer", twoDps);
    Blackboard deadHealerWarning = LiveRoster();
    Member(deadHealerWarning, 30004).Alive = false;
    Warn(deadHealerWarning);
    AssertRiders(deadHealerWarning, "pincer_preposition", twoDps);

    // Fallback: healers outside the closed load ranking never ride.
    Blackboard unrankedHealers = LiveRoster();
    for (uint32 guid : { 30003u, 30004u, 30005u })
        Member(unrankedHealers, guid).ClassSpec = "unclassified_healer";
    OpenWindow(unrankedHealers);
    AssertRiders(unrankedHealers, "mount_free_pincer", twoDps);

    // Without Discipline the lowest-ranked listed healer rides, ties by GUID.
    Blackboard noDiscipline = LiveRoster();
    Member(noDiscipline, 30005).ClassSpec = "restoration_druid";
    OpenWindow(noDiscipline);
    AssertRiders(noDiscipline, "pincer_approach", RiderSet{ 30003, 30007 });
    AssertRiders(noDiscipline, "mount_free_pincer", fireB);
    Blackboard holyPriest = LiveRoster();
    Member(holyPriest, 30004).ClassSpec = "holy_priest";
    Member(holyPriest, 30005).ClassSpec = "holy_paladin";
    OpenWindow(holyPriest);
    AssertRiders(holyPriest, "pincer_approach", RiderSet{ 30004, 30007 });

    // Fallback: with no eligible healer and one ordinary DPS, the previous
    // DPS order fills the second seat, which reaches Balance.
    Blackboard onlyBalanceLeft = LiveRoster();
    Remove(onlyBalanceLeft, { 30004, 30008, 30010 });
    OpenWindow(onlyBalanceLeft);
    AssertRiders(onlyBalanceLeft, "mount_free_pincer",
        RiderSet{ 30001, 30007 });

    // An eligible healer pairs with Balance only when Balance is the last
    // non-baiter DPS; Balance mounts first.
    Blackboard healerAndBalance = LiveRoster();
    Remove(healerAndBalance, { 30007, 30008, 30010 });
    OpenWindow(healerAndBalance);
    AssertRiders(healerAndBalance, "pincer_approach",
        RiderSet{ 30001, 30005 });
    AssertRiders(healerAndBalance, "mount_free_pincer", RiderSet{ 30001 });

    // Fallback: with no ordinary DPS, the next non-tank fills the second
    // seat after the selected healer. Two healer riders mount in list order.
    Blackboard healersOnly = LiveRoster();
    Remove(healersOnly, { 30001, 30007, 30008, 30010 });
    OpenWindow(healersOnly);
    AssertRiders(healersOnly, "pincer_approach", RiderSet{ 30003, 30005 });
    AssertRiders(healersOnly, "mount_free_pincer", priest);
    Seat(healersOnly, 30005, 0);
    AssertRiders(healersOnly, "mount_free_pincer", RiderSet{ 30003 });

    // Tanks and fixed baiters never ride; with nobody else nobody mounts.
    Blackboard nobody = LiveRoster();
    Remove(nobody, { 30001, 30003, 30004, 30005, 30007, 30008, 30010 });
    OpenWindow(nobody);
    assert(AnyHookHolders(nobody).empty());
    for (Blackboard const* board : { &open, &warning, &seated, &oneHealer,
             &twoHealers, &healersOnly, &brokenHealerLoss, &impaled })
    {
        RiderSet const holders = AnyHookHolders(*board);
        for (uint32 excluded : { 30002u, 30006u, 30009u })
            assert(!holders.count(excluded));
    }
}
''',
        encoding="utf-8",
    )
    _compile_and_run(source, binary)
