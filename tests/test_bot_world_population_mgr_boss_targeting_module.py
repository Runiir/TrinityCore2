from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrBossTargeting.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "IsBossContext",
    "FindBossTarget",
    "BuildBossMechanicFeatures",
)


def test_boss_targeting_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrBossTargeting.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text
        assert method in HEADER.read_text()


def test_boss_targeting_methods_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text


def test_boss_targeting_keeps_encounter_and_group_feature_contract():
    text = MODULE.read_text()
    for marker in (
        "IsDungeonBoss",
        "isWorldBoss",
        "SpellLooksDangerous",
        "SpellLooksLikeGroundDanger",
        "SpellLooksRaidWide",
        "SpellLooksTankSpike",
        "PriorityAddGuid",
        "InteractableGuid",
        "VehicleGuid",
        "StackPlaceholder",
        "SpreadPlaceholder",
        "HealerManaPct",
    ):
        assert marker in text
