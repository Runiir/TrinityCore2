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
#include "GameObject.h"
#include "InstanceScript.h"
#include "Map.h"
#include "MotionMaster.h"
#include "PassiveAI.h"
#include "ScriptedCreature.h"
#include "SpellMgr.h"
#include "TemporarySummon.h"
#include <cmath>
#include <list>

// Maloriak's helper creatures (Flash Freeze, the experiments, Magma Jet, Lord
// Victor Nefarius, Vile Swill), split from boss_maloriak.cpp by concern.
// AddSC_boss_maloriak() calls AddSC_boss_maloriak_minions().
namespace BlackwingDescent::Maloriak
{
enum MinionEvents
{
    // Experiments
    EVENT_LEAP_OUT_OF_CHAMBER = 1,
    EVENT_REND,

    // Lord Victor Nefarius
    EVENT_MOCK_MALORIAK,
    EVENT_THROW_BLACK_BOTTLE,
    EVENT_LAND,
    EVENT_SAY_MALORIAK_DEAD,
    EVENT_MASTER_ADVENTURER_AWARD,
    EVENT_TELEPORT_AWAY,

    // Vile Swill
    EVENT_DARK_SLUDGE
};

enum MinionMovePoints
{
    // Experiments
    POINT_GROUND    = 1,

    // Lord Victor Nefarius
    POINT_LAND      = 1
};

enum MinionTexts
{
    // Lord Victor Nefarius
    SAY_MOCK_MALORIAK       = 0,
    SAY_THROW_BLACK_BOTTLE  = 1,
    SAY_ANNOUNCE_BLACK_VIAL = 2,
    SAY_MALORIAK_DEAD       = 3
};

Position const LordVictorNefariusLandPosition = { -105.9514f, -494.0278f, 73.44659f };

struct npc_maloriak_flash_freeze : public NullCreatureAI
{
    npc_maloriak_flash_freeze(Creature* creature) : NullCreatureAI(creature) { }

    void JustAppeared() override
    {
        me->ApplySpellImmune(0, IMMUNITY_ID, sSpellMgr->GetSpellIdForDifficulty(SPELL_GROWTH_CATALYST, me), true);
        DoCastSelf(SPELL_FLASH_FREEZE_VISUAL);
        Creature* creature = me;
        me->m_Events.AddEventAtOffset([creature]() { creature->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE); }, 1s);
    }

    void JustDied(Unit* /*killer*/) override
    {
        if (TempSummon* summon = me->ToTempSummon())
            if (Unit* owner = summon->GetSummoner())
                owner->CastSpell(owner, SPELL_FLASH_FREEZE_DUMMY, true);

        DoCastAOE(SPELL_SHATTER, true);
        me->DespawnOrUnsummon(4s);
    }
};

struct npc_maloriak_experiment : public ScriptedAI
{
    npc_maloriak_experiment(Creature* creature) : ScriptedAI(creature)
    {
        Initialize();
    }

    void Initialize()
    {
        me->SetReactState(REACT_PASSIVE);
        me->AddUnitMovementFlag(MOVEMENTFLAG_DISABLE_GRAVITY);
    }

    void JustDied(Unit* /*killer*/) override
    {
        me->DespawnOrUnsummon(5s);
    }

