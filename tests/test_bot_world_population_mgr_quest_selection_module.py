from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrQuestSelection.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "IsQuestRelevantTarget",
    "IsProgressionCombatTarget",
    "SelectSafeTarget",
    "IsDummyEntryConfigured",
    "IsTrainingDummy",
    "SelectQuestAbilitySpell",
    "GetQuestObjectivePlan",
    "VerifyQuestObjectiveProgress",
    "SelectQuestObjectiveTarget",
    "SelectQuestGiver",
    "SelectQuestGameObject",
    "FindActiveQuestObjective",
    "HasSimpleSupportedObjective",
    "ClassifyQuestForBot",
)


def test_quest_selection_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrQuestSelection.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_quest_selection_preserves_native_target_gates() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for reason in (
        "not_progression_relevant",
        "ambient",
        "critter",
        "pet_or_totem",
        "dummy_without_quest",
        "no_loot",
        "no_xp",
    ):
        assert f'"{reason}"' in module
    assert "WorldDatabase.PQuery" in module
    assert "BotExperienceLearningPolicy::ScoreMob" in module


def test_quest_selection_keeps_objective_and_dummy_semantics() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for value in (
        "UseAbilityOnDummy",
        "UseItemOnTarget",
        "RequiresTrainingDummy",
        "RequiredSpellId",
        "QUEST_OBJECTIVES_COUNT",
        "QUEST_ITEM_OBJECTIVES_COUNT",
    ):
        assert value in module
