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

namespace NpcSpecial
{/*######
## npc_garments_of_quests
######*/

/// @todo get text for each NPC

enum Garments
{
    SPELL_LESSER_HEAL_R2    = 2052,
    SPELL_FORTITUDE_R1      = 1243,

    QUEST_MOON              = 5621,
    QUEST_LIGHT_1           = 5624,
    QUEST_LIGHT_2           = 5625,
    QUEST_SPIRIT            = 5648,
    QUEST_DARKNESS          = 5650,

    ENTRY_SHAYA             = 12429,
    ENTRY_ROBERTS           = 12423,
    ENTRY_DOLF              = 12427,
    ENTRY_KORJA             = 12430,
    ENTRY_DG_KEL            = 12428,

    // used by 12429, 12423, 12427, 12430, 12428, but signed for 12429
    SAY_THANKS              = 0,
    SAY_GOODBYE             = 1,
    SAY_HEALED              = 2,
};

class npc_garments_of_quests : public CreatureScript
{
public:
    npc_garments_of_quests() : CreatureScript("npc_garments_of_quests") { }

    struct npc_garments_of_questsAI : public EscortAI
    {
        npc_garments_of_questsAI(Creature* creature) : EscortAI(creature)
        {
            switch (me->GetEntry())
            {
                case ENTRY_SHAYA:
                    quest = QUEST_MOON;
                    break;
                case ENTRY_ROBERTS:
                    quest = QUEST_LIGHT_1;
                    break;
                case ENTRY_DOLF:
                    quest = QUEST_LIGHT_2;
                    break;
                case ENTRY_KORJA:
                    quest = QUEST_SPIRIT;
                    break;
                case ENTRY_DG_KEL:
                    quest = QUEST_DARKNESS;
                    break;
                default:
                    quest = 0;
                    break;
            }

            Reset();
        }

        ObjectGuid CasterGUID;

        bool IsHealed;
        bool CanRun;

        uint32 RunAwayTimer;
        uint32 quest;

        void Reset() override
        {
            CasterGUID.Clear();

            IsHealed = false;
            CanRun = false;

            RunAwayTimer = 5000;

            me->SetStandState(UNIT_STAND_STATE_KNEEL);
            // expect database to have RegenHealth=0
            me->SetHealth(me->CountPctFromMaxHealth(70));
        }

        void JustEngagedWith(Unit* /*who*/) override { }

        void SpellHit(WorldObject* caster, SpellInfo const* spell) override
        {
            if (spell->Id == SPELL_LESSER_HEAL_R2 || spell->Id == SPELL_FORTITUDE_R1)
            {
                //not while in combat
                if (me->IsInCombat())
                    return;

                //nothing to be done now
                if (IsHealed && CanRun)
                    return;

                if (Player* player = caster->ToPlayer())
                {
                    if (quest && player->GetQuestStatus(quest) == QUEST_STATUS_INCOMPLETE)
                    {
                        if (IsHealed && !CanRun && spell->Id == SPELL_FORTITUDE_R1)
                        {
                            Talk(SAY_THANKS, caster);
                            CanRun = true;
                        }
                        else if (!IsHealed && spell->Id == SPELL_LESSER_HEAL_R2)
                        {
                            CasterGUID = caster->GetGUID();
                            me->SetStandState(UNIT_STAND_STATE_STAND);
                            Talk(SAY_HEALED, caster);
                            IsHealed = true;
                        }
                    }

                    // give quest credit, not expect any special quest objectives
                    if (CanRun)
                        player->TalkedToCreature(me->GetEntry(), me->GetGUID());
                }
            }
        }

        void WaypointReached(uint32 /*waypointId*/, uint32 /*pathId*/) override
        {

        }

        void UpdateAI(uint32 diff) override
        {
            if (CanRun && !me->IsInCombat())
            {
                if (RunAwayTimer <= diff)
                {
                    if (Unit* unit = ObjectAccessor::GetUnit(*me, CasterGUID))
                    {
                        switch (me->GetEntry())
                        {
                            case ENTRY_SHAYA:
                            case ENTRY_ROBERTS:
                            case ENTRY_DOLF:
                            case ENTRY_KORJA:
                            case ENTRY_DG_KEL:
                                Talk(SAY_GOODBYE, unit);
                                break;
                        }

                        Start(false, true);
                    }
                    else
                        EnterEvadeMode();                       //something went wrong

                    RunAwayTimer = 30000;
                }
                else
                    RunAwayTimer -= diff;
            }

            EscortAI::UpdateAI(diff);
        }
    };

    CreatureAI* GetAI(Creature* creature) const override
    {
        return new npc_garments_of_questsAI(creature);
    }
};

/*######
## npc_guardian
######*/

enum GuardianSpells
{
    SPELL_DEATHTOUCH            = 5
};

class npc_guardian : public CreatureScript
{
public:
    npc_guardian() : CreatureScript("npc_guardian") { }

    struct npc_guardianAI : public ScriptedAI
    {
        npc_guardianAI(Creature* creature) : ScriptedAI(creature) { }

