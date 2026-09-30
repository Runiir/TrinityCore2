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

// The next three rules (knockout chance, Caustic Slime repeat, Feud skipping
// Break and Double Attack) were resolved from WCL for 10N (Normal 10 player)
// only. `tenNormal` selects them; 25N, 10H and 25H keep the rules the script
// had before the round-3 research (base c8e8bfe85b) until they have evidence.

// Bile-O-Tron knockout after a Massacre (Systems Failure, then Feud). Patch
// 4.1.0: "more resistant to being knocked offline many times in rapid
// succession". `massacresInCycle` counts the completed Massacres since the
// pull or the last knockout, this one included; the count restarts after each
// knockout in every mode.
//
// 10N (DBM: never after the first Massacre, after the 2nd or 3rd, the 3rd
// always; WCL 10N census, Chimaeron dossier, 2026-09-30: 0 of 30 on the first
// Massacre of a cycle, 11 of 24 on the second, 8 of 8 on the third): 0/50/100%.
constexpr int KnockoutChanceSecondMassacrePct = 50;

// Other modes: the previous roll, 40% at the first Massacre and 20 more points
// for every miss, 40/60/80/100%.
constexpr int PreviousKnockoutChanceFirstMassacrePct = 40;
constexpr int PreviousKnockoutChanceStepPct = 20;

constexpr int KnockoutChancePct(bool tenNormal, unsigned massacresInCycle)
{
    if (tenNormal)
    {
        if (massacresInCycle <= 1)
            return 0;
        return massacresInCycle == 2 ? KnockoutChanceSecondMassacrePct : 100;
    }

    if (massacresInCycle <= 1)
        return PreviousKnockoutChanceFirstMassacrePct;
    if (massacresInCycle >= 4)
        return 100;
    return PreviousKnockoutChanceFirstMassacrePct
        + PreviousKnockoutChanceStepPct * static_cast<int>(massacresInCycle - 1);
}

// Caustic Slime repeat. 10N WCL (MxFq7TRbvnjGY1hJ-27, vnwd3D61GcaYfHrg-29,
// 9DrAgFWwQj4dV2Tq-53; ten Massacre cycles): exactly two volleys per cycle,
// 5.8-6.1 s apart, then about 24 s to the next pair. A 5 s repeat would add a
// third volley at +29 s after the Massacre cast start. Other modes keep 5 s.
constexpr std::uint32_t CausticSlimeRepeatMs(bool tenNormal)
{
    return tenNormal ? 6000u : 5000u;
}

// Feud pacifies his melee; Break and Double Attack ride on it. On 10N they are
// skipped while Feud is up (WCL 10N: no Double Attack during Feud; BigWigs
// stops the normal-mode Break bar on Systems Failure). Pacify does not block
// these spells (no prevention type), so the script skips them itself. Other
// modes keep casting them during Feud. The timers keep running either way.
constexpr bool SkipsBreakAndDoubleAttack(bool tenNormal, bool inFeud)
{
    return tenNormal && inFeud;
}

// Mortality (20%) runs no Massacre cycle, so Feud has nothing to skip there: a
// Double Attack that comes due while Feud is still up on 10N is held and cast
// when Feud expires (ACTION_END_FEUD), not consumed as a completed repeat. The
// script schedules the opening Mortality Double Attack 1 ms after the
// transition; consuming it inside Feud would leave the first Mortality attack
// a whole 15 s repeat later, 10 s after Feud. Phase one keeps the skip, and the
// other modes never skip or hold.
constexpr bool HoldsDoubleAttackForFeudEnd(bool tenNormal, bool inFeud, bool mortality)
{
    return SkipsBreakAndDoubleAttack(tenNormal, inFeud) && mortality;
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
