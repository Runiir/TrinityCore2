from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrDecisionTrace.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "PersistDecisionFingerprintDelta",
    "FlushDecisionFingerprintMemory",
    "FlushPendingDecisionFingerprintMemory",
    "RecordDecisionFingerprintMemory",
    "RecordDecisionTrace",
)


def test_decision_trace_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrDecisionTrace.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_decision_trace_module_preserves_fingerprint_persistence() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for field in (
        "bot_memory_decision_fingerprints",
        "fingerprint_source",
        "DecisionFingerprintPersistHeartbeatMs",
        "LastDecisionFingerprintPersistedRepeatCount",
        "ON DUPLICATE KEY UPDATE",
    ):
        assert field in module


def test_decision_trace_module_preserves_native_context_receipts() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for field in (
        "DecisionTraceEntry",
        "EngagedHostileGuids",
        "TankOwnedHostileGuids",
        "HealerTargetingHostileGuids",
        "LoopGuardrailAction",
        "BlockedEpisodeId",
        "LastCombatAttempt",
        "LastRouteProgress",
    ):
        assert field in module
