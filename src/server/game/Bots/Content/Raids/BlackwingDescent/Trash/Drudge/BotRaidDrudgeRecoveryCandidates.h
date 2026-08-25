#ifndef TRINITY_BOT_RAID_DRUDGE_RECOVERY_CANDIDATES_H
#define TRINITY_BOT_RAID_DRUDGE_RECOVERY_CANDIDATES_H

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <vector>

namespace BotRaidDrudgeRecoveryCandidates
{
struct Point2d
{
    float X = 0.0f;
    float Y = 0.0f;
};

struct Candidate
{
    Point2d Point;
    std::uint8_t FanIndex = 0;
};

struct Constraints
{
    Point2d Source0;
    Point2d Source1;
    Point2d Midpoint;
    Point2d LaneAxis;
    float MinimumSourceDistance = 0.0f;
    float LaneSign = 0.0f;
    float MinimumLaneProjection = 0.0f;
};

// A landed Rush can displace a non-tank while its declared formation anchor
// remains valid for ordinary staging.  Only an unsafe non-tank in that
// recovery state may switch the fan origin to its live position.  Tanks and
// already-safe members retain the stable declared-anchor contract.
inline Point2d SelectOrigin(Point2d const& declared, Point2d const& current,
    bool tank, bool landedRushRecovery, bool currentSourceUnionSafe)
{
    return !tank && landedRushRecovery && !currentSourceUnionSafe
        ? current : declared;
}

inline float DistanceSquared(Point2d const& left, Point2d const& right)
{
    float const x = left.X - right.X;
    float const y = left.Y - right.Y;
    return x * x + y * y;
}

// A member already inside a live source radius must be able to leave it.
// Keep an unsafe start from moving materially closer, while preserving the
// configured minimum (with the same small native-path tolerance) once the
// member starts outside the radius.
inline float PathDistanceFloor(float startDistance, float minimumDistance)
{
    return std::max(0.0f,
        std::min(startDistance, minimumDistance) - 0.25f);
}

inline bool PathPointPreservesSourceDistance(
    Point2d const& point, Point2d const& source,
    float startDistance, float minimumDistance)
{
    float const floor = PathDistanceFloor(startDistance, minimumDistance);
    return minimumDistance > 0.0f && std::isfinite(startDistance)
        && DistanceSquared(point, source) >= floor * floor;
}

inline float Dot(Point2d const& left, Point2d const& right)
{
    return left.X * right.X + left.Y * right.Y;
}

inline Point2d Normalize(Point2d point)
{
    float const length = std::hypot(point.X, point.Y);
    if (length <= 0.001f)
        return {};
    point.X /= length;
    point.Y /= length;
    return point;
}

inline bool NearlyEqual(Point2d const& left, Point2d const& right)
{
    return DistanceSquared(left, right) <= 0.0001f;
}

inline Point2d Rotate(Point2d direction, float radians)
{
    float const cosine = std::cos(radians);
    float const sine = std::sin(radians);
    return { direction.X * cosine - direction.Y * sine,
        direction.X * sine + direction.Y * cosine };
}

template <std::size_t SourceCount>
inline float RequiredTravel(Point2d const& origin, Point2d const& direction,
    std::array<Point2d, SourceCount> const& sources, float safeDistance)
{
    float travel = 0.0f;
    float const safeDistanceSquared = safeDistance * safeDistance;
    for (Point2d const& source : sources)
    {
        float const offsetX = origin.X - source.X;
        float const offsetY = origin.Y - source.Y;
        float const distanceSquared = offsetX * offsetX + offsetY * offsetY;
        if (distanceSquared >= safeDistanceSquared)
            continue;
        float const projection = offsetX * direction.X + offsetY * direction.Y;
        float const discriminant = projection * projection
            + safeDistanceSquared - distanceSquared;
        if (discriminant < 0.0f)
            return std::numeric_limits<float>::infinity();
        travel = std::max(travel, -projection + std::sqrt(discriminant));
    }
    return travel + 0.5f;
}

inline float RequiredTravel(Point2d const& origin, Point2d const& direction,
    Point2d const& source0, Point2d const& source1, float safeDistance)
{
    return RequiredTravel(origin, direction,
        std::array<Point2d, 2>{ source0, source1 }, safeDistance);
}

// The declared point remains first. If a landed Rush makes it unsafe, the
// remaining points are a fixed, deterministic fan from the source-away
// direction. No random seed or live ordering participates in this list.
template <std::size_t SourceCount>
inline std::vector<Candidate> BuildCandidatesForSources(
    Point2d const& declared, std::array<Point2d, SourceCount> const& sources,
    Point2d const& laneAxis, float laneSign, float minimumSourceDistance)
{
    std::vector<Candidate> candidates;
    if (minimumSourceDistance <= 0.0f
        || (laneSign != -1.0f && laneSign != 1.0f))
        return candidates;

    candidates.push_back({ declared, 0 });
    Point2d const normalizedAxis = Normalize(laneAxis);
    Point2d away{ declared.X - (sources[0].X + sources[1].X) * 0.5f,
        declared.Y - (sources[0].Y + sources[1].Y) * 0.5f };
    away = Normalize(away);
    if (away.X == 0.0f && away.Y == 0.0f)
    {
        Point2d pairPerpendicular{ sources[1].Y - sources[0].Y,
            sources[0].X - sources[1].X };
        away = Normalize(pairPerpendicular);
        Point2d const laneDirection{ normalizedAxis.X * laneSign,
            normalizedAxis.Y * laneSign };
        if ((away.X != 0.0f || away.Y != 0.0f)
            && Dot(away, laneDirection) < 0.0f)
        {
            away.X = -away.X;
            away.Y = -away.Y;
        }
    }
    if (away.X == 0.0f && away.Y == 0.0f)
        away = { normalizedAxis.X * laneSign, normalizedAxis.Y * laneSign };
    if (away.X == 0.0f && away.Y == 0.0f)
        return candidates;

    constexpr std::array<float, 5> FanAnglesRadians{
        0.0f, 0.7853981633974483f, -0.7853981633974483f,
        1.5707963267948966f, -1.5707963267948966f };
    for (std::size_t index = 0; index < FanAnglesRadians.size(); ++index)
    {
        Point2d const direction = Rotate(away, FanAnglesRadians[index]);
        float const travel = RequiredTravel(declared, direction, sources,
            minimumSourceDistance);
        if (!std::isfinite(travel))
            continue;
        Point2d const candidate{
            declared.X + direction.X * travel,
            declared.Y + direction.Y * travel };
        bool duplicate = false;
        for (Candidate const& existing : candidates)
            if (NearlyEqual(existing.Point, candidate))
            {
                duplicate = true;
                break;
            }
        if (!duplicate)
            candidates.push_back({ candidate, static_cast<std::uint8_t>(index + 1) });
    }
    return candidates;
}

inline std::vector<Candidate> BuildCandidates(
    Point2d const& declared, Point2d const& source0, Point2d const& source1,
    Point2d const& laneAxis, float laneSign, float minimumSourceDistance)
{
    return BuildCandidatesForSources(
        declared, std::array<Point2d, 2>{ source0, source1 }, laneAxis,
        laneSign, minimumSourceDistance);
}

inline std::vector<Candidate> BuildCandidates(
    Point2d const& declared, Point2d const& source0, Point2d const& source1,
    Point2d const& source0Home, Point2d const& source1Home,
    Point2d const& laneAxis, float laneSign, float minimumSourceDistance)
{
    return BuildCandidatesForSources(declared,
        std::array<Point2d, 4>{ source0, source1, source0Home, source1Home },
        laneAxis, laneSign, minimumSourceDistance);
}

inline bool SourceSafe(Point2d const& candidate, Constraints const& constraints)
{
    float const minimum = constraints.MinimumSourceDistance;
    return minimum > 0.0f
        && DistanceSquared(candidate, constraints.Source0) >= minimum * minimum
        && DistanceSquared(candidate, constraints.Source1) >= minimum * minimum;
}

inline bool SourceSafeAgainstUnion(Point2d const& candidate,
    Constraints const& constraints, Point2d const& source0Home,
    Point2d const& source1Home)
{
    float const minimum = constraints.MinimumSourceDistance;
    return minimum > 0.0f
        && DistanceSquared(candidate, constraints.Source0) >= minimum * minimum
        && DistanceSquared(candidate, constraints.Source1) >= minimum * minimum
        && DistanceSquared(candidate, source0Home) >= minimum * minimum
        && DistanceSquared(candidate, source1Home) >= minimum * minimum;
}

inline bool LaneSafe(Point2d const& candidate, Constraints const& constraints)
{
    Point2d const axis = Normalize(constraints.LaneAxis);
    return (axis.X != 0.0f || axis.Y != 0.0f)
        && (constraints.LaneSign == -1.0f || constraints.LaneSign == 1.0f)
        && constraints.LaneSign * Dot(
            { candidate.X - constraints.Midpoint.X,
                candidate.Y - constraints.Midpoint.Y }, axis)
            >= constraints.MinimumLaneProjection;
}

}

#endif
