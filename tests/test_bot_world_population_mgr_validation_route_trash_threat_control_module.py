from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTrashThreatControl.cpp"
INTERVENTION_MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTrashIntervention.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTrashThreatControl.h"
OBJECTIVE_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTerminalArrival.h"
MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_trash_threat_control_module_is_bounded_and_registered():
    assert len(MODULE.read_text().splitlines()) <= 1000
    assert len(HEADER.read_text().splitlines()) <= 1000
    assert len(MGR_HEADER.read_text().splitlines()) == 1000
    assert "BotWorldPopulationMgrValidationRouteTrashThreatControl.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in MODULE.read_text()
    assert "struct TrashThreatControl;" in OBJECTIVE_HEADER.read_text()
    assert "RunTrashThreatControl" in OBJECTIVE_HEADER.read_text()


def test_trash_threat_control_block_moves_once_at_terminal_boundary():
    source = SOURCE.read_text()
    module = MODULE.read_text()
    intervention = INTERVENTION_MODULE.read_text()
    header = HEADER.read_text()

    assert source.count("struct TrashThreatControl") == 0
    assert header.count("struct TrashThreatControl\n") == 1
    assert module.count("bool ObjectiveContext::RunTrashThreatControl") == 1
    assert module.count("if (tryValidationRouteAdds())\n        return true;") == 1

    run_call = source.index("terminalArrivalContext.RunTrashThreatControl")
    defeated_boundary = source.index("recordDefeatedValidationRoutePackMembers()")
    assert run_call < defeated_boundary
    assert source.count("terminalArrivalContext.RunTrashThreatControl") == 1

    for marker in (
        "trash_threat_hold",
        "fade_early_trash_swarm_threat_drop",
        "healer_preposition_early_for_feral_trash_pickup",
        "misdirection_aoe_wait_for_focus",
        "focused_damage_during_trash_threat_build",
    ):
        assert marker in module
        assert marker not in source

    for callback in (
        "IsImmediateNextValidationRouteEncounterMember",
        "IsPendingScriptedEventEntry",
        "IsValidationRouteScriptTarget",
        "RouteEngageRange",
        "MoveOutOfProfileDeadZone",
        "TryValidationRouteAdds",
    ):
        assert f"trashThreatControlCallbacks.{callback}" in source
        assert callback in header


def test_trash_threat_control_keeps_typed_objective_friend_and_post_boundary_state():
    source = SOURCE.read_text()
    module = MODULE.read_text()
    intervention = INTERVENTION_MODULE.read_text()
    assert "friend struct BotWorldPopulationMgrValidationRoute::ObjectiveContext;" in MGR_HEADER.read_text()
    assert "TrashThreatControl& trashThreatControl" in module
    assert "trashThreatControl.EngagedCount" in intervention
    assert "if (recordDefeatedValidationRoutePackMembers()" in source
    assert source.index("terminalArrivalContext.RunTrashThreatControl") < source.index(
        "if (recordDefeatedValidationRoutePackMembers()"
    )
