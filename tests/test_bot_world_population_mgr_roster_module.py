from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRoster.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "GetLoadedBot",
    "GetBot",
    "BuildRosterPlan",
    "SelectNextRosterSlot",
    "GetBotClassSpec",
    "SelectPoolCandidateGuid",
    "SelectCalibrationPoolCandidateGuid",
)


def test_roster_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrRoster.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text
        assert method in HEADER.read_text()


def test_roster_methods_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text


def test_roster_keeps_exact_role_and_lease_selection_contract():
    text = MODULE.read_text()
    for marker in (
        "raid_tank_",
        "raid_healer_",
        "raid_dps_",
        "party_tank_1",
        "party_healer_1",
        "all_spec_candidate_pool",
        "PoolClassSpecFilter",
        "FailedSpawnGuids",
        "rejectedGuids",
        "expectedGuid",
        "expectedClassSpec",
    ):
        assert marker in text
