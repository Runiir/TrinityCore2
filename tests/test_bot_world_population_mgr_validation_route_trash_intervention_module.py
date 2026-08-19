from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTrashIntervention.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTrashIntervention.h"
OBJECTIVE_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTerminalArrival.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_trash_intervention_module_is_bounded_registered_and_typed():
    module = MODULE.read_text()
    header = HEADER.read_text()
    source = SOURCE.read_text()
    assert len(module.splitlines()) <= 1000
    assert len(header.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationRouteTrashIntervention.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in module
    assert "struct TrashInterventionCallbacks" in header
    assert "RunTrashIntervention" in OBJECTIVE_HEADER.read_text()
    assert '.cpp"' not in header
    assert source.count("terminalArrivalContext.RunTrashIntervention") == 1


def test_trash_intervention_moves_the_contiguous_boundary_once():
    source = SOURCE.read_text()
    module = MODULE.read_text()
    for marker in (
        "dps_stack_for_trash_pickup",
        "Threat rescue is route-kind agnostic",
        "tank_trash_swarm_defensive",
        "feralSecureMarginTarget",
        "feral_growl_lingering_party_trash_attacker",
        "feral_charge_remote_party_trash_cluster_pickup",
        "feral_move_remote_party_trash_cluster_pickup",
        "RunFeralTrashHandoff",
        "RunTankTrashRecovery",
    ):
        assert marker in module
        assert marker not in source

    assert module.index("dps_stack_for_trash_pickup") < module.index(
        "tank_trash_swarm_defensive"
    )
    assert module.index("tank_trash_swarm_defensive") < module.index(
        "feral_approach_insecure_trash_threat_cluster"
    )
    assert module.index("feral_growl_lingering_party_trash_attacker") < module.index(
        "RunFeralTrashHandoff"
    ) < module.index("RunTankTrashRecovery")
    assert source.index("RunTrashIntervention") < source.index(
        "RunTankFocusAssist"
    )


def test_trash_intervention_passes_explicit_typed_dependencies():
    source = SOURCE.read_text()
    header = HEADER.read_text()
    module = MODULE.read_text()
    for callback in (
        "IsProtectionProfile",
        "RouteEngageRange",
        "IsImmediateNextValidationRouteEncounterMember",
        "FindTrashClusterThreatTarget",
        "FindLastKnownFocusTarget",
        "RouteUsableCombatTarget",
        "RememberValidationRouteFocus",
    ):
        assert f"trashInterventionCallbacks.{callback}" in source
        assert callback in header
    assert "TrashThreatControl& trashThreatControl" in module
    assert "callbacks.IsProtectionProfile" in module
    assert "callbacks.RouteEngageRange" in module
