/*
 * This file is part of the TrinityCore Project. See AUTHORS file for Copyright information
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or (at your
 * option) any later version.
 */

#ifndef DEF_BOSS_MAGMAW_SHARED_H
#define DEF_BOSS_MAGMAW_SHARED_H

namespace BlackwingDescent::Magmaw
{
enum Spells
{
    // Magmaw
    SPELL_RIDE_VEHICLE                          = 77901,
    SPELL_BIRTH                                 = 26586,
    SPELL_MAGMA_SPIT_TARGETING                  = 95280,
    SPELL_MAGMA_SPIT_MISSILE                    = 78359,
    SPELL_LAVA_SPEW                             = 77839,
    SPELL_MAGMA_SPIT_MOLTEN_TANTRUM             = 78068,
    SPELL_MANGLE_1                              = 89773,
    SPELL_MANGLE_2                              = 78412,
    SPELL_MANGLE_TARGETING                      = 92047,
    SPELL_SWELTERING_ARMOR                      = 78199,
    SPELL_PILLAR_OF_FLAME                       = 77998,
    SPELL_PILLAR_OF_FLAME_MISSILE_PERIODIC      = 78006,
    SPELL_PILLAR_OF_FLAME_SET_VEHICLE_ID        = 77994,
    SPELL_MASSIVE_CRASH                         = 88253,
    SPELL_IMPALE_SELF                           = 77907,
    SPELL_EJECT_PASSENGER_3                     = 95204,
    SPELL_EMOTE_MAGMA_LAVA_SPLASH               = 79461,
    SPELL_EMOTE_SPELLCASTDIRECTED               = 20718,

    // Exposed Head of Magmaw
    SPELL_POINT_OF_VULNERABILITY_SHARE_DAMAGE   = 79010,
    SPELL_POINT_OF_VULNERABILITY                = 79011,
    SPELL_RIDE_VEHICLE_EXPOSED_HEAD             = 89743,
    SPELL_QUEST_INVIS_5                         = 95478,
    SPELL_RIDE_VEHICLE_HEAD                     = 94996,

    // Pillar of Flame
    SPELL_PILLAR_OF_FLAME_DUMMY                 = 78017,
    SPELL_PILLAR_OF_FLAME_PERIODIC              = 77970,

    // Magmaw's Pincer
    SPELL_LAUNCH_HOOK_1                         = 77917,
    SPELL_LAUNCH_HOOK_2                         = 77941,
    SPELL_EJECT_PASSENGER_1                     = 77946,

    // Magmaw Spike Stalker
    SPELL_CHAIN_VISUAL_1                        = 77940,
    SPELL_CHAIN_VISUAL_2                        = 77929,
    SPELL_EJECT_PASSENGER                       = 78643,

    // Lava Parasite
    SPELL_LAVA_PARASITE_PROC_AURA               = 78019,
    SPELL_LAVA_PARASITE_RIDE_VEHICLE            = 78020,
    SPELL_PARASITIC_INFECTION_VOMIT             = 78097,
    SPELL_PARASITIC_INFECTION_DAMAGE            = 78941,

    // Nefarian
    SPELL_BLAZING_INFERNO_TARGETING             = 94317,
    SPELL_BLAZING_INFERNO                       = 92153,
    SPELL_SHADOW_BREATH_TARGETING               = 95536,
    SPELL_SHADOW_BREATH                         = 92173,

    // Blazing Bone Construct
    SPELL_IGNITION                              = 92119,
    SPELL_FIERY_SLASH                           = 92144,
    SPELL_ARMAGEDDON                            = 92177
};

enum Actions
{
    ACTION_IMPALE_MAGMAW            = 0,
    ACTION_ENABLE_MOUNTING          = 1,
    ACTION_DISABLE_MOUNTING         = 2,
    ACTION_EXPOSE_HEAD              = 4,
    ACTION_COVER_HEAD               = 5,
    ACTION_SCHEDULE_SHADOW_BREATH   = 0,
    ACTION_MAGMAW_DEAD              = 1
};

enum Data
{
    DATA_FREE_PINCER = 0
};
}

#endif
