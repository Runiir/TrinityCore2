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
#include "Containers.h"
#include "GridNotifiers.h"
#include "Map.h"
#include "MoveSpline.h"
#include "PassiveAI.h"
#include "ScriptedCreature.h"
#include "SpellScript.h"
#include "SpellAuraEffects.h"
#include "SpellMgr.h"
#include "InstanceScript.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "TemporarySummon.h"
#include "blackwing_descent.h"

#include "boss_atramedes_shared.h"

void AddSC_boss_atramedes_spells();

namespace BlackwingDescent::Atramedes
{
struct boss_atramedes : public BossAI
{
    boss_atramedes(Creature* creature) : BossAI(creature, DATA_ATRAMEDES), _introFlight(false) { }

    void Reset() override
    {
        _Reset();
        events.SetPhase(PHASE_INTRO);
    }

    void JustEngagedWith(Unit* who) override
    {
        BossAI::JustEngagedWith(who);
        instance->SendEncounterUnit(ENCOUNTER_FRAME_ENGAGE, me);
        instance->DoUpdateWorldState(WORLD_STATE_ID_SILENCE_IS_GOLDEN, 0);
        Talk(SAY_AGGRO);
        DoCastSelf(SPELL_DEVASTATION_TRIGGER);
        DoCastSelf(SPELL_SOUND_BAR);
        events.SetPhase(PHASE_GROUND);
        events.ScheduleEvent(EVENT_CLOSE_DOOR, 5s, 0, PHASE_GROUND);
        events.ScheduleEvent(EVENT_SONAR_PULSE, 14s + 500ms, 0, PHASE_GROUND);
        events.ScheduleEvent(EVENT_MODULATION, 13s, 0, PHASE_GROUND);
        events.ScheduleEvent(EVENT_SEARING_FLAME, 46s, 0, PHASE_GROUND);
        events.ScheduleEvent(EVENT_SONIC_BREATH, 24s, 0, PHASE_GROUND);
        events.ScheduleEvent(EVENT_LIFTOFF, 1min + 31s, 0, PHASE_GROUND);

        if (IsHeroic())
            DoSummon(NPC_LORD_VICTOR_NEFARIUS_ATRAMEDES, LordVictorNefariusSummonPosition, 0, TEMPSUMMON_MANUAL_DESPAWN);
    }

