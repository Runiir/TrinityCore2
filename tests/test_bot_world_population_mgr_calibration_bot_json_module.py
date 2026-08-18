from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationBotJson.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_calibration_bot_json_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrCalibrationBotJson.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::AppendCalibrationBotActionJson" in text
    assert "AppendCalibrationBotActionJson" in HEADER.read_text()


def test_calibration_bot_action_json_is_not_left_in_monolith():
    text = SOURCE.read_text()
    assert "AppendCalibrationBotActionJson(json, metrics);" in text
    assert 'json << ",\\"action_groups\\":["' not in text


def test_calibration_bot_json_keeps_action_and_timeline_contract():
    text = MODULE.read_text()
    for marker in (
        "expected_action_groups",
        "scheduled_damage_phases",
        "action_attempts",
        "spell_damage",
        "primary_pet_spell_damage",
        "decision_timeline",
        "off_target_damage_events",
        "PeriodicHealthAuraCandidate",
    ):
        assert marker in text
