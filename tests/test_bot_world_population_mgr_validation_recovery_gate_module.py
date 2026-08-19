from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRecoveryGate.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "IsImmediateNextValidationRouteBossTarget",
    "IsImmediateNextValidationRouteEncounterMember",
    "IsNativeRaidRecoveryEvidencePending",
    "SuppressNativeRaidRecovery",
)


def test_validation_recovery_gate_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationRecoveryGate.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text
        assert method in HEADER.read_text()


def test_validation_recovery_gate_methods_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text


def test_validation_recovery_gate_keeps_future_guard_and_native_hold_contract():
    text = MODULE.read_text()
    for marker in (
        "ValidationRoutePackGeneration",
        "ValidationRoutePackMemberGuids",
        "ValidationRoutePackDeathGuids",
        "ValidationRoutePackTransitionGuids",
        "NativeFullWipeOnly",
        "NativeRecoveryHoldActive",
        "NativeRecoveryEvidenceComplete",
        "SetAllOffenseSuppressed",
        "native_recovery_evidence_pending",
        "NativeRecoveryHoldWipeGeneration",
        "controlledActive",
    ):
        assert marker in text
