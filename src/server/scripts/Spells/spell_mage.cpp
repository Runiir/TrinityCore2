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

namespace Spells::Mage
{

// -31571 - Arcane Potency
class spell_mage_arcane_potency : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_MAGE_ARCANE_POTENCY_RANK_1,
                SPELL_MAGE_ARCANE_POTENCY_RANK_2,
                SPELL_MAGE_ARCANE_POTENCY_TRIGGER_RANK_1,
                SPELL_MAGE_ARCANE_POTENCY_TRIGGER_RANK_2
            });
    }

    void HandleProc(AuraEffect const* aurEff, ProcEventInfo& /*eventInfo*/)
    {
        PreventDefaultAction();
        uint32 spellId = 0;

        if (GetSpellInfo()->Id == SPELL_MAGE_ARCANE_POTENCY_RANK_1)
            spellId = SPELL_MAGE_ARCANE_POTENCY_TRIGGER_RANK_1;
        else if (GetSpellInfo()->Id == SPELL_MAGE_ARCANE_POTENCY_RANK_2)
            spellId = SPELL_MAGE_ARCANE_POTENCY_TRIGGER_RANK_2;
        if (!spellId)
            return;

        GetTarget()->CastSpell(GetTarget(), spellId, aurEff);

    }

    void Register() override
    {
        OnEffectProc.Register(&spell_mage_arcane_potency::HandleProc, EFFECT_0, SPELL_AURA_DUMMY);
    }
};

// 42955 Conjure Refreshment
/// Updated 4.3.4
struct ConjureRefreshmentData
{
    uint32 minLevel;
    uint32 maxLevel;
    uint32 spellId;
};

ConjureRefreshmentData const _conjureData[] =
{
    { 33, 43, 92739 },
    { 44, 53, 92799 },
    { 54, 63, 92802 },
    { 64, 73, 92805 },
    { 74, 79, 74625 },
    { 80, 84, 92822 },
    { 85, 85, 92727 }
};
uint8 const MAX_CONJURE_REFRESHMENT_SPELLS = std::extent<decltype(_conjureData)>::value;

