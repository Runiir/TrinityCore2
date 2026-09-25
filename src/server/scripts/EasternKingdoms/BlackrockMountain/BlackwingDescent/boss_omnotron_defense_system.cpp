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
Position const FirstGolemPatrolStartPoint           = { -324.665f,  -398.085f,  213.8214f };
Position const LordVictorNefariusSummonPosition     = { -302.9167f, -350.4167f, 220.5673f, 4.537856f };

struct GolemInfo
{
    uint8 ActivateTextId;
    uint8 ShieldTextId;
};

std::unordered_map<uint32, GolemInfo> _golemInfoMap =
{
    { NPC_ELECTRON,     { SAY_ACTIVATE_ELECTRON,    SAY_SHIELD_ELECTRON     } },
    { NPC_MAGMATRON,    { SAY_ACTIVATE_MAGMATRON,   SAY_SHIELD_MAGMATRON    } },
    { NPC_ARCANOTRON,   { SAY_ACTIVATE_ARCANOTRON,  SAY_SHIELD_ARCANOTRON   } },
    { NPC_TOXITRON,     { SAY_ACTIVATE_TOXITRON,    SAY_SHIELD_TOXITRON     } }
};

struct boss_omnotron_defense_system : public BossAI
{
    boss_omnotron_defense_system(Creature* creature) : BossAI(creature, DATA_OMNOTRON_DEFENSE_SYSTEM)
    {
        Initialize();
    }

    void Initialize()
    {
        me->SetReactState(REACT_PASSIVE);
        _activatedGolemEntry = 0;
    }

    void Reset() override
    {
        Initialize();
        if (instance->GetBossState(DATA_OMNOTRON_DEFENSE_SYSTEM) == DONE)
            return;

        _Reset();
        me->SummonCreatureGroup(SUMMON_GROUP_GOLEMS);
        events.ScheduleEvent(EVENT_LINK_GOLEM_HEALTH, 5s);
        events.ScheduleEvent(EVENT_POWER_UP_FIRST_GOLEM, 10s);
    }

    void JustEngagedWith(Unit* /*target*/) override { }

    void JustSummoned(Creature* summon) override
    {
        switch (summon->GetEntry())
        {
            case NPC_ELECTRON:
            case NPC_MAGMATRON:
            case NPC_TOXITRON:
            case NPC_ARCANOTRON:
                _golemGuidVector.push_back(summon->GetGUID());
                break;
            default:
                summons.Summon(summon);
                break;
        }
    }

    ObjectGuid GetGUID(int32 type) const override
    {
        switch (type)
        {
            case DATA_NEXT_GOLEM_IN_QUEUE:
                return _nextGolemGUID;
            default:
                return ObjectGuid::Empty;
        }

        return ObjectGuid::Empty;
    }

    void SetGUID(ObjectGuid const& guid, int32 type) override
    {
        if (type == DATA_SAY_GOLEM_SHIELD)
            if (Creature* golem = ObjectAccessor::GetCreature(*me, guid))
                Talk(_golemInfoMap[golem->GetEntry()].ShieldTextId);
    }

