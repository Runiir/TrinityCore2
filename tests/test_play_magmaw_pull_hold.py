from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INCLUDES = [
    "src/server/game",
    "src/server/game/Entities/Object",
    "src/common",
    "src/common/Utilities",
    "src/common/Logging",
    "src/common/Debugging",
]


# Play raids pull Magmaw on the human leader's timer: bots stage and hold
# the pull while Route.PullPermitted is false, the designated tank pulls once
# it is true, and anyone engaging the boss releases every bot. Validation
# snapshots always carry PullPermitted = true.
PROGRAM = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include <cstdio>
#include <string>

using namespace BotEncounter;

std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }

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

static Blackboard Board(bool pullPermitted, bool bossEngaged)
{
    Blackboard board;
    board.CurrentScope = Scope{ "play-pull", 7, 0, 4, "bwd.magmaw.encounter", 669, 1, "magmaw" };
    board.Revision = 5;
    board.NativeBossState = bossEngaged ? "in_progress" : "not_started";
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Route.PullPermitted = pullPermitted;
    board.Players = {
        Player(30001, "dps", "balance_druid"),
        Player(30002, "tank", "blood_death_knight"),
        Player(30006, "dps", "fire_mage"),
        Player(30007, "dps", "fire_mage"),
        Player(30009, "dps", "survival_hunter"),
    };
    ActorSnapshot boss;
    boss.Guid = ObjectGuid(HighGuid::Unit, AdaptiveMagmawStrategy::BossEntry, uint32(39));
    boss.Entry = AdaptiveMagmawStrategy::BossEntry;
    boss.Alive = boss.Attackable = boss.Selectable = true;
    boss.InCombat = bossEngaged;
    board.Hostiles = { boss };
    return board;
}

static int failures = 0;

static void Expect(bool condition, char const* label)
{
    if (!condition)
    {
        std::fprintf(stderr, "FAIL: %s\n", label);
        ++failures;
    }
}

int main()
{
    AdaptiveMagmawStrategy strategy;
    ObjectGuid const tank(HighGuid::Player, uint32(30002));
    ObjectGuid const mage(HighGuid::Player, uint32(30006));
    ObjectGuid const boss(HighGuid::Unit, AdaptiveMagmawStrategy::BossEntry, uint32(39));

    // No timer yet: every bot, the pull tank included, holds the pull.
    Blackboard held = Board(false, false);
    AdaptiveMagmawPlan tankHeld = strategy.Propose(held, tank, "tank");
    Expect(tankHeld.SuppressOffense && tankHeld.SuppressReason == "prepull_pull_timer_wait",
        "tank holds for the pull timer");
    AdaptiveMagmawPlan mageHeld = strategy.Propose(held, mage, "dps");
    Expect(mageHeld.SuppressOffense && mageHeld.SuppressReason == "prepull_pull_timer_wait",
        "dps holds for the pull timer");

    // Timer expired: the designated tank pulls, the others wait for it.
    Blackboard released = Board(true, false);
    AdaptiveMagmawPlan tankPulls = strategy.Propose(released, tank, "tank");
    Expect(!tankPulls.SuppressOffense && tankPulls.DamageTarget == boss, "tank pulls on zero");
    AdaptiveMagmawPlan mageWaits = strategy.Propose(released, mage, "dps");
    Expect(mageWaits.SuppressOffense && mageWaits.SuppressReason == "prepull_pull_owner_wait",
        "dps waits for the tank pull");

    // A human pulled before zero: the fight is on for everyone.
    Blackboard engaged = Board(false, true);
    AdaptiveMagmawPlan tankFights = strategy.Propose(engaged, tank, "tank");
    Expect(tankFights.SuppressReason != "prepull_pull_timer_wait", "tank fights a human pull");
    AdaptiveMagmawPlan mageFights = strategy.Propose(engaged, mage, "dps");
    Expect(mageFights.SuppressReason != "prepull_pull_timer_wait", "dps fights a human pull");
    return failures == 0 ? 0 : 1;
}
'''


def test_magmaw_pull_waits_for_the_play_timer_or_a_human_pull(tmp_path: Path) -> None:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(PROGRAM)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_pull_permission_defaults_true_and_only_play_publishes_it() -> None:
    blackboard = (ROOT / "src/server/game/Bots/BotEncounterBlackboard.h").read_text()
    assert "bool PullPermitted = true;" in blackboard
    writers = [
        path.name
        for path in (ROOT / "src/server/game/Bots").rglob("*.cpp")
        if "Route.PullPermitted =" in path.read_text()
    ]
    assert writers == ["BotWorldPopulationMgrEncounterBlackboard.cpp"]
    publisher = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrEncounterBlackboard.cpp").read_text()
    block = publisher[publisher.index("if (Cohort().Purpose == CohortPurpose::Play)"):]
    assert block.index("Route.PullPermitted =") < block.index("\n    }\n")
