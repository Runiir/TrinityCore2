from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrPopulation.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_population_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrPopulation.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::EnsurePopulation" in text
    assert "EnsurePopulation" in HEADER.read_text()


def test_population_method_is_not_left_in_monolith():
    text = SOURCE.read_text()
    assert "BotWorldPopulationMgr::EnsurePopulation" not in text


def test_population_module_keeps_admission_and_spawn_contract():
    text = MODULE.read_text()
    for marker in (
        "terminateValidationAdmission",
        "ValidationAdmissionPhase::Active",
        "EnsureValidationRaidAdmission",
        "SelectNextRosterSlot",
        "SelectPoolCandidateGuid",
        "ClaimBotGuid",
        "ResolveSpawnPlacement",
        "ProvisionWorldBotInGroup",
        "RecordSpawnResolved",
        "EnsureValidationCohortGroup",
        "ValidationAdmissionBatchSealed",
    ):
        assert marker in text
