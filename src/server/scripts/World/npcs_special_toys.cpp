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
# npc_wormhole
######*/

enum NPC_Wormhole
{
    DATA_SHOW_UNDERGROUND = 1,     // -> Random 0 or 1

    MENU_ID_WORMHOLE      = 10668, // "This tear in the fabric of time and space looks ominous."
    NPC_TEXT_WORMHOLE     = 14785, // (not 907 "What brings you to this part of the world, $n?")
    GOSSIP_OPTION_1       = 0,     // "Borean Tundra"
    GOSSIP_OPTION_2       = 1,     // "Howling Fjord"
    GOSSIP_OPTION_3       = 2,     // "Sholazar Basin"
    GOSSIP_OPTION_4       = 3,     // "Icecrown"
    GOSSIP_OPTION_5       = 4,     // "Storm Peaks"
    GOSSIP_OPTION_6       = 5,     // "Underground..."

    SPELL_BOREAN_TUNDRA   = 67834, // 0
    SPELL_HOWLING_FJORD   = 67838, // 1
    SPELL_SHOLAZAR_BASIN  = 67835, // 2
    SPELL_ICECROWN        = 67836, // 3
    SPELL_STORM_PEAKS     = 67837, // 4
    SPELL_UNDERGROUND     = 68081  // 5
};

class npc_wormhole : public CreatureScript
{
    public:
        npc_wormhole() : CreatureScript("npc_wormhole") { }

        struct npc_wormholeAI : public PassiveAI
        {
            npc_wormholeAI(Creature* creature) : PassiveAI(creature)
            {
                Initialize();
            }

            void Initialize()
            {
                _showUnderground = urand(0, 100) == 0; // Guessed value, it is really rare though
            }

            void InitializeAI() override
            {
                Initialize();
            }

            uint32 GetData(uint32 type) const override
            {
                return (type == DATA_SHOW_UNDERGROUND && _showUnderground) ? 1 : 0;
            }

            bool GossipHello(Player* player) override
            {
                if (me->IsSummon())
                {
                    if (player == me->ToTempSummon()->GetSummoner())
                    {
                        AddGossipItemFor(player, MENU_ID_WORMHOLE, GOSSIP_OPTION_1, GOSSIP_SENDER_MAIN, GOSSIP_ACTION_INFO_DEF + 1);
                        AddGossipItemFor(player, MENU_ID_WORMHOLE, GOSSIP_OPTION_2, GOSSIP_SENDER_MAIN, GOSSIP_ACTION_INFO_DEF + 2);
                        AddGossipItemFor(player, MENU_ID_WORMHOLE, GOSSIP_OPTION_3, GOSSIP_SENDER_MAIN, GOSSIP_ACTION_INFO_DEF + 3);
                        AddGossipItemFor(player, MENU_ID_WORMHOLE, GOSSIP_OPTION_4, GOSSIP_SENDER_MAIN, GOSSIP_ACTION_INFO_DEF + 4);
                        AddGossipItemFor(player, MENU_ID_WORMHOLE, GOSSIP_OPTION_5, GOSSIP_SENDER_MAIN, GOSSIP_ACTION_INFO_DEF + 5);

                        if (GetData(DATA_SHOW_UNDERGROUND))
                            AddGossipItemFor(player, MENU_ID_WORMHOLE, GOSSIP_OPTION_6, GOSSIP_SENDER_MAIN, GOSSIP_ACTION_INFO_DEF + 6);

                        SendGossipMenuFor(player, NPC_TEXT_WORMHOLE, me->GetGUID());
                    }
                }

                return true;
            }

