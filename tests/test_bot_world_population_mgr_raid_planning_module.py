from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRaidPlanning.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "BuildRaidRoleAssignment",
    "BuildRaidPositioningAnchors",
    "BuildRaidMechanicAdapter",
    "BuildRaidGearTargetPlan",
)


def test_raid_planning_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrRaidPlanning.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text
        assert method in HEADER.read_text()


def test_raid_planning_methods_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text


def test_raid_planning_keeps_native_assignment_and_formation_contract():
    text = MODULE.read_text()
    for marker in (
        "RosterSlotId",
        "MainTankGuid",
        "FormationFamily",
        "FormationAnchor",
        "FormationOrientation",
        "route_anchor",
        "ControlledAoeMinimumTargets",
        "KillSyncExecutionFloorPct",
        "BattleResurrectionSlots",
        "PlatformDestinationMapId",
        "fail_closed_no_fidelity_acceptance",
        "TargetItemLevel",
        "ReadyForHeroicRaid",
    ):
        assert marker in text
