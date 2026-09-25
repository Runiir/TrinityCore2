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
#include "CommonPredicates.h"
#include "GameObjectAI.h"
#include "GossipDef.h"
#include "GridNotifiers.h"
#include "MoveSpline.h"
#include "MoveSplineInit.h"
#include "PassiveAI.h"
#include "PhasingHandler.h"
#include "ScriptedCreature.h"
#include "SpellScript.h"
#include "SpellAuraEffects.h"
#include "SpellMgr.h"
#include "Transport.h"
#include "InstanceScript.h"
#include "MotionMaster.h"
#include "TemporarySummon.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "blackwing_descent.h"
#include "boss_nefarians_end.h"

namespace BlackwingDescent::NefariansEnd
{
Position const NefarianSummonPosition                           = { -166.655f,    -224.602f,    40.48163f, 0.0f };

struct npc_nefarians_end_lord_victor_nefarius : public PassiveAI
{
    npc_nefarians_end_lord_victor_nefarius(Creature* creature) : PassiveAI(creature), _instance(me->GetInstanceScript()), _started(false){ }

    void DoAction(int32 action) override
    {
        switch (action)
        {
            case ACTION_START_INTRO:
                if (!_started)
                {
                    Talk(SAY_INTRO_1);
                    DoSummon(BOSS_NEFARIAN, NefarianSummonPosition, 0, TEMPSUMMON_MANUAL_DESPAWN);
                    _events.ScheduleEvent(EVENT_TALK_INTRO_2, 22s);
                    _events.ScheduleEvent(EVENT_RAISE_ELEVATOR, 20s + 500ms);
                    _events.ScheduleEvent(EVENT_CAST_TRANSFORM_VISUAL, 26s + 700ms);
                    _started = true;
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
                case EVENT_TALK_INTRO_2:
                    Talk(SAY_INTRO_2);
                    _events.ScheduleEvent(EVENT_TALK_INTRO_3, 11s);
                    break;
                case EVENT_TALK_INTRO_3:
                    Talk(SAY_INTRO_3);
                    _instance->SetData(DATA_NEFARIANS_END_INTRO_DONE, 1);
                    me->DespawnOrUnsummon();
                    break;
                case EVENT_RAISE_ELEVATOR:
                    if (GameObject* elevator = _instance->GetGameObject(DATA_BLACKWING_ELEVATOR_ONYXIA))
                        elevator->SetGoState(GOState(GO_STATE_TRANSPORT_ACTIVE + AsUnderlyingType(TRANSPORT_STOP_FRAME_RAISED)));
                    break;
                case EVENT_CAST_TRANSFORM_VISUAL:
                    if (Creature* stalker = me->FindNearestCreature(NPC_INVISIBLE_STALKER_CATACLYSM_BOSS, 1.0f))
                    {
                        stalker->CastSpell(stalker, SPELL_INTRO_1_TRANSFORM_VISUAL);
                        stalker->DespawnOrUnsummon(2s + 400ms);
                    }
                    break;
                default:
                    break;
            }
        }
    }

private:
    EventMap _events;
    InstanceScript* _instance;
    bool _started;
};

struct npc_nefarians_end_animated_bone_warrior : public ScriptedAI
{
    npc_nefarians_end_animated_bone_warrior(Creature* creature) : ScriptedAI(creature), _instance(me->GetInstanceScript())
    {
        me->SetReactState(REACT_PASSIVE);
        me->AddUnitState(UNIT_STATE_IGNORE_PATHFINDING); // tempfix until mmaps for transports have arrived
    }

    void JustAppeared() override
    {
        DoCastSelf(SPELL_FULL_POWER_NO_REGEN);
        DoCastSelf(SPELL_ANIMATE_BONES);

        if (GameObject* elevator = _instance->GetGameObject(DATA_BLACKWING_ELEVATOR_ONYXIA))
        {
            if (TransportBase* transport = elevator->ToTransportBase())
            {
                transport->AddPassenger(me);
                transport->UpdatePassengerPosition(me->GetMap(), me, me->GetPositionX(), me->GetPositionY(), me->GetPositionZ(), me->GetOrientation(), true);
            }
        }

        me->UpdatePositionData();

        me->m_Events.AddEventAtOffset([this]()
        {
            me->SetReactState(REACT_AGGRESSIVE);
            if (me->IsAIEnabled())
                DoZoneInCombat();
        }, 800ms);
    }

    void JustDied(Unit* /*killer*/) override
    {
        me->DespawnOrUnsummon(4s);
    }