            bool GossipSelect(Player* player, uint32 /*menuId*/, uint32 gossipListId) override
            {
                uint32 const action = player->PlayerTalkClass->GetGossipOptionAction(gossipListId);
                ClearGossipMenuFor(player);

                switch (action)
                {
                    case GOSSIP_ACTION_INFO_DEF + 1: // Borean Tundra
                        CloseGossipMenuFor(player);
                        me->CastSpell(player, SPELL_BOREAN_TUNDRA, false);
                        break;
                    case GOSSIP_ACTION_INFO_DEF + 2: // Howling Fjord
                        CloseGossipMenuFor(player);
                        me->CastSpell(player, SPELL_HOWLING_FJORD, false);
                        break;
                    case GOSSIP_ACTION_INFO_DEF + 3: // Sholazar Basin
                        CloseGossipMenuFor(player);
                        me->CastSpell(player, SPELL_SHOLAZAR_BASIN, false);
                        break;
                    case GOSSIP_ACTION_INFO_DEF + 4: // Icecrown
                        CloseGossipMenuFor(player);
                        me->CastSpell(player, SPELL_ICECROWN, false);
                        break;
                    case GOSSIP_ACTION_INFO_DEF + 5: // Storm peaks
                        CloseGossipMenuFor(player);
                        me->CastSpell(player, SPELL_STORM_PEAKS, false);
                        break;
                    case GOSSIP_ACTION_INFO_DEF + 6: // Underground
                        CloseGossipMenuFor(player);
                        me->CastSpell(player, SPELL_UNDERGROUND, false);
                        break;
                }

                return true;
            }

        private:
            bool _showUnderground;
        };

        CreatureAI* GetAI(Creature* creature) const override
        {
            return new npc_wormholeAI(creature);
        }
};

/*######
## npc_pet_trainer
######*/

enum PetTrainer
{
    MENU_ID_PET_UNLEARN      = 6520,
    OPTION_ID_PLEASE_DO      = 0
};

class npc_pet_trainer : public CreatureScript
{
    public:
        npc_pet_trainer() : CreatureScript("npc_pet_trainer") { }

        struct npc_pet_trainerAI : public ScriptedAI
        {
            npc_pet_trainerAI(Creature* creature) : ScriptedAI(creature) { }

            bool GossipSelect(Player* player, uint32 menuId, uint32 gossipListId) override
            {
                if (menuId == MENU_ID_PET_UNLEARN && gossipListId == OPTION_ID_PLEASE_DO)
                {
                    player->ResetPetTalents();
                    CloseGossipMenuFor(player);
                }
                return false;
            }
        };

        CreatureAI* GetAI(Creature* creature) const override
        {
            return new npc_pet_trainerAI(creature);
        }
};

/*######
## npc_experience
######*/

enum BehstenSlahtz
{
    MENU_ID_XP_ON_OFF  = 10638,
    NPC_TEXT_XP_ON_OFF = 14736,
    OPTION_ID_XP_OFF   = 0,     // "I no longer wish to gain experience."
    OPTION_ID_XP_ON    = 1      // "I wish to start gaining experience again."
};

class npc_experience : public CreatureScript
{
    public:
        npc_experience() : CreatureScript("npc_experience") { }

        struct npc_experienceAI : public ScriptedAI
        {
            npc_experienceAI(Creature* creature) : ScriptedAI(creature) { }

            bool GossipSelect(Player* player, uint32 /*menuId*/, uint32 gossipListId) override
            {
                uint32 const action = player->PlayerTalkClass->GetGossipOptionAction(gossipListId);

                switch (action)
                {
                    case GOSSIP_ACTION_INFO_DEF + 1: // XP ON selected
                        player->RemoveCharacterFlag(CHARACTER_FLAG_2_NO_XP_GAIN);
                        player->RemoveFlag(PLAYER_FLAGS, PLAYER_FLAGS_NO_XP_GAIN); // turn on XP gain
                        break;
                    case GOSSIP_ACTION_INFO_DEF + 2: // XP OFF selected
                        player->AddCharacterFlag(CHARACTER_FLAG_2_NO_XP_GAIN);
                        player->SetFlag(PLAYER_FLAGS, PLAYER_FLAGS_NO_XP_GAIN); // turn off XP gain
                        break;
                }
                CloseGossipMenuFor(player);
                return false;
            }

