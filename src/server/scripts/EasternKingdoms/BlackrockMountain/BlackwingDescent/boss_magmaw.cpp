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
#include "Log.h"
#include "Containers.h"
#include "ScriptedCreature.h"
#include "Spell.h"
#include "SpellScript.h"
#include "SpellAuraEffects.h"
#include "Player.h"
#include "Vehicle.h"
#include "InstanceScript.h"
#include "ObjectAccessor.h"
#include "MotionMaster.h"
#include "Map.h"
#include "blackwing_descent.h"
#include "boss_magmaw_shared.h"
#include <limits>

void AddSC_boss_magmaw_encounter_spells();

namespace BlackwingDescent::Magmaw
{
enum Events
{
    // Magmaw
    EVENT_MAGMA_PROJECTILE = 1,
    EVENT_LAVA_SPEW,
    EVENT_MANGLE,
    EVENT_PREPARE_MASSIVE_CRASH,
    EVENT_MASSIVE_CRASH,
    EVENT_ANNOUNCE_PINCERS_EXPOSED,
    EVENT_IMPALE_SELF,
    EVENT_SHOW_HEAD,
    EVENT_FINISH_IMPALE_SELF,

    // Nefarian
    EVENT_TALK_HEROIC_INTRO_1,
    EVENT_TALK_HEROIC_INTRO_2,
    EVENT_BLAZING_INFERNO,
    EVENT_SHADOW_BREATH,
    EVENT_TALK_MAGMAW_DEAD,

    // Lava Parasite
    EVENT_PREPARE_PARASITE,
    EVENT_ENGAGE_PLAYERS,

    // Blazing Bone Construct
    EVENT_FIERY_SLASH
};

enum Phases
{
    PHASE_OUT_OF_COMBAT = 1,
    PHASE_COMBAT        = 2,
    PHASE_IMPALED       = 3
};

enum Texts
{
    // Magmaw
    SAY_ANNOUNCE_LAVA_PARASITES = 0,
    SAY_ANNOUNCE_EXPOSE_PINCERS = 1,
    SAY_ANNOUNCE_EXPOSED_HEAD   = 2,

    // Nefarian
    SAY_INTRO_1                 = 0,
    SAY_INTRO_2                 = 1,
    SAY_MAGMAW_LOW_HEALTH       = 2,
    SAY_MAGMAW_DEAD             = 3
};

enum BroadcastTexts
{
    BROADCAST_TEXT_WHISPER_MANGLE = 48488
};

enum VehicleSeats
{
    // Magmaw
    SEAT_MAGMAWS_PINCER_1           = 0,
    SEAT_MAGMAWS_PINCER_2           = 1,
    SEAT_MANGLE                     = 2,
    SEAT_EXPOSED_HEAD_OF_MAGMAW_1   = 3,
    SEAT_EXPOSED_HEAD_OF_MAGMAW_2   = 4,

    // Magmaw's Pincer
    SEAT_PINCER                     = 0
};

enum MovePoints
{
    POINT_NONE = 0
};

enum SplineChains
{
    SPLINE_CHAIN_NEFARIAN_INTRO = 1
};

enum EncounterFramePriorities
{
    FRAME_PRIORITY_MAGMAW                   = 1,
    FRAME_PRIORITY_EXPOSED_HEAD_OF_MAGMAW   = 2
};

enum BodyParts : uint8
{
    BODY_PART_EXPOSED_HEAD_1 = 0,
    BODY_PART_EXPOSED_HEAD_2,
    BODY_PART_PINCER_1,
    BODY_PART_PINCER_2,
    MAX_BODY_PARTS
};

Position const ExposedHeadOfMagmawPos   = { -299.0f,    -28.9861f,  191.0293f, 4.118977f };
Position const NefarianIntroSummonPos   = { -390.1042f, 40.88411f,  207.8586f, 0.196609f };

#define SPELL_PARASITIC_INFECTION_PERIODIC_DAMAGE RAID_MODE<uint32>(78941, 91913, 94678, 94679)
#define SPELL_MANGLE_DAMAGE RAID_MODE<uint32>(89773, 91912, 94616, 94617)

struct boss_magmaw : public BossAI
{
    boss_magmaw(Creature* creature) : BossAI(creature, DATA_MAGMAW),
        _bodyPartGUIDs{}, _magmaProjectileCount(0), _headEngaged(false), _heroicPhaseTwoActive(!IsHeroic())
    {
        me->SetReactState(REACT_PASSIVE);
    }