    void UpdateAI(uint32 /*diff*/) override
    {
        // Prevent any victim update while we are in feign death state
        if (me->HasFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE))
            return;

        if (!UpdateVictim())
            return;

        DoMeleeAttackIfReady();
    }
private:
    InstanceScript* _instance;
};

struct npc_nefarians_end_chromatic_prototype : public PassiveAI
{
    npc_nefarians_end_chromatic_prototype(Creature* creature) : PassiveAI(creature), _instance(me->GetInstanceScript()) { }

    void MovementInform(uint32 type, uint32 id) override
    {
        if (type != POINT_MOTION_TYPE)
            return;

        switch (id)
        {
            case POINT_JUMP_DOWN:
                _events.ScheduleEvent(EVENT_JUMP_DOWN_TO_PLATFORM, 1s + 200ms);
                break;
            default:
                break;
        }
    }

    void JustDied(Unit* /*killer*/) override
    {
        _instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, me);
    }

    void DoAction(int32 action) override
    {
        switch (action)
        {
            case ACTION_DISENGAGE_PLAYERS:
                me->InterruptNonMeleeSpells(true);
                me->SetHomePosition(me->GetPosition());
                me->GetThreatManager().ClearAllThreat();
                me->CombatStop();
                _events.Reset();
                _events.ScheduleEvent(EVENT_DISENGAGE_PLAYERS, 3s + 700ms);
                break;
            default:
                break;
        }
    }

    void UpdateAI(uint32 diff) override
    {
        _events.Update(diff);

        if (me->HasUnitState(UNIT_STATE_CASTING))
            return;

        while (uint32 eventId = _events.ExecuteEvent())
        {
            switch (eventId)
            {
                case EVENT_JUMP_DOWN_TO_PLATFORM:
                    if (GameObject* elevator = _instance->GetGameObject(DATA_BLACKWING_ELEVATOR_ONYXIA))
                    {
                        if (TransportBase* transport = elevator->ToTransportBase())
                        {
                            transport->AddPassenger(me);
                            transport->UpdatePassengerPosition(me->GetMap(), me, me->GetPositionX(), me->GetPositionY(), me->GetPositionZ(), me->GetOrientation(), true);
                            DoCastAOE(SPELL_JUMP_DOWN_TO_PLATFORM);
                        }
                    }
                    _events.ScheduleEvent(EVENT_READY_PROTOTYPE, 5s);
                    break;
                case EVENT_READY_PROTOTYPE:
                    DoZoneInCombat();
                    _instance->SendEncounterUnit(ENCOUNTER_FRAME_ENGAGE, me, FRAME_INDEX_CHROMATIC_PROTOTYPE);
                    DoCastSelf(SPELL_READY_UNARMED);
                    for (uint8 i = 0; i < 3; i++) // no idea what Blizzard was thinking here...
                        DoCastSelf(SPELL_DUMMY_NUKE);

                    _events.ScheduleEvent(EVENT_DUMMY_NUKE, 1s);
                    _events.ScheduleEvent(EVENT_BLAST_NOVA, 3s + 500ms);
                    break;
                case EVENT_DUMMY_NUKE:
                    DoCastSelf(SPELL_DUMMY_NUKE);
                    _events.Repeat(1s);
                    break;
                case EVENT_BLAST_NOVA:
                    DoCastAOE(SPELL_BLAST_NOVA);
                    _events.Repeat(13s);
                    break;
                case EVENT_DISENGAGE_PLAYERS:
                    _instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, me);
                    me->DespawnOrUnsummon(5s);
                    break;
                default:
                    break;
            }
        }
    }

private:
    InstanceScript* _instance;
    EventMap _events;
};

struct npc_nefarians_end_shadowblaze : public NullCreatureAI
{
    npc_nefarians_end_shadowblaze(Creature* creature) : NullCreatureAI(creature), _summonedByController(false), _instance(me->GetInstanceScript()) { }

    void JustAppeared() override
    {
        if (me->GetEntry() == NPC_SHADOWBLAZE_FLASHPOINT)
            DoCastSelf(SPELL_BRUSHFIRE_FLASHPOINT_CONTROL);
        else
            DoCastSelf(SPELL_BRUSHFIRE_CHECK_VALID_LOCATION);

        DoCastSelf(SPELL_BRUSHFIRE_BURN_AURA);
        DoCastSelf(SPELL_BRUSHFIRE_GROWTH);
    }

    void IsSummonedBy(Unit* summoner) override
    {
        if (summoner->GetEntry() == NPC_SHADOWBLAZE_FLASHPOINT)
            _summonedByController = true;

        if (Creature* nefarian = _instance->GetCreature(DATA_NEFARIANS_END))
            if (nefarian->IsAIEnabled())
                nefarian->AI()->JustSummoned(me);
    }