    void DoAction(int32 action) override
    {
        switch (action)
        {
            case ACTION_GOLEM_ACTIVATED:
                if (instance->GetBossState(DATA_OMNOTRON_DEFENSE_SYSTEM) == IN_PROGRESS)
                {
                    if (Creature* golem = ObjectAccessor::GetCreature(*me, _nextGolemGUID))
                    {
                        _activatedGolemEntry = golem->GetEntry();
                        events.ScheduleEvent(EVENT_TALK_ACTIVATED_GOLEM, 1s + 500ms);
                        golem->CastSpell(golem, SPELL_INVISIBILITY_AND_STEALTH_DETECTION, true);
                        golem->CastSpell(golem, SPELL_ACTIVATED);
                        instance->SendEncounterUnit(ENCOUNTER_FRAME_ENGAGE, golem, 1);
                    }

                    SelectNextGolemGUID();
                    DoCastSelf(SPELL_CONTROLLER_RECHARGE, true);
                }
                break;
            case ACTION_START_ENCOUNTER:
                instance->SetBossState(DATA_OMNOTRON_DEFENSE_SYSTEM, IN_PROGRESS);
                instance->DoUpdateWorldState(WORLD_STATE_ID_STATIC_SHOCK, 0);
                instance->DoUpdateWorldState(WORLD_STATE_ID_POISON_BOMB, 0);
                instance->DoUpdateWorldState(WORLD_STATE_ID_ARCANE_ANNIHILATOR, 0);
                instance->DoUpdateWorldState(WORLD_STATE_ID_FLAMETHROWER, 0);

                if (IsHeroic())
                    DoSummon(NPC_LORD_VICTOR_NEFARIUS_OMNOTRON, LordVictorNefariusSummonPosition, 0, TEMPSUMMON_MANUAL_DESPAWN);

                for (ObjectGuid guid : _golemGuidVector)
                    if (Creature* golem = ObjectAccessor::GetCreature(*me, guid))
                        golem->AI()->DoZoneInCombat();

                // Since we blocked the first action call with our first golem we call it right away now to continue the cycle
                DoAction(ACTION_GOLEM_ACTIVATED);
                break;
            case ACTION_STOP_ENCOUNTER:
                for (ObjectGuid guid : _golemGuidVector)
                {
                    if (Creature* golem = ObjectAccessor::GetCreature(*me, guid))
                    {
                        instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, golem);
                        golem->DespawnOrUnsummon();
                    }
                }

                instance->SetBossState(DATA_OMNOTRON_DEFENSE_SYSTEM, FAIL);
                RemoveDebuffsFromRaid();
                summons.DespawnAll();
                _DespawnAtEvade();
                break;
            case ACTION_FINISH_ENCOUNTER:
                if (instance->GetBossState(DATA_OMNOTRON_DEFENSE_SYSTEM) != DONE)
                {
                    Talk(SAY_POWERING_DOWN);
                    _JustDied();
                    for (ObjectGuid guid : _golemGuidVector)
                        if (Creature* golem = ObjectAccessor::GetCreature(*me, guid))
                            instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, golem);

                    RemoveDebuffsFromRaid();
                }
                break;
            case ACTION_SAY_ACQUIRING_TARGET:
                Talk(SAY_ACQUIRING_TARGET);
                break;
            default:
                break;
        }
    }

    void UpdateAI(uint32 diff) override
    {
        events.Update(diff);

        while (uint32 eventId = events.ExecuteEvent())
        {
            switch (eventId)
            {
                case EVENT_LINK_GOLEM_HEALTH:
                    for (ObjectGuid guid : _golemGuidVector)
                        if (Creature* golem = ObjectAccessor::GetCreature(*me, guid))
                            golem->CastSpell(golem, SPELL_SHARED_HEALTH, true);
                    break;
                case EVENT_POWER_UP_FIRST_GOLEM:
                    // Randomize our golem order for each encounter
                    Trinity::Containers::RandomShuffle(_golemGuidVector);
                    SelectNextGolemGUID();
                    DoCastSelf(SPELL_CONTROLLER_RECHARGE);
                    break;
                case EVENT_TALK_ACTIVATED_GOLEM:
                    Talk(_golemInfoMap[_activatedGolemEntry].ActivateTextId);
                    break;
                default:
                    break;
            }
        }
    }

private:
    GuidVector _golemGuidVector;
    ObjectGuid _nextGolemGUID;
    uint32 _activatedGolemEntry;

    // Selects the ObjectGuid for the next Golem
    void SelectNextGolemGUID()
    {
        _nextGolemGUID = _golemGuidVector.front();
        _golemGuidVector.erase(_golemGuidVector.begin());
        _golemGuidVector.push_back(_nextGolemGUID);
    }

    void RemoveDebuffsFromRaid()
    {
        instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_LIGHTNING_CONDUCTOR);
        instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_SOAKED_IN_POISON);
        instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_SHADOW_CONDUCTOR);
    }
};

