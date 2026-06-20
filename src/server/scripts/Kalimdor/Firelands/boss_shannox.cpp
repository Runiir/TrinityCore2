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

#include "ScriptMgr.h"
#include "firelands.h"
#include "InstanceScript.h"
#include "MotionMaster.h"
#include "Player.h"
#include "ScriptedCreature.h"

namespace Firelands::Shannox
{
enum Spells
{
    SPELL_ARCING_SLASH                   = 99931,
    SPELL_HURL_SPEAR                     = 100002,
    SPELL_MAGMA_RUPTURE                  = 99840,
    SPELL_THROW_CRYSTAL_PRISON_TRAP      = 99836,
    SPELL_THROW_IMMOLATION_TRAP          = 99839,
    SPELL_CRYSTAL_PRISON_TRAP_EFFECT     = 99837,
    SPELL_IMMOLATION_TRAP_EFFECT         = 99838,
    SPELL_LIMB_RIP                       = 99832,
    SPELL_FACE_RAGE                      = 100129,
    SPELL_BERSERK                        = 26662
};

enum Events
{
    EVENT_ARCING_SLASH = 1,
    EVENT_HURL_SPEAR,
    EVENT_CRYSTAL_PRISON_TRAP,
    EVENT_IMMOLATION_TRAP,
    EVENT_BERSERK,
    EVENT_LIMB_RIP,
    EVENT_FACE_RAGE,
    EVENT_RAGEFACE_SWITCH_TARGET,
    EVENT_ARM_TRAP,
    EVENT_TRIGGER_TRAP
};

enum Actions
{
    ACTION_SHANNOX_ENGAGE = 1,
    ACTION_SHANNOX_EVADE,
    ACTION_SHANNOX_DIED,
    ACTION_SHANNOX_PET_DIED
};

class boss_shannox : public CreatureScript
{
public:
    boss_shannox() : CreatureScript("boss_shannox") { }

    struct boss_shannoxAI : public BossAI
    {
        boss_shannoxAI(Creature* creature) : BossAI(creature, DATA_SHANNOX), _frenzyStacks(0) { }

        void Reset() override
        {
            _Reset();
            _frenzyStacks = 0;
            instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, me);
        }

        void JustEngagedWith(Unit* who) override
        {
            BossAI::JustEngagedWith(who);
            instance->SendEncounterUnit(ENCOUNTER_FRAME_ENGAGE, me);

            events.ScheduleEvent(EVENT_ARCING_SLASH, 6 * IN_MILLISECONDS);
            events.ScheduleEvent(EVENT_IMMOLATION_TRAP, 8 * IN_MILLISECONDS);
            events.ScheduleEvent(EVENT_CRYSTAL_PRISON_TRAP, 18 * IN_MILLISECONDS);
            events.ScheduleEvent(EVENT_HURL_SPEAR, 30 * IN_MILLISECONDS);
            events.ScheduleEvent(EVENT_BERSERK, 10 * MINUTE * IN_MILLISECONDS);

            EngagePet(DATA_RIPLIMB, who);
            EngagePet(DATA_RAGEFACE, who);
        }

        void JustDied(Unit* /*killer*/) override
        {
            _JustDied();
            instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, me);
            summons.DespawnAll();
            DoPetAction(DATA_RIPLIMB, ACTION_SHANNOX_DIED);
            DoPetAction(DATA_RAGEFACE, ACTION_SHANNOX_DIED);
        }

