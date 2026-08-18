from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
CONTRACT = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteMovementCheck.h"
PLANNER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteMovementCheck.cpp"
ACTIONS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteMovementCheckActions.cpp"


def test_route_movement_check_is_typed_and_bounded() -> None:
    world = WORLD.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    planner = PLANNER.read_text(encoding="utf-8")
    actions = ACTIONS.read_text(encoding="utf-8")
    contract = CONTRACT.read_text(encoding="utf-8")

    assert len(header.splitlines()) <= 1000
    for source in (CONTRACT, PLANNER, ACTIONS):
        assert len(source.read_text(encoding="utf-8").splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationRouteMovementCheck.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    assert "BotWorldPopulationMgrValidationRouteMovementCheckActions.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    assert "MovementCheckCallbacks" in contract
    assert "TryValidationRouteMovementCheck" in header
    assert "TryValidationRouteFeralHazardHealerRoar" in actions
    assert "TryValidationRouteTankHazardHoldAreaThreat" in actions
    assert "BotWorldPopulationMgr::TryValidationRouteMovementCheck" in planner
    assert "auto tryValidationRouteMovementCheck" not in world
    assert "TryValidationRouteMovementCheck(state, bot, power, stage, activity" in world
    assert '#include "Bots/BotWorldPopulationMgr.cpp"' not in planner
    assert '#include "Bots/BotWorldPopulationMgr.cpp"' not in actions


def test_route_movement_check_keeps_observation_and_action_boundaries() -> None:
    planner = PLANNER.read_text(encoding="utf-8")
    actions = ACTIONS.read_text(encoding="utf-8")

    for marker in (
        "BuildDefinitions",
        "FindActive",
        "ValidationRouteDodgeCasterGuid",
        "positionOutsideActiveHazards",
        "PathOutside",
        "dodgeCandidates.erase",
        "hazard_exit_completed",
    ):
        assert marker in planner
    for marker in (
        "TryCastFriendlySpell(bot, bot, 99)",
        "TryCastCombatSpell(bot, looseAttacker, 6795)",
        "fade_in_flight_hazard_threat_drop",
        "feral_charge_safe_hazard_swarm_pickup",
        "tank_hazard_hold_aoe_threat",
    ):
        assert marker in actions
    assert "TryValidationRouteMovementCheck" not in actions
    assert "previousDefinition->Shape == \"radial\", true" in planner
    assert "previousHazard, safeRadius, true, false" in planner
