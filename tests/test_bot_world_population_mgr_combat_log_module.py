from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatLog.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "BeginPendingHealCast",
    "NotifyBotSpellStarted",
    "CancelBotSpellStart",
    "NotifyCreatureDeath",
    "NotifyBotHeal",
    "ResetCombatLog",
    "FindCombatLogCohortPlayer",
    "AddCombatLogAggregate",
    "AddCombatLogEvent",
    "NotifyNativeCreatureSpellStarted",
    "NotifyNativeCreatureSpellLanded",
)


def test_combat_log_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrCombatLog.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_combat_log_module_preserves_heal_and_death_receipts() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for field in (
        "PendingHealCasts",
        "AffectedAllyGuids",
        "ValidationRouteConfirmedBossDeathGuid",
        "ValidationRouteBossDeathEvidence",
        "CombatLogRecentEvents",
        "CombatLogSecondBuckets",
        "CombatActionOutcomes",
        "CombatCandidateRejections",
        "MaxRecentCombatEvents",
    ):
        assert field in module


def test_combat_log_module_preserves_native_charge_observation() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for field in (
        "BotRaidDrudgeThreatSeed",
        "ValidationRouteDrudgeChargeObservations",
        "ValidationRouteDrudgeChargeIntervalValid",
        "NativeThreatCandidates",
        "TacticCrossLaneEligible",
        "NotifyNativeCreatureSpellLanded",
    ):
        assert field in module


def test_boss_death_callback_advances_a_pending_manifest() -> None:
    module = MODULE.read_text(encoding="utf-8")
    terminal = module.index(
        'RecordEvent(*reporterState, reporter, "validation_route_terminal"'
    )
    assert "MaybeAdvanceValidationRouteManifest();" in module[terminal:]


def test_combat_attempts_feed_the_full_window_action_ledger() -> None:
    diagnostics = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatDiagnostics.cpp").read_text()
    status = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrStatus.cpp").read_text()
    assert "CombatActionOutcomeKey" in diagnostics
    assert "ValidationRouteTerminalState" in diagnostics
    assert "action_outcomes" in status
    assert "first_at_ms" in status
    assert "retry_reason" in status
    assert "candidate_rejections" in status
