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
#include "CellImpl.h"
#include "CharmInfo.h"
#include "CombatAI.h"
#include "Containers.h"
#include "CreatureTextMgr.h"
#include "GameEventMgr.h"
#include "GridNotifiersImpl.h"
#include "Log.h"
#include "MotionMaster.h"
#include "MoveSplineInit.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "PassiveAI.h"
#include "Pet.h"
#include "PetAI.h"
#include "ScriptedEscortAI.h"
#include "ScriptedGossip.h"
#include "SmartAI.h"
#include "SpellAuras.h"
#include "SpellHistory.h"
#include "SpellMgr.h"
#include "Vehicle.h"
#include "World.h"
#include "WorldObjectMovement.h"

namespace NpcSpecial
{/*######
## npc_argent_squire/gruntling
######*/

enum Pennants
{
    SPELL_DARNASSUS_PENNANT     = 63443,
    SPELL_EXODAR_PENNANT        = 63439,
    SPELL_GNOMEREGAN_PENNANT    = 63442,
    SPELL_IRONFORGE_PENNANT     = 63440,
    SPELL_STORMWIND_PENNANT     = 62727,
    SPELL_SENJIN_PENNANT        = 63446,
    SPELL_UNDERCITY_PENNANT     = 63441,
    SPELL_ORGRIMMAR_PENNANT     = 63444,
    SPELL_SILVERMOON_PENNANT    = 63438,
    SPELL_THUNDERBLUFF_PENNANT  = 63445,
    SPELL_AURA_POSTMAN_S        = 67376,
    SPELL_AURA_SHOP_S           = 67377,
    SPELL_AURA_BANK_S           = 67368,
    SPELL_AURA_TIRED_S          = 67401,
    SPELL_AURA_BANK_G           = 68849,
    SPELL_AURA_POSTMAN_G        = 68850,
    SPELL_AURA_SHOP_G           = 68851,
    SPELL_AURA_TIRED_G          = 68852,
    SPELL_TIRED_PLAYER          = 67334
};

enum ArgentPetGossipOptions
{
    GOSSIP_OPTION_BANK                            = 0,
    GOSSIP_OPTION_SHOP                            = 1,
    GOSSIP_OPTION_MAIL                            = 2,
    GOSSIP_OPTION_DARNASSUS_SENJIN_PENNANT        = 3,
    GOSSIP_OPTION_EXODAR_UNDERCITY_PENNANT        = 4,
    GOSSIP_OPTION_GNOMEREGAN_ORGRIMMAR_PENNANT    = 5,
    GOSSIP_OPTION_IRONFORGE_SILVERMOON_PENNANT    = 6,
    GOSSIP_OPTION_STORMWIND_THUNDERBLUFF_PENNANT  = 7
};

enum Misc
{
    NPC_ARGENT_SQUIRE  = 33238
};

struct ArgentPonyBannerSpells
{
    uint32 spellSquire;
    uint32 spellGruntling;
};

ArgentPonyBannerSpells const bannerSpells[5] =
{
    { SPELL_DARNASSUS_PENNANT, SPELL_SENJIN_PENNANT },
    { SPELL_EXODAR_PENNANT, SPELL_UNDERCITY_PENNANT },
    { SPELL_GNOMEREGAN_PENNANT, SPELL_ORGRIMMAR_PENNANT },
    { SPELL_IRONFORGE_PENNANT, SPELL_SILVERMOON_PENNANT },
    { SPELL_STORMWIND_PENNANT, SPELL_THUNDERBLUFF_PENNANT }
};

class npc_argent_squire_gruntling : public CreatureScript
{
public:
    npc_argent_squire_gruntling() : CreatureScript("npc_argent_squire_gruntling") { }

    struct npc_argent_squire_gruntlingAI : public ScriptedAI
    {
        npc_argent_squire_gruntlingAI(Creature* creature) : ScriptedAI(creature)
        {
            ScheduleTasks();
        }

        void ScheduleTasks()
        {
            _scheduler
                .Schedule(Seconds(1), [this](TaskContext /*context*/)
                {
                    if (Aura* ownerTired = me->GetOwner()->GetAura(SPELL_TIRED_PLAYER))
                        if (Aura* squireTired = me->AddAura(IsArgentSquire() ? SPELL_AURA_TIRED_S : SPELL_AURA_TIRED_G, me))
                            squireTired->SetDuration(ownerTired->GetDuration());
                })
                .Schedule(Seconds(1), [this](TaskContext context)
                {
                    if ((me->HasAura(SPELL_AURA_TIRED_S) || me->HasAura(SPELL_AURA_TIRED_G)) && me->HasFlag(UNIT_NPC_FLAGS, UNIT_NPC_FLAG_BANKER | UNIT_NPC_FLAG_MAILBOX | UNIT_NPC_FLAG_VENDOR))
                        me->RemoveFlag(UNIT_NPC_FLAGS, UNIT_NPC_FLAG_BANKER | UNIT_NPC_FLAG_MAILBOX | UNIT_NPC_FLAG_VENDOR);
                    context.Repeat();
                });
        }

