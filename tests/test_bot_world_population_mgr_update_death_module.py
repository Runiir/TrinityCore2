from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateDeath.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_update_death_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrUpdateDeath.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::HandleBotDeath" in text
    assert "HandleBotDeath" in HEADER.read_text()


def test_update_death_handler_is_not_left_in_monolith():
    text = SOURCE.read_text()
    assert "HandleBotDeath(state, bot, diff);" in text
    assert "state.DeathEpisodeRecorded = true;" not in text


def test_update_death_keeps_native_recovery_contract():
    text = MODULE.read_text()
    for marker in (
        "NativeFullWipeOnly",
        "native_full_wipe_only",
        "CurrentCombatResOwnerUsable",
        "PublishNativeBattleResDecision",
        "RecoverDeadBot",
        "death_recovery_started",
        "tactical_retreat_no_combat_res",
    ):
        assert marker in text


def test_partial_trash_deaths_do_not_require_a_manufactured_full_wipe():
    text = MODULE.read_text()
    full_wipe_gate = text.index(
        "Cohort().Config.ValidationRouteBossRecovery == ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly"
    )
    reset_gate = text.index("native_recovery_wait_hostile_activity")

    assert '&& Cohort().Config.ValidationRouteKind == "boss"' in text[
        full_wipe_gate:full_wipe_gate + 240
    ]
    assert "RecoverDeadBot(state, bot)" in text[reset_gate:]
