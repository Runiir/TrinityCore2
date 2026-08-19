from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTankTrashRecovery.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTankTrashRecovery.h"
OBJECTIVE_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTerminalArrival.h"
MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
THREAT_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTrashThreatControl.h"
THREAT_MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTrashThreatControl.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_tank_trash_recovery_module_is_bounded_registered_and_friended():
    assert len(MODULE.read_text().splitlines()) <= 1000
    assert len(HEADER.read_text().splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationRouteTankTrashRecovery.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in MODULE.read_text()
    assert "struct TankTrashRecoveryCallbacks" in HEADER.read_text()
    assert "RunTankTrashRecovery" in OBJECTIVE_HEADER.read_text()
    assert "friend struct BotWorldPopulationMgrValidationRoute::ObjectiveContext;" in MGR_HEADER.read_text()


def test_tank_trash_recovery_moves_the_requested_boundary_once():
    source = SOURCE.read_text()
    module = MODULE.read_text()
    assert source.count("terminalArrivalContext.RunTankTrashRecovery") == 1
    assert source.count("Rerun157 localized 28 of 37 Protection healer-target samples") == 0
    assert module.count("Rerun157 localized 28 of 37 Protection healer-target samples") == 1
    assert module.count("bool ObjectiveContext::RunTankTrashRecovery") == 1
    for marker in (
        "dark_command_healer_trash_pickup",
        "tank_trash_death_strike",
        "hand_of_protection_healer_trash_emergency",
        "hand_of_reckoning_healer_trash_pickup",
        "avengers_shield_healer_multi_trash_pickup",
        "trash_density_area_threat",
    ):
        assert marker in module
        assert marker not in source


def test_tank_trash_recovery_passes_explicit_typed_dependencies():
    source = SOURCE.read_text()
    header = HEADER.read_text()
    module = MODULE.read_text()
    for marker in (
        "tankTrashRecoveryCallbacks.DefenseTarget",
        "tankTrashRecoveryCallbacks.DefenseAttackerCount",
        "tankTrashRecoveryCallbacks.TrashThreatControlResult",
        "tankTrashRecoveryCallbacks.IsProtectionProfile",
        "tankTrashRecoveryCallbacks.RouteEngageRange",
        "tankTrashRecoveryCallbacks.IsImmediateNextValidationRouteEncounterMember",
        "tankTrashRecoveryCallbacks.FindTrashClusterThreatTarget",
        "tankTrashRecoveryCallbacks.FindLastKnownFocusTarget",
        "tankTrashRecoveryCallbacks.RouteUsableCombatTarget",
        "tankTrashRecoveryCallbacks.RememberValidationRouteFocus",
    ):
        assert marker in source
    for marker in (
        "std::function<Player*()> DefenseTarget",
        "std::function<std::size_t()> DefenseAttackerCount",
        "std::function<TrashThreatControl&()> TrashThreatControlResult",
        "std::function<bool()> IsProtectionProfile",
        "std::function<float(Player*, Unit const*, uint32)> RouteEngageRange",
        "FindTrashClusterThreatTarget",
        "FindLastKnownFocusTarget",
        "RouteUsableCombatTarget",
        "RememberValidationRouteFocus",
    ):
        assert marker in header
    assert "TrashThreatControl& trashThreatControl" in module
    assert "callbacks.TrashThreatControlResult()" in module
    assert "callbacks.DefenseTarget()" in module


def test_trash_threat_result_fields_cross_the_compile_boundary():
    header = THREAT_HEADER.read_text()
    threat_module = THREAT_MODULE.read_text()
    source = SOURCE.read_text()
    assert "bool InsecureTrashSwarm = false;" in header
    assert "bool TankOwnsTrashMajority = false;" in header
    assert "trashThreatControl.InsecureTrashSwarm =" in threat_module
    assert "trashThreatControl.TankOwnsTrashMajority =" in threat_module
    assert "bool insecureTrashSwarm" not in threat_module
    assert "bool tankOwnsTrashMajority" not in threat_module
    assert "trashThreatControl.InsecureTrashSwarm" in source
    assert "trashThreatControl.TankOwnsTrashMajority" in source
