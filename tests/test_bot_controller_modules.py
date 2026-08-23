from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
MONOLITH = BOT_DIR / "BotController.cpp"

MODULES = {
    "BotController.cpp": (
        "BotController::Update",
        "BotController::GetStatus",
    ),
    "BotControllerMovement.cpp": (
        "BotController::BuildMovementFrame",
        "BotController::ApplyMovementPolicy",
    ),
    "BotControllerCombat.cpp": (
        "BotController::BuildCombatState",
        "BotController::DecideSoloCombat",
        "BotController::ResolveSoloCombat",
        "BotController::SelectProfileCombatAction",
        "BotController::ResolveProfileCombat",
        "BotController::TryExecuteQueuedCombatAction",
    ),
    "BotControllerHealer.cpp": (
        "BotController::TryResolveHealerAction",
        "BotController::BuildFrame",
    ),
    "BotControllerRecording.cpp": (
        "BotController::BuildProfessionFrame",
        "BotController::RecordFrame",
        "BotController::RecordProfessionFrame",
        "BotController::RecordCombatFrame",
        "BotController::RecordMovementFrame",
    ),
}


def test_bot_controller_modules_are_bounded_and_registered():
    cmake = CMAKE.read_text(encoding="utf-8")
    for filename, methods in MODULES.items():
        source = BOT_DIR / filename
        text = source.read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 1000
        assert filename in cmake
        for method in methods:
            assert f"{method}(" in text

    header = BOT_DIR / "BotController.h"
    assert len(header.read_text(encoding="utf-8").splitlines()) <= 1000


def test_bot_controller_methods_are_not_left_in_the_lifecycle_module():
    lifecycle = MONOLITH.read_text(encoding="utf-8")
    for filename, methods in MODULES.items():
        if filename == MONOLITH.name:
            continue
        for method in methods:
            assert f"{method}(" not in lifecycle
