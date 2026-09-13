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
#include "Spells/SpellCombustion.h"
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

namespace Spells::Mage
{
// 11113 - Blast Wave
class spell_mage_blast_wave : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGE_FLAMESTRIKE });
    }

    void HandleImprovedFlamestrike(SpellEffIndex /*effIndex*/)
    {
        ++_hitTargetsCount;
        if (_hitTargetsCount != 2)
            return;

        if (AuraEffect const* aurEff = GetCaster()->GetAuraEffect(SPELL_AURA_DUMMY, SPELLFAMILY_MAGE, ICON_MAGE_IMPROVED_FLAMESTRIKE, EFFECT_0))
            if (!roll_chance_i(aurEff->GetAmount()))
                return;

        if (WorldLocation const* targetDest = GetExplTargetDest())
            GetCaster()->CastSpell(targetDest->GetPosition(), SPELL_MAGE_FLAMESTRIKE, true);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_mage_blast_wave::HandleImprovedFlamestrike, EFFECT_1, SPELL_EFFECT_APPLY_AURA);
    }
private:
    uint8 _hitTargetsCount = 0;
};

// -31641 - Blazing Speed
class spell_mage_blazing_speed : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGE_BLAZING_SPEED });
    }

    void OnProc(AuraEffect const* aurEff, ProcEventInfo& /*eventInfo*/)
    {
        PreventDefaultAction();
        GetTarget()->CastSpell(GetTarget(), SPELL_MAGE_BLAZING_SPEED, aurEff);
    }

    void Register() override
    {
        OnEffectProc.Register(&spell_mage_blazing_speed::OnProc, EFFECT_0, SPELL_AURA_PROC_TRIGGER_SPELL);
    }
};

// -31661 - Dragon's Breath
class spell_mage_dragon_breath : public AuraScript
{
    bool CheckProc(ProcEventInfo& eventInfo)
    {
        // Dont proc with Living Bomb explosion
        SpellInfo const* spellInfo = eventInfo.GetSpellInfo();
        if (spellInfo && spellInfo->SpellIconID == ICON_MAGE_LIVING_BOMB && spellInfo->SpellFamilyName == SPELLFAMILY_MAGE)
            return false;
        return true;
    }

    void Register() override
    {
        DoCheckProc.Register(&spell_mage_dragon_breath::CheckProc);
    }
};

// 44457 - Living Bomb
class spell_mage_living_bomb : public AuraScript
{
    bool Validate(SpellInfo const* spellInfo) override
    {
        return ValidateSpellInfo({ uint32(spellInfo->Effects[EFFECT_1].CalcValue()) });
    }

    void AfterRemove(AuraEffect const* aurEff, AuraEffectHandleModes /*mode*/)
    {
        if (!GetTargetApplication()->GetRemoveMode().HasFlag(AuraRemoveFlags::Expired))
            return;

        if (Unit* caster = GetCaster())
            caster->CastSpell(GetTarget(), uint32(aurEff->GetAmount()), aurEff);
    }

    void Register() override
    {
        AfterEffectRemove.Register(&spell_mage_living_bomb::AfterRemove, EFFECT_1, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};

// -11119 - Ignite
class spell_mage_ignite : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_MAGE_IGNITE,
                SPELL_MAGE_FLAME_ORB_DAMAGE,
                SPELL_MAGE_FROSTFIRE_ORB_DAMAGE_R1,
                SPELL_MAGE_FROSTFIRE_ORB_DAMAGE_R2
            });
    }

    bool CheckProc(ProcEventInfo& eventInfo)
    {
        if (!eventInfo.GetSpellInfo() || !eventInfo.GetProcTarget())
            return false;

        switch (eventInfo.GetSpellInfo()->Id)
        {
            case SPELL_MAGE_FLAME_ORB_DAMAGE:
            case SPELL_MAGE_FROSTFIRE_ORB_DAMAGE_R1:
            case SPELL_MAGE_FROSTFIRE_ORB_DAMAGE_R2:
                return false;
        }

        return true;
    }

    void HandleProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
    {
        PreventDefaultAction();
        Unit* target = GetTarget();

        DamageInfo* damage = eventInfo.GetDamageInfo();

        int32 bp = CalculatePct(damage->GetDamage(), aurEff->GetAmount()) * 0.5f;
        if (bp > 0)
            target->CastSpell(eventInfo.GetProcTarget(), SPELL_MAGE_IGNITE, CastSpellExtraArgs(aurEff).AddSpellBP0(bp));
    }

    void Register() override
    {
        DoCheckProc.Register(&spell_mage_ignite::CheckProc);
        OnEffectProc.Register(&spell_mage_ignite::HandleProc, EFFECT_0, SPELL_AURA_DUMMY);
    }
};

