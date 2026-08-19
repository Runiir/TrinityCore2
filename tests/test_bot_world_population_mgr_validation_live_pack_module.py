from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationLivePack.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CANONICAL_CALLER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteGroupRecovery.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_live_pack_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationLivePack.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::CurrentLiveValidationRoutePackCanContinue" in text
    assert "CurrentLiveValidationRoutePackCanContinue" in HEADER.read_text()


def test_validation_live_pack_lambda_is_not_left_in_monolith():
    text = SOURCE.read_text()
    canonical = CANONICAL_CALLER.read_text()
    assert "Manager.CurrentLiveValidationRoutePackCanContinue(" in canonical
    assert "CurrentLiveValidationRoutePackCanContinue(" not in text
    assert "selectedLivePackTarget" not in text


def test_validation_live_pack_preserves_native_gate_contract():
    text = MODULE.read_text()
    for marker in (
        "RosterCompositionValid",
        "ValidationRoutePackDeathGuids",
        "ValidationRoutePackTransitionGuids",
        "PATHFIND_NOPATH",
        "IsSuppressedFor",
        "livingHealers > 0",
        "livingDps > 0",
    ):
        assert marker in text
