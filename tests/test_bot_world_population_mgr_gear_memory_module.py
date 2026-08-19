from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrGearMemory.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "RecordActivityStart",
    "RecordActivityStop",
    "RecordGearEvaluation",
    "TrySmartGearDecision",
    "TryProfessionMemoryAction",
)


def test_gear_memory_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrGearMemory.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_gear_memory_module_preserves_upgrade_and_loot_contract() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for field in (
        "gear_upgrade",
        "gear_evaluated",
        "smart_loot_decision",
        "keep_upgrade_candidate",
        "need_upgrade",
        "greed_value",
        "RecordGearEvaluation",
        "UpdateSemanticOutcomeStats",
    ):
        assert field in module


def test_gear_memory_module_preserves_profession_source_memory() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for table in (
        "bot_memory_recipe_sources",
        "bot_memory_material_sources",
        "profession_recipe_acquisition",
        "material_farming_source",
        "plan_trainer_recipe_source",
        "plan_vendor_recipe_source",
    ):
        assert table in module
