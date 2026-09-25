#ifndef TRINITY_BOT_NEFARIAN_PATH_H
#define TRINITY_BOT_NEFARIAN_PATH_H

// Leg planner on the GO 207834 surface. Package T's transport-surface walk
// launches one straight, level-checked segment of at most
// MaxSurfaceWalkYards (12), only while the bot stands still, so a
// destination is reached as a sequence of short legs, one per decision:
// - on the centre floor (r <= 27, convex): straight;
// - between the centre floor and the ring: one short radial leg across the
//   rise (r 26.5 <-> 33.5) with a wider floor tolerance, since the rise is not
//   level;
// - on the ring: straight when the segment stays on the ring and 6 yards from
//   every pillar, otherwise along a lane: r 33.5 inside the pillars or r 50
//   outside them.
// The plan is recomputed from the observed position every decision, so a leg
// that was refused or cut short is simply planned again.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianGeometry.h"
#include <optional>
#include <string_view>

namespace BotEncounter::Nefarian
{
constexpr float MaxLegYards = 9.5f;
constexpr float InnerGateRadius = 26.5f;
constexpr float RingGateRadius = 33.5f;
constexpr float InnerLaneRadius = 33.5f;
constexpr float OuterLaneRadius = 50.0f;
constexpr float LevelLegFloorTolerance = 0.6f;
constexpr float RiseLegFloorTolerance = 0.9f;
constexpr float LegArrivalYards = 1.0f;

enum class PlatformRegion : uint8
{
    Centre,
    Rise,
    Ring
};

// Paths may run half a yard inside the standing limits: the rise ends at
// r 32 (package T's probe), and lane chords dip just inside r 33.5.
constexpr float RingPathLimit = RingFloorLimit - 0.5f;

inline PlatformRegion RegionOf(LocalPoint point)
{
    float const radius = Length(point);
    if (radius <= InnerFloorLimit)
        return PlatformRegion::Centre;
    if (radius < RingPathLimit)
        return PlatformRegion::Rise;
    return PlatformRegion::Ring;
}

struct PathLeg
{
    LocalPoint To;
    float LocalZ = PlatformFrame::FloorLocalZ;
    float FloorToleranceYards = LevelLegFloorTolerance;
    bool CrossesRise = false;
    std::string_view Kind; // centre, rise, ring_straight, ring_lane, lane_join
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

// A straight ring segment stays on the ring: its closest approach to the
// centre is on the ring side of the rise.
inline bool SegmentStaysOnRing(LocalPoint from, LocalPoint to)
{
    return PointSegmentDistance({ 0.0f, 0.0f }, from, to) >= RingPathLimit
        && Length(from) <= OuterFloorLimit + 0.5f
        && Length(to) <= OuterFloorLimit + 0.5f;
}

inline LocalPoint StepToward(LocalPoint from, LocalPoint to, float maxYards)
{
    float const distance = Distance(from, to);
    if (distance <= maxYards)
        return to;
    float const scale = maxYards / distance;
    return { from.X + (to.X - from.X) * scale, from.Y + (to.Y - from.Y) * scale };
}

// Level legs keep the bot's own height (the floor it stands on); the rise
// crossing aims at the far side's floor height.
inline PathLeg LevelLeg(LocalPoint to, float fromLocalZ, std::string_view kind)
{
    PathLeg leg;
    leg.To = to;
    leg.LocalZ = fromLocalZ;
    leg.Kind = kind;
    return leg;
}

inline PathLeg RiseLeg(LocalPoint to)
{
    PathLeg leg;
    leg.To = to;
    leg.LocalZ = FloorLocalZAt(to);
    leg.FloorToleranceYards = RiseLegFloorTolerance;
    leg.CrossesRise = true;
    leg.Kind = "rise";
    return leg;
}

// One step along a lane circle toward a heading, as a chord of at most
// MaxLegYards; the step never overshoots the target heading.
inline LocalPoint LaneStep(float fromAngle, float toAngle, float laneRadius)
{
    float const delta = NormalizeSigned(toAngle - fromAngle);
    float const maxStep = 2.0f * std::asin(std::min(0.99f,
        MaxLegYards * 0.5f / laneRadius));
    float const step = std::fabs(delta) <= maxStep ? delta
        : (delta > 0.0f ? maxStep : -maxStep);
    return Polar(fromAngle + step, laneRadius);
}

inline float LaneOf(LocalPoint point)
{
    return Length(point) < (InnerLaneRadius + OuterLaneRadius) * 0.5f
        ? InnerLaneRadius : OuterLaneRadius;
}

// A heading where a radial line from the centre-floor gate out to the outer
// lane clears every pillar.
inline bool RadialClear(float angle)
{
    return SegmentClearOfPillars(Polar(angle, InnerGateRadius),
        Polar(angle, OuterLaneRadius));
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

// Next leg on the ring toward a ring point (the goal, or the gate before a
// rise crossing): straight when that stays on the ring and clear of the
// pillars; otherwise along this bot's lane, changing lanes only on a radially
// clear heading.
inline std::optional<PathLeg> RingLeg(LocalPoint from, float fromLocalZ,
    LocalPoint to)
{
    if (SegmentStaysOnRing(from, to) && SegmentClearOfPillars(from, to))
        return LevelLeg(StepToward(from, to, MaxLegYards), fromLocalZ,
            "ring_straight");
    float const fromAngle = AngleOf(from);
    float const lane = LaneOf(from);
    if (std::fabs(Length(from) - lane) > 1.5f)
    {
        LocalPoint const join = StepToward(from, Polar(fromAngle, lane),
            MaxLegYards);
        if (!SegmentClearOfPillars(from, join))
            return std::nullopt;
        return LevelLeg(join, fromLocalZ, "lane_join");
    }
    float const toLane = LaneOf(to);
    float heading = AngleOf(to);
    if (toLane != lane)
    {
        float const crossing = NearestRadialCrossing(fromAngle, heading);
        if (std::fabs(NormalizeSigned(crossing - fromAngle)) < DegToRad(1.0f))
        {
            LocalPoint const change = StepToward(from, Polar(crossing, toLane),
                MaxLegYards);
            if (!SegmentClearOfPillars(from, change))
                return std::nullopt;
            return LevelLeg(change, fromLocalZ, "lane_change");
        }
        heading = crossing;
    }
    LocalPoint const next = LaneStep(fromAngle, heading, lane);
    if (Distance(next, from) < 0.2f || !SegmentClearOfPillars(from, next))
        return std::nullopt;
    return LevelLeg(next, fromLocalZ, "ring_lane");
}

// The next straight leg from the bot's local position toward a standing
// spot, or nothing when the bot has arrived or no lawful leg exists.
inline std::optional<PathLeg> NextLeg(LocalPoint from, float fromLocalZ,
    LocalPoint goal)
{
    goal = SnapToStandingArea(goal);
    if (Distance(from, goal) <= LegArrivalYards)
        return std::nullopt;
    PlatformRegion const here = RegionOf(from);
    PlatformRegion const there = RegionOf(goal);
    float const fromAngle = Length(from) < 0.01f ? AngleOf(goal) : AngleOf(from);

    if (here == PlatformRegion::Rise)
        return RiseLeg(Polar(fromAngle, there == PlatformRegion::Centre
            ? InnerGateRadius : RingGateRadius));

    if (here == PlatformRegion::Centre)
    {
        if (there == PlatformRegion::Centre)
            return LevelLeg(StepToward(from, goal, MaxLegYards), fromLocalZ,
                "centre");
        // Cross the rise radially toward the goal's heading.
        float const gateAngle = AngleOf(goal);
        LocalPoint const gate = Polar(gateAngle, InnerGateRadius);
        if (Distance(from, gate) > LegArrivalYards)
            return LevelLeg(StepToward(from, gate, MaxLegYards), fromLocalZ,
                "centre");
        return RiseLeg(Polar(gateAngle, RingGateRadius));
    }

    // On the ring.
    if (there == PlatformRegion::Ring)
        return RingLeg(from, fromLocalZ, goal);
    // Leave the ring through a gate inside the pillars: from the outer lane at
    // the nearest radially clear heading, from inside at this heading; then
    // radially across the rise.
    float const gateAngle = LaneOf(from) == OuterLaneRadius
        ? NearestRadialCrossing(fromAngle, AngleOf(goal)) : fromAngle;
    LocalPoint const gate = Polar(gateAngle, RingGateRadius);
    if (Distance(from, gate) > LegArrivalYards)
        return RingLeg(from, fromLocalZ, gate);
    return RiseLeg(Polar(gateAngle, InnerGateRadius));
}
}

#endif
