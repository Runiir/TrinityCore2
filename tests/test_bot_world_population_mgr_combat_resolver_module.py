from __future__ import annotations

from pathlib import Path

from tests.combat_resolver_source import combat_resolver_source


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp"
OUTCOME = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolverOutcome.cpp"
ADMISSION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolverAdmission.cpp"
ADMISSION_CONTEXT = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolverAdmission.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
SUPPORT = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatSupport.cpp"
SPELL = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatSpell.cpp"
BOSS = ROOT / "src/server/game/Bots/BotWorldPopulationMgrBossMechanics.cpp"
SWAP = ROOT / "src/server/game/Bots/BotWorldPopulationMgrTankSwap.cpp"


def test_combat_resolver_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    outcome = OUTCOME.read_text(encoding="utf-8")
    admission = ADMISSION.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")
    # Round 4 split the resolver by concern with headroom below the hook.
    assert len(module.splitlines()) < 700
    assert len(admission.splitlines()) < 700
    assert len(outcome.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrCombatResolver.cpp" in cmake
    assert "Bots/BotWorldPopulationMgrCombatResolverAdmission.cpp" in cmake
    assert "Bots/BotWorldPopulationMgrCombatResolverOutcome.cpp" in cmake
    # The per-candidate admission gates and ranking are their own module; the
    # resolver builds the candidates, delegates, then picks among the bests.
    assert "void BotWorldPopulationMgr::AdmitProfileCombatCandidates(" in admission
    assert "BotWorldPopulationMgr::AdmitProfileCombatCandidates(" not in module
    assert "    AdmitProfileCombatCandidates(admission);" in module
    assert module.index("BuildCandidates(bot, target, profile, potionHealthOwner);") \
        < module.index("    AdmitProfileCombatCandidates(admission);") \
        < module.index("    if (bestInterrupt)")
    assert "struct BotWorldPopulationMgr::ProfileCombatAdmission" in ADMISSION_CONTEXT.read_text(encoding="utf-8")
    assert "for (BotActionCandidate& candidate : candidates)" in admission
    assert "for (BotActionCandidate& candidate : candidates)" not in module
    assert "BotWorldPopulationMgr::ResolveProfileCombatAction" in module
    assert "BotWorldPopulationMgr::ResolveProfileCombatAction" not in world
    # The no-valid-action outcome (rejection aggregates and the wait/melee
    # fallback) is its own module; the resolver delegates to it.
    for name in ("RecordNoProfileActionRejections", "ResolveNoProfileAction"):
        assert f"BotWorldPopulationMgr::{name}(" in outcome
        assert f"BotWorldPopulationMgr::{name}(" not in module
    assert "RecordNoProfileActionRejections(bot, candidates);" in module
    assert "return ResolveNoProfileAction(bot, target, profile, candidates," in module


def test_combat_resolver_preserves_profile_and_safety_arbitration() -> None:
    module = combat_resolver_source()
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
    module = combat_resolver_source() + OUTCOME.read_text(encoding="utf-8")
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
    module = combat_resolver_source()
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

    assert "TryBossTankSwap(state, bot, role, result, raidAssignment, raidAdapter, recordTankSwap)" in boss
    swap_owner = SWAP.read_text(encoding="utf-8")
    swap_start = swap_owner.index("    if (tankSwapTriggered && std::string(role) == \"tank\"")
    swap_end = swap_owner.index("\nvoid BotWorldPopulationMgr::SubmitAdaptiveTankSwapCandidate", swap_start)
    swap = swap_owner[swap_start:swap_end]
    assert "TryCastCombatSpell(bot, result.Target, candidate.SpellId, forceFacing)" in swap
    assert "HasOtherLiveCohortTankVictim" not in swap
