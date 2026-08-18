from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrLifecycle.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "IsActive",
    "Start",
    "Stop",
    "StartAutonomy",
    "StopAutonomy",
    "Shutdown",
    "SpawnAutonomyBots",
)


def test_lifecycle_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrLifecycle.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text
        assert method in HEADER.read_text()


def test_lifecycle_methods_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text


def test_lifecycle_keeps_population_and_run_teardown_contract():
    text = MODULE.read_text()
    for marker in (
        "EnsurePopulation();",
        "RecordRunStart();",
        "RecordRunStop();",
        "FlushOpenClips",
        "ReleaseCohortLeases();",
        "RemoveWorldBot",
        "CharacterDatabase.DirectPExecute",
        "BotRaidAreaAuthority::Clear",
        "Cohort().RuntimeMode = BotWorldRuntimeMode::AlwaysOnAutonomy",
    ):
        assert marker in text