    void DoAction(int32 action) override
    {
        switch (action)
        {
            case ACTION_RELEASE_EXPERIMENT:
            {
                me->RemoveAurasDueToSpell(SPELL_DROWNED_STATE);
                me->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);

                // The chambers have super weird spawn points so FindNearestGameObject wont work here.
                std::list<GameObject*> gameObjectList;
                uint32 entry = me->GetEntry() == NPC_ABERRATION ? GO_GROWTH_CHAMBER : GO_LARGE_GROWTH_CHAMBER;
                me->GetGameObjectListWithEntryInGrid(gameObjectList, entry, 2.0f);
                float z = me->GetPositionZ();

                if (me->GetEntry() == NPC_ABERRATION)
                {
                    gameObjectList.remove_if([z](GameObject const* go)
                    {
                        if (go->GetPositionZ() > z)
                            return true;

                        if (std::abs(go->GetPositionZ() - z) > 7.0f)
                            return true;

                        return false;
                    });
                }

                if (gameObjectList.empty())
                    break;

                for (GameObject* chamber : gameObjectList)
                {
                    chamber->SetFlag(GAMEOBJECT_FLAGS, GO_FLAG_IN_USE);
                    chamber->SetGoState(GO_STATE_ACTIVE_ALTERNATIVE);
                }

                _events.ScheduleEvent(EVENT_LEAP_OUT_OF_CHAMBER, 1s + 700ms);
                break;
            }
            default:
                break;
        }
    }

    void MovementInform(uint32 motionType, uint32 pointId) override
    {
        if (motionType != EFFECT_MOTION_TYPE)
            return;

        switch (pointId)
        {
            case POINT_GROUND:
                me->SetDisableGravity(false);
                me->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_IMMUNE_TO_PC);
                me->SetReactState(REACT_AGGRESSIVE);
                DoZoneInCombat();
                DoCastSelf(SPELL_GROWTH_CATALYST);
                // 10N WCL (VL3fW9wNm2PRJDYt fight 13, MxFq7TRbvnjGY1hJ fight 34):
                // each Prime Subject casts Rend (78034, a stacking bleed on its
                // victim) 14.1-16.5 s after landing, then 9.7-16.2 s apart.
                if (me->GetEntry() == NPC_PRIME_SUBJECT && GetDifficulty() == RAID_DIFFICULTY_10MAN_NORMAL)
                    _events.ScheduleEvent(EVENT_REND, 14s + 100ms, 16s + 500ms);
                break;
            default:
                break;
        }
    }

    void UpdateAI(uint32 diff) override
    {
        // No return here. Maloriak handles the despawn.
        UpdateVictim();

        _events.Update(diff);

        while (uint32 eventId = _events.ExecuteEvent())
        {
            switch (eventId)
            {
                case EVENT_LEAP_OUT_OF_CHAMBER:
                {
                    Position pos = me->GetPosition();
                    pos.m_positionX += cos(me->GetOrientation()) * 11.64f;
                    pos.m_positionY += sin(me->GetOrientation()) * 11.64f;
                    pos.m_positionZ = me->GetMapHeight(pos.GetPositionX(), pos.GetPositionY(), me->GetPositionZ());
                    me->GetMotionMaster()->MoveJump(pos, 21.0f, 15.0f, POINT_GROUND);
                    break;
                }
                case EVENT_REND:
                    DoCastVictim(SPELL_REND);
                    _events.Repeat(9s + 700ms, 16s + 200ms);
                    break;
                default:
                    break;
            }
        }

        DoMeleeAttackIfReady();
    }
private:
    EventMap _events;
};

struct npc_maloriak_magma_jet : public NullCreatureAI
{
    npc_maloriak_magma_jet(Creature* creature) : NullCreatureAI(creature) { }

    void JustSummoned(Creature* summon) override
    {
        summon->CastSpell(summon, SPELL_MAGMA_JETS_ERUPTION);
        summon->DespawnOrUnsummon(30s);
    }
};

struct npc_maloriak_lord_victor_nefarius : public NullCreatureAI
{
    npc_maloriak_lord_victor_nefarius(Creature* creature) : NullCreatureAI(creature) { }

    void JustAppeared() override
    {
        me->SetHover(true);
        DoCastSelf(SPELL_TELEPORT_VISUAL_ONLY);
        _events.ScheduleEvent(EVENT_MOCK_MALORIAK, 7s + 200ms);
    }

    void MovementInform(uint32 motionType, uint32 pointId) override
    {
        if (motionType != POINT_MOTION_TYPE && motionType != EFFECT_MOTION_TYPE)
            return;

        switch (pointId)
        {
            case POINT_LAND:
                me->SetDisableGravity(false);
                me->SetHover(false);
                _events.ScheduleEvent(EVENT_SAY_MALORIAK_DEAD, 2s);
                break;
            default:
                break;
        }
    }