    void Reset() override
    {
        DespawnBody();
        _Reset();
        _magmaProjectileCount = 0;
        _headEngaged = false;
        _heroicPhaseTwoActive = !IsHeroic();
        me->SetUnkillable(true);
        me->SetReactState(REACT_PASSIVE);
        events.SetPhase(PHASE_OUT_OF_COMBAT);
    }

    void JustAppeared() override
    {
        if (uint8 missingBodyMask = RebuildBody())
            TC_LOG_ERROR("scripts", "Magmaw body construction failed on appearance missing_mask=%u; native engagement will remain held closed", missingBodyMask);
        events.SetPhase(PHASE_OUT_OF_COMBAT);
    }

    void JustEngagedWith(Unit* who) override
    {
        // The body is created while the grid first appears, which can be many
        // minutes before a route-directed raid reaches Magmaw. Keep those
        // encounter-owned parts on an explicit manual lifetime. An incomplete
        // set fails the pull closed and is rebuilt atomically by JustAppeared
        // after the native evade/respawn boundary. Never schedule encounter
        // events while a part is absent, dead, outside the world, or detached
        // from Magmaw's vehicle.
        uint8 missingBodyMask = GetMissingBodyMask();
        if (missingBodyMask)
        {
            TC_LOG_ERROR("scripts", "Magmaw body incomplete before engagement missing_mask=%u; native engagement held closed for exact respawn reconstruction", missingBodyMask);
            EnterEvadeMode(EVADE_REASON_OTHER);
            return;
        }

        // The template's unkillable flag must not clamp lethal combat damage
        // to one health. Release the reset protection only for a complete body.
        me->SetUnkillable(false);
        BossAI::JustEngagedWith(who);
        instance->SendEncounterUnit(ENCOUNTER_FRAME_ENGAGE, me, FRAME_PRIORITY_MAGMAW);
        instance->DoUpdateWorldState(WORLD_STATE_ID_PARASITE_EVENING, 0);
        me->SetReactState(REACT_AGGRESSIVE);

        events.SetPhase(PHASE_COMBAT);
        events.ScheduleEvent(EVENT_MAGMA_PROJECTILE, 6s, 0, PHASE_COMBAT);
        events.ScheduleEvent(EVENT_LAVA_SPEW, 19s, 0, PHASE_COMBAT);
        events.ScheduleEvent(EVENT_MANGLE, 1min + 30s, 0, PHASE_COMBAT);

        if (IsHeroic())
            DoSummon(NPC_NEFARIAN_MAGMAW, NefarianIntroSummonPos, 0, TEMPSUMMON_MANUAL_DESPAWN);
    }

    void PassengerBoarded(Unit* passenger, int8 seatId, bool apply) override
    {
        if (passenger && seatId == SEAT_MANGLE)
        {
            if (apply)
            {
                passenger->CastSpell(passenger, SPELL_MANGLE_2, true);
                passenger->CastSpell(passenger, SPELL_SWELTERING_ARMOR, true);

                if (Player* player = passenger->ToPlayer())
                    player->Whisper(BROADCAST_TEXT_WHISPER_MANGLE, player, true);
            }
            else
            {
                passenger->RemoveAurasDueToSpell(SPELL_MANGLE_DAMAGE);
                passenger->RemoveAurasDueToSpell(SPELL_MANGLE_2);
            }
        }
    }

    void EnterEvadeMode(EvadeReason /*why*/) override
    {
        _EnterEvadeMode();
        instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, me);

        Creature* head = GetBodyPart(BODY_PART_EXPOSED_HEAD_1);
        if (_headEngaged && head)
            instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, head);

        DoCastSelf(SPELL_EJECT_PASSENGER_3, true);
        for (BodyParts part : { BODY_PART_PINCER_1, BODY_PART_PINCER_2 })
            if (Creature* pincer = GetBodyPart(part))
                pincer->CastSpell(pincer, SPELL_EJECT_PASSENGER_1, true);