        void Reset() override
        {
            me->SetFlag(UNIT_FIELD_FLAGS, UNIT_FLAG_NON_ATTACKABLE);
        }

        void JustEngagedWith(Unit* /*who*/) override
        {
        }

        void UpdateAI(uint32 /*diff*/) override
        {
            if (!UpdateVictim())
                return;

            if (me->isAttackReady())
            {
                DoCastVictim(SPELL_DEATHTOUCH, true);
                me->resetAttackTimer();
            }
        }
    };

    CreatureAI* GetAI(Creature* creature) const override
    {
        return new npc_guardianAI(creature);
    }
};

/*######
## npc_sayge
######*/

enum Sayge
{
    GOSSIP_MENU_OPTION_ID_ANSWER_1   = 0,
    GOSSIP_MENU_OPTION_ID_ANSWER_2   = 1,
    GOSSIP_MENU_OPTION_ID_ANSWER_3   = 2,
    GOSSIP_MENU_OPTION_ID_ANSWER_4   = 3,
    GOSSIP_I_AM_READY_TO_DISCOVER    = 6186,
    GOSSIP_MENU_OPTION_SAYGE1        = 6185,
    GOSSIP_MENU_OPTION_SAYGE2        = 6185,
    GOSSIP_MENU_OPTION_SAYGE3        = 6185,
    GOSSIP_MENU_OPTION_SAYGE4        = 6185,
    GOSSIP_MENU_OPTION_SAYGE5        = 6187,
    GOSSIP_MENU_OPTION_SAYGE6        = 6187,
    GOSSIP_MENU_OPTION_SAYGE7        = 6187,
    GOSSIP_MENU_OPTION_SAYGE8        = 6208,
    GOSSIP_MENU_OPTION_SAYGE9        = 6208,
    GOSSIP_MENU_OPTION_SAYGE10       = 6208,
    GOSSIP_MENU_OPTION_SAYGE11       = 6209,
    GOSSIP_MENU_OPTION_SAYGE12       = 6209,
    GOSSIP_MENU_OPTION_SAYGE13       = 6209,
    GOSSIP_MENU_OPTION_SAYGE14       = 6210,
    GOSSIP_MENU_OPTION_SAYGE15       = 6210,
    GOSSIP_MENU_OPTION_SAYGE16       = 6210,
    GOSSIP_MENU_OPTION_SAYGE17       = 6211,
    GOSSIP_MENU_I_HAVE_LONG_KNOWN    = 7339,
    GOSSIP_MENU_YOU_HAVE_BEEN_TASKED = 7340,
    GOSSIP_MENU_SWORN_EXECUTIONER    = 7341,
    GOSSIP_MENU_DIPLOMATIC_MISSION   = 7361,
    GOSSIP_MENU_YOUR_BROTHER_SEEKS   = 7362,
    GOSSIP_MENU_A_TERRIBLE_BEAST     = 7363,
    GOSSIP_MENU_YOUR_FORTUNE_IS_CAST = 7364,
    GOSSIP_MENU_HERE_IS_YOUR_FORTUNE = 7365,
    GOSSIP_MENU_CANT_GIVE_YOU_YOUR   = 7393,

    SPELL_STRENGTH                   = 23735, // +10% Strength
    SPELL_AGILITY                    = 23736, // +10% Agility
    SPELL_STAMINA                    = 23737, // +10% Stamina
    SPELL_SPIRIT                     = 23738, // +10% Spirit
    SPELL_INTELLECT                  = 23766, // +10% Intellect
    SPELL_ARMOR                      = 23767, // +10% Armor
    SPELL_DAMAGE                     = 23768, // +10% Damage
    SPELL_RESISTANCE                 = 23769, // +25 Magic Resistance (All)
    SPELL_FORTUNE                    = 23765  // Darkmoon Faire Fortune
};

class npc_sayge : public CreatureScript
{
    public:
        npc_sayge() : CreatureScript("npc_sayge") { }

        struct npc_saygeAI : public ScriptedAI
        {
            npc_saygeAI(Creature* creature) : ScriptedAI(creature) { }

            bool GossipHello(Player* player) override
            {
                if (me->IsQuestGiver())
                    player->PrepareQuestMenu(me->GetGUID());

                if (player->GetSpellHistory()->HasCooldown(SPELL_STRENGTH) ||
                    player->GetSpellHistory()->HasCooldown(SPELL_AGILITY) ||
                    player->GetSpellHistory()->HasCooldown(SPELL_STAMINA) ||
                    player->GetSpellHistory()->HasCooldown(SPELL_SPIRIT) ||
                    player->GetSpellHistory()->HasCooldown(SPELL_INTELLECT) ||
                    player->GetSpellHistory()->HasCooldown(SPELL_ARMOR) ||
                    player->GetSpellHistory()->HasCooldown(SPELL_DAMAGE) ||
                    player->GetSpellHistory()->HasCooldown(SPELL_RESISTANCE))
                    SendGossipMenuFor(player, GOSSIP_MENU_CANT_GIVE_YOU_YOUR, me->GetGUID());
                else
                {
                    AddGossipItemFor(player, GOSSIP_I_AM_READY_TO_DISCOVER, GOSSIP_MENU_OPTION_ID_ANSWER_1, GOSSIP_SENDER_MAIN, GOSSIP_ACTION_INFO_DEF + 1);
                    SendGossipMenuFor(player, GOSSIP_MENU_I_HAVE_LONG_KNOWN, me->GetGUID());
                }

                return true;
            }

