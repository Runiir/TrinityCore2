/*
 * This file is part of the TrinityCore Project. See AUTHORS file for Copyright information
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or (at your
 * option) any later version.
 */

#include "Containers.h"
#include "InstanceScript.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "ScriptMgr.h"
#include "ScriptedCreature.h"
#include "Spell.h"
#include "SpellAuraEffects.h"
#include "SpellScript.h"
#include "Unit.h"
#include "Vehicle.h"
#include "blackwing_descent.h"
#include "boss_magmaw_shared.h"

namespace BlackwingDescent::Magmaw
{
namespace
{
class IsOnVehicleCheck
{
public:
    bool operator()(WorldObject* object) const
    {
        return object->ToUnit()->GetVehicle();
    }
};

class DistanceCheck
{
public:
    explicit DistanceCheck(Unit* caster) : _caster(caster) { }

    bool operator()(WorldObject* object) const
    {
        if (Unit* unit = object->ToUnit())
            return unit->GetExactDist2d(_caster) < _caster->GetCombatReach() + 15.0f;

        return true;
    }

private:
    Unit* _caster;
};
}

class spell_magmaw_pillar_of_flame_forcecast : public SpellScript
{
    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.empty())
            return;

        targets.remove_if(IsOnVehicleCheck());

        if (targets.empty())
            return;

        // Hotfix (2010-12-21): Magmaw's Pillar of Flame now prefers targets further than 15 yards away
        std::list<WorldObject*> targetsCopy = targets;
        targetsCopy.remove_if(DistanceCheck(GetCaster()));
        if (!targetsCopy.empty())
            targets = targetsCopy;

        Trinity::Containers::RandomResize(targets, 1);
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_magmaw_pillar_of_flame_forcecast::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENEMY);
    }
};

class spell_magmaw_ride_vehicle : public SpellScript
{
    void SetTarget(WorldObject*& target)
    {
        if (InstanceScript* instance = GetCaster()->GetInstanceScript())
        {
            if (Creature* magmaw = instance->GetCreature(DATA_MAGMAW))
            {
                if (Creature* pincer = ObjectAccessor::GetCreature(*GetCaster(), magmaw->AI()->GetGUID(DATA_FREE_PINCER)))
                    target = pincer;
                else
                    target = nullptr;
            }
        }
    }

    void Register() override
    {
        OnObjectTargetSelect.Register(&spell_magmaw_ride_vehicle::SetTarget, EFFECT_0, TARGET_UNIT_TARGET_ANY);
    }
};

class spell_magmaw_launch_hook : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_LAUNCH_HOOK_1,
                SPELL_LAUNCH_HOOK_2,
                SPELL_CHAIN_VISUAL_1,
                SPELL_CHAIN_VISUAL_2
            });
    }

    void AfterApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        Unit* target = GetTarget();

        if (target->HasAura(SPELL_LAUNCH_HOOK_1) && target->HasAura(SPELL_LAUNCH_HOOK_2))
        {
            if (InstanceScript* instance = target->GetInstanceScript())
                if (Creature* magmaw = instance->GetCreature(DATA_MAGMAW))
                    magmaw->AI()->DoAction(ACTION_IMPALE_MAGMAW);

            target->RemoveAllAuras();
            target->CastSpell(target, SPELL_CHAIN_VISUAL_1);
            target->CastSpell(target, SPELL_CHAIN_VISUAL_2);
            target->CastSpell(target, SPELL_EJECT_PASSENGER);
        }
    }

    void Register() override
    {
        AfterEffectApply.Register(&spell_magmaw_launch_hook::AfterApply, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};

class spell_magmaw_eject_passenger : public SpellScript
{
    void EjectPassenger(SpellEffIndex /*effIndex*/)
    {
        Unit* target = GetHitUnit();
        target->m_Events.AddEventAtOffset([target]()
        {
            target->CastSpell(target, SPELL_EJECT_PASSENGER_1, true);
        }, 3s + 500ms);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_magmaw_eject_passenger::EjectPassenger, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

class spell_magmaw_lava_parasite : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_PARASITIC_INFECTION_DAMAGE,
                SPELL_PARASITIC_INFECTION_VOMIT,
            });
    }

    void HandleProc(AuraEffect const* /*aurEff*/, ProcEventInfo& eventInfo)
    {
        // Hotfix (2010-12-21): Lava Parasites are functioning normally and cannot infest a player with more than 3 Parasite debuffs active
        PreventDefaultAction();

        Unit* caster = GetTarget();
        Unit* target = eventInfo.GetProcTarget();
        if (Vehicle* vehicle = target->GetVehicleKit())
        {
            if (vehicle->GetAvailableSeatCount())
            {
                caster->CastSpell(target, GetSpellInfo()->Effects[EFFECT_0].TriggerSpell, true);
                caster->CastSpell(target, SPELL_PARASITIC_INFECTION_DAMAGE, true);
                caster->CastSpell(target, SPELL_PARASITIC_INFECTION_VOMIT, true);
            }
        }
    }

    void Register() override
    {
        OnEffectProc.Register(&spell_magmaw_lava_parasite::HandleProc, EFFECT_0, SPELL_AURA_DUMMY);
    }
};

