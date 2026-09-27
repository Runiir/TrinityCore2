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
#include "DBCStores.h"
#include "GridNotifiers.h"
#include "InstanceScript.h"
#include "Map.h"
#include "MotionMaster.h"
#include "PassiveAI.h"
#include "ScriptedCreature.h"
#include "SpellMgr.h"
#include "TemporarySummon.h"
#include <limits>
#include <unordered_map>

namespace BlackwingDescent::Maloriak
{
#define SPELL_FLASH_FREEZE_STUN RAID_MODE<uint32>(77699, 92978, 92979, 92980)
#define SPELL_CONSUMING_FLAMES RAID_MODE<uint32>(77786, 92971, 92972, 92973)

enum Events
{
    // Maloriak
    EVENT_ARCANE_STORM = 1,
    EVENT_REMEDY,
    EVENT_RELEASE_ABERRATIONS,
    EVENT_FACE_TO_CAULDRON,
    EVENT_THROW_VIAL,
    EVENT_MOVE_TO_CAULDRON,
    EVENT_DRINK_BOTTLE,
    EVENT_IMBUED_BUFF,
    EVENT_EXPLODE_CAULDRON,
    EVENT_ATTACK_PLAYERS,
    EVENT_CONSUMING_FLAMES,
    EVENT_SCORCHING_BLAST,
    EVENT_BITING_CHILL,
    EVENT_FLASH_FREEZE,
    EVENT_ENTER_PHASE_TWO,
    EVENT_DRINK_ALL_BOTTLES,
    EVENT_UNSTABLE_MIX,
    EVENT_MAGMA_JETS,
    EVENT_ACID_NOVA,
    EVENT_ABSOLUTE_ZERO,
    EVENT_MOVE_AWAY_FROM_CAULDRON,
    EVENT_ENGULFING_DARKNESS,
    EVENT_VILE_SWILL,

    // Experiments
    EVENT_LEAP_OUT_OF_CHAMBER,

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

enum Phases
{
    PHASE_ONE = 1,
    PHASE_TWO = 2
};

enum MovePoints
{
    // Maloriak
    POINT_NONE      = 0,
    POINT_CAULDRON  = 1,

    // Experiments
    POINT_GROUND    = 1,

    // Lord Victor Nefarius
    POINT_LAND      = 1
};

enum Texts
{
    // Maloriak
    SAY_AGGRO               = 0,
    SAY_RED_VIAL            = 1,
    SAY_ANNOUNCE_RED_VIAL   = 2,
    SAY_BLUE_VIAL           = 3,
    SAY_ANNOUNCE_BLUE_VIAL  = 4,
    SAY_GREEN_VIAL          = 5,
    SAY_ANNOUNCE_GREEN_VIAL = 6,
    SAY_RELEASE_ABERRATIONS = 7,
    SAY_RELEASE_ALL_MINIONS = 8,
    SAY_SLAY                = 9,
    SAY_DEATH               = 10,

