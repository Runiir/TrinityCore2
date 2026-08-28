from __future__ import annotations

import json
import math
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
EXECUTOR = BOT_DIR / "BotWorldPopulationMgrMovementExecutor.cpp"
FORMATION = BOT_DIR / "BotWorldPopulationMgrValidationPatrolFormation.cpp"
MOVEMENT = BOT_DIR / "BotWorldPopulationMgrMovement.h"
SCENARIO = ROOT / "experiments/configs/validation_scenarios_cata_001.json"


def _chain_and_drudges() -> tuple[dict, dict]:
    config = json.loads(SCENARIO.read_text(encoding="utf-8"))
    scenario = next(row for row in config["scenarios"]
                    if row["id"] == "blackwing_descent_10n")
    chain = next(row for row in scenario["route"]
                 if row["node_id"] == "bwd.magmaw.chainwielder")
    drudges = next(row for row in scenario["route"]
                   if row["node_id"] == "bwd.magmaw.drudges")
    return chain, drudges


def test_central_guard_precedes_all_ordinary_movement_admission_boundaries():
    executor = EXECUTOR.read_text(encoding="utf-8")
    guard = "AppliesValidationRoutePatrolFutureDestinationGuard"
    guard_at = executor.index(guard)
    lease_at = executor.index("BuildMovementRequest", guard_at)
    active_at = executor.index("ObserveActiveMovement", guard_at)
    planner_at = executor.index("PlanMovementPath", guard_at)
    assert guard_at < lease_at < active_at < planner_at
    assert "IsValidationRoutePatrolCombatPointSafe(bot, intent.X, intent.Y" in executor
    assert '"future_pack_destination",' in executor
    assert '"route_destination_future_pack_unsafe"' in executor
    assert "RejectMovementPath(state, bot, intent" in executor[guard_at:lease_at]

    # The four ordinary producers all converge on MoveBotToPoint and therefore
    # cannot submit a native destination around the shared executor gate.
    for source_name in (
        "BotWorldPopulationMgrValidationPatrolFormation.cpp",
        "BotWorldPopulationMgrCombatMovement.cpp",
        "BotWorldPopulationMgrValidationRouteMovementCheck.cpp",
        "BotWorldPopulationMgrValidationRouteActiveCombat.cpp",
    ):
        assert "MoveBotToPoint" in (BOT_DIR / source_name).read_text(
            encoding="utf-8"
        )


def test_future_guard_keeps_recovery_exception_explicit_and_header_small():
    movement = MOVEMENT.read_text(encoding="utf-8")
    assert "AppliesValidationRoutePatrolFutureDestinationGuard" in movement
    assert "owner != BotMovementArbitration::Owner::Recovery" in movement
    assert "Native recovery movement is the only exception" in movement

    harness = r"""
#include "Bots/BotWorldPopulationMgrMovement.h"
#include <cassert>

int main()
{
    using Owner = BotMovementArbitration::Owner;
    using BotWorldMovement::AppliesValidationRoutePatrolFutureDestinationGuard;
    assert(AppliesValidationRoutePatrolFutureDestinationGuard(Owner::Route));
    assert(AppliesValidationRoutePatrolFutureDestinationGuard(Owner::Formation));
    assert(AppliesValidationRoutePatrolFutureDestinationGuard(Owner::CombatRange));
    assert(AppliesValidationRoutePatrolFutureDestinationGuard(Owner::Hazard));
    assert(!AppliesValidationRoutePatrolFutureDestinationGuard(Owner::Recovery));
}
"""
    source = ROOT / "tests" / ".tmp_central_future_guard.cpp"
    binary = ROOT / "tests" / ".tmp_central_future_guard"
    try:
        source.write_text(harness, encoding="utf-8")
        subprocess.run(
            ["g++", "-std=c++17", "-I", str(ROOT / "src/common"), "-I",
             str(ROOT / "src/server/game"), str(source), "-o", str(binary)],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    finally:
        source.unlink(missing_ok=True)
        binary.unlink(missing_ok=True)


def test_recorded_future_drudge_destination_is_rejected_and_anchor_is_admitted():
    chain, drudges = _chain_and_drudges()
    guard_clearance = max(
        chain["patrol_combat_clearance_yards"],
        chain["cluster_radius_yards"] + chain["patrol_future_guard_margin_yards"],
    )
    homes = [(row["x"], row["y"])
             for row in drudges["split_source_home_anchors"]]
    unsafe = (-334.058, -65.336)
    safe = (chain["patrol_combat_anchor"]["x"],
            chain["patrol_combat_anchor"]["y"])
    assert min(math.dist(unsafe, home) for home in homes) <= guard_clearance
    assert min(math.dist(safe, home) for home in homes) > guard_clearance


def test_target_independent_guard_uses_its_captured_map_identity():
    formation = FORMATION.read_text(encoding="utf-8")
    helper = formation[
        formation.index("Map* map, uint32 mapId"):
        formation.index("bool BotWorldPopulationMgr::TryValidationRoutePatrolCombatAnchor")
    ]
    assert "futureNode.MapId != mapId" in helper
    assert "target->GetMapId()" not in helper