    void EnterEvadeMode(EvadeReason /*why*/) override
    {
        _EnterEvadeMode();
        summons.DespawnAll();
        instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, me);
        instance->SetBossState(DATA_ATRAMEDES, FAIL);
        instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_APPLY_VEHICLE_PERIODIC);
        RemoveEncounterSoundFromPlayers();
        if (GameObject* door = instance->GetGameObject(DATA_ATHENAEUM_DOOR))
            door->SetGoState(GO_STATE_ACTIVE);
        me->DespawnOrUnsummon();
    }

    void JustDied(Unit* /*killer*/) override
    {
        _JustDied();
        instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, me);
        instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_APPLY_VEHICLE_PERIODIC);
        RemoveEncounterSoundFromPlayers();
        if (GameObject* door = instance->GetGameObject(DATA_ATHENAEUM_DOOR))
            door->SetGoState(GO_STATE_ACTIVE);
        Talk(SAY_DEATH);
    }

    // The player Sound Bar aura (88824) never expires and its re-application
    // only refreshes it, so a surviving player carried the previous attempt's
    // Sound into the next pull and kept the bar after the kill. Removing it
    // clears the alternate power (HandleEnableAltPower); the next engage
    // re-applies it from its start value. Noisy! goes with it.
    void RemoveEncounterSoundFromPlayers()
    {
        instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_SOUND_BAR_PLAYER);
        instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_NOISY);
    }

    // Read-only native schedule for bot observation (UnitAI contract). Only
    // the ground phase schedules these; the air phase returns "none".
    uint32 GetTimeUntilEncounterMechanic(uint32 spellId) const override
    {
        uint32 eventId = 0;
        switch (spellId)
        {
            case SPELL_SEARING_FLAME:
                eventId = EVENT_SEARING_FLAME;
                break;
            case SPELL_SONIC_BREATH:
                eventId = EVENT_SONIC_BREATH;
                break;
            case SPELL_TAKE_OFF_ANIM_KIT:
                eventId = EVENT_LIFTOFF;
                break;
            default:
                return std::numeric_limits<uint32>::max();
        }

        if (!events.IsInPhase(PHASE_GROUND))
            return std::numeric_limits<uint32>::max();

        // An event held past its due time (UpdateAI returns while casting or
        // stunned) is due now; GetTimeUntilEvent would wrap it to ~4.29e9.
        uint32 const dueAt = events.GetNextEventTime(eventId);
        if (dueAt && dueAt <= events.GetTimer())
            return 0;
        return events.GetTimeUntilEvent(eventId);
    }

    void KilledUnit(Unit* victim) override
    {
        if (victim->GetTypeId() == TYPEID_PLAYER)
            Talk(SAY_SLAY, victim);
    }

    void JustSummoned(Creature* summon) override
    {
        summons.Summon(summon);

        switch (summon->GetEntry())
        {
            case NPC_SONAR_PULSE:
                summon->m_Events.AddEventAtOffset([summon]()
                {
                    Unit* summoner = summon->ToTempSummon()->GetSummoner();
                    if (!summoner)
                        return;

                    summon->CastSpell(summon, SPELL_SONAR_PULSE_PERIODIC_TRIGGER);
                    summon->m_Events.AddEventAtOffset([summon, summoner]()
                    {
                        Position pos = summon->GetPosition();
                        pos.m_positionZ += 2.0f; // avoid hickups due to uneven terrain
                        float angle = summon->GetAngle(summoner) - summon->GetOrientation();

                        summon->MovePositionToFirstCollision(pos, 100.0f, angle);
                        summon->GetMotionMaster()->MovePoint(POINT_NONE, pos, false);
                        if (uint32 duration = summon->movespline->Duration())
                            summon->DespawnOrUnsummon(duration);
                    }, 800ms);
                }, 400ms);
                break;
            case NPC_TRACKING_FLAMES:
                if (Unit* summoner = summon->ToTempSummon()->GetSummoner())
                {
                    summon->CastSpell(summoner, SPELL_TRACKING);
                    summon->GetMotionMaster()->MoveFollow(summoner, 0.f, 0.f, false, false, true);
                    me->SetFacingToObject(summon);
                    DoCast(summon, SPELL_SONIC_BREATH_CAST);
                }
                break;
            case NPC_SONAR_PULSE_BOMB:
                DoCast(summon, SPELL_SONAR_BOMB, true);
                break;
            case NPC_REVERBERATING_FLAME:
                _reverberatingFlameGUID = summon->GetGUID();
                break;
            default:
                break;
        }
    }

    uint32 GetData(uint32 type) const override
    {
        switch (type)
        {
            case DATA_IS_IN_AIR:
                return (uint8(events.IsInPhase(PHASE_AIR)));
            case DATA_HAS_NOISY_PLAYER:
                return (uint8(!_noisyPlayerGUIDs.empty()));
            case DATA_IS_IN_INTRO_PHASE:
                return (uint8(events.IsInPhase(PHASE_INTRO)));
            case DATA_IS_IN_INTRO_FLIGHT:
                // Only the scripted intro flight (ACTION_START_INTRO until the
                // intro landing). events.IsInPhase(PHASE_INTRO) cannot tell:
                // phase 0 matches every phase, and REACT_PASSIVE also holds in
                // the air phase and for 800 ms after each landing.
                return uint8(_introFlight);
        }

        return 0;
    }

    void SetGUID(ObjectGuid const& guid, int32 type) override
    {
        switch (type)
        {
            case DATA_LAST_USED_ANCIENT_DWARVEN_SHIELD:
                _lastUsedAncientDwarvenShieldGUID = guid;
                if (Creature* flame = ObjectAccessor::GetCreature(*me, _reverberatingFlameGUID))
                    if (CreatureAI* ai = flame->AI())
                        ai->SetGUID(guid, DATA_LAST_USED_ANCIENT_DWARVEN_SHIELD);
                break;
            case DATA_ADD_NOISY_PLAYER:
                _noisyPlayerGUIDs.insert(guid);
                break;
            case DATA_REMOVE_NOISY_PLAYER:
                _noisyPlayerGUIDs.erase(guid);
                break;
            case DATA_LAST_SHIELD_USER:
                _lastShieldUserGUID = guid;
                if (Creature* flame = ObjectAccessor::GetCreature(*me, _reverberatingFlameGUID))
                    if (CreatureAI* ai = flame->AI())
                        ai->SetGUID(guid, DATA_LAST_SHIELD_USER);
                break;
            default:
                break;
        }
    }

    ObjectGuid GetGUID(int32 type) const override
    {
        switch (type)
        {
            case DATA_LAST_USED_ANCIENT_DWARVEN_SHIELD:
                return _lastUsedAncientDwarvenShieldGUID;
        }

        return ObjectGuid::Empty;
    }

    void MovementInform(uint32 motionType, uint32 pointId) override
    {
        if (motionType != POINT_MOTION_TYPE && motionType != EFFECT_MOTION_TYPE)
            return;

        switch (pointId)
        {
            case POINT_CAST_ROARING_BREATH:
                events.ScheduleEvent(EVENT_ROARING_BREATH, 2s);
                break;
            case POINT_PREPARE_LAND_INTRO:
                me->GetMotionMaster()->MoveLand(POINT_LAND_INTRO, IntroLandingPosition);
                break;
            case POINT_LAND_INTRO:
                _introFlight = false;
                me->SetDisableGravity(false);
                me->HandleEmoteCommand(EMOTE_ONESHOT_ROAR);
                me->SetReactState(REACT_AGGRESSIVE);
                break;
            case POINT_LIFTOFF:
                me->SetDisableGravity(true);
                Talk(SAY_FLIGHT_PHASE);
                DoCastSelf(SPELL_SONAR_PULSE_TRIGGER);
                DoCastSelf(SPELL_ROARING_FLAME_BREATH);
                events.ScheduleEvent(EVENT_LAND, 31s, 0, PHASE_AIR);
                break;
            case POINT_LAND:
                me->SetDisableGravity(false);
                events.SetPhase(PHASE_GROUND);
                events.ScheduleEvent(EVENT_REENGAGE_PLAYERS, 800ms, 0, PHASE_GROUND);
                events.ScheduleEvent(EVENT_SONAR_PULSE, 14s, 0, PHASE_GROUND);
                events.ScheduleEvent(EVENT_MODULATION, 13s, 0, PHASE_GROUND);
                events.ScheduleEvent(EVENT_SEARING_FLAME, 51s, 0, PHASE_GROUND);
                events.ScheduleEvent(EVENT_SONIC_BREATH, 22s, 0, PHASE_GROUND);
                events.ScheduleEvent(EVENT_LIFTOFF, 1min + 33s, 0, PHASE_GROUND);

                if (Creature* nefarius = instance->GetCreature(DATA_LORD_VICTOR_NEFARIUS_ATRAMEDES))
                    if (nefarius->IsAIEnabled())
                        nefarius->AI()->DoAction(ACTION_START_SUMMONING_FIENDS);
                break;
            default:
                break;
        }
    }

    void DoAction(int32 action) override
    {
        switch (action)
        {
            case ACTION_START_INTRO:
                _introFlight = true;
                me->GetMotionMaster()->MovePoint(POINT_CAST_ROARING_BREATH, IntroFlightPosition1, false);
                break;
            default:
                break;
        }
    }

    void UpdateAI(uint32 diff) override
    {
        if (!UpdateVictim() && (!events.IsInPhase(PHASE_INTRO)))
            return;

        events.Update(diff);

        if ((me->HasUnitState(UNIT_STATE_CASTING) && !(events.IsInPhase(PHASE_AIR))) || me->HasUnitState(UNIT_STATE_STUNNED))
            return;

        while (uint32 eventId = events.ExecuteEvent())
        {
            switch (eventId)
            {
                case EVENT_ROARING_BREATH:
                    DoCastSelf(SPELL_ROARING_BREATH);
                    events.ScheduleEvent(EVENT_FLY_TO_INTRO_LAND_POSITION, 4s + 300ms);
                    break;
                case EVENT_CLOSE_DOOR:
                    if (GameObject* door = instance->GetGameObject(DATA_ATHENAEUM_DOOR))
                        door->SetGoState(GO_STATE_READY);
                    break;
                case EVENT_FLY_TO_INTRO_LAND_POSITION:
                    me->GetMotionMaster()->MovePoint(POINT_PREPARE_LAND_INTRO, IntroFlightPosition2, false);
                    break;
                case EVENT_SONAR_PULSE:
                    DoCastAOE(SPELL_SONAR_PULSE);
                    events.Repeat(11s);
                    break;
                case EVENT_MODULATION:
                    DoCastAOE(SPELL_MODULATION);
                    // WCL MxFq7TRbvnjGY1hJ fight 32 (10N): unobstructed repeats 16.2 s and
                    // 16.8 s; BigWigs Classic also bars 16 s. Longer gaps were Vertigo stuns
                    // or casts delaying the event, not a slower cooldown.
                    events.Repeat(16s);
                    break;
                case EVENT_SEARING_FLAME:
                    Talk(SAY_ANNOUNCE_SEARING_FLAME);
                    Talk(SAY_SEARING_FLAME);
                    me->StopMoving();
                    DoCastSelf(SPELL_SEARING_FLAME);
                    // Patch 4.1: Searing Flame will put Modulation on a 6 seconds cooldown
                    events.RescheduleEvent(EVENT_MODULATION, 6s, 0, PHASE_GROUND);
                    break;
                case EVENT_SONIC_BREATH:
                    DoCastAOE(SPELL_SONIC_BREATH);
                    events.Repeat(42s, 43s);
                    break;
                case EVENT_LIFTOFF:
                    events.SetPhase(PHASE_AIR);
                    me->AttackStop();
                    me->SetReactState(REACT_PASSIVE);
                    DoCastSelf(SPELL_TAKE_OFF_ANIM_KIT);
                    me->GetMotionMaster()->MoveTakeoff(POINT_LIFTOFF, LiftoffPosition);

                    if (Creature* nefarius = instance->GetCreature(DATA_LORD_VICTOR_NEFARIUS_ATRAMEDES))
                        if (nefarius->IsAIEnabled())
                            nefarius->AI()->DoAction(ACTION_STOP_SUMMONING_FIENDS);
                    break;
                case EVENT_LAND:
                    // End the air Sonar Bomb trigger (92519 and its difficulty
                    // variant). 77674 is the ground disk's own periodic aura
                    // and was never on Atramedes.
                    me->RemoveAurasDueToSpell(sSpellMgr->GetSpellIdForDifficulty(SPELL_SONAR_PULSE_TRIGGER, me));
                    me->InterruptNonMeleeSpells(true);
                    summons.DespawnEntry(NPC_REVERBERATING_FLAME);
                    me->GetMotionMaster()->MoveLand(POINT_LAND, LandPosition, me->GetSpeed(MOVE_RUN) * 3.f);
                    break;
                case EVENT_REENGAGE_PLAYERS:
                    me->SetReactState(REACT_AGGRESSIVE);
                    break;
                default:
                    break;
            }
        }

        DoMeleeAttackIfReady();
    }

