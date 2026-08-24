from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
CONTROLLER = BOT_DIR / "BotController.cpp"
MOVEMENT = BOT_DIR / "BotControllerMovement.cpp"
MOVEMENT_ARBITER = BOT_DIR / "BotMovementArbiter.h"
HEALER = BOT_DIR / "BotControllerHealer.cpp"
EXECUTOR = BOT_DIR / "BotActionExecutor.cpp"


def _candidate_block(source: str, key: str, next_key: str) -> str:
    start = source.index(f'{key}.RequiredResources =')
    end = source.index(f'{key}.Attempt', start)
    return source[start:end]


def test_attached_actions_leave_the_native_movement_command_lane_free() -> None:
    source = CONTROLLER.read_text(encoding="utf-8")
    healer = _candidate_block(source, "healer", "combat")
    combat = _candidate_block(source, "combat", "movement")
    movement_start = source.index('movement.Key = "attached.movement"')
    movement = source[movement_start : source.index("movement.Attempt", movement_start)]

    assert "Resource::Movement" not in healer
    assert "Resource::Movement" not in combat
    assert "Resource::GlobalCooldown" in healer
    assert "Resource::Cast" in combat
    assert movement.count("Resource::Movement") == 1


def test_cast_time_and_hazard_safety_remain_native_gated() -> None:
    controller = CONTROLLER.read_text(encoding="utf-8")
    movement = MOVEMENT.read_text(encoding="utf-8")
    movement_contract = MOVEMENT_ARBITER.read_text(encoding="utf-8") + movement
    healer = HEALER.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")

    assert "movement.ActionPriority = _movementMode == BotMovementMode::MoveSafe" in controller
    assert "BotActionArbitration::Priority::Survival" in controller
    assert "movementFrame.Moving && castTime" in healer
    cast_gate = executor[executor.index("if (spellInfo && spellInfo->CalcCastTime"):]
    assert cast_gate.index("bot->StopMoving()") < cast_gate.index("return BotActionResult::Casting")
    assert "castTimeMovementBlocked" in controller
    assert "cast_time_movement_gate" in controller
    assert "HasUnitState(UNIT_STATE_CASTING)" in movement
    assert "NativePathReceipt" in movement_contract
    assert "MatchesNativePath" in movement_contract
    assert "NativeMovementGeneratorActive" in movement
    assert "_nativeMovementPath.Path.ExpiresAtMs = 0" in movement
    assert movement.index("NativeMovementGeneratorActive") < movement.index("Evaluate(arbitrationLease")
    assert movement.index("MatchesNativePath(_nativeMovementPath") < movement.index("commandSubmitted = true")


