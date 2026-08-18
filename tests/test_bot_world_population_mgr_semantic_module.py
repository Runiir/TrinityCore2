from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrSemantic.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "NotifyBotSpellFinished",
    "NotifyBotItemSpellFinished",
    "FlushPendingHealCast",
    "ClearPendingHealCasts",
    "UpdatePendingHealCasts",
    "UpdateSemanticOutcomeStats",
    "UpdateSemanticStatsFromEvent",
    "GetSemanticOutcomeStats",
    "BuildOutcomeStatsJson",
    "BuildEmbeddingFeaturesJson",
    "BuildNativeRecoveryEpisodeJson",
)


def test_semantic_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrSemantic.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_semantic_module_preserves_healing_lifecycle_receipts() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for field in (
        "bot_healing_lifecycle_v1",
        "SpellFinished",
        "collection_window_closed",
        "cast_deadline_exceeded",
        "PendingHealCasts",
        "NativePersistentPetSetupReceipt",
        "NativePoisonSetupReceipt",
    ):
        assert field in module


def test_semantic_module_preserves_outcome_feature_contract() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for field in (
        "bot_semantic_phase6_v1",
        "danger_score",
        "progression_value",
        "embedding_json",
        "SemanticMechanicKey",
        "EventLooksFailure",
        "BuildRoleSaturationState",
        "BuildNativeRecoveryEpisodeJson",
    ):
        assert field in module