struct npc_omnotron_electron : public ScriptedAI
{
    npc_omnotron_electron(Creature* creature) : ScriptedAI(creature), _instance(me->GetInstanceScript())
    {
        Initialize();
    }

    void Initialize()
    {
        me->SetReactState(REACT_PASSIVE);
    }

    void JustEngagedWith(Unit* /*who*/) override
    {
        if (_instance->GetBossState(DATA_OMNOTRON_DEFENSE_SYSTEM) != IN_PROGRESS)
        {
            if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
                omnotron->AI()->DoAction(ACTION_START_ENCOUNTER);
        }
    }

    void EnterEvadeMode(EvadeReason /*why*/) override
    {
        _EnterEvadeMode();

        if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
            omnotron->AI()->DoAction(ACTION_STOP_ENCOUNTER);
    }

    void JustDied(Unit* /*killer*/) override
    {
        if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
            omnotron->AI()->DoAction(ACTION_FINISH_ENCOUNTER);

        me->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
    }

    void MovementInform(uint32 type, uint32 pointId) override
    {
        if (type != POINT_MOTION_TYPE)
            return;

        if (pointId == POINT_START_WAYPOINTS)
        {
            me->GetMotionMaster()->MovePath(BOSS_OMNOTRON * 100, true);
            me->SetWalk(true);
        }
    }

    void DoAction(int32 action) override
    {
        switch (action)
        {
            case ACTION_ACTIVATE_GOLEM:
                me->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
                me->SetReactState(REACT_AGGRESSIVE);
                me->RemoveAurasDueToSpell(SPELL_INACTIVE);
                me->RemoveAurasDueToSpell(SPELL_POWERED_DOWN);

                if (_instance->GetBossState(DATA_OMNOTRON_DEFENSE_SYSTEM) != IN_PROGRESS)
                {
                    me->SetWalk(true);
                    me->GetMotionMaster()->MovePoint(POINT_START_WAYPOINTS, FirstGolemPatrolStartPoint);
                }
                else
                    DoZoneInCombat();

                // Golem is online, time to inform the controller about it
                if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
                    omnotron->AI()->DoAction(ACTION_GOLEM_ACTIVATED);
                break;
            case ACTION_DEACTIVATE_GOLEM:
                me->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
                _events.Reset();
                break;
            default:
                break;
        }
    }

    void SpellHit(WorldObject* /*caster*/, SpellInfo const* spell) override
    {
        if (spell->Id == SPELL_ACTIVATED)
        {
            _events.ScheduleEvent(EVENT_LIGHTNING_CONDUCTOR, 16s);
            _events.ScheduleEvent(EVENT_ELECTRICAL_DISCHARGE, 6s);
            _events.ScheduleEvent(EVENT_UNSTABLE_SHIELD, IsHeroic() ? 40s : 50s);
        }
    }