    void SpellHitTarget(WorldObject* target, SpellInfo const* spell) override
    {
        switch (spell->Id)
        {
            case SPELL_BRUSHFIRE_CHECK_VALID_LOCATION:
                _controllerStalkerPosition = target->GetPosition();
                break;
            default:
                break;
        }
    }

    void DoAction(int32 action) override
    {
        switch (action)
        {
            case ACTION_SPREAD_FLAMES:
            {
                float z = me->GetPositionZ();
                if (z >= 13.f) // tempfix to avoid flames spawn in the air when a controller gets spawned on a pillar
                    z = 8.472f;

                if (!_summonedByController && me->GetEntry() != NPC_SHADOWBLAZE_FLASHPOINT)
                {
                    // Select a destination that will serve as our offset selection helper
                    float angle = me->GetAngle(_controllerStalkerPosition) - float(M_PI / 2.5f);
                    float compareX = me->GetPositionX() + std::cos(angle) * 20.f;
                    float compareY = me->GetPositionY() + std::sin(angle) * 20.f;
                    Position comparePos = Position(compareX, compareY);

                    Position summonPos = me->GetPosition();
                    // Select the closest nearby location for summoning
                    float offsets[3] = { -5.f, 0.f, 5.f };

                    for (uint8 i = 0; i < 3; i++)
                    {
                        float x = me->GetPositionX() + offsets[i];
                        for (uint8 u = 0; u < 3; u++)
                        {
                            float y = me->GetPositionY() + offsets[u];
                            if (Position(x, y).GetExactDist2d(comparePos) < summonPos.GetExactDist2d(comparePos))
                                summonPos = Position(x, y);
                        }
                    }

                    me->CastSpell(Position{ summonPos.GetPositionX(), summonPos.GetPositionY(), z, 0.f }, SPELL_BRUSHFIRE_SUMMON, true);
                }
                else
                {
                    if (me->GetEntry() == NPC_SHADOWBLAZE_FLASHPOINT)
                    {
                        me->CastSpell(Position{ me->GetPositionX() - 5.f, me->GetPositionY(), z, 0.f }, SPELL_BRUSHFIRE_SUMMON, true);
                        me->CastSpell(Position{ me->GetPositionX(), me->GetPositionY() + 5.f, z, 0.f }, SPELL_BRUSHFIRE_SUMMON, true);
                    }
                    else if (_summonedByController)
                    {
                        for (uint8 i = 0; i < 2; i++)
                        {
                            float x = me->GetPositionX() + 5.f;
                            float y = me->GetPositionY() + 5.f;
                            me->CastSpell(Position{ x, y, z, 0.f }, SPELL_BRUSHFIRE_SUMMON, true);
                        }
                    }
                }
                break;
            }
            default:
                break;
        }
    }

private:
    Position _controllerStalkerPosition;
    bool _summonedByController;
    InstanceScript* _instance;
};

struct go_nefarians_end_orb_of_culmination : public GameObjectAI
{
    go_nefarians_end_orb_of_culmination(GameObject* go) : GameObjectAI(go), _instance(me->GetInstanceScript()) { }

    bool GossipSelect(Player* player, uint32 /*menuId*/, uint32 /*gossipListId*/) override
    {
        if (Creature* stalker = _instance->GetCreature(DATA_INVISIBLE_STALKER))
            stalker->RemoveAllAuras();

        if (Creature* nefarius = _instance->GetCreature(DATA_LORD_VICTOR_NEFARIUS_NEFARIANS_END))
            if (nefarius->IsAIEnabled())
                nefarius->AI()->DoAction(ACTION_START_INTRO);

        player->PlayerTalkClass->SendCloseGossip();
        me->DespawnOrUnsummon();

        return false;
    }

private:
    InstanceScript* _instance;
};
}

void AddSC_boss_nefarians_end_adds()
{
    using namespace BlackwingDescent;
    using namespace BlackwingDescent::NefariansEnd;
    RegisterBlackwingDescentCreatureAI(npc_nefarians_end_lord_victor_nefarius);
    RegisterBlackwingDescentCreatureAI(npc_nefarians_end_animated_bone_warrior);
    RegisterBlackwingDescentCreatureAI(npc_nefarians_end_chromatic_prototype);
    RegisterBlackwingDescentCreatureAI(npc_nefarians_end_shadowblaze);
    RegisterGameObjectAI(go_nefarians_end_orb_of_culmination);
}
