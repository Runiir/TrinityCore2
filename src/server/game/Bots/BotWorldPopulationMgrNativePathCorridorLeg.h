#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_PATH_CORRIDOR_LEG_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_PATH_CORRIDOR_LEG_H

#include <array>
#include <cmath>
#include <cstddef>
#include <vector>

namespace BotWorldMovement
{
// PathGenerator (Movement/PathGenerator.h) smooths a native walk into at most
// MAX_POINT_PATH_LENGTH = 74 points spaced SMOOTH_PATH_STEP_SIZE = 4 yd apart,
// about 74 x 4 = 296 yd. A longer walk is refused with
// PathEndpointResult::Capacity (path type NOPATH | SHORTCUT) even when Detour
// found a connected polygon corridor. The values are mirrored here so this
// header stays free of Detour; a test pins them to PathGenerator.h.
constexpr std::size_t NativeCorridorSmoothPointCapacity = 74;
constexpr float NativeCorridorSmoothStepYards = 4.0f;
constexpr float NativeCorridorSmoothCapacityYards =
    float(NativeCorridorSmoothPointCapacity) * NativeCorridorSmoothStepYards;

// Leg targets measured along the corridor's straight (corner) polyline, from
// the longest down. The smoothed walk to a target steers around corners and
// is somewhat longer than the corner polyline, so the longest target keeps a
// wide margin below the 296 yd cap; shorter targets are the fallbacks when a
// longer one cannot be proved by a complete ordinary native path.
constexpr std::array<float, 5> NativeCorridorLegDistances{
    220.0f, 180.0f, 140.0f, 100.0f, 60.0f };
constexpr float NativeCorridorLegMaximumYards = 220.0f;
// Every accepted leg moves the actor at least this far, so each leg consumes
// a measurable prefix of the corridor and the remaining walk shrinks.
constexpr float NativeCorridorLegMinimumYards = 40.0f;

static_assert(NativeCorridorLegMaximumYards < NativeCorridorSmoothCapacityYards,
    "a corridor leg must fit PathGenerator's smoothed point capacity");
static_assert(NativeCorridorLegDistances.front() == NativeCorridorLegMaximumYards,
    "the first leg target is the longest");
static_assert(NativeCorridorLegDistances.back() >= NativeCorridorLegMinimumYards,
    "every leg target reaches the minimum leg");

template <typename Point>
inline float NativeCorridorPointDistance(Point const& a, Point const& b)
{
    float const dx = b.x - a.x;
    float const dy = b.y - a.y;
    float const dz = b.z - a.z;
    return std::sqrt(dx * dx + dy * dy + dz * dz);
}

// cumulative[i] is the polyline distance from corners[0] to corners[i].
template <typename Point>
inline std::vector<float> NativeCorridorCumulativeDistances(
    std::vector<Point> const& corners)
{
    std::vector<float> cumulative;
    cumulative.reserve(corners.size());
    float total = 0.0f;
    for (std::size_t i = 0; i < corners.size(); ++i)
    {
        if (i)
            total += NativeCorridorPointDistance(corners[i - 1], corners[i]);
        cumulative.push_back(total);
    }
    return cumulative;
}

// The point at polyline distance `distance` from corners[0]. Fails outside
// [0, total] or for a degenerate polyline; never extrapolates past the end.
template <typename Point>
inline bool NativeCorridorPointAtDistance(std::vector<Point> const& corners,
    std::vector<float> const& cumulative, float distance, Point& out)
{
    if (corners.size() < 2 || cumulative.size() != corners.size()
        || !std::isfinite(distance) || distance < 0.0f
        || distance > cumulative.back())
        return false;
    for (std::size_t i = 1; i < corners.size(); ++i)
    {
        if (distance > cumulative[i])
            continue;
        float const span = cumulative[i] - cumulative[i - 1];
        float const t = span > 0.0f
            ? (distance - cumulative[i - 1]) / span : 0.0f;
        out = corners[i - 1];
        out.x = corners[i - 1].x + (corners[i].x - corners[i - 1].x) * t;
        out.y = corners[i - 1].y + (corners[i].y - corners[i - 1].y) * t;
        out.z = corners[i - 1].z + (corners[i].z - corners[i - 1].z) * t;
        return true;
    }
    return false;
}

template <typename Point>
struct NativeCorridorLegCandidate
{
    Point Position;
    float CorridorDistance = 0.0f;
    bool Corner = false;
};

// Ordered leg candidates on a corner polyline whose corners[0] is the actor:
// first the fixed leg distances (decreasing), then the interior corners
// within [minimum, maximum] leg (decreasing). Every candidate lies strictly
// inside the corridor, never at or beyond its end.
template <typename Point>
inline std::vector<NativeCorridorLegCandidate<Point>>
BuildNativeCorridorLegCandidates(std::vector<Point> const& corners)
{
    std::vector<NativeCorridorLegCandidate<Point>> candidates;
    if (corners.size() < 2)
        return candidates;
    std::vector<float> const cumulative =
        NativeCorridorCumulativeDistances(corners);
    float const total = cumulative.back();
    for (float distance : NativeCorridorLegDistances)
    {
        if (distance >= total || distance < NativeCorridorLegMinimumYards)
            continue;
        Point point = corners.front();
        if (NativeCorridorPointAtDistance(corners, cumulative, distance, point))
            candidates.push_back({ point, distance, false });
    }
    for (std::size_t i = corners.size() - 1; i-- > 1;)
    {
        float const distance = cumulative[i];
        if (distance >= total || distance > NativeCorridorLegMaximumYards
            || distance < NativeCorridorLegMinimumYards)
            continue;
        candidates.push_back({ corners[i], distance, true });
    }
    return candidates;
}

// Walks the candidates in order and keeps the first one that `verify` proves
// (verify writes the verified native endpoint) and whose verified endpoint is
// at least the minimum leg from the actor. Returns false when none qualifies.
template <typename Point, typename Verify>
inline bool SelectNativeCorridorLeg(std::vector<Point> const& corners,
    Point const& actor, Verify&& verify, Point& selectedEndpoint)
{
    for (NativeCorridorLegCandidate<Point> const& candidate :
        BuildNativeCorridorLegCandidates(corners))
    {
        Point endpoint = candidate.Position;
        if (!verify(candidate, endpoint))
            continue;
        if (!(NativeCorridorPointDistance(actor, endpoint)
                >= NativeCorridorLegMinimumYards))
            continue;
        selectedEndpoint = endpoint;
        return true;
    }
    return false;
}
}

#endif
