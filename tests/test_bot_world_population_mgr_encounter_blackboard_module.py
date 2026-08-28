import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrEncounterBlackboard.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
SCENARIO_CONFIG = ROOT / "experiments/configs/validation_scenarios_cata_001.json"


def test_encounter_blackboard_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrEncounterBlackboard.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::PublishEncounterBlackboard" in text
    assert "PublishEncounterBlackboard" in HEADER.read_text()


def test_encounter_blackboard_is_not_left_in_monolith():
    assert "BotWorldPopulationMgr::PublishEncounterBlackboard" not in SOURCE.read_text()


def test_encounter_blackboard_keeps_immutable_observation_contract():
    text = MODULE.read_text()
    for marker in (
        "EncounterSnapshotNextRefreshMs",
        "EncounterSnapshotRevision",
        "BotEncounter::Blackboard",
        "BotEncounter::ActorSnapshot",
        "BotEncounter::TargetChannels",
        "ValidationRouteManifestIndex",
        "AllWorldObjectsInRange",
        "snapshot->Hostiles",
        "snapshot->Interactables",
    ):
        assert marker in text


def test_encounter_blackboard_retains_only_route_declared_passive_mechanics():
    text = MODULE.read_text()
    assert "if (!attackable)" in text
    assert "creature->HasReactState(REACT_PASSIVE)" in text
    assert "std::binary_search(snapshot->Route.AllowedEntries.begin()," in text
    assert "else if (actor.Interactable || routeObserved)" in text
    assert "observer->IsValidAttackTarget(unit)" in text


def test_magmaw_routes_declare_passive_hook_spike():
    config = json.loads(SCENARIO_CONFIG.read_text(encoding="utf-8"))
    wanted = {
        "blackwing_descent_10n",
        "blackwing_descent_10n_magmaw_diagnostic",
    }
    magmaw_nodes = [
        step
        for scenario_group in ("scenarios", "diagnostic_scenarios")
        for scenario in config[scenario_group]
        if scenario["id"] in wanted
        for step in scenario["route"]
        if step.get("node_id") == "bwd.magmaw.encounter"
    ]
    assert len(magmaw_nodes) == 2
    assert all(node.get("scripted_event_entries") == [41767]
        for node in magmaw_nodes)
