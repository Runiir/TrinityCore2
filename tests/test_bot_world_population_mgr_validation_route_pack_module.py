from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRoutePack.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CONTEXTS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteContexts.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_route_pack_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationRoutePack.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BuildValidationRoutePackContext" in text
    assert "BuildValidationRoutePackContext" in HEADER.read_text()
    assert CONTEXTS.exists()


def test_validation_route_pack_membership_is_not_left_in_monolith():
    source = SOURCE.read_text()
    module = MODULE.read_text()
    assert "pack.EnrollMember" in source
    assert "pack.RetireStaleMembers" in source
    for marker in (
        "ValidationRoutePackMemberGuids",
        "ValidationRoutePackDeathGuids",
        "ValidationRoutePackTransitionGuids",
        "RecordScriptedTransition",
        "RetireStaleMembers",
        "EnrollEngagedMembers",
        "HasLiveMembers",
    ):
        assert marker in module