        void EnterEvadeMode(EvadeReason /*why*/) override
        {
            instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, me);
            DoPetAction(DATA_RIPLIMB, ACTION_SHANNOX_EVADE);
            DoPetAction(DATA_RAGEFACE, ACTION_SHANNOX_EVADE);
            me->GetMotionMaster()->MoveTargetedHome();
            summons.DespawnAll();
            _DespawnAtEvade();
        }

        void DoAction(int32 action) override
        {
            if (action != ACTION_SHANNOX_PET_DIED)
                return;

            ++_frenzyStacks;
            if (_frenzyStacks >= 2)
                DoCastSelf(SPELL_BERSERK, true);
        }

        void UpdateAI(uint32 diff) override
        {
            if (!UpdateVictim())
                return;

            events.Update(diff);

            if (me->HasUnitState(UNIT_STATE_CASTING))
                return;

            while (uint32 eventId = events.ExecuteEvent())
            {
                switch (eventId)
                {
                    case EVENT_ARCING_SLASH:
                        DoCastVictim(SPELL_ARCING_SLASH);
                        events.ScheduleEvent(EVENT_ARCING_SLASH, 12 * IN_MILLISECONDS);
                        break;
                    case EVENT_HURL_SPEAR:
                        if (IsRiplimbAlive())
                            DoCastVictim(SPELL_HURL_SPEAR);
                        else
                            DoCastAOE(SPELL_MAGMA_RUPTURE);
                        events.ScheduleEvent(EVENT_HURL_SPEAR, 45 * IN_MILLISECONDS);
                        break;
                    case EVENT_CRYSTAL_PRISON_TRAP:
                        if (Unit* target = SelectTarget(SELECT_TARGET_RANDOM, 0, 0.0f, true))
                            DoCast(target, SPELL_THROW_CRYSTAL_PRISON_TRAP);
                        events.ScheduleEvent(EVENT_CRYSTAL_PRISON_TRAP, 25 * IN_MILLISECONDS);
                        break;
                    case EVENT_IMMOLATION_TRAP:
                        if (Unit* target = SelectTarget(SELECT_TARGET_RANDOM, 0, 0.0f, true))
                            DoCast(target, SPELL_THROW_IMMOLATION_TRAP);
                        events.ScheduleEvent(EVENT_IMMOLATION_TRAP, 25 * IN_MILLISECONDS);
                        break;
                    case EVENT_BERSERK:
                        DoCastSelf(SPELL_BERSERK, true);
                        break;
                    default:
                        break;
                }
            }

            DoMeleeAttackIfReady();
        }

    private:
        void EngagePet(uint32 dataId, Unit* target)
        {
            if (Creature* pet = instance->GetCreature(dataId))
            {
                if (!pet->IsAlive() || !pet->IsAIEnabled())
                    return;

                pet->AI()->DoAction(ACTION_SHANNOX_ENGAGE);
                pet->AI()->AttackStart(target);
            }
        }

        void DoPetAction(uint32 dataId, int32 action)
        {
            if (Creature* pet = instance->GetCreature(dataId))
                if (pet->IsAIEnabled())
                    pet->AI()->DoAction(action);
        }

        bool IsRiplimbAlive() const
        {
            Creature* riplimb = instance->GetCreature(DATA_RIPLIMB);
            return riplimb && riplimb->IsAlive();
        }

        uint8 _frenzyStacks;
    };

    CreatureAI* GetAI(Creature* creature) const override
    {
        return GetFirelandsAI<boss_shannoxAI>(creature);
    }
};

class npc_shannox_riplimb : public CreatureScript
{
public:
    npc_shannox_riplimb() : CreatureScript("npc_shannox_riplimb") { }

    struct npc_shannox_riplimbAI : public ScriptedAI
    {
        npc_shannox_riplimbAI(Creature* creature) : ScriptedAI(creature), _instance(creature->GetInstanceScript()) { }

        void Reset() override
        {
            _events.Reset();
        }

        void DoAction(int32 action) override
        {
            switch (action)
            {
                case ACTION_SHANNOX_ENGAGE:
                    DoZoneInCombat();
                    StartEncounterEvents();
                    break;
                case ACTION_SHANNOX_EVADE:
                    EnterEvadeMode(EVADE_REASON_OTHER);
                    break;
                case ACTION_SHANNOX_DIED:
                    me->DespawnOrUnsummon(5 * IN_MILLISECONDS);
                    break;
                default:
                    break;
            }
        }

        void JustEngagedWith(Unit* /*who*/) override
        {
            StartEncounterEvents();
        }

        void JustDied(Unit* /*killer*/) override
        {
            if (Creature* shannox = _instance->GetCreature(DATA_SHANNOX))
                if (shannox->IsAlive() && shannox->IsAIEnabled())
                    shannox->AI()->DoAction(ACTION_SHANNOX_PET_DIED);
        }

        void UpdateAI(uint32 diff) override
        {
            if (!UpdateVictim())
                return;

            _events.Update(diff);

            if (me->HasUnitState(UNIT_STATE_CASTING))
                return;

            while (uint32 eventId = _events.ExecuteEvent())
            {
                switch (eventId)
                {
                    case EVENT_LIMB_RIP:
                        DoCastVictim(SPELL_LIMB_RIP);
                        _events.ScheduleEvent(EVENT_LIMB_RIP, 12 * IN_MILLISECONDS);
                        break;
                    default:
                        break;
                }
            }

            DoMeleeAttackIfReady();
        }

    private:
        void StartEncounterEvents()
        {
            _events.Reset();
            _events.ScheduleEvent(EVENT_LIMB_RIP, 6 * IN_MILLISECONDS);
        }

        InstanceScript* _instance;
        EventMap _events;
    };

    CreatureAI* GetAI(Creature* creature) const override
    {
        return GetFirelandsAI<npc_shannox_riplimbAI>(creature);
    }
};

class npc_shannox_rageface : public CreatureScript
{
public:
    npc_shannox_rageface() : CreatureScript("npc_shannox_rageface") { }

    struct npc_shannox_ragefaceAI : public ScriptedAI
    {
        npc_shannox_ragefaceAI(Creature* creature) : ScriptedAI(creature), _instance(creature->GetInstanceScript()) { }

        void Reset() override
        {
            _events.Reset();
        }

