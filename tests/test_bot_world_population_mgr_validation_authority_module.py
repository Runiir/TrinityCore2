from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationAuthority.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_authority_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationAuthority.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::ConfigureValidationRouteCombatAuthority" in text
    assert "ConfigureValidationRouteCombatAuthority" in HEADER.read_text()


def test_validation_authority_setup_is_not_left_in_monolith():
    text = SOURCE.read_text()
    assert "TryValidationRouteObjectiveGate" in text
    assert "SetProtectedEncounterEntries" not in text


def test_validation_authority_keeps_future_encounter_safety_contract():
    text = MODULE.read_text()
    for marker in (
        "ValidationRouteManifestIndex + 1",
        "SplitSourceGuids",
        "ValidationRoutePackMemberGuids",
        "SetProtectedEncounterEntries",
        "SetProtectedEncounterSpawnIds",
        "SetAllowedEncounterGuids",
        "SetAllOffenseSuppressed",
    ):
        assert marker in text