private:
    GuidSet _noisyPlayerGUIDs;
    ObjectGuid _lastShieldUserGUID;
    ObjectGuid _lastUsedAncientDwarvenShieldGUID;
    ObjectGuid _reverberatingFlameGUID;
    bool _introFlight;
};

struct npc_atramedes_ancient_dwarven_shield : public NullCreatureAI
{
    npc_atramedes_ancient_dwarven_shield(Creature* creature) : NullCreatureAI(creature), _instance(me->GetInstanceScript()) { }

    void JustDied(Unit* /*killer*/) override
    {
        me->DespawnOrUnsummon(4s);
    }

    void OnSpellClick(Unit* clicker, bool& /*result*/) override
    {
        Creature* atramedes = _instance->GetCreature(DATA_ATRAMEDES);
        if (!atramedes)
            return;

        if (atramedes->AI()->GetData(DATA_IS_IN_AIR))
            clicker->CastSpell(clicker, SPELL_RESONATING_CLASH_AIR, me->GetGUID());
        else
            DoCastSelf(SPELL_RESONATING_CLASH_GROUND);

        me->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
        me->RemoveFlag(UNIT_NPC_FLAGS, UNIT_NPC_FLAG_SPELLCLICK);
    }

private:
    InstanceScript* _instance;
};

