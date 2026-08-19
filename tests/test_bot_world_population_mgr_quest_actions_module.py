from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrQuestActions.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_quest_actions_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrQuestActions.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    assert "BotWorldPopulationMgr::TryQuesting" in module
    assert "BotWorldPopulationMgr::TryQuesting" not in world


def test_quest_actions_preserves_native_submission_wrappers() -> None:
    module = MODULE.read_text(encoding="utf-8")
    assert "HandleQuestgiverAcceptQuestOpcode" in module
    assert "HandleQuestgiverChooseRewardOpcode" in module
    assert "CMSG_QUEST_GIVER_ACCEPT_QUEST" in module
    assert "CMSG_QUEST_GIVER_CHOOSE_REWARD" in module
    assert "SubmitNativeQuestAccept(bot" in module
    assert "SubmitNativeQuestReward(bot" in module


def test_quest_actions_preserves_objective_state_transitions() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for phase in (
        "move_to_turnin",
        "verify_progress",
        "search_objective",
        "choose_objective",
        "kill_objective_mob",
        "move_to_target",
        "quest_pickup_search",
    ):
        assert f'"{phase}"' in module
    for action in (
        "reconcile_completed_objective",
        "complete_quest",
        "accept_quest",
        "choose_objective",
        "kill_quest_mob",
        "await_visible_quest_giver",
    ):
        assert f'"{action}"' in module