            bool GossipHello(Player* player) override
            {
                if (player->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_NO_XP_GAIN)) // not gaining XP
                {
                    AddGossipItemFor(player, MENU_ID_XP_ON_OFF, OPTION_ID_XP_ON, GOSSIP_SENDER_MAIN, GOSSIP_ACTION_INFO_DEF + 1);
                    SendGossipMenuFor(player, NPC_TEXT_XP_ON_OFF, me->GetGUID());
                }
                else // currently gaining XP
                {
                    AddGossipItemFor(player, MENU_ID_XP_ON_OFF, OPTION_ID_XP_OFF, GOSSIP_SENDER_MAIN, GOSSIP_ACTION_INFO_DEF + 2);
                    SendGossipMenuFor(player, NPC_TEXT_XP_ON_OFF, me->GetGUID());
                }
                return true;
            }
        };

        CreatureAI* GetAI(Creature* creature) const override
        {
            return new npc_experienceAI(creature);
        }
};

enum Fireworks
{
    NPC_OMEN                = 15467,
    NPC_MINION_OF_OMEN      = 15466,
    NPC_FIREWORK_BLUE       = 15879,
    NPC_FIREWORK_GREEN      = 15880,
    NPC_FIREWORK_PURPLE     = 15881,
    NPC_FIREWORK_RED        = 15882,
    NPC_FIREWORK_YELLOW     = 15883,
    NPC_FIREWORK_WHITE      = 15884,
    NPC_FIREWORK_BIG_BLUE   = 15885,
    NPC_FIREWORK_BIG_GREEN  = 15886,
    NPC_FIREWORK_BIG_PURPLE = 15887,
    NPC_FIREWORK_BIG_RED    = 15888,
    NPC_FIREWORK_BIG_YELLOW = 15889,
    NPC_FIREWORK_BIG_WHITE  = 15890,

    NPC_CLUSTER_BLUE        = 15872,
    NPC_CLUSTER_RED         = 15873,
    NPC_CLUSTER_GREEN       = 15874,
    NPC_CLUSTER_PURPLE      = 15875,
    NPC_CLUSTER_WHITE       = 15876,
    NPC_CLUSTER_YELLOW      = 15877,
    NPC_CLUSTER_BIG_BLUE    = 15911,
    NPC_CLUSTER_BIG_GREEN   = 15912,
    NPC_CLUSTER_BIG_PURPLE  = 15913,
    NPC_CLUSTER_BIG_RED     = 15914,
    NPC_CLUSTER_BIG_WHITE   = 15915,
    NPC_CLUSTER_BIG_YELLOW  = 15916,
    NPC_CLUSTER_ELUNE       = 15918,

    GO_FIREWORK_LAUNCHER_1  = 180771,
    GO_FIREWORK_LAUNCHER_2  = 180868,
    GO_FIREWORK_LAUNCHER_3  = 180850,
    GO_CLUSTER_LAUNCHER_1   = 180772,
    GO_CLUSTER_LAUNCHER_2   = 180859,
    GO_CLUSTER_LAUNCHER_3   = 180869,
    GO_CLUSTER_LAUNCHER_4   = 180874,

    SPELL_ROCKET_BLUE       = 26344,
    SPELL_ROCKET_GREEN      = 26345,
    SPELL_ROCKET_PURPLE     = 26346,
    SPELL_ROCKET_RED        = 26347,
    SPELL_ROCKET_WHITE      = 26348,
    SPELL_ROCKET_YELLOW     = 26349,
    SPELL_ROCKET_BIG_BLUE   = 26351,
    SPELL_ROCKET_BIG_GREEN  = 26352,
    SPELL_ROCKET_BIG_PURPLE = 26353,
    SPELL_ROCKET_BIG_RED    = 26354,
    SPELL_ROCKET_BIG_WHITE  = 26355,
    SPELL_ROCKET_BIG_YELLOW = 26356,
    SPELL_LUNAR_FORTUNE     = 26522,

    ANIM_GO_LAUNCH_FIREWORK = 3,
    ZONE_MOONGLADE          = 493,
};

Position omenSummonPos = {7558.993f, -2839.999f, 450.0214f, 4.46f};

class npc_firework : public CreatureScript
{
public:
    npc_firework() : CreatureScript("npc_firework") { }

    struct npc_fireworkAI : public ScriptedAI
    {
        npc_fireworkAI(Creature* creature) : ScriptedAI(creature) { }

