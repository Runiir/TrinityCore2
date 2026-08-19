from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrEncounterBlackboard.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


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