        bool GossipSelect(Player* player, uint32 /*menuId*/, uint32 gossipListId) override
        {
            switch (gossipListId)
            {
                case GOSSIP_OPTION_BANK:
                {
                    me->SetFlag(UNIT_NPC_FLAGS, UNIT_NPC_FLAG_BANKER);
                    uint32 _bankAura = IsArgentSquire() ? SPELL_AURA_BANK_S : SPELL_AURA_BANK_G;
                    if (!me->HasAura(_bankAura))
                        DoCastSelf(_bankAura);

                    if (!player->HasAura(SPELL_TIRED_PLAYER))
                        player->CastSpell(player, SPELL_TIRED_PLAYER, true);
                    break;
                }
                case GOSSIP_OPTION_SHOP:
                {
                    me->SetFlag(UNIT_NPC_FLAGS, UNIT_NPC_FLAG_VENDOR);
                    uint32 _shopAura = IsArgentSquire() ? SPELL_AURA_SHOP_S : SPELL_AURA_SHOP_G;
                    if (!me->HasAura(_shopAura))
                        DoCastSelf(_shopAura);

                    if (!player->HasAura(SPELL_TIRED_PLAYER))
                        player->CastSpell(player, SPELL_TIRED_PLAYER, true);
                    break;
                }
                case GOSSIP_OPTION_MAIL:
                {
                    me->SetFlag(UNIT_NPC_FLAGS, UNIT_NPC_FLAG_MAILBOX);
                    player->GetSession()->SendShowMailBox(me->GetGUID());

                    uint32 _mailAura = IsArgentSquire() ? SPELL_AURA_POSTMAN_S : SPELL_AURA_POSTMAN_G;
                    if (!me->HasAura(_mailAura))
                        DoCastSelf(_mailAura);

                    if (!player->HasAura(SPELL_TIRED_PLAYER))
                        player->CastSpell(player, SPELL_TIRED_PLAYER, true);
                    break;
                }
                case GOSSIP_OPTION_DARNASSUS_SENJIN_PENNANT:
                case GOSSIP_OPTION_EXODAR_UNDERCITY_PENNANT:
                case GOSSIP_OPTION_GNOMEREGAN_ORGRIMMAR_PENNANT:
                case GOSSIP_OPTION_IRONFORGE_SILVERMOON_PENNANT:
                case GOSSIP_OPTION_STORMWIND_THUNDERBLUFF_PENNANT:
                    if (IsArgentSquire())
                        DoCastSelf(bannerSpells[gossipListId - 3].spellSquire, true);
                    else
                        DoCastSelf(bannerSpells[gossipListId - 3].spellGruntling, true);
                    break;
            }
            player->PlayerTalkClass->SendCloseGossip();
            return false;
        }

        void UpdateAI(uint32 diff) override
        {
            _scheduler.Update(diff);
        }

        bool IsArgentSquire() const { return me->GetEntry() == NPC_ARGENT_SQUIRE; }

    private:
        TaskScheduler _scheduler;
    };

    CreatureAI* GetAI(Creature *creature) const override
    {
        return new npc_argent_squire_gruntlingAI(creature);
    }
};

enum BountifulTable
{
    SEAT_TURKEY_CHAIR                       = 0,
    SEAT_CRANBERRY_CHAIR                    = 1,
    SEAT_STUFFING_CHAIR                     = 2,
    SEAT_SWEET_POTATO_CHAIR                 = 3,
    SEAT_PIE_CHAIR                          = 4,
    SEAT_FOOD_HOLDER                        = 5,
    SEAT_PLATE_HOLDER                       = 6,
    NPC_THE_TURKEY_CHAIR                    = 34812,
    NPC_THE_CRANBERRY_CHAIR                 = 34823,
    NPC_THE_STUFFING_CHAIR                  = 34819,
    NPC_THE_SWEET_POTATO_CHAIR              = 34824,
    NPC_THE_PIE_CHAIR                       = 34822,
    SPELL_CRANBERRY_SERVER                  = 61793,
    SPELL_PIE_SERVER                        = 61794,
    SPELL_STUFFING_SERVER                   = 61795,
    SPELL_TURKEY_SERVER                     = 61796,
    SPELL_SWEET_POTATOES_SERVER             = 61797
};

typedef std::unordered_map<uint32 /*Entry*/, uint32 /*Spell*/> ChairSpells;
ChairSpells const _chairSpells =
{
    { NPC_THE_CRANBERRY_CHAIR, SPELL_CRANBERRY_SERVER },
    { NPC_THE_PIE_CHAIR, SPELL_PIE_SERVER },
    { NPC_THE_STUFFING_CHAIR, SPELL_STUFFING_SERVER },
    { NPC_THE_TURKEY_CHAIR, SPELL_TURKEY_SERVER },
    { NPC_THE_SWEET_POTATO_CHAIR, SPELL_SWEET_POTATOES_SERVER },
};

class CastFoodSpell : public BasicEvent
{
    public:
        CastFoodSpell(Unit* owner, uint32 spellId) : _owner(owner), _spellId(spellId) { }

