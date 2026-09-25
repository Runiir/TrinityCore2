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

#ifndef BOSS_CHIMAERON_LOGIC_H
#define BOSS_CHIMAERON_LOGIC_H

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <limits>

// Pure encounter rules used by boss_chimaeron.cpp. They take plain facts so
// unit tests can exercise them without a map, creatures or spells.
namespace BlackwingDescent::Chimaeron::Logic
{
enum class SlimeCandidate : std::uint8_t
{
    Excluded,       // the boss's current victim (repository behavior)
    BreakAffected,  // only fills a shortfall (Patch 4.0.6 hotfix)
    Eligible
};

// Patch 4.0.6 hotfix (Blizzard, 2011-02-09): "Chimaeron no longer casts
// Caustic Slime on targets who are affected by Break. Chimaeron now casts
// Caustic Slime on a tank target if there are not enough players present
// without Break."
constexpr SlimeCandidate ClassifyCausticSlimeCandidate(bool currentVictim, bool breakAffected)
{
    if (currentVictim)
        return SlimeCandidate::Excluded;
    return breakAffected ? SlimeCandidate::BreakAffected : SlimeCandidate::Eligible;
}

constexpr std::size_t CausticSlimeTargetCount(bool is25ManRaid)
{
    return is25ManRaid ? 4 : 2;
}

struct CausticSlimePick
{
    std::size_t FromEligible = 0;
    std::size_t FromBreakAffected = 0;
};

// How many targets each pool supplies: eligible players first, then
// Break-affected players for any shortfall.
constexpr CausticSlimePick PlanCausticSlimeTargets(std::size_t eligible,
    std::size_t breakAffected, std::size_t wanted)
{
    std::size_t const fromEligible = std::min(eligible, wanted);
    return { fromEligible, std::min(breakAffected, wanted - fromEligible) };
}

constexpr std::uint32_t NoMassacreTime = std::numeric_limits<std::uint32_t>::max();

// GetTimeUntilEncounterMechanic(Massacre): none outside phase one, 0 while
// the Massacre is being cast, otherwise the remaining event time. EventMap
// subtracts unsigned values, so an event held past its due time (the boss was
// casting) wraps to a value above the repeat interval: it is due now.
constexpr std::uint32_t MassacreRemainingMs(bool phaseOne, bool castingMassacre,
    std::uint32_t eventRemainingMs, std::uint32_t repeatMs)
{
    if (!phaseOne)
        return NoMassacreTime;
    if (castingMassacre)
        return 0;
    if (eventRemainingMs == NoMassacreTime)
        return NoMassacreTime;
    return eventRemainingMs > repeatMs ? 0 : eventRemainingMs;
}
}

#endif
