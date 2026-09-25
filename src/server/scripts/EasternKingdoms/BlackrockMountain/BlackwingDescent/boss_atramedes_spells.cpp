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

// Atramedes spell and aura scripts. The creature AIs live in
// boss_atramedes.cpp; both share boss_atramedes_shared.h.

#include "ScriptMgr.h"
#include "CommonPredicates.h"
#include "Containers.h"
#include "Creature.h"
#include "CreatureAI.h"
#include "InstanceScript.h"
#include "Map.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Spell.h"
#include "SpellAuraEffects.h"
#include "SpellMgr.h"
#include "SpellScript.h"
#include "blackwing_descent.h"
#include "boss_atramedes_shared.h"

namespace BlackwingDescent::Atramedes
{
class spell_atramedes_modulation : public SpellScript
{
    void ChangeDamage(SpellEffIndex /*effIndex*/)
    {
        Unit* target = GetHitUnit();
        if (!target)
            return;

        int32 damage = GetHitDamage();
        AddPct(damage, target->GetPower(POWER_ALTERNATE_POWER));
        SetHitDamage(damage);
    }

    void Register() override
    {
        OnEffectLaunchTarget.Register(&spell_atramedes_modulation::ChangeDamage, EFFECT_0, SPELL_EFFECT_SCHOOL_DAMAGE);
    }
};

class spell_atramedes_roaring_flame_breath_reverse_cast : public SpellScript
{
    void HandleScriptEffect(SpellEffIndex effIndex)
    {
        if (Unit* caster = GetCaster())
            GetHitUnit()->CastSpell(caster, GetSpellInfo()->Effects[effIndex].BasePoints);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_atramedes_roaring_flame_breath_reverse_cast::HandleScriptEffect, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

class spell_atramedes_roaring_flame_breath : public AuraScript
{
    void HandleTick(AuraEffect const* aurEff)
    {
        PreventDefaultAction();
        GetTarget()->CastSpell(GetTarget(), GetSpellInfo()->Effects[EFFECT_0].TriggerSpell, aurEff);
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_atramedes_roaring_flame_breath::HandleTick, EFFECT_0, SPELL_AURA_PERIODIC_TRIGGER_SPELL);
    }
};

class spell_atramedes_roaring_flame_breath_fire_periodic : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_ROARING_FLAME_SUMMON });
    }

    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.empty())
            GetCaster()->CastSpell(GetCaster(), SPELL_ROARING_FLAME_SUMMON, true);
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_atramedes_roaring_flame_breath_fire_periodic::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENTRY);
    }
};

