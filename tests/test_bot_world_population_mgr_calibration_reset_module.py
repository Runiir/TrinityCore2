from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationReset.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_calibration_reset_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrCalibrationReset.cpp" in CMAKE.read_text()
    assert "#include \"Bots/BotWorldPopulationMgr.h\"" in text
    assert "BotWorldPopulationMgr::ResetCalibrationScoredWindow" in text
    assert "void BotWorldPopulationMgr::ResetCalibrationScoredWindow" not in SOURCE.read_text()


def test_calibration_reset_keeps_pre_score_contract():
    text = MODULE.read_text()
    for marker in (
        "CalibrationPetObservationReady",
        "OrdinaryPetSetupSnapshot",
        "BotCalibrationFixtureContractGenerated::RequiredSetupAuraSpellIds",
        "calibration_target_fidelity_drift_before_scoring",
        "calibration_initial_resource_contract_mismatch",
        "calibration_pre_score_state_contract_mismatch",
        "InitialResourceSourceContract",
        "PreScoreGlobalCooldownClear",
        "CalibrationScoredStartedMs",
        "ObserveCalibrationReferenceConditions",
    ):
        assert marker in text
