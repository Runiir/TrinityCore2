#ifndef TRINITY_BOT_RAID_DRUDGE_MINIMUM_DISTANCE_EXIT_H
#define TRINITY_BOT_RAID_DRUDGE_MINIMUM_DISTANCE_EXIT_H

#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeRecoveryCandidates.h"

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <sstream>
#include <string>
#include <utility>
#include <vector>

// Pure candidate generation and rejection accounting for the Drudge
// minimum-distance exit.  Native path planning and movement submission stay
// in the route module; this header decides which directions are tried and
// how a failed exit is described in the decision trace.
namespace BotRaidDrudgeMinimumDistanceExit
{
struct Point
{
    float X = 0.0f;
    float Y = 0.0f;
};

using Direction = std::pair<float, float>;

// Unit exit directions, most preferred first: away from every source, away
// from the sources' centroid, then both perpendiculars of every source pair.
// A single source has no pair, so both perpendiculars of the bot-source axis
// are its fallbacks; without them one rejected path left the bot holding
// inside the Whirlwind with no move and no cast.  A bot exactly on its only
// source has no axis at all and falls back to the four map axes.
// primaryCount receives how many leading directions are the original set;
// the rest are fallbacks that must also pass FallbackLaneSafe.
inline std::vector<Direction> CandidateDirections(Point const& bot,
    std::vector<Point> const& sources, std::size_t* primaryCount = nullptr)
{
    std::vector<Direction> directions;
    auto addDirection = [&directions](float x, float y)
    {
        float const length = std::hypot(x, y);
        if (length <= 0.001f)
            return;
        x /= length;
        y /= length;
        for (Direction const& direction : directions)
            if (direction.first * x + direction.second * y >= 0.999f)
                return;
        directions.emplace_back(x, y);
    };
    if (sources.empty())
        return directions;

    float centroidX = 0.0f;
    float centroidY = 0.0f;
    for (Point const& source : sources)
    {
        centroidX += source.X;
        centroidY += source.Y;
        addDirection(bot.X - source.X, bot.Y - source.Y);
    }
    centroidX /= float(sources.size());
    centroidY /= float(sources.size());
    addDirection(bot.X - centroidX, bot.Y - centroidY);
    for (size_t left = 0; left < sources.size(); ++left)
        for (size_t right = left + 1; right < sources.size(); ++right)
        {
            float pairX = sources[right].X - sources[left].X;
            float pairY = sources[right].Y - sources[left].Y;
            addDirection(-pairY, pairX);
            addDirection(pairY, -pairX);
        }
    if (primaryCount)
        *primaryCount = directions.size();
    if (sources.size() == 1)
    {
        float const axisX = bot.X - sources.front().X;
        float const axisY = bot.Y - sources.front().Y;
        addDirection(-axisY, axisX);
        addDirection(axisY, -axisX);
        if (directions.empty())
        {
            addDirection(1.0f, 0.0f);
            addDirection(0.0f, 1.0f);
            addDirection(-1.0f, 0.0f);
            addDirection(0.0f, -1.0f);
        }
    }
    return directions;
}

// The part of the StrictNativePath lane check that applies without a
// resolved two-tank lane contract.  A fallback exit is not the direct escape
// the original exit was tuned for, so its native path (after its start
// point) and its end must also keep every Drudge's home position -- the lane
// a Drudge charges back along -- exactly as SourceUnionPathSafe does, and must
// never approach the next encounter's boss (the StrictNativePath future
// encounter clearance, measured from where the bot stands).
struct FallbackLaneInput
{
    Point Start;
    Point End;
    std::vector<Point> Path;
    std::vector<Point> SourceHomes;
    float MinimumDistance = 0.0f;
    bool NextBossKnown = false;
    Point NextBoss;
};

enum class FallbackLane : std::uint8_t
{
    Safe,
    SourceHomeUnsafe,
    NextEncounterUnsafe
};

inline FallbackLane EvaluateFallbackLane(FallbackLaneInput const& input)
{
    using BotRaidDrudgeRecoveryCandidates::DistanceSquared;
    using BotRaidDrudgeRecoveryCandidates::PathPointPreservesSourceDistance;
    using BotRaidDrudgeRecoveryCandidates::Point2d;
    if (input.MinimumDistance <= 0.0f)
        return FallbackLane::SourceHomeUnsafe;
    Point2d const start{ input.Start.X, input.Start.Y };
    Point2d const end{ input.End.X, input.End.Y };
    std::vector<Point2d> points;
    for (std::size_t index = 0; index < input.Path.size(); ++index)
    {
        Point const& point = input.Path[index];
        if (!index && std::hypot(point.X - start.X, point.Y - start.Y) <= 0.25f)
            continue;
        points.push_back({ point.X, point.Y });
    }
    points.push_back(end);
    for (Point const& homePoint : input.SourceHomes)
    {
        Point2d const home{ homePoint.X, homePoint.Y };
        if (DistanceSquared(end, home)
                < input.MinimumDistance * input.MinimumDistance)
            return FallbackLane::SourceHomeUnsafe;
        float const startDistance = std::sqrt(DistanceSquared(start, home));
        for (Point2d const& point : points)
            if (!PathPointPreservesSourceDistance(point, home, startDistance,
                    input.MinimumDistance))
                return FallbackLane::SourceHomeUnsafe;
    }
    if (input.NextBossKnown)
    {
        Point2d const boss{ input.NextBoss.X, input.NextBoss.Y };
        float const clearance = std::sqrt(DistanceSquared(start, boss));
        for (Point2d const& point : points)
            if (std::sqrt(DistanceSquared(point, boss)) + 0.01f < clearance)
                return FallbackLane::NextEncounterUnsafe;
    }
    return FallbackLane::Safe;
}

// An admitted exit ends 2 yd beyond the damaging radius, but the exit stops
// owning the decision once the bot crosses the radius.  While the movement
// admitted for that exit is still carrying the bot, keep it (and its lease)
// until the bot arrives, so a cast-time spell cannot park the bot at the
// radius edge.  Only that exact exit continues: an unexpired Mechanic lease to
// its recorded destination, real unit movement (never the cached moving flag)
// and at most ExitContinuationCapMs after it was admitted.
struct ExitProgress
{
    bool ExitRecorded = false;
    // Lease owner is Mechanic and its destination is the recorded exit.
    bool LeaseIsThisExit = false;
    // The lease has not expired.
    bool LeaseActive = false;
    // Native unit movement.
    bool Moving = false;
    std::uint64_t ElapsedMs = 0;
    // Nearest live source, from the bot and from the exit destination.
    float BotSourceDistance = 0.0f;
    float DestinationSourceDistance = 0.0f;
    float SafeDistance = 0.0f;
};

constexpr float ExitArrivalToleranceYards = 0.5f;
constexpr std::uint64_t ExitContinuationCapMs = 3000;

// Same tolerance as the movement lease's destination identity.
inline bool SameExitDestination(float leftX, float leftY, float rightX,
    float rightY)
{
    return std::fabs(leftX - rightX) <= 0.1f && std::fabs(leftY - rightY) <= 0.1f;
}

inline bool ContinueAdmittedExit(ExitProgress const& progress)
{
    return progress.ExitRecorded && progress.LeaseIsThisExit
        && progress.LeaseActive && progress.Moving
        && progress.ElapsedMs <= ExitContinuationCapMs
        && progress.BotSourceDistance + ExitArrivalToleranceYards
            < progress.SafeDistance
        && progress.DestinationSourceDistance + ExitArrivalToleranceYards
            >= progress.SafeDistance;
}

enum class Rejection : std::uint8_t
{
    // The native path to the exterior point was missing, incomplete, a
    // shortcut or far from the navmesh.
    PathType,
    // A complete corridor ended away from the requested exterior point.
    EndpointMismatch,
    // The endpoint or a path point stayed inside a source's damaging radius.
    UnsafePath,
    // A fallback path crossed a Drudge home lane or approached the next
    // encounter, or its native floor had a gap.
    LaneUnsafe,
    PathFloorGap,
    // The movement lease kept an existing movement of equal or higher
    // priority (native reason: higher_priority_movement_active).
    LeaseRefused,
    // The movement executor rejected an admitted exit path.
    MoveRejected
};

// One minimum-distance decision, published as the trace recovery result.
struct Attempt
{
    std::uint32_t Sources = 0;
    std::uint32_t Directions = 0;
    std::uint32_t Tried = 0;
    std::uint32_t PathType = 0;
    std::uint32_t EndpointMismatch = 0;
    std::uint32_t UnsafePath = 0;
    std::uint32_t LaneUnsafe = 0;
    std::uint32_t PathFloorGap = 0;
    std::uint32_t LeaseRefused = 0;
    std::uint32_t MoveRejected = 0;
    std::uint32_t LastPathType = 0;
    std::uint32_t LeaseOwner = 0;
    std::uint32_t LeasePriority = 0;