struct npc_atramedes_lord_victor_nefarius : public NullCreatureAI
{
    npc_atramedes_lord_victor_nefarius(Creature* creature) : NullCreatureAI(creature), _instance(me->GetInstanceScript()) { }

    void IsSummonedBy(Unit* /*summoner*/) override
    {
        _events.ScheduleEvent(EVENT_SAY_INTRO, 10s);
        _events.ScheduleEvent(EVENT_SUMMON_FIEND, 30s);
        DoCastSelf(SPELL_APPLY_VEHICLE_PERIODIC);
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
                case EVENT_SAY_INTRO:
                    Talk(SAY_INTRO);
                    break;
                case EVENT_SUMMON_FIEND:
                    Talk(SAY_SUMMON_FIEND);
                    DoCastSelf(SPELL_SUMMON_IMP);
                    _events.Repeat(35s);
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
            case ACTION_DESTROY_SHIELD:
                Talk(SAY_DESTROY_SHIELD);
                DoCastAOE(SPELL_DESTROY_SHIELD);
                break;
            case ACTION_STOP_SUMMONING_FIENDS:
                _events.Reset();
                break;
            case ACTION_START_SUMMONING_FIENDS:
                _events.ScheduleEvent(EVENT_SUMMON_FIEND, 30s);
                break;
            default:
                break;
        }
    }

