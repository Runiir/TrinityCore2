from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationLifecycle.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"

MOVED_METHODS = (
    "TryReattachValidationBot",
    "IsNativeCombatResTarget",
    "HasNativeRaidCorpseAuthority",
    "ObserveNativeRaidHostileActivity",
    "ResolveNativeValidationEntrance",
    "IsNativeReleasedGhostWorldport",
    "IsNativeValidationRunbackWorldport",
    "IsValidationCohortMemberInOriginalInstance",
    "MarkValidationCohortViolation",
    "FailValidationAttemptOnce",
)


def test_validation_lifecycle_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationLifecycle.cpp" in CMAKE.read_text()
    assert "#include \"Bots/BotWorldPopulationMgr.h\"" in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text


def test_validation_lifecycle_methods_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text


def test_validation_lifecycle_keeps_native_authority_contract():
    text = MODULE.read_text()
    for marker in (
        "NativeRaidHostileActivityVisitor",
        "BlackwingDescentEntranceTriggerId",
        "HasNativeRaidCorpseAuthority",
        "HandleMoveWorldportAck",
        "ValidationCohortViolation",
        "ValidationAttemptFailureReason",
        "validation_route_terminal",
        "BotRaidAreaAuthority::SetAllOffenseSuppressed",
        "BotMovementArbitration::Clear",
        "ResolveNativeValidationEntrance",
    ):
        assert marker in text
