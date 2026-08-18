from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationFeralPickup.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_feral_pickup_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationFeralPickup.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::TryValidationFeralRoarPickup" in text
    assert "TryValidationFeralRoarPickup" in HEADER.read_text()


def test_validation_feral_pickup_lambda_is_not_left_in_monolith():
    text = SOURCE.read_text()
    assert "TryValidationFeralRoarPickup(state, bot, power, stage" in text
    assert "feral_move_to_healer_for_split_swarm_pickup" not in text


def test_validation_feral_pickup_keeps_native_handoff_contract():
    text = MODULE.read_text()
    for marker in (
        "feral_move_to_healer_for_split_swarm_pickup",
        "feral_demoralizing_roar_split_swarm_handoff",
        "feral_demoralizing_roar_swarm_pickup",
        "FeralActiveSwarmPickupAnchorGuid",
        "FeralHealerThreatHandoffTargetGuid",
        "RecordEvent",
        "TryCastFriendlySpell",
    ):
        assert marker in text