class spell_magmaw_blazing_inferno_targeting : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_BLAZING_INFERNO });
    }

    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.empty())
            return;

        targets.remove_if(IsOnVehicleCheck());

        if (targets.empty())
            return;

        // Hotfix (2010-03-16): In addition, on Heroic difficulty, Nefarian will now prefer ranged targets when spawning Blazing Bone Constructs.
        InstanceScript* instance = GetCaster()->GetInstanceScript();
        if (!instance)
            return;

        Creature* magmaw = instance->GetCreature(DATA_MAGMAW);
        if (!magmaw)
            return;

        std::list<WorldObject*> targetsCopy = targets;
        targetsCopy.remove_if(DistanceCheck(magmaw));
        if (!targetsCopy.empty())
            targets = targetsCopy;

        Trinity::Containers::RandomResize(targets, 1);
    }

    void HandleScriptEffect(SpellEffIndex /*effIndex*/)
    {
        if (Unit* caster = GetCaster())
            caster->CastSpell(GetHitUnit(), SPELL_BLAZING_INFERNO);
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_magmaw_blazing_inferno_targeting::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENEMY);
        OnEffectHitTarget.Register(&spell_magmaw_blazing_inferno_targeting::HandleScriptEffect, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

class spell_magmaw_shadow_breath_targeting : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_SHADOW_BREATH });
    }

    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.empty())
            return;

        targets.remove_if(IsOnVehicleCheck());

        if (targets.empty() || targets.size() < 2)
            return;

        Trinity::Containers::RandomResize(targets, 2);
    }

    void HandleDummyEffect(SpellEffIndex /*effIndex*/)
    {
        if (Unit* caster = GetCaster())
            caster->CastSpell(GetHitUnit(), SPELL_SHADOW_BREATH);
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_magmaw_shadow_breath_targeting::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENEMY);
        OnEffectHitTarget.Register(&spell_magmaw_shadow_breath_targeting::HandleDummyEffect, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

class spell_magmaw_lava_parasite_summon : public SpellScript
{
    void SetDest(SpellDestination& dest)
    {
        dest.RelocateOffset({ 0.0f, 0.0f, frand(13.0f, 15.0f), 0.0f });
    }

    void Register() override
    {
        OnDestinationTargetSelect.Register(&spell_magmaw_lava_parasite_summon::SetDest, EFFECT_0, TARGET_DEST_DEST_RANDOM);
    }
};

class spell_magmaw_massive_crash : public AuraScript
{
    void AfterApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (Creature* magmaw = GetTarget()->ToCreature())
            if (magmaw->IsAIEnabled())
                magmaw->AI()->DoAction(ACTION_ENABLE_MOUNTING);
    }

    void AfterRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (Creature* magmaw = GetTarget()->ToCreature())
            if (magmaw->IsAIEnabled())
                magmaw->AI()->DoAction(ACTION_DISABLE_MOUNTING);
    }

    void Register() override
    {
        AfterEffectApply.Register(&spell_magmaw_massive_crash::AfterApply, EFFECT_1, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
        AfterEffectRemove.Register(&spell_magmaw_massive_crash::AfterRemove, EFFECT_1, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};

class spell_magmaw_impale_self : public AuraScript
{
    void AfterApply(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (Creature* magmaw = GetTarget()->ToCreature())
            if (magmaw->IsAIEnabled())
                magmaw->AI()->DoAction(ACTION_EXPOSE_HEAD);
    }

    void AfterRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (Creature* magmaw = GetTarget()->ToCreature())
            if (magmaw->IsAIEnabled())
                magmaw->AI()->DoAction(ACTION_COVER_HEAD);
    }

    void Register() override
    {
        AfterEffectApply.Register(&spell_magmaw_impale_self::AfterApply, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
        AfterEffectRemove.Register(&spell_magmaw_impale_self::AfterRemove, EFFECT_0, SPELL_AURA_DUMMY, AURA_EFFECT_HANDLE_REAL);
    }
};

class spell_magmaw_captured : public AuraScript
{
    bool Validate(SpellInfo const* /*spell*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_EMOTE_MAGMA_LAVA_SPLASH,
                SPELL_EMOTE_SPELLCASTDIRECTED
            });
    }

    void HandleTick(AuraEffect const* /*aurEff*/)
    {
        GetTarget()->CastSpell(GetTarget(), RAND(SPELL_EMOTE_MAGMA_LAVA_SPLASH, SPELL_EMOTE_SPELLCASTDIRECTED), true);
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_magmaw_captured::HandleTick, EFFECT_0, SPELL_AURA_PERIODIC_DUMMY);
    }
};
}

void AddSC_boss_magmaw_encounter_spells()
{
    using namespace BlackwingDescent::Magmaw;
    RegisterSpellScript(spell_magmaw_pillar_of_flame_forcecast);
    RegisterSpellScript(spell_magmaw_ride_vehicle);
    RegisterSpellScript(spell_magmaw_launch_hook);
    RegisterSpellScript(spell_magmaw_eject_passenger);
    RegisterSpellScript(spell_magmaw_lava_parasite);
    RegisterSpellScript(spell_magmaw_lava_parasite_summon);
    RegisterSpellScript(spell_magmaw_blazing_inferno_targeting);
    RegisterSpellScript(spell_magmaw_shadow_breath_targeting);
    RegisterSpellScript(spell_magmaw_massive_crash);
    RegisterSpellScript(spell_magmaw_impale_self);
    RegisterSpellScript(spell_magmaw_captured);
}
