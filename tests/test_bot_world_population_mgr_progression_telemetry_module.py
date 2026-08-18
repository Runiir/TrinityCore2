from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrProgressionTelemetry.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "RecordRaidTelemetry",
    "RecordQuestObjectiveProgressForTarget",
    "RecordQuestEvent",
    "RecordObjectiveClusterMemory",
    "RecordExperimentSegmentEvent",
    "RecordQuestReplay",
    "RecordBossReplay",
)


def test_progression_telemetry_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrProgressionTelemetry.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_progression_telemetry_preserves_raid_and_quest_event_contracts() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "raid_telemetry",
        "raid_role_assignment",
        "raid_positioning_anchors",
        "heroic_raid_progression",
        "objective_progress",
        "objective_no_progress",
        "quest_event",
        "bot_memory_objective_clusters",
        "experiment_bot_events",
    ):
        assert marker in module


def test_progression_telemetry_preserves_replay_and_policy_gates() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "experiment_bot_replay_records",
        "RecordPolicyReplay",
        "BotTelemetryPolicy::DecideEvent",
        "writeReplay",
        "HandleTelemetryEvent",
        "UpdateSemanticOutcomeStats",
    ):
        assert marker in module