// 12654 - Ignite
class spell_mage_ignite_periodic : public AuraScript
{
    void CalculateRefreshedDot(AuraEffect const* /*aurEff*/, int32& amount, bool& canBeRecalculated)
    {
        canBeRecalculated = false;
        _critDamageValues.emplace_back(std::make_pair(2, amount));

        amount = 0;
        for (auto const& damageValuePair : _critDamageValues)
            amount += damageValuePair.second;
    }

    void HandlePeriodic(AuraEffect const* aurEff)
    {
        int32 newDotValue = 0;
        bool changed = false;
        for (std::vector<std::pair<uint8, int32>>::iterator itr = _critDamageValues.begin(); itr != _critDamageValues.end();)
        {
            --itr->first;
            newDotValue += itr->second;
            if (itr->first == 0)
            {
                itr = _critDamageValues.erase(itr);
                changed = true;
            }
            else
                ++itr;
        }

        if (changed)
            const_cast<AuraEffect*>(aurEff)->SetAmount(newDotValue);
    }

    void Register() override
    {
        DoEffectCalcAmount.Register(&spell_mage_ignite_periodic::CalculateRefreshedDot, EFFECT_0, SPELL_AURA_PERIODIC_DAMAGE);
        OnEffectPeriodic.Register(&spell_mage_ignite_periodic::HandlePeriodic, EFFECT_0, SPELL_AURA_PERIODIC_DAMAGE);
    }
private:
    std::vector<std::pair<uint8, int32>> _critDamageValues;
};

// 44445 - Hot Streak
class spell_mage_hot_streak : public AuraScript
{
    bool Load() override
    {
        return GetCaster()->IsPlayer();
    }

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_MAGE_HOT_STREAK_TRIGGERED,
                SPELL_MAGE_T12_4P_BONUS,
                SPELL_MAGE_IMPROVED_HOT_STREAK
            });
    }

    bool CheckProc(ProcEventInfo& /*eventInfo*/)
    {
        if (AuraEffect const* aurEff = GetTarget()->GetDummyAuraEffect(SPELLFAMILY_MAGE, ICON_MAGE_HOT_STREAK, EFFECT_0))
            if (aurEff->GetSpellInfo()->Id == SPELL_MAGE_IMPROVED_HOT_STREAK || aurEff->GetSpellInfo()->GetRank() > 1)
                return false;

        int32 procChance = GetSpellInfo()->Effects[EFFECT_0].CalcValue();
        // T12 4P bonus
        if (AuraEffect const* aurEff = GetTarget()->GetAuraEffect(SPELL_MAGE_T12_4P_BONUS, EFFECT_1))
            procChance += aurEff->GetAmount();

        return roll_chance_i(procChance);
    }

    void HandleProc(AuraEffect const* aurEff, ProcEventInfo& /*eventInfo*/)
    {
        PreventDefaultAction();
        GetCaster()->CastSpell(GetCaster(), SPELL_MAGE_HOT_STREAK_TRIGGERED, aurEff);
    }

    void Register() override
    {
        DoCheckProc.Register(&spell_mage_hot_streak::CheckProc);
        OnEffectProc.Register(&spell_mage_hot_streak::HandleProc, EFFECT_0, SPELL_AURA_DUMMY);
    }
};

// -44446 - Improved Hot Streak
class spell_mage_improved_hot_streak : public AuraScript
{
    bool Load() override
    {
        _critCount = 0;
        return GetCaster()->IsPlayer();
    }

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGE_HOT_STREAK_TRIGGERED });
    }

    bool CheckProc(ProcEventInfo& eventInfo)
    {
        if (eventInfo.GetDamageInfo()->GetDamageType() != SPELL_DIRECT_DAMAGE)
            return false;

        if (eventInfo.GetDamageInfo()->GetHitMask() & PROC_HIT_CRITICAL)
            _critCount++;
        else
            _critCount = 0;

        if (_critCount == 2)
        {
            _critCount = 0;
            return roll_chance_i(GetSpellInfo()->Effects[EFFECT_0].CalcValue());
        }

        return false;
    }

    void HandleProc(AuraEffect const* aurEff, ProcEventInfo& /*eventInfo*/)
    {
        PreventDefaultAction();
        GetCaster()->CastSpell(GetCaster(), SPELL_MAGE_HOT_STREAK_TRIGGERED, aurEff);
    }

    void Register() override
    {
        DoCheckProc.Register(&spell_mage_improved_hot_streak::CheckProc);
        OnEffectProc.Register(&spell_mage_improved_hot_streak::HandleProc, EFFECT_0, SPELL_AURA_DUMMY);
    }