            bool GossipSelect(Player* player, uint32 /*menuId*/, uint32 gossipListId) override
            {
                uint32 const sender = player->PlayerTalkClass->GetGossipOptionSender(gossipListId);
                uint32 const action = player->PlayerTalkClass->GetGossipOptionAction(gossipListId);
                ClearGossipMenuFor(player);
                uint32 spellId = 0;
                switch (sender)
                {
                    case GOSSIP_SENDER_MAIN:
                        SendAction(player, action);
                        break;
                    case GOSSIP_SENDER_MAIN + 1:
                        spellId = SPELL_DAMAGE;
                        break;
                    case GOSSIP_SENDER_MAIN + 2:
                        spellId = SPELL_RESISTANCE;
                        break;
                    case GOSSIP_SENDER_MAIN + 3:
                        spellId = SPELL_ARMOR;
                        break;
                    case GOSSIP_SENDER_MAIN + 4:
                        spellId = SPELL_SPIRIT;
                        break;
                    case GOSSIP_SENDER_MAIN + 5:
                        spellId = SPELL_INTELLECT;
                        break;
                    case GOSSIP_SENDER_MAIN + 6:
                        spellId = SPELL_STAMINA;
                        break;
                    case GOSSIP_SENDER_MAIN + 7:
                        spellId = SPELL_STRENGTH;
                        break;
                    case GOSSIP_SENDER_MAIN + 8:
                        spellId = SPELL_AGILITY;
                        break;
                }

                if (spellId)
                {
                    me->CastSpell(player, spellId, false);
                    player->GetSpellHistory()->AddCooldown(spellId, 0, std::chrono::hours(2));
                    SendAction(player, action);
                }
                return true;
            }