    void Reject(Rejection rejection)
    {
        switch (rejection)
        {
            case Rejection::PathType: ++PathType; break;
            case Rejection::EndpointMismatch: ++EndpointMismatch; break;
            case Rejection::UnsafePath: ++UnsafePath; break;
            case Rejection::LaneUnsafe: ++LaneUnsafe; break;
            case Rejection::PathFloorGap: ++PathFloorGap; break;
            case Rejection::LeaseRefused: ++LeaseRefused; break;
            case Rejection::MoveRejected: ++MoveRejected; break;
        }
    }

    std::uint32_t Rejected() const
    {
        return PathType + EndpointMismatch + UnsafePath + LaneUnsafe
            + PathFloorGap + LeaseRefused + MoveRejected;
    }

    std::string ToString(bool moved) const
    {
        std::ostringstream out;
        out << (moved ? "exit_started" : "exit_failed")
            << ":sources=" << Sources
            << ",directions=" << Directions
            << ",tried=" << Tried
            << ",path_type=" << PathType
            << ",endpoint_mismatch=" << EndpointMismatch
            << ",unsafe_path=" << UnsafePath
            << ",lane_unsafe=" << LaneUnsafe
            << ",path_floor_gap=" << PathFloorGap
            << ",lease_refused=" << LeaseRefused
            << ",move_rejected=" << MoveRejected
            << ",last_path_type=" << LastPathType;
        if (LeaseRefused)
            out << ",lease_owner=" << LeaseOwner
                << ",lease_priority=" << LeasePriority;
        return out.str();
    }
};
}

#endif