        instance->SetBossState(DATA_MAGMAW, FAIL);
        instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_PARASITIC_INFECTION_VOMIT);
        instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_PARASITIC_INFECTION_PERIODIC_DAMAGE);
        if (head)
            head->DespawnOrUnsummon();
        summons.DespawnAll();

        if (Creature* nefarian = instance->GetCreature(DATA_NEFARIAN_MAGMAW))
            nefarian->DespawnOrUnsummon();
        _DespawnAtEvade();
    }

    void JustDied(Unit* /*killer*/) override
    {
        if (Creature* head = GetBodyPart(BODY_PART_EXPOSED_HEAD_1))
            if (_headEngaged)
                instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, head);

        instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_PARASITIC_INFECTION_VOMIT);
        instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_PARASITIC_INFECTION_PERIODIC_DAMAGE);
        instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, me);

        if (Creature* nefarian = instance->GetCreature(DATA_NEFARIAN_MAGMAW))
            nefarian->AI()->DoAction(ACTION_MAGMAW_DEAD);

        DespawnBody();
        _JustDied();
    }

    void JustSummoned(Creature* summon) override
    {
        switch (summon->GetEntry())
        {
            case NPC_PILLAR_OF_FLAME:
                summon->CastSpell(summon, SPELL_PILLAR_OF_FLAME_DUMMY);
                summon->SetDisplayFromModel(0);
                summon->DespawnOrUnsummon(7s);
                Talk(SAY_ANNOUNCE_LAVA_PARASITES);
                summons.Summon(summon);
                break;
            case NPC_NEFARIAN_MAGMAW:
            case NPC_EXPOSED_HEAD_OF_MAGMAW:
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
            case DATA_FREE_PINCER:
                for (BodyParts part : { BODY_PART_PINCER_1, BODY_PART_PINCER_2 })
                    if (Creature* pincer = GetBodyPart(part))
                        if (pincer->GetVehicleKit() && pincer->GetVehicleKit()->GetAvailableSeatCount())
                            return pincer->GetGUID();
                break;
            default:
                return ObjectGuid::Empty;
        }

        return ObjectGuid::Empty;
    }

    uint32 GetTimeUntilEncounterMechanic(uint32 spellId) const override
    {
        if (spellId != SPELL_MASSIVE_CRASH)
            return std::numeric_limits<uint32>::max();

        // The sequence is already reserved after Mangle fires and remains so
        // through Prepare Massive Crash. Release it only after the native
        // Massive Crash event executes.
        if (events.GetTimeUntilEvent(EVENT_PREPARE_MASSIVE_CRASH)
                != std::numeric_limits<uint32>::max()
            || events.GetTimeUntilEvent(EVENT_MASSIVE_CRASH)
                != std::numeric_limits<uint32>::max())
            return 0;

        return events.GetTimeUntilEvent(EVENT_MANGLE);
    }

    void DamageTaken(Unit* /*attacker*/, uint32& damage) override
    {
        if (me->HealthBelowPctDamaged(30, damage) && !_heroicPhaseTwoActive)
        {
            if (Creature* nefarian = instance->GetCreature(DATA_NEFARIAN_MAGMAW))
                nefarian->AI()->DoAction(ACTION_SCHEDULE_SHADOW_BREATH);
            _heroicPhaseTwoActive = true;
        }

        if (damage >= me->GetHealth())
        {
            // Make sure we eject all passengers nicely before we die so they wont end up in the lava
            DoCastSelf(SPELL_EJECT_PASSENGER_3, true);

            for (BodyParts part : { BODY_PART_PINCER_1, BODY_PART_PINCER_2 })
                if (Creature* pincer = GetBodyPart(part))
                    pincer->CastSpell(pincer, SPELL_EJECT_PASSENGER_1, true);
        }
    }

    void DoAction(int32 action) override
    {
        switch (action)
        {
            case ACTION_IMPALE_MAGMAW:
                events.SetPhase(PHASE_IMPALED);
                me->InterruptNonMeleeSpells(true);
                me->RemoveAurasDueToSpell(SPELL_MASSIVE_CRASH);
                me->RemoveAurasDueToSpell(SPELL_PILLAR_OF_FLAME_MISSILE_PERIODIC);
                me->AttackStop();
                me->SetReactState(REACT_PASSIVE);
                me->ReleaseSpellFocus(nullptr, false);

                if (Creature* spikeStalker = me->FindNearestCreature(NPC_MAGMAW_SPIKE_STALKER, 60.0f))
                    me->SetFacingToObject(spikeStalker);

                events.ScheduleEvent(EVENT_IMPALE_SELF, 1s, 0, PHASE_IMPALED);
                break;
            case ACTION_ENABLE_MOUNTING:
                me->SetFlag(UNIT_NPC_FLAGS, UNIT_NPC_FLAG_SPELLCLICK);
                me->SetFlag(UNIT_FIELD_FLAGS_2, UNIT_FLAG2_INTERACT_WHILE_HOSTILE);

                if (Creature* head = GetBodyPart(BODY_PART_EXPOSED_HEAD_1))
                    head->CastSpell(head, SPELL_RIDE_VEHICLE_HEAD, true);

                for (BodyParts part : { BODY_PART_PINCER_1, BODY_PART_PINCER_2 })
                    if (Creature* pincer = GetBodyPart(part))
                        pincer->CastSpell(pincer, SPELL_EJECT_PASSENGER_1, true);
                events.ScheduleEvent(EVENT_ANNOUNCE_PINCERS_EXPOSED, 1s, 0, PHASE_COMBAT);
                break;
            case ACTION_DISABLE_MOUNTING:
                me->RemoveFlag(UNIT_NPC_FLAGS, UNIT_NPC_FLAG_SPELLCLICK);
                me->RemoveFlag(UNIT_FIELD_FLAGS_2, UNIT_FLAG2_INTERACT_WHILE_HOSTILE);

                if (events.IsInPhase(PHASE_COMBAT))
                {
                    me->SetReactState(REACT_AGGRESSIVE);
                    events.ScheduleEvent(EVENT_LAVA_SPEW, 1ms, 0, PHASE_COMBAT);
                }
                break;
            case ACTION_EXPOSE_HEAD:
                DoCastSelf(SPELL_EJECT_PASSENGER_3, true);
                Talk(SAY_ANNOUNCE_EXPOSED_HEAD);
                instance->SendEncounterUnit(ENCOUNTER_FRAME_UPDATE_PRIORITY, me);
                me->RemoveAurasDueToSpell(SPELL_CHAIN_VISUAL_1);
                me->RemoveAurasDueToSpell(SPELL_CHAIN_VISUAL_2);
                break;
            case ACTION_COVER_HEAD:
                events.SetPhase(PHASE_COMBAT);
                events.ScheduleEvent(EVENT_FINISH_IMPALE_SELF, 3s, 0, PHASE_COMBAT);

                if (Creature* head = GetBodyPart(BODY_PART_EXPOSED_HEAD_1))
                {
                    head->CastSpell(head, SPELL_RIDE_VEHICLE_EXPOSED_HEAD, true);
                    head->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
                }
                break;
            default:
                break;
        }
    }

    void UpdateAI(uint32 diff) override
    {
        if (!UpdateVictim() && !events.IsInPhase(PHASE_OUT_OF_COMBAT))
            return;

        events.Update(diff);

        if (me->HasUnitState(UNIT_STATE_CASTING) && !events.IsInPhase(PHASE_IMPALED))
            return;

        while (uint32 eventId = events.ExecuteEvent())
        {
            switch (eventId)
            {
                case EVENT_MAGMA_PROJECTILE:
                    if (_magmaProjectileCount < 4)
                    {
                        if (me->GetVictim() && me->GetVictim()->IsWithinMeleeRange(me))
                            DoCastAOE(SPELL_MAGMA_SPIT_TARGETING);
                        else
                            DoCastAOE(SPELL_MAGMA_SPIT_MOLTEN_TANTRUM);

                        _magmaProjectileCount++;
                        events.Repeat(6s);
                    }
                    else
                    {
                        DoCastAOE(SPELL_PILLAR_OF_FLAME);
                        DoCastAOE(SPELL_PILLAR_OF_FLAME_SET_VEHICLE_ID);
                        _magmaProjectileCount = 0;
                        events.Repeat(8s);
                    }
                    break;
                case EVENT_LAVA_SPEW:
                    DoCastAOE(SPELL_LAVA_SPEW);
                    events.RescheduleEvent(EVENT_MAGMA_PROJECTILE, 6s, 0, PHASE_COMBAT);
                    events.Repeat(24s);
                    break;
                case EVENT_MANGLE:
                    if (SelectTarget(SELECT_TARGET_RANDOM, 0, NonTankTargetSelector(me)))
                        DoCastAOE(SPELL_MANGLE_TARGETING);

                    events.CancelEvent(EVENT_MAGMA_PROJECTILE);
                    events.CancelEvent(EVENT_LAVA_SPEW);
                    events.ScheduleEvent(EVENT_PREPARE_MASSIVE_CRASH, 3s + 500ms, 0, PHASE_COMBAT);
                    events.Repeat(1min + 35s);
                    break;
                case EVENT_PREPARE_MASSIVE_CRASH:
                    if (ObjectGuid guid = instance->GetGuidData(DATA_PREPARE_MASSIVE_CRASH_AND_GET_TARGET_GUID))
                    {
                        if (Creature* stalker = ObjectAccessor::GetCreature(*me, guid))
                        {
                            me->AttackStop();
                            me->SetReactState(REACT_PASSIVE);
                            me->ReleaseSpellFocus(nullptr, false);
                            me->SetFacingToObject(stalker, true);
                            events.ScheduleEvent(EVENT_MASSIVE_CRASH, 5s);
                        }
                    }
                    break;
                case EVENT_MASSIVE_CRASH:
                    DoCast(SPELL_MASSIVE_CRASH);
                    for (BodyParts part : { BODY_PART_PINCER_1, BODY_PART_PINCER_2 })
                        if (Creature* pincer = GetBodyPart(part))
                            pincer->CastSpell(pincer, SPELL_EJECT_PASSENGER_1, true);
                    break;
                case EVENT_ANNOUNCE_PINCERS_EXPOSED:
                    Talk(SAY_ANNOUNCE_EXPOSE_PINCERS);
                    break;
                case EVENT_IMPALE_SELF:
                    DoCastSelf(SPELL_IMPALE_SELF);
                    events.ScheduleEvent(EVENT_SHOW_HEAD, 5s, 0, PHASE_IMPALED);
                    break;
                case EVENT_SHOW_HEAD:
                    if (Creature* head = GetBodyPart(BODY_PART_EXPOSED_HEAD_1))
                    {
                        if (!_headEngaged)
                        {
                            instance->SendEncounterUnit(ENCOUNTER_FRAME_ENGAGE, head, FRAME_PRIORITY_EXPOSED_HEAD_OF_MAGMAW);
                            _headEngaged = true;
                        }
                        head->CastSpell(head, SPELL_RIDE_VEHICLE_HEAD, true);
                        head->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
                    }
                    break;
                case EVENT_FINISH_IMPALE_SELF:
                    me->SetReactState(REACT_AGGRESSIVE);
                    events.ScheduleEvent(EVENT_LAVA_SPEW, 1ms, 0, PHASE_COMBAT);
                    events.ScheduleEvent(EVENT_MAGMA_PROJECTILE, 4s, 0, PHASE_COMBAT);
                    break;
                default:
                    break;
            }

            // A due event may have started a cast. Leave later events queued
            // until it finishes, while preserving impale's head-exposure events.
            if (me->HasUnitState(UNIT_STATE_CASTING) && !events.IsInPhase(PHASE_IMPALED))
                return;
        }

        DoMeleeAttackIfReady();
    }

