from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteSharedFocusAction.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteSharedFocusAction.h"
OBJECTIVE_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTerminalArrival.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_shared_focus_action_module_is_bounded_registered_and_typed():
    assert len(MODULE.read_text().splitlines()) <= 1000
    assert len(HEADER.read_text().splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationRouteSharedFocusAction.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in MODULE.read_text()
    assert "struct SharedFocusActionCallbacks" in HEADER.read_text()
    assert "RunSharedFocusAction" in OBJECTIVE_HEADER.read_text()
    assert ".cpp\"" not in HEADER.read_text()


def test_shared_focus_action_moves_the_requested_contiguous_boundary_once():
    source = SOURCE.read_text()
    module = MODULE.read_text()
    assert "if (Unit* focusTarget = routeGroupFocusTarget())" not in source
    assert module.count("if (Unit* focusTarget = routeGroupFocusTarget())") == 1
    assert source.count("terminalArrivalContext.RunSharedFocusAction") == 1
    assert module.count("bool ObjectiveContext::RunSharedFocusAction") == 1
    assert source.index("terminalArrivalContext.RunTankFocusAssist") < source.index(
        "terminalArrivalContext.RunSharedFocusAction"
    )
    assert source.index("terminalArrivalContext.RunSharedFocusAction") < source.index(
        "terminalArrivalContext.RunActiveCombat"
    )
    for marker in (
        "assist_target_search_authoritative_focus_",
        "shared_boss_target_not_declared",
        "shared_focus_mechanic_fail_closed",
        "assist_focus_no_health_progress",
    ):
        assert marker in module
        assert marker not in source


def test_shared_focus_action_passes_typed_focus_and_action_callbacks():
    source = SOURCE.read_text()
    header = HEADER.read_text()
    for callback in (
        "RouteGroupFocusTarget",
        "TeacherAssistAuthoritativeFocus",
        "AuthoritativeRouteFocusActive",
        "AuthoritativeFocusFailure",
        "IsValidationRouteObjectiveTarget",
        "GetDungeonRole",
        "RouteEngageRange",
        "MoveOutOfProfileDeadZone",
        "TryRouteGroupHeal",
        "MaybeValidationPrerequisiteNoProgressAssist",
    ):
        assert f"sharedFocusActionCallbacks.{callback}" in source
        assert callback in header
