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
                assert(move.Z == 211.815002f);
                if (warning)
                {
                    // The warning wait point stays on the room ray, 2.5 yd
                    // beyond Magmaw's 3D melee reach (15 + 1.5 + 4/3).
                    auto const& boss = airborne.Hostiles.front().Position;
                    float const reach = std::sqrt(std::pow(move.X - boss.X, 2.0f)
                        + std::pow(move.Y - boss.Y, 2.0f)
                        + std::pow(move.Z - boss.Z, 2.0f));
                    assert(std::fabs(reach - (15.0f + 1.5f + 4.0f / 3.0f + 2.5f))
                        < 0.01f);
                    assert(move.Y < boss.Y);
                    found = true;
                    continue;
                }
                assert(std::fabs(move.Y + 34.0812607f) < 0.001f);
                // Behavioral red before producer correction: elevated declared
                // endpoint fails the unchanged native admission envelope.
                assert(admission(move));
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


def test_magmaw_hook_riders_are_dps_with_healers_last(tmp_path: Path) -> None:
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
    RiderSet const twoDps{ 30007, 30008 };
    RiderSet const fireB{ 30007 };

    // Live roster: Fire B and Affliction ride. Balance and every healer stay
    // out, from the warning to the native launch, in any board order.
    Blackboard warning = LiveRoster();
    Warn(warning);
    AssertRiders(warning, "pincer_preposition", twoDps);
    Blackboard open = LiveRoster();
    OpenWindow(open);
    AssertRiders(open, "pincer_approach", twoDps);
    AssertRiders(open, "mount_free_pincer", twoDps);
    assert(AnyHookHolders(open) == twoDps);
    Blackboard seated = open;
    Seat(seated, 30007, 0);
    Seat(seated, 30008, 1);
    AssertRiders(seated, "launch_native_hook", twoDps);
    assert(Holders(seated, "release_pincer_seat").empty());
    assert(PlanFor(seated, 30007).Movement.Empty());

    // The Discipline Priest keeps Mangle support: no hook duty, and the
    // warning sends it to the Mangle midpoint stage like the other healers.
    for (uint32 healer : { 30003u, 30004u, 30005u })
        assert(HasMechanic(PlanFor(warning, healer), "mangle_midpoint_stage"));

    // Partner dead before mounting: the next non-Balance DPS replaces it.
    Blackboard partnerDead = open;
    Member(partnerDead, 30008).Alive = false;
    AssertRiders(partnerDead, "pincer_approach", RiderSet{ 30007, 30010 });
    AssertRiders(partnerDead, "mount_free_pincer", RiderSet{ 30007, 30010 });
    // Partner dies after one DPS mounted: the seated DPS keeps its seat for
    // the replacement while the window is open.
    Blackboard brokenPair = open;
    Seat(brokenPair, 30007, 0);
    Member(brokenPair, 30008).Alive = false;
    AssertRiders(brokenPair, "mount_free_pincer", RiderSet{ 30010 });
    assert(Holders(brokenPair, "release_pincer_seat").empty());
    assert(Holders(brokenPair, "launch_native_hook").empty());
    // The window closes first: the seat can never pair, so the DPS leaves.
    Blackboard brokenClosed = brokenPair;
    brokenClosed.Hostiles.front().Interactable = false;
    AssertRiders(brokenClosed, "release_pincer_seat", fireB);
    AdaptiveMagmawPlan const released = PlanFor(brokenClosed, 30007);
    assert(std::holds_alternative<BotNativeAction::VehicleExit>(
        released.Interaction->Action));
    // A complete DPS pair launches through a healer death or a critical tank.
    Blackboard seatedHealerLoss = seated;
    Member(seatedHealerLoss, 30003).Alive = false;
    AssertRiders(seatedHealerLoss, "launch_native_hook", twoDps);
    Blackboard pairTankCritical = seated;
    Mangle(pairTankCritical, 20.0f);
    AssertRiders(pairTankCritical, "launch_native_hook", twoDps);
    assert(Holders(pairTankCritical, "release_pincer_seat").empty());
    // After the impale a complete DPS pair waits for the native eject.
    Blackboard impaled = seated;
    impaled.Hostiles.front().Interactable = false;
    assert(Holders(impaled, "release_pincer_seat").empty());

    // After the ride nobody holds hook duty.
    assert(AnyHookHolders(LiveRoster()).empty());

    // Healer count never changes the DPS pair.
    Blackboard oneHealer = LiveRoster();
    Remove(oneHealer, { 30004, 30005 });
    OpenWindow(oneHealer);
    AssertRiders(oneHealer, "mount_free_pincer", twoDps);

    // Fallback: one ordinary DPS left, so the previous DPS order brings
    // Balance in before any healer.
    Blackboard onlyBalanceLeft = LiveRoster();
    Remove(onlyBalanceLeft, { 30008, 30010 });
    OpenWindow(onlyBalanceLeft);
    AssertRiders(onlyBalanceLeft, "mount_free_pincer",
        RiderSet{ 30001, 30007 });

    // Last resort: one DPS in total, so the lowest-GUID healer fills the
    // second seat. It mounts only after the DPS holds a pincer.
    Blackboard lastResort = LiveRoster();
    Remove(lastResort, { 30001, 30008, 30010 });
    OpenWindow(lastResort);
    RiderSet const druidAndFire{ 30003, 30007 };
    AssertRiders(lastResort, "pincer_approach", druidAndFire);
    AssertRiders(lastResort, "mount_free_pincer", fireB);
    Blackboard lrPartnerSeated = lastResort;
    Seat(lrPartnerSeated, 30007, 1);
    AssertRiders(lrPartnerSeated, "mount_free_pincer", RiderSet{ 30003 });
    Blackboard lrSeated = lrPartnerSeated;
    Seat(lrSeated, 30003, 0);
    AssertRiders(lrSeated, "launch_native_hook", druidAndFire);
    // Its partner dies after it mounted: with three healers and the tank
    // healthy it keeps the seat while the window is open.
    Blackboard lrBroken = lrSeated;
    Member(lrBroken, 30007).Alive = false;
    Member(lrBroken, 30007).VehicleGuid = ObjectGuid();
    assert(Holders(lrBroken, "release_pincer_seat").empty());
    Blackboard lrBrokenClosed = lrBroken;
    lrBrokenClosed.Hostiles.front().Interactable = false;
    AssertRiders(lrBrokenClosed, "release_pincer_seat", RiderSet{ 30003 });
    // Another healer dies, or the mangled tank drops below 35%: it leaves
    // at once, even inside the window.
    Blackboard lrHealerLoss = lrBroken;
    Member(lrHealerLoss, 30005).Alive = false;
    AssertRiders(lrHealerLoss, "release_pincer_seat", RiderSet{ 30003 });
    AdaptiveMagmawPlan const releasedHealer = PlanFor(lrHealerLoss, 30003);
    assert(releasedHealer.Movement.Empty());
    Blackboard lrTankCritical = lrBroken;
    Mangle(lrTankCritical, 34.0f);
    AssertRiders(lrTankCritical, "release_pincer_seat", RiderSet{ 30003 });
    Blackboard lrTankLow = lrBroken;
    Mangle(lrTankLow, 36.0f);
    assert(Holders(lrTankLow, "release_pincer_seat").empty());
    // A complete pair still launches with the tank critical: the impale is
    // what frees the tank from Mangle.
    Blackboard lrPairTankCritical = lrSeated;
    Mangle(lrPairTankCritical, 20.0f);
    AssertRiders(lrPairTankCritical, "launch_native_hook", druidAndFire);
    assert(Holders(lrPairTankCritical, "release_pincer_seat").empty());
    // After the impale the healer leaves without the 3.5 s native eject,
    // then its now unpaired DPS partner leaves too.
    Blackboard lrImpaled = lrSeated;
    lrImpaled.Hostiles.front().Interactable = false;
    AssertRiders(lrImpaled, "release_pincer_seat", RiderSet{ 30003 });
    Member(lrImpaled, 30003).VehicleGuid = ObjectGuid();
    AssertRiders(lrImpaled, "release_pincer_seat", fireB);

    // No DPS at all: two healers ride and mount in list order.
    Blackboard healersOnly = LiveRoster();
    Remove(healersOnly, { 30001, 30007, 30008, 30010 });
    OpenWindow(healersOnly);
    AssertRiders(healersOnly, "pincer_approach", RiderSet{ 30003, 30004 });
    AssertRiders(healersOnly, "mount_free_pincer", RiderSet{ 30003 });
    Seat(healersOnly, 30003, 0);
    AssertRiders(healersOnly, "mount_free_pincer", RiderSet{ 30004 });

    // Tanks and fixed baiters never ride; with nobody else nobody mounts.
    Blackboard nobody = LiveRoster();
    Remove(nobody, { 30001, 30003, 30004, 30005, 30007, 30008, 30010 });
    OpenWindow(nobody);
    assert(AnyHookHolders(nobody).empty());
    for (Blackboard const* board : { &open, &warning, &seated, &oneHealer,
             &lastResort, &healersOnly, &lrHealerLoss, &brokenClosed })
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