        private:
            void SendAction(Player* player, uint32 action) const
            {
                switch (action)
                {
                    case GOSSIP_ACTION_INFO_DEF + 1:
                        AddGossipItemFor(player, GOSSIP_MENU_OPTION_SAYGE1, GOSSIP_MENU_OPTION_ID_ANSWER_1, GOSSIP_SENDER_MAIN, GOSSIP_ACTION_INFO_DEF + 2);
                        AddGossipItemFor(player, GOSSIP_MENU_OPTION_SAYGE2, GOSSIP_MENU_OPTION_ID_ANSWER_2, GOSSIP_SENDER_MAIN, GOSSIP_ACTION_INFO_DEF + 3);
                        AddGossipItemFor(player, GOSSIP_MENU_OPTION_SAYGE3, GOSSIP_MENU_OPTION_ID_ANSWER_3, GOSSIP_SENDER_MAIN, GOSSIP_ACTION_INFO_DEF + 4);
                        AddGossipItemFor(player, GOSSIP_MENU_OPTION_SAYGE4, GOSSIP_MENU_OPTION_ID_ANSWER_4, GOSSIP_SENDER_MAIN, GOSSIP_ACTION_INFO_DEF + 5);
                        SendGossipMenuFor(player, GOSSIP_MENU_YOU_HAVE_BEEN_TASKED, me->GetGUID());
                        break;
                    case GOSSIP_ACTION_INFO_DEF + 2:
                        AddGossipItemFor(player, GOSSIP_MENU_OPTION_SAYGE5, GOSSIP_MENU_OPTION_ID_ANSWER_1, GOSSIP_SENDER_MAIN + 1, GOSSIP_ACTION_INFO_DEF);
                        AddGossipItemFor(player, GOSSIP_MENU_OPTION_SAYGE6, GOSSIP_MENU_OPTION_ID_ANSWER_2, GOSSIP_SENDER_MAIN + 2, GOSSIP_ACTION_INFO_DEF);
                        AddGossipItemFor(player, GOSSIP_MENU_OPTION_SAYGE7, GOSSIP_MENU_OPTION_ID_ANSWER_3, GOSSIP_SENDER_MAIN + 3, GOSSIP_ACTION_INFO_DEF);
                        SendGossipMenuFor(player, GOSSIP_MENU_SWORN_EXECUTIONER, me->GetGUID());
                        break;
                    case GOSSIP_ACTION_INFO_DEF + 3:
                        AddGossipItemFor(player, GOSSIP_MENU_OPTION_SAYGE8, GOSSIP_MENU_OPTION_ID_ANSWER_1, GOSSIP_SENDER_MAIN + 4, GOSSIP_ACTION_INFO_DEF);
                        AddGossipItemFor(player, GOSSIP_MENU_OPTION_SAYGE9, GOSSIP_MENU_OPTION_ID_ANSWER_2, GOSSIP_SENDER_MAIN + 5, GOSSIP_ACTION_INFO_DEF);
                        AddGossipItemFor(player, GOSSIP_MENU_OPTION_SAYGE10, GOSSIP_MENU_OPTION_ID_ANSWER_3, GOSSIP_SENDER_MAIN + 2, GOSSIP_ACTION_INFO_DEF);
                        SendGossipMenuFor(player, GOSSIP_MENU_DIPLOMATIC_MISSION, me->GetGUID());
                        break;
                    case GOSSIP_ACTION_INFO_DEF + 4:
                        AddGossipItemFor(player, GOSSIP_MENU_OPTION_SAYGE11, GOSSIP_MENU_OPTION_ID_ANSWER_1, GOSSIP_SENDER_MAIN + 6, GOSSIP_ACTION_INFO_DEF);
                        AddGossipItemFor(player, GOSSIP_MENU_OPTION_SAYGE12, GOSSIP_MENU_OPTION_ID_ANSWER_2, GOSSIP_SENDER_MAIN + 7, GOSSIP_ACTION_INFO_DEF);
                        AddGossipItemFor(player, GOSSIP_MENU_OPTION_SAYGE13, GOSSIP_MENU_OPTION_ID_ANSWER_3, GOSSIP_SENDER_MAIN + 8, GOSSIP_ACTION_INFO_DEF);
                        SendGossipMenuFor(player, GOSSIP_MENU_YOUR_BROTHER_SEEKS, me->GetGUID());
                        break;
                    case GOSSIP_ACTION_INFO_DEF + 5:
                        AddGossipItemFor(player, GOSSIP_MENU_OPTION_SAYGE14, GOSSIP_MENU_OPTION_ID_ANSWER_1, GOSSIP_SENDER_MAIN + 5, GOSSIP_ACTION_INFO_DEF);
                        AddGossipItemFor(player, GOSSIP_MENU_OPTION_SAYGE15, GOSSIP_MENU_OPTION_ID_ANSWER_2, GOSSIP_SENDER_MAIN + 4, GOSSIP_ACTION_INFO_DEF);
                        AddGossipItemFor(player, GOSSIP_MENU_OPTION_SAYGE16, GOSSIP_MENU_OPTION_ID_ANSWER_3, GOSSIP_SENDER_MAIN + 3, GOSSIP_ACTION_INFO_DEF);
                        SendGossipMenuFor(player, GOSSIP_MENU_A_TERRIBLE_BEAST, me->GetGUID());
                        break;
                    case GOSSIP_ACTION_INFO_DEF:
                        AddGossipItemFor(player, GOSSIP_MENU_OPTION_SAYGE17, GOSSIP_MENU_OPTION_ID_ANSWER_1, GOSSIP_SENDER_MAIN, GOSSIP_ACTION_INFO_DEF + 6);
                        SendGossipMenuFor(player, GOSSIP_MENU_YOUR_FORTUNE_IS_CAST, me->GetGUID());
                        break;
                    case GOSSIP_ACTION_INFO_DEF + 6:
                        me->CastSpell(player, SPELL_FORTUNE, false);
                        SendGossipMenuFor(player, GOSSIP_MENU_HERE_IS_YOUR_FORTUNE, me->GetGUID());
                        break;
                }
            }
        };

        CreatureAI* GetAI(Creature* creature) const override
        {
            return new npc_saygeAI(creature);
        }
};

class npc_steam_tonk : public CreatureScript
{
public:
    npc_steam_tonk() : CreatureScript("npc_steam_tonk") { }

    struct npc_steam_tonkAI : public ScriptedAI
    {
        npc_steam_tonkAI(Creature* creature) : ScriptedAI(creature) { }

        void Reset() override { }
        void JustEngagedWith(Unit* /*who*/) override { }

        void OnPossess(bool apply)
        {
            if (apply)
            {
                // Initialize the action bar without the melee attack command
                me->InitCharmInfo();
                me->GetCharmInfo()->InitEmptyActionBar(false);

                me->SetReactState(REACT_PASSIVE);
            }
            else
                me->SetReactState(REACT_AGGRESSIVE);
        }
    };

    CreatureAI* GetAI(Creature* creature) const override
    {
        return new npc_steam_tonkAI(creature);
    }
};

enum TonkMine
{
    SPELL_TONK_MINE_DETONATE    = 25099
};

class npc_tonk_mine : public CreatureScript
{
public:
    npc_tonk_mine() : CreatureScript("npc_tonk_mine") { }

    struct npc_tonk_mineAI : public ScriptedAI
    {
        npc_tonk_mineAI(Creature* creature) : ScriptedAI(creature)
        {
            Initialize();
            me->SetReactState(REACT_PASSIVE);
        }

        void Initialize()
        {
            ExplosionTimer = 3000;
        }

        uint32 ExplosionTimer;

        void Reset() override
        {
            Initialize();
        }

