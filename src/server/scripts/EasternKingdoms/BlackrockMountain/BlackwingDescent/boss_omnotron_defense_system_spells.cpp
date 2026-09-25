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

#include "ObjectMgr.h"
#include "ScriptMgr.h"
#include "Containers.h"
#include "ScriptedCreature.h"
#include "SpellScript.h"
#include "SpellAuraEffects.h"
#include "PassiveAI.h"
#include "Player.h"
#include "SpellMgr.h"
#include "InstanceScript.h"
#include "ObjectAccessor.h"
#include "Map.h"
#include "MotionMaster.h"
#include "TemporarySummon.h"
#include "blackwing_descent.h"
#include "boss_omnotron_defense_system_shared.h"

namespace BlackwingDescent::OmnotronDefenseSystem
{
struct npc_lord_victor_nefarius_omnotron : public PassiveAI
{
    npc_lord_victor_nefarius_omnotron(Creature* creature) : PassiveAI(creature), _instance(me->GetInstanceScript()), _abilitiesOnCooldown(false) { }

    void IsSummonedBy(Unit* /*summoner*/) override
    {
        _events.ScheduleEvent(EVENT_TALK_INTRO, 4s + 700ms);
    }

    void JustSummoned(Creature* summon) override
    {
        if (summon->GetEntry() != NPC_POWER_GENERATOR && summon->GetEntry() != NPC_CHEMICAL_CLOUD)
            return;

        TempSummon* summoned = summon->ToTempSummon();
        if (!summoned)
            return;

        // Lord Victor Nefarius only manipulates the abilities of longest active golem at a time
        if (!_abilitiesOnCooldown)
        {
            switch (summon->GetEntry())
            {
                case NPC_CHEMICAL_CLOUD:
                    _events.ScheduleEvent(EVENT_TELEPORT_INTO_CHEMICAL_CLOUD, 2s);
                    _abilitiesOnCooldown = true;
                    _events.ScheduleEvent(EVENT_CLEAR_ABILITY_COOLDOWN, 30s);
                    break;
                case NPC_POWER_GENERATOR:
                    _events.ScheduleEvent(EVENT_OVERCHARGE, 10s);
                    _abilitiesOnCooldown = true;
                    _events.ScheduleEvent(EVENT_CLEAR_ABILITY_COOLDOWN, 30s);
                    break;
                default:
                    break;
            }
        }
    }

    void DoAction(int32 action) override
    {
        switch (action)
        {
            case ACTION_CAST_SHADOW_INFUSION:
                if (!_abilitiesOnCooldown)
                {
                    DoCastAOE(SPELL_SHADOW_INFUSION);
                    _events.ScheduleEvent(EVENT_TALK_MANIPULATE_LIGHTNING_CONDUCTOR, 6s);
                    _abilitiesOnCooldown = true;
                    _events.ScheduleEvent(EVENT_CLEAR_ABILITY_COOLDOWN, 30s);
                }
                break;
            case ACTION_CAST_ENCASING_SHADOWS:
                if (!_abilitiesOnCooldown)
                {
                    _events.ScheduleEvent(EVENT_ENCASING_SHADOWS, 300ms);
                    _abilitiesOnCooldown = true;
                    _events.ScheduleEvent(EVENT_CLEAR_ABILITY_COOLDOWN, 30s);
                }
                break;
            default:
                break;
        }
    }