// 42955 - Conjure Refreshment
class spell_mage_conjure_refreshment : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        for (uint8 i = 0; i < MAX_CONJURE_REFRESHMENT_SPELLS; ++i)
            if (!ValidateSpellInfo({ _conjureData[i].spellId }))
                return false;
        return true;
    }

    bool Load() override
    {
        return GetCaster()->IsPlayer();
    }

    void HandleDummy(SpellEffIndex /*effIndex*/)
    {
        uint8 level = GetHitUnit()->getLevel();
        for (uint8 i = 0; i < MAX_CONJURE_REFRESHMENT_SPELLS; ++i)
        {
            ConjureRefreshmentData const& spellData = _conjureData[i];
            if (level < spellData.minLevel || level > spellData.maxLevel)
                continue;
            GetHitUnit()->CastSpell(GetHitUnit(), spellData.spellId);
            break;
        }
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_mage_conjure_refreshment::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

// 54646 - Focus Magic
class spell_mage_focus_magic : public AuraScript
{
    void HandleProc(AuraEffect const* aurEff, ProcEventInfo& /*eventInfo*/)
    {
        PreventDefaultAction();
        if (Unit* caster = GetCaster())
            if (caster->IsAlive())
                caster->CastSpell(caster, GetSpellInfo()->Effects[EFFECT_1].TriggerSpell, aurEff);
    }

    void Register() override
    {
        OnEffectProc.Register(&spell_mage_focus_magic::HandleProc, EFFECT_1, SPELL_AURA_PROC_TRIGGER_SPELL);
    }
};

// 543 - Mage Ward
/// Updated 4.3.4
class spell_mage_mage_ward : public AuraScript
{
    void CalculateAmount(AuraEffect const* /*aurEff*/, int32& amount, bool& canBeRecalculated)
    {
        canBeRecalculated = false;
        if (Unit* caster = GetCaster())
        {
            // ${$m1+0.807*$SPA}
            float bonus = 0.807f * caster->SpellBaseDamageBonusDone(SPELL_SCHOOL_MASK_ARCANE);
            amount += int32(bonus);
        }
    }

    void HandleAbsorb(AuraEffect* /*aurEff*/, DamageInfo& /*dmgInfo*/, uint32& absorbAmount)
    {
        if (AuraEffect const* aurEff = GetTarget()->GetAuraEffect(SPELL_AURA_DUMMY, SPELLFAMILY_GENERIC, ICON_MAGE_INCANTERS_ABSORPTION, EFFECT_0))
        {
            int32 bp = CalculatePct(absorbAmount, aurEff->GetAmount());
            GetTarget()->CastSpell(GetTarget(), SPELL_MAGE_INCANTERS_ABSORBTION_TRIGGERED, CastSpellExtraArgs(true).AddSpellBP0(bp));
        }
    }

    void Register() override
    {
        DoEffectCalcAmount.Register(&spell_mage_mage_ward::CalculateAmount, EFFECT_0, SPELL_AURA_SCHOOL_ABSORB);
        AfterEffectAbsorb.Register(&spell_mage_mage_ward::HandleAbsorb, EFFECT_0);
    }
};

// 1463 - Mana Shield
/// Updated 4.3.4
class spell_mage_mana_shield : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_MAGE_INCANTERS_ABSORBTION_TRIGGERED,
                SPELL_MAGE_INCANTERS_ABSORBTION_KNOCKBACK
            });
    }

    void CalculateAmount(AuraEffect const* /*aurEff*/, int32& amount, bool& canBeRecalculated)
    {
        canBeRecalculated = false;
        if (Unit* caster = GetCaster())
        {
            // 87% of the spellpower as bonus
            float bonus = 0.807f * caster->SpellBaseDamageBonusDone(GetSpellInfo()->GetSchoolMask());
            amount += int32(bonus);
        }
    }

    void HandleAbsorb(AuraEffect* /*aurEff*/, DamageInfo& /*dmgInfo*/, uint32& absorbAmount)
    {
        if (AuraEffect const* aurEff = GetTarget()->GetAuraEffect(SPELL_AURA_DUMMY, SPELLFAMILY_GENERIC, ICON_MAGE_INCANTERS_ABSORPTION, EFFECT_0))
        {
            int32 bp = CalculatePct(absorbAmount, aurEff->GetAmount());
            GetTarget()->CastSpell(GetTarget(), SPELL_MAGE_INCANTERS_ABSORBTION_TRIGGERED, CastSpellExtraArgs(true).AddSpellBP0(bp));
        }
    }

    void AfterRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (GetTarget()->GetAuraEffect(SPELL_AURA_DUMMY, SPELLFAMILY_GENERIC, ICON_MAGE_INCANTERS_ABSORPTION, EFFECT_0))
            if (GetTargetApplication()->GetRemoveMode().HasFlag(AuraRemoveFlags::ByEnemySpell))
                GetTarget()->CastSpell(GetTarget(), SPELL_MAGE_INCANTERS_ABSORBTION_KNOCKBACK, true);
    }

    void Register() override
    {
        DoEffectCalcAmount.Register(&spell_mage_mana_shield::CalculateAmount, EFFECT_0, SPELL_AURA_MANA_SHIELD);
        AfterEffectManaShield.Register(&spell_mage_mana_shield::HandleAbsorb, EFFECT_0);
        AfterEffectRemove.Register(&spell_mage_mana_shield::AfterRemove, EFFECT_0, SPELL_AURA_MANA_SHIELD, AURA_EFFECT_HANDLE_REAL);
    }
};

