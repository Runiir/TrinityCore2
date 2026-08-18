from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationAdmission.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_admission_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationAdmission.cpp" in CMAKE.read_text()
    assert "#include \"Bots/BotWorldPopulationMgr.h\"" in text
    assert "BotWorldPopulationMgr::EnsureValidationRaidAdmission" in text
    assert "EnsureValidationRaidAdmission" in HEADER.read_text()


def test_population_controller_is_bounded_after_admission_split():
    lines = SOURCE.read_text().splitlines()
    start = next(i for i, line in enumerate(lines)
                 if line.startswith("void BotWorldPopulationMgr::EnsurePopulation("))
    end = next(i for i, line in enumerate(lines[start:], start)
               if line.startswith("void BotWorldPopulationMgr::UpdateCalibrationBot("))
    assert end - start <= 1000
    assert "EnsureValidationRaidAdmission(rosterPlan, expectedPopulation)" in "\n".join(lines[start:end])


def test_validation_admission_keeps_transaction_and_identity_contract():
    text = MODULE.read_text()
    for marker in (
        "validation_raid_admission_claim_failed",
        "validation_raid_admission_identity_drift",
        "validation_raid_preflight_exact_roster_missing",
        "validation_raid_preflight_initial_recovery_state",
        "validation_raid_admission_exact_group_or_alive_state_failed",
        "ValidationAdmissionBatchSealed",
        "ValidationRaidAdmissionComplete",
        "ValidationGhostCharacterFlag",
        "BotRaidAreaAuthority::SetAllOffenseSuppressed",
        "ProvisionWorldBotInGroup",
        "RecordRaidTelemetry",
        "rollbackAdmission",
    ):
        assert marker in text
