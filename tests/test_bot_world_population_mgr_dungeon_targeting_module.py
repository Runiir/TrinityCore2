from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrDungeonTargeting.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "IsDungeonTrashContext",
    "FindDungeonAnchor",
    "FindGroupCombatTarget",
    "BuildDungeonTrashPackFeatures",
)


def test_dungeon_targeting_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrDungeonTargeting.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text
        assert method in HEADER.read_text()


def test_dungeon_targeting_methods_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text


def test_dungeon_targeting_keeps_pack_risk_and_anchor_contract():
    text = MODULE.read_text()
    for marker in (
        "IsNonRaidDungeon",
        "IsDungeonBoss",
        "FindDungeonAnchor",
        "PriorityTargetGuid",
        "PrioritySpellId",
        "InterruptPriority",
        "AoeValue",
        "CcValue",
        "PullRisk",
        "HealerManaPct",
        "TankThreat",
        "AllWorldObjectsInRange",
    ):
        assert marker in text
