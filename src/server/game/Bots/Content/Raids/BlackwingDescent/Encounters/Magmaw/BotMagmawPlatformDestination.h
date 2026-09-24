#ifndef TRINITY_BOT_MAGMAW_PLATFORM_DESTINATION_H
#define TRINITY_BOT_MAGMAW_PLATFORM_DESTINATION_H

#include "Bots/BotActionArbiter.h"
#include "Bots/BotEncounterBlackboard.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawMoveAwayGeometry.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <functional>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace BotEncounter
{
// HEAL-003 (b3-0dbce440-k1): radial parasite escape legs walked six ranged
// bots north off the platform. Where the navmesh ends over the pit the legs
// had no polygon (endpoint mismatch) and two healers stood 2.9 yd below the
// route floor; under the north ledge the nearest polygon was 10 yd above
// (path_control_level_gap). This value layer judges native observations of a
// candidate before it is issued. Native pathing still owns the terrain: the
// observation comes from the native mmap/map queries of the world layer and
// no candidate coordinate is steered, clamped, or teleported here.
struct MagmawPlatformNavigation
{
    static constexpr uint32 BossEntry = 41570;
    // Mirrors AdaptiveMagmawStrategy::SupportStackDistance (static_assert in
    // BotAdaptiveMagmawStrategyHazard.h).
    static constexpr float SupportStackDistance = 8.0f;
    // A native floor this far below the route floor is not the platform: the
    // stranded lip was 2.9 yd below, the lowest platform dip 1.6 yd.
    static constexpr float BelowPlatformTolerance = 2.5f;
    static constexpr float AbovePlatformTolerance = 4.0f;
    static constexpr uint64 HoldRetryMs = 500;
    static constexpr uint32 ReturnFailureThreshold = 3;
    static constexpr uint64 StrandHoldMs = 8000;
    static constexpr float SamePointTolerance = 1.0f;
    static constexpr float GroupPositionRadius = 12.0f;
};

// The ordinary ranged support anchor, derived exactly as the strategy's
// ResolveRangedAnchors().Support: the last living boss observation and the
// first route navigation hint.
inline std::optional<Vector3> ResolveMagmawSupportReturnAnchor(
    Blackboard const& board)
{
    if (board.Route.NavigationHints.empty())
        return std::nullopt;
    ActorSnapshot const* boss = nullptr;
    for (std::vector<ActorSnapshot> const* actors : {
             &board.Hostiles, &board.Summons })
        for (ActorSnapshot const& actor : *actors)
            if (actor.Alive && actor.Entry == MagmawPlatformNavigation::BossEntry)
                boss = &actor;
    Vector3 const& roomSide = board.Route.NavigationHints.front();
    if (!boss || !std::isfinite(roomSide.X) || !std::isfinite(roomSide.Y)
        || !std::isfinite(roomSide.Z) || !std::isfinite(boss->Position.X)
        || !std::isfinite(boss->Position.Y) || !std::isfinite(boss->Position.Z))
        return std::nullopt;
    float const dx = roomSide.X - boss->Position.X;
    float const dy = roomSide.Y - boss->Position.Y;
    float const length = std::sqrt(dx * dx + dy * dy);
    if (length < 1.0f)
        return std::nullopt;
    return Vector3{
        boss->Position.X + dx / length
            * MagmawPlatformNavigation::SupportStackDistance,
        boss->Position.Y + dy / length
            * MagmawPlatformNavigation::SupportStackDistance,
        roomSide.Z };
}

struct MagmawPlatformDestinationObservation
{
    bool Observed = false;
    bool FloorAvailable = false;
    float FloorZ = 0.0f;
    // Complete native path actor -> candidate with a matched endpoint.
    bool OutboundComplete = false;
    // Every native path control stays on the actor's level.
    bool OutboundLevel = false;
    float EndpointZ = 0.0f;
    bool ReturnChecked = false;
    // Complete native path candidate -> ranged support anchor.
    bool ReturnComplete = false;
    bool ReturnLevel = false;
};

enum class MagmawPlatformVerdict : uint8
{
    Admitted,
    Unobserved,
    NoFloor,
    BelowPlatform,
    AbovePlatform,
    OutboundIncomplete,
    OutboundLevelGap,
    ReturnIncomplete,
    ReturnLevelGap
};

inline char const* ToString(MagmawPlatformVerdict verdict)
{
    switch (verdict)
    {
        case MagmawPlatformVerdict::Admitted: return "admitted";
        case MagmawPlatformVerdict::Unobserved: return "unobserved";
        case MagmawPlatformVerdict::NoFloor: return "no_floor";
        case MagmawPlatformVerdict::BelowPlatform: return "below_platform";
        case MagmawPlatformVerdict::AbovePlatform: return "above_platform";
        case MagmawPlatformVerdict::OutboundIncomplete:
            return "outbound_incomplete";
        case MagmawPlatformVerdict::OutboundLevelGap:
            return "outbound_level_gap";
        case MagmawPlatformVerdict::ReturnIncomplete:
            return "return_incomplete";
        case MagmawPlatformVerdict::ReturnLevelGap: return "return_level_gap";
    }
    return "unknown";
}

inline MagmawPlatformVerdict JudgeMagmawPlatformDestination(
    MagmawPlatformDestinationObservation const& observation, float platformZ)
{
    if (!observation.Observed || !std::isfinite(platformZ))
        return MagmawPlatformVerdict::Unobserved;
    if (!observation.FloorAvailable || !std::isfinite(observation.FloorZ))
        return MagmawPlatformVerdict::NoFloor;
    if (observation.FloorZ
        < platformZ - MagmawPlatformNavigation::BelowPlatformTolerance)
        return MagmawPlatformVerdict::BelowPlatform;
    if (observation.FloorZ
        > platformZ + MagmawPlatformNavigation::AbovePlatformTolerance)
        return MagmawPlatformVerdict::AbovePlatform;
    if (!observation.OutboundComplete || !std::isfinite(observation.EndpointZ))
        return MagmawPlatformVerdict::OutboundIncomplete;
    if (!observation.OutboundLevel)
        return MagmawPlatformVerdict::OutboundLevelGap;
    if (observation.ReturnChecked && !observation.ReturnComplete)
        return MagmawPlatformVerdict::ReturnIncomplete;
    if (observation.ReturnChecked && !observation.ReturnLevel)
        return MagmawPlatformVerdict::ReturnLevelGap;
    return MagmawPlatformVerdict::Admitted;
}

// Per-tick native view supplied by the world layer; empty in pure replays.
struct MagmawNativeMovementProbe
{
    std::function<MagmawPlatformDestinationObservation(Vector3 const&,
        std::optional<Vector3> const&)> ObserveDestination;
    std::function<bool(ObjectGuid)> LineOfSightTo;
};

inline float MagmawPlatformDistance2d(Vector3 const& left,
    Vector3 const& right)
{
    return std::hypot(left.X - right.X, left.Y - right.Y);
}

// The unchanged radial escape first, then the same exit radius rotated by
// 30/60/90 degrees. Within one magnitude the side nearer the return anchor
// is tried first. Every candidate keeps the actor Z, as the radial one does.
inline std::array<Vector3, 7> MagmawPlatformEscapeCandidates(
    Vector3 const& actor, float actorFacing, Vector3 const& danger,
    float exitDistance, std::optional<Vector3> const& returnAnchor)
{
    std::array<Vector3, 7> candidates{};
    Vector3 const primary = MagmawMoveAwayDestination(actor, actorFacing,
        danger, exitDistance);
    candidates[0] = primary;
    float const baseX = exitDistance > 0.0f
        ? (primary.X - danger.X) / exitDistance : 1.0f;
    float const baseY = exitDistance > 0.0f
        ? (primary.Y - danger.Y) / exitDistance : 0.0f;
    auto rotated = [&](float angle)
    {
        float const c = std::cos(angle);
        float const s = std::sin(angle);
        return Vector3{ danger.X + (baseX * c - baseY * s) * exitDistance,
            danger.Y + (baseX * s + baseY * c) * exitDistance, actor.Z };
    };
    constexpr float Step = 3.14159265f / 6.0f;
    for (size_t magnitude = 1; magnitude <= 3; ++magnitude)
    {
        Vector3 first = rotated(Step * float(magnitude));
        Vector3 second = rotated(-Step * float(magnitude));
        if (returnAnchor && MagmawPlatformDistance2d(second, *returnAnchor)
                < MagmawPlatformDistance2d(first, *returnAnchor))
            std::swap(first, second);
        candidates[magnitude * 2 - 1] = first;
        candidates[magnitude * 2] = second;
    }
    return candidates;
}

struct MagmawPlatformSelection
{
    std::optional<Vector3> Destination;
    uint32 Probed = 0;
    uint32 Rejected = 0;
    MagmawPlatformVerdict LastRejection = MagmawPlatformVerdict::Admitted;
};

// First admitted candidate in caller order. The admitted destination keeps
// the requested X/Y and takes the native path endpoint Z.
template <typename Candidates>
MagmawPlatformSelection SelectMagmawPlatformDestination(
    MagmawNativeMovementProbe const& probe, Candidates const& candidates,
    std::optional<Vector3> const& returnAnchor, float platformZ,
    std::vector<Vector3> const& excluded = {})
{
    MagmawPlatformSelection selection;
    if (!probe.ObserveDestination)
        return selection;
    for (Vector3 const& candidate : candidates)
    {
        if (std::any_of(excluded.begin(), excluded.end(),
                [&candidate](Vector3 const& point)
                {
                    return MagmawPlatformDistance2d(candidate, point)
                        <= MagmawPlatformNavigation::SamePointTolerance;
                }))
            continue;
        MagmawPlatformDestinationObservation const observation =
            probe.ObserveDestination(candidate, returnAnchor);
        MagmawPlatformVerdict const verdict =
            JudgeMagmawPlatformDestination(observation, platformZ);
        ++selection.Probed;
        if (verdict == MagmawPlatformVerdict::Admitted)
        {
            selection.Destination = Vector3{ candidate.X, candidate.Y,
                observation.EndpointZ };
            return selection;
        }
        ++selection.Rejected;
        selection.LastRejection = verdict;
    }
    return selection;
}

// Consecutive native rejections of the same formation return destination.
// After ReturnFailureThreshold rejections the strategy stops retrying it and
// uses the nearest reachable ranged anchor / group position instead; the
// original is retried once StrandHoldMs passes without a new rejection.
struct MagmawStrandRecoveryState
{
    bool Tracking = false;
    Vector3 Original;
    uint32 ConsecutiveFailures = 0;
    uint64 FirstFailureAtMs = 0;
    uint64 LastFailureAtMs = 0;
    std::string LastReason;
    bool FallbackActive = false;
    Vector3 Fallback;
    uint32 FallbackFailures = 0;
    uint64 FallbackSelectedAtMs = 0;
    uint64 NextProbeAtMs = 0;
    uint64 FallbackCount = 0;
    uint64 HoldCount = 0;
    std::vector<Vector3> Excluded;

    static bool IsReturnPathRejection(std::string_view reason)
    {
        return reason.rfind("route_destination_", 0) == 0;
    }

    static bool Near(Vector3 const& left, Vector3 const& right)
    {
        return MagmawPlatformDistance2d(left, right)
            <= MagmawPlatformNavigation::SamePointTolerance;
    }

    bool Stranded(Vector3 const& original, uint64 nowMs) const
    {
        return Tracking && Near(Original, original)
            && ConsecutiveFailures
                >= MagmawPlatformNavigation::ReturnFailureThreshold
            && nowMs < LastFailureAtMs + MagmawPlatformNavigation::StrandHoldMs;
    }

    void ObserveReturnOutcome(Vector3 const& destination,
        BotActionArbitration::Disposition result, std::string_view reason,
        uint64 observedAtMs)
    {
        bool const committed =
            result == BotActionArbitration::Disposition::Committed;
        bool const rejected = !committed
            && result != BotActionArbitration::Disposition::NotApplicable
            && IsReturnPathRejection(reason);
        if (FallbackActive && Near(destination, Fallback))
        {
            if (committed)
                FallbackFailures = 0;
            else if (rejected && ++FallbackFailures
                    >= MagmawPlatformNavigation::ReturnFailureThreshold)
            {
                Excluded.push_back(Fallback);
                FallbackActive = false;
                FallbackFailures = 0;
            }
            return;
        }
        if (!Tracking || !Near(destination, Original) || committed)
            Restart(destination);
        if (rejected)
        {
            if (!ConsecutiveFailures++)
                FirstFailureAtMs = observedAtMs;
            LastFailureAtMs = observedAtMs;
            LastReason = std::string(reason);
        }
    }

private:
    // A new destination or a committed return closes the strand episode;
    // only the lifetime diagnostic counters survive.
    void Restart(Vector3 const& destination)
    {
        uint64 const fallbackCount = FallbackCount;
        uint64 const holdCount = HoldCount;
        *this = {};
        Tracking = true;
        Original = destination;
        FallbackCount = fallbackCount;
        HoldCount = holdCount;
    }
};
}

#endif