// -29074 - Master of Elements
class spell_mage_master_of_elements : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGE_MASTER_OF_ELEMENTS_ENERGIZE });
    }

    bool CheckProc(ProcEventInfo& eventInfo)
    {
        return eventInfo.GetDamageInfo()->GetSpellInfo() != nullptr;
    }

    void HandleProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
    {
        PreventDefaultAction();

        SpellInfo const* spell = eventInfo.GetSpellInfo();
        int32 mana = int32(spell->CalcPowerCost(GetTarget(), spell->GetSchoolMask()));
        mana = CalculatePct(mana, aurEff->GetAmount());

        if (mana)
            GetTarget()->CastSpell(GetTarget(), SPELL_MAGE_MASTER_OF_ELEMENTS_ENERGIZE, CastSpellExtraArgs(aurEff).AddSpellBP0(mana));
    }

    void Register() override
    {
        DoCheckProc.Register(&spell_mage_master_of_elements::CheckProc);
        OnEffectProc.Register(&spell_mage_master_of_elements::HandleProc, EFFECT_0, SPELL_AURA_DUMMY);
    }
};

// -86181 - Nether Vortex
class spell_mage_nether_vortex : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGE_SLOW });
    }

    bool CheckProc(ProcEventInfo& /*eventInfo*/)
    {
        return !GetTarget()->HasSingleCastAuraOfSpell(SPELL_MAGE_SLOW);
    }

    void HandleEffectProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
    {
        PreventDefaultAction();
        GetTarget()->CastSpell(eventInfo.GetProcTarget(), SPELL_MAGE_SLOW, aurEff);
    }

    void Register() override
    {
        DoCheckProc.Register(&spell_mage_nether_vortex::CheckProc);
        OnEffectProc.Register(&spell_mage_nether_vortex::HandleEffectProc, EFFECT_0, SPELL_AURA_DUMMY);
    }
};

// 118 - Polymorph
class spell_mage_polymorph : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_MAGE_IMPROVED_POLYMORPH_RANK_1,
                SPELL_MAGE_IMPROVED_POLYMORPH_STUN_RANK_1,
                SPELL_MAGE_IMPROVED_POLYMORPH_MARKER
            });
    }

    void HandleGlyphEffect(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (Unit* caster = GetCaster())
        {
            if (AuraEffect const* aurEff = caster->GetDummyAuraEffect(SPELLFAMILY_MAGE, ICON_MAGE_GLYPH_OF_POLYMORPH, EFFECT_0))
            {
                // Improved Polymorph and Glyph of Polymorph both use dummy auras with the same icon.
                if (aurEff->GetSpellInfo()->Id == SPELL_MAGE_IMPROVED_POLYMORPH_RANK_1 || aurEff->GetSpellInfo()->GetRank() > 1)
                    return;

                GetTarget()->RemoveAurasByType(SPELL_AURA_PERIODIC_DAMAGE);
                GetTarget()->RemoveAurasByType(SPELL_AURA_PERIODIC_DAMAGE_PERCENT);
                GetTarget()->RemoveAurasByType(SPELL_AURA_PERIODIC_LEECH);
            }
        }
    }

    bool CheckProc(ProcEventInfo& eventInfo)
    {
        if (!eventInfo.GetDamageInfo() || eventInfo.GetDamageInfo()->GetDamage() == 0)
            return false;

        Unit* caster = GetCaster();
        return caster && !caster->HasAura(SPELL_MAGE_IMPROVED_POLYMORPH_MARKER);
    }

    void HandleEffectProc(AuraEffect const* aurEff, ProcEventInfo& /*eventInfo*/)
    {
        PreventDefaultAction();

        Unit* caster = GetCaster();
        if (!caster)
            return;

        // Improved Polymorph
        if (AuraEffect const* improvedPolymorph = caster->GetAuraEffectOfRankedSpell(SPELL_MAGE_IMPROVED_POLYMORPH_RANK_1, EFFECT_0))
        {
            if (caster->HasAura(SPELL_MAGE_IMPROVED_POLYMORPH_MARKER))
                return;

            GetTarget()->CastSpell(GetTarget(), sSpellMgr->GetSpellWithRank(SPELL_MAGE_IMPROVED_POLYMORPH_STUN_RANK_1, improvedPolymorph->GetSpellInfo()->GetRank()), aurEff);
            caster->CastSpell(nullptr, SPELL_MAGE_IMPROVED_POLYMORPH_MARKER, aurEff);
        }
    }

    void Register() override
    {
        AfterEffectApply.Register(&spell_mage_polymorph::HandleGlyphEffect, EFFECT_0, SPELL_AURA_MOD_CONFUSE, AURA_EFFECT_HANDLE_REAL_OR_REAPPLY_MASK);
        DoCheckProc.Register(&spell_mage_polymorph::CheckProc);
        OnEffectProc.Register(&spell_mage_polymorph::HandleEffectProc, EFFECT_0, SPELL_AURA_MOD_CONFUSE);
    }
};

