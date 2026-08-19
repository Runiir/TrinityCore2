from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrEventRecording.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = ("RecordEvent", "RecordDecision")


def test_event_recording_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrEventRecording.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_event_recording_preserves_deduplication_and_trace_contracts() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "RepeatableDiagnosticEventHeartbeatMs",
        "LastRepeatableEventKey",
        "SuppressedRepeatableEventCount",
        "PendingTraceSuppressedRepeatableEventCount",
        "RecordDecisionTrace",
        "experiment_bot_events",
    ):
        assert marker in module


def test_decision_recording_preserves_policy_and_progression_payloads() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "experiment_bot_decisions",
        "RecordDecisionReplay",
        "PolicyModelTrace",
        "bot_decision_mask_v3",
        "BuildActivityCandidatesJson",
        "BuildRoleSaturationState",
        "UpdateSemanticOutcomeStats",
        "increase_character_power",
        "BotProgressionGoalPolicy::QuestPortfolioSummaryJson",
    ):
        assert marker in module
