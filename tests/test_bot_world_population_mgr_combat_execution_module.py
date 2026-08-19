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
