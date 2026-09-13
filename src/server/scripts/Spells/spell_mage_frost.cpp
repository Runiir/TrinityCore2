/*
 * This file is part of the TrinityCore Project. See AUTHORS file for Copyright information
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or (at your
 * option) any later version.
 *
 * This program is distributed in the hope that it will be useful, but WITHOUT
 * ANY WARRANTY; without even the implied warranty of MERCHANTABILITY or
 * FITNESS FOR A PARTICULAR PURPOSE. See the GNU General Public License for
 * more details.
 *
 * You should have received a copy of the GNU General Public License along
 * with this program. If not, see <http://www.gnu.org/licenses/>.
 */

/*
 * Scripts for spells with SPELLFAMILY_MAGE and SPELLFAMILY_GENERIC spells used by mage players.
 * Ordered alphabetically using scriptname.
 * Scriptnames of files in this file should be prefixed with "spell_mage_".
 */

#include "ScriptMgr.h"
#include "spell_mage_shared.h"
#include "SpellInfo.h"
#include "SpellAuras.h"
#include "Unit.h"
#include "Util.h"
#include "GridNotifiers.h"
#include "ObjectAccessor.h"
#include "Pet.h"
#include "Player.h"
#include "SpellAuraEffects.h"
#include "SpellHistory.h"
#include "SpellMgr.h"
#include "SpellScript.h"
#include <array>

namespace Spells::Mage
{
// 42208 - Blizzard
/// Updated 4.3.4
class spell_mage_blizzard : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_MAGE_CHILLED_R1,
                SPELL_MAGE_CHILLED_R2
            });
    }

    void AddChillEffect(SpellEffIndex /*effIndex*/)
    {
        Unit* caster = GetCaster();
        if (Unit* unitTarget = GetHitUnit())
        {
            if (caster->IsScriptOverriden(GetSpellInfo(), 836))
                caster->CastSpell(unitTarget, SPELL_MAGE_CHILLED_R1, true);
            else if (caster->IsScriptOverriden(GetSpellInfo(), 988))
                caster->CastSpell(unitTarget, SPELL_MAGE_CHILLED_R2, true);
        }
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_mage_blizzard::AddChillEffect, EFFECT_0, SPELL_EFFECT_SCHOOL_DAMAGE);
    }
};

// 11958 - Cold Snap
class spell_mage_cold_snap : public SpellScript
{
    bool Load() override
    {
        return GetCaster()->IsPlayer();
    }

    void HandleDummy(SpellEffIndex /*effIndex*/)
    {
        GetCaster()->GetSpellHistory()->ResetCooldowns([](SpellHistory::CooldownStorageType::iterator itr) -> bool
        {
            SpellInfo const* spellInfo = sSpellMgr->AssertSpellInfo(itr->first);
        return spellInfo->SpellFamilyName == SPELLFAMILY_MAGE && (spellInfo->GetSchoolMask() & SPELL_SCHOOL_MASK_FROST) &&
            spellInfo->Id != SPELL_MAGE_COLD_SNAP && spellInfo->GetRecoveryTime() > 0;
        }, true);
    }

    void Register() override
    {
        OnEffectHit.Register(&spell_mage_cold_snap::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

// 120 - Cone of Cold
/// Updated 4.3.4
static std::array<uint32, 2> const ImprovedConeOfColdSpellIds = { SPELL_MAGE_CONE_OF_COLD_TRIGGER_R1, SPELL_MAGE_CONE_OF_COLD_TRIGGER_R2 };

class spell_mage_cone_of_cold : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(ImprovedConeOfColdSpellIds);
    }

    void HandleConeOfColdScript(SpellEffIndex /*effIndex*/)
    {
        if (AuraEffect const* aurEff = GetCaster()->GetDummyAuraEffect(SPELLFAMILY_MAGE, ICON_MAGE_IMPROVED_CONE_OF_COLD, EFFECT_0))
            if (aurEff->IsAffectingSpell(GetSpellInfo()))
                GetHitUnit()->CastSpell(GetHitUnit(), ImprovedConeOfColdSpellIds[uint8(aurEff->GetSpellInfo()->GetRank() - 1)], true);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_mage_cone_of_cold::HandleConeOfColdScript, EFFECT_0, SPELL_EFFECT_APPLY_AURA);
    }
};

