from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatMovement.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "BeginMeleeAutoAttackDecision",
    "SubmitMeleeAutoAttackIntent",
    "ResolveAndReconcileMeleeAutoAttack",
    "MoveBotToProfileRange",
)


def test_combat_movement_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrCombatMovement.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_combat_movement_keeps_single_native_attack_authority() -> None:
    module = MODULE.read_text(encoding="utf-8")
    assert "AttackStop()" in module
    assert "bot->Attack(target, true)" in module
    assert "native_toggle_rejected" in module
    assert "BotRaidAreaAuthority::IsAllOffenseSuppressed" in module
    assert "BotRaidAreaAuthority::IsProtectedEncounterTarget" in module


def test_combat_movement_preserves_profile_range_and_path_guards() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for directive in ("melee_behind", "melee"):
        assert f'"{directive}"' in module
    assert "PathGenerator approachPath" in module
    assert "MoveBotToPoint" in module
    assert "preciseMaximumRangeApproach" in module