    void UpdateAI(uint32 diff) override
    {
        _events.Update(diff);

        while (uint32 eventId = _events.ExecuteEvent())
        {
            switch (eventId)
            {
                case EVENT_TALK_INTRO:
                    Talk(SAY_INTRO_HEROIC);
                    break;
                case EVENT_TELEPORT_INTO_CHEMICAL_CLOUD:
                    DoCastSelf(SPELL_SHADOW_TELEPORT);
                    _events.ScheduleEvent(EVENT_GRIP_OF_DEATH, 100ms);
                    break;
                case EVENT_GRIP_OF_DEATH:
                    DoCastAOE(SPELL_GRIP_OF_DEATH);
                    _events.ScheduleEvent(EVENT_TALK_PULL_PLAYERS_INTO_CHEMICAL_CLOUD, 2s);
                    break;
                case EVENT_TALK_PULL_PLAYERS_INTO_CHEMICAL_CLOUD:
                    Talk(SAY_PULL_INTO_CHEMICAL_CLOUD);
                    _events.ScheduleEvent(EVENT_TELEPORT_BACK, 1s + 300ms);
                    break;
                case EVENT_TELEPORT_BACK:
                    DoCastSelf(SPELL_SHADOW_TELEPORT_BACK);
                    break;
                case EVENT_TALK_MANIPULATE_LIGHTNING_CONDUCTOR:
                    Talk(SAY_MANIPULATE_LIGHTNING_CONDUCTOR);
                    break;
                case EVENT_ENCASING_SHADOWS:
                    DoCastAOE(SPELL_ENCASING_SHADOWS);
                    _events.ScheduleEvent(EVENT_TALK_ROOT_PLAYER, 5s);
                    break;
                case EVENT_TALK_ROOT_PLAYER:
                    Talk(SAY_ROOT_PLAYER_IN_PLACE);
                    break;
                case EVENT_OVERCHARGE:
                    DoCastAOE(SPELL_OVERCHARGE);
                    _events.ScheduleEvent(EVENT_TALK_OVERCHARGE_POWER_GENERATOR, 5s + 400ms);
                    break;
                case EVENT_TALK_OVERCHARGE_POWER_GENERATOR:
                    Talk(SAY_OVERCHARGE_POWER_GENERATOR);
                    break;
                case EVENT_CLEAR_ABILITY_COOLDOWN:
                    _abilitiesOnCooldown = false;
                    break;
                default:
                    break;
            }
        }
    }

private:
    EventMap _events;
    InstanceScript* _instance;
    bool _abilitiesOnCooldown;
};

class DistanceCheck
{
    public:
        DistanceCheck(Unit* caster) : _caster(caster) { }

        bool operator()(WorldObject* object)
        {
            return (object->GetExactDist2d(_caster) < 10.0f);
        }
    private:
        Unit* _caster;
};

struct npc_omnotron_poison_bomb : public ScriptedAI
{
    npc_omnotron_poison_bomb(Creature* creature) : ScriptedAI(creature) { }

    void IsSummonedBy(Unit* summoner) override
    {
        DoZoneInCombat();

        // Blizzard has a AOE target spell for this but for some reason they doesn't use it so we wont do so as well.
        std::list<Unit*> targets;
        SelectTargetList(targets, 25, SELECT_TARGET_RANDOM, 0, 100.0f, true);

        if (targets.empty())
            return;

        std::list<Unit*> targetsCopy = targets;
        targets.remove_if(DistanceCheck(summoner));

        if (targets.empty())
            targets = targetsCopy;

        Trinity::Containers::RandomResize(targets, 1);

        if (Unit* target = targets.front())
        {
            DoCast(target, SPELL_FIXATE_DUMMY, true);
            me->ClearUnitState(UNIT_STATE_CASTING);
            AddThreat(target, 500000.0f);
            me->GetThreatManager().FixateTarget(target);
        }
    }

    void JustDied(Unit* /*killer*/) override
    {
        me->DespawnOrUnsummon(2s + 500ms);
    }

    void SpellHit(WorldObject* /*caster*/, SpellInfo const* spell) override
    {
        if (spell->Id == SPELL_QUIETE_SUICIDE)
        {
            if (InstanceScript* instance = me->GetInstanceScript())
                if (!instance->instance->GetWorldStateValue(WORLD_STATE_ID_POISON_BOMB))
                    instance->DoUpdateWorldState(WORLD_STATE_ID_POISON_BOMB, 1);

            DoCastSelf(SPELL_POISON_BOMB_DAMAGE, true);
            DoCastSelf(SPELL_POISON_BOMB_SUMMON_PUDDLE, true);
        }
    }
};

class GuidCheck
{
    public:
        GuidCheck(ObjectGuid golemGUID) : _golemGUID(golemGUID)  { }

