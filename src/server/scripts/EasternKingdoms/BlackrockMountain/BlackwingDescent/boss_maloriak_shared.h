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

#ifndef DEF_BOSS_MALORIAK_SHARED_H
#define DEF_BOSS_MALORIAK_SHARED_H

#include "Define.h"
#include <limits>

// Identifiers shared by the Maloriak creature AIs (boss_maloriak.cpp) and
// its spell scripts (boss_maloriak_spells.cpp).
namespace BlackwingDescent::Maloriak
{
enum Spells
{
    // Maloriak
    SPELL_ARCANE_STORM                  = 77896,
    SPELL_REMEDY                        = 77912,
    SPELL_THROW_RED_BOTTLE              = 77925,
    SPELL_THROW_BLUE_BOTTLE             = 77932,
    SPELL_THROW_GREEN_BOTTLE            = 77937,
    SPELL_DRINK_RED_BOTTLE              = 88699,
    SPELL_DRINK_BLUE_BOTTLE             = 88700,
    SPELL_DRINK_BLACK_BOTTLE            = 92828,
    SPELL_FIRE_IMBUED                   = 78896,
    SPELL_FROST_IMBUED                  = 78895,
    SPELL_SHADOW_IMBUED                 = 92716,
    SPELL_SLIME_IMBUED                  = 92917,
    SPELL_THROW_RED_BOTTLE_TRIGGERED    = 77928,
    SPELL_THROW_BLUE_BOTTLE_TRIGGERED   = 77934,
    SPELL_THROW_GREEN_BOTTLE_TRIGGERED  = 77938,
    SPELL_RELEASE_ABERRATIONS           = 77569,
    SPELL_RELEASE_ALL_MINIONS           = 77991,
    SPELL_SCORCHING_BLAST               = 77679,
    SPELL_BITING_CHILL                  = 77760,
    SPELL_FLASH_FREEZE_TARGETING        = 97693,
    SPELL_DRINK_ALL_BOTTLES             = 95662,
    SPELL_UNSTABLE_MIX                  = 95663,
    SPELL_MAGMA_JETS_SCRIPT_EFFECT      = 93022,
    SPELL_MAGMA_JETS_SUMMON             = 78194,
    SPELL_ACID_NOVA                     = 78225,
    SPELL_ABSOLUTE_ZERO                 = 78223,
    SPELL_ENGULFING_DARKNESS            = 92754,
    SPELL_VILE_SWILL                    = 92720,
    SPELL_VILE_SWILL_SUMMON             = 92724,

    // Cauldron Trigger
    SPELL_DEBILITATING_SLIME_CAST       = 77602,
    SPELL_DEBILITATING_SLIME_KNOCKBACK  = 77948,
    SPELL_DEBILITATING_SLIME_DEBUFF     = 77615,

    // Flash Freeze
    SPELL_FLASH_FREEZE_VISUAL           = 77712,
    SPELL_SHATTER                       = 77715,

    // Experiments
    SPELL_DROWNED_STATE                 = 77564,
    SPELL_GROWTH_CATALYST               = 77987,

    // Magma Jet
    SPELL_MAGMA_JETS_SUMMON_FIRE        = 78094,
    SPELL_MAGMA_JETS_ERUPTION           = 78095,

    // Absolute Zero
    SPELL_ABSOLUTE_ZERO_TRANSFORM       = 78201,
    SPELL_ABSOLUTE_ZERO_EXPLOSION       = 78208,

    // Lord Victor Nefarius
    SPELL_TELEPORT_VISUAL_ONLY          = 41232,
    SPELL_THROW_BLACK_BOTTLE            = 92831,
    SPELL_THROW_BLACK_BOTTLE_TRIGGERED  = 92837,
    SPELL_MASTER_ADVENTURER_AWARD       = 89798,

    // Vile Swill
    SPELL_DARK_SLUDGE                   = 92929,

    // Player
    SPELL_FLASH_FREEZE_SUMMON           = 77711,
    SPELL_FLASH_FREEZE_DUMMY            = 77716,
    SPELL_FLASH_FREEZE_STUN_NORMAL      = 77699
};

enum Actions
{
    // Maloriak
    ACTION_SCHEDULE_EVENTS_FOR_PHASE    = 1,

    // Experiments
    ACTION_RELEASE_EXPERIMENT           = 1,

    // Lord Victor Nefarius
    ACTION_THROW_BLACK_BOTTLE           = 1,
    ACTION_MALORIAK_DEAD                = 2
};

enum GameObjectCustomAnim
{
    CUSTOM_ANIM_RED_CAULDRON    = 0,
    CUSTOM_ANIM_BLUE_CAULDRON   = 1,
    CUSTOM_ANIM_GREEN_CAULDRON  = 2,
    CUSTOM_ANIM_BLACK_CAULDRON  = 3
};

enum Misc
{
    SUMMON_GROUP_EXPERIMENTS            = 0,
    SPAWN_GROUP_GROWTH_CHAMBERS         = 401,
    AI_ANIM_KIT_ID_LORD_VICTOR_NEFARIUS = 1173,
    TITLE_ADVENTURER_AWARD              = 188
};

enum Vials : uint8
{
    VIAL_RED    = 0,
    VIAL_BLUE   = 1,
    VIAL_GREEN  = 2,
    VIAL_BLACK  = 3
};

// Deterministic part of the native vial order. EVENT_FACE_TO_CAULDRON and
// the read-only mechanic timer both use this helper, so the published "next
// vial" can never diverge from the executed one. `current` is the vial drunk
// last; the cycle starts from VIAL_GREEN (Reset), so the first normal vial is
// the random Red/Blue branch and the first heroic vial is Black. Returns
// VIAL_BLACK + 1 when the choice is the random Red/Blue branch.
constexpr uint8 VIAL_RANDOM_RED_OR_BLUE = VIAL_BLACK + 1;

constexpr uint8 SelectNextVial(uint8 current, uint8 usedVials,
    uint8 vialsPerCycle, bool heroic)
{
    if (!usedVials && heroic)
        return VIAL_BLACK;
    if ((current == VIAL_BLACK || current == VIAL_GREEN)
        && usedVials < vialsPerCycle)
        return VIAL_RANDOM_RED_OR_BLUE;
    if (usedVials == vialsPerCycle)
        return VIAL_GREEN;
    return current == VIAL_BLUE ? VIAL_RED : VIAL_BLUE;
}

constexpr uint8 AdvanceUsedVials(uint8 usedVials, uint8 vialsPerCycle)
{
    return usedVials < vialsPerCycle ? usedVials + 1 : 0;
}

// Read-only EventMap query behind GetTimeUntilEncounterMechanic: the
// remaining time of the next scheduled eventId, 0 when it is due or overdue
// (UpdateAI holds due events while Maloriak casts), and uint32 max when it
// is not scheduled. GetNextEventTime returns the absolute due time, or 0.
template <typename EventMapT>
uint32 TimeUntilScheduledEvent(EventMapT const& events, uint32 eventId)
{
    uint32 const at = events.GetNextEventTime(eventId);
    if (!at)
        return std::numeric_limits<uint32>::max();
    return at <= events.GetTimer() ? 0 : at - events.GetTimer();
}
}

void AddSC_boss_maloriak_spells();

#endif
