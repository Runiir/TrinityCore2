#ifndef TRINITY_BOT_MAGMAW_CRASH_SIDE_MOVEMENT_H
#define TRINITY_BOT_MAGMAW_CRASH_SIDE_MOVEMENT_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawEventMovementTransition.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <limits>
#include <optional>
#include <string>
#include <vector>

namespace BotEncounter
{
// Native Massive Crash (instance_blackwing_descent.cpp,
// DATA_PREPARE_MASSIVE_CRASH_AND_GET_TARGET_GUID) picks one of two crash
// dummies at random, lights every Room Stalker inside that dummy's 45-degree
// arc with Light Show for 7 s, and 6 s later the dummy damages that cone.  The
// whole lit set is one native fact per crash and is identical for every bot,
// so a footprint built from all of it cannot flip while a bot moves.  The lit
// stalker nearest a bot can: at the ranged support point it was 29.88 against
// 29.84 yd from the two side anchors, which is the retained zig-zag.
//
// Retained evidence (kills base-0891a99, bundle1, bundle2 and fid16, 108 native
// Massive Crash hits): every hit lay at most 4.2 yd outside the convex hull of
// the lit stalkers, while the support-side evade destinations lie 7.2 and
// 12.8 yd outside it.  A point within this margin of the hull is covered.
constexpr float MagmawCrashCoverageMargin = 5.5f;
constexpr std::size_t MagmawCrashCoverageMinimumStalkers = 3;

struct MagmawCrashFootprint
{
    bool Valid = false;
    // Lowest raw GUID of the lit set: a stable identity for one crash.
    ObjectGuid Identity;
    Vector3 Centroid;
    uint32 LitCount = 0;
    // Counter-clockwise convex hull of the lit stalkers. Empty when fewer
    // than three non-collinear stalkers are visible; callers then keep the
    // side-anchor rule without a coverage model.
    std::vector<Vector3> Hull;

