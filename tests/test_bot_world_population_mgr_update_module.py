from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdate.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_update_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrUpdate.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::Update" in text
    assert "Update" in HEADER.read_text()


def test_update_is_not_left_in_monolith():
    assert "BotWorldPopulationMgr::Update(" not in SOURCE.read_text()


def test_update_keeps_population_calibration_and_recovery_contract():
    text = MODULE.read_text()
    for marker in (
        "RotateAutoRecordingWindowIfNeeded",
        "UpdatePendingHealCasts",
        "EnsurePopulation",
        "PublishEncounterBlackboard",
        "ReconcileNativeBattleResDecisions",
        "validation_active_member_unloaded",
        "TryReattachValidationBot",
        "EnsureCalibrationPopulation",
        "EnsureCalibrationCohortGroup",
        "RequiredPresenceSetupSpellId",
        "PersistentPetSetup",
        "RoguePoisonSetupRequired",
        "CompleteCalibrationScoredWindow",
        "MaybeAdvanceValidationRouteManifest",
    ):
        assert marker in text