private:
    uint8 GetMissingBodyMask() const
    {
        uint8 missingMask = 0;
        for (uint8 i = BODY_PART_EXPOSED_HEAD_1; i < MAX_BODY_PARTS; ++i)
        {
            Creature* bodyPart = GetBodyPart(BodyParts(i));
            if (!bodyPart || !bodyPart->IsAlive() || !bodyPart->IsInWorld() || bodyPart->GetVehicleBase() != me)
                missingMask |= uint8(1u << i);
        }
        return missingMask;
    }

    void DespawnBody()
    {
        // The real exposed head is deliberately not in SummonList because it
        // owns encounter-frame behavior. Despawn every remembered part first,
        // then clear any remaining encounter-owned summons and GUID identity.
        for (uint8 i = BODY_PART_EXPOSED_HEAD_1; i < MAX_BODY_PARTS; ++i)
            if (Creature* bodyPart = GetBodyPart(BodyParts(i)))
                bodyPart->DespawnOrUnsummon();
        summons.DespawnAll();
        _bodyPartGUIDs.fill(ObjectGuid::Empty);
    }

    uint8 RebuildBody()
    {
        DespawnBody();
        return SetupBody();
    }

    uint8 SetupBody()
    {
        Creature* pincer1 = DoSummon(NPC_MAGMAWS_PINCER_1, me->GetPosition(), 0, TEMPSUMMON_MANUAL_DESPAWN);
        if (pincer1)
            _bodyPartGUIDs[BODY_PART_PINCER_1] = pincer1->GetGUID();

        Creature* pincer2 = DoSummon(NPC_MAGMAWS_PINCER_2, me->GetPosition(), 0, TEMPSUMMON_MANUAL_DESPAWN);
        if (pincer2)
            _bodyPartGUIDs[BODY_PART_PINCER_2] = pincer2->GetGUID();

        Creature* exposedHead1 = DoSummon(NPC_EXPOSED_HEAD_OF_MAGMAW, ExposedHeadOfMagmawPos, 0, TEMPSUMMON_MANUAL_DESPAWN);
        Creature* exposedHead2 = DoSummon(NPC_EXPOSED_HEAD_OF_MAGMAW_2, me->GetPosition(), 0, TEMPSUMMON_MANUAL_DESPAWN);

        if (exposedHead1)
            _bodyPartGUIDs[BODY_PART_EXPOSED_HEAD_1] = exposedHead1->GetGUID();
        if (exposedHead2)
            _bodyPartGUIDs[BODY_PART_EXPOSED_HEAD_2] = exposedHead2->GetGUID();

        uint8 missingBodyMask = 0;
        if (!exposedHead1)
            missingBodyMask |= uint8(1u << BODY_PART_EXPOSED_HEAD_1);
        if (!exposedHead2)
            missingBodyMask |= uint8(1u << BODY_PART_EXPOSED_HEAD_2);
        if (!pincer1)
            missingBodyMask |= uint8(1u << BODY_PART_PINCER_1);
        if (!pincer2)
            missingBodyMask |= uint8(1u << BODY_PART_PINCER_2);
        if (missingBodyMask)
        {
            DespawnBody();
            return missingBodyMask;
        }

        pincer1->EnterVehicle(me, SEAT_MAGMAWS_PINCER_1);
        pincer1->SetDisplayFromModel(2);
        pincer2->EnterVehicle(me, SEAT_MAGMAWS_PINCER_2);
        pincer2->SetDisplayFromModel(2);

        exposedHead1->SetReactState(REACT_PASSIVE);
        exposedHead2->SetReactState(REACT_PASSIVE);

        exposedHead2->EnterVehicle(me, SEAT_EXPOSED_HEAD_OF_MAGMAW_2);
        DoCastSelf(SPELL_BIRTH);

        // First we link the real exposed head
        exposedHead1->CastSpell(me, SPELL_POINT_OF_VULNERABILITY_SHARE_DAMAGE);
        exposedHead1->CastSpell(exposedHead1, SPELL_POINT_OF_VULNERABILITY);
        exposedHead1->CastSpell(exposedHead2, SPELL_POINT_OF_VULNERABILITY_SHARE_DAMAGE);
        // ... now the dummy exposed head
        exposedHead2->CastSpell(me, SPELL_POINT_OF_VULNERABILITY_SHARE_DAMAGE);
        exposedHead2->CastSpell(exposedHead2, SPELL_POINT_OF_VULNERABILITY);
        // ... and now Magmaw
        DoCast(exposedHead2, SPELL_POINT_OF_VULNERABILITY_SHARE_DAMAGE);
        DoCast(exposedHead1, SPELL_POINT_OF_VULNERABILITY_SHARE_DAMAGE);

        exposedHead2->CastSpell(exposedHead2, SPELL_QUEST_INVIS_5);

        ObjectGuid guid = me->GetGUID();
        Unit* head = exposedHead1;
        head->m_Events.AddEventAtOffset([head, guid]()
        {
            if (Unit* target = ObjectAccessor::GetUnit(*head, guid))
                head->CastSpell(target, SPELL_RIDE_VEHICLE_EXPOSED_HEAD, true);
        }, 1s + 200ms);

        return 0;
    }

    Creature* GetBodyPart(BodyParts part) const
    {
        return ObjectAccessor::GetCreature(*me, _bodyPartGUIDs[part]);
    }

    std::array<ObjectGuid, MAX_BODY_PARTS> _bodyPartGUIDs;
    uint8 _magmaProjectileCount;
    bool _headEngaged;
    bool _heroicPhaseTwoActive;
};