        void JustEngagedWith(Unit* /*who*/) override { }
        void AttackStart(Unit* /*who*/) override { }
        void MoveInLineOfSight(Unit* /*who*/) override { }


        void UpdateAI(uint32 diff) override
        {
            if (ExplosionTimer <= diff)
            {
                DoCast(me, SPELL_TONK_MINE_DETONATE, true);
                me->setDeathState(DEAD); // unsummon it
            }
            else
                ExplosionTimer -= diff;
        }
    };

    CreatureAI* GetAI(Creature* creature) const override
    {
        return new npc_tonk_mineAI(creature);
    }
};

enum TournamentPennantSpells
{
    SPELL_PENNANT_STORMWIND_ASPIRANT        = 62595,
    SPELL_PENNANT_STORMWIND_VALIANT         = 62596,
    SPELL_PENNANT_STORMWIND_CHAMPION        = 62594,
    SPELL_PENNANT_GNOMEREGAN_ASPIRANT       = 63394,
    SPELL_PENNANT_GNOMEREGAN_VALIANT        = 63395,
    SPELL_PENNANT_GNOMEREGAN_CHAMPION       = 63396,
    SPELL_PENNANT_SEN_JIN_ASPIRANT          = 63397,
    SPELL_PENNANT_SEN_JIN_VALIANT           = 63398,
    SPELL_PENNANT_SEN_JIN_CHAMPION          = 63399,
    SPELL_PENNANT_SILVERMOON_ASPIRANT       = 63401,
    SPELL_PENNANT_SILVERMOON_VALIANT        = 63402,
    SPELL_PENNANT_SILVERMOON_CHAMPION       = 63403,
    SPELL_PENNANT_DARNASSUS_ASPIRANT        = 63404,
    SPELL_PENNANT_DARNASSUS_VALIANT         = 63405,
    SPELL_PENNANT_DARNASSUS_CHAMPION        = 63406,
    SPELL_PENNANT_EXODAR_ASPIRANT           = 63421,
    SPELL_PENNANT_EXODAR_VALIANT            = 63422,
    SPELL_PENNANT_EXODAR_CHAMPION           = 63423,
    SPELL_PENNANT_IRONFORGE_ASPIRANT        = 63425,
    SPELL_PENNANT_IRONFORGE_VALIANT         = 63426,
    SPELL_PENNANT_IRONFORGE_CHAMPION        = 63427,
    SPELL_PENNANT_UNDERCITY_ASPIRANT        = 63428,
    SPELL_PENNANT_UNDERCITY_VALIANT         = 63429,
    SPELL_PENNANT_UNDERCITY_CHAMPION        = 63430,
    SPELL_PENNANT_ORGRIMMAR_ASPIRANT        = 63431,
    SPELL_PENNANT_ORGRIMMAR_VALIANT         = 63432,
    SPELL_PENNANT_ORGRIMMAR_CHAMPION        = 63433,
    SPELL_PENNANT_THUNDER_BLUFF_ASPIRANT    = 63434,
    SPELL_PENNANT_THUNDER_BLUFF_VALIANT     = 63435,
    SPELL_PENNANT_THUNDER_BLUFF_CHAMPION    = 63436,
    SPELL_PENNANT_ARGENT_CRUSADE_ASPIRANT   = 63606,
    SPELL_PENNANT_ARGENT_CRUSADE_VALIANT    = 63500,
    SPELL_PENNANT_ARGENT_CRUSADE_CHAMPION   = 63501,
    SPELL_PENNANT_EBON_BLADE_ASPIRANT       = 63607,
    SPELL_PENNANT_EBON_BLADE_VALIANT        = 63608,
    SPELL_PENNANT_EBON_BLADE_CHAMPION       = 63609
};

enum TournamentMounts
{
    NPC_STORMWIND_STEED                     = 33217,
    NPC_IRONFORGE_RAM                       = 33316,
    NPC_GNOMEREGAN_MECHANOSTRIDER           = 33317,
    NPC_EXODAR_ELEKK                        = 33318,
    NPC_DARNASSIAN_NIGHTSABER               = 33319,
    NPC_ORGRIMMAR_WOLF                      = 33320,
    NPC_DARK_SPEAR_RAPTOR                   = 33321,
    NPC_THUNDER_BLUFF_KODO                  = 33322,
    NPC_SILVERMOON_HAWKSTRIDER              = 33323,
    NPC_FORSAKEN_WARHORSE                   = 33324,
    NPC_ARGENT_WARHORSE                     = 33782,
    NPC_ARGENT_STEED_ASPIRANT               = 33845,
    NPC_ARGENT_HAWKSTRIDER_ASPIRANT         = 33844
};

enum TournamentQuestsAchievements
{
    ACHIEVEMENT_CHAMPION_STORMWIND          = 2781,
    ACHIEVEMENT_CHAMPION_DARNASSUS          = 2777,
    ACHIEVEMENT_CHAMPION_IRONFORGE          = 2780,
    ACHIEVEMENT_CHAMPION_GNOMEREGAN         = 2779,
    ACHIEVEMENT_CHAMPION_THE_EXODAR         = 2778,
    ACHIEVEMENT_CHAMPION_ORGRIMMAR          = 2783,
    ACHIEVEMENT_CHAMPION_SEN_JIN            = 2784,
    ACHIEVEMENT_CHAMPION_THUNDER_BLUFF      = 2786,
    ACHIEVEMENT_CHAMPION_UNDERCITY          = 2787,
    ACHIEVEMENT_CHAMPION_SILVERMOON         = 2785,
    ACHIEVEMENT_ARGENT_VALOR                = 2758,
    ACHIEVEMENT_CHAMPION_ALLIANCE           = 2782,
    ACHIEVEMENT_CHAMPION_HORDE              = 2788,