    void DoAction(int32 action) override
    {
        switch (action)
        {
            case ACTION_THROW_BLACK_BOTTLE:
                Talk(SAY_THROW_BLACK_BOTTLE);
                _events.ScheduleEvent(EVENT_THROW_BLACK_BOTTLE, 2s + 400ms);
                break;
            case ACTION_MALORIAK_DEAD:
                me->SetAIAnimKitId(AI_ANIM_KIT_ID_LORD_VICTOR_NEFARIUS);
                _events.Reset();
                _events.ScheduleEvent(EVENT_LAND, 3s);
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
                case EVENT_MOCK_MALORIAK:
                    Talk(SAY_MOCK_MALORIAK);
                    break;
                case EVENT_THROW_BLACK_BOTTLE:
                    Talk(SAY_ANNOUNCE_BLACK_VIAL);
                    DoCastAOE(SPELL_THROW_BLACK_BOTTLE, true);
                    break;
                case EVENT_LAND:
                    me->GetMotionMaster()->MoveLand(POINT_LAND, LordVictorNefariusLandPosition);
                    break;
                case EVENT_SAY_MALORIAK_DEAD:
                    Talk(SAY_MALORIAK_DEAD);
                    _events.ScheduleEvent(EVENT_MASTER_ADVENTURER_AWARD, 7s);
                    break;
                case EVENT_MASTER_ADVENTURER_AWARD:
                    DoCastAOE(SPELL_MASTER_ADVENTURER_AWARD);
                    _events.ScheduleEvent(EVENT_TELEPORT_AWAY, 2s + 500ms);
                    break;
                case EVENT_TELEPORT_AWAY:
                    DoCastSelf(SPELL_TELEPORT_VISUAL_ONLY);
                    me->DespawnOrUnsummon(1s + 200ms);
                    break;
                default:
                    break;
            }
        }
    }

private:
    EventMap _events;
};

struct npc_maloriak_vile_swill : public ScriptedAI
{
    npc_maloriak_vile_swill(Creature* creature) : ScriptedAI(creature) {  }

    void JustAppeared() override
    {
        DoZoneInCombat();
        me->ApplySpellImmune(0, IMMUNITY_ID, sSpellMgr->GetSpellIdForDifficulty(SPELL_GROWTH_CATALYST, me), true);
        _events.ScheduleEvent(EVENT_DARK_SLUDGE, 6s);
    }

    void JustDied(Unit* /*killer*/) override
    {
        me->DespawnOrUnsummon(5s);
    }

    void UpdateAI(uint32 diff) override
    {
        if (!UpdateVictim())
            return;

        _events.Update(diff);

        while (uint32 eventId = _events.ExecuteEvent())
        {
            switch (eventId)
            {
                case EVENT_DARK_SLUDGE:
                    if (Unit* target = SelectTarget(SELECT_TARGET_RANDOM, 0, 60.0f, true))
                        DoCast(target, SPELL_DARK_SLUDGE);
                    _events.Repeat(6s);
                    break;
                default:
                    break;
            }
        }

        DoMeleeAttackIfReady();
    }
private:
    EventMap _events;
};
}

void AddSC_boss_maloriak_minions()
{
    using namespace BlackwingDescent;
    using namespace BlackwingDescent::Maloriak;
    RegisterBlackwingDescentCreatureAI(npc_maloriak_flash_freeze);
    RegisterBlackwingDescentCreatureAI(npc_maloriak_experiment);
    RegisterBlackwingDescentCreatureAI(npc_maloriak_magma_jet);
    RegisterBlackwingDescentCreatureAI(npc_maloriak_lord_victor_nefarius);
    RegisterBlackwingDescentCreatureAI(npc_maloriak_vile_swill);
}
