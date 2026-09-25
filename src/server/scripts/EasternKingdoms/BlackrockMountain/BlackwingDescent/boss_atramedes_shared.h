/*
 * This file is part of the TrinityCore Project. See AUTHORS file for Copyright information
 *
 * This program is free software; you can redistribute it and/or modify it
 * under the terms of the GNU General Public License as published by the
 * Free Software Foundation; either version 2 of the License, or (at your
 * option) any later version.
 */

#ifndef DEF_BOSS_ATRAMEDES_SHARED_H
#define DEF_BOSS_ATRAMEDES_SHARED_H

#include "Position.h"

// Identifiers shared by the Atramedes creature AIs (boss_atramedes.cpp) and
// its spell scripts (boss_atramedes_spells.cpp).
namespace BlackwingDescent::Atramedes
{
enum Spells
{
    // Atramedes
    SPELL_ROARING_BREATH                    = 81573,
    SPELL_DEVASTATION_TRIGGER               = 78898,
    SPELL_SOUND_BAR                         = 89683,
    SPELL_DEVASTATION                       = 78868,
    SPELL_SONAR_PULSE                       = 77672,
    SPELL_MODULATION                        = 77612,
    SPELL_SEARING_FLAME                     = 77840,
    SPELL_SONIC_BREATH                      = 78075,
    SPELL_SONIC_BREATH_CAST                 = 78098,
    SPELL_TAKE_OFF_ANIM_KIT                 = 86915,
    SPELL_SONAR_PULSE_TRIGGER               = 92519,
    SPELL_SONAR_BOMB                        = 92557,
    SPELL_ROARING_FLAME_BREATH              = 78207,

    // Player Sound Bar aura, applied by SPELL_SOUND_BAR every second
    // (client aura 346 ENABLE_ALT_POWER, UnitPowerBar 23).
    SPELL_SOUND_BAR_PLAYER                  = 88824,

    // Sonar Pulse
    SPELL_SONAR_PULSE_PERIODIC_TRIGGER      = 77674,

    // Tracking Flames & Reverberating Flame
    SPELL_TRACKING                          = 78092,

    // Reverberating Flame
    SPELL_ROARING_FLAME_BREATH_REVERSE_CAST = 78230,
    SPELL_ROARING_FLAME_SUMMON              = 78272,
    SPELL_AGGRO_CREATOR                     = 63709,
    SPELL_SONIC_FLAMES                      = 78945,
    // Stacking +20% speed from the Building Speed Trigger addon aura (78217).
    // Difficulty variants: SpellDifficulty row 3135.
    SPELL_BUILDING_SPEED_EFFECT             = 78218,

    // Lord Victor Nefarius
    SPELL_SUMMON_IMP                        = 92625,
    SPELL_DESTROY_SHIELD                    = 92607,
    SPELL_APPLY_VEHICLE_PERIODIC            = 92647,

    // Obnoxious Imp
    SPELL_PHASE_SHIFT                       = 92681,
    SPELL_PESTERED                          = 92685,
    SPELL_OBNOXIOUS                         = 92677,

    // Player
    SPELL_RESONATING_CLASH_GROUND           = 77611,
    SPELL_RESONATING_CLASH_AIR              = 78168,
    SPELL_RESONATING_CLASH_RESET_ENERGY     = 77709,
    SPELL_NOISY                             = 78897
};

enum Texts
{
    // Atramedes
    SAY_AGGRO                   = 0,
    SAY_ANNOUNCE_SEARING_FLAME  = 1,
    SAY_SEARING_FLAME           = 2,
    SAY_FLIGHT_PHASE            = 3,
    SAY_SLAY                    = 4,
    SAY_DEATH                   = 5,

    // Lord Victor Nefarius
    SAY_INTRO                   = 0,
    SAY_SUMMON_FIEND            = 1,
    SAY_DESTROY_SHIELD          = 2
};

enum Sounds
{
    SOUND_ID_ATRAMEDES_VERTIGO = 20828
};

enum Events
{
    // Atramedes
    EVENT_ROARING_BREATH = 1,
    EVENT_CLOSE_DOOR,
    EVENT_FLY_TO_INTRO_LAND_POSITION,
    EVENT_SONAR_PULSE,
    EVENT_MODULATION,
    EVENT_SEARING_FLAME,
    EVENT_SONIC_BREATH,
    EVENT_LIFTOFF,
    EVENT_LAND,
    EVENT_LANDED,
    EVENT_REENGAGE_PLAYERS,

    // Lord Victor Nefarius
    EVENT_SAY_INTRO,
    EVENT_SUMMON_FIEND,

    // Obnoxious Imp
    EVENT_FOCUS_PLAYER,
    EVENT_CHASE_PLAYER,
    EVENT_OBNOXIOUS,

    // Reverberating Flame
    EVENT_MOVE_TO_DWARVEN_SHIELD,
    EVENT_CHECK_TRACKING_TARGET
};

enum Actions
{
    // Atramedes
    ACTION_START_INTRO              = 0,

    // Lord Victor Nefarius
    ACTION_DESTROY_SHIELD           = 0,
    ACTION_STOP_SUMMONING_FIENDS    = 1,
    ACTION_START_SUMMONING_FIENDS   = 2,

    // Obnoxious Imp
    ACTION_PLAYER_ENTERED           = 0,
    ACTION_PLAYER_LEFT              = 1
};

enum MovePoints
{
    // Atramedes
    POINT_NONE = 0,
    POINT_CAST_ROARING_BREATH,
    POINT_PREPARE_LAND_INTRO,
    POINT_LAND_INTRO,
    POINT_LIFTOFF,
    POINT_LAND,

    //Reverberating Flame
    POINT_DWARVEN_SHIELD
};

enum Phases
{
    PHASE_INTRO     = 0,
    PHASE_GROUND    = 1,
    PHASE_AIR       = 2
};

enum Data
{
    // Setter
    DATA_LAST_USED_ANCIENT_DWARVEN_SHIELD   = 0,
    DATA_ADD_NOISY_PLAYER                   = 1,
    DATA_REMOVE_NOISY_PLAYER                = 2,
    DATA_LAST_SHIELD_USER                   = 3,


    // Getter
    DATA_IS_IN_AIR                          = 0,
    DATA_HAS_NOISY_PLAYER                   = 1,
    DATA_IS_IN_INTRO_PHASE                  = 2,
    // True only during the scripted intro flight: from ACTION_START_INTRO
    // (the bell summon) until the intro landing (POINT_LAND_INTRO).
    DATA_IS_IN_INTRO_FLIGHT                 = 3
};

enum Misc
{
    AI_ANIM_KIT_ID_OBNOXIOUS_IMP = 1162
};

Position const IntroFlightPosition1             = { 249.432f, -223.616f, 98.6447f };
Position const IntroFlightPosition2             = { 214.531f, -223.918f, 93.4661f };
Position const IntroLandingPosition             = { 214.531f, -223.918f, 74.7668f };
Position const LiftoffPosition                  = { 130.655f, -226.637f, 113.21f  };
Position const LandPosition                     = { 124.575f, -224.797f, 75.4534f };
Position const LordVictorNefariusSummonPosition = { 92.91319f, -223.9931f, 96.8985f, 0.0f };
}

#endif