        bool isCluster()
        {
            switch (me->GetEntry())
            {
                case NPC_FIREWORK_BLUE:
                case NPC_FIREWORK_GREEN:
                case NPC_FIREWORK_PURPLE:
                case NPC_FIREWORK_RED:
                case NPC_FIREWORK_YELLOW:
                case NPC_FIREWORK_WHITE:
                case NPC_FIREWORK_BIG_BLUE:
                case NPC_FIREWORK_BIG_GREEN:
                case NPC_FIREWORK_BIG_PURPLE:
                case NPC_FIREWORK_BIG_RED:
                case NPC_FIREWORK_BIG_YELLOW:
                case NPC_FIREWORK_BIG_WHITE:
                    return false;
                case NPC_CLUSTER_BLUE:
                case NPC_CLUSTER_GREEN:
                case NPC_CLUSTER_PURPLE:
                case NPC_CLUSTER_RED:
                case NPC_CLUSTER_YELLOW:
                case NPC_CLUSTER_WHITE:
                case NPC_CLUSTER_BIG_BLUE:
                case NPC_CLUSTER_BIG_GREEN:
                case NPC_CLUSTER_BIG_PURPLE:
                case NPC_CLUSTER_BIG_RED:
                case NPC_CLUSTER_BIG_YELLOW:
                case NPC_CLUSTER_BIG_WHITE:
                case NPC_CLUSTER_ELUNE:
                default:
                    return true;
            }
        }

        GameObject* FindNearestLauncher()
        {
            GameObject* launcher = nullptr;

            if (isCluster())
            {
                GameObject* launcher1 = GetClosestGameObjectWithEntry(me, GO_CLUSTER_LAUNCHER_1, 0.5f);
                GameObject* launcher2 = GetClosestGameObjectWithEntry(me, GO_CLUSTER_LAUNCHER_2, 0.5f);
                GameObject* launcher3 = GetClosestGameObjectWithEntry(me, GO_CLUSTER_LAUNCHER_3, 0.5f);
                GameObject* launcher4 = GetClosestGameObjectWithEntry(me, GO_CLUSTER_LAUNCHER_4, 0.5f);

                if (launcher1)
                    launcher = launcher1;
                else if (launcher2)
                    launcher = launcher2;
                else if (launcher3)
                    launcher = launcher3;
                else if (launcher4)
                    launcher = launcher4;
            }
            else
            {
                GameObject* launcher1 = GetClosestGameObjectWithEntry(me, GO_FIREWORK_LAUNCHER_1, 0.5f);
                GameObject* launcher2 = GetClosestGameObjectWithEntry(me, GO_FIREWORK_LAUNCHER_2, 0.5f);
                GameObject* launcher3 = GetClosestGameObjectWithEntry(me, GO_FIREWORK_LAUNCHER_3, 0.5f);

                if (launcher1)
                    launcher = launcher1;
                else if (launcher2)
                    launcher = launcher2;
                else if (launcher3)
                    launcher = launcher3;
            }

            return launcher;
        }

        uint32 GetFireworkSpell(uint32 entry)
        {
            switch (entry)
            {
                case NPC_FIREWORK_BLUE:
                    return SPELL_ROCKET_BLUE;
                case NPC_FIREWORK_GREEN:
                    return SPELL_ROCKET_GREEN;
                case NPC_FIREWORK_PURPLE:
                    return SPELL_ROCKET_PURPLE;
                case NPC_FIREWORK_RED:
                    return SPELL_ROCKET_RED;
                case NPC_FIREWORK_YELLOW:
                    return SPELL_ROCKET_YELLOW;
                case NPC_FIREWORK_WHITE:
                    return SPELL_ROCKET_WHITE;
                case NPC_FIREWORK_BIG_BLUE:
                    return SPELL_ROCKET_BIG_BLUE;
                case NPC_FIREWORK_BIG_GREEN:
                    return SPELL_ROCKET_BIG_GREEN;
                case NPC_FIREWORK_BIG_PURPLE:
                    return SPELL_ROCKET_BIG_PURPLE;
                case NPC_FIREWORK_BIG_RED:
                    return SPELL_ROCKET_BIG_RED;
                case NPC_FIREWORK_BIG_YELLOW:
                    return SPELL_ROCKET_BIG_YELLOW;
                case NPC_FIREWORK_BIG_WHITE:
                    return SPELL_ROCKET_BIG_WHITE;
                default:
                    return 0;
            }
        }

