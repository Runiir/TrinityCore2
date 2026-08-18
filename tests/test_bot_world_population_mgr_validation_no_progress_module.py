from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationNoProgress.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_no_progress_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationNoProgress.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::MaybeValidationPrerequisiteNoProgressAssist" in text
    assert "MaybeValidationPrerequisiteNoProgressAssist" in HEADER.read_text()


def test_validation_no_progress_lambda_is_not_left_in_monolith():
    text = SOURCE.read_text()
    assert "MaybeValidationPrerequisiteNoProgressAssist(state, bot, power" in text
    assert "observedBestHealthPct" not in text


def test_validation_no_progress_preserves_progress_contract():
    text = MODULE.read_text()
    for marker in (
        "noProgressSampleIntervalMs",
        "ValidationRoutePackNoProgressCount",
        "ValidationRouteCombatNoProgressCount",
        "unengaged_trash_target_repath",
        "validation_trash_no_progress",
        "RecordRouteProgress",
        "MarkValidationRouteTrashFailed",
    ):
        assert marker in text