    QUEST_VALIANT_OF_STORMWIND              = 13593,
    QUEST_A_VALIANT_OF_STORMWIND            = 13684,
    QUEST_VALIANT_OF_DARNASSUS              = 13706,
    QUEST_A_VALIANT_OF_DARNASSUS            = 13689,
    QUEST_VALIANT_OF_IRONFORGE              = 13703,
    QUEST_A_VALIANT_OF_IRONFORGE            = 13685,
    QUEST_VALIANT_OF_GNOMEREGAN             = 13704,
    QUEST_A_VALIANT_OF_GNOMEREGAN           = 13688,
    QUEST_VALIANT_OF_THE_EXODAR             = 13705,
    QUEST_A_VALIANT_OF_THE_EXODAR           = 13690,
    QUEST_VALIANT_OF_ORGRIMMAR              = 13707,
    QUEST_A_VALIANT_OF_ORGRIMMAR            = 13691,
    QUEST_VALIANT_OF_SEN_JIN                = 13708,
    QUEST_A_VALIANT_OF_SEN_JIN              = 13693,
    QUEST_VALIANT_OF_THUNDER_BLUFF          = 13709,
    QUEST_A_VALIANT_OF_THUNDER_BLUFF        = 13694,
    QUEST_VALIANT_OF_UNDERCITY              = 13710,
    QUEST_A_VALIANT_OF_UNDERCITY            = 13695,
    QUEST_VALIANT_OF_SILVERMOON             = 13711,
    QUEST_A_VALIANT_OF_SILVERMOON           = 13696
};

class npc_tournament_mount : public CreatureScript
{
    public:
        npc_tournament_mount() : CreatureScript("npc_tournament_mount") { }

        struct npc_tournament_mountAI : public VehicleAI
        {
            npc_tournament_mountAI(Creature* creature) : VehicleAI(creature)
            {
                _pennantSpellId = 0;
            }

            void PassengerBoarded(Unit* passenger, int8 /*seatId*/, bool apply) override
            {
                Player* player = passenger->ToPlayer();
                if (!player)
                    return;

                if (apply)
                {
                    _pennantSpellId = GetPennantSpellId(player);
                    player->CastSpell((Unit*)nullptr, _pennantSpellId, true);
                }
                else
                    player->RemoveAurasDueToSpell(_pennantSpellId);
            }

        private:
            uint32 _pennantSpellId;

