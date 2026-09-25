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

#include "blackwing_descent.h"
#include "boss_maloriak_shared.h"
#include "ScriptMgr.h"
#include "Containers.h"
#include "ObjectMgr.h"
#include "CommonPredicates.h"
#include "DBCStores.h"
#include "GridNotifiers.h"
#include "InstanceScript.h"
#include "Map.h"
#include "MotionMaster.h"
#include "PassiveAI.h"
#include "Player.h"
#include "ScriptedCreature.h"
#include "SpellAuraEffects.h"
#include "SpellMgr.h"
#include "SpellScript.h"
#include "TemporarySummon.h"

// Maloriak spell and aura scripts, split from boss_maloriak.cpp by concern.
// AddSC_boss_maloriak() calls AddSC_boss_maloriak_spells().
namespace BlackwingDescent::Maloriak
{
class spell_maloriak_throw_bottle : public SpellScript
{
    void HandleDummyEffect(SpellEffIndex effIndex)
    {
        if (Unit* caster = GetCaster())
            caster->CastSpell(GetHitUnit(), GetSpellInfo()->Effects[effIndex].BasePoints, true);
    }

    void Register() override
    {
        OnEffectLaunchTarget.Register(&spell_maloriak_throw_bottle::HandleDummyEffect, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

class spell_maloriak_throw_bottle_triggered : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_THROW_RED_BOTTLE_TRIGGERED,
                SPELL_THROW_BLUE_BOTTLE_TRIGGERED,
                SPELL_THROW_GREEN_BOTTLE_TRIGGERED,
                SPELL_THROW_BLACK_BOTTLE_TRIGGERED
            });
    }

    void HandleDummyEffect(SpellEffIndex /*effIndex*/)
    {
        InstanceScript* instance = GetHitUnit()->GetInstanceScript();
        if (!instance)
            return;

        if (GameObject* cauldron = instance->GetGameObject(DATA_CAULDRON))
        {
            switch (GetSpellInfo()->Id)
            {
                case SPELL_THROW_RED_BOTTLE_TRIGGERED:
                    cauldron->SendCustomAnim(CUSTOM_ANIM_RED_CAULDRON);
                    break;
                case SPELL_THROW_BLUE_BOTTLE_TRIGGERED:
                    cauldron->SendCustomAnim(CUSTOM_ANIM_BLUE_CAULDRON);
                    break;
                case SPELL_THROW_GREEN_BOTTLE_TRIGGERED:
                    cauldron->SendCustomAnim(CUSTOM_ANIM_GREEN_CAULDRON);
                    break;
                case SPELL_THROW_BLACK_BOTTLE_TRIGGERED:
                    cauldron->SendCustomAnim(CUSTOM_ANIM_BLACK_CAULDRON);
                    break;
                default:
                    break;
            }
        }
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_maloriak_throw_bottle_triggered::HandleDummyEffect, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

class spell_maloriak_consuming_flames: public AuraScript
{
    bool CheckProc(ProcEventInfo& eventInfo)
    {
        if (!eventInfo.GetSpellInfo() || eventInfo.GetSpellInfo()->DmgClass != SPELL_DAMAGE_CLASS_MAGIC || eventInfo.GetSpellInfo()->Id == GetId())
            return false;

        return eventInfo.GetDamageInfo();
    }

    void HandleProc(AuraEffect const* /*aurEff*/, ProcEventInfo& eventInfo)
    {
        AuraEffect* effect = GetEffect(EFFECT_0);
        effect->SetAmount(effect->GetAmount() + CalculatePct(eventInfo.GetDamageInfo()->GetDamage(), 50));
    }

    void Register() override
    {
        OnEffectProc.Register(&spell_maloriak_consuming_flames::HandleProc, EFFECT_0, SPELL_AURA_PERIODIC_DAMAGE);
    }
};

class spell_maloriak_flash_freeze_targeting : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_FLASH_FREEZE_SUMMON });
    }

    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.size() <= 1)
            return;

        targets.remove_if(Trinity::Predicates::IsVictimOf(GetCaster()));

        if (targets.empty())
            return;

        targets.remove_if([](WorldObject* obj)
        {
            Unit const* target = obj->ToUnit();
            if (!target)
                return true;

            for (Unit* attacker : target->getAttackers())
                if (attacker->GetEntry() == NPC_ABERRATION && attacker->GetVictim() == target)
                    return true;

            return false;
        });

        if (!targets.empty())
            Trinity::Containers::RandomResize(targets, 1);
    }

    void HandleDummyEffect(SpellEffIndex effIndex)
    {
        if (Unit* caster = GetCaster())
        {
            caster->CastSpell(GetHitUnit(), GetSpellInfo()->Effects[effIndex].BasePoints, true);
            GetHitUnit()->CastSpell(GetHitUnit(), SPELL_FLASH_FREEZE_SUMMON, true);
        }
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_maloriak_flash_freeze_targeting::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENEMY);
        OnEffectHitTarget.Register(&spell_maloriak_flash_freeze_targeting::HandleDummyEffect, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

class spell_maloriak_flash_freeze_dummy : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_FLASH_FREEZE_STUN_NORMAL });
    }

    void FilterTargets(std::list<WorldObject*>& targets)
    {
        Unit* caster = GetCaster();
        if (targets.empty())
        {
            caster->RemoveAurasDueToSpell(sSpellMgr->GetSpellIdForDifficulty(SPELL_FLASH_FREEZE_STUN_NORMAL, caster));
            return;
        }

        targets.remove_if([caster](WorldObject* obj)
        {
            Unit* target = obj->ToUnit();
            if (!target)
                return true;

            return target->isDead() || !target->ToTempSummon() || target->ToTempSummon()->GetSummoner() != caster;
        });

       if (targets.empty())
           caster->RemoveAurasDueToSpell(sSpellMgr->GetSpellIdForDifficulty(SPELL_FLASH_FREEZE_STUN_NORMAL, caster));
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_maloriak_flash_freeze_dummy::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENTRY);
    }
};

