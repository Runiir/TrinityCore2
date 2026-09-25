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

#ifndef DEF_BOSS_NEFARIANS_END_H
#define DEF_BOSS_NEFARIANS_END_H

#include "Define.h"

// Shared identities of the Nefarian's End scripts: boss_nefarians_end.cpp
// (Nefarian and Onyxia), boss_nefarians_end_adds.cpp (intro and adds) and
// boss_nefarians_end_spells.cpp (spell and aura scripts).
namespace BlackwingDescent::NefariansEnd
{
enum Spells
{
    // Nefarian
    SPELL_INTRO_2_STALKER_TRANSFORM                     = 78750,
    SPELL_INTRO_3_SHRINK_AURA                           = 78753,
    SPELL_INTRO_4_LIFT_OFF_ANIM_KIT                     = 78692,
    SPELL_INTRO_5A_START_FIGHT_PROC                     = 78730,
    SPELL_ELECTRICAL_CHARGE_NEFARIAN                    = 95793,
    SPELL_SHADOW_OF_COWARDICE                           = 79355,
    SPELL_CHILDREN_OF_DEATHWING_NEFARIAN                = 80787,
    SPELL_HAIL_OF_BONES                                 = 78679,
    SPELL_NEFARIAN_PHASE_2_HEALTH_AURA                  = 81582,
    SPELL_SHADOWFLAME_BARRAGE                           = 78621,
    SPELL_BRUSHFIRE_PRE_START_PERIODIC                  = 94630,
    SPELL_BRUSHFIRE_START                               = 79813,
    SPELL_DOMINION_DUMMY                                = 94211,
    SPELL_DOMINION_OVERRIDE_ACTION_BAR                  = 79318,
    SPELL_EXPLOSIVE_CINDERS                             = 79339,
    SPELL_EXPLOSIVE_CINDERS_EXPLOSION                   = 79347,
    SPELL_BERSERK                                       = 26662,

    // Onyxia
    SPELL_PERMANENT_FEIGN_DEATH_1                       = 29266,
    SPELL_ONYXIA_START_FIGHT_1_PERIODIC                 = 81516,
    SPELL_ELECTRICAL_CHARGE_ONYXIA                      = 78949,
    SPELL_ELECTRICAL_OVERLOAD                           = 78999,
    SPELL_LIGHTNING_DISCHARGE                           = 78090,
    SPELL_LIGHTNING_DISCHARGE_VISUAL_LEFT_1             = 81435,
    SPELL_LIGHTNING_DISCHARGE_VISUAL_LEFT_2             = 81436,
    SPELL_LIGHTNING_DISCHARGE_VISUAL_RIGHT_1            = 81437,
    SPELL_LIGHTNING_DISCHARGE_VISUAL_RIGHT_2            = 81438,
    SPELL_LIGHTNING_DISCHARGE_CONE_BACK                 = 77833,
    SPELL_LIGHTNING_DISCHARGE_CONE_FRONT                = 77836,
    SPELL_LIGHTNING_DISCHARGE_DAMAGE                    = 77943,
    SPELL_CHILDREN_OF_DEATHWING_ONYXIA                  = 80785,

    // Nefarian and Onyxia
    SPELL_TAIL_LASH                                     = 77827,
    SPELL_SHADOWFLAME_BREATH                            = 77826,
    SPELL_SHADOW_OF_COWARDICE_DAMAGE                    = 79353,
    SPELL_SHADOW_OF_COWARDICE_DUMMY                     = 80963,

    // Nefarian's Lightning Machine
    SPELL_ELECTROCUTE                                   = 81198,
    SPELL_ELECTROCUTE_DAMAGE                            = 81272,

    // Animated Bone Warrior
    SPELL_FULL_POWER_NO_REGEN                           = 78120,
    SPELL_ANIMATE_BONES                                 = 78122,
    SPELL_PERMANENT_FEIGN_DEATH_2                       = 70628,
    SPELL_CLEAR_ALL_DEBUFFS                             = 34098,
    SPELL_EMPOWER                                       = 79330,

    // Chromatic Prototype
    SPELL_JUMP_DOWN_TO_PLATFORM                         = 79205,
    SPELL_READY_UNARMED                                 = 94610,
    SPELL_DUMMY_NUKE                                    = 80776,
    SPELL_BLAST_NOVA                                    = 80734,

    // Invisible Stalker (Cataclysm Boss, Ignore Combat, Floating)
    SPELL_INTRO_1_TRANSFORM_VISUAL                      = 78205,
    SPELL_CHAINS_A_STEEL                                = 81159,
    SPELL_CHAINS_B_STEEL                                = 81174,
    SPELL_CHAINS_C_STEEL                                = 81176,
    SPELL_CHAINS_A_LIGHTNING                            = 81158,
    SPELL_CHAINS_B_LIGHTNING                            = 81175,
    SPELL_CHAINS_C_LIGHTNING                            = 81177,

    // Controller Stalker
    SPELL_PET_HACK_1                                    = 95278, // Todo: we don't need this (yet). This is going to disable pathfinding for pets.

    // Shadowblase Flashpoint / Shadowblaze
    SPELL_BRUSHFIRE_FLASHPOINT_CONTROL                  = 79392,
    SPELL_BRUSHFIRE_GROWTH                              = 79393,
    SPELL_BRUSHFIRE_BURN_AURA                           = 79396,
    SPELL_BRUSHFIRE_SUMMON                              = 79405,
    SPELL_BRUSHFIRE_CHECK_VALID_LOCATION                = 79401,