    // Lord Victor Nefarius
    SAY_MOCK_MALORIAK       = 0,
    SAY_THROW_BLACK_BOTTLE  = 1,
    SAY_ANNOUNCE_BLACK_VIAL = 2,
    SAY_MALORIAK_DEAD       = 3
};

// Release Aberrations frees three chamber creatures per successful cast; the
// 18-creature reserve therefore allows six successful casts.
constexpr uint8 MAX_SUCCESSFUL_ABERRATION_RELEASES = 6;

Position const CauldronMovePosition             = { -106.6782f, -475.4438f, 73.45684f };
Position const LordVictorNefariusSummonPosition = { -105.9514f, -494.0278f, 89.33157f, 1.605703f };
Position const LordVictorNefariusLandPosition   = { -105.9514f, -494.0278f, 73.44659f };

struct VialData
{
    uint8 SayTextId;
    uint8 AnnounceTextId;
    uint32 ThrowSpellId;
    uint32 DrinkSpellId;
    uint32 ImbuedSpellId;
};

std::unordered_map<uint8, VialData> vialData =
{
    { VIAL_RED,    { SAY_RED_VIAL,      SAY_ANNOUNCE_RED_VIAL,      SPELL_THROW_RED_BOTTLE,     SPELL_DRINK_RED_BOTTLE,    SPELL_FIRE_IMBUED   }},
    { VIAL_BLUE,   { SAY_BLUE_VIAL,     SAY_ANNOUNCE_BLUE_VIAL,     SPELL_THROW_BLUE_BOTTLE,    SPELL_DRINK_BLUE_BOTTLE,   SPELL_FROST_IMBUED  }},
    { VIAL_GREEN,  { SAY_GREEN_VIAL,    SAY_ANNOUNCE_GREEN_VIAL,    SPELL_THROW_GREEN_BOTTLE,   0,                         SPELL_SLIME_IMBUED  }},
    { VIAL_BLACK,  { 0,                 0,                          0,                          SPELL_DRINK_BLACK_BOTTLE,  SPELL_SHADOW_IMBUED  }},
};

// Vial published under a mechanic spell id: the throw spell of the vial, or
// the Black drink for the heroic Dark Magic vial thrown by Nefarius.
bool IsVialMechanicSpell(uint32 spellId, uint8 vial)
{
    switch (vial)
    {
        case VIAL_RED: return spellId == SPELL_THROW_RED_BOTTLE;
        case VIAL_BLUE: return spellId == SPELL_THROW_BLUE_BOTTLE;
        case VIAL_GREEN: return spellId == SPELL_THROW_GREEN_BOTTLE;
        case VIAL_BLACK: return spellId == SPELL_DRINK_BLACK_BOTTLE;
        case VIAL_RANDOM_RED_OR_BLUE:
            return spellId == SPELL_THROW_RED_BOTTLE
                || spellId == SPELL_THROW_BLUE_BOTTLE;
        default: return false;
    }
}

struct boss_maloriak : public BossAI
{
    // VIAL_GREEN is the cycle start: the first normal vial is the random
    // Red/Blue branch and heroic starts with Black. The former VIAL_RED start
    // made the first normal vial always Blue.
    boss_maloriak(Creature* creature) : BossAI(creature, DATA_MALORIAK),
        _currentVial(VIAL_GREEN), _usedVialsCount(0), _vialsPerCycle(IsHeroic() ? 3 : 2), _releasedAberrationsCount(0),
        _vialSequenceActive(false) { }

    void Reset() override
    {
        _Reset();
        me->MakeInterruptable(false);
        // Defensive. Maloriak's spawn (250112) has no spawn_group row, so it
        // is in the Default Group without compatibility mode and
        // _DespawnAtEvade respawns a new Creature with a new AI. Only a
        // compatibility-mode respawn (Creature::Respawn calls Reset on the
        // same AI) would otherwise keep the failed attempt's vial cycle and
        // release reserve.
        _currentVial = VIAL_GREEN;
        _usedVialsCount = 0;
        _releasedAberrationsCount = 0;
        _vialSequenceActive = false;
    }

    void JustAppeared() override
    {
        instance->instance->SpawnGroupSpawn(SPAWN_GROUP_GROWTH_CHAMBERS, true);
        me->SummonCreatureGroup(SUMMON_GROUP_EXPERIMENTS);
    }

    void JustEngagedWith(Unit* who) override
    {
        BossAI::JustEngagedWith(who);
        Talk(SAY_AGGRO);
        instance->SendEncounterUnit(ENCOUNTER_FRAME_ENGAGE, me);
        events.SetPhase(PHASE_ONE);
        events.ScheduleEvent(EVENT_FACE_TO_CAULDRON, 15s + 500ms, 0, PHASE_ONE);

        if (IsHeroic())
            DoSummon(NPC_LORD_VICTOR_NEFARIUS_MALORIAK, LordVictorNefariusSummonPosition, 0, TEMPSUMMON_MANUAL_DESPAWN);
    }

    void EnterEvadeMode(EvadeReason /*why*/) override
    {
        _EnterEvadeMode();
        instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, me);
        if (Creature* nefarius = instance->GetCreature(DATA_LORD_VICTOR_NEFARIUS_MALORIAK))
            nefarius->DespawnOrUnsummon();
        CleanupEncounter();
        _DespawnAtEvade();
    }

    void JustDied(Unit* /*killer*/) override
    {
        Talk(SAY_DEATH);
        instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, me);
        CleanupEncounter();
        _JustDied();