// 116 - Frostbolt
/// Updated 4.3.4
class spell_mage_frostbolt : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                 SPELL_MAGE_EARLY_FROST_R1,
                 SPELL_MAGE_EARLY_FROST_R2,
                 SPELL_MAGE_EARLY_FROST_TRIGGERED_R1,
                 SPELL_MAGE_EARLY_FROST_TRIGGERED_R2,
                 SPELL_MAGE_EARLY_FROST_VISUAL
            });
    }

    bool Load() override
    {
        _earlyFrostActive = false;
        _earlyFrostSpellId = 0;

        Unit* caster = GetCaster();
        if (!caster)
            return false;

        // Check Early Frost state
        if (AuraEffect const* aurEff = caster->GetAuraEffect(SPELL_AURA_ADD_FLAT_MODIFIER, SPELLFAMILY_MAGE, ICON_MAGE_EARLY_FROST_SKILL, 0))
        {
            // Check if the cooldown effect is inactive
            if (!caster->GetAuraEffect(SPELL_AURA_ADD_FLAT_MODIFIER, SPELLFAMILY_MAGE, ICON_MAGE_EARLY_FROST, EFFECT_0))
            {
                _earlyFrostActive = true;
                if (aurEff->GetId() == SPELL_MAGE_EARLY_FROST_R1)
                    _earlyFrostSpellId = SPELL_MAGE_EARLY_FROST_TRIGGERED_R1;
                else if (aurEff->GetId() == SPELL_MAGE_EARLY_FROST_R2)
                    _earlyFrostSpellId = SPELL_MAGE_EARLY_FROST_TRIGGERED_R2;
            }
        }

        return true;
    }

    void HandleEarlyFrost()
    {
        if (Unit* caster = GetCaster())
        {
            if (_earlyFrostActive)
            {
                caster->CastSpell(caster, _earlyFrostSpellId, true);
                caster->RemoveAurasDueToSpell(SPELL_MAGE_EARLY_FROST_VISUAL);
            }
        }
    }

    void RecalculateDamage(SpellEffIndex /*effIndex*/)
    {
        if (GetHitUnit() && GetHitUnit()->HasAuraState(AURA_STATE_FROZEN, GetSpellInfo(), GetCaster()))
        {
            if (AuraEffect* aurEff = GetCaster()->GetAuraEffect(SPELL_AURA_DUMMY, SPELLFAMILY_MAGE, ICON_MAGE_SHATTER, EFFECT_1))
            {
                int32 damage = GetHitDamage();
                AddPct(damage, aurEff->GetAmount());
                SetHitDamage(damage);
            }
        }
    }

    void Register() override
    {
        OnSpellStart.Register(&spell_mage_frostbolt::HandleEarlyFrost);
        OnEffectHitTarget.Register(&spell_mage_frostbolt::RecalculateDamage, EFFECT_1, SPELL_EFFECT_SCHOOL_DAMAGE);
    }

private:
    bool _earlyFrostActive;
    uint32 _earlyFrostSpellId;
};

// 45438 - Ice Block
class spell_mage_ice_block : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGE_HYPOTHERMIA, SPELL_MAGE_FROST_NOVA });
    }

    void AfterApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        // Hypothermia debuff
        GetTarget()->CastSpell(nullptr, SPELL_MAGE_HYPOTHERMIA, true);

        // Glyph of Ice Block
        if (GetTarget()->GetDummyAuraEffect(SPELLFAMILY_MAGE, ICON_MAGE_GLYPH_OF_ICE_BLOCK, EFFECT_0))
            GetTarget()->GetSpellHistory()->ResetCooldown(SPELL_MAGE_FROST_NOVA, true);
    }

    void Register() override
    {
        AfterEffectApply.Register(&spell_mage_ice_block::AfterApply, EFFECT_0, SPELL_AURA_MOD_STUN, AURA_EFFECT_HANDLE_REAL_OR_REAPPLY_MASK);
    }
};

// 12472 - Icy Veins
class spell_mage_icy_veins : public AuraScript
{
    void AfterApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (GetTarget()->GetDummyAuraEffect(SPELLFAMILY_MAGE, ICON_MAGE_GLYPH_OF_ICY_VEINS, EFFECT_0))
        {
            GetTarget()->RemoveAurasByType(SPELL_AURA_HASTE_SPELLS, ObjectGuid::Empty, 0, true, false);
            GetTarget()->RemoveAurasByType(SPELL_AURA_MOD_DECREASE_SPEED);
        }
    }

    void Register() override
    {
        AfterEffectApply.Register(&spell_mage_icy_veins::AfterApply, EFFECT_0, SPELL_AURA_MOD_CASTING_SPEED_NOT_STACK, AURA_EFFECT_HANDLE_REAL_OR_REAPPLY_MASK);
    }
};

