from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationBot.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_calibration_bot_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrCalibrationBot.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::UpdateCalibrationBot" in text
    assert "UpdateCalibrationBot" in HEADER.read_text()


def test_calibration_bot_method_is_not_left_in_monolith():
    assert "BotWorldPopulationMgr::UpdateCalibrationBot" not in SOURCE.read_text()


def test_calibration_bot_keeps_fixture_and_timeline_contract():
    text = MODULE.read_text()
    for marker in (
        "CalibrationPetObservationReady",
        "LoadedBotMatchesPinnedHunterPet",
        "ObserveEquippedGearIdentity",
        "CalibrationFixtureTargetGuid",
        "ReferenceBuffsReady",
        "UpdateCalibrationHealer",
        "UsesRangedAoeCalibrationLane",
        "DecisionTimeline",
        "MovementRangeLossTicks",
        "ThreatSampleCount",
        "ExecuteProfileCombatAction",
        "SubmitMeleeAutoAttackIntent",
    ):
        assert marker in text