struct npc_magmaw_nefarian : public ScriptedAI
{
    npc_magmaw_nefarian(Creature* creature) : ScriptedAI(creature), _instance(me->GetInstanceScript())
    {
        Initialize();
    }

    void Initialize()
    {
        me->SetReactState(REACT_PASSIVE);
    }

    void IsSummonedBy(Unit* /*summoner*/) override
    {
        me->GetMotionMaster()->MoveAlongSplineChain(POINT_NONE, SPLINE_CHAIN_NEFARIAN_INTRO, false);
        _events.ScheduleEvent(EVENT_TALK_HEROIC_INTRO_1, 11s);
        _events.ScheduleEvent(EVENT_BLAZING_INFERNO, 27s);
    }

    void DoAction(int32 action) override
    {
        switch (action)
        {
            case ACTION_SCHEDULE_SHADOW_BREATH:
                Talk(SAY_MAGMAW_LOW_HEALTH);
                _events.ScheduleEvent(EVENT_SHADOW_BREATH, 9s);
                break;
            case ACTION_MAGMAW_DEAD:
                _events.Reset();
                _events.ScheduleEvent(EVENT_TALK_MAGMAW_DEAD, 2s + 400ms);
                me->DespawnOrUnsummon(6s);
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
                case EVENT_TALK_HEROIC_INTRO_1:
                    Talk(SAY_INTRO_1);
                    _events.ScheduleEvent(EVENT_TALK_HEROIC_INTRO_2, 16s);
                    break;
                case EVENT_TALK_HEROIC_INTRO_2:
                    Talk(SAY_INTRO_2);
                    break;
                case EVENT_BLAZING_INFERNO:
                    DoCastAOE(SPELL_BLAZING_INFERNO_TARGETING, true);
                    _events.Repeat(36s);
                    break;
                case EVENT_SHADOW_BREATH:
                    DoCastAOE(SPELL_SHADOW_BREATH_TARGETING);
                    _events.Repeat(1s + 200ms);
                    break;
                case EVENT_TALK_MAGMAW_DEAD:
                    Talk(SAY_MAGMAW_DEAD);
                    break;
                default:
                    break;
            }
        }
    }

