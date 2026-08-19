from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatRes.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"

MOVED_METHODS = (
    "CurrentCombatResOwnerUsable",
    "PublishNativeBattleResDecision",
    "ReconcileNativeBattleResDecisions",
    "BuildCombatResNativeActionCandidate",
)


def test_combat_res_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrCombatRes.cpp" in CMAKE.read_text()
    assert "#include \"Bots/BotWorldPopulationMgr.h\"" in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text


def test_combat_res_methods_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text


def test_combat_res_module_keeps_native_reservation_contract():
    text = MODULE.read_text()
    for marker in (
        "declined_reservation_missing",
        "reserved_approach",
        "reserved_cast_submitted",
        "declined_no_combat_res_spell",
        "CombatResReservationLifetimeMs",
        "IsNativeCombatResSpell",
        "HasPowerForSpell",
        "PathGenerator",
        "ValidationCohort",
        "NativeResurrectionPendingUntilMs",
    ):
        assert marker in text
