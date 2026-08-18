from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CONFIG = ROOT / "src/server/game/Bots/BotWorldPopulationMgrConfig.h"


def test_public_botworld_config_contract_is_standalone_and_bounded():
    assert len(CONFIG.read_text().splitlines()) <= 1000
    assert '#include "Bots/BotWorldPopulationMgrConfig.h"' in HEADER.read_text()
    text = CONFIG.read_text()
    for marker in (
        "BotWorldExperimentConfig",
        "BotPolicyModelConfig",
        "BotWorldStatus",
        "ValidationRouteBossRecoveryPolicy",
        "ValidationAdmissionPhase",
    ):
        assert marker in text


def test_population_manager_header_no_longer_owns_public_config_definitions():
    text = HEADER.read_text()
    assert "struct BotWorldExperimentConfig" not in text
    assert "struct BotPolicyModelConfig" not in text
    assert "struct BotWorldStatus" not in text