class spell_atramedes_resonating_clash_ground : public SpellScript
{
    void HandleScriptEffect(SpellEffIndex effIndex)
    {
        Unit* caster = GetCaster();
        Creature* target = GetHitCreature();
        if (!target || !caster || !target->IsAIEnabled())
            return;

        target->AI()->SetGUID(caster->GetGUID(), DATA_LAST_USED_ANCIENT_DWARVEN_SHIELD);
        target->CastSpell(target, GetSpellInfo()->Effects[effIndex].BasePoints, true);
        target->PlayDirectSound(SOUND_ID_ATRAMEDES_VERTIGO);

        // Atramedes has a interrupt mechanic immunity so we interrupt him manually
        target->InterruptNonMeleeSpells(true);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_atramedes_resonating_clash_ground::HandleScriptEffect, EFFECT_1, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

class spell_atramedes_resonating_clash_air : public SpellScript
{
    void HandleScriptEffect(SpellEffIndex /*effIndex*/)
    {
        Unit* caster = GetCaster();
        Creature* target = GetHitCreature();
        if (!target || !caster || !target->IsAIEnabled())
            return;

        if (CreatureAI* ai = target->AI())
        {
            if (Unit* shield = GetSpell()->GetOriginalCaster())
                ai->SetGUID(shield->GetGUID(), DATA_LAST_USED_ANCIENT_DWARVEN_SHIELD);

            ai->SetGUID(caster->GetGUID(), DATA_LAST_SHIELD_USER);

            target->PlayDirectSound(SOUND_ID_ATRAMEDES_VERTIGO);
        }
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_atramedes_resonating_clash_air::HandleScriptEffect, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

class spell_atramedes_resonating_clash: public SpellScript
{
    void HandleScriptEffect(SpellEffIndex effIndex)
    {
        GetHitUnit()->RemoveAurasDueToSpell(GetSpellInfo()->Effects[effIndex].BasePoints);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_atramedes_resonating_clash::HandleScriptEffect, EFFECT_2, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

class spell_atramedes_sound_bar : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_NOISY });
    }

    void HandleNoisyAura(AuraEffect const* aurEff)
    {
        Unit* target = GetTarget();
        InstanceScript* instance = target->GetInstanceScript();
        if (!instance)
            return;

        if (target->GetPower(POWER_ALTERNATE_POWER) == target->GetMaxPower(POWER_ALTERNATE_POWER))
        {
            if (!target->HasAura(SPELL_NOISY))
                if (Creature* atramedes = instance->GetCreature(DATA_ATRAMEDES))
                    atramedes->AI()->SetGUID(target->GetGUID(), DATA_ADD_NOISY_PLAYER);

            target->CastSpell(target, SPELL_NOISY, aurEff);
        }
        else if (target->GetPower(POWER_ALTERNATE_POWER) >= 50)
            if (!instance->instance->GetWorldStateValue(WORLD_STATE_ID_SILENCE_IS_GOLDEN))
                instance->DoUpdateWorldState(WORLD_STATE_ID_SILENCE_IS_GOLDEN, 1);
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_atramedes_sound_bar::HandleNoisyAura, EFFECT_1, SPELL_AURA_PERIODIC_DUMMY);
    }
};

class spell_atramedes_noisy : public AuraScript
{
    void AfterRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (InstanceScript* instance = GetTarget()->GetInstanceScript())
            if (Creature* atramedes = instance->GetCreature(DATA_ATRAMEDES))
                atramedes->AI()->SetGUID(GetTarget()->GetGUID(), DATA_REMOVE_NOISY_PLAYER);
    }

    void Register() override
    {
        AfterEffectRemove.Register(&spell_atramedes_noisy::AfterRemove, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};

class spell_atramedes_vertigo : public AuraScript
{
    void AfterRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();
        target->CastSpell(target, GetSpellInfo()->Effects[EFFECT_1].BasePoints, true);

        if (Creature* atramedes = target->ToCreature())
        {
            if (atramedes->IsAIEnabled())
            {
                // A gong during the scripted intro flight must resume the
                // landing. The intro phase is Atramedes' AI state, not an
                // instance data value: asking the instance for it always
                // returned 0, so an intro Vertigo left him hovering passive.
                if (atramedes->AI()->GetData(DATA_IS_IN_INTRO_FLIGHT))
                    atramedes->GetMotionMaster()->MovePoint(POINT_PREPARE_LAND_INTRO, IntroFlightPosition2, false);

                if (InstanceScript* instance = atramedes->GetInstanceScript())
                    if (Creature* nefarius = instance->GetCreature(DATA_LORD_VICTOR_NEFARIUS_ATRAMEDES))
                        if (nefarius->IsAIEnabled())
                            nefarius->AI()->DoAction(ACTION_DESTROY_SHIELD);
            }
        }
    }

    void Register() override
    {
        AfterEffectRemove.Register(&spell_atramedes_vertigo::AfterRemove, EFFECT_1, SPELL_AURA_MOD_STUN, AURA_EFFECT_HANDLE_REAL);
    }
};

class spell_atramedes_sonic_flames : public SpellScript
{
    void SetTarget(WorldObject*& target)
    {
        if (InstanceScript* instance = GetCaster()->GetInstanceScript())
            if (Creature* atramedes = instance->GetCreature(DATA_ATRAMEDES))
                if (Creature* shield = ObjectAccessor::GetCreature(*GetCaster(), atramedes->AI()->GetGUID(DATA_LAST_USED_ANCIENT_DWARVEN_SHIELD)))
                    target = shield;
    }

    void Register() override
    {
        OnObjectTargetSelect.Register(&spell_atramedes_sonic_flames::SetTarget, EFFECT_0, TARGET_UNIT_NEARBY_ENTRY);
    }
};

class spell_atramedes_sonic_flames_AuraScript : public AuraScript
{
    void HandlePeriodic(AuraEffect const* aurEff)
    {
        Unit* caster = GetCaster();
        if (!caster)
            return;

        PreventDefaultAction();
        caster->CastSpell(GetTarget(), GetSpellInfo()->Effects[EFFECT_0].TriggerSpell, aurEff);
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_atramedes_sonic_flames_AuraScript::HandlePeriodic, EFFECT_0, SPELL_AURA_PERIODIC_TRIGGER_SPELL);
    }
};