// 11426 - Ice Barrier
/// Updated 4.3.4
class spell_mage_ice_barrier : public AuraScript
{
    void CalculateAmount(AuraEffect const* /*aurEff*/, int32& amount, bool& canBeRecalculated)
    {
        canBeRecalculated = false;
        if (Unit* caster = GetCaster())
            amount += int32(0.87f * caster->SpellBaseHealingBonusDone(GetSpellInfo()->GetSchoolMask()));
    }

    void AfterRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (!GetTargetApplication()->GetRemoveMode().HasFlag(AuraRemoveFlags::ByEnemySpell))
            return;

        if (GetTarget()->HasAura(SPELL_MAGE_SHATTERED_BARRIER_R1))
            GetTarget()->CastSpell(GetTarget(), SPELL_MAGE_SHATTERED_BARRIER_FREEZE_R1, true);
        else if (GetTarget()->HasAura(SPELL_MAGE_SHATTERED_BARRIER_R2))
            GetTarget()->CastSpell(GetTarget(), SPELL_MAGE_SHATTERED_BARRIER_FREEZE_R2, true);
    }

    void Register() override
    {
        DoEffectCalcAmount.Register(&spell_mage_ice_barrier::CalculateAmount, EFFECT_0, SPELL_AURA_SCHOOL_ABSORB);
        AfterEffectRemove.Register(&spell_mage_ice_barrier::AfterRemove, EFFECT_0, SPELL_AURA_SCHOOL_ABSORB, AURA_EFFECT_HANDLE_REAL);
        AfterEffectRemove.Register(&spell_mage_ice_barrier::AfterRemove, EFFECT_0, SPELL_AURA_SCHOOL_ABSORB, AURA_EFFECT_HANDLE_REAL);
    }
};

// -11175 - Permafrost
class spell_mage_permafrost : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_MAGE_PERMAFROST_HEAL,
                SPELL_MAGE_PERMAFROST_REDUCE_HEAL
            });
    }

    bool DoCheck(ProcEventInfo& eventInfo)
    {
        return GetTarget()->GetGuardianPet() && eventInfo.GetDamageInfo()->GetDamage() && eventInfo.GetProcTarget();
    }

    void HandleEffectProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
    {
        PreventDefaultAction();

        Unit* target = GetTarget();
        int32 heal = int32(CalculatePct(eventInfo.GetDamageInfo()->GetDamage(), aurEff->GetAmount()));
        target->CastSpell(nullptr, SPELL_MAGE_PERMAFROST_HEAL, CastSpellExtraArgs(aurEff).AddSpellBP0(heal));
        target->CastSpell(eventInfo.GetProcTarget(), SPELL_MAGE_PERMAFROST_REDUCE_HEAL, aurEff);
    }

    void Register() override
    {
        DoCheckProc.Register(&spell_mage_permafrost::DoCheck);
        OnEffectProc.Register(&spell_mage_permafrost::HandleEffectProc, EFFECT_0, SPELL_AURA_DUMMY);
    }
};

// 82676 - Ring of Frost
/// Updated 4.3.4
class spell_mage_ring_of_frost : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_MAGE_RING_OF_FROST_SUMMON,
                SPELL_MAGE_RING_OF_FROST_FREEZE,
                SPELL_MAGE_RING_OF_FROST_DUMMY
            });
    }

    bool Load() override
    {
        ringOfFrost = nullptr;
        return true;
    }

    void HandleEffectPeriodic(AuraEffect const* /*aurEff*/)
    {
        if (ringOfFrost)
            if (GetMaxDuration() - (int32)ringOfFrost->GetTimer() >= sSpellMgr->GetSpellInfo(SPELL_MAGE_RING_OF_FROST_DUMMY)->GetDuration())
                GetTarget()->CastSpell(Position{ ringOfFrost->GetPositionX(), ringOfFrost->GetPositionY(), ringOfFrost->GetPositionZ() }, SPELL_MAGE_RING_OF_FROST_FREEZE, true);
    }

    void Apply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        std::list<Creature*> MinionList;
        GetTarget()->GetAllMinionsByEntry(MinionList, GetSpellInfo()->Effects[EFFECT_0].MiscValue);

        // Get the last summoned RoF, save it and despawn older ones
        for (std::list<Creature*>::iterator itr = MinionList.begin(); itr != MinionList.end(); itr++)
        {
            TempSummon* summon = (*itr)->ToTempSummon();

            if (ringOfFrost && summon)
            {
                if (summon->GetTimer() > ringOfFrost->GetTimer())
                {
                    ringOfFrost->DespawnOrUnsummon();
                    ringOfFrost = summon;
                }
                else
                    summon->DespawnOrUnsummon();
            }
            else if (summon)
                ringOfFrost = summon;
        }
    }

    TempSummon* ringOfFrost;

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_mage_ring_of_frost::HandleEffectPeriodic, EFFECT_1, SPELL_AURA_PERIODIC_TRIGGER_SPELL);
        OnEffectApply.Register(&spell_mage_ring_of_frost::Apply, EFFECT_1, SPELL_AURA_PERIODIC_TRIGGER_SPELL, AURA_EFFECT_HANDLE_REAL_OR_REAPPLY_MASK);
    }
};

