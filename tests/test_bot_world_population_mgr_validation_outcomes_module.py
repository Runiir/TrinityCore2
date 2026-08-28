from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationOutcomes.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_outcomes_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationOutcomes.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    for method in (
        "BotWorldPopulationMgr::MarkTrashClusterCleared",
        "BotWorldPopulationMgr::MarkValidationRouteTrashFailed",
        "BotWorldPopulationMgr::ClearValidationRouteKilledFocus",
        "BotWorldPopulationMgr::RecordValidationRouteBossKill",
       "BotWorldPopulationMgr::RecordValidationRouteTrashKill",
        "BotWorldPopulationMgr::RecordDefeatedValidationRouteTarget",
        "BotWorldPopulationMgr::RecordDefeatedValidationRoutePackMembers",
        "BotWorldPopulationMgr::CompleteDiscoveredPackIfReady",
    ):
        assert method in text
    assert "MarkTrashClusterCleared" in HEADER.read_text()


def test_validation_outcomes_lambdas_are_not_left_in_monolith():
    text = SOURCE.read_text()
    assert "MarkTrashClusterCleared(state, bot, power, stage" in text
    assert "MarkValidationRouteTrashFailed(state, bot, power, stage" in text
    assert "ClearValidationRouteKilledFocus(state, killedGuid)" in text
    assert "observedBestHealthPct" not in text
    assert "preservePartialWipeRendezvous" not in text


def test_validation_outcomes_preserve_terminal_and_focus_state():
    text = MODULE.read_text()
    for marker in (
        "ValidationRouteManifestAdvancePending",
        "ValidationRouteTerminalState",
        "RecordRouteProgress",
        "LastNoProgressReason",
        "ResetValidationRouteBossAddDensityState",
        "ValidationRouteUnresolvedFocusHoldCount",
    ):
        assert marker in text


def test_dead_engaged_pack_reconciliation_precedes_route_movement():
    text = SOURCE.read_text()
    reconciliation = text.index("if (recordDefeatedValidationRoutePackMembers())")
    first_movement = text.index(
        "if (TryValidationRouteMovementCheck(state, bot, power, stage, activity,")
    stale_target = text.index(
        'recordDefeatedValidationRouteTarget(target, "stale_target_seen_dead")'
    )

    assert reconciliation < first_movement
    assert first_movement < stale_target
    recovery_block = text[reconciliation:stale_target]
    assert 'situation = "validation_route_recovery";' in recovery_block
    assert 'action = "validation_route_recovery";' in recovery_block
    assert "target = nullptr;" in recovery_block
    assert "state.TargetGuid.Clear();" in recovery_block
