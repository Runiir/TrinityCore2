from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrQuestObjective.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "FindQuestObjective",
    "BuildHeroicRaidProgression",
)


def test_quest_objective_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrQuestObjective.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text
        assert method in HEADER.read_text()


def test_quest_objective_methods_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text


def test_quest_objective_keeps_supported_dummy_and_heroic_progression_contract():
    text = MODULE.read_text()
    for marker in (
        "QUEST_OBJECTIVES_COUNT",
        "QUEST_ITEM_OBJECTIVES_COUNT",
        "HasSimpleSupportedObjective",
        "IsDummyEntryConfigured",
        "training dummy",
        "UseAbilityOnDummy",
        "UseItemOnTarget",
        "HeroicEligible",
        "HeroicRaidBossKills",
        "TrackHeroicRaidProgression",
        "TargetItemLevel",
    ):
        assert marker in text
