from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationPatrolPull.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_patrol_pull_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationPatrolPull.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::TryValidationRoutePatrolPull" in text
    assert "TryValidationRoutePatrolPull" in HEADER.read_text()


def test_validation_patrol_pull_lambda_is_not_left_in_monolith():
    text = SOURCE.read_text()
    assert "TryValidationRoutePatrolPull(state, bot, power, stage, activity" in text
    assert "sourcePathKeepsFutureEncountersSafe" not in text


def test_validation_patrol_pull_keeps_native_pull_contract():
    text = MODULE.read_text()
    for marker in (
        "ranged_patrol_to_anchor",
        "patrol_pull_contract_unresolved",
        "sourcePathKeepsFutureEncountersSafe",
        "ValidationRoutePatrolPullOwnerRosterSlot",
        "ordinary_ranged_pull_submitted",
        "validation_route_patrol_tank_action",
        "SetAllOffenseSuppressed",
    ):
        assert marker in text