private:
    EventMap _events;
    InstanceScript* _instance;
};

struct npc_magmaw_lava_parasite : public ScriptedAI
{
    npc_magmaw_lava_parasite(Creature* creature) : ScriptedAI(creature), _instance(me->GetInstanceScript())
    {
        me->SetReactState(REACT_PASSIVE);
    }

    void JustAppeared() override
    {
        me->GetMotionMaster()->MoveFall();
    }

    void IsSummonedBy(Unit* /*summoner*/) override
    {
        // I have no idea why Blizzard is delaying it but they do so we comply here as well
        _events.ScheduleEvent(EVENT_PREPARE_PARASITE, 1s + 700ms);
    }

    void JustDied(Unit* /*killer*/) override
    {
        _events.Reset();
        me->DespawnOrUnsummon(2s + 500ms);
    }

    void SpellHitTarget(WorldObject* /*target*/, SpellInfo const* spell) override
    {
        if (spell->Id == SPELL_LAVA_PARASITE_RIDE_VEHICLE)
        {
            me->AttackStop();
            me->SetReactState(REACT_PASSIVE);
            me->DespawnOrUnsummon(4s);
            if (!_instance->instance->GetWorldStateValue(WORLD_STATE_ID_PARASITE_EVENING))
                _instance->DoUpdateWorldState(WORLD_STATE_ID_PARASITE_EVENING, 1);
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
                case EVENT_PREPARE_PARASITE:
                    DoCastSelf(SPELL_LAVA_PARASITE_PROC_AURA);
                    _events.ScheduleEvent(EVENT_ENGAGE_PLAYERS, 2s);
                    break;
                case EVENT_ENGAGE_PLAYERS:
                    me->SetReactState(REACT_AGGRESSIVE);
                    DoZoneInCombat();
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

struct npc_magmaw_blazing_bone_construct : public ScriptedAI
{
    npc_magmaw_blazing_bone_construct(Creature* creature) : ScriptedAI(creature), _instance(me->GetInstanceScript())
    {
        Initialize();
    }

    void Initialize()
    {
        me->SetReactState(REACT_PASSIVE);
        _armageddonTriggered = false;
    }

    void IsSummonedBy(Unit* /*summoner*/) override
    {
        // The movementId of this creature uses a speed value of 7 which is correct for most creatures that use the Id.
        // However, according to sniffs, this creature uses a speed of 10 so we have to manually set the speed until we know more about how movementIds select their speed
        me->SetSpeed(MOVE_RUN, 10.f);
        if (_instance->GetBossState(DATA_MAGMAW) == IN_PROGRESS)
        {
            for (uint8 i = 0; i < 20; i++)
            {
                Position const pos = me->GetRandomNearPosition(10.0f);
                me->CastSpell(Position{ pos.GetPositionX(), pos.GetPositionY(), pos.GetPositionZ() }, SPELL_IGNITION, true);
            }
            _events.ScheduleEvent(EVENT_ENGAGE_PLAYERS, 1s);
        }
        else
            me->DespawnOrUnsummon();
    }

    void JustSummoned(Creature* summon) override
    {
        if (summon->GetEntry() == NPC_IGNITION)
        {
            summon->m_Events.AddEventAtOffset([summon]()
            {
                summon->GetMotionMaster()->MoveCirclePath(summon->GetPositionX(), summon->GetPositionY(), summon->GetPositionZ(), 4.f, bool(urand(0, 1)), 7);
            }, 4s + 500ms);
        }
    }

    void JustDied(Unit* /*killer*/) override
    {
        _events.Reset();
        me->DespawnOrUnsummon(2s + 500ms);
    }

    void DamageTaken(Unit* /*attacker*/, uint32& damage) override
    {
        if (!_armageddonTriggered && me->HealthBelowPctDamaged(20, damage))
        {
            _armageddonTriggered = true;
            DoCastSelf(SPELL_ARMAGEDDON);
        }
    }

    void UpdateAI(uint32 diff) override
    {
        UpdateVictim();

        _events.Update(diff);

        if (me->HasUnitState(UNIT_STATE_CASTING))
            return;

        while (uint32 eventId = _events.ExecuteEvent())
        {
            switch (eventId)
            {
                case EVENT_ENGAGE_PLAYERS:
                    me->SetReactState(REACT_AGGRESSIVE);
                    DoZoneInCombat();
                    _events.ScheduleEvent(EVENT_FIERY_SLASH, 2s);
                    break;
                case EVENT_FIERY_SLASH:
                    DoCastVictim(SPELL_FIERY_SLASH);
                    _events.Repeat(2s, 8s);
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
    bool _armageddonTriggered;
};

class IsOnVehicleCheck
{
    public:
        IsOnVehicleCheck() { }

        bool operator()(WorldObject* object)
        {
            return object->ToUnit()->GetVehicle();
        }
};

class spell_magmaw_magma_spit: public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MAGMA_SPIT_MISSILE });
    }

    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.empty())
            return;

        targets.remove_if(IsOnVehicleCheck());

        if (targets.empty())
            return;

        Trinity::Containers::RandomResize(targets, GetCaster()->GetMap()->Is25ManRaid() ? 8 : 3);
    }

