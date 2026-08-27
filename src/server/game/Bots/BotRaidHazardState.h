#ifndef TRINITYCORE_BOT_RAID_HAZARD_STATE_H
#define TRINITYCORE_BOT_RAID_HAZARD_STATE_H

#include <cstdint>

namespace BotRaidHazard
{
// A summoned cast marker can outlive the spell that makes its location
// dangerous. Keep the native cast and aura/effect window authoritative while
// failing closed when the summon lifetime cannot be reconstructed.
inline bool TimedMarkerDangerActive(uint32_t remainingLifetimeMs,
    uint32_t totalLifetimeMs, uint32_t castTimeMs, uint32_t effectDurationMs,
    uint32_t safetyBufferMs = 1000)
{
    if (!totalLifetimeMs || remainingLifetimeMs > totalLifetimeMs)
        return true;

    uint64_t const elapsedMs = uint64_t(totalLifetimeMs) - remainingLifetimeMs;
    uint64_t const dangerWindowMs = uint64_t(castTimeMs)
        + effectDurationMs + safetyBufferMs;
    return elapsedMs <= dangerWindowMs;
}

// A failed bearing must not repeat forever merely because two roster GUIDs
// share the same spread bucket. Rotate through the same five deterministic
// bearings that the exact cohort already uses; each retry still receives the
// unchanged native path and union-hazard checks.
inline uint8_t RotatedBearingBucket(uint32_t guidCounter, uint8_t attempt)
{
    return uint8_t((guidCounter % 5u + attempt % 5u) % 5u);
}

// A route with an exact native hazard marker must not also turn the owning
// creature's cast telegraph into a generic raid-wide dodge. For example, the
// Chainwielder casts Overhead Smash, then entry 42690 marks the actual
// 20-yard danger. Moving for both interrupts every ranged cast and makes the
// whole raid run on each telegraph. Keep generic detection for a different
// enrolled pack member so a secondary, undeclared ground cast still receives
// the normal fail-closed response.
inline bool ShouldInspectGenericCastCandidate(
    bool currentNodeHasConfiguredHazard, uint32_t candidateEntry,
    uint32_t routeSourceEntry, bool candidateIsConfiguredHazardSource,
    bool packGenerationCurrent, bool enrolledPackMember,
    bool deadPackMember, bool transitionedPackMember, bool combatLinked)
{
    if (!currentNodeHasConfiguredHazard)
        return true;

    if (!candidateEntry || candidateIsConfiguredHazardSource
        || (routeSourceEntry && candidateEntry == routeSourceEntry)
        || !packGenerationCurrent || !enrolledPackMember
        || deadPackMember || transitionedPackMember)
        return false;

    return combatLinked;
}
}

#endif
