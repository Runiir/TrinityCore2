from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationHealer.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_calibration_healer_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrCalibrationHealer.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::UpdateCalibrationHealer" in text
    assert "UpdateCalibrationHealer" in HEADER.read_text()


def test_calibration_healer_method_is_not_left_in_monolith():
    assert "BotWorldPopulationMgr::UpdateCalibrationHealer" not in SOURCE.read_text()


def test_calibration_healer_keeps_response_and_action_contract():
    text = MODULE.read_text()
    for marker in (
        "ControlledDispelAuraForHealer",
        "HealResponseLatenciesMs",
        "LastControlledDamageMsByTarget",
        "DispelAttempts",
        "CooldownAttempts",
        "HealSelectionAttempts",
        "BotActionProfileSpell",
        "TryCastFriendlySpell",
        "SelectHealSpell",
        "recordHealResponse",
    ):
        assert marker in text
