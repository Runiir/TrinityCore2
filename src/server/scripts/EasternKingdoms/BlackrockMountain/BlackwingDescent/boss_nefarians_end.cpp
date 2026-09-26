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
#include "Log.h"
#include "MotionMaster.h"
#include "TemporarySummon.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "blackwing_descent.h"
#include "boss_nefarians_end.h"

namespace BlackwingDescent::NefariansEnd
{
struct OnyxiaChainData
{
    Position ComparisonPosition;
    uint32 ChainSpellId;
    uint32 LightningSpellId;
};

static OnyxiaChainData OnyxiaChainInfo[] =
{
    { { -141.3331f, -224.6247f }, SPELL_CHAINS_A_STEEL, SPELL_CHAINS_A_LIGHTNING },
    { { -90.35625f, -253.4714f }, SPELL_CHAINS_B_STEEL, SPELL_CHAINS_B_LIGHTNING },
    { { -90.22045f, -195.6071f }, SPELL_CHAINS_C_STEEL, SPELL_CHAINS_C_LIGHTNING }
};

Position const NefarianLiftOffPosition                          = { -162.076f,    -224.604f,    57.9262f   };
Position const NefarianElevatorPrepareLandPositionPhaseOne      = { -107.255753f, -223.944778f, 17.38522f  };
Position const NefarianElevatorLandPhaseOnePosition             = { -106.899124f, -225.162415f, 6.488089f  };
Position const NefarianElevatorCenterPosition                   = { -106.209747f, -224.530594f, 6.488089f  };
Position const NefarianElevatorLiftOffPosition                  = { -107.205688f, -224.597412f, 35.630280f };
Position const NefarianElevatorPrepareLandPositionPhaseThree    = { -107.238045f, -224.599579f, 17.629690f };
Position const NefarianElevatorLandPhaseThreePosition           = { -107.238045f, -224.599579f, 6.488089f  };

static constexpr uint32 const CyclicPathPoints = 17;
Position const NefarianCyclicPath[CyclicPathPoints] =
{
    { -162.076f,  -224.604f,  57.9262f  },
    { -169.3941f, -250.8021f, 91.78177f },
    { -154.9757f, -272.2014f, 92.11506f },
    { -132.934f,  -286.8906f, 92.25407f },
    { -106.7951f, -292.2639f, 93.06911f },
    { -81.66319f, -287.3004f, 93.81921f },
    { -59.42708f, -272.5538f, 94.29151f },
    { -44.60417f, -251.0191f, 94.40255f },
    { -39.86979f, -225.0208f, 93.93014f },
    { -44.62847f, -198.8733f, 94.15247f },
    { -59.65799f, -176.8993f, 94.81911f },
    { -81.1875f,  -162.474f,  94.70798f },
    { -107.0816f, -157.3715f, 94.20808f },
    { -132.8073f, -162.3507f, 93.4026f  },
    { -154.6771f, -177.1233f, 92.95815f },
    { -169.151f,  -199.1771f, 92.23587f },
    { -174.6406f, -225.2222f, 92.31927f }
};

static constexpr uint32 const CyclicRespawnPathPoints = 17;
Position const NefarianCyclicRespawnPath[CyclicRespawnPathPoints] =
{
    { -184.1267f, -224.5573f, 97.70717f },
    { -169.3941f, -250.8021f, 91.78177f },
    { -154.9757f, -272.2014f, 92.11506f },
    { -132.934f,  -286.8906f, 92.25407f },
    { -106.7951f, -292.2639f, 93.06911f },
    { -81.66319f, -287.3004f, 93.81921f },
    { -59.42708f, -272.5538f, 94.29151f },
    { -44.60417f, -251.0191f, 94.40255f },
    { -39.86979f, -225.0208f, 93.93014f },
    { -44.62847f, -198.8733f, 94.15247f },
    { -59.65799f, -176.8993f, 94.81911f },
    { -81.1875f,  -162.474f,  94.70798f },
    { -107.0816f, -157.3715f, 94.20808f },
    { -132.8073f, -162.3507f, 93.4026f  },
    { -154.6771f, -177.1233f, 92.95815f },
    { -169.151f,  -199.1771f, 92.23587f },
    { -174.6406f, -225.2222f, 92.31927f }
};

Position const ChromaticPrototypeSummonPositions[MaxChromaticPrototypes]
{
    { -183.972f,  -225.163f,  43.17013f, 0.05235988f },
    { -63.20486f, -135.6719f, 65.17735f, 4.29351f },
    { -62.87326f, -312.467f,  65.01746f, 2.007129f }
};

Position const ChromaticPrototypeMovePositions[MaxChromaticPrototypes]
{
    { -164.7852f, -224.4054f, 40.39833f },
    { -73.10334f, -156.7224f, 65.5925f  },
    { -72.80968f, -292.0725f, 65.65186f }
};

struct boss_nefarians_end : public BossAI
{
    boss_nefarians_end(Creature* creature) : BossAI(creature, DATA_NEFARIANS_END),
        _elevatorLowered(false), _encounterReset(instance->GetData(DATA_NEFARIANS_END_INTRO_DONE)),
        _nextElectrocuteHealthPercentage(90), _deadChromaticPrototypes(0)
    {
        me->AddUnitState(UNIT_STATE_IGNORE_PATHFINDING); // Remove this little workarround when mmaps for transports have arrived.
        me->SetReactState(REACT_PASSIVE);
    }