// 5405  - Replenish Mana (Mana Gem)
/// Updated 4.3.4
class spell_mage_replenish_mana : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGE_IMPROVED_MANA_GEM_TRIGGERED });
    }

    void HandleImprovedManaGem()
    {
        if (AuraEffect* aurEff = GetCaster()->GetAuraEffect(SPELL_AURA_DUMMY, SPELLFAMILY_MAGE, ICON_MAGE_IMPROVED_MANA_GEM, EFFECT_0))
        {
            int32 bp = CalculatePct(GetCaster()->GetMaxPower(POWER_MANA), aurEff->GetAmount());
            GetCaster()->CastSpell(GetCaster(), SPELL_MAGE_IMPROVED_MANA_GEM_TRIGGERED, CastSpellExtraArgs(true).AddSpellBP0(bp).AddSpellMod(SPELLVALUE_BASE_POINT1, bp));
        }
    }

    void Register() override
    {
        AfterCast.Register(&spell_mage_replenish_mana::HandleImprovedManaGem);
    }
};

// 80353 - Time Warp
class spell_mage_time_warp : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_MAGE_TEMPORAL_DISPLACEMENT,
                SPELL_HUNTER_INSANITY,
                SPELL_SHAMAN_EXHAUSTION,
                SPELL_SHAMAN_SATED
            });
    }

    void RemoveInvalidTargets(std::list<WorldObject*>& targets)
    {
        targets.remove_if(Trinity::UnitAuraCheck(true, SPELL_MAGE_TEMPORAL_DISPLACEMENT));
        targets.remove_if(Trinity::UnitAuraCheck(true, SPELL_HUNTER_INSANITY));
        targets.remove_if(Trinity::UnitAuraCheck(true, SPELL_SHAMAN_EXHAUSTION));
        targets.remove_if(Trinity::UnitAuraCheck(true, SPELL_SHAMAN_SATED));
    }

    void ApplyDebuff()
    {
        if (Unit* target = GetHitUnit())
            target->CastSpell(target, SPELL_MAGE_TEMPORAL_DISPLACEMENT, true);
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_mage_time_warp::RemoveInvalidTargets, EFFECT_ALL, TARGET_UNIT_CASTER_AREA_RAID);
        AfterHit.Register(&spell_mage_time_warp::ApplyDebuff);
    }
};

