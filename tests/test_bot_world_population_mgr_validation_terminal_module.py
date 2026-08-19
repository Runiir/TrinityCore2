from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationTerminal.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_terminal_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationTerminal.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::MarkValidationRouteTerminalAfterProgress" in text
    assert "MarkValidationRouteTerminalAfterProgress" in HEADER.read_text()


def test_validation_terminal_lambda_is_not_left_in_monolith():
    text = SOURCE.read_text()
    canonical = MODULE.read_text()
    assert "BotWorldPopulationMgr::MarkValidationRouteTerminalAfterProgress(" in canonical
    assert "MarkValidationRouteTerminalAfterProgress(" not in text
    assert "route_exhausted_after_progress" not in text


def test_validation_terminal_preserves_route_recovery_event():
    text = MODULE.read_text()
    for marker in (
        "ValidationRouteFocusGuid",
        "ValidationRouteTerminalState",
        "LoopRecoveryCooldownUntilMs",
        "validation_route_recovery",
        "validation_route_failed",
    ):
        assert marker in text
