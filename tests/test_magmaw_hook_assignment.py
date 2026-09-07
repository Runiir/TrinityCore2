from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_magmaw_hook_ownership_excludes_fixed_baiters(tmp_path: Path) -> None:
    source = tmp_path / "magmaw_hook_assignment.cpp"
    binary = tmp_path / "magmaw_hook_assignment"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include <algorithm>
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
    // slot with the existing board-order healer. It still skips both fixed
    // baiters and never admits the tank.
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
    assert(fallbackHealer.Interaction.has_value());
    assert(fallbackDps.Interaction->Id.Mechanic == "mount_free_pincer");
    assert(fallbackHealer.Interaction->Id.Mechanic == "mount_free_pincer");
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