private:
    EventMap _events;
    InstanceScript* _instance;
};

struct npc_atramedes_obnoxious_fiend : public ScriptedAI
{
    npc_atramedes_obnoxious_fiend(Creature* creature) : ScriptedAI(creature), _instance(me->GetInstanceScript())
    {
        Initialize();
    }

    void Initialize()
    {
        me->SetReactState(REACT_PASSIVE);
    }

    void JustDied(Unit* /*killer*/) override
    {
        me->DespawnOrUnsummon(2s);
    }

    void JustAppeared() override
    {
        DoZoneInCombat();
        DoCastSelf(SPELL_PHASE_SHIFT, true);
        _events.ScheduleEvent(EVENT_FOCUS_PLAYER, 1s);
    }

    void DoAction(int32 action) override
    {
        switch (action)
        {
            case ACTION_PLAYER_ENTERED:
                me->AttackStop();
                me->SetReactState(REACT_PASSIVE);
                _events.ScheduleEvent(EVENT_OBNOXIOUS, 1s);
                me->SetAIAnimKitId(AI_ANIM_KIT_ID_OBNOXIOUS_IMP);
                break;
            case ACTION_PLAYER_LEFT:
                DoCastSelf(SPELL_PHASE_SHIFT, true);
                _events.Reset();
                _events.ScheduleEvent(EVENT_FOCUS_PLAYER, 1s);
                me->SetAIAnimKitId(0);
                break;
            default:
                break;
        }
    }