        if (Creature * nefarius = instance->GetCreature(DATA_LORD_VICTOR_NEFARIUS_MALORIAK))
            if (nefarius->IsAIEnabled())
                nefarius->AI()->DoAction(ACTION_MALORIAK_DEAD);
    }

    void KilledUnit(Unit* victim) override
    {
        if (victim->GetTypeId() == TYPEID_PLAYER)
            Talk(SAY_SLAY, victim);
    }

    void JustSummoned(Creature* summon) override
    {
        switch (summon->GetEntry())
        {
            case NPC_LORD_VICTOR_NEFARIUS_MALORIAK:
                break;
            case NPC_ABSOLUTE_ZERO:
                summon->GetMotionMaster()->MoveRandom(10.0f);
                summon->CastSpell(summon, SPELL_ABSOLUTE_ZERO_TRANSFORM);
                summons.Summon(summon);
                break;
            default:
                summons.Summon(summon);
                break;
        }
    }

    void OnSpellCastFinished(SpellInfo const* spell, SpellFinishReason reason) override
    {
        switch (spell->Id)
        {
            case SPELL_ARCANE_STORM:
                if (reason == SPELL_FINISHED_CHANNELING_COMPLETE || reason == SPELL_FINISHED_CANCELED)
                {
                    me->MakeInterruptable(false);
                    me->m_Events.KillAllEvents(true);
                }
                break;
            case SPELL_RELEASE_ABERRATIONS:
                me->MakeInterruptable(false);
                if (reason == SPELL_FINISHED_SUCCESSFUL_CAST)
                {
                    Talk(SAY_RELEASE_ABERRATIONS);
                    ++_releasedAberrationsCount;
                }
                break;
            default:
                break;
        }
    }

    void MovementInform(uint32 motionType, uint32 pointId) override
    {
        if (motionType != POINT_MOTION_TYPE && motionType != EFFECT_MOTION_TYPE)
            return;

        switch (pointId)
        {
            case POINT_CAULDRON:
                // A cauldron walk that began before the 25% transition must
                // not drink a colored vial in phase two.
                if (!events.IsInPhase(PHASE_TWO))
                    events.ScheduleEvent(EVENT_DRINK_BOTTLE, 1s + 500ms);
                break;
            default:
                break;
        }
    }

    void DoAction(int32 action) override
    {
        switch (action)
        {
            case ACTION_SCHEDULE_EVENTS_FOR_PHASE:
                _vialSequenceActive = false;
                if (events.IsInPhase(PHASE_TWO))
                    break;

                if (_currentVial != VIAL_BLACK)
                    events.ScheduleEvent(EVENT_ATTACK_PLAYERS, _currentVial != VIAL_GREEN ? 1ms : 4s);
                events.ScheduleEvent(EVENT_FACE_TO_CAULDRON, _currentVial == VIAL_BLACK ? 1min + 30s : 40s, 0, PHASE_ONE);

                switch (_currentVial)
                {
                    case VIAL_RED:
                        events.ScheduleEvent(EVENT_ARCANE_STORM, 15s + 500ms, 0, PHASE_ONE);
                        events.ScheduleEvent(EVENT_REMEDY, 20s + 500ms, 0, PHASE_ONE);
                        events.ScheduleEvent(EVENT_RELEASE_ABERRATIONS, 11s, 0, PHASE_ONE);
                        events.ScheduleEvent(EVENT_CONSUMING_FLAMES, 7s, 8s, 0, PHASE_ONE);
                        events.ScheduleEvent(EVENT_SCORCHING_BLAST, 19s, 22s, 0, PHASE_ONE);
                        break;
                    case VIAL_BLUE:
                        events.ScheduleEvent(EVENT_ARCANE_STORM, 6s, 0, PHASE_ONE);
                        events.ScheduleEvent(EVENT_REMEDY, 21s + 500ms, 0, PHASE_ONE);
                        events.ScheduleEvent(EVENT_RELEASE_ABERRATIONS, 14s + 500ms, 0, PHASE_ONE);
                        events.ScheduleEvent(EVENT_BITING_CHILL, 13s, 14s, 0, PHASE_ONE);
                        events.ScheduleEvent(EVENT_FLASH_FREEZE, 17s, 0, PHASE_ONE);
                        break;
                    case VIAL_GREEN:
                        if (Creature* cauldron = instance->GetCreature(DATA_CAULDRON_TRIGGER))
                        {
                            // According to sniffs, the cauldron stalker leaves combat after 8 seconds
                            cauldron->m_Events.AddEventAtOffset([cauldron]()
                            {
                                if (cauldron->IsAIEnabled())
                                    cauldron->AI()->EnterEvadeMode();
                            }, 8s);
                            cauldron->CastSpell(cauldron, SPELL_DEBILITATING_SLIME_DEBUFF);
                        }

                        events.ScheduleEvent(EVENT_ARCANE_STORM, 5s, 0, PHASE_ONE);
                        events.ScheduleEvent(EVENT_REMEDY, 7s + 500ms, 0, PHASE_ONE);
                        events.ScheduleEvent(EVENT_RELEASE_ABERRATIONS, 9s, 0, PHASE_ONE);
                        break;
                    case VIAL_BLACK:
                        me->GetMotionMaster()->MovePoint(POINT_NONE, me->GetHomePosition());
                        events.ScheduleEvent(EVENT_VILE_SWILL, 2s, 0, PHASE_ONE);
                        events.ScheduleEvent(EVENT_ENGULFING_DARKNESS, 8s, 0, PHASE_ONE);
                        break;
                    default:
                        break;
                }
                break;
            default:
                break;
        }
    }