        uint32 GetFireworkGameObjectId()
        {
            uint32 spellId = 0;

            switch (me->GetEntry())
            {
                case NPC_CLUSTER_BLUE:
                    spellId = GetFireworkSpell(NPC_FIREWORK_BLUE);
                    break;
                case NPC_CLUSTER_GREEN:
                    spellId = GetFireworkSpell(NPC_FIREWORK_GREEN);
                    break;
                case NPC_CLUSTER_PURPLE:
                    spellId = GetFireworkSpell(NPC_FIREWORK_PURPLE);
                    break;
                case NPC_CLUSTER_RED:
                    spellId = GetFireworkSpell(NPC_FIREWORK_RED);
                    break;
                case NPC_CLUSTER_YELLOW:
                    spellId = GetFireworkSpell(NPC_FIREWORK_YELLOW);
                    break;
                case NPC_CLUSTER_WHITE:
                    spellId = GetFireworkSpell(NPC_FIREWORK_WHITE);
                    break;
                case NPC_CLUSTER_BIG_BLUE:
                    spellId = GetFireworkSpell(NPC_FIREWORK_BIG_BLUE);
                    break;
                case NPC_CLUSTER_BIG_GREEN:
                    spellId = GetFireworkSpell(NPC_FIREWORK_BIG_GREEN);
                    break;
                case NPC_CLUSTER_BIG_PURPLE:
                    spellId = GetFireworkSpell(NPC_FIREWORK_BIG_PURPLE);
                    break;
                case NPC_CLUSTER_BIG_RED:
                    spellId = GetFireworkSpell(NPC_FIREWORK_BIG_RED);
                    break;
                case NPC_CLUSTER_BIG_YELLOW:
                    spellId = GetFireworkSpell(NPC_FIREWORK_BIG_YELLOW);
                    break;
                case NPC_CLUSTER_BIG_WHITE:
                    spellId = GetFireworkSpell(NPC_FIREWORK_BIG_WHITE);
                    break;
                case NPC_CLUSTER_ELUNE:
                    spellId = GetFireworkSpell(urand(NPC_FIREWORK_BLUE, NPC_FIREWORK_WHITE));
                    break;
            }

            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
            if (spellInfo && spellInfo->Effects[0].Effect == SPELL_EFFECT_SUMMON_OBJECT_WILD)
                return spellInfo->Effects[0].MiscValue;

            return 0;
        }

        void Reset() override
        {
            if (GameObject* launcher = FindNearestLauncher())
            {
                launcher->SendCustomAnim(ANIM_GO_LAUNCH_FIREWORK);
                me->SetOrientation(launcher->GetOrientation() + float(M_PI) / 2);
            }
            else
                return;

            if (isCluster())
            {
                // Check if we are near Elune'ara lake south, if so try to summon Omen or a minion
                if (me->GetZoneId() == ZONE_MOONGLADE)
                {
                    if (!me->FindNearestCreature(NPC_OMEN, 100.0f) && me->GetDistance2d(omenSummonPos.GetPositionX(), omenSummonPos.GetPositionY()) <= 100.0f)
                    {
                        switch (urand(0, 9))
                        {
                            case 0:
                            case 1:
                            case 2:
                            case 3:
                                if (Creature* minion = me->SummonCreature(NPC_MINION_OF_OMEN, me->GetPositionX()+frand(-5.0f, 5.0f), me->GetPositionY()+frand(-5.0f, 5.0f), me->GetPositionZ(), 0.0f, TEMPSUMMON_CORPSE_TIMED_DESPAWN, 20000))
                                    minion->AI()->AttackStart(me->SelectNearestPlayer(20.0f));
                                break;
                            case 9:
                                me->SummonCreature(NPC_OMEN, omenSummonPos);
                                break;
                        }
                    }
                }
                if (me->GetEntry() == NPC_CLUSTER_ELUNE)
                    DoCast(SPELL_LUNAR_FORTUNE);

                float displacement = 0.7f;
                for (uint8 i = 0; i < 4; i++)
                    me->SummonGameObject(GetFireworkGameObjectId(), me->GetPositionX() + (i % 2 == 0 ? displacement : -displacement), me->GetPositionY() + (i > 1 ? displacement : -displacement), me->GetPositionZ() + 4.0f, me->GetOrientation(), QuaternionData(), 1);
            }
            else
                //me->CastSpell(me, GetFireworkSpell(me->GetEntry()), true);
                me->CastSpell(Position{ me->GetPositionX(), me->GetPositionY(), me->GetPositionZ() }, GetFireworkSpell(me->GetEntry()), true);
        }
    };

