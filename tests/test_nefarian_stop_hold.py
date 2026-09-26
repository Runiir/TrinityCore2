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


def test_holds_clear_native_chase_and_renew_a_lease() -> None:
    code = _code(CANDIDATES)
    renew = code[code.index("auto renewLease = [this, &context]"):]
    renew = renew[:renew.index("};")]
    for line in ("lease.X = bot->GetPositionX();", "lease.Z = bot->GetPositionZ();",
                 "lease.Owner = owner;", "lease.Priority = priority;",
                 "BotMovementArbitration::Apply(context.State.MovementLease,",
                 "BuildMovementRequest(bot, lease, context.DecisionNowMs)"):
        assert line in renew, line
    block = code[code.index("std::string const& hold = context.AdaptiveNefarianMovementHold;"):]
    block = block[:block.index("DecisionKernel.Submit(std::move(stop));")]
    assert "hold == BotEncounter::Nefarian::WarriorStopHold;" in block
    assert "BotEncounter::Nefarian::IsPlatformHold(hold);" in block
    assert "hold == BotEncounter::Nefarian::LegInFlightHold;" in block
    assert "? BotMovementArbitration::Owner::Hazard : BotMovementArbitration::Owner::Mechanic;" in block
    assert "Priority::Survival" in block
    assert "bool const stopMoving = warriorStop || platformStop;" in block
    assert "Uses(\n            BotActionArbitration::Resource::Movement)" in block
    # Beside a proposed leg the platform hold is the fallback: below every leg.
    assert "bool const fallback = platformStop && context.AdaptiveNefarianMovement" in block
    assert ": fallback ? BotActionArbitration::Priority::CombatMovement" in block
    assert "warriorStop ? 480.0f : fallback ? 1.0f : 250.0f" in block
    controlled = block.index("GetMotionSlot(MOTION_SLOT_CONTROLLED)")
    stop = block.index("if (stopMoving)")
    for step in ("bot->StopMoving();", "motion->Clear(MOTION_SLOT_ACTIVE);", "motion->MoveIdle();"):
        assert controlled < stop < block.index(step), step
    assert controlled < block.index("renewLease(owner, priority);")


def test_admitted_legs_publish_their_lease() -> None:
    code = _code(CANDIDATES)
    leg = code[code.index("if (context.AdaptiveNefarianMovement\n"):]
    leg = leg[:leg.index("context.State.DecisionKernel.Submit(std::move(movement));")]
    committed = leg.index("if (outcome.Result == BotActionArbitration::Disposition::Committed)")
    assert committed < leg.index("renewLease(survival ? BotMovementArbitration::Owner::Hazard")
    assert ">= uint8(BotActionArbitration::Priority::Survival);" in leg


def test_damage_dealers_hold_fire_on_the_target_lane() -> None:
    code = _code(CANDIDATES)
    hold = code[code.index("if (suppressReason == BotEncounter::Nefarian::HoldFirePreEngage"):]
    hold = hold[:hold.index("context.State.DecisionKernel.Submit(std::move(holdFire));")]
    assert "suppressReason == BotEncounter::Nefarian::HoldFireForOnyxiaTank" in hold
    assert "Uses(\n                BotActionArbitration::Resource::Target)" in hold
    assert "Resource::Cast" not in hold and "Resource::GlobalCooldown" not in hold
    assert "Outcome::Committed(" in hold


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
    // The platform hold's Mechanic lease also keeps combat range out.
    Lease platform;
    Request mechanic = hold;
    mechanic.MovementOwner = Owner::Mechanic;
    mechanic.MovementPriority = Priority::Mechanic;
    Apply(platform, mechanic);
    if (Evaluate(platform, range, 1000) != Decision::PreserveExisting) return 8;
    Request routeWalk = range;
    routeWalk.MovementOwner = Owner::Route;
    routeWalk.MovementPriority = Priority::Route;
    if (Evaluate(platform, routeWalk, 1000) != Decision::PreserveExisting) return 9;
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


def test_onyxia_landing_chain_is_instrumented_not_rewritten() -> None:
    """Round 7 review: the native "no death before Nefarian lands" rule stays
    as it was (one-shot ACTION_NEFARIAN_LANDED); the chain is instrumented so
    the next live run shows where it breaks."""
    script = _code(ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_nefarians_end.cpp")
    onyxia = script[script.index("struct npc_nefarians_end_onyxia"):]
    damage = onyxia[onyxia.index("void DamageTaken("):]
    damage = damage[:damage.index("\n    }\n")]
    assert "if (damage >= me->GetHealth() && !_allowDeath)" in damage
    assert "damage = me->GetHealth() - 1;" in damage
    assert "IsEngaged()" not in damage and "IsFlying()" not in damage
    assert "_allowDeath = true" not in damage
    assert "NefariansEnd onyxia lethal_clamp" in damage
    assert "case ACTION_NEFARIAN_LANDED:\n                _allowDeath = true;" in onyxia
    assert "NefariansEnd onyxia landed_received" in onyxia
    for marker in ("NefariansEnd nefarian movement_inform", "NefariansEnd nefarian move_land",
                   "NefariansEnd nefarian landed nefarian", "NefariansEnd nefarian landed_signal"):
        assert marker in script, marker
    # printf-style logging (TC_LOG_* here takes %-formats).
    assert "{}" not in "".join(line for line in script.splitlines() if "NefariansEnd" in line)


def test_onyxia_unkillable_flag_goes_with_the_landing() -> None:
    """Round 8 (r07 root cause): Onyxia's 4.3.4 creature_template StaticFlags
    carry CREATURE_STATIC_FLAG_UNKILLABLE, which Unit::DealDamage enforces
    after her AI's DamageTaken; the script clears it with the landing and
    sets it again when she appears."""
    sql = (ROOT / "sql/updates/world/4.3.4/2023_08_27_00_world.sql").read_text(encoding="utf-8")
    row = [line for line in sql.splitlines() if "WHERE `entry`= 41270;" in line and "StaticFlags" in line]
    assert row, "Onyxia's static flags row"
    flags = int(re.search(r"`StaticFlags`= (\d+)", row[0]).group(1))
    assert flags & 0x8, "CREATURE_STATIC_FLAG_UNKILLABLE"
    unit = _code(ROOT / "src/server/game/Entities/Unit/Unit.cpp")
    assert "HasStaticFlag(CREATURE_STATIC_FLAG_UNKILLABLE)" in unit
    script = _code(ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_nefarians_end.cpp")
    onyxia = script[script.index("struct npc_nefarians_end_onyxia"):]
    landed = onyxia[onyxia.index("case ACTION_NEFARIAN_LANDED:"):]
    landed = landed[:landed.index("break;")]
    assert "_allowDeath = true;" in landed and "me->SetUnkillable(false);" in landed
    appeared = onyxia[onyxia.index("void JustAppeared() override"):]
    appeared = appeared[:appeared.index("\n    }\n")]
    assert "me->SetUnkillable(true);" in appeared
