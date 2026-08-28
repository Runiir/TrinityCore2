from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatExecution.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "TryEnsureCombatTotems",
    "ExecuteProfileCombatAction",
)


def test_combat_execution_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrCombatExecution.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    assert module.count("BotWorldPopulationMgr::ExecuteProfileCombatAction") == 2
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_combat_execution_preserves_setup_and_hard_mask_gates() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "TryEnsurePersistentCombatSetup",
        "TryEnsureCombatTotems",
        "future_encounter_target_forbidden",
        "world.hard_mask.future_encounter",
        "SubmitMeleeAutoAttackIntent",
        "profile_melee_autoattack",
        "BotActionExecutor",
    ):
        assert marker in module


def test_combat_execution_preserves_position_reconciliation_and_backoff() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "native_position_reconciled",
        "native_out_of_range",
        "native_no_line_of_sight",
        "ProfileCastSuppressedSpellId",
        "candidate_backoff",
        "cast_succeeded",
    ):
        assert marker in module


def test_failed_totem_and_offensive_cooldown_attempts_release_profile_fallback() -> None:
    module = MODULE.read_text(encoding="utf-8")
    totems = module.split(
        "bool BotWorldPopulationMgr::TryEnsureCombatTotems", 1
    )[1].split(
        "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction", 1
    )[0]
    successful_totem_path = totems.split("if (bot->CastSpell", 1)[1].split(
        "RecordCombatAttempt(state, bot, bot, \"totems\", &action, BotActionResult::CastFailed", 1
    )[0]
    failed_totem_path = totems.split(
        "RecordCombatAttempt(state, bot, bot, \"totems\", &action, BotActionResult::CastFailed", 1
    )[1]
    assert "return true;" in successful_totem_path
    assert "return false;" in failed_totem_path

    execution = module.split(
        "BotActionResult BotWorldPopulationMgr::ExecuteProfileCombatAction(WorldBotState*", 1
    )[1]
    fallback = execution.split("bool const failedOffensiveCooldown", 1)[1].split(
        "std::string const castLifecycleKey", 1
    )[0]
    assert 'action.DebugName == "offensive_cooldown"' in fallback
    assert "BotActionResult::NoAction" in fallback
    assert "BotActionResult::CastFailed" in fallback
    assert "ProfileCastSuppressedSpellId = action.SpellId" in fallback
    assert "target->GetGUID() : action.TargetGuid" in fallback
    assert "ProfileCastSuppressedUntilMs = nowMs + 3000" in fallback
