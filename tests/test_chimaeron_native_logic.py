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

    // 10N knockout cycle (WCL 10N census, DBM): never on the first Massacre of
    // a cycle, a roll on the second, certain on the third.
    CHECK(KnockoutChancePct(true, 0) == 0);
    CHECK(KnockoutChancePct(true, 1) == 0);
    CHECK(KnockoutChancePct(true, 2) == KnockoutChanceSecondMassacrePct);
    CHECK(KnockoutChancePct(true, 2) > 0 && KnockoutChancePct(true, 2) < 100);
    CHECK(KnockoutChancePct(true, 3) == 100);
    CHECK(KnockoutChancePct(true, 4) == 100);
    CHECK(KnockoutChancePct(true, 200) == 100);

    // 25N, 10H and 25H keep the previous roll: 40% at the first Massacre, 20
    // more points per miss, 100% at the fourth.
    CHECK(KnockoutChancePct(false, 0) == 40);
    CHECK(KnockoutChancePct(false, 1) == 40);
    CHECK(KnockoutChancePct(false, 2) == 60);
    CHECK(KnockoutChancePct(false, 3) == 80);
    CHECK(KnockoutChancePct(false, 4) == 100);
    CHECK(KnockoutChancePct(false, 5) == 100);
    CHECK(KnockoutChancePct(false, 200) == 100);
    // The two rules differ at every position before the certain knockout.
    for (unsigned position = 0; position <= 3; ++position)
        CHECK(KnockoutChancePct(true, position) != KnockoutChancePct(false, position));

    // Caustic Slime repeat: 6 s on 10N, the previous 5 s elsewhere.
    static_assert(CausticSlimeRepeatMs(true) == 6000u);
    static_assert(CausticSlimeRepeatMs(false) == 5000u);
    CHECK(CausticSlimeRepeatMs(true) == 6000u);
    CHECK(CausticSlimeRepeatMs(false) == 5000u);

    // Feud: Break and Double Attack are skipped on 10N only; elsewhere they
    // are cast whether or not Feud is up.
    CHECK(SkipsBreakAndDoubleAttack(true, true));
    CHECK(!SkipsBreakAndDoubleAttack(true, false));
    CHECK(!SkipsBreakAndDoubleAttack(false, true));
    CHECK(!SkipsBreakAndDoubleAttack(false, false));

    // Mortality: on 10N a Double Attack due inside Feud is held for Feud's end
    // (the opening Mortality attack is not consumed). Phase one keeps the
    // skip, no Feud means nothing to hold, and other modes never hold.
    static_assert(HoldsDoubleAttackForFeudEnd(true, true, true));
    CHECK(HoldsDoubleAttackForFeudEnd(true, true, true));
    CHECK(!HoldsDoubleAttackForFeudEnd(true, true, false));
    CHECK(!HoldsDoubleAttackForFeudEnd(true, false, true));
    CHECK(!HoldsDoubleAttackForFeudEnd(true, false, false));
    for (int feud = 0; feud <= 1; ++feud)
        for (int mortality = 0; mortality <= 1; ++mortality)
            CHECK(!HoldsDoubleAttackForFeudEnd(false, feud != 0, mortality != 0));

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
    # Knockout: the cycle count and the difficulty feed the helper, and the
    # count restarts on a knockout in every mode. The helper carries the
    # previous 40/60/80/100% roll for 25N/10H/25H, so the old field stays gone
    # (test_chimaeron_mode_gating.py pins the 10N gate itself).
    assert "++_massacresInCycle;" in source
    assert "roll_chance_i(Logic::KnockoutChancePct(IsTenNormal(), _massacresInCycle))" in source
    feud = source.index("DoCastSelf(SPELL_FEUD);")
    assert source.index("_massacresInCycle = 0;", feud) - feud < 80
    assert "_knockOutChance" not in source
    # Slime cadence and the Feud skip read their mode-dependent rules from the helpers.
    assert "events.Repeat(Logic::CausticSlimeRepeatMs(IsTenNormal()));" in source
    assert source.count("Logic::SkipsBreakAndDoubleAttack(IsTenNormal(), _isInFeud)") == 2
    # Mortality holds a Feud-time Double Attack for ACTION_END_FEUD, which schedules it.
    assert source.count("Logic::HoldsDoubleAttackForFeudEnd(IsTenNormal(), _isInFeud, events.IsInPhase(PHASE_2))") == 1
    assert "_doubleAttackHeldByFeud = false;" in source
    assert "events.ScheduleEvent(EVENT_DOUBLE_ATTACK, 1ms, 0, PHASE_2);" in source
    # The logic header needs nothing from the core.
    logic = LOGIC.read_text(encoding="utf-8")
    includes = [line for line in logic.splitlines() if line.startswith("#include")]
    assert includes == ["#include <algorithm>", "#include <cstddef>", "#include <cstdint>",
                        "#include <limits>"]
