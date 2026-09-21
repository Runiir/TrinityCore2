from __future__ import annotations

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatMovement.cpp"
LIFECYCLE_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationLifecycle.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "BeginMeleeAutoAttackDecision",
    "SubmitMeleeAutoAttackIntent",
    "ResolveAndReconcileMeleeAutoAttack",
    "MoveBotToProfileRange",
)


def test_combat_movement_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrCombatMovement.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_combat_movement_keeps_single_native_attack_authority() -> None:
    module = MODULE.read_text(encoding="utf-8")
    assert "AttackStop()" in module
    assert "bot->Attack(target, true)" in module
    assert "native_toggle_rejected" in module
    assert "BotRaidAreaAuthority::IsAllOffenseSuppressed" in module
    assert "BotRaidAreaAuthority::IsProtectedEncounterTarget" in module


def test_calibration_terminal_state_suppresses_the_retained_melee_toggle() -> None:
    module = MODULE.read_text(encoding="utf-8")
    reconcile = module[module.index(
        "void BotWorldPopulationMgr::ResolveAndReconcileMeleeAutoAttack"
    ):module.index("bool BotWorldPopulationMgr::MoveBotToProfileRange")]

    assert "Cohort().CalibrationWindowComplete" in reconcile
    assert "Cohort().CalibrationStopping" in reconcile
    assert "BotMeleeAutoAttack::Kind::Suppress" in reconcile
    assert '"calibration_teardown"' in reconcile
    assert reconcile.index("calibration_teardown") < reconcile.index(
        "all_offense_suppressed"
    )
    assert "state.SpawnSource" in reconcile
    assert "ShouldSuppressMeleeAutoAttack" in reconcile
    assert "bot->Attack(target, true)" in reconcile


def test_calibration_lifecycle_header_executes_clone_identity_boundaries(tmp_path):
    source = r'''
#include "Bots/BotWorldPopulationMgrCalibrationLifecycle.h"

#include <array>
#include <cassert>
#include <cstdint>
#include <set>
#include <string>

struct State
{
    std::uint32_t Guid;
    std::string SpawnSource;
};

int main()
{
    using namespace BotWorldPopulationMgrCalibrationLifecycle;
    std::array<State, 2> live = {{
        {41u, "combat_calibration"},
        {73u, "ordinary"},
    }};
    std::set<std::uint32_t> retained{41u};

    assert(ShouldSuppressMeleeAutoAttack(
        "combat_calibration", false, true, true));
    assert(!ShouldSuppressMeleeAutoAttack("ordinary", false, true, true));
    assert(IsRetainedStoppingCalibrationClone(41u, retained));
    assert(!IsRetainedStoppingCalibrationClone(99u, retained));
    assert(IsIdentifiedCalibrationClone(41u, retained, live));
    assert(!IsIdentifiedCalibrationClone(99u, retained, live));
    assert(!IsLiveCalibrationClone(73u, live));
    return 0;
}
'''
    source_path = tmp_path / "calibration_lifecycle.cpp"
    binary_path = tmp_path / "calibration_lifecycle"
    source_path.write_text(source, encoding="utf-8")
    compile_result = subprocess.run(
        [
            "c++", "-std=c++11", "-Wall", "-Wextra", "-Werror",
            "-I", str(LIFECYCLE_HEADER.parent.parent), str(source_path),
            "-o", str(binary_path),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert compile_result.returncode == 0, compile_result.stderr
    run_result = subprocess.run(
        [str(binary_path)], capture_output=True, text=True, check=False,
    )
    assert run_result.returncode == 0, run_result.stderr


def test_combat_movement_preserves_profile_range_and_path_guards() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for directive in ("melee_behind", "melee"):
        assert f'"{directive}"' in module
    assert "PathGenerator approachPath" in module
    assert "MoveBotToPoint" in module
    assert "preciseMaximumRangeApproach" in module


def test_los_reposition_requires_target_visible_from_candidate_point() -> None:
    module = MODULE.read_text(encoding="utf-8")
    start = module.index("auto moveProfilePoint")
    end = module.index("auto moveToTerrainProjectedPoint", start)
    point_move = module[start:end]
    assert "forceRangedReposition" in point_move
    assert "reference->IsWithinLOS(x, y, z)" in point_move
    assert_ordered = [
        "if (forceRangedReposition",
        "reference->IsWithinLOS(x, y, z)",
        "return false;",
        "MoveBotToPoint",
    ]
    positions = [point_move.index(marker) for marker in assert_ordered]
    assert positions == sorted(positions)


def test_profile_range_diagnostic_uses_object_guid_counters() -> None:
    module = MODULE.read_text(encoding="utf-8")
    start = module.index("auto annotateProfileRangeReceipt")
    end = module.index("auto moveProfilePoint", start)
    diagnostic = module[start:end]

    assert "bot->GetGUID().GetCounter()" in diagnostic
    assert "reference->GetGUID().GetCounter()" in diagnostic
    assert "GetRawValue" not in diagnostic


def test_melee_range_uses_live_target_chase_without_target_z_floor_gate() -> None:
    module = MODULE.read_text(encoding="utf-8")
    start = module.index(
        'if (directive == "melee" || (minRange <= 0.0f && maxRange <= 5.0f))'
    )
    end = module.index("    // A small center-to-center offset", start)
    melee = module[start:end]

    # A Magmaw-like actor can expose a model origin far below the navigable
    # floor. The live target must reach ExecuteMovementIntent as a dynamic
    # chase instead of being rejected by the target-elevation floor probe.
    assert "reference->GetPositionX()" in melee
    assert "reference->GetPositionY()" in melee
    assert "bot->GetPositionZ()" in melee
    assert "reference);" in melee
    assert "GetHeight" not in melee
    assert "targetZ" not in melee
