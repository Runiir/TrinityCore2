from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationGroup.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_calibration_group_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrCalibrationGroup.cpp" in CMAKE.read_text()
    assert "#include \"Bots/BotWorldPopulationMgr.h\"" in text
    assert "BotWorldPopulationMgr::EnsureCalibrationCohortGroup" in text
    assert "void BotWorldPopulationMgr::EnsureCalibrationCohortGroup" not in SOURCE.read_text()


def test_calibration_group_keeps_native_group_contract():
    text = MODULE.read_text()
    for marker in (
        "exact_raid_roster_plan_unavailable",
        "BuildRosterPlan",
        "sGroupMgr->AddGroup",
        "sBotMgr->GetBotRoleName",
        "lfg::PLAYER_ROLE_TANK",
        "lfg::PLAYER_ROLE_HEALER",
        "lfg::PLAYER_ROLE_DAMAGE",
    ):
        assert marker in text