        void DoAction(int32 action) override
        {
            switch (action)
            {
                case ACTION_SHANNOX_ENGAGE:
                    DoZoneInCombat();
                    StartEncounterEvents();
                    break;
                case ACTION_SHANNOX_EVADE:
                    EnterEvadeMode(EVADE_REASON_OTHER);
                    break;
                case ACTION_SHANNOX_DIED:
                    me->DespawnOrUnsummon(5 * IN_MILLISECONDS);
                    break;
                default:
                    break;
            }
        }

        void JustEngagedWith(Unit* /*who*/) override
        {
            StartEncounterEvents();
        }

        void JustDied(Unit* /*killer*/) override
        {
            if (Creature* shannox = _instance->GetCreature(DATA_SHANNOX))
                if (shannox->IsAlive() && shannox->IsAIEnabled())
                    shannox->AI()->DoAction(ACTION_SHANNOX_PET_DIED);
        }

        void UpdateAI(uint32 diff) override
        {
            if (!UpdateVictim())
                return;

            _events.Update(diff);

            if (me->HasUnitState(UNIT_STATE_CASTING))
                return;

            while (uint32 eventId = _events.ExecuteEvent())
            {
                switch (eventId)
                {
                    case EVENT_RAGEFACE_SWITCH_TARGET:
                        if (Unit* target = SelectTarget(SELECT_TARGET_RANDOM, 0, 0.0f, true))
                            AttackStart(target);
                        _events.ScheduleEvent(EVENT_RAGEFACE_SWITCH_TARGET, 10 * IN_MILLISECONDS);
                        break;
                    case EVENT_FACE_RAGE:
                        if (Unit* target = SelectTarget(SELECT_TARGET_RANDOM, 0, 0.0f, true))
                            DoCast(target, SPELL_FACE_RAGE);
                        _events.ScheduleEvent(EVENT_FACE_RAGE, 30 * IN_MILLISECONDS);
                        break;
                    default:
                        break;
                }
            }

            DoMeleeAttackIfReady();
        }

    private:
        void StartEncounterEvents()
        {
            _events.Reset();
            _events.ScheduleEvent(EVENT_RAGEFACE_SWITCH_TARGET, 5 * IN_MILLISECONDS);
            _events.ScheduleEvent(EVENT_FACE_RAGE, 20 * IN_MILLISECONDS);
        }

        InstanceScript* _instance;
        EventMap _events;
    };

    CreatureAI* GetAI(Creature* creature) const override
    {
        return GetFirelandsAI<npc_shannox_ragefaceAI>(creature);
    }
};

class npc_shannox_trap : public CreatureScript
{
public:
    npc_shannox_trap() : CreatureScript("npc_shannox_trap") { }

    struct npc_shannox_trapAI : public ScriptedAI
    {
        npc_shannox_trapAI(Creature* creature) : ScriptedAI(creature), _armed(false)
        {
            me->SetReactState(REACT_PASSIVE);
            me->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NON_ATTACKABLE);
        }

        void Reset() override
        {
            _armed = false;
            _events.Reset();
            _events.ScheduleEvent(EVENT_ARM_TRAP, 2 * IN_MILLISECONDS);
        }

        void IsSummonedBy(Unit* /*summoner*/) override
        {
            Reset();
        }

        void UpdateAI(uint32 diff) override
        {
            _events.Update(diff);

            while (uint32 eventId = _events.ExecuteEvent())
            {
                switch (eventId)
                {
                    case EVENT_ARM_TRAP:
                        _armed = true;
                        _events.ScheduleEvent(EVENT_TRIGGER_TRAP, 500);
                        break;
                    case EVENT_TRIGGER_TRAP:
                        if (Unit* target = SelectTriggerTarget())
                        {
                            DoCast(target, me->GetEntry() == NPC_CRYSTAL_PRISON_TRAP ? SPELL_CRYSTAL_PRISON_TRAP_EFFECT : SPELL_IMMOLATION_TRAP_EFFECT);
                            me->DespawnOrUnsummon(250);
                            break;
                        }
                        _events.ScheduleEvent(EVENT_TRIGGER_TRAP, 500);
                        break;
                    default:
                        break;
                }
            }
        }

    private:
        Unit* SelectTriggerTarget() const
        {
            if (!_armed)
                return nullptr;

            if (Creature* riplimb = me->FindNearestCreature(NPC_RIPLIMB, 2.5f, true))
                return riplimb;

            if (Creature* rageface = me->FindNearestCreature(NPC_RAGEFACE, 2.5f, true))
                return rageface;

            return me->SelectNearestPlayer(2.5f);
        }

        bool _armed;
        EventMap _events;
    };

    CreatureAI* GetAI(Creature* creature) const override
    {
        return GetFirelandsAI<npc_shannox_trapAI>(creature);
    }
};
}

void AddSC_boss_shannox()
{
    using namespace Firelands;
    using namespace Firelands::Shannox;

    new boss_shannox();
    new npc_shannox_riplimb();
    new npc_shannox_rageface();
    new npc_shannox_trap();
}