    void SpellHitTarget(WorldObject* /*target*/, SpellInfo const* spell) override
    {
        if (spell->Id == SPELL_LIGHTNING_CONDUCTOR)
            if (IsHeroic())
                if (Creature* nefarius = _instance->GetCreature(DATA_LORD_VICTOR_NEFARIUS_OMNOTRON))
                    nefarius->AI()->DoAction(ACTION_CAST_SHADOW_INFUSION);
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
                case EVENT_LIGHTNING_CONDUCTOR:
                    if (Unit* target = SelectTarget(SELECT_TARGET_RANDOM, 0, 0, true))
                    {
                        Talk(SAY_ANNOUNCE_ABILITY_1, target);
                        DoCast(target, SPELL_LIGHTNING_CONDUCTOR);
                        _events.Repeat(21s);
                    }
                    break;
                case EVENT_ELECTRICAL_DISCHARGE:
                    // The trigger (95499, registered spell script) picks one
                    // random enemy and casts the chain on it. Casting 79879
                    // without an explicit target fell back to the victim, so
                    // every discharge started on the tank instead of a random
                    // raid member (omnotron_defense_system ledger:
                    // electrical_discharge_target).
                    DoCastAOE(SPELL_ELECTRICAL_DISCHARGE_TRIGGER);
                    _events.Repeat(6s);
                    break;
                case EVENT_UNSTABLE_SHIELD:
                    DoCastSelf(SPELL_UNSTABLE_SHIELD);
                    Talk(SAY_ANNOUNCE_ABILITY_2);
                    if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
                        omnotron->AI()->SetGUID(me->GetGUID(), DATA_SAY_GOLEM_SHIELD);
                    break;
                default:
                    break;
            }
        }

        DoMeleeAttackIfReady();
    }

private:
    EventMap _events;
    InstanceScript* _instance;
};

struct npc_omnotron_magmatron : public ScriptedAI
{
    npc_omnotron_magmatron(Creature* creature) : ScriptedAI(creature), _instance(me->GetInstanceScript())
    {
        Initialize();
    }

    void Initialize()
    {
        me->SetReactState(REACT_PASSIVE);
    }

    void JustEngagedWith(Unit* /*who*/) override
    {
        if (_instance->GetBossState(DATA_OMNOTRON_DEFENSE_SYSTEM) != IN_PROGRESS)
        {
            if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
                omnotron->AI()->DoAction(ACTION_START_ENCOUNTER);
        }
    }

    void EnterEvadeMode(EvadeReason /*why*/) override
    {
        _EnterEvadeMode();

        if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
            omnotron->AI()->DoAction(ACTION_STOP_ENCOUNTER);
    }

    void JustDied(Unit* /*killer*/) override
    {
        if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
            omnotron->AI()->DoAction(ACTION_FINISH_ENCOUNTER);

        me->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
    }

    void MovementInform(uint32 type, uint32 pointId) override
    {
        if (type != POINT_MOTION_TYPE)
            return;

        if (pointId == POINT_START_WAYPOINTS)
        {
            me->GetMotionMaster()->MovePath(BOSS_OMNOTRON * 100, true);
            me->SetWalk(true);
        }
    }

    void DoAction(int32 action) override
    {
        switch (action)
        {
            case ACTION_ACTIVATE_GOLEM:
                me->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
                me->SetReactState(REACT_AGGRESSIVE);
                me->RemoveAurasDueToSpell(SPELL_INACTIVE);
                me->RemoveAurasDueToSpell(SPELL_POWERED_DOWN);

                if (_instance->GetBossState(DATA_OMNOTRON_DEFENSE_SYSTEM) != IN_PROGRESS)
                {
                    me->SetWalk(true);
                    me->GetMotionMaster()->MovePoint(POINT_START_WAYPOINTS, FirstGolemPatrolStartPoint);
                }
                else
                    DoZoneInCombat();

                // Golem is online, time to inform the controller about it
                if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
                    omnotron->AI()->DoAction(ACTION_GOLEM_ACTIVATED);
                break;
            case ACTION_DEACTIVATE_GOLEM:
                me->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
                _events.Reset();
                break;
            default:
                break;
        }
    }

    void SpellHit(WorldObject* /*caster*/, SpellInfo const* spell) override
    {
        if (spell->Id == SPELL_ACTIVATED)
        {
            _events.ScheduleEvent(EVENT_INCINERATION_SECURITY_MEASURE, 10s + 500ms);
            _events.ScheduleEvent(EVENT_ACQUIRING_TARGET, 21s);
            _events.ScheduleEvent(EVENT_BARRIER, IsHeroic() ? 40s : 50s);
        }
    }

