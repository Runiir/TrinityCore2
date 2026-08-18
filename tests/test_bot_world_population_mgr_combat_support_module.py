from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatSupport.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "GetDungeonRole",
    "SelectInterruptSpell",
    "SelectHealSpell",
    "TryCastFriendlySpell",
    "TryNativeSelfResurrection",
)


def test_combat_support_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrCombatSupport.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in text
        assert method in HEADER.read_text()


def test_combat_support_methods_are_not_left_in_monolith():
    text = SOURCE.read_text()
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" not in text


def test_combat_support_keeps_native_healing_and_resurrection_gates():
    text = MODULE.read_text()
    for marker in (
        "PLAYER_ROLE_TANK",
        "character_bot_pool",
        "movement_requires_instant_heal",
        "target_immune",
        "injured_player_count_too_low",
        "raid_offense_suppressed",
        "future_encounter_target_forbidden",
        "future_encounter_splash_forbidden",
        "BeginPendingHealCast",
        "cast_submission_failed",
        "SPELL_EFFECT_SELF_RESURRECT",
        "native_self_resurrection_submitted",
        "NativeResurrectionRetryAfterMs",
    ):
        assert marker in text
