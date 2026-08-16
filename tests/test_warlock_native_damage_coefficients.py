from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_missing_cataclysm_warlock_coefficients_use_native_spell_info_corrections() -> None:
    source = (ROOT / "src/server/game/Spells/SpellMgr.cpp").read_text()

    assert "ApplySpellFix({ 6353 }" in source
    assert "BonusMultiplier = 0.726f" in source
    assert "ApplySpellFix({ 48181 }" in source
    assert "BonusMultiplier = 0.5577f" in source
    assert "ApplySpellFix({ 54049 }" in source
    assert "BonusMultiplier = 1.228f" in source


def test_shadow_bite_scales_from_owned_warlock_dots_without_damage_injection() -> None:
    source = (ROOT / "src/server/scripts/Spells/spell_warlock.cpp").read_text()

    assert "class spell_warl_shadow_bite : public SpellScript" in source
    assert "GetAuraEffectsByType(SPELL_AURA_PERIODIC_DAMAGE)" in source
    assert "effect->GetCasterGUID() == owner->GetGUID()" in source
    assert "spellInfo->SpellFamilyName == SPELLFAMILY_WARLOCK" in source
    assert "AddPct(pctMod, int32(30 * activeDots.size()))" in source
    assert "SetHitDamage" not in source[source.index("class spell_warl_shadow_bite") : source.index("// 755 - Health Funnel")]


def test_shadow_bite_script_binding_is_idempotent() -> None:
    migration = (
        ROOT / "sql/custom/world/2026_08_16_02_warlock_native_damage_coefficients.sql"
    ).read_text()

    assert "VALUES (54049, 'spell_warl_shadow_bite')" in migration
    assert "ON DUPLICATE KEY UPDATE" in migration


def test_affliction_modifier_diagnostics_observe_native_auras_without_applying_them() -> None:
    source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()
    header = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text()

    assert "AfflictionModifierObservationTicks" in header
    assert 'Cohort().CalibrationTargetSpec == "affliction_warlock"' in source
    assert "bot->HasAura(87339)" in source
    assert "bot->HasAura(77215)" in source
    assert "fixtureTarget->HasAura(48181, bot->GetGUID())" in source
    assert "fixtureTarget->GetAura(32389," in source
    assert "hauntModifier->IsAffectingSpell(corruption)" in source
    assert "shadowEmbraceModifier->IsAffectingSpell(corruption)" in source
    assert "fixtureTarget->SpellDamageBonusTaken(bot, corruption," in source
    assert "minimum_corruption_taken_multiplier_ppm" in source
    assert '\\"affliction_modifier_observation\\"' in source
    assert "CastSpell(32389" not in source
    assert "AddAura(32389" not in source


def test_pet_resource_contract_waits_for_native_regeneration_without_refilling() -> None:
    source = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text()

    assert "fixtureContract->PetResourceRequired" in source
    assert 'std::string_view(power.UnitKind) != "pet"' in source
    assert "pet->GetPower(powerType)" in source
    assert "populationReady = petResourceReady" in source
    assert 'std::string_view(unitKind) != "pet"' in source
    assert "unit->SetPower(power, int32(expectedNative))" in source