        bool Execute(uint64 /*execTime*/, uint32 /*diff*/) override
        {
            _owner->CastSpell(_owner, _spellId, true);
            return true;
        }

    private:
        Unit* _owner;
        uint32 _spellId;
};

class npc_bountiful_table : public CreatureScript
{
public:
    npc_bountiful_table() : CreatureScript("npc_bountiful_table") { }

    struct npc_bountiful_tableAI : public PassiveAI
    {
        npc_bountiful_tableAI(Creature* creature) : PassiveAI(creature) { }

        void PassengerBoarded(Unit* who, int8 seatId, bool /*apply*/) override
        {
            float x = 0.0f;
            float y = 0.0f;
            float z = 0.0f;
            float o = 0.0f;

            switch (seatId)
            {
                case SEAT_TURKEY_CHAIR:
                    x = 3.87f;
                    y = 2.07f;
                    o = 3.700098f;
                    break;
                case SEAT_CRANBERRY_CHAIR:
                    x = 3.87f;
                    y = -2.07f;
                    o = 2.460914f;
                    break;
                case SEAT_STUFFING_CHAIR:
                    x = -2.52f;
                    break;
                case SEAT_SWEET_POTATO_CHAIR:
                    x = -0.09f;
                    y = -3.24f;
                    o = 1.186824f;
                    break;
                case SEAT_PIE_CHAIR:
                    x = -0.18f;
                    y = 3.24f;
                    o = 5.009095f;
                    break;
                case SEAT_FOOD_HOLDER:
                case SEAT_PLATE_HOLDER:
                    if (Vehicle* holders = who->GetVehicleKit())
                        holders->InstallAllAccessories(true);
                    return;
                default:
                    break;
            }

            Movement::MoveSplineInit init(who);
            init.DisableTransportPathTransformations();
            init.MoveTo(x, y, z, false);
            init.SetFacing(o);
            who->GetMotionMaster()->LaunchMoveSpline(std::move(init), EVENT_VEHICLE_BOARD, MOTION_SLOT_CONTROLLED);
            who->m_Events.AddEvent(new CastFoodSpell(who, _chairSpells.at(who->GetEntry())), who->m_Events.CalculateTime(1000));
            if (Creature* creature = who->ToCreature())
                creature->SetDisplayFromModel(0);
        }
    };

    CreatureAI* GetAI(Creature* creature) const override
    {
        return new npc_bountiful_tableAI(creature);
    }
};

enum MageOrb
{
    EVENT_MOVE_FORWARD          = 1,
    EVENT_APPLY_PERIODIC_EFFECT = 2,
    EVENT_EARLY_EXPLOSION       = 3,
    EVENT_EXPLODE               = 4,

    SPELL_FLAME_ORB_AURA        = 82690,
    SPELL_FROSTFIRE_ORB_AURA    = 84717,
    SPELL_ORB_SELF_SNARE        = 82736,
    SPELL_FIRE_POWER_EXPLOSION  = 83619,
    SPELL_FIRE_POWER_R1         = 18459,
    NPC_FLAME_ORB               = 44214,
    NPC_FROSTFIRE_ORB           = 45322

};

// Frostfire Orb / Flaming Orb
 struct npc_mage_orb : public ScriptedAI
 {
     npc_mage_orb(Creature* creature) : ScriptedAI(creature) { }

     // This summon owns its motion; do not install generic idle owner-follow.
     void JustAppeared() override { }

     void AttackStart(Unit* /*target*/) override
     {
         // Calling MovePoint again to apply movement speed changes
         if (me->isMoving())
             me->GetMotionMaster()->MovePoint(0, pos, false);
     }