private:
    uint8 _critCount = 0;
};

// -34293 - Pyromaniac
class spell_mage_pyromaniac : public AuraScript
{
    bool Load() override
    {
        _buffActive = false;
        return true;
    }

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGE_PYROMANIAC_TRIGGERED });
    }

    void CalcPeriodic(AuraEffect const* /*aurEff*/, bool& isPeriodic, int32& amplitude)
    {
        isPeriodic = true;
        amplitude = 1 * IN_MILLISECONDS;
    }

    void HandleProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
    {
        PreventDefaultAction();

        _dotTargetGuids.insert(eventInfo.GetProcTarget()->GetGUID());

        // Pyomaniac is active already so there is no need to iterate through potential targets
        if (_buffActive)
            return;

        Unit* target = GetTarget();
        CleanDotTargets(target);

        if (_dotTargetGuids.size() >= 3)
        {
            target->CastSpell(target, SPELL_MAGE_PYROMANIAC_TRIGGERED, CastSpellExtraArgs(aurEff).AddSpellBP0(aurEff->GetAmount()));
            _buffActive = true;
        }
    }

    void HandlePeriodic(AuraEffect const* /*aurEff*/)
    {
        // Buff is not active right now so there is no need to check targets
        if (!_buffActive)
            return;

        Unit* target = GetTarget();
        CleanDotTargets(target);

        if (_dotTargetGuids.size() < 3)
        {
            target->RemoveAurasDueToSpell(SPELL_MAGE_PYROMANIAC_TRIGGERED);
            _buffActive = false;
        }
    }

    void Register() override
    {
        DoEffectCalcPeriodic.Register(&spell_mage_pyromaniac::CalcPeriodic, EFFECT_0, SPELL_AURA_DUMMY);
        OnEffectProc.Register(&spell_mage_pyromaniac::HandleProc, EFFECT_0, SPELL_AURA_DUMMY);
        OnEffectPeriodic.Register(&spell_mage_pyromaniac::HandlePeriodic, EFFECT_0, SPELL_AURA_DUMMY);
    }
private:
    GuidSet _dotTargetGuids;
    bool _buffActive;

    void CleanDotTargets(Unit* caster)
    {
        GuidSet guids = _dotTargetGuids;
        for (ObjectGuid guid : guids)
            if (!IsValidDotTarget(caster, guid))
                _dotTargetGuids.erase(guid);
    }

    bool IsValidDotTarget(Unit* caster, ObjectGuid guid) const
    {
        Unit* target = ObjectAccessor::GetUnit(*caster, guid);
        if (!target)
            return false;

        Unit::AuraEffectList const& dotAuraEffects = target->GetAuraEffectsByType(SPELL_AURA_PERIODIC_DAMAGE);
        if (dotAuraEffects.empty())
            return false;

        for (AuraEffect const* effect : dotAuraEffects)
            if (effect->GetCasterGUID() == caster->GetGUID() && effect->GetSpellInfo()->SpellFamilyFlags[2] & 0x00000008)
                return true;

        return true;
    }
};

// -11103 - Impact
class spell_mage_impact : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGE_FIRE_BLAST });
    }

    void HandleProc(AuraEffect const* /*aurEff*/, ProcEventInfo& /*eventInfo*/)
    {
        GetTarget()->GetSpellHistory()->ResetCooldown(SPELL_MAGE_FIRE_BLAST, true);
    }

    void Register() override
    {
        OnEffectProc.Register(&spell_mage_impact::HandleProc, EFFECT_0, SPELL_AURA_PROC_TRIGGER_SPELL);
    }
};

// 12355 - Impact
class spell_mage_impact_triggered : public SpellScript
{
    void RegisterFireDots(SpellEffIndex /*effIndex*/)
    {
        Unit* caster = GetCaster();
        Unit* target = GetExplTargetUnit();
        Unit* launchTarget = GetHitUnit();
        if (!target || !caster || target != launchTarget)
            return;

        Unit::AuraEffectList const& dotAuraEffects = target->GetAuraEffectsByType(SPELL_AURA_PERIODIC_DAMAGE);
        if (dotAuraEffects.empty())
            return;

        for (AuraEffect const* effect : dotAuraEffects)
            if (effect->GetCasterGUID() == caster->GetGUID() && effect->GetSpellInfo()->SpellFamilyFlags[2] & 0x00000008)
                _fireDotEffects.push_back(effect->GetBase());
    }

