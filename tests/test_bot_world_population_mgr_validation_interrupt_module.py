from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationInterrupt.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_interrupt_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationInterrupt.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::TryValidationRouteInterrupt" in text
    assert "TryValidationRouteInterrupt" in HEADER.read_text()


def test_validation_interrupt_lambda_is_not_left_in_monolith():
    text = SOURCE.read_text()
    assert "TryValidationRouteInterrupt(state, bot, power, stage" in text
    assert "assigned_interrupt_probe" not in text


def test_validation_interrupt_preserves_cast_contract():
    text = MODULE.read_text()
    for marker in (
        "SelectInterruptSpell",
        "IsWithinLOSInMap",
        "TryCastCombatSpell",
        "MustInterrupt",
        "validation_interrupt",
    ):
        assert marker in text
