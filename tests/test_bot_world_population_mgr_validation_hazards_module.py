from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationHazards.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationHazards.h"
CANONICAL_CALLER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteMovementCheck.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_hazards_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert len(HEADER.read_text().splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationHazards.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgrValidationHazards.h"' in text
    for marker in (
        "BuildDefinitions",
        "FindActive",
        "PositionOutside",
        "PathOutside",
    ):
        assert marker in text


def test_validation_hazard_geometry_is_not_left_in_monolith():
    text = SOURCE.read_text()
    canonical = CANONICAL_CALLER.read_text()
    assert "BotWorldValidationHazards::FindActive" in canonical
    assert "auto refreshActiveHazards" in canonical
    assert "BotWorldValidationHazards::FindActive" not in text
    assert "auto refreshActiveHazards" not in text
    assert "struct HazardDefinition" not in text


def test_validation_hazard_module_preserves_native_geometry_contract():
    text = MODULE.read_text()
    for marker in (
        "TimedMarkerDangerActive",
        "IsValidAttackTarget",
        "CURRENT_GENERIC_SPELL",
        "PATHFIND_INCOMPLETE",
        "PositionsOutside",
    ):
        assert marker in text
