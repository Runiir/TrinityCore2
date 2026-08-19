from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationPopulation.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_calibration_population_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrCalibrationPopulation.cpp" in CMAKE.read_text()
    assert "#include \"Bots/BotWorldPopulationMgr.h\"" in text
    assert "BotWorldPopulationMgr::EnsureCalibrationPopulation" in text
    assert "void BotWorldPopulationMgr::EnsureCalibrationPopulation" not in SOURCE.read_text()


def test_calibration_population_keeps_fixture_geometry_contract():
    text = MODULE.read_text()
    for marker in (
        "BotCalibrationFixtureContractGenerated::TargetEntry",
        "UsesRangedAoeCalibrationLane",
        "calibration_fixture_spec_contract_missing",
        "calibration_isolated_target_not_dry_land",
        "calibration_isolated_target_fidelity_mismatch",
        "PathGenerator",
        "nativeMeleeReachable",
        "CharacterDatabase.DirectPExecute",
        "SelectCalibrationPoolCandidateGuid",
    ):
        assert marker in text
