from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationCompletion.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_calibration_completion_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrCalibrationCompletion.cpp" in CMAKE.read_text()
    assert "#include \"Bots/BotWorldPopulationMgr.h\"" in text
    assert "BotWorldPopulationMgr::CompleteCalibrationScoredWindow" in text
    assert "void BotWorldPopulationMgr::CompleteCalibrationScoredWindow" not in SOURCE.read_text()


def test_calibration_completion_keeps_boundary_and_continuity_contract():
    text = MODULE.read_text()
    for marker in (
        "CalibrationSingleTargetDurationMs",
        "scheduledEndedMs",
        "CalibrationFixtureTargetPassiveObservationSampleCount",
        "PetSetupGuidMismatchSampleCount",
        "LoadedBotMatchesPinnedHunterPet",
        "CalibrationPreviousWindowValid",
        "CalibrationCompletedAoeWindows",
        "CalibrationCompletedSingleWindows",
        "DrainCalibrationPostWindowEffects",
        "ObserveCalibrationReferenceConditions",
    ):
        assert marker in text
