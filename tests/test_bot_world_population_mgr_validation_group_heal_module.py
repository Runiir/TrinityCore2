from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationGroupHeal.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_group_heal_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrValidationGroupHeal.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    assert "BotWorldPopulationMgr::TryValidationRouteGroupHeal" in text
    assert "TryValidationRouteGroupHeal" in HEADER.read_text()


def test_validation_group_heal_lambda_is_not_left_in_monolith():
    text = SOURCE.read_text()
    assert "TryValidationRouteGroupHeal(state, bot, healer, combatTarget" in text
    assert "auto tryRouteGroupHeal =" in text
    assert "BotActionProfileSpell const* bestHeal" not in text


def test_validation_group_heal_keeps_native_triage_contract():
    text = MODULE.read_text()
    for marker in (
        "chakra_serenity_primed",
        "fade_threat_drop",
        "guardian_spirit_self_emergency",
        "healer_hold_for_pending_dungeon_pull",
        "healer_preposition_for_feral_swarm_pickup",
        "validation_route_group_heal",
        "RecordCombatAttempt",
        "MaintainedProfileAuraBlocksRefresh",
    ):
        assert marker in text
