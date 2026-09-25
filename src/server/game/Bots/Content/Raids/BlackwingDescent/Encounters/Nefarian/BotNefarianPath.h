#ifndef TRINITY_BOT_NEFARIAN_PATH_H
#define TRINITY_BOT_NEFARIAN_PATH_H

// Leg planner on the GO 207834 surface. Package T's transport-surface walk
// launches one straight segment of at most MaxSurfaceWalkYards (12), moving
// at the segment's linearly interpolated height, and refuses it unless every
// 0.25-yard sample has the platform's floor within the leg's tolerance of
// that height and the body sweep clears the pillars. So a destination is
// reached as a sequence of short legs, one per decision:
// - every leg ends at the model floor height of its end (FloorLocalZAt);
// - the whole floor is walkable: the flat centre, the 10-degree ramp and the
//   ring. A straight chord over the ramp's two creases deviates from the floor
//   by at most slope x (a x b) / (a + b) for the parts a and b on either side,
//   so a leg that crosses a crease is capped at 6 yards (0.26 yards at most);
// - a leg keeps 7 yards from every pillar centre; when the straight segment
//   does not, it goes through one or two waypoints on the inner circle (r 27,
//   on the ramp, inside the pillars) or the outer circle (r 50, outside them),
//   whichever gives the shortest clear path.
// The plan is recomputed from the observed position every decision, so a leg
// that was refused or cut short is simply planned again.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianGeometry.h"
#include <optional>
#include <string_view>
#include <vector>

