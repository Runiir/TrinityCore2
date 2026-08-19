from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrSpawnMemory.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "ResolveSpawnPlacement",
    "ResolveSavedSpawnPlacement",
    "ResolveRaceStartSpawnPlacement",
    "ResolveNearPlayerSpawnPlacement",
    "ResolveConfiguredCenterSpawnPlacement",
    "PersistBotPosition",
    "RecordSpawnResolved",
    "RememberSafePosition",
    "RememberVisiblePois",
    "RememberPoi",
    "RememberVisibleSourceMemory",
    "MarkDeathDangerZone",
    "MarkStuckFailure",
    "GetLocalDangerScore",
    "IsFailedPathRecently",
    "FindMemoryPoiTarget",
    "MarkPoiVisited",
)


def test_spawn_memory_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrSpawnMemory.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_spawn_memory_preserves_route_and_native_storage_boundaries() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for source in (
        "saved_position",
        "race_start",
        "near_player",
        "configured_center",
        "spawn_resolved",
        "visible_scan",
        "repeated_death",
        "stuck",
    ):
        assert source in module
    assert "CharacterDatabase.PQuery" in module
    assert "CharacterDatabase.DirectPExecute" in module
    assert "MapManager::IsValidMapCoord" in module


def test_spawn_memory_keeps_learned_poi_scoring() -> None:
    module = MODULE.read_text(encoding="utf-8")
    assert "BotExperienceLearningPolicy::ScorePoi" in module
    assert "BotExperienceLearningPolicy::ScorePath" in module