// 79683 Arcane Missiles!
class spell_mage_arcane_missiles_trigger : public AuraScript
{
    bool Load() override
    {
        return GetCaster()->IsPlayer();
    }

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGE_ARCANE_MISSILES_AURASTATE });
    }

    void HandleProc(AuraEffect const* /*aurEff*/, ProcEventInfo& /*eventInfo*/)
    {
        PreventDefaultAction();
    }

    void OnApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        GetCaster()->CastSpell(GetCaster(), SPELL_MAGE_ARCANE_MISSILES_AURASTATE, true);
    }

    void OnRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        GetCaster()->RemoveAura(SPELL_MAGE_ARCANE_MISSILES_AURASTATE);
    }

    void Register() override
    {
        OnEffectProc.Register(&spell_mage_arcane_missiles_trigger::HandleProc, EFFECT_0, SPELL_AURA_DUMMY);
        AfterEffectApply.Register(&spell_mage_arcane_missiles_trigger::OnApply, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
        AfterEffectRemove.Register(&spell_mage_arcane_missiles_trigger::OnRemove, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};

// 79684 Offensive State (DND)
class spell_mage_offensive_state_dnd : public AuraScript
{
    bool Load() override
    {
        return GetCaster()->IsPlayer();
    }

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_MAGE_ARCANE_MISSILES,
                SPELL_MAGE_HOT_STREAK,
                SPELL_MAGE_BRAIN_FREEZE_R1
            });
    }

    bool CheckProc(ProcEventInfo& eventInfo)
    {
        Player* player = GetTarget()->ToPlayer();
        if (!player || !eventInfo.GetSpellInfo())
            return false;

        // Don't proc when caster does not know Arcane Missiles
        if (!player->HasSpell(SPELL_MAGE_ARCANE_MISSILES))
            return false;

        // Hot Streak will no longer allow Arcane Missiles to proc
        if (player->HasAura(SPELL_MAGE_HOT_STREAK))
            return false;

        // Brain Freeze will no longer allow Arcane Missiles to proc
        if (player->GetAuraOfRankedSpell(SPELL_MAGE_BRAIN_FREEZE_R1))
            return false;

        return true;
    }

    void Register() override
    {
        DoCheckProc.Register(&spell_mage_offensive_state_dnd::CheckProc);
    }
};

// 82731 - Flame Orb
class spell_mage_flame_orb : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_MAGE_FLAME_ORB_DUMMY,
                SPELL_MAGE_FROSTFIRE_ORB_DUMMY,
                SPELL_MAGE_FLAME_ORB_SUMMON,
                SPELL_MAGE_FROSTFIRE_ORB_SUMMON
            });
    }

    bool Load() override
    {
        dummySpellId = GetSpellInfo()->Id;
        return true;
    }

    void HandleDummy(SpellEffIndex /*effIndex*/)
    {
        if (Unit* caster = GetCaster())
        {
            switch (dummySpellId)
            {
                case SPELL_MAGE_FLAME_ORB_DUMMY:
                    caster->CastSpell(caster, SPELL_MAGE_FLAME_ORB_SUMMON, true);
                    break;
                case SPELL_MAGE_FROSTFIRE_ORB_DUMMY:
                    caster->CastSpell(caster, SPELL_MAGE_FROSTFIRE_ORB_SUMMON, true);
                    break;
                default:
                    break;
            }
        }
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_mage_flame_orb::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
    }

private:
    uint32 dummySpellId;
};

