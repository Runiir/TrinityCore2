from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _magmaw_contracts() -> list[dict[str, object]]:
    config = json.loads(
        (ROOT / "experiments/configs/validation_scenarios_cata_001.json").read_text()
    )
    return [
        step["mechanic_contract"]
        for scenarios in (config["scenarios"], config["diagnostic_scenarios"])
        for scenario in scenarios
        for step in scenario["route"]
        if step.get("node_id") == "bwd.magmaw.encounter"
    ]


def test_magmaw_scoped_area_exception_is_narrow_and_quarantined() -> None:
    contracts = _magmaw_contracts()
    assert len(contracts) == 2
    for contract in contracts:
        assert contract["allow_area_damage"] is False
        assert contract["area_damage_spell_allowlist"] == [421, 48505, 55050]
        assert contract["area_damage_target_allowlist"] == [41570, 42347]
        assert contract["allow_multidot"] is False


def test_scoped_area_authority_reaches_every_native_gate() -> None:
    resolver = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp").read_text()
    executor = (ROOT / "src/server/game/Bots/BotActionExecutor.cpp").read_text()
    mechanics = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrBossMechanics.cpp").read_text()
    planning = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrRaidPlanning.cpp").read_text()
    fallback = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelFallback.cpp").read_text()
    manifest = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteManifest.cpp").read_text()

    assert "bool const scopedAreaAction" in resolver
    assert resolver.count("!magmawMushroomAction && !scopedAreaAction") == 2
    assert "action.AllowScopedEncounterAreaDamage" in resolver
    assert executor.count("!action.AllowScopedEncounterAreaDamage") == 2
    assert "ResolveScopedEncounterAreaSpellId(Player* bot" in planning
    assert "contract.NodeId != \"bwd.magmaw.encounter\"" in planning
    assert 'specTag == "balance_druid"' in planning
    assert "starfallSpellId = 48505" in planning
    assert "ResolveScopedEncounterAreaSpellId(bot, result.Target)" in mechanics
    assert "uint32 const scopedAreaSpellId = preserveScopedArea" in mechanics
    assert "bot->HasAura(48505) && scopedAreaSpellId != 48505" in mechanics
    assert "action.SpellId != scopedAreaSpellId" in mechanics
    assert "ResolveScopedEncounterAreaSpellId(\n                context.Bot, context.Target)" in fallback
    assert "BuildBossMechanicFeatures(\n                    context.Bot, context.Target).AddCount" in fallback
    assert "scopedAreaSpellId,\n                context.Target->GetEntry()" in fallback
    assert '"area_damage_spell_allowlist"' in manifest
    assert '"area_damage_target_allowlist"' in manifest


def test_scoped_magic_keeps_the_melee_chain_protection_split() -> None:
    semantics = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrSpellSemantics.cpp").read_text()
    header = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrSpellSemantics.h").read_text()
    resolver = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatResolver.cpp").read_text()
    executor = (ROOT / "src/server/game/Bots/BotActionExecutor.cpp").read_text()

    assert "SpellHasHostileMeleeChainSemantics" in header
    assert "spellInfo->DmgClass != SPELL_DAMAGE_CLASS_MELEE" in semantics
    assert "effect.ChainTarget > 1" in semantics
    assert "SpellHasHostileMeleeChainSemantics(candidateSpellInfo)" in resolver
    assert "SpellHasHostileMeleeChainSemantics(preview.Effective)" in executor
    assert "SpellHasHostileMeleeChainSemantics(resolved.Effective)" in executor

    # A scoped exception remains available to the two existing magic roots,
    # while the melee-chain exception is still subject to future-target safety.
    nearby_gate = resolver[resolver.index("if (HasNearbyProtectedEncounterTarget(bot, target)") :]
    nearby_gate = nearby_gate[:nearby_gate.index("if (forbidArea")]
    assert "!scopedAreaAction || SpellHasHostileMeleeChainSemantics(candidateSpellInfo)" in nearby_gate