    bool HasCoverage() const
    {
        return Hull.size() >= MagmawCrashCoverageMinimumStalkers;
    }
};

inline std::vector<Vector3> MagmawCrashCoverageHull(std::vector<Vector3> points)
{
    std::sort(points.begin(), points.end(),
        [](Vector3 const& left, Vector3 const& right)
        {
            return left.X < right.X || (left.X == right.X && left.Y < right.Y);
        });
    points.erase(std::unique(points.begin(), points.end(),
        [](Vector3 const& left, Vector3 const& right)
        {
            return left.X == right.X && left.Y == right.Y;
        }), points.end());
    if (points.size() < MagmawCrashCoverageMinimumStalkers)
        return {};
    auto cross = [](Vector3 const& origin, Vector3 const& first,
        Vector3 const& second)
    {
        return (first.X - origin.X) * (second.Y - origin.Y)
            - (first.Y - origin.Y) * (second.X - origin.X);
    };
    std::vector<Vector3> hull(points.size() * 2);
    std::size_t count = 0;
    for (Vector3 const& point : points)
    {
        while (count >= 2 && cross(hull[count - 2], hull[count - 1], point) <= 0.0f)
            --count;
        hull[count++] = point;
    }
    std::size_t const lowerCount = count + 1;
    for (std::size_t index = points.size() - 1; index > 0; --index)
    {
        Vector3 const& point = points[index - 1];
        while (count >= lowerCount
            && cross(hull[count - 2], hull[count - 1], point) <= 0.0f)
            --count;
        hull[count++] = point;
    }
    hull.resize(count > 0 ? count - 1 : 0);
    if (hull.size() < MagmawCrashCoverageMinimumStalkers)
        return {};
    return hull;
}

// The caller supplies only alive Room Stalkers that carry native Light Show.
inline MagmawCrashFootprint BuildMagmawCrashFootprint(
    std::vector<ActorSnapshot const*> const& lit)
{
    MagmawCrashFootprint footprint;
    // Accumulate in GUID order so the footprint is bit-identical however the
    // blackboard happened to enumerate the same lit set on a given tick.
    std::vector<ActorSnapshot const*> ordered;
    for (ActorSnapshot const* stalker : lit)
        if (stalker && std::isfinite(stalker->Position.X)
            && std::isfinite(stalker->Position.Y)
            && std::isfinite(stalker->Position.Z))
            ordered.push_back(stalker);
    std::sort(ordered.begin(), ordered.end(),
        [](ActorSnapshot const* left, ActorSnapshot const* right)
        {
            return left->Guid.GetRawValue() < right->Guid.GetRawValue();
        });
    std::vector<Vector3> points;
    float sumX = 0.0f;
    float sumY = 0.0f;
    float sumZ = 0.0f;
    for (ActorSnapshot const* stalker : ordered)
    {
        if (footprint.Identity.IsEmpty())
            footprint.Identity = stalker->Guid;
        sumX += stalker->Position.X;
        sumY += stalker->Position.Y;
        sumZ += stalker->Position.Z;
        points.push_back(stalker->Position);
    }
    if (points.empty())
        return {};
    float const count = float(points.size());
    footprint.Valid = true;
    footprint.LitCount = uint32(points.size());
    footprint.Centroid = { sumX / count, sumY / count, sumZ / count };
    footprint.Hull = MagmawCrashCoverageHull(std::move(points));
    return footprint;
}

// Negative inside the hull, positive outside (horizontal yards).
inline float MagmawCrashCoverageSignedDistance(
    std::vector<Vector3> const& hull, Vector3 const& point)
{
    if (hull.size() < MagmawCrashCoverageMinimumStalkers)
        return std::numeric_limits<float>::infinity();
    bool inside = true;
    float nearest = std::numeric_limits<float>::infinity();
    for (std::size_t index = 0; index < hull.size(); ++index)
    {
        Vector3 const& start = hull[index];
        Vector3 const& end = hull[(index + 1) % hull.size()];
        float const edgeX = end.X - start.X;
        float const edgeY = end.Y - start.Y;
        float const offsetX = point.X - start.X;
        float const offsetY = point.Y - start.Y;
        if (edgeX * offsetY - edgeY * offsetX < 0.0f)
            inside = false;
        float const lengthSquared = edgeX * edgeX + edgeY * edgeY;
        float const t = lengthSquared > 0.0f
            ? std::clamp((offsetX * edgeX + offsetY * edgeY) / lengthSquared,
                0.0f, 1.0f)
            : 0.0f;
        nearest = std::min(nearest, std::hypot(offsetX - t * edgeX,
            offsetY - t * edgeY));
    }
    return inside ? -nearest : nearest;
}

inline bool MagmawCrashCovers(MagmawCrashFootprint const& footprint,
    Vector3 const& point, float margin = MagmawCrashCoverageMargin)
{
    return footprint.HasCoverage() && std::isfinite(point.X)
        && std::isfinite(point.Y)
        && MagmawCrashCoverageSignedDistance(footprint.Hull, point) <= margin;
}

struct MagmawCrashSideMovement
{
    bool Resolved = false;
    bool ActorUnsafe = false;
    Vector3 UnsafeSideAnchor;
    Vector3 SafeSideAnchor;
    // Set only when the actor is on the unsafe side (historical contract).
    Vector3 Destination;
    // The same safe-side point, resolved regardless of the actor's side so a
    // coverage check can ask whether any reachable point clears the crash.
    bool SafeDestinationValid = false;
    Vector3 SafeDestination;
};

inline MagmawCrashSideMovement ResolveMagmawCrashSideMovement(
    Vector3 const& actor, Vector3 const& footprint, Vector3 const& support,
    Vector3 const& left, Vector3 const& right, bool fixedLane,
    float supportSideDistance)
{
    MagmawCrashSideMovement result;
    auto finite = [](Vector3 const& point)
    {
        return std::isfinite(point.X) && std::isfinite(point.Y)
            && std::isfinite(point.Z);
    };
    auto distance = [](Vector3 const& first, Vector3 const& second)
    {
        return std::hypot(first.X - second.X, first.Y - second.Y);
    };
    if (!finite(actor) || !finite(footprint) || !finite(support)
        || !finite(left) || !finite(right)
        || !std::isfinite(supportSideDistance)
        || supportSideDistance <= 0.0f)
        return result;

    bool const footprintLeft = distance(footprint, left)
        <= distance(footprint, right);
    result.UnsafeSideAnchor = footprintLeft ? left : right;
    result.SafeSideAnchor = footprintLeft ? right : left;
    result.Resolved = true;
    result.ActorUnsafe = distance(actor, result.UnsafeSideAnchor)
        < distance(actor, result.SafeSideAnchor);

    // Preserve the destination anchor's logical floor. Native pathing remains
    // responsible for following terrain and validating the endpoint.
    if (fixedLane)
    {
        result.SafeDestination = result.SafeSideAnchor;
        result.SafeDestinationValid = true;
    }
    else
    {
        float const dx = result.SafeSideAnchor.X - result.UnsafeSideAnchor.X;
        float const dy = result.SafeSideAnchor.Y - result.UnsafeSideAnchor.Y;
        float const length = std::hypot(dx, dy);
        if (length >= 0.01f)
        {
            result.SafeDestination = {
                support.X + dx / length * supportSideDistance,
                support.Y + dy / length * supportSideDistance,
                support.Z };
            result.SafeDestinationValid = true;
        }
        else if (result.ActorUnsafe)
            return {};
    }
    if (result.ActorUnsafe)
        result.Destination = result.SafeDestination;
    return result;
}

struct MagmawCrashSideProposal
{
    bool Hold = false;
    // Hold because the only reachable evade point is also inside the crash:
    // keep position and keep casting instead of moving under the crash.
    bool NoSafeSpot = false;
    bool CoverageModel = false;
    std::optional<BotNativeAction::Candidate> Movement;
};

inline MagmawCrashSideProposal ProposeMagmawCrashSideMovement(
    Blackboard const& board, ActorSnapshot const& bot,
    MagmawCrashFootprint const& crash, Vector3 const& support,
    Vector3 const& left, Vector3 const& right, bool fixedLane,
    float supportSideDistance, MagmawEventMovementTransitionState* transition,
    float utility)
{
    MagmawCrashSideProposal proposal;
    if (!crash.Valid)
        return proposal;
    MagmawCrashSideMovement const movement =
        ResolveMagmawCrashSideMovement(bot.Position, crash.Centroid, support,
            left, right, fixedLane, supportSideDistance);
    if (!movement.Resolved)
        return proposal;

    Vector3 destination = movement.Destination;
    bool completeOnDestination = false;
    if (crash.HasCoverage())
    {
        // The lit cone, not the anchor midline, decides safety. The support
        // point sits on that midline yet inside one of the two native cones.
        proposal.CoverageModel = true;
        if (!MagmawCrashCovers(crash, bot.Position))
        {
            proposal.Hold = true;
            return proposal;
        }
        if (!movement.SafeDestinationValid
            || MagmawCrashCovers(crash, movement.SafeDestination))
        {
            proposal.Hold = true;
            proposal.NoSafeSpot = true;
            return proposal;
        }
        destination = movement.SafeDestination;
        completeOnDestination = true;
    }
    else if (!movement.ActorUnsafe)
    {
        proposal.Hold = true;
        return proposal;
    }

    if (transition)
    {
        // With coverage, finish only at the cleared destination; stopping at
        // the anchor midline can still leave the actor inside the cone.
        auto const* episode = completeOnDestination
            ? transition->RetainLethal(crash.Identity, bot.Guid,
                "massive_crash_evade", destination, crash.Centroid, 0.0f)
            : transition->RetainRoomSideLethal(crash.Identity, bot.Guid,
                "massive_crash_evade", destination,
                movement.UnsafeSideAnchor, movement.SafeSideAnchor);
        if (episode)
            proposal.Movement = BuildMagmawEventMovement(board, *episode,
                BotActionArbitration::Priority::Survival, utility);
        return proposal;
    }

    MagmawEventMovementTransitionState::Episode episode;
    episode.Mechanic = "massive_crash_evade";
    episode.AssignmentGuid = bot.Guid;
    episode.IntentId = board.Revision;
    episode.Destination = destination;
    proposal.Movement = BuildMagmawEventMovement(board, episode,
        BotActionArbitration::Priority::Survival, utility);
    return proposal;
}
}

#endif
