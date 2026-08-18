from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrReplay.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "RecordRunStart",
    "RecordRunStop",
    "LoadReplayRecord",
    "RecordReplayEvent",
    "ExecuteReplayRecord",
    "BuildReplayResultJson",
    "Replay",
    "CompareBrains",
)


def test_replay_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrReplay.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    assert module.count("BotWorldPopulationMgr::LoadReplayRecord") == 2
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_replay_module_preserves_record_and_run_lifecycle() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for table in (
        "experiment_bot_runs",
        "experiment_bot_replay_records",
        "experiment_bot_events",
        "replay_started",
        "replay_finished",
        "RecordRunStart",
        "RecordRunStop",
    ):
        assert table in module


def test_replay_module_preserves_safe_fixture_gates() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for gate in (
        "replay_record_not_found",
        "botexp_population_active",
        "botworld_or_playerbot_disabled",
        "no_available_replay_bot",
        "BotWorldRuntimeMode::ReplayFixture",
        "BotRaidAreaAuthority::Clear",
        "UpdateBot",
        "CompareBrains",
    ):
        assert gate in module
