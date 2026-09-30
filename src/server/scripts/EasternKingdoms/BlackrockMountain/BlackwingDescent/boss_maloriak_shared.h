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
#include "Duration.h"
#include <limits>

class Creature;

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
    SPELL_BERSERK                       = 64238,

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
    SPELL_REND                          = 78034,

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

// 10N opening before the first vial (WCL, 19 kills; ledger
// pre_vial_opening_10N). Maloriak begins an Arcane Storm 10.9-14.9 s after
// engage (the observed begin times below are drawn uniformly). His next action
// comes about 3.2 s after that begin (the "slot"): slots at 14.1-16.4 s were
// Release Aberrations or Remedy (4 and 4 kills, never earlier than 15.7 s);
// slots at 17.4-18.1 s were the first vial throw (7 of 11), Remedy (3) or
// Release (1). No slot fell between, so the cut is placed at 17 s. The throw
// follows 1.2-1.7 s after a Remedy and 1.6-1.7 s after a Release begins. The
// script decides 1.3 s before the slot, because the throw comes 1.3 s after
// EVENT_FACE_TO_CAULDRON.
constexpr uint32 PRE_VIAL_STORM_BEGIN_MS[] = { 10900, 11117, 11195, 12548, 12600, 12614, 13100,
    13206, 14193, 14300, 14357, 14400, 14400, 14485, 14551, 14565, 14773, 14800, 14900 };
constexpr uint32 PRE_VIAL_SLOT_AFTER_STORM_MS = 3200;
constexpr uint32 PRE_VIAL_FACE_LEAD_MS = 1300;
constexpr uint32 PRE_VIAL_VIAL_DUE_MS = 17000;
constexpr uint32 PRE_VIAL_EARLIEST_CAST_MS = 15700;
constexpr uint32 PRE_VIAL_FACE_AFTER_REMEDY_MS = 300;
constexpr uint32 PRE_VIAL_FACE_AFTER_RELEASE_MS = 400;

enum class PreVialAction : uint8
{
    Vial,
    ReleaseAberrations,
    Remedy
};

// `roll` is uniform in [0, 7].
constexpr PreVialAction ChoosePreVialAction(uint32 slotMs, uint32 roll)
{
    if (slotMs < PRE_VIAL_VIAL_DUE_MS)
        return roll < 4 ? PreVialAction::ReleaseAberrations : PreVialAction::Remedy;
    if (roll == 0)
        return PreVialAction::ReleaseAberrations;
    return roll < 3 ? PreVialAction::Remedy : PreVialAction::Vial;
}