// 82691 - Ring of Frost (freeze efect)
/// Updated 4.3.4
class spell_mage_ring_of_frost_freeze : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGE_RING_OF_FROST_SUMMON, SPELL_MAGE_RING_OF_FROST_FREEZE });
    }

    void FilterTargets(std::list<WorldObject*>& targets)
    {
        float outRadius = sSpellMgr->GetSpellInfo(SPELL_MAGE_RING_OF_FROST_SUMMON)->Effects[EFFECT_0].CalcRadius();
        float inRadius = 4.7f;

        for (std::list<WorldObject*>::iterator itr = targets.begin(); itr != targets.end(); ++itr)
            if (Unit* unit = (*itr)->ToUnit())
                if (unit->HasAura(SPELL_MAGE_RING_OF_FROST_DUMMY) || unit->HasAura(SPELL_MAGE_RING_OF_FROST_FREEZE) || unit->GetExactDist(GetExplTargetDest()) > outRadius || unit->GetExactDist(GetExplTargetDest()) < inRadius)
                    targets.erase(itr--);
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_mage_ring_of_frost_freeze::FilterTargets, EFFECT_0, TARGET_UNIT_DEST_AREA_ENEMY);
    }
};

class spell_mage_ring_of_frost_freeze_AuraScript : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGE_RING_OF_FROST_DUMMY });
    }

    void OnRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (!GetTargetApplication()->GetRemoveMode().HasFlag(AuraRemoveFlags::Expired))
            if (GetCaster())
                GetCaster()->CastSpell(GetTarget(), SPELL_MAGE_RING_OF_FROST_DUMMY, true);
    }

    void Register() override
    {
        AfterEffectRemove.Register(&spell_mage_ring_of_frost_freeze_AuraScript::OnRemove, EFFECT_0, SPELL_AURA_MOD_STUN, AURA_EFFECT_HANDLE_REAL);
    }
};

// 33395 Water Elemental's Freeze
/// Updated 4.3.4
class spell_mage_water_elemental_freeze : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGE_FINGERS_OF_FROST });
    }

    void CountTargets(std::list<WorldObject*>& targetList)
    {
        _didHit = !targetList.empty();
    }

    void HandleImprovedFreeze()
    {
        if (!_didHit)
            return;

        Unit* owner = GetCaster()->GetOwner();
        if (!owner)
            return;

        if (AuraEffect* aurEff = owner->GetAuraEffect(SPELL_AURA_DUMMY, SPELLFAMILY_MAGE, ICON_MAGE_IMPROVED_FREEZE, EFFECT_0))
        {
            if (roll_chance_i(aurEff->GetAmount()))
                owner->CastSpell(owner, SPELL_MAGE_FINGERS_OF_FROST, CastSpellExtraArgs(true).AddSpellMod(SPELLVALUE_AURA_STACK, 2));
        }
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_mage_water_elemental_freeze::CountTargets, EFFECT_0, TARGET_UNIT_DEST_AREA_ENEMY);
        AfterCast.Register(&spell_mage_water_elemental_freeze::HandleImprovedFreeze);
    }

private:
    bool _didHit;
};