    CreatureAI* GetAI(Creature* creature) const override
    {
        return new npc_fireworkAI(creature);
    }
};

/*#####
# npc_spring_rabbit
#####*/

enum rabbitSpells
{
    SPELL_SPRING_FLING          = 61875,
    SPELL_SPRING_RABBIT_JUMP    = 61724,
    SPELL_SPRING_RABBIT_WANDER  = 61726,
    SPELL_SUMMON_BABY_BUNNY     = 61727,
    SPELL_SPRING_RABBIT_IN_LOVE = 61728,
    NPC_SPRING_RABBIT           = 32791
};

class npc_spring_rabbit : public CreatureScript
{
public:
    npc_spring_rabbit() : CreatureScript("npc_spring_rabbit") { }

    CreatureAI* GetAI(Creature* creature) const override
    {
        return new npc_spring_rabbitAI(creature);
    }

    struct npc_spring_rabbitAI : public ScriptedAI
    {
        npc_spring_rabbitAI(Creature* creature) : ScriptedAI(creature)
        {
            Initialize();
        }

        void Initialize()
        {
            inLove = false;
            rabbitGUID.Clear();
            jumpTimer = urand(5000, 10000);
            bunnyTimer = urand(10000, 20000);
            searchTimer = urand(5000, 10000);
        }

        bool inLove;
        uint32 jumpTimer;
        uint32 bunnyTimer;
        uint32 searchTimer;
        ObjectGuid rabbitGUID;

        void Reset() override
        {
            Initialize();
            if (Unit* owner = me->GetOwner())
                me->FollowTarget(owner);
        }

        void JustEngagedWith(Unit* /*who*/) override { }

        void DoAction(int32 /*param*/) override
        {
            inLove = true;
            if (Unit* owner = me->GetOwner())
                owner->CastSpell(owner, SPELL_SPRING_FLING, true);
        }

        void UpdateAI(uint32 diff) override
        {
            if (inLove)
            {
                if (jumpTimer <= diff)
                {
                    if (Unit* rabbit = ObjectAccessor::GetUnit(*me, rabbitGUID))
                        DoCast(rabbit, SPELL_SPRING_RABBIT_JUMP);
                    jumpTimer = urand(5000, 10000);
                } else jumpTimer -= diff;

                if (bunnyTimer <= diff)
                {
                    DoCast(SPELL_SUMMON_BABY_BUNNY);
                    bunnyTimer = urand(20000, 40000);
                } else bunnyTimer -= diff;
            }
            else
            {
                if (searchTimer <= diff)
                {
                    if (Creature* rabbit = me->FindNearestCreature(NPC_SPRING_RABBIT, 10.0f))
                    {
                        if (rabbit == me || rabbit->HasAura(SPELL_SPRING_RABBIT_IN_LOVE))
                            return;

                        me->AddAura(SPELL_SPRING_RABBIT_IN_LOVE, me);
                        DoAction(1);
                        rabbit->AddAura(SPELL_SPRING_RABBIT_IN_LOVE, rabbit);
                        rabbit->AI()->DoAction(1);
                        rabbit->CastSpell(rabbit, SPELL_SPRING_RABBIT_JUMP, true);
                        rabbitGUID = rabbit->GetGUID();
                    }
                    searchTimer = urand(5000, 10000);
                } else searchTimer -= diff;
            }
        }
    };
};

