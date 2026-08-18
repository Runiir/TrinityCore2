from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationReference.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "ApplyCalibrationReferenceConditions",
    "ObserveCalibrationReferenceConditions",
    "UpdateCalibrationTargetHealthSchedule",
)


def test_calibration_reference_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrCalibrationReference.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text
        assert method in HEADER.read_text()


def test_calibration_reference_methods_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text


def test_calibration_reference_keeps_aura_and_health_window_contract():
    text = MODULE.read_text()
    for marker in (
        "CalibrationSpecUsesMana",
        "CalibrationExecuteHealthWindows",
        "CalibrationExecuteHealthWindowIndex",
        "CalibrationSingleTargetDurationMs",
        "ReferencePlayerAuraActiveSamples",
        "ReferenceTargetAuraOwnerMismatchSamples",
        "CalibrationFixtureTargetPassiveObservationSampleCount",
        "TargetHealthPhaseObservations",
        "target->SetHealth(desiredHealth)",
        "target->GetAura(58567, bot->GetGUID())",
    ):
        assert marker in text