        bool operator()(WorldObject* object)
        {
            return object->GetGUID() != _golemGUID;
        }
    private:
        ObjectGuid _golemGUID;
};

class spell_omnotron_controller_recharge : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_RECHARGING_ELECTRON,
                SPELL_RECHARGING_MAGMATRON,
                SPELL_RECHARGING_TOXITRON,
                SPELL_RECHARGING_ARCANOTRON
            });
    }

    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.empty())
            return;

        InstanceScript* instance = GetCaster()->GetInstanceScript();
        if (!instance)
            return;

        Creature* omnotron = instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM);
        if (!omnotron)
            return;

        ObjectGuid golemGuid = omnotron->AI()->GetGUID(DATA_NEXT_GOLEM_IN_QUEUE);
        targets.remove_if(GuidCheck(golemGuid));
    }

    void HandleScriptEffect(SpellEffIndex /*effIndex*/)
    {
        if (Unit* caster = GetCaster())
        {
            uint32 rechargingSpellId = 0;
            switch (GetHitUnit()->GetEntry())
            {
                case NPC_ELECTRON:
                    rechargingSpellId = SPELL_RECHARGING_ELECTRON;
                    break;
                case NPC_MAGMATRON:
                    rechargingSpellId = SPELL_RECHARGING_MAGMATRON;
                    break;
                case NPC_TOXITRON:
                    rechargingSpellId = SPELL_RECHARGING_TOXITRON;
                    break;
                case NPC_ARCANOTRON:
                    rechargingSpellId = SPELL_RECHARGING_ARCANOTRON;
                    break;
                default:
                    break;
            }

            if (rechargingSpellId)
                caster->CastSpell(caster, rechargingSpellId);
        }
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_omnotron_controller_recharge::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENTRY);
        OnEffectHitTarget.Register(&spell_omnotron_controller_recharge::HandleScriptEffect, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

class spell_omnotron_recharging : public AuraScript
{
    void AfterRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (GetTargetApplication()->GetRemoveMode().HasFlag(AuraRemoveFlags::Expired))
            if (Creature* golem = GetTarget()->ToCreature())
                if (golem->IsAIEnabled())
                    golem->AI()->DoAction(ACTION_ACTIVATE_GOLEM);
    }

    void Register() override
    {
        AfterEffectRemove.Register(&spell_omnotron_recharging::AfterRemove, EFFECT_0, SPELL_AURA_PERIODIC_ENERGIZE, AURA_EFFECT_HANDLE_REAL);
    }
};

class spell_omnotron_activated : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_SHUTTING_DOWN });
    }

    void HandleTick(AuraEffect const* /*aurEff*/)
    {
        PreventDefaultAction();
        if (Unit* caster = GetCaster())
            if (caster->GetVictim())
                caster->CastSpell(GetCaster()->GetVictim(), GetSpellInfo()->Effects[EFFECT_0].TriggerSpell, TriggerCastFlags(TRIGGERED_FULL_MASK & ~TRIGGERED_IGNORE_POWER_COST));
    }

    void AfterRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        GetTarget()->CastSpell(GetTarget(), SPELL_SHUTTING_DOWN);
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_omnotron_activated::HandleTick, EFFECT_0, SPELL_AURA_PERIODIC_TRIGGER_SPELL);
        AfterEffectRemove.Register(&spell_omnotron_activated::AfterRemove, EFFECT_0, SPELL_AURA_PERIODIC_TRIGGER_SPELL, AURA_EFFECT_HANDLE_REAL);
    }
};

class spell_omnotron_inactive : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_RECHARGING_ELECTRON });
    }

    void HandleScriptEffect(SpellEffIndex /*effIndex*/)
    {
        Unit* target = GetHitUnit();
        target->CastSpell(target, SPELL_POWERED_DOWN, true);
        if (Creature* golem = target->ToCreature())
            if (golem->IsAIEnabled())
                golem->AI()->DoAction(ACTION_DEACTIVATE_GOLEM);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_omnotron_inactive::HandleScriptEffect, EFFECT_2, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

class spell_omnotron_electrical_discharge_trigger : public SpellScript
{
    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.empty())
            return;

        Trinity::Containers::RandomResize(targets, 1);
    }

    void HandleDummyEffect(SpellEffIndex effIndex)
    {
        if (Unit* caster = GetCaster())
            caster->CastSpell(GetHitUnit(), GetSpellInfo()->Effects[effIndex].BasePoints, true);
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_omnotron_electrical_discharge_trigger::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENEMY);
        OnEffectHitTarget.Register(&spell_omnotron_electrical_discharge_trigger::HandleDummyEffect, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

class spell_omnotron_electrical_discharge : public SpellScript
{
    bool Load() override
    {
        _chainTargetCount = 0;
        return true;
    }

    void HandleDamageBonus(SpellEffIndex /*effIndex*/)
    {
        int32 damage = GetHitDamage();
        AddPct(damage, _chainTargetCount * 20);
        _chainTargetCount++;
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_omnotron_electrical_discharge::HandleDamageBonus, EFFECT_0, SPELL_EFFECT_SCHOOL_DAMAGE);
    }
private:
    uint8 _chainTargetCount;
};