class spell_atramedes_devastation_trigger : public AuraScript
{
    void HandlePeriodic(AuraEffect const* /*aurEff*/)
    {
        if (Creature* target = GetTarget()->ToCreature())
            if (target->IsAIEnabled())
                if (!target->AI()->GetData(DATA_HAS_NOISY_PLAYER))
                    PreventDefaultAction();
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_atramedes_devastation_trigger::HandlePeriodic, EFFECT_0, SPELL_AURA_PERIODIC_TRIGGER_SPELL);
    }
};

class spell_atramedes_sonic_breath : public SpellScript
{
    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.empty())
            return;

        targets.remove_if(Trinity::Predicates::IsVictimOf(GetCaster()));

        if (targets.size() > 1)
            Trinity::Containers::RandomResize(targets, 1);
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_atramedes_sonic_breath::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENEMY);
    }
};

class spell_atramedes_destroy_shield : public SpellScript
{
    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.empty())
            return;

        targets.remove_if([](WorldObject const* obj)
        {
            return obj->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
        });

        if (targets.size() > 1)
            Trinity::Containers::RandomResize(targets, 1);
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_atramedes_destroy_shield::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENTRY);
    }
};

class spell_atramedes_pestered : public AuraScript
{
    void AfterApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (Unit* caster = GetCaster())
            if (Creature* creature = caster->ToCreature())
                if (creature->IsAIEnabled())
                    creature->AI()->DoAction(ACTION_PLAYER_ENTERED);
    }

    void AfterRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (Unit* caster = GetCaster())
            if (Creature* creature = caster->ToCreature())
                if (creature->IsAIEnabled())
                    creature->AI()->DoAction(ACTION_PLAYER_LEFT);
    }

    void Register() override
    {
        AfterEffectApply.Register(&spell_atramedes_pestered::AfterApply, EFFECT_0, SPELL_AURA_CONTROL_VEHICLE, AURA_EFFECT_HANDLE_REAL);
        AfterEffectRemove.Register(&spell_atramedes_pestered::AfterRemove, EFFECT_0, SPELL_AURA_CONTROL_VEHICLE, AURA_EFFECT_HANDLE_REAL);
    }
};

class spell_atramedes_apply_vehicle_periodic : public AuraScript
{
    void AfterApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        GetTarget()->RemoveFlag(UNIT_NPC_FLAGS, UNIT_NPC_FLAG_PLAYER_VEHICLE);
    }

    void Register() override
    {
        AfterEffectApply.Register(&spell_atramedes_apply_vehicle_periodic::AfterApply, EFFECT_0, SPELL_AURA_SET_VEHICLE_ID, AURA_EFFECT_HANDLE_REAL);
    }
};
}

void AddSC_boss_atramedes_spells()
{
    using namespace BlackwingDescent;
    using namespace BlackwingDescent::Atramedes;
    RegisterSpellScript(spell_atramedes_modulation);
    RegisterSpellScript(spell_atramedes_roaring_flame_breath_reverse_cast);
    RegisterSpellScript(spell_atramedes_roaring_flame_breath);
    RegisterSpellScript(spell_atramedes_roaring_flame_breath_fire_periodic);
    RegisterSpellScript(spell_atramedes_resonating_clash_ground);
    RegisterSpellScript(spell_atramedes_resonating_clash_air);
    RegisterSpellScript(spell_atramedes_resonating_clash);
    RegisterSpellScript(spell_atramedes_sound_bar);
    RegisterSpellScript(spell_atramedes_noisy);
    RegisterSpellScript(spell_atramedes_vertigo);
    RegisterSpellAndAuraScriptPair(spell_atramedes_sonic_flames, spell_atramedes_sonic_flames_AuraScript);
    RegisterSpellScript(spell_atramedes_devastation_trigger);
    RegisterSpellScript(spell_atramedes_sonic_breath);
    RegisterSpellScript(spell_atramedes_destroy_shield);
    RegisterSpellScript(spell_atramedes_pestered);
    RegisterSpellScript(spell_atramedes_apply_vehicle_periodic);
}
