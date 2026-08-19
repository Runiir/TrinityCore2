from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
BOT_STATE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrBotState.h"


def test_bot_state_header_is_bounded_and_directly_included():
    assert len(BOT_STATE.read_text().splitlines()) <= 1000
    assert '#include "Bots/BotWorldPopulationMgrBotState.h"' in HEADER.read_text()
    text = BOT_STATE.read_text()
    for marker in (
        "struct WorldBotState",
        "NativePersistentPetSetupReceipt",
        "DecisionTraceEntry",
        "BotQuestWorkState",
        "ValidationRouteDescentPhase",
    ):
        assert marker in text


def test_population_manager_uses_a_private_bot_state_alias():
    text = HEADER.read_text()
    assert "using WorldBotState = BotWorldPopulationMgrBotState::WorldBotState" in text
    assert "struct WorldBotState" not in text