    void JustEngagedWith(Unit* who) override
    {
        // Attacking Nefarian while Onyxia is not engaged is not suposed to trigger anything
        if (instance->GetBossState(DATA_NEFARIANS_END) != IN_PROGRESS)
        {
            me->GetThreatManager().ClearAllThreat();
            me->CombatStop();
            return;
        }
        BossAI::JustEngagedWith(who);
    }

    void JustAppeared() override
    {
        events.SetPhase(PHASE_ONE);
        if (!_encounterReset)
        {
            events.ScheduleEvent(EVENT_CHAIN_ONYXIA, 1s, 0, PHASE_ONE);
            events.ScheduleEvent(EVENT_REMOVE_TRANSFORM_AURA, 26s + 700ms, 0, PHASE_ONE);
            me->SetDisableGravity(false);
            DoCastSelf(SPELL_INTRO_2_STALKER_TRANSFORM);
            DoCastSelf(SPELL_INTRO_3_SHRINK_AURA);
        }
        else
        {
            me->SetDisableGravity(true);
            me->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_IMMUNE_TO_NPC | UNIT_FLAG_IMMUNE_TO_PC | UNIT_FLAG_NOT_SELECTABLE);
            me->GetMotionMaster()->MoveCyclicPath(NefarianCyclicRespawnPath, CyclicRespawnPathPoints, false, true, 14.0f);
            DoCastSelf(SPELL_INTRO_5A_START_FIGHT_PROC);
            SetupTransportSpawns(SUMMON_GROUP_CONTROLLER_STALKER);

        }
        SetupTransportSpawns(SUMMON_GROUP_ELEVATOR);
    }

    void EnterEvadeMode(EvadeReason /*why*/) override
    {
        _EnterEvadeMode();
        DisengageLightningMachine();
        instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, me);

        if (events.IsInPhase(PHASE_TWO) && !_elevatorLowered)
            instance->SetData(DATA_RESET_ELEVATOR, events.GetTimeUntilEvent(EVENT_ELEVATOR_LOWERED));
        else if (GameObject* transport = GetElevator())
            transport->SetGoState(GOState(GO_STATE_TRANSPORT_ACTIVE + AsUnderlyingType(TRANSPORT_STOP_FRAME_RAISED)));