class spell_mage_early_frost : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGE_EARLY_FROST_VISUAL });
    }

    void AfterRemove(AuraEffect const* aurEff, AuraEffectHandleModes /*mode*/)
    {
        if (Unit* caster = GetCaster())
            caster->CastSpell(caster, SPELL_MAGE_EARLY_FROST_VISUAL, aurEff);
    }

    void Register() override
    {
        AfterEffectRemove.Register(&spell_mage_early_frost::AfterRemove, EFFECT_0, SPELL_AURA_ADD_FLAT_MODIFIER, AURA_EFFECT_HANDLE_REAL);
    }
};

class spell_mage_deep_freeze : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGE_DEEP_FREEZE_DAMAGE });
    }

    void HandleDamage(SpellEffIndex /*effIndex*/)
    {
        Unit* caster = GetCaster();
        Unit* target = GetExplTargetUnit();
        if (!target)
            return;

        if (target->GetTypeId() == TYPEID_UNIT)
            if (target->IsImmunedToSpell(GetSpellInfo(), caster))
                caster->CastSpell(target, SPELL_MAGE_DEEP_FREEZE_DAMAGE, true);
    }

    void Register() override
    {
        OnEffectLaunch.Register(&spell_mage_deep_freeze::HandleDamage, EFFECT_0, SPELL_EFFECT_APPLY_AURA);
    }
};

// 44614 - Frostfire Bolt
class spell_mage_frostfire_bolt : public SpellScript
{
    void HandleGlyphSlow(SpellEffIndex effIndex)
    {
        Unit* caster = GetCaster();
        if (!caster)
            return;

        if (Aura* aura = GetHitAura())
        {
            if (AuraEffect* effect = aura->GetEffect(effIndex))
            {
                if (caster->GetDummyAuraEffect(SPELLFAMILY_MAGE, ICON_MAGE_GLYPH_OF_FROSTFIRE, EFFECT_2))
                    effect->SetAmount(0);
                else
                    effect->SetAmount(GetSpellInfo()->Effects[effIndex].CalcValue());
            }
        }
    }

    void HandleGlyphDot(SpellEffIndex effIndex)
    {
        if (Unit* caster = GetCaster())
            if (!caster->GetDummyAuraEffect(SPELLFAMILY_MAGE, ICON_MAGE_GLYPH_OF_FROSTFIRE, EFFECT_2))
                if (Aura* aura = GetHitAura())
                    if (AuraEffect* effect = aura->GetEffect(effIndex))
                        effect->SetAmount(0);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_mage_frostfire_bolt::HandleGlyphSlow, EFFECT_0, SPELL_EFFECT_APPLY_AURA);
        OnEffectHitTarget.Register(&spell_mage_frostfire_bolt::HandleGlyphDot, EFFECT_2, SPELL_EFFECT_APPLY_AURA);
    }
};

void RegisterMageScript_blizzard()
{
    RegisterSpellScript(spell_mage_blizzard);
}

void RegisterMageScript_cold_snap()
{
    RegisterSpellScript(spell_mage_cold_snap);
}

void RegisterMageScript_cone_of_cold()
{
    RegisterSpellScript(spell_mage_cone_of_cold);
}

void RegisterMageScript_deep_freeze()
{
    RegisterSpellScript(spell_mage_deep_freeze);
}

void RegisterMageScript_early_frost()
{
    RegisterSpellScript(spell_mage_early_frost);
}

void RegisterMageScript_frostbolt()
{
    RegisterSpellScript(spell_mage_frostbolt);
}

void RegisterMageScript_frostfire_bolt()
{
    RegisterSpellScript(spell_mage_frostfire_bolt);
}

void RegisterMageScript_ice_barrier()
{
    RegisterSpellScript(spell_mage_ice_barrier);
}

void RegisterMageScript_ice_block()
{
    RegisterSpellScript(spell_mage_ice_block);
}

void RegisterMageScript_icy_veins()
{
    RegisterSpellScript(spell_mage_icy_veins);
}

void RegisterMageScript_permafrost()
{
    RegisterSpellScript(spell_mage_permafrost);
}

void RegisterMageScript_ring_of_frost()
{
    RegisterSpellScript(spell_mage_ring_of_frost);
}

void RegisterMageScript_ring_of_frost_freeze()
{
    RegisterSpellAndAuraScriptPair(spell_mage_ring_of_frost_freeze, spell_mage_ring_of_frost_freeze_AuraScript);
}

void RegisterMageScript_water_elemental_freeze()
{
    RegisterSpellScript(spell_mage_water_elemental_freeze);
}
}