     void IsSummonedBy(Unit* summoner) override
     {
         pos = summoner->GetPosition();
         pos.m_positionZ += 2.0f; // increasing the height to avoid terrain hickups
         WorldObjectMovement::MovePositionToFirstCollision(*summoner, pos, 100.0f, 0.0f, false);
         events.ScheduleEvent(EVENT_MOVE_FORWARD, Milliseconds(1));
         events.ScheduleEvent(EVENT_APPLY_PERIODIC_EFFECT, Milliseconds(400));
         events.ScheduleEvent(EVENT_EARLY_EXPLOSION, Seconds(5));
         events.ScheduleEvent(EVENT_EXPLODE, Seconds(15) + Milliseconds(400));
     }

     void UpdateAI(uint32 diff) override
     {
         events.Update(diff);

         if (uint32 eventId = events.ExecuteEvent())
         {
             switch (eventId)
             {
                 case EVENT_MOVE_FORWARD:
                     me->GetMotionMaster()->Clear();
                     me->GetMotionMaster()->MovePoint(0, pos, false);
                     break;
                 case EVENT_APPLY_PERIODIC_EFFECT:
                     DoCastSelf(me->GetEntry() == NPC_FLAME_ORB ? SPELL_FLAME_ORB_AURA : SPELL_FROSTFIRE_ORB_AURA, true);
                     break;
                 case EVENT_EARLY_EXPLOSION:
                     if (!me->IsInCombat() && !me->HasAura(SPELL_ORB_SELF_SNARE))
                         if (Unit* summoner = me->ToTempSummon()->GetSummoner())
                             if (Aura* aura = summoner->GetAuraOfRankedSpell(SPELL_FIRE_POWER_R1))
                                 if (roll_chance_i(aura->GetSpellInfo()->ProcChance))
                                 {
                                     Position explPos = me->GetPosition();
                                     float z = explPos.GetPositionZ() - me->GetFloatValue(UNIT_FIELD_HOVERHEIGHT);
                                     summoner->CastSpell(Position{ explPos.GetPositionX(), explPos.GetPositionY(), z }, SPELL_FIRE_POWER_EXPLOSION, true);
                                     me->DespawnOrUnsummon();
                                 }
                     break;
                 case EVENT_EXPLODE:
                     if (Unit* summoner = me->ToTempSummon()->GetSummoner())
                         if (Aura* aura = summoner->GetAuraOfRankedSpell(SPELL_FIRE_POWER_R1))
                             if (roll_chance_i(aura->GetSpellInfo()->ProcChance))
                             {
                                 Position explPos = me->GetPosition();
                                 float z = explPos.GetPositionZ() - me->GetFloatValue(UNIT_FIELD_HOVERHEIGHT);
                                 summoner->CastSpell(Position{ explPos.GetPositionX(), explPos.GetPositionY(), z }, SPELL_FIRE_POWER_EXPLOSION, true);
                                 me->DespawnOrUnsummon();
                             }
                     break;
                 default:
                     break;
             }
         }
     }
 private:
     EventMap events;
     Position pos;
 };


enum DruidTreant
{
    SPELL_FUNGAL_GROWTH_R1        = 78788,
    SPELL_FUNGAL_GROWTH_R2        = 78789,
    SPELL_FUNGAL_GROWTH_SUMMON_R1 = 81291,
    SPELL_FUNGAL_GROWTH_SUMMON_R2 = 81283
};

class npc_druid_treant : public CreatureScript
{
    public:
        npc_druid_treant() : CreatureScript("npc_druid_treant") { }

        struct npc_druid_treantAI : public PetAI
        {
            npc_druid_treantAI(Creature* creature) : PetAI(creature) { }

            void JustDied(Unit* /*killer*/) override
            {
                if (TempSummon* summon = me->ToTempSummon())
                {
                    if (Unit* summoner = summon->GetSummoner())
                    {
                        if (summoner->HasAura(SPELL_FUNGAL_GROWTH_R1))
                            summoner->CastSpell(me, SPELL_FUNGAL_GROWTH_SUMMON_R1, true);
                        else if (summoner->HasAura(SPELL_FUNGAL_GROWTH_R2))
                            summoner->CastSpell(me, SPELL_FUNGAL_GROWTH_SUMMON_R2, true);
                    }
                }
            }
        };

        CreatureAI* GetAI(Creature* creature) const override
        {
            return new npc_druid_treantAI(creature);
        }
};

enum WhackAGnoll
{
    NPC_DARKMOON_FAIRE_GNOLL        = 54444,
    NPC_DARKMOON_FAIRE_GNOLL_BABY   = 54466,
    NPC_DARKMOON_FAIRE_GNOLL_BONUS  = 54549,

