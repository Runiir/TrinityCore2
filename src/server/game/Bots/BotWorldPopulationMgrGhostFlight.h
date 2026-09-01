#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_GHOST_FLIGHT_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_GHOST_FLIGHT_H

#include <cstdint>

namespace BotWorldGhostFlight
{
constexpr std::uint32_t BurningSteppesMapId = 0;
constexpr std::uint32_t BurningSteppesZoneId = 46;

// A corpse-run ghost may use the same flight-capable movement primitive as a
// normal player only for the exact outdoor leg from the native raid corpse to
// its entrance.  The caller supplies all runtime identity checks; this
// predicate deliberately has no world or encounter side effects.
struct Eligibility
{
    std::uint32_t MapId = 0;
    std::uint32_t ZoneId = 0;
    bool DeadGhost = false;
    bool InWorld = false;
    bool NativeRecoveryEpisode = false;
    bool NativeCorpseAuthority = false;
    bool CrossMapRecovery = false;
    bool Outdoors = false;
    bool InstanceMap = false;
    bool OnTransport = false;
    bool InFlight = false;
};

constexpr bool IsEligible(Eligibility const& value)
{
    return value.MapId == BurningSteppesMapId
        && value.ZoneId == BurningSteppesZoneId
        && value.DeadGhost
        && value.InWorld
        && value.NativeRecoveryEpisode
        && value.NativeCorpseAuthority
        && value.CrossMapRecovery
        && value.Outdoors
        && !value.InstanceMap
        && !value.OnTransport
        && !value.InFlight;
}

// A retained ground generator predates flight authorization when eligibility
// rises during an already-running cross-map corpse recovery.  Replan that
// exact path once so the existing native aerial executor can consume the same
// destination.  NativeRecoveryGhostFlightEnabled becomes true on the same
// tick, making this a rising-edge predicate rather than a per-tick retry.
struct RetainedPath
{
    bool Active = false;
    bool EntranceRequired = false;
    bool NativeLongPath = false;
    bool TargetIsEmpty = false;
    bool RecoveryOwner = false;
    bool ScopeMatches = false;
};

constexpr bool ShouldReplanOnEligibilityRise(bool wasFlightEnabled,
    bool flightEligible, RetainedPath const& path)
{
    return !wasFlightEnabled
        && flightEligible
        && path.Active
        && path.EntranceRequired
        && path.NativeLongPath
        && path.TargetIsEmpty
        && path.RecoveryOwner
        && path.ScopeMatches;
}
}

#endif
