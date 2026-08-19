from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_combat_resolver_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrCombatResolver.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    assert "BotWorldPopulationMgr::ResolveProfileCombatAction" in module
    assert "BotWorldPopulationMgr::ResolveProfileCombatAction" not in world


def test_combat_resolver_preserves_profile_and_safety_arbitration() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "BotClassSpecActionProfileStore::BuildCandidates",
        "future_encounter_target_forbidden",
        "HasNearbyProtectedEncounterTarget",
        "SpellHasHostileMultiTargetSemantics",
        "target_immune",
        "target_health_gate",
        "self_health_gate",
        "no_valid_profile_action",
    ):
        assert marker in module


def test_combat_resolver_preserves_density_and_range_fallbacks() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "living_bomb_spread",
        "densityRecovery",
        "bestDensityResourceFallback",
        "bestRangeRecovery",
        "global_cooldown",
        "melee_auto_attack_fallback",
        "effectiveSpellMinRange",
        "effectiveSpellMaxRange",
        "MaintainedProfileAuraBlocksRefresh",
    ):
        assert marker in module
