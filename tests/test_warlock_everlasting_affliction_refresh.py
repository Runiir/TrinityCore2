from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SQL = (
    ROOT
    / "sql/custom/world/2026_08_23_03_affliction_everlasting_affliction_native_binding.sql"
)
SPELL = ROOT / "src/server/scripts/Spells/spell_warlock.cpp"
SPELL_MGR = ROOT / "src/server/game/Spells/SpellMgr.cpp"
PLAYER = ROOT / "src/server/game/Entities/Player/Player.cpp"
UNIT = ROOT / "src/server/game/Entities/Unit/Unit.cpp"


def test_everlasting_affliction_trigger_spell_binding_is_idempotent() -> None:
    migration = SQL.read_text()

    assert "DELETE FROM `spell_ranks`" in migration
    assert "WHERE `first_spell_id` = 47201;" in migration
    assert "(47201, 47201, 1)" in migration
    assert "(47201, 47202, 2)" in migration
    assert "(47201, 47203, 3)" in migration

    assert "DELETE FROM `spell_proc` WHERE `SpellId` = -47201" in migration
    assert "`SpellFamilyName`, `SpellFamilyMask0`" in migration
    assert "`SpellFamilyMask1`, `SpellFamilyMask2`" in migration
    assert "`SpellPhaseMask`" in migration
    assert "(-47201, 0, 5, 16392, 262144, 0, 0, 0, 2" in migration

    assert "DELETE FROM `spell_script_names`" in migration
    assert "`spell_id` = 47422" in migration
    assert "'spell_warl_everlasting_affliction'" in migration
    assert "VALUES (47422, 'spell_warl_everlasting_affliction')" in migration
    assert "ON DUPLICATE KEY UPDATE" in migration
    assert "bot_rotation_action" not in migration
    assert "CastSpell" not in migration
    assert "AddAura" not in migration


def test_native_refresh_trigger_uses_owned_corruption_and_refreshes_duration() -> None:
    source = SPELL.read_text()
    start = source.index("// 47422 - Everlasting Affliction")
    end = source.index("// 77799 - Fel Flame", start)
    handler = source[start:end]

    assert "class spell_warl_everlasting_affliction : public SpellScript" in handler
    assert (
        "OnEffectHitTarget.Register(&spell_warl_everlasting_affliction::HandleScriptEffect,"
        in handler
    )
    assert "EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT" in handler
    assert (
        "GetAuraEffect(SPELL_AURA_PERIODIC_DAMAGE, SPELLFAMILY_WARLOCK,"
        " 0x2, 0, 0, caster->GetGUID())"
        in handler
    )
    assert "aurEff->RecalculateAmount(caster);" in handler
    assert "aurEff->CalculatePeriodic(caster, false, false);" in handler
    assert "aurEff->GetBase()->RefreshDuration();" in handler
    assert "CastSpell" not in handler

    assert "RegisterSpellScript(spell_warl_everlasting_affliction);" in source


def test_everlasting_affliction_ranks_route_to_corruption_class_mask() -> None:
    source = SPELL_MGR.read_text()
    start = source.index("// Everlasting Affliction")
    end = source.index("// Summon Ravenous Worgen", start)
    fix = source[start:end]

    assert "ApplySpellFix({ 47201, 47202, 47203 }" in fix
    assert "spellInfo->Effects[EFFECT_1].SpellClassMask[0] |= 2;" in fix


def test_periodic_crit_spellmods_are_not_filtered_by_direct_crit_gate() -> None:
    player = PLAYER.read_text()
    start = player.index("bool Player::IsAffectedBySpellmod")
    end = player.index("template <class T>\nvoid Player::GetSpellModValues", start)
    helper = player[start:end]

    # Unit::SpellCritChanceDone owns the direct-spell legality check. Keeping a
    # second check here prevents periodic auras, which explicitly pass
    # isPeriodic=true, from receiving CritChance spellmods.
    assert "case SpellModOp::CritChance" not in helper

    unit = UNIT.read_text()
    start = unit.index("float Unit::SpellCritChanceDone")
    end = unit.index("float Unit::SpellCritChanceTaken", start)
    crit_chance = unit[start:end]
    assert "if (!isPeriodic && !spellInfo->HasAttribute(SPELL_ATTR0_CU_CAN_CRIT))" in crit_chance
    assert "modOwner->ApplySpellMod(spellInfo, SpellModOp::CritChance, crit_chance);" in crit_chance
