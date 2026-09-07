from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FALLBACK = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelFallback.cpp"


def statement(source: str, marker: str) -> str:
    start = source.index(marker)
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]
    raise AssertionError(f"unterminated statement: {marker}")


def fixture_source(restore_block: str) -> str:
    return r'''#include <cassert>
#include <cstdint>
#include <string>
#include <string_view>

using ObjectGuid = std::uint64_t;

namespace BotActionArbitration
{
struct Outcome
{
    std::string Reason;

    static Outcome Retryable(std::string_view reason)
    {
        return { std::string(reason) };
    }
};
}

struct Creature;

struct Unit
{
    virtual ~Unit() = default;

    virtual Creature* ToCreature()
    {
        return nullptr;
    }

    bool IsAlive() const
    {
        return alive;
    }

    bool IsInCombat() const
    {
        return inCombat;
    }

    ObjectGuid GetGUID() const
    {
        return guid;
    }

    ObjectGuid guid = 0;
    bool alive = true;
    bool attackable = true;
    bool inCombat = false;
};

struct Creature : Unit
{
    explicit Creature(ObjectGuid creatureGuid)
    {
        guid = creatureGuid;
    }

    Creature* ToCreature() override
    {
        return this;
    }

    bool immediateNextEncounter = false;
};

struct StubBot
{
    bool inCombat = true;

    bool IsValidAttackTarget(Unit* target) const
    {
        return target && target->attackable;
    }

    bool IsInCombat() const
    {
        return inCombat;
    }
};

struct StubState
{
    ObjectGuid TargetGuid = 0;
    std::string LastRecoveryMode;
    std::string LastRecoveryResult;
    std::string LastNoProgressReason;
};

struct StubContext
{
    Unit* Target = nullptr;
    StubBot* Bot = nullptr;
    std::string Action = "validation_route_hold";
    StubState State;
};

struct RouteAttempt
{
    BotActionArbitration::Outcome RouteOutcome;
};

struct RestoreFixture
{
    bool IsImmediateNextValidationRouteEncounterMember(
        Creature const* creature) const
    {
        return creature && creature->immediateNextEncounter;
    }

    StubContext Run(Unit* initialTarget, ObjectGuid initialStateTarget,
        Unit* routeTarget, StubBot* bot)
    {
        StubContext context;
        context.Target = initialTarget;
        context.State.TargetGuid = initialStateTarget;
        context.Bot = bot;

        // This is the production call's result boundary. The route resolver
        // has already replaced Target and TargetGuid before the yield block.
        Unit* const targetBeforeRoute = context.Target;
        ObjectGuid const stateTargetBeforeRoute = context.State.TargetGuid;
        context.Target = routeTarget;
        context.State.TargetGuid = routeTarget
            ? routeTarget->GetGUID() : ObjectGuid{};
        RouteAttempt routeAttemptStorage;
        RouteAttempt* routeAttempt = &routeAttemptStorage;
        bool const routeYield = true;
''' + restore_block + r'''
        return context;
    }
};

static void AssertRestored(StubContext const& context, Unit* target,
    ObjectGuid guid)
{
    assert(context.Target == target);
    assert(context.State.TargetGuid == guid);
}

int main()
{
    RestoreFixture fixture;
    StubBot bot;
    Creature current(27);
    Creature protectedOld(39);
    protectedOld.immediateNextEncounter = true;
    Creature ordinaryOld(40);

    // A usable route result must survive the yield, even when the old target
    // is the next encounter member that native combat must protect.
    StubContext currentWins = fixture.Run(&protectedOld,
        protectedOld.GetGUID(), &current, &bot);
    AssertRestored(currentWins, &current, current.GetGUID());

    // Clearing a protected old target must not reintroduce it when the route
    // produced no current target.
    StubContext protectedCleared = fixture.Run(&protectedOld,
        protectedOld.GetGUID(), nullptr, &bot);
    AssertRestored(protectedCleared, nullptr, 0);

    // A dead route result may remain dead or be cleared by the route, but the
    // protected old target must never be restored over that result.
    Creature deadCurrent(41);
    deadCurrent.alive = false;
    StubContext deadResult = fixture.Run(&protectedOld,
        protectedOld.GetGUID(), &deadCurrent, &bot);
    assert(deadResult.Target == nullptr || deadResult.Target == &deadCurrent);
    assert(deadResult.Target != &protectedOld);
    assert(deadResult.State.TargetGuid != protectedOld.GetGUID());

    // An unusable current result can recover an ordinary live combat target.
    StubContext ordinaryRestored = fixture.Run(&ordinaryOld,
        ordinaryOld.GetGUID(), nullptr, &bot);
    AssertRestored(ordinaryRestored, &ordinaryOld, ordinaryOld.GetGUID());

    // A valid current result always wins over an ordinary old target too.
    StubContext validCurrent = fixture.Run(&ordinaryOld,
        ordinaryOld.GetGUID(), &current, &bot);
    AssertRestored(validCurrent, &current, current.GetGUID());

    // The old target's existing liveness, attackability, and combat checks
    // remain rejection gates for restoration.
    Creature deadOld(50);
    deadOld.alive = false;
    StubContext deadOldRejected = fixture.Run(&deadOld, deadOld.GetGUID(),
        nullptr, &bot);
    AssertRestored(deadOldRejected, nullptr, 0);

    ordinaryOld.attackable = false;
    StubContext unattackableOldRejected = fixture.Run(&ordinaryOld,
        ordinaryOld.GetGUID(), nullptr, &bot);
    AssertRestored(unattackableOldRejected, nullptr, 0);
    ordinaryOld.attackable = true;

    bot.inCombat = false;
    ordinaryOld.inCombat = false;
    StubContext nonCombatOldRejected = fixture.Run(&ordinaryOld,
        ordinaryOld.GetGUID(), nullptr, &bot);
    AssertRestored(nonCombatOldRejected, nullptr, 0);
}
'''


def compile_fixture(tmp_path: Path, restore_block: str) -> Path:
    source = tmp_path / "validation_route_target_restore.cpp"
    binary = tmp_path / "validation_route_target_restore"
    source.write_text(fixture_source(restore_block), encoding="utf-8")
    subprocess.run(
        [
            "g++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            str(source),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    return binary


def test_validation_route_target_restore_behavior(tmp_path: Path) -> None:
    fallback = FALLBACK.read_text(encoding="utf-8")
    restore_block = statement(fallback, "if (routeYield)")
    binary = compile_fixture(tmp_path, restore_block)
    subprocess.run([str(binary)], check=True, cwd=ROOT)

