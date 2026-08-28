import json
import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "experiments/configs/validation_scenarios_cata_001.json"
BOT_DIR = ROOT / "src/server/game/Bots"


def _chain_and_drudges():
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    scenario = next(row for row in config["scenarios"]
                    if row["id"] == "blackwing_descent_10n")
    chain = next(row for row in scenario["route"]
                 if row["node_id"] == "bwd.magmaw.chainwielder")
    drudges = next(row for row in scenario["route"]
                   if row["node_id"] == "bwd.magmaw.drudges")
    return chain, drudges


def test_chainwielder_combat_anchor_keeps_future_drudges_out_of_proc_lane():
    chain, drudges = _chain_and_drudges()
    anchor = chain["patrol_combat_anchor"]
    anchor_xy = (anchor["x"], anchor["y"])
    clearance = chain["patrol_combat_clearance_yards"]
    future_home_clearance = (
        chain["cluster_radius_yards"]
        + chain["patrol_future_guard_margin_yards"]
    )

    assert (anchor["x"], anchor["y"], anchor["z"]) == (-327.0, -111.0, 214.0)
    assert math.dist(anchor_xy, (chain["x"], chain["y"])) > clearance
    assert all(
        math.dist(anchor_xy, (home["x"], home["y"])) > future_home_clearance
        for home in drudges["split_source_home_anchors"]
    )

    # Replay the first unsafe tick: the anchor must remain outside the native
    # 10-yard volley radius plus the declared 2-yard route safety margin from
    # both the current target and the live future units.
    current_target = (-332.244, -97.396)
    future_units = [(-308.898, -84.639), (-310.867, -90.532)]
    assert math.dist(anchor_xy, current_target) > clearance
    assert all(math.dist(anchor_xy, unit) > clearance for unit in future_units)


def test_chainwielder_patrol_geometry_uses_route_owned_native_movement():
    formation = (BOT_DIR / "BotWorldPopulationMgrValidationPatrolFormation.cpp").read_text(
        encoding="utf-8"
    )
    movement = (BOT_DIR / "BotWorldPopulationMgrCombatMovement.cpp").read_text(
        encoding="utf-8"
    )
    active = (BOT_DIR / "BotWorldPopulationMgrValidationRouteActiveCombat.cpp").read_text(
        encoding="utf-8"
    )
    for token in (
        "ValidationRoutePatrolCombatAnchor",
        "ValidationRoutePatrolCombatClearanceYards",
        "ValidationRouteClusterRadiusYards",
        "SplitSourceGuids",
        "BotMovementArbitration::Owner::Route",
        "BotMovementArbitration::Priority::Route",
    ):
        assert token in formation
    assert "IsValidationRoutePatrolCombatPointSafe" in movement
    assert "TryValidationRoutePatrolCombatAnchor" in active


def test_chainwielder_profile_range_checks_null_action_destinations():
    chain, drudges = _chain_and_drudges()
    movement = (BOT_DIR / "BotWorldPopulationMgrCombatMovement.cpp").read_text(
        encoding="utf-8"
    )
    unsafe_trace_point = (-310.569, -97.0254)
    anchor = chain["patrol_combat_anchor"]
    future_home_clearance = (
        chain["cluster_radius_yards"]
        + chain["patrol_future_guard_margin_yards"]
    )

    assert 'return !action || action->AutoAttackMode == "melee"' not in movement
    assert "return IsValidationRoutePatrolCombatPointSafe(reference, x, y, z);" in movement
    assert 'action && action->AutoAttackMode == "melee"' in movement
    assert min(
        math.dist(unsafe_trace_point, (home["x"], home["y"]))
        for home in drudges["split_source_home_anchors"]
    ) < future_home_clearance
    assert min(
        math.dist((anchor["x"], anchor["y"]), (home["x"], home["y"]))
        for home in drudges["split_source_home_anchors"]
    ) > future_home_clearance


def test_chainwielder_melee_future_destination_is_rejected_but_current_pack_is_admitted():
    chain, drudges = _chain_and_drudges()
    movement = (BOT_DIR / "BotWorldPopulationMgrCombatMovement.cpp").read_text(
        encoding="utf-8"
    )
    start = movement.index(
        'if (directive == "melee" || (minRange <= 0.0f && maxRange <= 5.0f))'
    )
    end = movement.index("    // A small center-to-center offset", start)
    melee = movement[start:end]

    future_destination = (-308.208, -64.122, 212.863)
    current_pack_anchor = (
        chain["patrol_combat_anchor"]["x"],
        chain["patrol_combat_anchor"]["y"],
        chain["patrol_combat_anchor"]["z"],
    )
    future_home_clearance = (
        chain["cluster_radius_yards"]
        + chain["patrol_future_guard_margin_yards"]
    )

    def future_pack_safe(point):
        return min(
            math.dist(point[:2], (home["x"], home["y"]))
            for home in drudges["split_source_home_anchors"]
        ) > future_home_clearance

    assert future_destination == (-308.208, -64.122, 212.863)
    assert not future_pack_safe(future_destination)
    assert future_pack_safe(current_pack_anchor)

    # Dynamic melee chase keeps its native target/floor behavior, but cannot
    # submit either recorded future destination or another unsafe endpoint.
    gate = 'if (!patrolCombatPointSafe(targetX, targetY, bot->GetPositionZ()))'
    assert gate in melee
    assert melee.index(gate) < melee.index("return MoveBotToPoint")
