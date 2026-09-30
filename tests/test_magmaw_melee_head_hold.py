"""Melee DPS stay on the Exposed Head of Magmaw instead of the ranged formation restore.

Round 3 (tier-11 gear) is the first canonical run whose kills reach the head window with melee DPS
(Retribution, Assassination); the accepted legacy roster had none. Melee have no configured ranged
combat range, so the ranged head hold (InConfiguredHeadRange) never admitted them and the Mechanic
ranged_formation_restore pulled them to the support anchor beside the body for the whole window.
Exercised through AdaptiveMagmawStrategy::Propose.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INCLUDES = (
    "src/server/game",
    "src/server/game/Entities/Object",
    "src/common",
    "src/common/Utilities",
    "src/common/Logging",
)

FIXTURE = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include <cassert>
#include <cmath>
#include <string>
#include <vector>

using namespace BotEncounter;

namespace
{
ActorSnapshot Player(uint32 guid, char const* role, char const* spec, Vector3 position)
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

ActorSnapshot Boss()
{
    ActorSnapshot boss;
    boss.Guid = ObjectGuid(HighGuid::Unit, AdaptiveMagmawStrategy::BossEntry, uint32(700));
    boss.Entry = AdaptiveMagmawStrategy::BossEntry;
    boss.Alive = true;
    boss.Attackable = true;
    boss.Selectable = true;
    boss.InCombat = true;
    boss.Position = { -302.467f, -31.7101f, 210.848f };
    return boss;
}

ActorSnapshot Head(Vector3 position)
{
    ActorSnapshot head;
    head.Guid = ObjectGuid(HighGuid::Unit, AdaptiveMagmawStrategy::HeadEntry, uint32(701));
    head.Entry = AdaptiveMagmawStrategy::HeadEntry;
    head.Alive = true;
    head.Attackable = true;
    head.Selectable = true;
    head.InCombat = true;
    head.Position = position;
    return head;
}

Vector3 RoomSide(ActorSnapshot const& boss)
{
    float dx = -308.9f - boss.Position.X;
    float dy = -36.5f - boss.Position.Y;
    float const length = std::hypot(dx, dy);
    return { boss.Position.X + dx / length * 30.0f, boss.Position.Y + dy / length * 30.0f, 211.815f };
}

Blackboard Board(ActorSnapshot const& boss, std::vector<ActorSnapshot> hostiles,
    std::vector<ActorSnapshot> players)
{
    Blackboard board;
    board.CurrentScope = Scope{ "melee-head-hold", 11, 0, 4, "bwd.magmaw.encounter", 669, 2, "magmaw" };
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Route.NavigationHints = { RoomSide(boss) };
    board.Route.PullPermitted = true;
    board.NativeBossState = "in_progress";
    board.Revision = 900;
    board.ObservedAtMs = 130000;
    board.Players = std::move(players);
    board.Hostiles = std::move(hostiles);
    return board;
}

std::vector<ActorSnapshot> Raid(ActorSnapshot const& tested)
{
    // Two lower-GUID ranged DPS own the pincer duty, so the tested actor never does.
    return { Player(30002, "dps", "affliction_warlock", { -309.5f, -37.0f, 211.815f }),
        Player(30003, "dps", "affliction_warlock", { -309.5f, -37.5f, 211.815f }),
        tested };
}

bool Restores(AdaptiveMagmawPlan const& plan)
{
    if (plan.Movement.Empty())
        return false;
    return plan.Movement->Id.Mechanic == "ranged_formation_restore";
}
}

int main()
{
    ActorSnapshot const boss = Boss();
    // The head's seat position, away from the support anchor on the room-side ray.
    ActorSnapshot const head = Head({ -290.0f, -22.0f, 211.0f });
    Vector3 const nearHead{ -292.0f, -24.0f, 211.815f };
    AdaptiveMagmawStrategy strategy;

    for (char const* spec : { "retribution_paladin", "assassination_rogue" })
    {
        ActorSnapshot tested = Player(30008, "dps", spec, nearHead);
        // Head window: damage the head and keep melee closure (no formation restore).
        {
            MagmawEventMovementTransitionState state;
            Blackboard board = Board(boss, { boss, head }, Raid(tested));
            auto plan = strategy.Propose(board, tested.Guid, "dps", nullptr, false, false,
                nullptr, nullptr, &state);
            assert(plan.OwnsNode);
            assert(plan.DamageTarget == head.Guid);
            assert(!Restores(plan));
            assert(!plan.SuppressOffense);
        }
        // Control: without an exposed head the same position is restored to the support anchor.
        {
            MagmawEventMovementTransitionState state;
            Blackboard board = Board(boss, { boss }, Raid(tested));
            auto plan = strategy.Propose(board, tested.Guid, "dps", nullptr, false, false,
                nullptr, nullptr, &state);
            assert(plan.DamageTarget == boss.Guid);
            assert(Restores(plan));
        }
        // A head that is no longer selectable (covered) sends melee back to Magmaw and formation.
        {
            MagmawEventMovementTransitionState state;
            ActorSnapshot covered = head;
            covered.Selectable = false;
            Blackboard board = Board(boss, { boss, covered }, Raid(tested));
            auto plan = strategy.Propose(board, tested.Guid, "dps", nullptr, false, false,
                nullptr, nullptr, &state);
            assert(plan.DamageTarget == boss.Guid);
            assert(Restores(plan));
        }
    }

    // A ranged spec without a configured range keeps the prior behavior: formation restore.
    {
        ActorSnapshot tested = Player(30008, "dps", "elemental_shaman", nearHead);
        MagmawEventMovementTransitionState state;
        Blackboard board = Board(boss, { boss, head }, Raid(tested));
        auto plan = strategy.Propose(board, tested.Guid, "dps", nullptr, false, false,
            nullptr, nullptr, &state);
        assert(plan.DamageTarget == head.Guid);
        assert(Restores(plan));
    }
    // Healers are not head attackers either.
    {
        ActorSnapshot tested = Player(30008, "healer", "holy_paladin", nearHead);
        MagmawEventMovementTransitionState state;
        Blackboard board = Board(boss, { boss, head }, Raid(tested));
        auto plan = strategy.Propose(board, tested.Guid, "healer", nullptr, false, false,
            nullptr, nullptr, &state);
        assert(Restores(plan));
    }
    return 0;
}
'''


def test_magmaw_melee_dps_hold_the_exposed_head(tmp_path: Path) -> None:
    source = tmp_path / "magmaw_melee_head_hold.cpp"
    binary = tmp_path / "magmaw_melee_head_hold"
    source.write_text(FIXTURE, encoding="utf-8")
    subprocess.run(
        ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
         *[arg for path in INCLUDES for arg in ("-I", str(ROOT / path))],
         str(source), "-o", str(binary)],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)
