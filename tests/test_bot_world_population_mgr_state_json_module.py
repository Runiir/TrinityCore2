from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrStateJson.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "BuildRawJson",
    "BuildSemanticJson",
    "BuildRoleSaturationState",
    "BuildConfigJson",
)


def test_state_json_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrStateJson.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_state_json_preserves_raw_and_semantic_observation_contracts() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "target_cast_spell_id",
        "native_recovery_episode",
        "bot_semantic_phase6_v1",
        "learned_outcomes",
        "embedding_features",
        "quest_work",
        "trash_pack",
        "boss_mechanics",
        "raid_role_assignment",
    ):
        assert marker in module


def test_state_json_preserves_config_and_policy_contracts() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "bot_world_autonomy",
        "validation_route",
        "telemetry_enabled",
        "bot_learning",
        "bot_policy_model",
        "role_saturation_state_json",
        "BuildRoleSaturationState",
    ):
        assert marker in module