class npc_imp_in_a_ball : public CreatureScript
{
private:
    enum
    {
        SAY_RANDOM,

        EVENT_TALK = 1,
    };

public:
    npc_imp_in_a_ball() : CreatureScript("npc_imp_in_a_ball") { }

    struct npc_imp_in_a_ballAI : public ScriptedAI
    {
        npc_imp_in_a_ballAI(Creature* creature) : ScriptedAI(creature)
        {
            summonerGUID.Clear();
        }

        void IsSummonedBy(Unit* summoner) override
        {
            if (summoner->GetTypeId() == TYPEID_PLAYER)
            {
                summonerGUID = summoner->GetGUID();
                events.ScheduleEvent(EVENT_TALK, 3000);
            }
        }

        void UpdateAI(uint32 diff) override
        {
            events.Update(diff);

            if (events.ExecuteEvent() == EVENT_TALK)
            {
                if (Player* owner = ObjectAccessor::GetPlayer(*me, summonerGUID))
                {
                    sCreatureTextMgr->SendChat(me, SAY_RANDOM, owner,
                        owner->GetGroup() ? CHAT_MSG_MONSTER_PARTY : CHAT_MSG_MONSTER_WHISPER, LANG_ADDON, TEXT_RANGE_NORMAL);
                }
            }
        }

    private:
        EventMap events;
        ObjectGuid summonerGUID;
    };

    CreatureAI* GetAI(Creature* creature) const override
    {
        return new npc_imp_in_a_ballAI(creature);
    }
};

enum StableMasters
{
    SPELL_MINIWING                  = 54573,
    SPELL_JUBLING                   = 54611,
    SPELL_DARTER                    = 54619,
    SPELL_WORG                      = 54631,
    SPELL_SMOLDERWEB                = 54634,
    SPELL_CHIKEN                    = 54677,
    SPELL_WOLPERTINGER              = 54688,

    NPC_TEXT_STABLE_MASTER_HUNTER   = 13557,
    NPC_TEXT_STABLE_MASTER_OTHER    = 13584,
    GOSSIP_MENU_STABLE_MASTER       = 9821,
    STABLE_MASTER_GOSSIP_SUB_MENU   = 9820
};

class npc_stable_master : public CreatureScript
{
    public:
        npc_stable_master() : CreatureScript("npc_stable_master") { }

        struct npc_stable_masterAI : public ScriptedAI
        {
            npc_stable_masterAI(Creature* creature) : ScriptedAI(creature) { }

            bool GossipSelect(Player* player, uint32 menuId, uint32 gossipListId) override
            {
                if (menuId == STABLE_MASTER_GOSSIP_SUB_MENU)
                {
                    switch (gossipListId)
                    {
                        case 0:
                            player->CastSpell(player, SPELL_MINIWING, false);
                            break;
                        case 1:
                            player->CastSpell(player, SPELL_JUBLING, false);
                            break;
                        case 2:
                            player->CastSpell(player, SPELL_DARTER, false);
                            break;
                        case 3:
                            player->CastSpell(player, SPELL_WORG, false);
                            break;
                        case 4:
                            player->CastSpell(player, SPELL_SMOLDERWEB, false);
                            break;
                        case 5:
                            player->CastSpell(player, SPELL_CHIKEN, false);
                            break;
                        case 6:
                            player->CastSpell(player, SPELL_WOLPERTINGER, false);
                            break;
                        default:
                            return false;
                    }
                }
                else
                {
                    if (gossipListId == 0)
                    {
                        player->GetSession()->SendStablePet(me->GetGUID());
                        player->PlayerTalkClass->SendCloseGossip();
                    }
                }
                return false;
            }
        };

        CreatureAI* GetAI(Creature* creature) const override
        {
            return new npc_stable_masterAI(creature);
        }
};