    void HandleHit(SpellEffIndex /*effIndex*/)
    {
        if (Unit* caster = GetCaster())
            caster->CastSpell(GetHitUnit(), SPELL_MAGMA_SPIT_MISSILE, true);
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_magmaw_magma_spit::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENEMY);
        OnEffectHitTarget.Register(&spell_magmaw_magma_spit::HandleHit, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

class VictimCheck
{
    public:
        VictimCheck(Unit* attacker) : _attacker(attacker)  { }

        bool operator()(WorldObject* object)
        {
            return (_attacker->GetVictim() && _attacker->GetVictim() != object->ToUnit());
        }
    private:
        Unit* _attacker;
};

class spell_magmaw_mangle : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_MANGLE_1 });
    }

    void FilterTargets(std::list<WorldObject*>& targets)
    {
        if (targets.empty())
            return;

        targets.remove_if(VictimCheck(GetCaster()));
    }

    void HandleHit(SpellEffIndex /*effIndex*/)
    {
        Unit* caster = GetCaster();
        if (!caster)
            return;

        Unit* target = GetHitUnit();
        caster->CastSpell(target, SPELL_MANGLE_1, true);
    }

    void Register() override
    {
        OnObjectAreaTargetSelect.Register(&spell_magmaw_mangle::FilterTargets, EFFECT_0, TARGET_UNIT_SRC_AREA_ENEMY);
        OnEffectHitTarget.Register(&spell_magmaw_mangle::HandleHit, EFFECT_0, SPELL_EFFECT_DUMMY);
    }
};