    void UpdateAI(uint32 diff) override
    {
        UpdateVictim();

        _events.Update(diff);

        while (uint32 eventId = _events.ExecuteEvent())
        {
            switch (eventId)
            {
                case EVENT_SAY_INTRO:
                    Talk(SAY_INTRO);
                    break;
                case EVENT_FOCUS_PLAYER:
                    if (Unit* target = SelectTarget(SELECT_TARGET_RANDOM, 0, 100.0f, true, true, -SPELL_PESTERED))
                        AddThreat(target, 50000000.0f);
                    _events.ScheduleEvent(EVENT_CHASE_PLAYER, 1s);
                    break;
                case EVENT_CHASE_PLAYER:
                    me->SetReactState(REACT_AGGRESSIVE);
                    break;
                case EVENT_OBNOXIOUS:
                    if (Unit* vehicle = me->GetVehicleBase())
                        DoCast(vehicle, SPELL_OBNOXIOUS);
                    _events.Repeat(2s + 500ms);
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

struct npc_atramedes_reverberating_flame : public NullCreatureAI
{
    npc_atramedes_reverberating_flame(Creature* creature) : NullCreatureAI(creature) { }

    void IsSummonedBy(Unit* summoner) override
    {
        DoCastSelf(SPELL_ROARING_FLAME_BREATH_REVERSE_CAST);
        DoCastSelf(SPELL_AGGRO_CREATOR);
        trackTarget(summoner);
    }

    void SetGUID(ObjectGuid const& guid, int32 type) override
    {
        switch (type)
        {
            case DATA_LAST_USED_ANCIENT_DWARVEN_SHIELD:
                _lastUsedDwarvenShieldGUID = guid;

                me->InterruptNonMeleeSpells(true);
                me->GetMotionMaster()->InitDefault();
                me->StopMoving();
                me->SetTarget(ObjectGuid::Empty);
                _events.Reset();
                _events.ScheduleEvent(EVENT_MOVE_TO_DWARVEN_SHIELD, 2s);
                break;
            case DATA_LAST_SHIELD_USER:
                _lastUsedDwarvenShieldUserGUID = guid;
                break;
            default:
                break;
        }
    }

    void MovementInform(uint32 motionType, uint32 pointId) override
    {
        if (motionType != POINT_MOTION_TYPE)
            return;

        switch (pointId)
        {
            case POINT_DWARVEN_SHIELD:
            {
                DoCastSelf(SPELL_SONIC_FLAMES);
                // The redirected breath restarts on the gong user at its
                // initial speed (Wowhead Cata Classic guide, 2024-06-04;
                // Icy Veins detailed guide, 2012-10-08). The Building Speed
                // Trigger addon aura then stacks it up again from zero.
                me->RemoveAurasDueToSpell(sSpellMgr->GetSpellIdForDifficulty(SPELL_BUILDING_SPEED_EFFECT, me));
                Unit* target = ObjectAccessor::GetUnit(*me, _lastUsedDwarvenShieldUserGUID);
                if (!target)
                    target = me->SelectNearestPlayer(100.f);

                if (target)
                    trackTarget(target);

                _lastUsedDwarvenShieldUserGUID = ObjectGuid::Empty;
                break;
            }
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
                case EVENT_MOVE_TO_DWARVEN_SHIELD:
                    if (Creature* shield = ObjectAccessor::GetCreature(*me, _lastUsedDwarvenShieldGUID))
                        me->GetMotionMaster()->MovePoint(POINT_DWARVEN_SHIELD, shield->GetPosition());
                    _lastUsedDwarvenShieldGUID = ObjectGuid::Empty;
                    break;
                case EVENT_CHECK_TRACKING_TARGET:
                {
                    Unit* target = ObjectAccessor::GetUnit(*me, me->GetTarget());
                    if (!target || !target->IsAlive())
                    {
                        target = me->SelectNearestPlayer(100.f);
                        if (target)
                            trackTarget(target);
                    }
                    else
                        _events.Repeat(500ms);
                    break;
                }
                default:
                    break;
            }
        }
    }

private:
    EventMap _events;
    ObjectGuid _lastUsedDwarvenShieldGUID;
    ObjectGuid _lastUsedDwarvenShieldUserGUID;

    void trackTarget(Unit* target)
    {
        DoCast(target, SPELL_TRACKING);
        me->GetMotionMaster()->MoveFollow(target, 0.0f, 0.f, false, false, true);
        me->SetTarget(target->GetGUID());
        _events.ScheduleEvent(EVENT_CHECK_TRACKING_TARGET, 500ms);
    }
};
}

void AddSC_boss_atramedes()
{
    using namespace BlackwingDescent;
    using namespace BlackwingDescent::Atramedes;
    RegisterBlackwingDescentCreatureAI(boss_atramedes);
    RegisterBlackwingDescentCreatureAI(npc_atramedes_ancient_dwarven_shield);
    RegisterBlackwingDescentCreatureAI(npc_atramedes_lord_victor_nefarius);
    RegisterBlackwingDescentCreatureAI(npc_atramedes_obnoxious_fiend);
    RegisterBlackwingDescentCreatureAI(npc_atramedes_reverberating_flame);
    AddSC_boss_atramedes_spells();
}