enum TrainWrecker
{
    GO_TOY_TRAIN          = 193963,
    SPELL_TOY_TRAIN_PULSE =  61551,
    SPELL_WRECK_TRAIN     =  62943,
    ACTION_WRECKED        =      1,
    EVENT_DO_JUMP         =      1,
    EVENT_DO_FACING       =      2,
    EVENT_DO_WRECK        =      3,
    EVENT_DO_DANCE        =      4,
    MOVEID_CHASE          =      1,
    MOVEID_JUMP           =      2
};
class npc_train_wrecker : public CreatureScript
{
    public:
        npc_train_wrecker() : CreatureScript("npc_train_wrecker") { }

        struct npc_train_wreckerAI : public NullCreatureAI
        {
            npc_train_wreckerAI(Creature* creature) : NullCreatureAI(creature), _isSearching(true), _nextAction(0), _timer(1 * IN_MILLISECONDS) { }

            GameObject* VerifyTarget() const
            {
                if (GameObject* target = ObjectAccessor::GetGameObject(*me, _target))
                    return target;
                me->HandleEmoteCommand(EMOTE_ONESHOT_RUDE);
                me->DespawnOrUnsummon(3 * IN_MILLISECONDS);
                return nullptr;
            }

            void UpdateAI(uint32 diff) override
            {
                if (_isSearching)
                {
                    if (diff < _timer)
                        _timer -= diff;
                    else
                    {
                        if (GameObject* target = me->FindNearestGameObject(GO_TOY_TRAIN, 15.0f))
                        {
                            _isSearching = false;
                            _target = target->GetGUID();
                            me->SetWalk(true);
                            me->GetMotionMaster()->MovePoint(MOVEID_CHASE, target->GetNearPosition(3.0f, target->GetAngle(me)));
                        }
                        else
                            _timer = 3 * IN_MILLISECONDS;
                    }
                }
                else
                {
                    switch (_nextAction)
                    {
                        case EVENT_DO_JUMP:
                            if (GameObject* target = VerifyTarget())
                                me->GetMotionMaster()->MoveJump(*target, 5.0, 10.0, MOVEID_JUMP);
                            _nextAction = 0;
                            break;
                        case EVENT_DO_FACING:
                            if (GameObject* target = VerifyTarget())
                            {
                                me->SetFacingTo(target->GetOrientation());
                                me->HandleEmoteCommand(EMOTE_ONESHOT_ATTACK1H);
                                _timer = 1.5 * AsUnderlyingType(IN_MILLISECONDS);
                                _nextAction = EVENT_DO_WRECK;
                            }
                            else
                                _nextAction = 0;
                            break;
                        case EVENT_DO_WRECK:
                            if (diff < _timer)
                            {
                                _timer -= diff;
                                break;
                            }
                            if (GameObject* target = VerifyTarget())
                            {
                                me->CastSpell(target, SPELL_WRECK_TRAIN, false);
                                target->AI()->DoAction(ACTION_WRECKED);
                                _timer = 2 * IN_MILLISECONDS;
                                _nextAction = EVENT_DO_DANCE;
                            }
                            else
                                _nextAction = 0;
                            break;
                        case EVENT_DO_DANCE:
                            if (diff < _timer)
                            {
                                _timer -= diff;
                                break;
                            }
                            me->SetUInt32Value(UNIT_NPC_EMOTESTATE, EMOTE_ONESHOT_DANCE);
                            me->DespawnOrUnsummon(5 * IN_MILLISECONDS);
                            _nextAction = 0;
                            break;
                        default:
                            break;
                    }
                }
            }

            void MovementInform(uint32 /*type*/, uint32 id) override
            {
                if (id == MOVEID_CHASE)
                    _nextAction = EVENT_DO_JUMP;
                else if (id == MOVEID_JUMP)
                    _nextAction = EVENT_DO_FACING;
            }

        private:
            bool _isSearching;
            uint8 _nextAction;
            uint32 _timer;
            ObjectGuid _target;
        };

        CreatureAI* GetAI(Creature* creature) const override
        {
            return new npc_train_wreckerAI(creature);
        }
};


}

void AddSC_npcs_special_toys()
{
    using namespace NpcSpecial;
    new npc_wormhole();
    new npc_pet_trainer();
    new npc_experience();
    new npc_firework();
    new npc_spring_rabbit();
    new npc_imp_in_a_ball();
    new npc_stable_master();
    new npc_train_wrecker();
}