namespace BotEncounter::Nefarian
{
constexpr float MaxLegYards = 9.5f;
constexpr float CreaseLegYards = 6.0f;
constexpr float LegFloorTolerance = 0.6f;
constexpr float LegArrivalYards = 1.0f;
constexpr float InnerWaypointRadius = 27.0f;
constexpr float OuterWaypointRadius = 50.0f;
constexpr int WaypointHeadingStepDeg = 10;

struct PathLeg
{
    LocalPoint To;
    float LocalZ = PlatformFrame::FloorLocalZ;
    float FloorToleranceYards = LegFloorTolerance;
    std::string_view Kind; // direct, waypoint
};

inline float PointSegmentDistance(LocalPoint point, LocalPoint from, LocalPoint to)
{
    float const dx = to.X - from.X;
    float const dy = to.Y - from.Y;
    float const lengthSq = dx * dx + dy * dy;
    float t = lengthSq > 0.0f
        ? ((point.X - from.X) * dx + (point.Y - from.Y) * dy) / lengthSq : 0.0f;
    t = std::max(0.0f, std::min(1.0f, t));
    return Distance(point, { from.X + t * dx, from.Y + t * dy });
}

inline bool SegmentClearOfPillars(LocalPoint from, LocalPoint to)
{
    for (LocalPoint const& pillar : PillarCenters)
        if (PointSegmentDistance(pillar, from, to) < PillarPathClearance)
            return false;
    return true;
}

// Clear of the pillars and inside the platform's outer limit (the floor is
// convex out to r 60, so both ends inside r 57 keep the segment inside).
inline bool SegmentWalkable(LocalPoint from, LocalPoint to)
{
    return Length(from) <= OuterFloorLimit + 0.5f
        && Length(to) <= OuterFloorLimit + 0.5f
        && SegmentClearOfPillars(from, to);
}

inline LocalPoint StepToward(LocalPoint from, LocalPoint to, float maxYards)
{
    float const distance = Distance(from, to);
    if (distance <= maxYards)
        return to;
    float const scale = maxYards / distance;
    return { from.X + (to.X - from.X) * scale, from.Y + (to.Y - from.Y) * scale };
}

// Closest and farthest distance from the centre along a segment.
inline void SegmentRadiusRange(LocalPoint from, LocalPoint to, float& nearest,
    float& farthest)
{
    nearest = PointSegmentDistance({ 0.0f, 0.0f }, from, to);
    farthest = std::max(Length(from), Length(to));
}

inline bool SegmentCrossesCrease(LocalPoint from, LocalPoint to)
{
    float nearest = 0.0f;
    float farthest = 0.0f;
    SegmentRadiusRange(from, to, nearest, farthest);
    for (float crease : { RampStartRadius, RampEndRadius })
        if (nearest < crease && farthest > crease)
            return true;
    return false;
}

// One leg toward a point the straight segment already reaches lawfully.
inline PathLeg LegToward(LocalPoint from, LocalPoint to, std::string_view kind)
{
    LocalPoint next = StepToward(from, to, MaxLegYards);
    if (SegmentCrossesCrease(from, next))
        next = StepToward(from, to, CreaseLegYards);
    PathLeg leg;
    leg.To = next;
    leg.LocalZ = FloorLocalZAt(next);
    leg.Kind = kind;
    return leg;
}

// A heading whose radial line from the ramp out to the outer circle clears
// every pillar (used for the tanks' pull points).
inline bool RadialClear(float angle)
{
    return SegmentClearOfPillars(Polar(angle, InnerWaypointRadius),
        Polar(angle, OuterWaypointRadius + 2.0f));
}

// The radially clear heading nearest to `fromAngle`, searched in 3-degree
// steps and first toward `towardAngle`.
inline float NearestRadialCrossing(float fromAngle, float towardAngle)
{
    float const preferred = NormalizeSigned(towardAngle - fromAngle) >= 0.0f
        ? 1.0f : -1.0f;
    for (int step = 0; step <= 60; ++step)
        for (float sign : { preferred, -preferred })
        {
            float const angle = fromAngle + sign * DegToRad(3.0f * float(step));
            if (RadialClear(angle))
                return NormalizeSigned(angle);
        }
    return fromAngle;
}

inline std::vector<LocalPoint> PathWaypoints()
{
    std::vector<LocalPoint> points;
    for (float radius : { InnerWaypointRadius, OuterWaypointRadius })
        for (int heading = 0; heading < 360; heading += WaypointHeadingStepDeg)
        {
            LocalPoint const point = Polar(DegToRad(float(heading)), radius);
            if (!NearPillar(point, PillarPathClearance + 0.5f))
                points.push_back(point);
        }
    return points;
}

// The next straight leg from the bot's local position toward a standing
// spot, or nothing when the bot has arrived or no lawful path exists.
inline std::optional<PathLeg> NextLeg(LocalPoint from, LocalPoint goal)
{
    goal = SnapToStandingArea(goal);
    if (Distance(from, goal) <= LegArrivalYards)
        return std::nullopt;
    // Too close to a pillar block (a knockback, say): step straight away from
    // it first.
    for (LocalPoint const& pillar : PillarCenters)
        if (Distance(from, pillar) < PillarPathClearance)
        {
            LocalPoint const away{ from.X - pillar.X, from.Y - pillar.Y };
            float const angle = Length(away) < 0.01f ? AngleOf(from) + Pi
                : AngleOf(away);
            return LegToward(from, Offset(pillar, angle,
                PillarPathClearance + 0.5f), "pillar_clearance");
        }
    if (SegmentWalkable(from, goal))
        return LegToward(from, goal, "direct");

    // Shortest clear path through one waypoint, then through two.
    static std::vector<LocalPoint> const waypoints = PathWaypoints();
    std::optional<LocalPoint> best;
    float bestLength = 0.0f;
    for (LocalPoint const& waypoint : waypoints)
    {
        if (!SegmentWalkable(from, waypoint) || !SegmentWalkable(waypoint, goal))
            continue;
        float const length = Distance(from, waypoint) + Distance(waypoint, goal);
        if (!best || length < bestLength)
        {
            best = waypoint;
            bestLength = length;
        }
    }
    if (!best)
        for (LocalPoint const& first : waypoints)
        {
            if (!SegmentWalkable(from, first))
                continue;
            for (LocalPoint const& second : waypoints)
            {
                if (!SegmentWalkable(first, second)
                    || !SegmentWalkable(second, goal))
                    continue;
                float const length = Distance(from, first)
                    + Distance(first, second) + Distance(second, goal);
                if (!best || length < bestLength)
                {
                    best = first;
                    bestLength = length;
                }
            }
        }
    if (!best)
        return std::nullopt;
    return LegToward(from, *best, "waypoint");
}
}

#endif