    void DamageTaken(Unit* /*attacker*/, uint32& damage) override
    {
        if (me->HealthBelowPctDamaged(25, damage) && !events.IsInPhase(PHASE_TWO))
        {
            events.SetPhase(PHASE_TWO);
            // Cancel at the crossing itself, so no vial step can run in the
            // gap before EVENT_ENTER_PHASE_TWO executes.
            CancelVialVisitEvents();
            events.ScheduleEvent(EVENT_ENTER_PHASE_TWO, 1ms, 0, PHASE_TWO);
        }
    }

    // Read-only observation of the native schedule (UnitAI contract): the
    // remaining time of the next event that casts `spellId`, 0 while that
    // cast is in progress or overdue, uint32 max when nothing is scheduled.
    // Vial throw spells (and the Black drink) report the next cauldron visit
    // for the vial SelectNextVial will pick, or 0 for the vial being drunk.
    uint32 GetTimeUntilEncounterMechanic(uint32 spellId) const override
    {
        constexpr uint32 Unscheduled = std::numeric_limits<uint32>::max();
        bool const phaseTwo = events.IsInPhase(PHASE_TWO);
        auto untilEvent = [this](uint32 eventId) -> uint32
        {
            return TimeUntilScheduledEvent(events, eventId);
        };
        auto casting = [this](uint32 castSpellId)
        {
            return me->FindCurrentSpellBySpellId(castSpellId) != nullptr;
        };

        switch (spellId)
        {
            case SPELL_ARCANE_STORM:
                if (casting(SPELL_ARCANE_STORM))
                    return 0;
                return phaseTwo ? Unscheduled : untilEvent(EVENT_ARCANE_STORM);
            case SPELL_RELEASE_ABERRATIONS:
                if (casting(SPELL_RELEASE_ABERRATIONS))
                    return 0;
                if (phaseTwo || _releasedAberrationsCount >= MAX_SUCCESSFUL_ABERRATION_RELEASES)
                    return Unscheduled;
                return untilEvent(EVENT_RELEASE_ABERRATIONS);
            case SPELL_REMEDY:
                return phaseTwo ? Unscheduled : untilEvent(EVENT_REMEDY);
            case SPELL_SCORCHING_BLAST:
                return phaseTwo ? Unscheduled : untilEvent(EVENT_SCORCHING_BLAST);
            case 77786: // Consuming Flames, base id of every difficulty variant
                return phaseTwo ? Unscheduled : untilEvent(EVENT_CONSUMING_FLAMES);
            case SPELL_BITING_CHILL:
                return phaseTwo ? Unscheduled : untilEvent(EVENT_BITING_CHILL);
            case SPELL_FLASH_FREEZE_TARGETING:
                return phaseTwo ? Unscheduled : untilEvent(EVENT_FLASH_FREEZE);
            case SPELL_ENGULFING_DARKNESS:
                if (casting(SPELL_ENGULFING_DARKNESS))
                    return 0;
                return phaseTwo ? Unscheduled : untilEvent(EVENT_ENGULFING_DARKNESS);
            case SPELL_MAGMA_JETS_SCRIPT_EFFECT:
                if (casting(SPELL_MAGMA_JETS_SUMMON))
                    return 0;
                return phaseTwo ? untilEvent(EVENT_MAGMA_JETS) : Unscheduled;
            case SPELL_ACID_NOVA:
                return phaseTwo ? untilEvent(EVENT_ACID_NOVA) : Unscheduled;
            case SPELL_ABSOLUTE_ZERO:
                return phaseTwo ? untilEvent(EVENT_ABSOLUTE_ZERO) : Unscheduled;
            case SPELL_THROW_RED_BOTTLE:
            case SPELL_THROW_BLUE_BOTTLE:
            case SPELL_THROW_GREEN_BOTTLE:
            case SPELL_DRINK_BLACK_BOTTLE:
                if (phaseTwo)
                    return Unscheduled;
                if (_vialSequenceActive)
                    return IsVialMechanicSpell(spellId, _currentVial) ? 0 : Unscheduled;
                if (!IsVialMechanicSpell(spellId, SelectNextVial(_currentVial,
                        _usedVialsCount, _vialsPerCycle, IsHeroic())))
                    return Unscheduled;
                return untilEvent(EVENT_FACE_TO_CAULDRON);
            default:
                return Unscheduled;
        }
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
                case EVENT_ARCANE_STORM:
                {
                    me->MakeInterruptable(true);
                    DoCastSelf(SPELL_ARCANE_STORM);
                    Creature* maloriak = me;
                    me->m_Events.AddEventAtOffset([maloriak]() { maloriak->MakeInterruptable(false); }, 6s + 500ms);
                    events.Repeat(15s + 500ms, 17s);
                    break;
                }
                case EVENT_REMEDY:
                    DoCastSelf(SPELL_REMEDY);
                    events.Repeat(24s);
                    break;
                case EVENT_RELEASE_ABERRATIONS:
                    if (_releasedAberrationsCount < MAX_SUCCESSFUL_ABERRATION_RELEASES)
                    {
                        me->MakeInterruptable(true);
                        DoCastAOE(SPELL_RELEASE_ABERRATIONS);
                        events.Repeat(17s, 18s);
                    }
                    break;
                case EVENT_FACE_TO_CAULDRON:
                    events.Reset();
                    if (Creature* cauldron = instance->GetCreature(DATA_CAULDRON_TRIGGER))
                    {
                        me->AttackStop();
                        me->SetReactState(REACT_PASSIVE);
                        me->ClearUnitState(UNIT_STATE_ROOT);
                        me->SetFacingToObject(cauldron);

                        uint8 const nextVial = SelectNextVial(_currentVial, _usedVialsCount, _vialsPerCycle, IsHeroic());
                        _currentVial = nextVial == VIAL_RANDOM_RED_OR_BLUE ? uint8(urand(VIAL_RED, VIAL_BLUE)) : nextVial;

                        if (_currentVial != VIAL_BLACK)
                            Talk(vialData[_currentVial].SayTextId);
                        else if (Creature * nefarius = instance->GetCreature(DATA_LORD_VICTOR_NEFARIUS_MALORIAK))
                            if (nefarius->IsAIEnabled())
                                nefarius->AI()->DoAction(ACTION_THROW_BLACK_BOTTLE);

                        _usedVialsCount = AdvanceUsedVials(_usedVialsCount, _vialsPerCycle);
                        _vialSequenceActive = true;
                        events.ScheduleEvent(EVENT_THROW_VIAL, 1s + 300ms, 0, PHASE_ONE);
                    }
                    break;
                case EVENT_THROW_VIAL:
                    if (_currentVial != VIAL_BLACK)
                    {
                        DoCastSelf(vialData[_currentVial].ThrowSpellId);
                        Talk(vialData[_currentVial].AnnounceTextId);
                    }
                    events.ScheduleEvent(EVENT_MOVE_TO_CAULDRON, 1s);
                    break;
                case EVENT_MOVE_TO_CAULDRON:
                    me->GetMotionMaster()->MovePoint(POINT_CAULDRON, CauldronMovePosition);
                    break;
                case EVENT_DRINK_BOTTLE:
                    DoCastSelf(vialData[_currentVial].DrinkSpellId);
                    events.ScheduleEvent(EVENT_IMBUED_BUFF, 2s + 500ms);

                    if (_currentVial == VIAL_GREEN)
                        events.ScheduleEvent(EVENT_EXPLODE_CAULDRON, 1s);
                    break;
                case EVENT_IMBUED_BUFF:
                    DoCastSelf(vialData[_currentVial].ImbuedSpellId);
                    DoAction(ACTION_SCHEDULE_EVENTS_FOR_PHASE);
                    break;
                case EVENT_EXPLODE_CAULDRON:
                    if (Creature* cauldron = instance->GetCreature(DATA_CAULDRON_TRIGGER))
                    {
                        cauldron->CastSpell(cauldron, SPELL_DEBILITATING_SLIME_CAST);
                        cauldron->CastSpell(cauldron, SPELL_DEBILITATING_SLIME_KNOCKBACK);
                    }
                    break;
                case EVENT_ATTACK_PLAYERS:
                    me->SetReactState(REACT_AGGRESSIVE);
                    break;
                case EVENT_CONSUMING_FLAMES:
                    if (Unit* target = SelectTarget(SELECT_TARGET_RANDOM, 0, 60.0f, true))
                        DoCast(target, SPELL_CONSUMING_FLAMES);
                    events.Repeat(14s + 500ms);
                    break;
                case EVENT_SCORCHING_BLAST:
                    DoCastVictim(SPELL_SCORCHING_BLAST);
                    events.Repeat(17s);
                    break;
                case EVENT_BITING_CHILL:
                   if (Unit* target = SelectTarget(SELECT_TARGET_RANDOM, 0, 60.0f, true))
                        DoCast(target, SPELL_BITING_CHILL);
                    events.Repeat(11s);
                    break;
                case EVENT_FLASH_FREEZE:
                    DoCastAOE(SPELL_FLASH_FREEZE_TARGETING);
                    events.Repeat(19s);
                    break;
                case EVENT_ENTER_PHASE_TWO:
                    CancelVialVisitEvents();
                    // Stop a cauldron (or heroic Black home) walk already in
                    // progress; the chase resumes after Unstable Mix.
                    if (me->GetMotionMaster()->GetCurrentMovementGeneratorType() == POINT_MOTION_TYPE)
                    {
                        me->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
                        me->StopMoving();
                    }
                    me->AttackStop();
                    me->SetReactState(REACT_PASSIVE);
                    Talk(SAY_RELEASE_ALL_MINIONS);
                    DoCastSelf(SPELL_RELEASE_ALL_MINIONS);
                    events.ScheduleEvent(EVENT_DRINK_ALL_BOTTLES, 5s, 0, PHASE_TWO);
                    break;
                case EVENT_DRINK_ALL_BOTTLES:
                    for (uint8 i = 0; i < VIAL_BLACK; i++)
                        me->RemoveAurasDueToSpell(vialData[i].ImbuedSpellId);

                    DoCastSelf(SPELL_DRINK_ALL_BOTTLES);
                    events.ScheduleEvent(EVENT_UNSTABLE_MIX, 2s + 300ms, 0, PHASE_TWO);
                    break;
                case EVENT_UNSTABLE_MIX:
                    DoCastSelf(SPELL_UNSTABLE_MIX);
                    me->ClearUnitState(UNIT_STATE_ROOT);
                    me->SetReactState(REACT_AGGRESSIVE);
                    // Phase-two cadence from 10N WCL kills (ledger
                    // wcl_10N_boss_timeline_*): after Unstable Mix, Magma Jets
                    // begin 3.5 s / 4.6 s, Acid Nova 6.5 s / 8.1 s, Absolute
                    // Zero 11.3 s in both kills. Repeats: Magma Jets
                    // begin-to-begin 12.4, 11.4, 11.8 s; Acid Nova 30.7 s;
                    // Absolute Zero 11.3, 11.3 s (VL3fW9wNm2PRJDYt fight 13).
                    // The evidence is 10N only: 25N/10H/25H keep the previous
                    // 8.4 s first Absolute Zero and 6/20/7 s repeats.
                    events.ScheduleEvent(EVENT_MAGMA_JETS, 3s + 500ms, 0, PHASE_TWO);
                    events.ScheduleEvent(EVENT_ACID_NOVA, 8s + 400ms, 0, PHASE_TWO);
                    events.ScheduleEvent(EVENT_ABSOLUTE_ZERO,
                        IsTenNormal() ? Milliseconds(11s + 300ms) : Milliseconds(8s + 400ms), 0, PHASE_TWO);
                    break;
                case EVENT_MAGMA_JETS:
                    DoCastAOE(SPELL_MAGMA_JETS_SCRIPT_EFFECT);
                    events.Repeat(IsTenNormal() ? Milliseconds(11s + 800ms) : Milliseconds(6s));
                    break;
                case EVENT_ACID_NOVA:
                    DoCastAOE(SPELL_ACID_NOVA);
                    events.Repeat(IsTenNormal() ? Milliseconds(30s + 700ms) : Milliseconds(20s));
                    break;
                case EVENT_ABSOLUTE_ZERO:
                    if (Unit* target = SelectTarget(SELECT_TARGET_RANDOM, 0, 60.0f, true))
                        DoCast(target, SPELL_ABSOLUTE_ZERO);
                    events.Repeat(IsTenNormal() ? Milliseconds(11s + 300ms) : Milliseconds(7s));
                    break;
                case EVENT_ENGULFING_DARKNESS:
                    if (me->GetReactState() == REACT_PASSIVE)
                    {
                        me->AddUnitState(UNIT_STATE_ROOT);
                        me->SetReactState(REACT_AGGRESSIVE);
                    }
                    DoCastSelf(SPELL_ENGULFING_DARKNESS);
                    events.Repeat(12s + 500ms);
                    break;
                case EVENT_VILE_SWILL:
                    DoCastSelf(SPELL_VILE_SWILL);
                    break;
                default:
                    break;
            }
        }

        DoMeleeAttackIfReady();
    }
