from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationTargeting.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_targeting_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationTargeting.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::ResolveUsableValidationRouteCombatTarget" in text
    assert "ResolveUsableValidationRouteCombatTarget" in HEADER.read_text()


def test_validation_targeting_lambda_is_not_left_in_monolith():
    text = SOURCE.read_text()
    assert "ResolveUsableValidationRouteCombatTarget(bot, discoveryLeg" in text
    assert "unengagedListedBossAdd" not in text


def test_validation_targeting_preserves_admission_contract():
    text = MODULE.read_text()
    for marker in (
        "ValidationRouteFinalTransitionGuids",
        "ValidationRoutePackMemberGuids",
        "currentDiscoveryPackMember",
        "explicitTerminalCombatFocus",
        "ValidationRouteAddTargetEntries",
        "IsDungeonBoss",
    ):
        assert marker in text