class spell_magmaw_pillar_of_flame_dummy : public SpellScript
{
    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo(
            {
                SPELL_PILLAR_OF_FLAME_MISSILE_PERIODIC,
                SPELL_PILLAR_OF_FLAME_PERIODIC
            });
    }

    void HandleHit(SpellEffIndex /*effIndex*/)
    {
        GetHitUnit()->CastSpell(GetHitUnit(), SPELL_PILLAR_OF_FLAME_MISSILE_PERIODIC);
        if (Unit* caster = GetCaster())
            caster->m_Events.AddEventAtOffset([caster]()
            {
                caster->CastSpell(caster, SPELL_PILLAR_OF_FLAME_PERIODIC);
            }, 2s);
    }

    void Register() override
    {
        OnEffectHitTarget.Register(&spell_magmaw_pillar_of_flame_dummy::HandleHit, EFFECT_1, SPELL_EFFECT_DUMMY);
    }
};

}

void AddSC_boss_magmaw()
{
    using namespace BlackwingDescent;
    using namespace BlackwingDescent::Magmaw;
    RegisterBlackwingDescentCreatureAI(boss_magmaw);
    RegisterBlackwingDescentCreatureAI(npc_magmaw_nefarian);
    RegisterBlackwingDescentCreatureAI(npc_magmaw_lava_parasite);
    RegisterBlackwingDescentCreatureAI(npc_magmaw_blazing_bone_construct);
    RegisterSpellScript(spell_magmaw_magma_spit);
    RegisterSpellScript(spell_magmaw_mangle);
    RegisterSpellScript(spell_magmaw_pillar_of_flame_dummy);
    AddSC_boss_magmaw_encounter_spells();
}
