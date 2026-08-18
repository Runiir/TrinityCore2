from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationActivation.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_activation_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationActivation.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::TryValidationRouteActivation" in text
    assert "TryValidationRouteActivation" in HEADER.read_text()


def test_validation_activation_lambda_is_not_left_in_monolith():
    text = SOURCE.read_text()
    assert "TryValidationRouteActivation(state, bot, power, stage" in text
    assert "native_area_trigger_unavailable" not in text


def test_validation_activation_preserves_native_interaction_contract():
    text = MODULE.read_text()
    for marker in (
        "sAreaTriggerStore.LookupEntry",
        "BotNativeAction::AreaTrigger",
        "native_area_trigger_submitted",
        "native_player_interaction_required",
        "ExecuteNativeActionIntent",
    ):
        assert marker in text