class spell_maloriak_release_experiments : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_RELEASE_ABERRATIONS,
                SPELL_RELEASE_ALL_MINIONS
            });
    }

    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.empty())
            return;

        targets.remove_if(Trinity::UnitAuraCheck(false, SPELL_DROWNED_STATE));

        if (!targets.empty() && GetSpellInfo()->Id == SPELL_RELEASE_ABERRATIONS)
            Trinity::Containers::RandomResize(targets, 3);
    }

    void HandleDummyEffect(SpellEffIndex /*effIndex*/)
    {
        if (Creature* target = GetHitCreature())
            if (target->IsAIEnabled())
                target->AI()->DoAction(ACTION_RELEASE_EXPERIMENT);
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_maloriak_release_experiments::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENTRY);
        OnEffectHitTarget.Register(&spell_maloriak_release_experiments::HandleDummyEffect, EFFECT_0, SPELL_EFFECT_DUMMY);
        if (m_scriptSpellId == SPELL_RELEASE_ALL_MINIONS)
        {
            OnObjectAreaTargetSelect.Register(&spell_maloriak_release_experiments::FilterTargets, EFFECT_1, TARGET_UNIT_SRC_AREA_ENTRY);
            OnEffectHitTarget.Register(&spell_maloriak_release_experiments::HandleDummyEffect, EFFECT_1, SPELL_EFFECT_DUMMY);
        }
    }
};

class spell_maloriak_magma_jets_script : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGMA_JETS_SUMMON });
    }

    void HandleScriptEffect(SpellEffIndex /*effIndex*/)
    {
        Unit* caster = GetCaster();
        if (!caster)
            return;

        Unit* target = GetHitUnit();

        if (target == caster->GetVictim())
        {
            caster->SetOrientation(caster->GetAngle(target));
            caster->SetFacingToObject(target); // update orientation immediately
            caster->CastSpell(target, SPELL_MAGMA_JETS_SUMMON);
        }
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_maloriak_magma_jets_script::HandleScriptEffect, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

class spell_maloriak_magma_jets_periodic : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGMA_JETS_SUMMON_FIRE });
    }

    void HandlePeriodic(AuraEffect const* aurEff)
    {
        PreventDefaultAction();
        Unit* target = GetTarget();

        uint8 ticks = aurEff->GetTickNumber();
        float dist = 3.0f * ticks;
        float x = target->GetPositionX() + cos(target->GetOrientation()) * dist;
        float y = target->GetPositionY() + sin(target->GetOrientation()) * dist;
        float z = target->GetMapHeight(x, y, target->GetPositionZ() + 5.0f);
        if (target->IsWithinLOS(x, y, z))
            target->CastSpell(Position{ x, y, z }, SPELL_MAGMA_JETS_SUMMON_FIRE, true);
        else
            Remove();
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_maloriak_magma_jets_periodic::HandlePeriodic, EFFECT_0, SPELL_AURA_PERIODIC_TRIGGER_SPELL);
    }
};

