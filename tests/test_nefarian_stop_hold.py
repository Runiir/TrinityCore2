"""The Nefarian warrior-path stop holds (third re-review, P1.2).

A bot leading bone warriors with no lawful leg is held by the candidate the
plan's WarriorStopHold produces (BotWorldPopulationMgrNefarianCandidates.cpp):
it clears the autonomous generator of the active motion slot (a native chase
included) and stops the spline, leaving a controlled effect alone, and it
renews a Hazard movement lease at the bot's own position. Every ordinary
movement producer, combat range recovery included (MoveBotToProfileRange, the
CombatRange owner at Combat priority, from the trained combat candidate that
claims no movement resource), converges on the movement executor, which
evaluates that lease before launching a point path or a chase and preserves
it. The arbitration itself is compiled and replayed below.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
CANDIDATES = BOTS / "Content/Raids/BlackwingDescent/Encounters/Nefarian/BotWorldPopulationMgrNefarianCandidates.cpp"


def _code(path: Path) -> str:
    return re.sub(r"//[^\n]*", "", path.read_text(encoding="utf-8"))


def test_stop_clears_native_chase_and_renews_a_hazard_lease() -> None:
    code = _code(CANDIDATES)
    stop = code[code.index("if (context.AdaptiveNefarianMovementHold == BotEncounter::Nefarian::WarriorStopHold)"):]
    stop = stop[:stop.index("DecisionKernel.Submit(std::move(stop));")]
    assert "Uses(\n            BotActionArbitration::Resource::Movement)" in stop
    assert "Priority::Survival" in stop
    controlled = stop.index("GetMotionSlot(MOTION_SLOT_CONTROLLED)")
    for step in ("bot->StopMoving();", "motion->Clear(MOTION_SLOT_ACTIVE);", "motion->MoveIdle();",
                 "BotMovementArbitration::Apply(context.State.MovementLease,"):
        assert controlled < stop.index(step), step
    assert "hold.Owner = BotMovementArbitration::Owner::Hazard;" in stop
    assert "hold.Priority = BotMovementArbitration::Priority::Hazard;" in stop
    assert "BuildMovementRequest(bot, hold, context.DecisionNowMs)" in stop
    assert "hold.X = bot->GetPositionX();" in stop and "hold.Z = bot->GetPositionZ();" in stop


def test_combat_range_movement_meets_the_lease_before_any_launch() -> None:
    combat = _code(BOTS / "BotWorldPopulationMgrCombatMovement.cpp")
    profile = combat[combat.index("bool BotWorldPopulationMgr::MoveBotToProfileRange("):]
    assert "BotMovementArbitration::Owner::CombatRange" in profile
    assert "BotMovementArbitration::Priority::Combat" in profile
    executor = _code(BOTS / "BotWorldPopulationMgrMovementExecutor.cpp")
    evaluate = executor.index("BotMovementArbitration::Evaluate(state.MovementLease, request, nowMs)")
    preserve = executor.index("Decision::PreserveExisting)", evaluate)
    assert "return false;" in executor[preserve:preserve + 700]
    assert evaluate < executor.index("MoveChase(intent.DynamicTarget")


def test_lease_arbitration_replay(tmp_path: Path) -> None:
    program = r'''
#include "Bots/BotMovementArbiter.h"
#include <cstdio>
using namespace BotMovementArbitration;
int main()
{
    Scope const scope{ 1, 0, 0, 669, 1 };
    Request hold;
    hold.MovementOwner = Owner::Hazard;
    hold.MovementPriority = Priority::Hazard;
    hold.ExpiresAtMs = 1000 + 1500;
    hold.MovementScope = scope;
    Lease lease;
    if (Evaluate(lease, hold, 1000) != Decision::Acquire) return 1;
    Apply(lease, hold);
    Request range;  // combat range recovery, same tick and until expiry
    range.MovementOwner = Owner::CombatRange;
    range.MovementPriority = Priority::Combat;
    range.ExpiresAtMs = 1000 + 1500;
    range.MovementScope = scope;
    range.X = 5.0f;
    range.DynamicTargetGuid = 77;  // a chase of the boss
    if (Evaluate(lease, range, 1000) != Decision::PreserveExisting) return 2;
    if (Evaluate(lease, range, 2400) != Decision::PreserveExisting) return 3;
    Request formation = range;
    formation.MovementOwner = Owner::Mechanic;
    formation.MovementPriority = Priority::Mechanic;
    if (Evaluate(lease, formation, 1000) != Decision::PreserveExisting) return 4;
    Request renewed = hold;  // the next decision renews it
    renewed.ExpiresAtMs = 2000 + 1500;
    if (Evaluate(lease, renewed, 2000) != Decision::Refresh) return 5;
    Apply(lease, renewed);
    range.ExpiresAtMs = 3000 + 1500;
    if (Evaluate(lease, range, 3000) != Decision::PreserveExisting) return 6;
    // Released: no renewal, the lease lapses and combat movement resumes.
    range.ExpiresAtMs = 3600 + 1500;
    if (Evaluate(lease, range, 3600) != Decision::Acquire) return 7;
    std::puts("lease ok");
    return 0;
}
'''
    source = tmp_path / "lease.cpp"
    source.write_text(program)
    binary = tmp_path / "lease"
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
                    "-I", str(ROOT / "src/server/game"), "-I", str(ROOT / "src/common"),
                    str(source), "-o", str(binary)], check=True)
    result = subprocess.run([str(binary)], capture_output=True, text=True)
    assert result.returncode == 0, result.returncode
    assert "lease ok" in result.stdout
