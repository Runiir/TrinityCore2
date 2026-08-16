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
