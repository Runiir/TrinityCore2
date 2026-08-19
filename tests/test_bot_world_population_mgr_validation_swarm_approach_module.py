from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationSwarmApproach.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CANONICAL_CALLER = ROOT / (
    "src/server/game/Bots/Content/Dungeons/Stonecore/Encounters/"
    "HighPriestessAzil/HighPriestessAzilAddWaveOrchestration.cpp"
)
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_swarm_approach_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationSwarmApproach.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::ContinueStableTankSwarmApproach" in text
    assert "ContinueStableTankSwarmApproach" in HEADER.read_text()


def test_validation_swarm_approach_lambda_is_not_left_in_monolith():
    text = SOURCE.read_text()
    canonical = CANONICAL_CALLER.read_text()
    assert "manager.ContinueStableTankSwarmApproach(state, selectedAdd," in canonical
    assert "ContinueStableTankSwarmApproach(state, selectedAdd" not in text
    assert "uint64 stableApproachLimitMs" not in text


def test_validation_swarm_approach_keeps_native_dwell_contract():
    text = MODULE.read_text()
    for marker in (
        "LastPathChangeMs",
        "ActivePathValid",
        "IsMoving",
        "feral_druid_tank",
        "tankDensityClusterRadius",
    ):
        assert marker in text
