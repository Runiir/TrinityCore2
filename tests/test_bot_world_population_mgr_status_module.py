from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrStatus.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "GetStatus",
    "BuildValidationRouteEvidenceJson",
    "GetStatusJson",
    "GetSummaryJson",
    "GetBotDiagnosisJson",
    "GetBotTraceJson",
    "GetCombatLogJson",
    "GetBotDebugJson",
    "JsonEscape",
)


def test_status_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrStatus.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_status_module_preserves_operator_json_contracts() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for action in (
        "botauto_status",
        "botauto_diagnose",
        "botauto_trace",
        "botauto_combatlog",
        "botauto_debug",
        "diagnosis_schema_version",
        "trace_schema_version",
        "combat_log_schema_version",
        "debug_schema_version",
    ):
        assert action in module


def test_status_module_preserves_delta_and_debug_evidence() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for field in (
        "TraceExportCursorByGuid",
        "gap",
        "recent_events_dropped",
        "second_bucket_count",
        "target_progression_relevant",
        "dummy_allowed_by_active_quest",
        "decision_fingerprint_hash",
        "BuildBotDiagnosisObjectJson",
    ):
        assert field in module