// 82734 - Flame Orb dummy AOE
class spell_mage_flame_orb_aoe_dummy : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_MAGE_FLAME_ORB_AOE,
                SPELL_MAGE_FROSTFIRE_ORB_AOE,
                SPELL_MAGE_FLAME_ORB_BEAM_DUMMY,
                SPELL_MAGE_FROSTFIRE_ORB_DAMAGE_R1,
                SPELL_MAGE_FROSTFIRE_ORB_DAMAGE_R2,
                SPELL_MAGE_FLAME_ORB_DAMAGE,
                SPELL_MAGE_FLAME_ORB_SELF_SNARE,
                SPELL_MAGE_FROSTFIRE_ORB_RANK_R2,
            });
    }

    bool Load() override
    {
        dummySpellId = GetSpellInfo()->Id;
        return true;
    }

    void FilterTargets(std::list<WorldObject*>& targets)
    {
        Unit* caster = GetCaster();
        TempSummon* summon = caster ? caster->ToTempSummon() : nullptr;
        Unit* summoner = summon ? summon->GetSummoner() : nullptr;
        SpellInfo const* damageInfo = ResolveDamageSpell(summoner);
        targets.remove_if([summoner, damageInfo](WorldObject* target)
        {
            return !IsLegalDamageTarget(summoner, target, damageInfo);
        });

        if (targets.empty())
            return;

        targets.sort(Trinity::ObjectDistanceOrderPred(caster, true));
        targets.resize(1);
    }

    void HandleDummy(SpellEffIndex /*effIndex*/)
    {
        if (Unit* unitCaster = GetCaster())
            if (TempSummon* caster = unitCaster->ToTempSummon())
                if (Unit* summoner = caster->GetSummoner())
                    if (Unit* target = GetHitUnit())
                    {
                        SpellInfo const* damageInfo = ResolveDamageSpell(summoner);
                        if (!IsLegalDamageTarget(summoner, target, damageInfo))
                            return;

                        caster->CastSpell(caster, SPELL_MAGE_FLAME_ORB_SELF_SNARE, true);
                        caster->CastSpell(target, SPELL_MAGE_FLAME_ORB_BEAM_DUMMY, true);
                        summoner->CastSpell(target, damageInfo->Id, true);
                    }
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_mage_flame_orb_aoe_dummy::FilterTargets, EFFECT_0, TARGET_UNIT_DEST_AREA_ENEMY);
        OnEffectHitTarget.Register(&spell_mage_flame_orb_aoe_dummy::HandleDummy, EFFECT_0, SPELL_EFFECT_DUMMY);
    }

private:
    SpellInfo const* ResolveDamageSpell(Unit const* summoner) const
    {
        if (!summoner)
            return nullptr;

        switch (dummySpellId)
        {
            case SPELL_MAGE_FLAME_ORB_AOE:
                return sSpellMgr->GetSpellInfo(SPELL_MAGE_FLAME_ORB_DAMAGE);
            case SPELL_MAGE_FROSTFIRE_ORB_AOE:
                return sSpellMgr->GetSpellInfo(summoner->HasAura(SPELL_MAGE_FROSTFIRE_ORB_RANK_R2)
                    ? SPELL_MAGE_FROSTFIRE_ORB_DAMAGE_R2 : SPELL_MAGE_FROSTFIRE_ORB_DAMAGE_R1);
            default:
                return nullptr;
        }
    }

    static bool IsLegalDamageTarget(Unit const* summoner, WorldObject const* target, SpellInfo const* damageInfo)
    {
        Unit const* unitTarget = target ? target->ToUnit() : nullptr;
        return summoner && unitTarget && damageInfo
            && damageInfo->CheckExplicitTarget(summoner, unitTarget) == SPELL_CAST_OK
            && damageInfo->CheckTarget(summoner, unitTarget, true) == SPELL_CAST_OK;
    }

    uint32 dummySpellId;
};

// 55342 - Mirror Image
class spell_mage_mirror_image : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_MAGE_MIRROR_IMAGE_TRIGGERED_FIRE,
                SPELL_MAGE_MIRROR_IMAGE_TRIGGERED_ARCANE,
                SPELL_MAGE_MIRROR_IMAGE_TRIGGERED_FROST
            });
    }

    void HandleDummyEffect(SpellEffIndex /*effIndex*/)
    {
        Player* player = GetHitPlayer();
        if (!player)
            return;

        uint32 spellId = SPELL_MAGE_MIRROR_IMAGE_TRIGGERED_FROST;
        if (player->GetDummyAuraEffect(SPELLFAMILY_MAGE, ICON_MAGE_GLYPH_OF_MIRROR_IMAGE, EFFECT_0))
        {
            if (player->GetPrimaryTalentTree(player->GetActiveSpec()) == TALENT_TREE_MAGE_FIRE)
                spellId = SPELL_MAGE_MIRROR_IMAGE_TRIGGERED_FIRE;
            else if (player->GetPrimaryTalentTree(player->GetActiveSpec()) == TALENT_TREE_MAGE_ARCANE)
                spellId = SPELL_MAGE_MIRROR_IMAGE_TRIGGERED_ARCANE;
        }

        player->CastSpell(player, spellId, true);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_mage_mirror_image::HandleDummyEffect, EFFECT_1, SPELL_EFFECT_DUMMY);
    }
};