        if (Creature* onyxia = instance->GetCreature(DATA_ONYXIA))
            if (onyxia->IsAlive())
                instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, onyxia);

        for (ObjectGuid summon : summons)
        {
            if (Creature* creature = instance->instance->GetCreature(summon))
                if (creature->GetEntry() == NPC_CHROMATIC_PROTOTYPE && creature->IsAlive())
                    instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, creature);
        }

        summons.DespawnAll();
        instance->SetBossState(DATA_NEFARIANS_END, FAIL);
        instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_EXPLOSIVE_CINDERS);
        instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_DOMINION_OVERRIDE_ACTION_BAR);
        me->DespawnOrUnsummon();
    }

    void KilledUnit(Unit* who) override
    {
        if (who->GetTypeId() == TYPEID_PLAYER)
            Talk(SAY_SLAY);
    }

    // Nefarian's Lightning Machine (51089, an instance creature, not one of
    // his summons) enters combat with the raid through its Electrocute casts
    // and stays there once the fight is over. Round 8's kill left it in
    // combat for 12 minutes: the raid never left combat, the fallen could not
    // release and the route never completed. The encounter over (killed or
    // reset), the machine leaves combat.
    void DisengageLightningMachine()
    {
        if (Creature* machine = instance->GetCreature(DATA_NEFARIANS_LIGHTNING_MACHINE))
        {
            machine->InterruptNonMeleeSpells(false);
            machine->CombatStop(true);
            TC_LOG_INFO("server.nefarians_end", "NefariansEnd lightning_machine disengaged machine=%s in_combat=%d",
                machine->GetGUID().ToString().c_str(), int(machine->IsInCombat()));
        }
    }

    void JustDied(Unit* /*killer*/) override
    {
        _JustDied();
        DisengageLightningMachine();
        Talk(SAY_DEATH);
        instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, me);
        instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_EXPLOSIVE_CINDERS);
        instance->DoRemoveAurasDueToSpellOnPlayers(SPELL_DOMINION_OVERRIDE_ACTION_BAR);
    }

    void JustSummoned(Creature* summon) override
    {
        summons.Summon(summon);
        // keeping the summon list clean because we have to deal with many tempoary summons
        summons.RemoveNotExisting();

        switch (summon->GetEntry())
        {
            case NPC_DOMINION_STALKER:
                summon->CastSpell(summon, SPELL_DOMINION_DETERMINE_FARTHEST_PORTAL_STALKER);
                break;
            default:
                break;
        }
    }

    void MovementInform(uint32 type, uint32 id) override
    {
        // Round 7 instrumentation (landing chain: MoveLand, this inform,
        // EVENT_LANDED, ACTION_NEFARIAN_LANDED, Onyxia's receipt).
        if (id == POINT_PREPARE_LANDING || id == POINT_LAND)
            TC_LOG_INFO("server.nefarians_end", "NefariansEnd nefarian movement_inform nefarian=%s type=%u id=%u phase_one=%d phase_three=%d z=%.3f passenger=%d",
                me->GetGUID().ToString().c_str(), type, id, int(events.IsInPhase(PHASE_ONE)),
                int(events.IsInPhase(PHASE_THREE)), me->GetPositionZ(), int(me->GetTransport() != nullptr));
        if (type != POINT_MOTION_TYPE && type != EFFECT_MOTION_TYPE)
            return;

        switch (id)
        {
            case POINT_LIFTOFF:
                me->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_IMMUNE_TO_NPC | UNIT_FLAG_IMMUNE_TO_PC);
                DoCastSelf(SPELL_INTRO_5A_START_FIGHT_PROC);
                me->GetMotionMaster()->MoveCyclicPath(NefarianCyclicPath, CyclicPathPoints, false, true, 14.0f);

                if (Creature* machine = instance->GetCreature(DATA_NEFARIANS_LIGHTNING_MACHINE))
                    machine->CastSpell(machine, SPELL_ELECTROCUTE);

                if (Creature* onyxia = instance->GetCreature(DATA_ONYXIA))
                    if (onyxia->IsAIEnabled())
                        onyxia->AI()->DoAction(ACTION_REANIMATED);

                SetupTransportSpawns(SUMMON_GROUP_CONTROLLER_STALKER);

                for (ObjectGuid guid : summons)
                {
                    if (Creature* stalker = instance->instance->GetCreature(guid))
                    {
                        if (stalker->GetEntry() == NPC_INVISIBLE_STALKER_CATACLYSM_BOSS)
                        {
                            for (OnyxiaChainData const& data : OnyxiaChainInfo)
                            {
                                if (stalker->GetExactDist2d(data.ComparisonPosition) < 1.0f)
                                {
                                    stalker->InterruptNonMeleeSpells(true);
                                    stalker->CastSpell(stalker, data.LightningSpellId);
                                }
                            }
                        }
                    }
                }
                break;
            case POINT_PREPARE_LANDING:
                if (events.IsInPhase(PHASE_ONE))
                    events.ScheduleEvent(EVENT_LAND_PHASE_ONE, 200ms, 0, PHASE_ONE);
                else if (events.IsInPhase(PHASE_THREE))
                    events.ScheduleEvent(EVENT_LAND_PHASE_THREE, 200ms, 0, PHASE_THREE);
                break;
            case POINT_LAND:
                events.ScheduleEvent(EVENT_LANDED, 400ms);
                break;
            case POINT_ELEVATOR_CENTER:
                events.ScheduleEvent(EVENT_LIFTOFF_PHASE_TWO, 1s, 0, PHASE_TWO);
                break;
            default:
                break;
        }
    }

    void DamageTaken(Unit* /*attacker*/, uint32& damage) override
    {
        // Do not allow Nefarian to die before he raised the platform again
        if (damage >= me->GetHealth() && !events.IsInPhase(PHASE_THREE))
            damage = 0;

        if (damage >= me->GetHealth())
            return;

        if (me->HealthBelowPctDamaged(_nextElectrocuteHealthPercentage, damage))
        {
            Talk(SAY_ANNOUNCE_AIR_CRACKLES);
            events.ScheduleEvent(EVENT_ELECTROCUTE, 5s);
            _nextElectrocuteHealthPercentage -= 10;
        }
    }

    void OnSpellCastFinished(SpellInfo const* spell, SpellFinishReason reason) override
    {
        if (reason != SPELL_FINISHED_SUCCESSFUL_CAST)
            return;

        switch (spell->Id)
        {
            case SPELL_BRUSHFIRE_START:
                Talk(SAY_SHADOWBLAZE_SPARK);
                break;
            case SPELL_DOMINION_OVERRIDE_ACTION_BAR:
                Talk(SAY_DOMINION);
                break;
            default:
                break;
        }
    }

    void DoAction(int32 action) override
    {
        switch (action)
        {
            case ACTION_ONYXIA_ENGAGED:
                Talk(SAY_HAIL_OF_BONES);
                DoCastSelf(SPELL_ELECTRICAL_CHARGE_NEFARIAN);
                DoCastSelf(SPELL_HAIL_OF_BONES);
                events.ScheduleEvent(EVENT_PREPARE_LANDING, 24s, 0, PHASE_ONE);
                events.ScheduleEvent(EVENT_BERSERK, 10min + 30s);
                break;
            case ACTION_ONYXIA_DIED:
                events.ScheduleEvent(EVENT_SAY_ONYXIA_DEAD, 1ms, 0, PHASE_ONE);
                break;
            default:
                break;
        }
    }

    void SummonedCreatureDies(Creature* summon, Unit* /*killer*/) override
    {
        switch (summon->GetEntry())
        {
            case NPC_CHROMATIC_PROTOTYPE:
                // Nefarian enters phase three when the first Chromatic Prototype has died on heroic difficulty
                if (IsHeroic())
                    events.ScheduleEvent(EVENT_ENTER_PHASE_THREE, 1ms, 0, PHASE_TWO);
                else
                {
                    _deadChromaticPrototypes++;
                    if (_deadChromaticPrototypes == 3)
                        events.ScheduleEvent(EVENT_ENTER_PHASE_THREE, 1ms, 0, PHASE_TWO);
                }
                break;
            default:
                break;
        }
    }

    void UpdateAI(uint32 diff) override
    {
        if (!UpdateVictim() && !events.IsInPhase(PHASE_ONE))
            return;

        events.Update(diff);

        if (me->HasUnitState(UNIT_STATE_CASTING))
            return;

        while (uint32 eventId = events.ExecuteEvent())
        {
            switch (eventId)
            {
                case EVENT_CHAIN_ONYXIA:
                    for (ObjectGuid guid : summons)
                    {
                        if (Creature* stalker = ObjectAccessor::GetCreature(*me, guid))
                            if (stalker->GetEntry() == NPC_INVISIBLE_STALKER_CATACLYSM_BOSS)
                                for (OnyxiaChainData const& data : OnyxiaChainInfo)
                                    if (stalker->GetExactDist2d(data.ComparisonPosition) < 1.0f)
                                        stalker->CastSpell(stalker, data.ChainSpellId);
                    }
                    break;
                case EVENT_REMOVE_TRANSFORM_AURA:
                    me->RemoveAurasDueToSpell(SPELL_INTRO_2_STALKER_TRANSFORM);
                    me->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NOT_SELECTABLE);
                    me->SetDisableGravity(true);
                    events.ScheduleEvent(EVENT_LIFT_OFF, 2s, 0, PHASE_ONE);
                    break;
                case EVENT_LIFT_OFF:
                    DoCastSelf(SPELL_INTRO_4_LIFT_OFF_ANIM_KIT);
                    me->RemoveAurasDueToSpell(SPELL_INTRO_3_SHRINK_AURA);
                    events.ScheduleEvent(EVENT_ANNOUNCE_AIR_CRACKLES, 8s + 500ms, 0, PHASE_ONE);
                    break;
                case EVENT_ANNOUNCE_AIR_CRACKLES:
                    Talk(SAY_ANNOUNCE_AIR_CRACKLES);
                    me->GetMotionMaster()->MovePoint(POINT_LIFTOFF, NefarianLiftOffPosition, false);
                    break;
                case EVENT_PREPARE_LANDING:
                {
                    Position pos = events.IsInPhase(PHASE_ONE) ? NefarianElevatorPrepareLandPositionPhaseOne : NefarianElevatorPrepareLandPositionPhaseThree;
                    me->GetMotionMaster()->MovePoint(POINT_PREPARE_LANDING, pos, false);
                    break;
                }
                case EVENT_LAND_PHASE_ONE:
                    if (GameObject* elevator = GetElevator())
                    {
                        if (TransportBase* transport = elevator->ToTransportBase())
                        {
                            transport->AddPassenger(me);
                            transport->UpdatePassengerPosition(me->GetMap(), me, me->GetPositionX(), me->GetPositionY(), me->GetPositionZ(), me->GetOrientation(), true);
                        }
                    }

                    me->GetMotionMaster()->MoveLand(POINT_LAND, NefarianElevatorLandPhaseOnePosition);
                    TC_LOG_INFO("server.nefarians_end", "NefariansEnd nefarian move_land nefarian=%s z=%.3f passenger=%d",
                        me->GetGUID().ToString().c_str(), me->GetPositionZ(), int(me->GetTransport() != nullptr));
                    break;
                case EVENT_LANDED:
                    me->SetDisableGravity(false);
                    TC_LOG_INFO("server.nefarians_end", "NefariansEnd nefarian landed nefarian=%s phase_one=%d phase_three=%d",
                        me->GetGUID().ToString().c_str(), int(events.IsInPhase(PHASE_ONE)), int(events.IsInPhase(PHASE_THREE)));

                    if (events.IsInPhase(PHASE_ONE))
                    {
                        DoCastSelf(SPELL_SHADOW_OF_COWARDICE);
                        DoZoneInCombat();
                        instance->SendEncounterUnit(ENCOUNTER_FRAME_ENGAGE, me, FRAME_INDEX_NEFARIAN);
                        events.ScheduleEvent(EVENT_ENGAGE_PLAYERS, 2s, 0, PHASE_ONE);
                        Creature* onyxia = instance->GetCreature(DATA_ONYXIA);
                        TC_LOG_INFO("server.nefarians_end", "NefariansEnd nefarian landed_signal nefarian=%s onyxia=%s ai_enabled=%d ai=%p",
                            me->GetGUID().ToString().c_str(), onyxia ? onyxia->GetGUID().ToString().c_str() : "none",
                            int(onyxia && onyxia->IsAIEnabled()), onyxia ? static_cast<void const*>(onyxia->AI()) : nullptr);
                        if (onyxia && onyxia->IsAIEnabled())
                            onyxia->AI()->DoAction(ACTION_NEFARIAN_LANDED);
                    }
                    else if (events.IsInPhase(PHASE_THREE))
                        events.ScheduleEvent(EVENT_ENGAGE_PLAYERS, 2s, 0, PHASE_THREE);
                    break;
                case EVENT_ENGAGE_PLAYERS:
                    me->SetReactState(REACT_AGGRESSIVE);

                    if (events.IsInPhase(PHASE_ONE))
                    {
                        DoCastSelf(SPELL_CHILDREN_OF_DEATHWING_NEFARIAN);
                        if (Creature* onyxia = instance->GetCreature(DATA_ONYXIA))
                            onyxia->CastSpell(onyxia, SPELL_CHILDREN_OF_DEATHWING_ONYXIA, true);

                        events.ScheduleEvent(EVENT_TAIL_LASH, 18s, 0, PHASE_ONE);
                        events.ScheduleEvent(EVENT_SHADOWFLAME_BREATH, 9s, 10s, 0, PHASE_ONE);

                        if (IsHeroic())
                            events.ScheduleEvent(EVENT_DOMINION, 13s, 0, PHASE_ONE);
                    }
                    else if (events.IsInPhase(PHASE_THREE))
                    {
                        DoCastSelf(SPELL_SHADOW_OF_COWARDICE);
                        DoCastSelf(SPELL_BRUSHFIRE_PRE_START_PERIODIC);
                        events.ScheduleEvent(EVENT_SHADOWFLAME_BREATH, 9s, 0, PHASE_THREE);
                        events.ScheduleEvent(EVENT_TAIL_LASH, 1s, 0, PHASE_THREE);
                    }
                    break;
                case EVENT_TAIL_LASH:
                    DoCastSelf(SPELL_TAIL_LASH);
                    if (events.IsInPhase(PHASE_ONE))
                        events.Repeat(5s);
                    else if (events.IsInPhase(PHASE_THREE))
                        events.Repeat(15s, 22s);
                    break;
                case EVENT_SHADOWFLAME_BREATH:
                    DoCastVictim(SPELL_SHADOWFLAME_BREATH);

                    if (events.IsInPhase(PHASE_ONE))
                        events.Repeat(9s, 14s);
                    else if (events.IsInPhase(PHASE_THREE))
                        events.Repeat(17s, 22s);
                    break;
                case EVENT_SAY_ONYXIA_DEAD:
                    me->AttackStop();
                    me->SetReactState(REACT_PASSIVE);
                    me->RemoveAurasDueToSpell(SPELL_CHILDREN_OF_DEATHWING_NEFARIAN);
                    me->RemoveAurasDueToSpell(SPELL_ELECTRICAL_CHARGE_NEFARIAN);
                    me->RemoveAurasDueToSpell(SPELL_SHADOW_OF_COWARDICE);
                    Talk(SAY_ONYXIA_DIED);
                    events.SetPhase(PHASE_TWO);
                    events.ScheduleEvent(EVENT_MOVE_TO_CENTER, 2s, 0, PHASE_TWO);
                    break;
                case EVENT_MOVE_TO_CENTER:
                    me->GetMotionMaster()->MovePoint(POINT_ELEVATOR_CENTER, NefarianElevatorCenterPosition);
                    break;
                case EVENT_LIFTOFF_PHASE_TWO:
                    DoCastSelf(SPELL_NEFARIAN_PHASE_2_HEALTH_AURA);
                    me->SetDisableGravity(true);
                    me->GetMotionMaster()->MovePoint(POINT_NONE, NefarianElevatorLiftOffPosition);
                    events.ScheduleEvent(EVENT_SUMMON_CHROMATIC_PROTOTYPES, 400ms, 0, PHASE_TWO);
                    events.ScheduleEvent(EVENT_LOWER_ELEVATOR, 800ms, 0, PHASE_TWO);
                    events.ScheduleEvent(EVENT_SAY_PHASE_TWO, 4s + 800ms, 0, PHASE_TWO);
                    events.ScheduleEvent(EVENT_ENTER_PHASE_THREE, 2min + 30s, 0, PHASE_TWO);
                    events.ScheduleEvent(EVENT_SHADOWFLAME_BARRAGE, 2s + 500ms, 0, PHASE_TWO);

                    if (IsHeroic())
                        events.ScheduleEvent(EVENT_EXPLOSIVE_CINDERS, 2s, 0, PHASE_TWO);
                    break;
                case EVENT_SUMMON_CHROMATIC_PROTOTYPES:
                    for (uint8 i = 0; i < MaxChromaticPrototypes; i++)
                    {
                        if (Creature* prototype = DoSummon(NPC_CHROMATIC_PROTOTYPE, ChromaticPrototypeSummonPositions[i], 4000))
                        {
                            Position point = ChromaticPrototypeMovePositions[i];
                            prototype->m_Events.AddEventAtOffset([prototype, point]()
                            {
                                prototype->GetMotionMaster()->MovePoint(POINT_JUMP_DOWN, point);
                            }, 800ms);
                        }
                    }
                    break;
                case EVENT_LOWER_ELEVATOR:
                    if (GameObject* transport = GetElevator())
                        transport->SetGoState(GO_STATE_TRANSPORT_ACTIVE);
                    events.ScheduleEvent(EVENT_ELEVATOR_LOWERED, 9s, 0, PHASE_TWO);
                    break;
                case EVENT_ELEVATOR_LOWERED:
                    _elevatorLowered = true;
                    break;
                case EVENT_SHADOWFLAME_BARRAGE:
                    DoCastAOE(SPELL_SHADOWFLAME_BARRAGE);
                    events.Repeat(2s + 500ms);
                    break;
                case EVENT_SAY_PHASE_TWO:
                    Talk(SAY_MOLTEN_LAVA);
                    break;
                case EVENT_ENTER_PHASE_THREE:
                    if (!_elevatorLowered)
                    {
                        events.Repeat(1s);
                        break;
                    }
                    EnterPhaseThree();
                    break;
                case EVENT_SAY_PHASE_THREE:
                    Talk(SAY_LAND_PHASE_THREE);
                    break;
                case EVENT_LAND_PHASE_THREE:
                    if (me->GetHealthPct() > 50.f)
                        instance->DoUpdateWorldState(WORLD_STATE_ID_KEEPING_IT_IN_THE_FAMILY, 0);

                    me->RemoveAurasDueToSpell(SPELL_NEFARIAN_PHASE_2_HEALTH_AURA);
                    me->GetMotionMaster()->MoveLand(POINT_LAND, NefarianElevatorLandPhaseThreePosition);
                    break;
                case EVENT_ELECTROCUTE:
                    if (Creature* machine = instance->GetCreature(DATA_NEFARIANS_LIGHTNING_MACHINE))
                    {
                        machine->CastSpell(machine, SPELL_ELECTROCUTE);
                        machine->CastSpell(machine, SPELL_ELECTROCUTE_DAMAGE);
                    }

                    if (Creature* onyxia = instance->GetCreature(DATA_ONYXIA))
                        if (Aura* charge = onyxia->GetAura(SPELL_ELECTRICAL_CHARGE_ONYXIA))
                            charge->ModStackAmount(17, AuraRemoveFlags::ByDefault | AuraRemoveFlags::DontResetPeriodicTimer);
                    break;
                case EVENT_DOMINION:
                    DoCastAOE(SPELL_DOMINION_DUMMY);
                    events.Repeat(15s);
                    break;
                case EVENT_EXPLOSIVE_CINDERS:
                    DoCastAOE(SPELL_EXPLOSIVE_CINDERS);
                    events.Repeat(15s);
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
    /*
        This is a clusterfuck but required to make spawning on transports work properly. If we don't add creatures to transports before they are
        being sent out via update_object the passenger visual will not work so we wont see the passengers move with the transport. This will take care
        of it for now.
    */
    void SetupTransportSpawns(uint32 summonGroupId)
    {
        GameObject* elevator = instance->GetGameObject(DATA_BLACKWING_ELEVATOR_ONYXIA);
        if (!elevator)
            return;

        TransportBase* transport = elevator->ToTransportBase();
        if (!transport)
            return;

        std::vector<TempSummonData> const* summonGroupData = sObjectMgr->GetSummonGroup(me->GetEntry(), SUMMONER_TYPE_CREATURE, summonGroupId);
        if (!summonGroupData)
            return;

        Map* map = me->GetMap();
        for (TempSummonData const& data : *summonGroupData)
        {
            TempSummon* summon = new TempSummon(nullptr, me, false);
            if (!summon->Create(map->GenerateLowGuid<HighGuid::Unit>(), map, data.entry, data.pos, nullptr, 0, true))
            {
                delete summon;
                continue;
            }

            float x, y, z, o;
            data.pos.GetPosition(x, y, z, o);

            // Keeping the current transport position in mind for example if we spawn the units after a reset above the lava
            if (summonGroupId == SUMMON_GROUP_ELEVATOR)
                z += std::abs(elevator->GetPositionZ() - elevator->GetStationaryZ());

            transport->CalculatePassengerOffset(x, y, z, &o);
            summon->m_movementInfo.transport.pos.Relocate(x, y, z, o);
            transport->AddPassenger(summon);

            summon->Relocate(data.pos);
            summon->SetHomePosition(data.pos);
            summon->SetTransportHomePosition({ x, y, z, o });

            PhasingHandler::InheritPhaseShift(summon, me);

            if (!map->AddToMap<Creature>(summon))
            {
                // Returning false will cause the object to be deleted - remove from transport
                if (transport)
                    transport->RemovePassenger(summon);

                delete summon;
                continue;
            }

            summon->InitSummon();
        }
    }

    void EnterPhaseThree()
    {
        if (events.IsInPhase(PHASE_THREE))
            return;

        events.SetPhase(PHASE_THREE);
        events.ScheduleEvent(EVENT_SAY_PHASE_THREE, 14s + 700ms);
        events.ScheduleEvent(EVENT_PREPARE_LANDING, 15s + 500ms, 0, PHASE_THREE);
        if (GameObject* elevator = GetElevator())
            elevator->SetGoState(GOState(GO_STATE_TRANSPORT_ACTIVE + AsUnderlyingType(TRANSPORT_STOP_FRAME_RAISED)));

        for (ObjectGuid guid : summons)
        {
            if (Creature* creature = ObjectAccessor::GetCreature(*me, guid))
                if (creature->GetEntry() == NPC_CHROMATIC_PROTOTYPE &&  creature->IsAlive() && creature->IsAIEnabled())
                    creature->AI()->DoAction(ACTION_DISENGAGE_PLAYERS);
        }
    }

    GameObject* GetElevator()
    {
        return instance->GetGameObject(DATA_BLACKWING_ELEVATOR_ONYXIA);
    }

    bool _elevatorLowered;
    bool _encounterReset;
    uint8 _nextElectrocuteHealthPercentage;
    uint8 _deadChromaticPrototypes;
};

struct npc_nefarians_end_onyxia : public ScriptedAI
{
    npc_nefarians_end_onyxia(Creature* creature) : ScriptedAI(creature), _instance(me->GetInstanceScript()), _allowDeath(false), _chargeWarningLevel(0), _lethalClampCount(0)
    {
        me->AddUnitState(UNIT_STATE_IGNORE_PATHFINDING); // Remove this little workarround when mmaps for transports have arrived.
    }

    void JustAppeared() override
    {
        // Until Nefarian lands she cannot die (her template's unkillable
        // flag; cleared on ACTION_NEFARIAN_LANDED).
        me->SetUnkillable(true);
        if (_instance->GetData(DATA_NEFARIANS_END_INTRO_DONE))
            DoAction(ACTION_REANIMATED);
    }

    void JustEngagedWith(Unit* /*who*/) override
    {
        if (_instance->GetBossState(DATA_NEFARIANS_END) != IN_PROGRESS)
        {
            _instance->SetBossState(DATA_NEFARIANS_END, IN_PROGRESS);
            _instance->DoUpdateWorldState(WORLD_STATE_ID_KEEPING_IT_IN_THE_FAMILY, 1);
        }

        _instance->SendEncounterUnit(ENCOUNTER_FRAME_ENGAGE, me, FRAME_INDEX_ONYXIA);

        if (Creature* nefarian = _instance->GetCreature(DATA_NEFARIANS_END))
            nefarian->AI()->DoAction(ACTION_ONYXIA_ENGAGED);

        me->RemoveAurasDueToSpell(SPELL_ONYXIA_START_FIGHT_1_PERIODIC);
        DoCastSelf(SPELL_ELECTRICAL_CHARGE_ONYXIA);
        _events.ScheduleEvent(EVENT_TAIL_LASH, 20s);
        _events.ScheduleEvent(EVENT_SHADOWFLAME_BREATH, 11s, 12s);
        _events.ScheduleEvent(EVENT_LIGHTNING_DISCHARGE, 22s);

        if (Creature* controller = _instance->GetCreature(DATA_CONTROLLER_STALKER))
        {
            if (controller->IsAIEnabled())
                controller->AI()->DoZoneInCombat();

            controller->CastSpell(controller, SPELL_PET_HACK_1);
        }
    }

    void EnterEvadeMode(EvadeReason /*why*/) override
    {
        _EnterEvadeMode();
        if (Creature* nefarian = _instance->GetCreature(DATA_NEFARIANS_END))
            nefarian->AI()->EnterEvadeMode();
    }

    void JustDied(Unit* /*killer*/) override
    {
        _instance->SendEncounterUnit(ENCOUNTER_FRAME_DISENGAGE, me);
        if (Creature* nefarian = _instance->GetCreature(DATA_NEFARIANS_END))
            nefarian->AI()->DoAction(ACTION_ONYXIA_DIED);

        me->DespawnOrUnsummon(19s);
    }

    void DoAction(int32 action) override
    {
        switch (action)
        {
            case ACTION_REANIMATED:
                me->RemoveAurasDueToSpell(SPELL_PERMANENT_FEIGN_DEATH_1);
                me->RemoveFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_IMMUNE_TO_PC | UNIT_FLAG_IMMUNE_TO_NPC);
                me->HandleEmoteCommand(EMOTE_ONESHOT_ROAR);
                me->PlayDirectSound(SOUND_ID_ROAR);
                me->SetReactState(REACT_AGGRESSIVE);
                DoCastSelf(SPELL_ONYXIA_START_FIGHT_1_PERIODIC);
                break;
            case ACTION_UPDATE_ELECTRICAL_CHARGE:
                if (Aura* chargeAura = me->GetAura(SPELL_ELECTRICAL_CHARGE_ONYXIA))
                {
                    uint8 stacks = chargeAura->GetStackAmount();
                    if (stacks == chargeAura->GetSpellInfo()->StackAmount)
                    {
                        DoCastAOE(SPELL_ELECTRICAL_OVERLOAD);
                        stacks = 1;
                        _chargeWarningLevel = 0;
                        chargeAura->SetStackAmount(stacks);
                    }

                    if (stacks >= 50 && _chargeWarningLevel == 0)
                    {
                        Talk(SAY_ANNOUNCE_WARNING_1);
                        _chargeWarningLevel = 1;
                    }
                    else if (stacks >= 80 && _chargeWarningLevel != 2)
                    {
                        Talk(SAY_ANNOUNCE_WARNING_2);
                        _chargeWarningLevel = 2;
                    }

                    me->SetPower(POWER_ALTERNATE_POWER, stacks - 1);
                }
                break;
            case ACTION_NEFARIAN_LANDED:
                _allowDeath = true;
                // Round 8: the 4.3.4 sniffed creature_template StaticFlags of
                // Onyxia (sql/updates/world/4.3.4/2023_08_27_00_world.sql,
                // 0x5089000c) carry CREATURE_STATIC_FLAG_UNKILLABLE, which
                // Unit::DealDamage enforces after this AI's DamageTaken: the
                // r06 and r07 live attempts held her at 1 health until her
                // Electrical Charge reached 100 and Electrical Overload wiped
                // the raid. The flag is her "no death before Nefarian lands";
                // it goes with the landing, as _allowDeath does.
                me->SetUnkillable(false);
                TC_LOG_INFO("server.nefarians_end", "NefariansEnd onyxia landed_received onyxia=%s ai=%p allow_death=%d unkillable=%d health=%u",
                    me->GetGUID().ToString().c_str(), static_cast<void const*>(this), int(_allowDeath),
                    int(me->HasStaticFlag(CREATURE_STATIC_FLAG_UNKILLABLE)), me->GetHealth());
                break;
            default:
                break;
        }
    }

    void DamageTaken(Unit* /*attacker*/, uint32& damage) override
    {
        // Onyxia may not die before Nefarian has landed
        if (damage >= me->GetHealth() && !_allowDeath)
        {
            damage = me->GetHealth() - 1;
            // Round 7 instrumentation: the first live bot attempt held her at
            // 1 health for minutes with Nefarian landed and fighting.
            if (++_lethalClampCount == 1 || _lethalClampCount % 200 == 0)
                TC_LOG_INFO("server.nefarians_end", "NefariansEnd onyxia lethal_clamp onyxia=%s ai=%p allow_death=%d clamps=%u",
                    me->GetGUID().ToString().c_str(), static_cast<void const*>(this), int(_allowDeath), _lethalClampCount);
        }
    }

    void OnSpellCastFinished(SpellInfo const* spell, SpellFinishReason /*reason*/) override
    {
        switch (spell->Id)
        {
            case SPELL_LIGHTNING_DISCHARGE_CONE_FRONT:
                DoCastAOE(SPELL_LIGHTNING_DISCHARGE_DAMAGE);
                break;
            default:
                break;
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
                case EVENT_TAIL_LASH:
                    DoCastSelf(SPELL_TAIL_LASH);
                    _events.Repeat(17s, 18s);
                    break;
                case EVENT_SHADOWFLAME_BREATH:
                    DoCastVictim(SPELL_SHADOWFLAME_BREATH);
                    _events.Repeat(13s, 17s);
                    break;
                case EVENT_LIGHTNING_DISCHARGE:
                    DoCastSelf(SPELL_LIGHTNING_DISCHARGE);
                    _events.Repeat(22s);
                    break;
                default:
                    break;
            }
        }

        DoMeleeAttackIfReady();
    }

private:
    InstanceScript* _instance;
    EventMap _events;
    bool _allowDeath;
    uint32 _lethalClampCount;
    uint8 _chargeWarningLevel;
};
}

void AddSC_boss_nefarians_end_adds();
void AddSC_boss_nefarians_end_spells();

void AddSC_boss_nefarians_end()
{
    using namespace BlackwingDescent;
    using namespace BlackwingDescent::NefariansEnd;
    RegisterBlackwingDescentCreatureAI(boss_nefarians_end);
    RegisterBlackwingDescentCreatureAI(npc_nefarians_end_onyxia);
    AddSC_boss_nefarians_end_adds();
    AddSC_boss_nefarians_end_spells();
}
