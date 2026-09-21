from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationDamage.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"

MOVED_METHODS = (
    "DrainCalibrationPostWindowEffects",
    "UpdateCalibrationControlledDamage",
)


def test_calibration_damage_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrCalibrationDamage.cpp" in CMAKE.read_text()
    assert "#include \"Bots/BotWorldPopulationMgr.h\"" in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text
        assert f"void BotWorldPopulationMgr::{method}" not in SOURCE.read_text()


def test_calibration_damage_module_keeps_control_contract():
    text = MODULE.read_text()
    for marker in (
        "CalibrationLastPostWindowDrainMs",
        "CalibrationCurrentDamagePhase",
        "tank_sustained_damage",
        "unequal_health_triage",
        "controlledDispelAura",
        "ControlledDispelAuraForHealer",
        "BotClassSpecActionProfileStore::Build",
        "CalibrationInterruptTargetGuid",
        "RemoveAllDynObjects",
        "IsTrainingDummy",
    ):
        assert marker in text


def test_completed_window_drain_stops_the_player_toggle_before_combat_teardown():
    text = MODULE.read_text()
    drain = text[text.index("void BotWorldPopulationMgr::DrainCalibrationPostWindowEffects"):
        text.index("void BotWorldPopulationMgr::UpdateCalibrationControlledDamage")]

    assert "bot->AttackStop();" in drain
    assert drain.index("bot->AttackStop();") < drain.index(
        "bot->CombatStopWithPets(true);"
    )