    // Dominion Stalker
    SPELL_DOMINION_DETERMINE_FARTHEST_PORTAL_STALKER    = 81664,
    SPELL_DOMINION_PORTAL_TRIGGER                       = 81752,
    SPELL_DOMINION_PORTAL_BEAM                          = 81709,

    // Players
    SPELL_DOMINION_IMMUNITY                             = 95900,
    SPELL_SUMMON_DOMINION_STALKER_NORTH                 = 81665,
    SPELL_SUMMON_DOMINION_STALKER_EAST                  = 81745,
    SPELL_SUMMON_DOMINION_STALKER_SOUTH                 = 81746,
    SPELL_SUMMON_DOMINION_STALKER_WEST                  = 81747,
    SPELL_STOLEN_POWER                                  = 80627,
    SPELL_INSTAKILL_SELF                                = 29878
};

enum Texts
{
    // Nefarian
    SAY_ANNOUNCE_AIR_CRACKLES   = 0,
    SAY_HAIL_OF_BONES           = 1,
    SAY_ONYXIA_DIED             = 2,
    SAY_MOLTEN_LAVA             = 3,
    SAY_LAND_PHASE_THREE        = 4,
    SAY_SHADOWBLAZE_SPARK       = 5,
    SAY_SLAY                    = 6,
    SAY_DEATH                   = 7,
    SAY_DOMINION                = 8,

    // Onyxia
    SAY_ANNOUNCE_WARNING_1      = 0,
    SAY_ANNOUNCE_WARNING_2      = 1,

    // Lord Victor Nefarius
    SAY_INTRO_1                 = 0,
    SAY_INTRO_2                 = 1,
    SAY_INTRO_3                 = 2
};

enum Events
{
    // Nefarian
    EVENT_CHAIN_ONYXIA = 1,
    EVENT_REMOVE_TRANSFORM_AURA,
    EVENT_LIFT_OFF,
    EVENT_ANNOUNCE_AIR_CRACKLES,
    EVENT_MAKE_ATTACKABLE,
    EVENT_FLY_CYCLIC_PATH,
    EVENT_PREPARE_LANDING,
    EVENT_LAND_PHASE_ONE,
    EVENT_LANDED,
    EVENT_ENGAGE_PLAYERS,
    EVENT_SAY_ONYXIA_DEAD,
    EVENT_MOVE_TO_CENTER,
    EVENT_LIFTOFF_PHASE_TWO,
    EVENT_SUMMON_CHROMATIC_PROTOTYPES,
    EVENT_LOWER_ELEVATOR,
    EVENT_ELEVATOR_LOWERED,
    EVENT_SHADOWFLAME_BARRAGE,
    EVENT_SAY_PHASE_TWO,
    EVENT_ENTER_PHASE_THREE,
    EVENT_SAY_PHASE_THREE,
    EVENT_LAND_PHASE_THREE,
    EVENT_ELECTROCUTE,
    EVENT_DOMINION,
    EVENT_EXPLOSIVE_CINDERS,
    EVENT_BERSERK,

    // Onyxia
    EVENT_LIGHTNING_DISCHARGE,
    EVENT_ELECTRICAL_CHARGE,
    EVENT_SHADOW_OF_CORWARDICE,

    // Nefarian and Onyxia
    EVENT_TAIL_LASH,
    EVENT_SHADOWFLAME_BREATH,

    // Lord Victor Nefarius
    EVENT_TALK_INTRO_2,
    EVENT_TALK_INTRO_3,
    EVENT_CAST_TRANSFORM_VISUAL,
    EVENT_RAISE_ELEVATOR,

    // Chromatic Prototype
    EVENT_JUMP_DOWN_TO_PLATFORM,
    EVENT_READY_PROTOTYPE,
    EVENT_DUMMY_NUKE,
    EVENT_BLAST_NOVA,
    EVENT_DISENGAGE_PLAYERS,
};

enum Phases
{
    PHASE_ONE   = 1,
    PHASE_TWO   = 2,
    PHASE_THREE = 3
};

enum Actions
{
    // Lord Victor Nefarius
    ACTION_START_INTRO              = 1,

    // Nefarian
    ACTION_ONYXIA_ENGAGED           = 1,
    ACTION_ONYXIA_DIED              = 2,

    // Onyxia
    ACTION_REANIMATED               = 1,
    ACTION_UPDATE_ELECTRICAL_CHARGE = 2,
    ACTION_NEFARIAN_LANDED          = 3,

    // Chromatic Prototype
    ACTION_DISENGAGE_PLAYERS        = 1,

    // Shadowblaze Flashpoint / Shadowblaze
    ACTION_DESPAWN_FLAMES           = 1,
    ACTION_SPREAD_FLAMES            = 2
};

enum TransportStopFrames
{
    TRANSPORT_STOP_FRAME_LOWERED    = 0,
    TRANSPORT_STOP_FRAME_RAISED     = 1
};

enum SummonGroups
{
    SUMMON_GROUP_ELEVATOR           = 0,
    SUMMON_GROUP_CONTROLLER_STALKER = 1
};

enum MovePoints
{
    // Nefarian
    POINT_NONE              = 0,
    POINT_LIFTOFF           = 1,
    POINT_PREPARE_LANDING   = 2,
    POINT_LAND              = 3,
    POINT_ELEVATOR_CENTER   = 4,

    // Chromatic Prototype
    POINT_JUMP_DOWN         = 1
};

enum EncounterFrames
{
    FRAME_INDEX_CHROMATIC_PROTOTYPE = 1,
    FRAME_INDEX_ONYXIA              = 2,
    FRAME_INDEX_NEFARIAN            = 3
};

enum Misc
{
    SOUND_ID_ROAR = 7274
};

static constexpr uint8 const MaxChromaticPrototypes = 3;
}

#endif
