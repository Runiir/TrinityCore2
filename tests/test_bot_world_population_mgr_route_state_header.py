from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
ROUTE_STATE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRouteState.h"


def test_route_state_header_is_bounded_and_directly_included():
    assert len(ROUTE_STATE.read_text().splitlines()) <= 1000
    assert '#include "Bots/BotWorldPopulationMgrRouteState.h"' in HEADER.read_text()
    text = ROUTE_STATE.read_text()
    for marker in (
        "RaidRosterPlanSlot",
        "BotWorldExperimentProfile",
        "ValidationRouteManifestNode",
        "ValidationRouteDrudgeChargeObservation",
        "ValidationRouteDrudgeThreatSeedEvidence",
    ):
        assert marker in text


def test_population_manager_keeps_private_aliases_for_route_state_names():
    text = HEADER.read_text()
    for marker in (
        "using RaidRosterPlanSlot",
        "using ValidationRouteManifestNode",
        "using ValidationRouteDrudgeMemberGeometry",
    ):
        assert marker in text
    assert "struct ValidationRouteManifestNode" not in text
    assert "struct ValidationRouteDrudgeChargeObservation" not in text