            uint32 GetPennantSpellId(Player* player) const
            {
                switch (me->GetEntry())
                {
                    case NPC_ARGENT_STEED_ASPIRANT:
                    case NPC_STORMWIND_STEED:
                    {
                        if (player->HasAchieved(ACHIEVEMENT_CHAMPION_STORMWIND))
                            return SPELL_PENNANT_STORMWIND_CHAMPION;
                        else if (player->GetQuestRewardStatus(QUEST_VALIANT_OF_STORMWIND) || player->GetQuestRewardStatus(QUEST_A_VALIANT_OF_STORMWIND))
                            return SPELL_PENNANT_STORMWIND_VALIANT;
                        else
                            return SPELL_PENNANT_STORMWIND_ASPIRANT;
                    }
                    case NPC_GNOMEREGAN_MECHANOSTRIDER:
                    {
                        if (player->HasAchieved(ACHIEVEMENT_CHAMPION_GNOMEREGAN))
                            return SPELL_PENNANT_GNOMEREGAN_CHAMPION;
                        else if (player->GetQuestRewardStatus(QUEST_VALIANT_OF_GNOMEREGAN) || player->GetQuestRewardStatus(QUEST_A_VALIANT_OF_GNOMEREGAN))
                            return SPELL_PENNANT_GNOMEREGAN_VALIANT;
                        else
                            return SPELL_PENNANT_GNOMEREGAN_ASPIRANT;
                    }
                    case NPC_DARK_SPEAR_RAPTOR:
                    {
                        if (player->HasAchieved(ACHIEVEMENT_CHAMPION_SEN_JIN))
                            return SPELL_PENNANT_SEN_JIN_CHAMPION;
                        else if (player->GetQuestRewardStatus(QUEST_VALIANT_OF_SEN_JIN) || player->GetQuestRewardStatus(QUEST_A_VALIANT_OF_SEN_JIN))
                            return SPELL_PENNANT_SEN_JIN_VALIANT;
                        else
                            return SPELL_PENNANT_SEN_JIN_ASPIRANT;
                    }
                    case NPC_ARGENT_HAWKSTRIDER_ASPIRANT:
                    case NPC_SILVERMOON_HAWKSTRIDER:
                    {
                        if (player->HasAchieved(ACHIEVEMENT_CHAMPION_SILVERMOON))
                            return SPELL_PENNANT_SILVERMOON_CHAMPION;
                        else if (player->GetQuestRewardStatus(QUEST_VALIANT_OF_SILVERMOON) || player->GetQuestRewardStatus(QUEST_A_VALIANT_OF_SILVERMOON))
                            return SPELL_PENNANT_SILVERMOON_VALIANT;
                        else
                            return SPELL_PENNANT_SILVERMOON_ASPIRANT;
                    }
                    case NPC_DARNASSIAN_NIGHTSABER:
                    {
                        if (player->HasAchieved(ACHIEVEMENT_CHAMPION_DARNASSUS))
                            return SPELL_PENNANT_DARNASSUS_CHAMPION;
                        else if (player->GetQuestRewardStatus(QUEST_VALIANT_OF_DARNASSUS) || player->GetQuestRewardStatus(QUEST_A_VALIANT_OF_DARNASSUS))
                            return SPELL_PENNANT_DARNASSUS_VALIANT;
                        else
                            return SPELL_PENNANT_DARNASSUS_ASPIRANT;
                    }
                    case NPC_EXODAR_ELEKK:
                    {
                        if (player->HasAchieved(ACHIEVEMENT_CHAMPION_THE_EXODAR))
                            return SPELL_PENNANT_EXODAR_CHAMPION;
                        else if (player->GetQuestRewardStatus(QUEST_VALIANT_OF_THE_EXODAR) || player->GetQuestRewardStatus(QUEST_A_VALIANT_OF_THE_EXODAR))
                            return SPELL_PENNANT_EXODAR_VALIANT;
                        else
                            return SPELL_PENNANT_EXODAR_ASPIRANT;
                    }
                    case NPC_IRONFORGE_RAM:
                    {
                        if (player->HasAchieved(ACHIEVEMENT_CHAMPION_IRONFORGE))
                            return SPELL_PENNANT_IRONFORGE_CHAMPION;
                        else if (player->GetQuestRewardStatus(QUEST_VALIANT_OF_IRONFORGE) || player->GetQuestRewardStatus(QUEST_A_VALIANT_OF_IRONFORGE))
                            return SPELL_PENNANT_IRONFORGE_VALIANT;
                        else
                            return SPELL_PENNANT_IRONFORGE_ASPIRANT;
                    }
                    case NPC_FORSAKEN_WARHORSE:
                    {
                        if (player->HasAchieved(ACHIEVEMENT_CHAMPION_UNDERCITY))
                            return SPELL_PENNANT_UNDERCITY_CHAMPION;
                        else if (player->GetQuestRewardStatus(QUEST_VALIANT_OF_UNDERCITY) || player->GetQuestRewardStatus(QUEST_A_VALIANT_OF_UNDERCITY))
                            return SPELL_PENNANT_UNDERCITY_VALIANT;
                        else
                            return SPELL_PENNANT_UNDERCITY_ASPIRANT;
                    }
                    case NPC_ORGRIMMAR_WOLF:
                    {
                        if (player->HasAchieved(ACHIEVEMENT_CHAMPION_ORGRIMMAR))
                            return SPELL_PENNANT_ORGRIMMAR_CHAMPION;
                        else if (player->GetQuestRewardStatus(QUEST_VALIANT_OF_ORGRIMMAR) || player->GetQuestRewardStatus(QUEST_A_VALIANT_OF_ORGRIMMAR))
                            return SPELL_PENNANT_ORGRIMMAR_VALIANT;
                        else
                            return SPELL_PENNANT_ORGRIMMAR_ASPIRANT;
                    }
                    case NPC_THUNDER_BLUFF_KODO:
                    {
                        if (player->HasAchieved(ACHIEVEMENT_CHAMPION_THUNDER_BLUFF))
                            return SPELL_PENNANT_THUNDER_BLUFF_CHAMPION;
                        else if (player->GetQuestRewardStatus(QUEST_VALIANT_OF_THUNDER_BLUFF) || player->GetQuestRewardStatus(QUEST_A_VALIANT_OF_THUNDER_BLUFF))
                            return SPELL_PENNANT_THUNDER_BLUFF_VALIANT;
                        else
                            return SPELL_PENNANT_THUNDER_BLUFF_ASPIRANT;
                    }
                    case NPC_ARGENT_WARHORSE:
                    {
                        if (player->HasAchieved(ACHIEVEMENT_CHAMPION_ALLIANCE) || player->HasAchieved(ACHIEVEMENT_CHAMPION_HORDE))
                            return player->getClass() == CLASS_DEATH_KNIGHT ? SPELL_PENNANT_EBON_BLADE_CHAMPION : SPELL_PENNANT_ARGENT_CRUSADE_CHAMPION;
                        else if (player->HasAchieved(ACHIEVEMENT_ARGENT_VALOR))
                            return player->getClass() == CLASS_DEATH_KNIGHT ? SPELL_PENNANT_EBON_BLADE_VALIANT : SPELL_PENNANT_ARGENT_CRUSADE_VALIANT;
                        else
                            return player->getClass() == CLASS_DEATH_KNIGHT ? SPELL_PENNANT_EBON_BLADE_ASPIRANT : SPELL_PENNANT_ARGENT_CRUSADE_ASPIRANT;
                    }
                    default:
                        return 0;
                }
            }
        };

