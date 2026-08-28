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


def test_melee_range_uses_live_target_chase_without_target_z_floor_gate() -> None:
    module = MODULE.read_text(encoding="utf-8")
    start = module.index(
        'if (directive == "melee" || (minRange <= 0.0f && maxRange <= 5.0f))'
    )
    end = module.index("    // A small center-to-center offset", start)
    melee = module[start:end]

    # A Magmaw-like actor can expose a model origin far below the navigable
    # floor. The live target must reach ExecuteMovementIntent as a dynamic
    # chase instead of being rejected by the target-elevation floor probe.
    assert "reference->GetPositionX()" in melee
    assert "reference->GetPositionY()" in melee
    assert "bot->GetPositionZ()" in melee
    assert "reference);" in melee
    assert "GetHeight" not in melee
    assert "targetZ" not in melee
