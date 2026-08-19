from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatNotifications.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "NotifyCombatAttackAttempt",
    "NotifyCombatDamage",
    "NotifyCombatHeal",
)


def test_combat_notifications_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrCombatNotifications.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text
        assert method in HEADER.read_text()


def test_combat_notifications_methods_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text


def test_combat_notifications_keep_calibration_and_party_log_contract():
    text = MODULE.read_text()
    for marker in (
        "CalibrationFixtureTargetAttackEventCount",
        "CalibrationFixtureTargetGuid",
        "HealResponseLatenciesMs",
        "HealingDone",
        "HealingReceived",
        "CombatOwnerPlayer",
        "FindCombatLogCohortPlayer",
        "CalibrationSingleTargetDurationMs",
        "CalibrationExecuteHealthWindowIndex",
        "UpdateCalibrationTargetHealthSchedule",
        "CalibrationExcludedBoundaryDamageEventCount",
        "PrimaryTargetDamage",
        "OffTargetDamageEvents",
        "DamageEventSampleCount",
        "AddCombatLogEvent",
    ):
        assert marker in text
