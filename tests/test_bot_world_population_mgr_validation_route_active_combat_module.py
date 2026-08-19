from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteActiveCombat.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteActiveCombat.h"
OBJECTIVE_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTerminalArrival.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_active_combat_module_is_bounded_registered_and_typed():
    assert len(MODULE.read_text().splitlines()) <= 1000
    assert len(HEADER.read_text().splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationRouteActiveCombat.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in MODULE.read_text()
    assert "struct ActiveCombatCallbacks" in HEADER.read_text()
    assert "RunActiveCombat" in OBJECTIVE_HEADER.read_text()
    assert '.cpp"' not in HEADER.read_text()


def test_active_combat_moves_the_requested_contiguous_boundary_once():
    source = SOURCE.read_text()
    module = MODULE.read_text()
    assert "if (std::string(GetDungeonRole(bot)) != \"tank\"" not in source
    assert module.count("if (std::string(GetDungeonRole(bot)) != \"tank\"") == 1
    assert source.count("terminalArrivalContext.RunActiveCombat") == 1
    assert module.count("bool ObjectiveContext::RunActiveCombat") == 1
    assert source.index("terminalArrivalContext.RunSharedFocusAction") < source.index(
        "terminalArrivalContext.RunActiveCombat"
    ) < source.index("boss_route_early_activation")
    for marker in (
        "regroup_anchor_no_focus",
        "ineligible_trash_target",
        "raid_mechanic_contract_fail_closed",
        "misdirection_to_tank",
        "wait_for_tank_threat",
        "move_to_profile_min_range",
        "validation_route_tank_boss",
    ):
        assert marker in module
        assert marker not in source


def test_active_combat_passes_typed_regroup_and_combat_callbacks():
    source = SOURCE.read_text()
    header = HEADER.read_text()
    for callback in (
        "GetDungeonRole",
        "FindDungeonAnchor",
        "RouteEngageRange",
        "IsValidationCohortCombatLinked",
        "EnrollValidationRoutePackMember",
        "IsValidationRouteObjectiveTarget",
        "IsEligibleTrashClusterMob",
        "RememberValidationRouteFocus",
        "HasValidationRouteActivation",
        "ValidationRouteHasLivingTank",
        "RouteFocusTankOwned",
        "MoveOutOfProfileDeadZone",
        "TryRouteGroupHeal",
        "TryValidationRouteInterrupt",
        "MaybeValidationPrerequisiteNoProgressAssist",
    ):
        assert f"activeCombatCallbacks.{callback}" in source
        assert callback in header
