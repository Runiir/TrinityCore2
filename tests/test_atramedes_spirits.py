"""Header-only decision tests for the Dark Iron spirit packs before Atramedes.

Round 2 wiped on bwd.atramedes.north_spirits: the whole raid stood inside
the four-spirit pack (ranged within 1-10 yd of every spirit for 60 s), every
Thunderclap (15 yd) hit about eight players, and Moltenfist died first, so
the other three gained Thunderclap. The C++ program below drives the
production headers with that geometry and checks the kill order, the ranged
standoff half circle and that the plan leaves the route in charge.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INCLUDES = [
    "-I", str(ROOT / "src/server/game"),
    "-I", str(ROOT / "src/server/game/Entities/Object"),
    "-I", str(ROOT / "src/common"),
    "-I", str(ROOT / "src/common/Utilities"),
    "-I", str(ROOT / "src/common/Logging"),
    "-I", str(ROOT / "src/common/Debugging"),
]

PROGRAM = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAdaptiveAtramedesStrategy.h"
#include <cassert>
#include <cstdio>
#include <string>
#include <variant>
#include <vector>

using namespace BotEncounter;
namespace A = BotEncounter::Atramedes;
namespace S = BotEncounter::Atramedes::Spirits;
namespace G = BotEncounter::Atramedes::Geometry;

static ObjectGuid PlayerGuid(uint32 counter) { return ObjectGuid(HighGuid::Player, counter); }
static ObjectGuid UnitGuid(uint32 entry, uint32 counter) { return ObjectGuid(HighGuid::Unit, entry, counter); }

enum Slot : uint32
{
    Tank = 11003001, Balance, Hunter, Mage, HolyPaladin, Retribution,
    Discipline, Rogue, Elemental, Warlock
};

static ActorSnapshot MakePlayer(uint32 counter, char const* role, char const* spec, float x, float y)
{
    ActorSnapshot actor;
    actor.Guid = PlayerGuid(counter);
    actor.Kind = ActorKind::Player;
    actor.Role = role;
    actor.ClassSpec = spec;
    actor.Position = { x, y, 75.0f };
    actor.Alive = true;
    actor.InCombat = true;
    return actor;
}

static ActorSnapshot MakeSpirit(uint32 entry, uint32 counter, float x, float y)
{
    ActorSnapshot actor;
    actor.Guid = UnitGuid(entry, counter);
    actor.Entry = entry;
    actor.Kind = ActorKind::Hostile;
    actor.Position = { x, y, 75.0f };
    actor.Alive = true;
    actor.Attackable = true;
    actor.Selectable = true;
    actor.InCombat = true;
    actor.VictimGuid = PlayerGuid(Tank);
    return actor;
}

// Round 2 geometry: bots provisioned on the pack centre (147.9, -189.3),
// spirits where the combat log saw them.
static Blackboard NorthBoard(bool engaged = true)
{
    Blackboard board;
    board.Route.NodeId = std::string(S::NorthNode);
    board.ObservedAtMs = 5000;
    board.Revision = 3;
    board.Players = {
        MakePlayer(Tank, "tank", "blood_death_knight", 148.0f, -189.0f),
        MakePlayer(Balance, "dps", "balance_druid", 154.0f, -186.0f),
        MakePlayer(Hunter, "dps", "beast_mastery_hunter", 154.0f, -186.0f),
        MakePlayer(Mage, "dps", "fire_mage", 154.0f, -186.0f),
        MakePlayer(HolyPaladin, "healer", "holy_paladin", 154.0f, -189.0f),
        MakePlayer(Retribution, "dps", "retribution_paladin", 148.0f, -189.0f),
        MakePlayer(Discipline, "healer", "discipline_priest", 154.0f, -189.0f),
        MakePlayer(Rogue, "dps", "assassination_rogue", 148.0f, -189.0f),
        MakePlayer(Elemental, "dps", "elemental_shaman", 148.0f, -189.0f),
        MakePlayer(Warlock, "dps", "demonology_warlock", 154.0f, -186.0f),
    };
    board.Hostiles = {
        MakeSpirit(S::Shadowforge, 56, 153.0f, -190.0f),
        MakeSpirit(S::Anvilrage, 55, 144.0f, -186.0f),
        MakeSpirit(S::Moltenfist, 21, 142.5f, -187.0f),
        MakeSpirit(S::Corehammer, 43, 152.5f, -192.5f),
    };
    for (ActorSnapshot& spirit : board.Hostiles)
        spirit.InCombat = engaged;
    return board;
}

static Blackboard SouthBoard()
{
    Blackboard board = NorthBoard();
    board.Route.NodeId = std::string(S::SouthNode);
    board.Hostiles = {
        MakeSpirit(S::Ironstar, 60, 142.0f, -257.0f),
        MakeSpirit(S::Burningeye, 61, 151.0f, -257.0f),
        MakeSpirit(S::Thaurissan, 62, 143.0f, -263.0f),
        MakeSpirit(S::Angerforge, 63, 152.0f, -262.0f),
    };
    for (ActorSnapshot& player : board.Players)
        player.Position = { 147.0f, -259.0f, 75.0f };
    return board;
}

static ActorSnapshot& Member(Blackboard& board, uint32 counter)
{
    for (ActorSnapshot& player : board.Players)
        if (player.Guid == PlayerGuid(counter))
            return player;
    assert(false);
    return board.Players.front();
}

static ActorSnapshot& Spirit(Blackboard& board, uint32 entry)
{
    for (ActorSnapshot& hostile : board.Hostiles)
        if (hostile.Entry == entry)
            return hostile;
    assert(false);
    return board.Hostiles.front();
}

static AdaptiveAtramedesPlan Plan(Blackboard const& board, uint32 counter, char const* role = "dps")
{
    return AdaptiveAtramedesStrategy().Propose(board, PlayerGuid(counter), role);
}

static BotNativeAction::Move const* MoveOf(AdaptiveAtramedesPlan const& plan)
{
    return plan.Movement ? std::get_if<BotNativeAction::Move>(&plan.Movement->Action) : nullptr;
}

static std::string Mechanic(AdaptiveAtramedesPlan const& plan)
{
    return plan.Movement ? plan.Movement->Id.Mechanic : std::string();
}

static std::vector<uint32> const StandoffSlots{ Balance, Hunter, Mage, HolyPaladin,
    Discipline, Elemental, Warlock };

static void TestNothingBeforeThePull()
{
    Blackboard const board = NorthBoard(false);
    for (ActorSnapshot const& player : board.Players)
    {
        AdaptiveAtramedesPlan const plan = AdaptiveAtramedesStrategy().Propose(board,
            player.Guid, player.Role.c_str());
        assert(!plan.OwnsNode && plan.DamageTarget.IsEmpty() && !plan.Movement);
    }
    // Any other node (the regroup, the bell) is not a spirit node.
    Blackboard regroup = NorthBoard();
    regroup.Route.NodeId = "bwd.atramedes.regroup";
    assert(Plan(regroup, Mage).DamageTarget.IsEmpty() && !Plan(regroup, Mage).Movement);
}

static void TestNorthKillOrder()
{
    Blackboard board = NorthBoard();
    // The route keeps the node. The tank's target is the kill-order spirit:
    // on a trash route the shared group focus is the tank's own target
    // (FindValidationRouteGroupFocusTarget), so this is what the raid hits.
    AdaptiveAtramedesPlan const tank = Plan(board, Tank, "tank");
    assert(!tank.OwnsNode && !tank.Movement);
    assert(tank.DamageTarget == UnitGuid(S::Corehammer, 43));
    assert(tank.Duty == "spirit_tank");
    for (uint32 slot : { Balance, Hunter, Mage, Retribution, Rogue, Elemental, Warlock,
            HolyPaladin, Discipline })
        assert(Plan(board, slot).DamageTarget == UnitGuid(S::Corehammer, 43));
    // Corehammer first (Burden of the Crown then buffs the raid), Moltenfist
    // before Shadowforge so Chain Lightning is never handed on.
    Spirit(board, S::Corehammer).Alive = false;
    assert(Plan(board, Mage).DamageTarget == UnitGuid(S::Anvilrage, 55));
    assert(Plan(board, Tank, "tank").DamageTarget == UnitGuid(S::Anvilrage, 55));
    Spirit(board, S::Anvilrage).Alive = false;
    assert(Plan(board, Rogue).DamageTarget == UnitGuid(S::Moltenfist, 21));
    assert(Plan(board, Tank, "tank").DamageTarget == UnitGuid(S::Moltenfist, 21));
    Spirit(board, S::Moltenfist).Alive = false;
    assert(Plan(board, Warlock).DamageTarget == UnitGuid(S::Shadowforge, 56));
    assert(Plan(board, Tank, "tank").DamageTarget == UnitGuid(S::Shadowforge, 56));
    // The route's shared focus defers to the same target
    // (spirit_kill_order_focus.patch): empty off the spirit nodes and before
    // the pull.
    assert(S::OrderedKillTarget(board) == UnitGuid(S::Shadowforge, 56));
    assert(S::OrderedKillTarget(NorthBoard(false)).IsEmpty());
    {
        Blackboard regroup = NorthBoard();
        regroup.Route.NodeId = "bwd.atramedes.regroup";
        assert(S::OrderedKillTarget(regroup).IsEmpty());
    }
    // An unattackable spirit is skipped.
    board = NorthBoard();
    Spirit(board, S::Corehammer).Attackable = false;
    assert(Plan(board, Mage).DamageTarget == UnitGuid(S::Anvilrage, 55));
}

static void TestSouthKillOrder()
{
    Blackboard board = SouthBoard();
    assert(Plan(board, Mage).DamageTarget == UnitGuid(S::Angerforge, 63));
    assert(Plan(board, Tank, "tank").DamageTarget == UnitGuid(S::Angerforge, 63));
    Spirit(board, S::Angerforge).Alive = false;
    assert(Plan(board, Mage).DamageTarget == UnitGuid(S::Thaurissan, 62));
    Spirit(board, S::Thaurissan).Alive = false;
    assert(Plan(board, Mage).DamageTarget == UnitGuid(S::Burningeye, 61));
    Spirit(board, S::Burningeye).Alive = false;
    assert(Plan(board, Mage).DamageTarget == UnitGuid(S::Ironstar, 60));
}

// Every standoff slot, for the round 2 geometry of each pack.
static void CheckSlots(Blackboard const& board, Vector3 const& otherPack)
{
    S::Pack const pack = S::BuildPack(board);
    std::vector<Vector3> slots;
    for (uint32 slot : StandoffSlots)
    {
        std::optional<Vector3> const at = S::StandoffSlot(board, pack, PlayerGuid(Tank),
            PlayerGuid(slot));
        assert(at);
        for (ActorSnapshot const* spirit : pack.Engaged)
        {
            float const distance = G::Distance2d(spirit->Position, *at);
            // Outside Thunderclap (15 yd + 1.5 player reach), inside 40 yd
            // spell range of every spirit.
            assert(distance >= S::DangerRadius);
            assert(distance <= 38.0f);
        }
        // Far from the other pack (20 yd aggro + its 6 yd spread + margin)
        // and on the arena floor inside the shield ring.
        assert(G::Distance2d(*at, otherPack) >= 35.0f);
        assert(G::Distance2d(*at, A::ArenaCenter) <= 50.0f);
        slots.push_back(*at);
    }
    // Chain Lightning jumps 12.5 yd: no two ranged within that.
    for (std::size_t i = 0; i < slots.size(); ++i)
        for (std::size_t j = i + 1; j < slots.size(); ++j)
            assert(G::Distance2d(slots[i], slots[j]) > S::ChainJumpRadius);
}

static void TestStandoff()
{
    Blackboard board = NorthBoard();
    CheckSlots(board, { 146.87f, -259.78f, 75.0f });
    CheckSlots(SouthBoard(), { 147.92f, -189.29f, 75.0f });

    // Inside the pack (the round 2 positions): every ranged and healer leaves
    // with survival priority, pre-empting a cast.
    S::Pack const pack = S::BuildPack(board);
    for (uint32 slot : StandoffSlots)
    {
        AdaptiveAtramedesPlan const plan = Plan(board, slot,
            slot == HolyPaladin || slot == Discipline ? "healer" : "dps");
        assert(plan.Duty == "spirit_ranged");
        assert(Mechanic(plan) == "spirit_thunderclap_exit");
        assert(plan.Movement->ActionPriority == BotActionArbitration::Priority::Survival);
        assert(MoveOf(plan)->PreemptCasting);
        std::optional<Vector3> const at = S::StandoffSlot(board, pack, PlayerGuid(Tank),
            PlayerGuid(slot));
        assert(G::Distance2d({ MoveOf(plan)->X, MoveOf(plan)->Y, 75.0f }, *at) < 0.01f);
    }
    // Melee stay in melee range.
    for (uint32 slot : { Retribution, Rogue })
    {
        AdaptiveAtramedesPlan const plan = Plan(board, slot);
        assert(plan.Duty == "spirit_melee" && !plan.Movement);
        assert(!plan.DamageTarget.IsEmpty());
    }

    // At the slot: hold (no move every decision).
    std::optional<Vector3> const mageSlot = S::StandoffSlot(board, pack, PlayerGuid(Tank),
        PlayerGuid(Mage));
    Member(board, Mage).Position = { mageSlot->X + 2.0f, mageSlot->Y, 75.0f };
    assert(!Plan(board, Mage).Movement);
    // Off the slot but outside the Thunderclap: a positioning move only.
    Member(board, Mage).Position = { mageSlot->X + 8.0f, mageSlot->Y, 75.0f };
    assert(S::NearestSpiritDistance(pack, Member(board, Mage).Position) >= S::DangerRadius);
    AdaptiveAtramedesPlan const drift = Plan(board, Mage);
    assert(Mechanic(drift) == "spirit_ranged_standoff");
    assert(drift.Movement->ActionPriority == BotActionArbitration::Priority::Mechanic);
    assert(!MoveOf(drift)->PreemptCasting);

    // Slots do not shift when a ranged dies.
    Member(board, Balance).Alive = false;
    std::optional<Vector3> const after = S::StandoffSlot(board, pack, PlayerGuid(Tank),
        PlayerGuid(Mage));
    assert(G::Distance2d(*after, *mageSlot) < 0.01f);
    // A dead bot plans nothing.
    assert(!Plan(board, Balance).Movement && Plan(board, Balance).DamageTarget.IsEmpty());
}

static void TestStrayPull()
{
    // A south spirit pulled during the north pack is danger and a target
    // after the north order.
    Blackboard board = NorthBoard();
    ActorSnapshot stray = SouthBoard().Hostiles.front();
    stray.Position = { 150.0f, -214.0f, 75.0f };
    board.Hostiles.push_back(stray);
    for (uint32 entry : S::NorthKillOrder)
        Spirit(board, entry).Alive = false;
    assert(Plan(board, Mage).DamageTarget == stray.Guid);
    Member(board, Mage).Position = { 151.0f, -210.0f, 75.0f };
    assert(Mechanic(Plan(board, Mage)) == "spirit_thunderclap_exit");
}

int main()
{
    TestNothingBeforeThePull();
    TestNorthKillOrder();
    TestSouthKillOrder();
    TestStandoff();
    TestStrayPull();
    std::puts("atramedes spirits ok");
    return 0;
}
'''


def test_atramedes_spirit_packs(tmp_path: Path) -> None:
    source = tmp_path / "atramedes_spirits.cpp"
    binary = tmp_path / "atramedes_spirits"
    source.write_text(PROGRAM, encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O0",
                    *INCLUDES, str(source), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], check=True, cwd=ROOT, capture_output=True, text=True)
    assert "atramedes spirits ok" in result.stdout


def test_spirit_nodes_match_the_route_rows() -> None:
    import json

    scenarios = json.loads((ROOT / "experiments/configs/validation_scenarios_cata_001.json")
                           .read_text(encoding="utf-8"))
    header = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/"
              "Atramedes/BotAtramedesSpirits.h").read_text(encoding="utf-8")
    rows = [row for group in ("scenarios", "diagnostic_scenarios")
            for scenario in scenarios[group] for row in scenario.get("route") or []
            if str(row.get("node_id", "")).endswith("_spirits")
            and str(row.get("node_id", "")).startswith("bwd.atramedes.")]
    assert rows
    for row in rows:
        assert f'"{row["node_id"]}"' in header
        for entry in row["pack_target_entries"]:
            assert str(entry) in header
