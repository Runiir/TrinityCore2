from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
SUPPORT = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatSupport.cpp"
SPELL = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatSpell.cpp"
BOSS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrBossMechanics.cpp"


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


def test_generic_taunt_ownership_gate_is_shared_with_select_combat_spell() -> None:
    module = MODULE.read_text(encoding="utf-8")
    header = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text(
        encoding="utf-8"
    )
    support = SUPPORT.read_text(encoding="utf-8")
    spell = SPELL.read_text(encoding="utf-8")
    boss = BOSS.read_text(encoding="utf-8")
    helper = "HasOtherLiveCohortTankVictim(Player const* bot, Unit const* target) const"
    assert helper in header
    assert support.count("BotWorldPopulationMgr::HasOtherLiveCohortTankVictim(") == 1
    assert module.count("HasOtherLiveCohortTankVictim(bot, target)") == 1
    assert spell.count("HasOtherLiveCohortTankVictim(bot, target)") == 1
    assert "validationCohortVictim" not in spell

    # The generic no-victim/self guard remains ahead of the shared ownership
    # predicate in both candidate paths.
    resolver_order = module.index("threat_already_established")
    assert resolver_order < module.index("HasOtherLiveCohortTankVictim(bot, target)")
    spell_order = spell.index("threat_already_established")
    assert spell_order < spell.index("HasOtherLiveCohortTankVictim(bot, target)")

    swap_start = boss.index("    if (tankSwapTriggered && std::string(role) == \"tank\"")
    swap_end = boss.index("    if (result.Features.MoveOut", swap_start)
    swap = boss[swap_start:swap_end]
    assert "TryCastCombatSpell(bot, result.Target, candidate.SpellId)" in swap
    assert "HasOtherLiveCohortTankVictim" not in swap