    void SpellHitTarget(WorldObject* target, SpellInfo const* spell) override
    {
        if (spell->Id == SPELL_ACQUIRING_TARGET && target)
        {
            Talk(SAY_ANNOUNCE_ABILITY_1, target);
            if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
                omnotron->AI()->DoAction(ACTION_SAY_ACQUIRING_TARGET);

            if (Creature* nefarius = _instance->GetCreature(DATA_LORD_VICTOR_NEFARIUS_OMNOTRON))
                nefarius->AI()->DoAction(ACTION_CAST_ENCASING_SHADOWS);
        }
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
                case EVENT_INCINERATION_SECURITY_MEASURE:
                    DoCastAOE(SPELL_INCINERATION_SECURITY_MEASURE);
                    _events.Repeat(26s + 500ms);
                    break;
                case EVENT_ACQUIRING_TARGET:
                    DoCastAOE(SPELL_ACQUIRING_TARGET, true);
                    // Two Acquiring Targets per activation (Wowhead; DBM
                    // DarkIronGolemCouncil.lua r20241103125714 repeats 40 s on
                    // normal). A 26 s repeat gave a third Flamethrower inside
                    // the 90 s normal activation. Heroic keeps 26 s: two casts
                    // in its 60 s activation (DBM measures 27 s).
                    _events.Repeat(IsHeroic() ? 26s : 40s);
                    break;
                case EVENT_BARRIER:
                    DoCastSelf(SPELL_BARRIER);
                    if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
                        omnotron->AI()->SetGUID(me->GetGUID(), DATA_SAY_GOLEM_SHIELD);
                    break;
                default:
                    break;
            }
        }

        DoMeleeAttackIfReady();
    }

private:
    EventMap _events;
    InstanceScript* _instance;
};

struct npc_omnotron_toxitron : public ScriptedAI
{
    npc_omnotron_toxitron(Creature* creature) : ScriptedAI(creature), _instance(me->GetInstanceScript())
    {
        Initialize();
    }

    void Initialize()
    {
        me->SetReactState(REACT_PASSIVE);
    }

    void JustEngagedWith(Unit* /*who*/) override
    {
        if (_instance->GetBossState(DATA_OMNOTRON_DEFENSE_SYSTEM) != IN_PROGRESS)
        {
            if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
                omnotron->AI()->DoAction(ACTION_START_ENCOUNTER);
        }
    }

    void EnterEvadeMode(EvadeReason /*why*/) override
    {
        _EnterEvadeMode();

        if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
            omnotron->AI()->DoAction(ACTION_STOP_ENCOUNTER);
    }

    void JustDied(Unit* /*killer*/) override
    {
        if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
            omnotron->AI()->DoAction(ACTION_FINISH_ENCOUNTER);

        me->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
    }

    void MovementInform(uint32 type, uint32 pointId) override
    {
        if (type != POINT_MOTION_TYPE)
            return;

        if (pointId == POINT_START_WAYPOINTS)
        {
            me->GetMotionMaster()->MovePath(BOSS_OMNOTRON * 100, true);
            me->SetWalk(true);
        }
    }

    void DoAction(int32 action) override
    {
        switch (action)
        {
            case ACTION_ACTIVATE_GOLEM:
                me->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
                me->SetReactState(REACT_AGGRESSIVE);
                me->RemoveAurasDueToSpell(SPELL_INACTIVE);
                me->RemoveAurasDueToSpell(SPELL_POWERED_DOWN);

                if (_instance->GetBossState(DATA_OMNOTRON_DEFENSE_SYSTEM) != IN_PROGRESS)
                {
                    me->SetWalk(true);
                    me->GetMotionMaster()->MovePoint(POINT_START_WAYPOINTS, FirstGolemPatrolStartPoint);
                }
                else
                    DoZoneInCombat();

                // Golem is online, time to inform the controller about it
                if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
                    omnotron->AI()->DoAction(ACTION_GOLEM_ACTIVATED);
                break;
            case ACTION_DEACTIVATE_GOLEM:
                me->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
                _events.Reset();
                break;
            default:
                break;
        }
    }

