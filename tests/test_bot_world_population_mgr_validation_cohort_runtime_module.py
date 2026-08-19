from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationCohortRuntime.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_cohort_runtime_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationCohortRuntime.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::UpdateValidationCohortRaidRuntime" in text
    assert "UpdateValidationCohortRaidRuntime" in HEADER.read_text()


def test_validation_cohort_runtime_method_is_not_left_in_monolith():
    assert "BotWorldPopulationMgr::UpdateValidationCohortRaidRuntime" not in SOURCE.read_text()


def test_validation_cohort_runtime_keeps_native_roster_and_recovery_contract():
    text = MODULE.read_text()
    for marker in (
        "RaidRuntime& raid = Cohort().Raid",
        "RosterCompositionValid",
        "NativeSignalsByGuid",
        "ObserveNativeRaidHostileActivity",
        "NativeRecoveryEvidenceComplete",
        "NativeReadyCheckActionObserved",
        "LoadedBotMatchesDeclaredSpec",
        "LoadedBotMatchesPinnedHunterPet",
        "raid.ReadyCheckSatisfied",
    ):
        assert marker in text
