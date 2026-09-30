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
#include <algorithm>
#include <list>

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
        // CheckProc was never registered, so each Consuming Flames tick fed
        // 50% of itself back into the aura: r03 10N ticks grew 4500, 6322,
        // 8598, 12467 ... 58733 with no other damage taken (each step exactly
        // +50% of the previous landed tick). Only other magic damage feeds it.
        DoCheckProc.Register(&spell_maloriak_consuming_flames::CheckProc);
        OnEffectProc.Register(&spell_maloriak_consuming_flames::HandleProc, EFFECT_0, SPELL_AURA_PERIODIC_DAMAGE);
    }
};

// Remedy 77912 (10N; its 25N/10H/25H variants 92965-92967 are not bound: the
// evidence is 10N only). WCL 10N
// VL3fW9wNm2PRJDYt fight 13, two full casts: the heal grows by the base value
// every tick, 22,500, 45,000, 67,500 ... 225,000 and 250,000 on the tenth
// (25,000 x tick, less a -10% healing debuff while it was up), about 1.25-1.32M
// per cast. The client row is a flat 25,000 per second, so the aura script
// scales each tick by its tick number, as the Wowhead 4.4.2 page says
// ("increasing each tick").
class spell_maloriak_remedy : public AuraScript
{
    void RampHeal(AuraEffect* aurEff)
    {
        aurEff->SetAmount(aurEff->GetBaseAmount() * int32(std::max<uint32>(aurEff->GetTickNumber(), 1)));
    }

    void Register() override
    {
        OnEffectUpdatePeriodic.Register(&spell_maloriak_remedy::RampHeal, EFFECT_0, SPELL_AURA_PERIODIC_HEAL);
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

        // 10N WCL (ledger flash_freeze_targets_10N): all 16 Flash Freezes in
        // ten kills froze ranged damage dealers or healers, never a tank or a
        // melee player, as both guides say ("one ranged player"). Players
        // beyond Biting Chill's 10-yd melee reach are preferred.
        Unit* caster = GetCaster();
        if (caster && caster->GetMap()->GetDifficulty() == RAID_DIFFICULTY_10MAN_NORMAL)
        {
            std::list<WorldObject*> ranged = targets;
            ranged.remove_if([caster](WorldObject* obj)
            {
                Unit const* target = obj->ToUnit();
                return !target || caster->IsWithinCombatRange(target, FLASH_FREEZE_MIN_RANGE_10N);
            });
            if (!ranged.empty())
                targets.swap(ranged);
        }

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

namespace BlackwingDescent::Maloriak
{
// WCL 10N VL3fW9wNm2PRJDYt fight 13 (Slime Imbued 02:05.122): the Growth
// Catalyst auras of every Aberration, their own included, were removed at the
// Debilitating Slime and the auras they had spread 26 ms later; a surviving
// Aberration's own aura came back 5.2 s later (02:10.332). Both Icy Veins
// guides say the slime removes Growth Catalyst. The client row of 77615 has
// no effect that does it, so the script removes the auras and each survivor
// casts Growth Catalyst again after the observed delay.
void StripGrowthCatalystForSlime(Creature* source)
{
    uint32 const catalyst = sSpellMgr->GetSpellIdForDifficulty(SPELL_GROWTH_CATALYST, source);
    for (uint32 entry : { uint32(NPC_ABERRATION), uint32(NPC_PRIME_SUBJECT) })
    {
        std::list<Creature*> experiments;
        source->GetCreatureListWithEntryInGrid(experiments, entry, 200.0f);
        for (Creature* experiment : experiments)
        {
            if (!experiment->IsAlive() || !experiment->HasAura(catalyst))
                continue;
            experiment->RemoveAurasDueToSpell(catalyst);
            experiment->m_Events.AddEventAtOffset([experiment]()
            {
                if (experiment->IsAlive() && experiment->IsInCombat())
                    experiment->CastSpell(experiment, SPELL_GROWTH_CATALYST, true);
            }, Milliseconds(GROWTH_CATALYST_SLIME_RECAST_MS));
        }
    }
}
}

void AddSC_boss_maloriak_spells()
{
    using namespace BlackwingDescent::Maloriak;
    RegisterSpellScript(spell_maloriak_throw_bottle);
    RegisterSpellScript(spell_maloriak_throw_bottle_triggered);
    RegisterSpellScript(spell_maloriak_consuming_flames);
    RegisterSpellScript(spell_maloriak_remedy);
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