class spell_maloriak_absolute_zero : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_ABSOLUTE_ZERO_EXPLOSION });
    }

    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.empty())
            return;

        Unit* caster = GetCaster();
        caster->RemoveAllAuras();
        caster->CastSpell(caster, SPELL_ABSOLUTE_ZERO_EXPLOSION);
        if (Creature * creature = caster->ToCreature())
            creature->DespawnOrUnsummon(3s);
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_maloriak_absolute_zero::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENEMY);
    }
};

class spell_maloriak_vile_swill: public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_VILE_SWILL_SUMMON });
    }

    void HandlePeriodic(AuraEffect const* /*aurEff*/)
    {
        PreventDefaultAction();
        Unit* target = GetTarget();
        Position const destination = target->GetRandomPoint(target->GetPosition(), 11.0f);
        target->CastSpell(Position{ destination.GetPositionX(), destination.GetPositionY(), destination.GetPositionZ() }, SPELL_VILE_SWILL_SUMMON, true);
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_maloriak_vile_swill::HandlePeriodic, EFFECT_0, SPELL_AURA_PERIODIC_TRIGGER_SPELL);
    }
};

class spell_maloriak_vile_swill_summon: public AuraScript
{
    void AfterApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        int32 summonSpellId = GetSpellInfo()->Effects[EFFECT_0].TriggerSpell;
        Creature* target = GetTarget()->ToCreature();
        if (!target)
            return;

        target->m_Events.AddEventAtOffset([target, summonSpellId]()
        {
            target->CastSpell(target, summonSpellId, true);
            target->SetObjectScale(0.1f);
            target->m_Events.AddEventAtOffset([target]()
            {
                target->RemoveAllAuras();
                target->DespawnOrUnsummon(4s + 300ms);
            }, 1s + 200ms);
        }, 2s);
    }

    void Register() override
    {
        AfterEffectApply.Register(&spell_maloriak_vile_swill_summon::AfterApply, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};

class spell_maloriak_master_adventurer_award : public AuraScript
{
    void HandleApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Player* player = GetTarget()->ToPlayer();
        if (!player)
            return;

        CharTitlesEntry const* titleInfo = sCharTitlesStore.LookupEntry(TITLE_ADVENTURER_AWARD);
        if (!titleInfo)
            return;

        player->SetTitle(titleInfo);
        player->SetUInt32Value(PLAYER_CHOSEN_TITLE, titleInfo->Mask_ID);
    }

    void HandleRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Player* player = GetTarget()->ToPlayer();
        if (!player)
            return;

        CharTitlesEntry const* titleInfo = sCharTitlesStore.LookupEntry(TITLE_ADVENTURER_AWARD);
        if (!titleInfo)
            return;

        player->SetTitle(titleInfo, true);

        if (!player->HasTitle(player->GetInt32Value(PLAYER_CHOSEN_TITLE)))
            player->SetUInt32Value(PLAYER_CHOSEN_TITLE, 0);
    }

    void Register() override
    {
        AfterEffectApply.Register(&spell_maloriak_master_adventurer_award::HandleApply, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
        AfterEffectRemove.Register(&spell_maloriak_master_adventurer_award::HandleRemove, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};
}

void AddSC_boss_maloriak_spells()
{
    using namespace BlackwingDescent::Maloriak;
    RegisterSpellScript(spell_maloriak_throw_bottle);
    RegisterSpellScript(spell_maloriak_throw_bottle_triggered);
    RegisterSpellScript(spell_maloriak_consuming_flames);
    RegisterSpellScript(spell_maloriak_flash_freeze_targeting);
    RegisterSpellScript(spell_maloriak_flash_freeze_dummy);
    RegisterSpellScript(spell_maloriak_release_experiments);
    RegisterSpellScript(spell_maloriak_magma_jets_script);
    RegisterSpellScript(spell_maloriak_magma_jets_periodic);
    RegisterSpellScript(spell_maloriak_absolute_zero);
    RegisterSpellScript(spell_maloriak_vile_swill);
    RegisterSpellScript(spell_maloriak_vile_swill_summon);
    RegisterSpellScript(spell_maloriak_master_adventurer_award);
}
