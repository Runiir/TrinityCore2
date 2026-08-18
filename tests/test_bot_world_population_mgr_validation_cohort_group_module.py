from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationCohortGroup.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_cohort_group_module_is_bounded_and_registered():
    assert len(MODULE.read_text().splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationCohortGroup.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in MODULE.read_text()


def test_validation_cohort_group_gate_is_not_left_in_monolith():
    source = SOURCE.read_text()
    module = MODULE.read_text()
    signature = "void BotWorldPopulationMgr::EnsureValidationCohortGroup()"
    assert signature not in source
    assert signature in module


def test_validation_cohort_group_keeps_native_admission_receipts():
    module = MODULE.read_text()
    for marker in (
        "ServerProvisioningComplete",
        "AdmissionReceiptByGuid",
        "BotActionsEnabled",
        "validation_active_group_identity_drift",
        "ObserveActiveOrdinaryHunterPet",
    ):
        assert marker in module