private:
    uint8 _currentVial;
    uint8 _usedVialsCount;
    uint8 _vialsPerCycle;
    uint8 _releasedAberrationsCount;
    // True from the cauldron facing until the imbued buff schedules the
    // vial's abilities (or phase two cancels the visit).
    bool _vialSequenceActive;

    // Phase-two cadence evidence comes from 10N WCL kills only.
    bool IsTenNormal() const { return GetDifficulty() == RAID_DIFFICULTY_10MAN_NORMAL; }

    // The vial pipeline events carry no phase mask. A 25% crossing during a
    // cauldron visit must not finish that visit (walk, drink, colored imbue,
    // green slime, early attack) inside phase two.
    void CancelVialVisitEvents()
    {
        for (uint32 vialEvent : { EVENT_MOVE_TO_CAULDRON, EVENT_DRINK_BOTTLE, EVENT_IMBUED_BUFF,
                EVENT_EXPLODE_CAULDRON, EVENT_ATTACK_PLAYERS })
            events.CancelEvent(vialEvent);
        _vialSequenceActive = false;
    }

    void CleanupEncounter()
    {
        instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_FLASH_FREEZE_STUN);
        instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_BITING_CHILL);
        instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_CONSUMING_FLAMES);
        instance->instance->SpawnGroupDespawn(SPAWN_GROUP_GROWTH_CHAMBERS);
        summons.DespawnAll();
    }
};

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

void AddSC_boss_maloriak()
{
    using namespace BlackwingDescent;
    using namespace BlackwingDescent::Maloriak;
    RegisterBlackwingDescentCreatureAI(boss_maloriak);
    RegisterBlackwingDescentCreatureAI(npc_maloriak_flash_freeze);
    RegisterBlackwingDescentCreatureAI(npc_maloriak_experiment);
    RegisterBlackwingDescentCreatureAI(npc_maloriak_magma_jet);
    RegisterBlackwingDescentCreatureAI(npc_maloriak_lord_victor_nefarius);
    RegisterBlackwingDescentCreatureAI(npc_maloriak_vile_swill);
    // The spell scripts live in boss_maloriak_spells.cpp; registering them
    // here keeps the Eastern Kingdoms script loader unchanged.
    AddSC_boss_maloriak_spells();
}