        CreatureAI* GetAI(Creature* creature) const override
        {
            return new npc_tournament_mountAI(creature);
        }
};

/*####
## npc_brewfest_reveler
####*/

enum BrewfestReveler
{
    SPELL_BREWFEST_TOAST = 41586
};

class npc_brewfest_reveler : public CreatureScript
{
    public:
        npc_brewfest_reveler() : CreatureScript("npc_brewfest_reveler") { }

        struct npc_brewfest_revelerAI : public ScriptedAI
        {
            npc_brewfest_revelerAI(Creature* creature) : ScriptedAI(creature) { }

            void ReceiveEmote(Player* player, uint32 emote) override
            {
                if (!IsHolidayActive(HOLIDAY_BREWFEST))
                    return;

                if (emote == TEXT_EMOTE_DANCE)
                    me->CastSpell(player, SPELL_BREWFEST_TOAST, false);
            }
        };

        CreatureAI* GetAI(Creature* creature) const override
        {
            return new npc_brewfest_revelerAI(creature);
        }
};

/*####
## npc_training_dummy
####*/

enum TrainingDummy
{
    NPC_ADVANCED_TARGET_DUMMY                  = 2674,
    NPC_TARGET_DUMMY                           = 2673,
    NPC_SPELL_PRACTICE_CREDIT                  = 44175,
    SPELL_CHARGE                               = 100,
    SPELL_JUDGEMENT                            = 20271,
    SPELL_STEADY_SHOT                          = 56641,
    SPELL_EVISCERATE                           = 2098,
    SPELL_PRIMAL_STRIKE                        = 73899,
    SPELL_IMMOLATE                             = 348,
    SPELL_ARCANE_MISSILES                      = 5143,
};

struct npc_training_dummy : NullCreatureAI
{
    npc_training_dummy(Creature* creature) : NullCreatureAI(creature)
    {
        uint32 const entry = me->GetEntry();
        if (entry == NPC_TARGET_DUMMY || entry == NPC_ADVANCED_TARGET_DUMMY)
            me->DespawnOrUnsummon(16s);
    }

    void DamageTaken(Unit* attacker, uint32& damage) override
    {
        damage = 0;

        if (!attacker)
            return;

        _combatTimer[attacker->GetGUID()] = int32(5 * IN_MILLISECONDS);
    }

    // Todo: the involved training dummys have a proc aura for that. Drop this part here, once converted.
    void SpellHit(WorldObject* caster, SpellInfo const* spell) override
    {
        switch (spell->Id)
        {
            case SPELL_CHARGE:          // Charge - Warrior
            case SPELL_JUDGEMENT:       // Judgement - Paladin
            case SPELL_STEADY_SHOT:     // Steady Shot - Hunter
            case SPELL_EVISCERATE:      // Eviscerate - Rouge
            case SPELL_PRIMAL_STRIKE:   // Primal Strike - Shaman
            case SPELL_IMMOLATE:        // Immolate - Warlock
            case SPELL_ARCANE_MISSILES: // Arcane Missiles - Mage
                if (caster->GetTypeId() == TYPEID_PLAYER)
                    caster->ToPlayer()->KilledMonsterCredit(NPC_SPELL_PRACTICE_CREDIT);
                break;
            default:
                break;
        }
    }

    void UpdateAI(uint32 diff) override
    {
        for (auto itr = _combatTimer.begin(); itr != _combatTimer.end();)
        {
            itr->second -= diff;
            if (itr->second <= 0)
            {
                auto const& pveRefs = me->GetCombatManager().GetPvECombatRefs();
                auto it = pveRefs.find(itr->first);
                if (it != pveRefs.end())
                    it->second->EndCombat();

                itr = _combatTimer.erase(itr);
            }
            else
                ++itr;
        }
    }
private:
    std::unordered_map<ObjectGuid /*attackerGUID*/, int32 /*combatTime*/> _combatTimer;
};


}

void AddSC_npcs_special_services()
{
    using namespace NpcSpecial;
    new npc_garments_of_quests();
    new npc_guardian();
    new npc_sayge();
    new npc_steam_tonk();
    new npc_tonk_mine();
    new npc_tournament_mount();
    new npc_brewfest_reveler();
    RegisterCreatureAI(npc_training_dummy);
}
