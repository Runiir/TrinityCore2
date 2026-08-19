from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrTelemetryPolicy.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "GetTelemetryPolicyConfig",
    "BuildTelemetryPolicyInput",
    "RecordPolicyReplay",
    "RecordDecisionReplay",
    "BuildTelemetryFrame",
    "MaybeCaptureTelemetryClip",
)


def test_telemetry_policy_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrTelemetryPolicy.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_telemetry_policy_module_preserves_policy_and_clip_contracts() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "smartSampling",
        "alwaysRecordFailures",
        "normalDecisionSampleRate",
        "BotTelemetryPolicyInput",
        "openClip",
        "CaptureEvent",
        "BotTelemetryFrame",
    ):
        assert marker in module


def test_telemetry_policy_module_preserves_replay_persistence() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "experiment_bot_replay_records",
        "policy_replay",
        "decision_replay",
        "BotDatasetEvent::SchemaVersion",
        "WorldPolicySource",
        "ReadLastInsertId",
    ):
        assert marker in module
