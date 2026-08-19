from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTankFocusAssist.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTankFocusAssist.h"
OBJECTIVE_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTerminalArrival.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_tank_focus_assist_module_is_bounded_registered_and_typed():
    assert len(MODULE.read_text().splitlines()) <= 1000
    assert len(HEADER.read_text().splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationRouteTankFocusAssist.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in MODULE.read_text()
    assert "struct TankFocusAssistCallbacks" in HEADER.read_text()
    assert "RunTankFocusAssist" in OBJECTIVE_HEADER.read_text()
    assert ".cpp\"" not in HEADER.read_text()


def test_tank_focus_assist_moves_the_requested_contiguous_boundary_once():
    source = SOURCE.read_text()
    module = MODULE.read_text()
    assert source.count("terminalArrivalContext.RunTankFocusAssist") == 1
    assert module.count("bool ObjectiveContext::RunTankFocusAssist") == 1
    assert 'if (std::string(GetDungeonRole(bot)) == "tank")' in module
    assert 'if (Cohort().Config.ValidationRouteKind == "boss" && std::string(GetDungeonRole(bot)) != "tank")' in module
    assert source.index("terminalArrivalContext.RunTrashIntervention") < source.index(
        "terminalArrivalContext.RunTankFocusAssist"
    ) < source.index("terminalArrivalContext.RunSharedFocusAction")
    for marker in (
        "shared_focus_not_declared",
        "shared_boss_mechanic_fail_closed",
        "assist_tank_focus_interrupt",
        "unresolved_authoritative_focus_recovery",
        "regroup_tank_focus_mismatch",
    ):
        assert marker in module
        assert marker not in source


def test_tank_focus_assist_passes_focus_action_and_recovery_callbacks():
    source = SOURCE.read_text()
    header = HEADER.read_text()
    for callback in (
        "GetDungeonRole",
        "RouteUsableCombatTarget",
        "RememberValidationRouteFocus",
        "RouteTankFocusGuid",
        "RouteTankFocusTarget",
        "FindLastKnownFocusTarget",
        "IsValidationRouteObjectiveTarget",
        "RouteFocusMemoryActive",
        "AuthoritativeRouteFocusActive",
        "RecoverAuthoritativeFocus",
        "TeacherAssistAuthoritativeFocus",
        "RouteEngageRange",
        "MoveOutOfProfileDeadZone",
        "TryRouteGroupHeal",
        "TryValidationRouteInterrupt",
        "MaybeValidationPrerequisiteNoProgressAssist",
    ):
        assert f"tankFocusAssistCallbacks.{callback}" in source
        assert callback in header