def test_attached_arbitration_replay_coexists_and_deduplicates(tmp_path: Path) -> None:
    source = tmp_path / "attached_movement_replay.cpp"
    binary = tmp_path / "attached_movement_replay"
    source.write_text(
        r'''
#include "Bots/BotActionArbiter.h"
#include "Bots/BotMovementArbiter.h"
#include <cassert>

int main()
{
    namespace Action = BotActionArbitration;
    namespace Movement = BotMovementArbitration;

    Movement::Scope scope{7, 2, 9, 669, 41};
    Movement::Request movement{Movement::Owner::Formation,
        Movement::Priority::Formation, 1100,
        scope, 10.0f, 20.0f, 30.0f};
    Movement::NativePathReceipt receipt;
    receipt.Active = true;
    Movement::Apply(receipt.Path, movement);
    receipt.Path.ExpiresAtMs = 1000;
    movement.DynamicTargetGuid = 1234;
    Movement::Apply(receipt.Path, movement);
    receipt.Path.ExpiresAtMs = 1000;

    // The receipt identifies the native path independently of the short
    // arbitration lease.  The lease has the exact expiry boundary, while the
    // path identity remains matchable at every decision cadence.
    Movement::Request nextTick = movement;
    nextTick.X += 25.0f;
    nextTick.ExpiresAtMs = 5000;
    unsigned nativeSubmissions = 0;
    for (uint64 nowMs : {999ULL, 1000ULL, 1001ULL})
    {
        if (!Movement::MatchesNativePath(receipt, nextTick))
            ++nativeSubmissions;
        Movement::Decision const decision = Movement::Evaluate(
            receipt.Path, nextTick, nowMs);
        if (nowMs < 1000)
            assert(decision == Movement::Decision::Refresh);
        else
            assert(decision == Movement::Decision::Acquire);
    }
    assert(nativeSubmissions == 0);

    Action::Kernel coexist;
    coexist.Begin(2000);
    unsigned movementSubmissions = 0;
    unsigned combatSubmissions = 0;
    unsigned healSubmissions = 0;
    coexist.Submit(Action::Candidate{
        "attached.movement", "movement_mode_adapter",
        Action::Priority::CombatMovement,
        0.5f, 0.0f, 0.0f, Action::Uses(Action::Resource::Movement),
        0, 100, 3000, 5,
        true, "", [&]
        {
            ++movementSubmissions;
            return Action::Outcome::Submitted("native_motion_submitted");
        }
    });
    coexist.Submit(Action::Candidate{
        "attached.profile_combat", "db_class_spec_profile",
        Action::Priority::Support,
        1.0f, 0.0f, 0.0f,
        Action::Uses(Action::Resource::GlobalCooldown, Action::Resource::Cast,
            Action::Resource::Target),
        0, 100, 3000, 5, true, "", [&]
        {
            ++combatSubmissions;
            return Action::Outcome::Submitted("instant_combat_submitted");
        }
    });
    coexist.Submit(Action::Candidate{
        "attached.healer_profile", "db_class_spec_profile",
        Action::Priority::TrainedDamage,
        1.0f, 0.0f, 0.0f,
        Action::Uses(Action::Resource::GlobalCooldown, Action::Resource::Cast,
            Action::Resource::Target),
        0, 100, 3000, 5, true, "", [&]
        {
            ++healSubmissions;
            return Action::Outcome::Submitted("heal_lane_owned");
        }
    });
    Action::Resolution const& coexistResolution = coexist.Resolve();
    assert(movementSubmissions == 1);
    assert(combatSubmissions == 1);
    assert(healSubmissions == 0);
    assert(coexistResolution.CommittedCandidates.size() == 2);

    Action::Kernel hazard;
    hazard.Begin(2100);
    unsigned routeMovementSubmissions = 0;
    unsigned hazardSubmissions = 0;
    unsigned instantHealSubmissions = 0;
    hazard.Submit(Action::Candidate{
        "attached.route_movement", "movement_mode_adapter",
        Action::Priority::RouteMovement,
        0.5f, 0.0f, 0.0f, Action::Uses(Action::Resource::Movement),
        0, 100, 3000, 5,
        true, "", [&]
        {
            ++routeMovementSubmissions;
            return Action::Outcome::Submitted("route_motion_submitted");
        }
    });
    hazard.Submit(Action::Candidate{
        "attached.hazard_movement", "movement_mode_adapter",
        Action::Priority::Survival,
        3.0f, 0.0f, 0.0f, Action::Uses(Action::Resource::Movement),
        0, 100, 3000, 5,
        true, "", [&]
        {
            ++hazardSubmissions;
            return Action::Outcome::Submitted("hazard_motion_submitted");
        }
    });
    hazard.Submit(Action::Candidate{
        "attached.instant_heal", "db_class_spec_profile",
        Action::Priority::Support,
        1.0f, 0.0f, 0.0f,
        Action::Uses(Action::Resource::GlobalCooldown, Action::Resource::Cast,
            Action::Resource::Target),
        0, 100, 3000, 5, true, "", [&]
        {
            ++instantHealSubmissions;
            return Action::Outcome::Submitted("instant_heal_submitted");
        }
    });
    Action::Resolution const& hazardResolution = hazard.Resolve();
    assert(routeMovementSubmissions == 0);
    assert(hazardSubmissions == 1);
    assert(instantHealSubmissions == 1);
    assert(hazardResolution.CommittedCandidates.size() == 2);

    Action::Kernel duplicate;
    duplicate.Begin(2200);
    unsigned duplicateSubmissions = 0;
    auto submitMovement = [&]
    {
        duplicate.Submit(Action::Candidate{
            "attached.movement", "movement_mode_adapter",
            Action::Priority::RouteMovement,
            0.5f, 0.0f, 0.0f,
            Action::Uses(Action::Resource::Movement), 0, 100, 3000, 5,
            true, "", [&]
            {
                ++duplicateSubmissions;
                return Action::Outcome::Submitted("native_motion_submitted_once");
            }
        });
    };
    submitMovement();
    submitMovement();
    duplicate.Resolve();
    assert(duplicateSubmissions == 1);
    return 0;
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