class spell_omnotron_unstable_shield : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_STATIC_SHOCK });
    }

    bool CheckProc(ProcEventInfo& eventInfo)
    {
        return eventInfo.GetDamageInfo();
    }

    void HandleProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
    {
        PreventDefaultAction();
        Unit* caster = GetTarget();
        Unit* target = eventInfo.GetDamageInfo()->GetAttacker();
        if (!target)
            return;

        caster->CastSpell(target, SPELL_STATIC_SHOCK, aurEff);

        if (InstanceScript* instance = caster->GetInstanceScript())
            if (!instance->instance->GetWorldStateValue(WORLD_STATE_ID_STATIC_SHOCK))
                instance->DoUpdateWorldState(WORLD_STATE_ID_STATIC_SHOCK, 1);
    }

    void Register() override
    {
        DoCheckProc.Register(&spell_omnotron_unstable_shield::CheckProc);
        OnEffectProc.Register(&spell_omnotron_unstable_shield::HandleProc, EFFECT_0, SPELL_AURA_PROC_TRIGGER_SPELL);
    }
};

class spell_omnotron_aquiring_target : public SpellScript
{
    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.empty())
            return;

        Trinity::Containers::RandomResize(targets, 1);
    }

    void HandleDummyEffect(SpellEffIndex effIndex)
    {
        if (Unit* caster = GetCaster())
        {
            caster->StopMoving();
            caster->CastSpell(GetHitUnit(), GetSpellInfo()->Effects[effIndex].BasePoints, true);
        }
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_omnotron_aquiring_target::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENEMY);
        OnEffectHitTarget.Register(&spell_omnotron_aquiring_target::HandleDummyEffect, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

class spell_omnotron_acquiring_target_periodic : public AuraScript
{
    void HandleTick(AuraEffect const* /*aurEff*/)
    {
        PreventDefaultAction();
        if (Unit* caster = GetCaster())
            caster->CastSpell(GetTarget(), GetSpellInfo()->Effects[EFFECT_0].TriggerSpell, true);
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_omnotron_acquiring_target_periodic::HandleTick, EFFECT_0, SPELL_AURA_PERIODIC_TRIGGER_SPELL);
    }
};

class spell_omnotron_barrier : public AuraScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_BACKDRAFT });
    }

    void HandleAbsorbRemove(AuraEffect const* /*aurEff*/, AuraEffectHandleModes /*mode*/)
    {
        if (GetTargetApplication()->GetRemoveMode().HasFlag(AuraRemoveFlags::ByEnemySpell))
            if (Unit* caster = GetCaster())
                caster->CastSpell(caster, SPELL_BACKDRAFT, true);
    }

    void Register() override
    {
        AfterEffectRemove.Register(&spell_omnotron_barrier::HandleAbsorbRemove, EFFECT_0, SPELL_AURA_SCHOOL_ABSORB, AURA_EFFECT_HANDLE_REAL);
    }
};