// 10N Green (Slime Imbued) casts, milliseconds after the imbue, in the time the
// script fires at: EVENT_ARCANE_STORM fires when the 0.5 s Arcane Storm cast
// begins, EVENT_REMEDY when the instant Remedy is cast (Spell.dbc cast times
// 500 and 0 ms), so every observed value is compared as a begin. Ledger
// green_phase_10N / target_era_corroboration_10N: before the 2025-02-20 target
// the storm began 3.6-4.4 s and Remedy was cast 7.3-10.9 s after the imbue
// (six Green phases). The five 10N kills after it
// (wcl_maloriak_10n_post_cutoff_20260930; official_hotfix_audit_20250113_20250220
// found no change) log Cast rows only: the storm Cast 3.66-6.57 s, which is a
// begin at 3.13-6.10 s (minus the 0.474-0.531 s begin-to-cast offset of 31
// round-2 Begin/Cast pairs), and one Remedy Cast at 14.15 s (instant, so the
// same as its fire time). 10N draws both uniformly over the combined ranges,
// stated to 0.1 s.
// EVENT_RELEASE_ABERRATIONS fires when the 1.5 s Release cast begins, so its
// range is the exact first Release begin after Slime Imbued over both periods
// (ledger green_release_begins_10N, milliseconds after the imbue): Begin Cast
// rows 6.415 (canceled, 7PT6hQ3wBqXmdtcH 49), 7.299, 7.666, 8.888 (canceled in
// the report), 9.312 (canceled) and 10.505 s, plus the Cast rows 10.405 and
// 11.201 s of H7NA9PFKgfkCQntm 12 and V2dvWRwtBmA6rk1H 30, which are begins at
// 8.905 and 9.701 s after the 1.5 s cast. The minimum and maximum are Begin
// Cast rows, so they are used unrounded. The range overlaps the Remedy range:
// either order is observed (Remedy first in NYcJZtHd6baDC41p 28, Release first
// in cDQCyb4B71Wj9dV8 15) and a Remedy due during the Release cast waits for
// it (UpdateAI does not execute events while Maloriak casts). The other modes
// keep their fixed 5 / 7.5 / 9 s.
constexpr uint32 GREEN_STORM_10N_MIN_MS = 3100;
constexpr uint32 GREEN_STORM_10N_MAX_MS = 6100;
constexpr uint32 GREEN_REMEDY_10N_MIN_MS = 7300;
constexpr uint32 GREEN_REMEDY_10N_MAX_MS = 14200;
constexpr uint32 GREEN_RELEASE_10N_MIN_MS = 6415;
constexpr uint32 GREEN_RELEASE_10N_MAX_MS = 10505;
// Neither Remedy nor Release is drawn before the storm, so the observed order
// of the storm holds. Release and Remedy are deliberately not ordered.
static_assert(GREEN_STORM_10N_MAX_MS < GREEN_REMEDY_10N_MIN_MS, "the Green Remedy follows the Green storm");
static_assert(GREEN_STORM_10N_MAX_MS < GREEN_RELEASE_10N_MIN_MS, "the Green Release follows the Green storm");

// Schedules the Green-phase storm, Remedy and Release on `events` (an
// EventMap). Off 10N nothing is drawn: the storm at 5 s, Remedy at 7.5 s and
// Release at 9 s are fixed, exactly as before the 10N ranges.
template <typename EventMapT>
void ScheduleGreenPhaseCasts(EventMapT& events, bool tenNormal,
    uint32 stormEvent, uint32 remedyEvent, uint32 releaseEvent, uint8 phase)
{
    if (tenNormal)
    {
        events.ScheduleEvent(stormEvent, Milliseconds(GREEN_STORM_10N_MIN_MS),
            Milliseconds(GREEN_STORM_10N_MAX_MS), 0, phase);
        events.ScheduleEvent(remedyEvent, Milliseconds(GREEN_REMEDY_10N_MIN_MS),
            Milliseconds(GREEN_REMEDY_10N_MAX_MS), 0, phase);
        events.ScheduleEvent(releaseEvent, Milliseconds(GREEN_RELEASE_10N_MIN_MS),
            Milliseconds(GREEN_RELEASE_10N_MAX_MS), 0, phase);
    }
    else
    {
        events.ScheduleEvent(stormEvent, 5s, 0, phase);
        events.ScheduleEvent(remedyEvent, 7s + 500ms, 0, phase);
        events.ScheduleEvent(releaseEvent, 9s, 0, phase);
    }
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

namespace BlackwingDescent::Maloriak
{
// Seconds after Debilitating Slime until a surviving experiment casts Growth
// Catalyst again (StripGrowthCatalystForSlime).
// 10N WCL cDQCyb4B71Wj9dV8 fight 15 (a 7:06 kill): Berserk 64238 at 7:02.6 of
// the fight; the historical guide gives 7 min on normal (ledger enrage_10N).
constexpr uint32 BERSERK_10N_MS = 7 * 60 * 1000;

constexpr uint32 GROWTH_CATALYST_SLIME_RECAST_MS = 5200;

// 10N Flash Freeze prefers players beyond this range of Maloriak (the reach of
// his 10-yd Biting Chill, which only ever took melee-range players).
constexpr float FLASH_FREEZE_MIN_RANGE_10N = 10.0f;

// Debilitating Slime strips Growth Catalyst from every living Aberration and
// Prime Subject near `source` (boss_maloriak_spells.cpp).
void StripGrowthCatalystForSlime(Creature* source);
}

void AddSC_boss_maloriak_minions();
void AddSC_boss_maloriak_spells();

#endif