    SPELL_WHACK                     = 102022,
    SPELL_WHACK_A_GNOLL_SPAWN       = 102136,
    SPELL_WHACK_A_GNOLL_KILL_CREDIT = 101835,
    SPELL_WRONG_WHACK               = 101679,
    SPELL_EXPLODE_SMALL             = 101640,
    SPELL_EXPLODE_BIG               = 101655,

    SOUND_ID_LAUGHTER               = 11816,
    SOUND_ID_SUBMERGE               = 4791,
    AI_ANIM_KIT_SUBMERGE            = 529,

    EVENT_REGULAR_SUBMERGE = 1,
    EVENT_TRIGGERED_SUBMERGE
};

struct npc_darkmoon_island_gnoll : public ScriptedAI
{
    npc_darkmoon_island_gnoll(Creature* creature) : ScriptedAI(creature)
    {
        Initialize();
    }

    void Initialize()
    {
        _hit = false;
    }

    void IsSummonedBy(Unit* /*summoner*/) override
    {
        DoCastSelf(SPELL_WHACK_A_GNOLL_SPAWN);
        _events.ScheduleEvent(EVENT_REGULAR_SUBMERGE, 3s + 500ms);
    }

    void SpellHit(WorldObject* caster, SpellInfo const* spell) override
    {
        if (!caster || _hit)
            return;

        if (spell->Id == SPELL_WHACK)
        {
            _events.CancelEvent(EVENT_REGULAR_SUBMERGE);

            switch (me->GetEntry())
            {
                case NPC_DARKMOON_FAIRE_GNOLL:
                    //DoCast(caster, SPELL_WHACK_A_GNOLL_KILL_CREDIT, true);
                    caster->CastSpell(caster, SPELL_WHACK_A_GNOLL_KILL_CREDIT, true);
                    DoCastSelf(SPELL_EXPLODE_SMALL);
                    me->KillSelf();
                    me->DespawnOrUnsummon(2s);
                    break;
                case NPC_DARKMOON_FAIRE_GNOLL_BONUS:
                    for (uint8 i = 0; i < 3; i++)
                        caster->CastSpell(caster, SPELL_WHACK_A_GNOLL_KILL_CREDIT, true);
                        //DoCast(caster, SPELL_WHACK_A_GNOLL_KILL_CREDIT, true);
                    DoCastSelf(SPELL_EXPLODE_BIG);
                    me->KillSelf();
                    me->DespawnOrUnsummon(2s);
                    break;
                case NPC_DARKMOON_FAIRE_GNOLL_BABY:
                    caster->CastSpell(caster, SPELL_WRONG_WHACK, true);
                    //DoCast(caster, SPELL_WRONG_WHACK, true);
                    if (Player* player = caster->ToPlayer())
                        me->PlayDirectSound(SOUND_ID_LAUGHTER, player);
                    _events.ScheduleEvent(EVENT_TRIGGERED_SUBMERGE, 3s + 600ms);
                    break;
                default:
                    break;
            }

            _hit = true;
        }
    }

    void UpdateAI(uint32 diff) override
    {
        _events.Update(diff);

        while (uint32 eventId = _events.ExecuteEvent())
        {
            switch (eventId)
            {
                case EVENT_REGULAR_SUBMERGE:
                    _hit = true;
                    me->SetAIAnimKitId(AI_ANIM_KIT_SUBMERGE);

                    if (TempSummon* summon = me->ToTempSummon())
                        if (Unit* summoner = summon->GetSummoner())
                            if (Player* player = summoner->ToPlayer())
                                me->PlayDirectSound(SOUND_ID_SUBMERGE, player);
                    me->DespawnOrUnsummon(1s + 500ms);
                    break;
                case EVENT_TRIGGERED_SUBMERGE:
                    me->SetUInt32Value(UNIT_NPC_EMOTESTATE, EMOTE_STATE_SUBMERGED_NEW);
                    me->DespawnOrUnsummon(2s + 500ms);
                    break;
                default:
                    break;
            }
        }
    }

private:
    EventMap _events;
    bool _hit;
};
}

void AddSC_npcs_special_summons()
{
    using namespace NpcSpecial;
    new npc_argent_squire_gruntling();
    new npc_bountiful_table();
    RegisterCreatureAI(npc_mage_orb);
    new npc_druid_treant();
    RegisterCreatureAI(npc_darkmoon_island_gnoll);
}