    void SpellHit(WorldObject* /*caster*/, SpellInfo const* spell) override
    {
        if (spell->Id == SPELL_ACTIVATED)
        {
            _poisonProtocolCasts = 0;
            _events.ScheduleEvent(EVENT_CHEMICAL_BOMB, 27s);
            _events.ScheduleEvent(EVENT_POISON_PROTOCOL, 16s);
            // Same shield point as the other three constructs: 50 s normal,
            // 40 s heroic (DBM DarkIronGolemCouncil.lua r20241103125714 warns
            // 10 s ahead at 40/30 s; Wowhead reports 40 s on heroic). The old
            // 40/30 s raised Poison Soaked Shell 10 s early.
            _events.ScheduleEvent(EVENT_POISON_SOAKED_SHELL, IsHeroic() ? 40s : 50s);
        }
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
                case EVENT_CHEMICAL_BOMB:
                    if (Unit* target = SelectTarget(SELECT_TARGET_RANDOM, 0, 0, true))
                        DoCast(target, SPELL_CHEMICAL_BOMB);
                    _events.Repeat(30s);
                    break;
                case EVENT_POISON_PROTOCOL:
                    me->StopMoving();
                    DoCastSelf(SPELL_POISON_PROTOCOL);
                    // Two Poison Protocols per activation (Wowhead; DBM repeats
                    // 45 s on normal and 25 s on heroic). Scheduling it once
                    // dropped the second wave of Poison Bombs.
                    if (++_poisonProtocolCasts < 2)
                        _events.Repeat(IsHeroic() ? 25s : 45s);
                    break;
                case EVENT_POISON_SOAKED_SHELL:
                    DoCastSelf(SPELL_POISON_SOAKED_SHELL);
                    Talk(SAY_ANNOUNCE_ABILITY_1);
                    if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
                        omnotron->AI()->SetGUID(me->GetGUID(), DATA_SAY_GOLEM_SHIELD);
                    break;
                default:
                    break;
            }
        }

        DoMeleeAttackIfReady();
    }

private:
    EventMap _events;
    InstanceScript* _instance;
    uint8 _poisonProtocolCasts = 0;
};

struct npc_omnotron_arcanotron : public ScriptedAI
{
    npc_omnotron_arcanotron(Creature* creature) : ScriptedAI(creature), _instance(me->GetInstanceScript())
    {
        Initialize();
    }

    void Initialize()
    {
        me->SetReactState(REACT_PASSIVE);
        me->MakeInterruptable(false);
    }

    void JustEngagedWith(Unit* /*who*/) override
    {
        if (_instance->GetBossState(DATA_OMNOTRON_DEFENSE_SYSTEM) != IN_PROGRESS)
        {
            if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
                omnotron->AI()->DoAction(ACTION_START_ENCOUNTER);
        }
    }

    void EnterEvadeMode(EvadeReason /*why*/) override
    {
        _EnterEvadeMode();

        if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
            omnotron->AI()->DoAction(ACTION_STOP_ENCOUNTER);
    }

    void JustDied(Unit* /*killer*/) override
    {
        if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
            omnotron->AI()->DoAction(ACTION_FINISH_ENCOUNTER);

        me->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
    }

    void MovementInform(uint32 type, uint32 pointId) override
    {
        if (type != POINT_MOTION_TYPE)
            return;

        if (pointId == POINT_START_WAYPOINTS)
        {
            me->GetMotionMaster()->MovePath(BOSS_OMNOTRON * 100, true);
            me->SetWalk(true);
        }
    }

