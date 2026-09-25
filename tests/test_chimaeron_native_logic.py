"""Compiled unit tests for the pure Chimaeron script rules (boss_chimaeron_logic.h).

boss_chimaeron.cpp routes the Caustic Slime target filter and the Massacre
observation clamp through these helpers; the source checks below pin that use.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent"
LOGIC = SCRIPTS / "boss_chimaeron_logic.h"
SCRIPT = SCRIPTS / "boss_chimaeron.cpp"

PROGRAM = r'''
#include "boss_chimaeron_logic.h"
#include <cstdio>

using namespace BlackwingDescent::Chimaeron::Logic;

static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { ++failures; \
    std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #condition); } } while (0)

// Compile-time use proves the helpers stay constexpr and dependency-free.
static_assert(ClassifyCausticSlimeCandidate(true, false) == SlimeCandidate::Excluded);
static_assert(PlanCausticSlimeTargets(8, 1, 2).FromEligible == 2);

int main()
{
    // The current victim is never a candidate, with or without Break.
    CHECK(ClassifyCausticSlimeCandidate(true, false) == SlimeCandidate::Excluded);
    CHECK(ClassifyCausticSlimeCandidate(true, true) == SlimeCandidate::Excluded);
    CHECK(ClassifyCausticSlimeCandidate(false, true) == SlimeCandidate::BreakAffected);
    CHECK(ClassifyCausticSlimeCandidate(false, false) == SlimeCandidate::Eligible);

    CHECK(CausticSlimeTargetCount(false) == 2);
    CHECK(CausticSlimeTargetCount(true) == 4);

    // Enough players without Break: Break-affected players are never chosen.
    CausticSlimePick pick = PlanCausticSlimeTargets(8, 1, 2);
    CHECK(pick.FromEligible == 2 && pick.FromBreakAffected == 0);
    // Shortfall: Break-affected players fill it, never more than asked.
    pick = PlanCausticSlimeTargets(1, 3, 2);
    CHECK(pick.FromEligible == 1 && pick.FromBreakAffected == 1);
    pick = PlanCausticSlimeTargets(0, 1, 4);
    CHECK(pick.FromEligible == 0 && pick.FromBreakAffected == 1);
    pick = PlanCausticSlimeTargets(0, 0, 2);
    CHECK(pick.FromEligible == 0 && pick.FromBreakAffected == 0);
    pick = PlanCausticSlimeTargets(3, 5, 4);
    CHECK(pick.FromEligible == 3 && pick.FromBreakAffected == 1);

    constexpr std::uint32_t repeat = 30000;
    // Outside phase one there is no Massacre schedule, even if an old event
    // is still queued.
    CHECK(MassacreRemainingMs(false, false, 12000, repeat) == NoMassacreTime);
    CHECK(MassacreRemainingMs(false, true, 0, repeat) == NoMassacreTime);
    // Casting: the sequence is active now.
    CHECK(MassacreRemainingMs(true, true, 29000, repeat) == 0);
    // Scheduled: the event's remaining time, up to the repeat interval.
    CHECK(MassacreRemainingMs(true, false, 26000, repeat) == 26000);
    CHECK(MassacreRemainingMs(true, false, repeat, repeat) == repeat);
    CHECK(MassacreRemainingMs(true, false, 0, repeat) == 0);
    // Overdue (held by a cast): EventMap's unsigned subtraction wrapped.
    CHECK(MassacreRemainingMs(true, false, 0xFFFFFF00u, repeat) == 0);
    CHECK(MassacreRemainingMs(true, false, repeat + 1, repeat) == 0);
    // Not scheduled at all.
    CHECK(MassacreRemainingMs(true, false, NoMassacreTime, repeat) == NoMassacreTime);

    if (failures)
        std::fprintf(stderr, "%d checks failed\n", failures);
    return failures ? 1 : 0;
}
'''


def test_chimaeron_script_logic_compiles_and_holds(tmp_path: Path) -> None:
    source = tmp_path / "chimaeron_logic.cpp"
    binary = tmp_path / "chimaeron_logic"
    source.write_text(PROGRAM)
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(SCRIPTS),
                    str(source), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_script_routes_its_rules_through_the_helpers() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert '#include "boss_chimaeron_logic.h"' in source
    assert "Logic::ClassifyCausticSlimeCandidate(" in source
    assert "Logic::PlanCausticSlimeTargets(" in source
    assert "Logic::CausticSlimeTargetCount(caster->GetMap()->Is25ManRaid())" in source
    assert "Logic::MassacreRemainingMs(events.IsInPhase(PHASE_1), castingMassacre," in source
    # The logic header needs nothing from the core.
    logic = LOGIC.read_text(encoding="utf-8")
    includes = [line for line in logic.splitlines() if line.startswith("#include")]
    assert includes == ["#include <algorithm>", "#include <cstddef>", "#include <cstdint>",
                        "#include <limits>"]