class spell_mage_mirror_image_AurasScript : public AuraScript
{
    void HandleEffectPeriodic(AuraEffect const* aurEff)
    {
        if (aurEff->GetTickNumber() == 1)
            GetTarget()->CastSpell(GetTarget(), GetSpellInfo()->Effects[aurEff->GetEffIndex()].TriggerSpell, true);
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_mage_mirror_image_AurasScript::HandleEffectPeriodic, EFFECT_2, SPELL_AURA_PERIODIC_DUMMY);
    }
};

class SummonerCheck
{
    public:
        SummonerCheck(Unit* _summoner) : summoner(_summoner)  { }

        bool operator()(WorldObject* object)
        {
            if (Unit* unit = object->ToUnit())
                if (TempSummon* summon = unit->ToTempSummon())
                    return (summon->GetSummoner() && summon->GetSummoner() != summoner);

            return false;
        }

    private:
        Unit* summoner;
};

class spell_mage_initialize_images : public SpellScript
{
    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.empty())
            return;

        targets.remove_if(SummonerCheck(GetCaster()));
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_mage_initialize_images::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENTRY);
    }
};

}

void AddSC_mage_spell_scripts()
{
    using namespace Spells::Mage;
    RegisterSpellScript(spell_mage_arcane_missiles_trigger);
    RegisterSpellScript(spell_mage_arcane_potency);
    RegisterMageScript_blast_wave();
    RegisterMageScript_blazing_speed();
    RegisterMageScript_blizzard();
    RegisterMageScript_cold_snap();
    RegisterMageScript_combustion();
    RegisterMageScript_cone_of_cold();
    RegisterSpellScript(spell_mage_conjure_refreshment);
    RegisterMageScript_deep_freeze();
    RegisterMageScript_dragon_breath();
    RegisterMageScript_early_frost();
    RegisterSpellScript(spell_mage_flame_orb);
    RegisterSpellScript(spell_mage_flame_orb_aoe_dummy);
    RegisterSpellScript(spell_mage_focus_magic);
    RegisterMageScript_frostbolt();
    RegisterMageScript_frostfire_bolt();
    RegisterMageScript_hot_streak();
    RegisterMageScript_ice_barrier();
    RegisterMageScript_ice_block();
    RegisterMageScript_icy_veins();
    RegisterMageScript_ignite();
    RegisterMageScript_ignite_periodic();
    RegisterMageScript_impact();
    RegisterMageScript_impact_triggered();
    RegisterMageScript_improved_hot_streak();
    RegisterSpellScript(spell_mage_initialize_images);
    RegisterMageScript_living_bomb();
    RegisterSpellScript(spell_mage_mage_ward);
    RegisterSpellScript(spell_mage_mana_shield);
    RegisterSpellScript(spell_mage_master_of_elements);
    RegisterSpellAndAuraScriptPair(spell_mage_mirror_image, spell_mage_mirror_image_AurasScript);
    RegisterSpellScript(spell_mage_nether_vortex);
    RegisterSpellScript(spell_mage_offensive_state_dnd);
    RegisterMageScript_permafrost();
    RegisterSpellScript(spell_mage_polymorph);
    RegisterMageScript_pyromaniac();
    RegisterSpellScript(spell_mage_replenish_mana);
    RegisterMageScript_ring_of_frost();
    RegisterMageScript_ring_of_frost_freeze();
    RegisterSpellScript(spell_mage_time_warp);
    RegisterMageScript_water_elemental_freeze();
}
