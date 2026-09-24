from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAGMAW = "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw"
INCLUDES = [
    "src/server/game",
    "src/server/game/Entities/Object",
    "src/common",
    "src/common/Utilities",
    "src/common/Logging",
    "src/common/Debugging",
]


def _compile_and_run(tmp_path: Path, program: str) -> None:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(
        command
        + [str(source), str(ROOT / MAGMAW / "BotMagmawDutyPlan.cpp"), "-o", str(binary)],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


# The accepted Magmaw 10N roster (validation_routes.jsonl, scenario
# blackwing_descent_10n_magmaw_diagnostic) and the owners today's selectors
# give it at the first parasite wave. Baiters, mushrooms and the tank taunt
# are confirmed by the accepted b5-d1898555 kill evidence
# (tests/fixtures/magmaw_full_roster_duties_v1.json); hook riders, pull tank
# and Bloodlust owner are not in kill evidence and are pinned here.
PROGRAM = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawDutyPlan.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotAdaptiveMagmawStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBaiterRotation.h"
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

static Blackboard Board(char const* cohort)
{
    Blackboard board;
    board.CurrentScope = Scope{ cohort, 7, 0, 4, "bwd.magmaw.encounter", 669, 1,
        "magmaw" };
    board.Revision = 21;
    board.ObservedAtMs = 1790220781549;
    board.NativeBossState = "in_progress";
    board.Route.NodeId = "bwd.magmaw.encounter";
    board.Players = {
        Player(30001, "dps", "balance_druid"),
        Player(30002, "tank", "blood_death_knight"),
        Player(30003, "healer", "restoration_druid"),
        Player(30004, "healer", "holy_paladin"),
        Player(30005, "healer", "discipline_priest"),
        Player(30006, "dps", "fire_mage"),
        Player(30007, "dps", "fire_mage"),
        Player(30008, "dps", "affliction_warlock"),
        Player(30009, "dps", "survival_hunter"),
        Player(30010, "dps", "elemental_shaman"),
    };
    ActorSnapshot boss;
    boss.Guid = ObjectGuid(HighGuid::Unit, AdaptiveMagmawStrategy::BossEntry, uint32(39));
    boss.Entry = AdaptiveMagmawStrategy::BossEntry;
    boss.Alive = boss.Attackable = boss.Selectable = boss.InCombat = true;
    boss.VictimGuid = board.Players[1].Guid;
    board.Hostiles = { boss };
    return board;
}

static int Fail(char const* what, std::string const& json)
{
    std::fprintf(stderr, "FAIL %s: %s\n", what, json.c_str());
    return 1;
}

int main()
{
    std::string const expected = "{\"applies\":true,\"revision\":21,"
        "\"pull_tank\":30002,\"bait_mage\":30006,\"bait_hunter\":30009,"
        "\"hook_riders\":[30007,30008],\"mushroom_owners\":[30001],"
        "\"bloodlust_owner\":30010}";

    Blackboard const board = Board("full-roster");
    std::string json = BuildMagmawDutyPlanStatusJson(&board);
    if (json != expected)
        return Fail("full roster", json);
    // Observation is idempotent per revision: a second status read agrees.
    if (BuildMagmawDutyPlanStatusJson(&board) != expected)
        return Fail("repeat read", json);

    // External (human) members never enter the duty selectors, and
    // FindActor still resolves them for consumers that opt in.
    Blackboard withHumans = Board("with-humans");
    withHumans.ExternalPlayers = {
        Player(50001, "dps", "fire_mage"),
        Player(50002, "tank", "protection_paladin"),
        Player(50003, "dps", "elemental_shaman"),
    };
    json = BuildMagmawDutyPlanStatusJson(&withHumans);
    if (json != expected)
        return Fail("externals changed the plan", json);
    ActorSnapshot const* human = withHumans.FindActor(
        ObjectGuid(HighGuid::Player, uint32(50002)));
    if (!human || human->Role != "tank")
        return Fail("external lookup", json);

    // Today's rules, pinned: with the only tank dead there is no pull tank,
    // and a nine-player snapshot has no Bloodlust owner.
    Blackboard nine = Board("nine");
    nine.Players[1].Alive = false;
    nine.Players.pop_back();
    MagmawDutyPlan const partial = BuildMagmawDutyPlan(nine);
    if (!partial.Applies || !partial.PullTank.IsEmpty()
        || !partial.BloodlustOwner.IsEmpty())
        return Fail("nine", MagmawDutyPlanJson(partial));

    Blackboard offNode = Board("off-node");
    offNode.CurrentScope.NodeId = "bwd.magmaw.drudges";
    offNode.Route.NodeId = "bwd.magmaw.drudges";
    json = BuildMagmawDutyPlanStatusJson(&offNode);
    if (json != "{\"applies\":false,\"revision\":21}")
        return Fail("off node", json);
    json = BuildMagmawDutyPlanStatusJson(nullptr);
    if (json != "{\"applies\":false,\"revision\":0}")
        return Fail("no snapshot", json);
    return 0;
}
'''


def test_magmaw_duty_plan_reports_live_selectors_and_ignores_externals(
    tmp_path: Path,
) -> None:
    _compile_and_run(tmp_path, PROGRAM)


# Review finding (e4fa8a143a): the status command sees snapshot revisions no
# bot observes (wipe recovery, runback, partial rosters). A duty-plan read of
# such a snapshot must not latch the roster or switch the bait mage on the
# shared rotation that the bots act on.
PEEK_PROGRAM = PROGRAM.split("int main()")[0] + r"""
static ObjectGuid BotBaiter(Blackboard board, uint64 revision)
{
    board.Revision = revision;
    return MagmawParasitePolicy::ResolveFixedBaiters(board).first;
}

int main()
{
    // (a) the primary fire mage is absent from the status read's snapshot.
    Blackboard partial = Board("peek-a");
    partial.Players.erase(partial.Players.begin() + 5);
    BuildMagmawDutyPlanStatusJson(&partial);
    ObjectGuid const afterAbsent = BotBaiter(Board("peek-a"), 22);
    ObjectGuid const controlAbsent = BotBaiter(Board("peek-a-control"), 22);
    if (afterAbsent != controlAbsent || afterAbsent.GetCounter() != 30006)
        return Fail("absent-primary read moved the rotation",
            std::to_string(afterAbsent.GetCounter()));

    // (b) the primary fire mage is dead in the status read's snapshot.
    Blackboard dead = Board("peek-b");
    dead.Players[5].Alive = false;
    BuildMagmawDutyPlanStatusJson(&dead);
    ObjectGuid const afterDead = BotBaiter(Board("peek-b"), 22);
    ObjectGuid const controlDead = BotBaiter(Board("peek-b-control"), 22);
    if (afterDead != controlDead || afterDead.GetCounter() != 30006)
        return Fail("dead-primary read moved the rotation",
            std::to_string(afterDead.GetCounter()));

    // Once the bots have observed a revision, the receipt reports exactly
    // their baiters and hook riders.
    Blackboard observed = Board("peek-c");
    MagmawParasitePolicy::ResolveFixedBaiters(observed);
    MagmawDutyPlan const plan = BuildMagmawDutyPlan(observed);
    if (plan.BaitMage.GetCounter() != 30006 || plan.HookRiders.size() != 2
        || plan.HookRiders[0].GetCounter() != 30007)
        return Fail("observed receipt", MagmawDutyPlanJson(plan));
    return 0;
}
"""


def test_duty_plan_status_read_never_moves_the_baiter_rotation(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PEEK_PROGRAM)
