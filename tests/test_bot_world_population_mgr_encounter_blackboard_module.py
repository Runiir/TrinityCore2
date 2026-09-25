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


def test_encounter_blackboard_retains_magmaw_native_pincer_warning():
    text = MODULE.read_text()
    assert "IsMagmawPincerWarningCreature" in text
    assert 'route.NodeId != "bwd.magmaw.encounter"' in text
    pincer_start = text.index("bool IsMagmawPincerWarningCreature")
    pincer = text[pincer_start:text.index("\n}\n}", pincer_start)]
    assert "creature.GetEntry() == 47330" not in pincer
    assert "creature.GetEntry() == 47196 && creature.HasAura(87949)" in pincer
    assert "creature.GetEntry() == 47330" not in text[pincer_start:]
    assert "else if (pincerWarning)" in text
    assert "snapshot->Hostiles.push_back(std::move(actor));" in text


def test_magmaw_routes_declare_passive_hook_spike():
    config = json.loads(SCENARIO_CONFIG.read_text(encoding="utf-8"))
    wanted = {
        "blackwing_descent_10n",
        "blackwing_descent_10n_magmaw_diagnostic",
    }
    magmaw_nodes = {
        scenario["id"]: step
        for scenario_group in ("scenarios", "diagnostic_scenarios")
        for scenario in config[scenario_group]
        if scenario["id"] in wanted
        for step in scenario["route"]
        if step.get("node_id") == "bwd.magmaw.encounter"
    }
    assert set(magmaw_nodes) == wanted
    assert all(node.get("scripted_event_entries") == [41767]
        for node in magmaw_nodes.values())
    # The composed full raid keeps the two-tank assignment; the accepted
    # Magmaw shard is a single Blood tank and declares no tank pair.
    full = magmaw_nodes["blackwing_descent_10n"]["mechanic_contract"]
    assert (full["main_tank_roster_slot"], full["off_tank_roster_slot"]) == (2, 1)
    shard = magmaw_nodes["blackwing_descent_10n_magmaw_diagnostic"]["mechanic_contract"]
    assert "main_tank_roster_slot" not in shard
    assert "off_tank_roster_slot" not in shard


def test_encounter_blackboard_publishes_configured_tank_assignment_lease():
    text = MODULE.read_text()
    assert "ResolveConfiguredRaidTankAssignment(mainTankGuid, offTankGuid)" in text
    assert 'lease.Slot = "main_tank"' in text
    assert "lease.AssigneeGuid = mainTankGuid" in text
    assert "lease.BackupGuid = offTankGuid" in text
