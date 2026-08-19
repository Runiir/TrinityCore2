from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrQuestRouting.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "ResolveObjectiveRoutePoint",
    "BuildQuestPortfolioPlan",
    "SelectQuestObjectiveBucket",
    "FindQuestTurnInDestination",
    "FindQuestPickupDestination",
    "HasNearbySupportedQuestGiver",
    "IsGenericGrindingAllowed",
    "MoveToObjectiveSearchPoint",
    "ChooseQuestReward",
)


def test_quest_routing_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrQuestRouting.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_quest_routing_preserves_native_route_sources() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for source in (
        "visible_target",
        "visible_object",
        "creature_spawn",
        "gameobject_spawn",
        "quest_poi",
        "remembered_poi",
        "creature_questender",
        "gameobject_questender",
        "creature_queststarter",
        "gameobject_queststarter",
    ):
        assert f'"{source}"' in module
    assert "WorldDatabase.PQuery" in module
    assert "CharacterDatabase.PQuery" in module


def test_quest_routing_keeps_grinding_and_reward_gates() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for reason in (
        "combat_disabled",
        "grinding_disabled",
        "active_quest_objective",
        "recently_accepted_quest",
        "known_objective_target",
        "nearby_supported_quest",
        "activity_not_grinding",
    ):
        assert f'"{reason}"' in module
    assert "BotLongTermProgressionBrain::ScoreItemForRole" in module