    void DoAction(int32 action) override
    {
        switch (action)
        {
            case ACTION_ACTIVATE_GOLEM:
                me->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
                me->SetReactState(REACT_AGGRESSIVE);
                me->RemoveAurasDueToSpell(SPELL_INACTIVE);
                me->RemoveAurasDueToSpell(SPELL_POWERED_DOWN);

                if (_instance->GetBossState(DATA_OMNOTRON_DEFENSE_SYSTEM) != IN_PROGRESS)
                {
                    me->SetWalk(true);
                    me->GetMotionMaster()->MovePoint(POINT_START_WAYPOINTS, FirstGolemPatrolStartPoint);
                }
                else
                    DoZoneInCombat();

                // Golem is online, time to inform the controller about it
                if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
                    omnotron->AI()->DoAction(ACTION_GOLEM_ACTIVATED);
                break;
            case ACTION_DEACTIVATE_GOLEM:
                me->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
                me->MakeInterruptable(false);
                _events.Reset();
                break;
            default:
                break;
        }
    }

    void SpellHit(WorldObject* /*caster*/, SpellInfo const* spell) override
    {
        if (spell->Id == SPELL_ACTIVATED)
        {
            _events.ScheduleEvent(EVENT_POWER_GENERATOR, 16s);
            _events.ScheduleEvent(EVENT_ARCANE_ANNIHILATION, 3s + 300ms);
            _events.ScheduleEvent(EVENT_POWER_CONVERSION, IsHeroic() ? 40s : 50s);
        }
    }

    void OnSpellCastFinished(SpellInfo const* spell, SpellFinishReason /*reason*/) override
    {
        if (spell->Id == SPELL_ARCANE_ANNIHILATION)
            me->MakeInterruptable(false);
    }

    void SpellHitTarget(WorldObject* /*target*/, SpellInfo const* spell) override
    {
        if (spell->Id == SPELL_ARCANE_ANNIHILATION)
            if (!_instance->instance->GetWorldStateValue(WORLD_STATE_ID_ARCANE_ANNIHILATOR))
                _instance->DoUpdateWorldState(WORLD_STATE_ID_ARCANE_ANNIHILATOR, 1);
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
                case EVENT_POWER_GENERATOR:
                    DoCastAOE(SPELL_POWER_GENERATOR);
                    _events.Repeat(20s);
                    break;
                case EVENT_ARCANE_ANNIHILATION:
                    me->MakeInterruptable(true);
                    if (!Is25ManRaid())
                    {
                        if (Unit* target = SelectTarget(SELECT_TARGET_RANDOM, 0, 100.0f, true))
                            DoCast(target, SPELL_ARCANE_ANNIHILATION);
                    }
                    else
                        DoCastAOE(SPELL_ARCANE_ANNIHILATION);
                    _events.Repeat(6s, 7s);
                    break;
                case EVENT_POWER_CONVERSION:
                    DoCastSelf(SPELL_POWER_CONVERSION);
                    Talk(SAY_ANNOUNCE_ABILITY_1);
                    if (Creature* omnotron = _instance->GetCreature(DATA_OMNOTRON_DEFENSE_SYSTEM))
                        omnotron->AI()->SetGUID(me->GetGUID(), DATA_SAY_GOLEM_SHIELD);
                    break;
                default:
                    break;
            }
        }

        DoMeleeAttackIfReady();
    }

private:
    EventMap _events;
    InstanceScript* _instance;
};
}

void AddSC_boss_omnotron_defense_system()
{
    using namespace BlackwingDescent;
    using namespace BlackwingDescent::OmnotronDefenseSystem;
    RegisterBlackwingDescentCreatureAI(boss_omnotron_defense_system);
    RegisterBlackwingDescentCreatureAI(npc_omnotron_electron);
    RegisterBlackwingDescentCreatureAI(npc_omnotron_magmatron);
    RegisterBlackwingDescentCreatureAI(npc_omnotron_toxitron);
    RegisterBlackwingDescentCreatureAI(npc_omnotron_arcanotron);
    AddSC_boss_omnotron_defense_system_spells();
}