class spell_omnotron_shadow_infusion : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_SHADOW_CONDUCTOR,
                SPELL_LIGHTNING_CONDUCTOR_10N
            });
    }

    void HandleScriptEffect(SpellEffIndex /*effIndex*/)
    {
        Unit* target = GetHitUnit();
        target->RemoveAurasDueToSpell(sSpellMgr->GetSpellIdForDifficulty(SPELL_LIGHTNING_CONDUCTOR_10N, target));
        target->CastSpell(target, SPELL_SHADOW_CONDUCTOR, true);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_omnotron_shadow_infusion::HandleScriptEffect, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

class spell_omnotron_shadow_conductor : public SpellScript
{
    void ChangeDamage(SpellEffIndex /*effIndex*/)
    {
        Unit* caster = GetCaster();
        Unit* target = GetHitUnit();

        if (!caster || !target)
            return;

        float distanceMultiplier = std::max(caster->GetExactDist2d(target) * 0.5f, 1.0f);
        SetEffectValue(int32(6000 * distanceMultiplier));
    }

    void Register() override
    {
        OnEffectLaunchTarget.Register(&spell_omnotron_shadow_conductor::ChangeDamage, EFFECT_0, SPELL_EFFECT_SCHOOL_DAMAGE);
    }
};

class spell_omnotron_overcharge : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_POWER_GENERATOR_NORMAL,
                SPELL_OVERCHARGED_POWER_GENERATOR,
                SPELL_GROW_STACKER,
                SPELL_ARCANE_BLOWBACK
            });
    }

    void HandleScriptEffect(SpellEffIndex /*effIndex*/)
    {
        Creature* target = GetHitCreature();
        if (!target)
            return;

        target->RemoveAurasDueToSpell(sSpellMgr->GetSpellIdForDifficulty(SPELL_POWER_GENERATOR_NORMAL, target));
        target->CastSpell(target, SPELL_OVERCHARGED_POWER_GENERATOR, true);
        target->CastSpell(target, SPELL_GROW_STACKER);
        target->m_Events.AddEventAtOffset([target]()
        {
            target->RemoveAllAuras();
            target->CastSpell(target, SPELL_ARCANE_BLOWBACK);
            target->DespawnOrUnsummon(1s);
        }, 8s);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_omnotron_overcharge::HandleScriptEffect, EFFECT_0, SPELL_EFFECT_SCRIPT_EFFECT);
    }
};

class spell_omnotron_overcharged_power_generator : public AuraScript
{
    void HandlePeriodic(AuraEffect const* aurEff)
    {
        PreventDefaultAction();
        if (Unit* target = GetTarget())
        {
            uint32 triggerSpell = GetSpellInfo()->Effects[EFFECT_0].TriggerSpell;
            int32 radius = target->GetObjectScale() * 10000;
            target->CastSpell(nullptr, triggerSpell,  CastSpellExtraArgs(aurEff).SetOriginalCaster(target->GetGUID()).AddSpellMod(SPELLVALUE_RADIUS_MOD, radius));
        }
    }

    void Register() override
    {
        OnEffectPeriodic.Register(&spell_omnotron_overcharged_power_generator::HandlePeriodic, EFFECT_0, SPELL_AURA_PERIODIC_TRIGGER_SPELL);
    }
};

class spell_omnotron_flamethrower : public SpellScript
{
    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.size() >= 2)
            if (InstanceScript* instance = GetCaster()->GetInstanceScript())
                if (!instance->instance->GetWorldStateValue(WORLD_STATE_ID_FLAMETHROWER))
                    instance->DoUpdateWorldState(WORLD_STATE_ID_FLAMETHROWER, 1);
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_omnotron_flamethrower::FilterTargets, EFFECT_0, TARGET_UNIT_CONE_CASTER_TO_DEST_ENEMY);
    }
};
}

void AddSC_boss_omnotron_defense_system_spells()
{
    using namespace BlackwingDescent;
    using namespace BlackwingDescent::OmnotronDefenseSystem;
    RegisterBlackwingDescentCreatureAI(npc_lord_victor_nefarius_omnotron);
    RegisterBlackwingDescentCreatureAI(npc_omnotron_poison_bomb);
    RegisterSpellScript(spell_omnotron_controller_recharge);
    RegisterSpellScript(spell_omnotron_recharging);
    RegisterSpellScript(spell_omnotron_activated);
    RegisterSpellScript(spell_omnotron_inactive);
    RegisterSpellScript(spell_omnotron_electrical_discharge);
    RegisterSpellScript(spell_omnotron_electrical_discharge_trigger);
    RegisterSpellScript(spell_omnotron_unstable_shield);
    RegisterSpellScript(spell_omnotron_aquiring_target);
    RegisterSpellScript(spell_omnotron_acquiring_target_periodic);
    RegisterSpellScript(spell_omnotron_barrier);
    RegisterSpellScript(spell_omnotron_shadow_infusion);
    RegisterSpellScript(spell_omnotron_shadow_conductor);
    RegisterSpellScript(spell_omnotron_overcharge);
    RegisterSpellScript(spell_omnotron_overcharged_power_generator);
    RegisterSpellScript(spell_omnotron_flamethrower);
}
