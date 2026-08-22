from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteGroupRecovery.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteGroupRecovery.h"
MGR_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_route_group_recovery_module_is_bounded_and_registered():
    module = MODULE.read_text()
    assert len(module.splitlines()) <= 1000
    assert HEADER.exists()
    assert "BotWorldPopulationMgrValidationRouteGroupRecovery.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in module
    assert "BotWorldPopulationMgr::TryValidationRouteGroupRecovery" in module
    assert "GroupRecoveryRequest" in HEADER.read_text()
    assert "GroupRecoveryContext" in MGR_HEADER.read_text()


def test_group_recovery_is_extracted_at_the_validation_route_boundary():
    source = SOURCE.read_text()
    module = MODULE.read_text()
    source_call = source.index("TryValidationRouteGroupRecovery")
    terminal_context = source.index("ObjectiveContext terminalArrivalContext")
    assert source_call < terminal_context
    assert "terminalArrivalContext.Run()" in source
    assert "auto markValidationRouteTerminalAfterProgress" not in source
    assert "RetireStalePackMembers" in source
    for marker in (
        "CurrentLiveValidationRoutePackCanContinue",
        "EnrollEngagedPackMembers",
        "PersistedPackHasLiveMembers",
        "RetireStalePackMembers",
        "native_full_wipe_hold_partial_death",
        "validation_route_partial_wipe_retreat_rendezvous",
        "validation_route_tactical_retreat",
        "validation_route_hold_retreat",
    ):
        assert marker in module
    assert "Partial deaths do not make a trash pull terminal" in module
    assert "drudge_partial_death_before_threat_seed" not in module
    assert "drudge_native_full_wipe_hold_partial_death" not in module


def test_group_recovery_passes_pack_and_failure_callbacks_explicitly():
    source = SOURCE.read_text()
    for marker in (
        "groupRecoveryCallbacks.RetireStalePackMembers",
        "groupRecoveryCallbacks.EnrollEngagedPackMembers",
        "groupRecoveryCallbacks.PersistedPackHasLiveMembers",
        "groupRecoveryCallbacks.IsPackEntry",
        "groupRecoveryCallbacks.ResolvedTransitionAura",
    ):
        assert marker in source
