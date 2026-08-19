from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteFeralTrashHandoff.cpp"
INTERVENTION_MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTrashIntervention.cpp"
TANK_MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTankTrashRecovery.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteFeralTrashHandoff.h"
OBJECTIVE_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteTerminalArrival.h"
MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_feral_trash_handoff_module_is_bounded_and_registered():
    assert len(MODULE.read_text().splitlines()) <= 1000
    assert len(HEADER.read_text().splitlines()) <= 1000
    assert len(MGR_HEADER.read_text().splitlines()) == 1000
    assert "BotWorldPopulationMgrValidationRouteFeralTrashHandoff.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in MODULE.read_text()
    assert "FeralTrashHandoffCallbacks" in HEADER.read_text()
    assert "RunFeralTrashHandoff" in OBJECTIVE_HEADER.read_text()


def test_feral_trash_handoff_has_exact_single_boundary_and_ownership():
    source = SOURCE.read_text()
    module = MODULE.read_text()
    intervention = INTERVENTION_MODULE.read_text()

    assert source.count("terminalArrivalContext.RunTrashIntervention") == 1
    assert intervention.count("terminalArrivalContext.RunFeralTrashHandoff") == 1
    assert "bool feralTrashHandoffExpired" not in source
    assert "Rerun157 localized 28 of 37 Protection healer-target samples" not in source
    assert "Rerun157 localized 28 of 37 Protection healer-target samples" not in module
    assert "Rerun157 localized 28 of 37 Protection healer-target samples" in TANK_MODULE.read_text()

    for marker in (
        "feral_charge_remote_healer_trash_cluster_in_flight",
        "feral_charge_remote_healer_trash_cluster_active_handoff",
        "feral_move_remote_healer_trash_cluster_pre_roar",
        "feral_thrash_healer_swarm_retention_before_roar",
        "feral_swipe_healer_swarm_retention_before_roar",
        "feral_demoralizing_roar_remote_healer_trash_cluster_handoff",
        "feral_hold_charge_trash_arrival_for_roar",
        "feral_hold_remote_healer_trash_cluster_for_roar",
        "feral_growl_lingering_healer_trash_attacker",
    ):
        assert module.count(marker) >= 1
        assert marker not in source

    assert module.index("bool feralTrashHandoffExpired") < module.index(
        "feralTrashChargeInFlight"
    )
    assert module.index("bool feralTrashChargeArrived") < module.index(
        "bool feralTrashHandoffActive"
    )


def test_feral_trash_handoff_passes_typed_local_dependencies():
    source = SOURCE.read_text()
    header = HEADER.read_text()
    module = MODULE.read_text()
    intervention = INTERVENTION_MODULE.read_text()

    for marker in (
        "feralTrashHandoffCallbacks.DefenseTarget",
        "feralTrashHandoffCallbacks.DefenseAttackerCount",
        "feralTrashHandoffCallbacks.TrashThreatControlResult",
    ):
        assert marker in intervention
    for marker in (
        "std::function<Player*()> DefenseTarget",
        "std::function<std::size_t()> DefenseAttackerCount",
        "std::function<TrashThreatControl const&()> TrashThreatControlResult",
    ):
        assert marker in header
    assert "callbacks.TrashThreatControlResult()" in module
    assert "Player* defenseTarget = callbacks.DefenseTarget()" in module
