from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationFocus.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_focus_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationFocus.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::FindValidationRouteGroupFocusTarget" in text
    assert "FindValidationRouteGroupFocusTarget" in HEADER.read_text()


def test_validation_focus_lambda_is_not_left_in_monolith():
    text = SOURCE.read_text()
    assert "FindValidationRouteGroupFocusTarget(bot" in text
    assert "livingTankAvailable" not in text


def test_validation_focus_preserves_group_vote_contract():
    text = MODULE.read_text()
    for marker in (
        "ValidationRouteFocusGuid",
        "livingTankAvailable",
        "activeTankFocus",
        "GroupReference",
        "countVote",
        "bestScore",
    ):
        assert marker in text

