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


def test_validation_cohort_runtime_pet_pinning_is_scoped_to_cohort_roster():
    text = MODULE.read_text()
    # The composition gate keeps requiring an active ordinary pet for every
    # hunter member, but the expected identity comes from the shard's own
    # frozen roster: the compile-time catalog pins one reference-world pet
    # row number and spellbook that a disjoint roster can never equal.
    assert "!LoadedBotMatchesPinnedHunterPet(bot, slot.ClassSpec)" in text
    assert "Diagnostic shards own disjoint pet rows" in text
    assert "return ObserveActiveOrdinaryHunterPet(bot, observed);" in text
    assert "ResolveExpectedHunterPetIdentity" not in text
    assert "observed.PetId == expectedPetId" not in text