    void SpeadFireDots(SpellEffIndex /*effIndex*/)
    {
        Unit* caster = GetCaster();
        if (!caster)
            return;

        if (GetExplTargetUnit() == GetHitUnit())
            return;

        for (Aura* aura : _fireDotEffects)
        {
            if (Aura* addAura = caster->AddAura(aura->GetSpellInfo()->Id, GetHitUnit()))
            {
                for (uint8 i = 0; i < MAX_SPELL_EFFECTS; i++)
                    if (AuraEffect* originalEffect = aura->GetEffect(i))
                        if (AuraEffect* effect = addAura->GetEffect(i))
                            effect->SetAmount(originalEffect->GetAmount());

                addAura->SetDuration(aura->GetDuration());
            }
        }
    }

    void Register() override
    {
        OnEffectLaunchTarget.Register(&spell_mage_impact_triggered::RegisterFireDots, EFFECT_1, SPELL_EFFECT_SCRIPT_EFFECT);
        OnEffectHitTarget.Register(&spell_mage_impact_triggered::SpeadFireDots, EFFECT_1, SPELL_EFFECT_SCRIPT_EFFECT);
    }
private:
    std::vector<Aura*> _fireDotEffects;
};

// 11129 - Combustion
class spell_mage_combustion : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGE_COMBUSTION_DAMAGE });
    }

    void HandleScriptEffect(SpellEffIndex effIndex)
    {
        Unit* caster = GetCaster();
        if (!caster)
            return;

        Unit* target = GetHitUnit();

        double sourceRate = 0;
        float scalingFactor = static_cast<float>(GetEffectValue());

        for (AuraEffect const* aurEff : target->GetAuraEffectsByType(SPELL_AURA_PERIODIC_DAMAGE))
        {
            if (aurEff->GetCasterGUID() != caster->GetGUID()
                || !(aurEff->GetSpellInfo()->GetSchoolMask() & SPELL_SCHOOL_MASK_FIRE)
                || aurEff->GetSpellInfo()->SpellFamilyName != SPELLFAMILY_MAGE)
                continue;

            // Only combine auras specified in the script effect's class mask
            if (!aurEff->GetSpellInfo()->IsAffected(SPELLFAMILY_MAGE, GetSpellInfo()->Effects[effIndex].SpellClassMask))
                continue;

            sourceRate += SpellCombustion::SourceRate(aurEff->GetAmount(),
                aurEff->GetSpellInfo()->Effects[aurEff->GetEffIndex()].AuraPeriod);
        }

        int32 const basePoints = SpellCombustion::ScaledBasePoints(sourceRate, scalingFactor);
        if (basePoints > 0)
            caster->CastSpell(target, SPELL_MAGE_COMBUSTION_DAMAGE, CastSpellExtraArgs(true).AddSpellBP0(basePoints));
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_mage_combustion::HandleScriptEffect, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

void RegisterMageScript_blast_wave()
{
    RegisterSpellScript(spell_mage_blast_wave);
}

void RegisterMageScript_blazing_speed()
{
    RegisterSpellScript(spell_mage_blazing_speed);
}

void RegisterMageScript_combustion()
{
    RegisterSpellScript(spell_mage_combustion);
}

void RegisterMageScript_dragon_breath()
{
    RegisterSpellScript(spell_mage_dragon_breath);
}

void RegisterMageScript_hot_streak()
{
    RegisterSpellScript(spell_mage_hot_streak);
}

void RegisterMageScript_ignite()
{
    RegisterSpellScript(spell_mage_ignite);
}

void RegisterMageScript_ignite_periodic()
{
    RegisterSpellScript(spell_mage_ignite_periodic);
}

void RegisterMageScript_impact()
{
    RegisterSpellScript(spell_mage_impact);
}

void RegisterMageScript_impact_triggered()
{
    RegisterSpellScript(spell_mage_impact_triggered);
}

void RegisterMageScript_improved_hot_streak()
{
    RegisterSpellScript(spell_mage_improved_hot_streak);
}

void RegisterMageScript_living_bomb()
{
    RegisterSpellScript(spell_mage_living_bomb);
}

void RegisterMageScript_pyromaniac()
{
    RegisterSpellScript(spell_mage_pyromaniac);
}
}
