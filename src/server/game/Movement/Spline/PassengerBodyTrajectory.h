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

#ifndef TRINITYSERVER_PASSENGER_BODY_TRAJECTORY_H
#define TRINITYSERVER_PASSENGER_BODY_TRAJECTORY_H

// The whole body along a trajectory the unit does not steer: a fall, a jump
// arc. PassengerSplineCollision.h sweeps a walk with rays along the segment
// at lateral offsets perpendicular to its horizontal direction; a fall has no
// horizontal direction, so that sweep sees only the centre line and a body
// falling beside a wall or a sloped skirt ends inside it (BWD 10N round 3:
// the pillar-1 slot-2 step-off landed on the ring with 0.65 yd of the body in
// the pillar skirt).
//
// The body is a vertical cylinder of the collision radius from the knee
// (KneeYards over the feet; below it the floor's own proof owns clearance, as
// for every walk) up to the collision height. ProveTrajectory proves, against
// a caller-supplied `blocked(origin, unitDirection, length)` ray query:
// - the landing: that cylinder at the last point is empty (FootprintOffsets
//   cast straight down from the head to the knee, and 16 radial rays from the
//   centre out to the radius at every LevelStepYards from the knee to the
//   head);
// - the path: a vertical piece sweeps the whole column it passes (the same
//   footprint rays from the highest head to the lowest knee, the radial rays
//   at every level of it); any other piece is cut every LevelStepYards, the
//   footprint grid is swept along each cut at every level, and the cylinder
//   at each cut is proved as at the landing.
// The first point is where the unit already stands and is not re-proved. A
// sampled proof: an obstacle thinner than the ray spacing (0.15 yd between
// rim rays, 0.35 yd between levels) could pass between rays; walls, skirts,
// rims and floors cannot. Cost: the landing is 25 + 16 * levels rays; a
// vertical fall of d yards adds 25 + 16 * (d + height - knee) / 0.35.
//
// An effect spline (MoveSpline with Falling or Parabolic) is sampled as the
// server runs it (SampleSpline) and reduced to chords; the body grows, in
// radius, knee and head alike (MakeBody), by the chords' largest 3D deviation
// from the samples plus the curve's largest bulge between samples
// (ReduceToChords), so a proof of the chords covers the curve.
// Pure: the caller supplies the ray query.

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace Movement::BodyTrajectory
{
constexpr float KneeYards = 0.5f;
constexpr float LevelStepYards = 0.35f;
constexpr int RimDirections = 16;
constexpr int InnerDirections = 8;
// DEFAULT_PLAYER_BOUNDING_RADIUS.
constexpr float MinBodyRadiusYards = 0.389f;
// Less horizontal motion than this is a vertical piece (the column proof).
constexpr float VerticalYards = 1e-3f;
constexpr float DegenerateYards = 1e-4f;
constexpr int SampleStepMs = 5;
constexpr float ChordToleranceYards = 0.05f;
constexpr std::size_t MaxSamples = 512;

struct Body
{
    float Radius = MinBodyRadiusYards;
    float Knee = KneeYards;
    float Top = 2.0f;
};

// `inflation` (ReduceToChords' InflationYards: how far the arc lies from its
// chords, in 3D) grows the body in every direction, not only sideways: a
// cylinder standing anywhere within `inflation` of a chord point lies inside
// the cylinder of radius + inflation from knee - inflation to top + inflation.
// A parabola's apex rises straight above its chord, so a head that clears the
// chords by less than the inflation can still meet a ceiling the arc reaches.
inline Body MakeBody(float radius, float collisionHeight, float inflation = 0.0f)
{
    float const grow = std::max(inflation, 0.0f);
    Body body;
    body.Radius = std::max(radius, MinBodyRadiusYards) + grow;
    body.Knee = std::max(KneeYards - grow, 0.0f);
    body.Top = std::max(collisionHeight, 1.0f) + grow;
    return body;
}

// From `low` to `high`, both included, at most LevelStepYards apart.
inline std::vector<float> Levels(float low, float high)
{
    std::vector<float> levels;
    for (float level = low; level < high; level += LevelStepYards)
        levels.push_back(level);
    levels.push_back(high);
    return levels;
}

// The footprint grid: the centre, InnerDirections at half the radius and
// RimDirections on the rim.
template <class Vec>
std::vector<Vec> FootprintOffsets(float radius)
{
    constexpr float TwoPi = 6.28318530717958647692f;
    std::vector<Vec> offsets{ Vec{ 0.0f, 0.0f, 0.0f } };
    for (int k = 0; k < InnerDirections; ++k)
    {
        float const angle = TwoPi * float(k) / float(InnerDirections);
        offsets.push_back(Vec{ 0.5f * radius * std::cos(angle), 0.5f * radius * std::sin(angle), 0.0f });
    }
    for (int k = 0; k < RimDirections; ++k)
    {
        float const angle = TwoPi * float(k) / float(RimDirections);
        offsets.push_back(Vec{ radius * std::cos(angle), radius * std::sin(angle), 0.0f });
    }
    return offsets;
}

enum class Obstruction
{
    None,
    Landing,  // the body at the last point overlaps a surface
    Path      // the body meets a surface on the way there
};

struct Proof
{
    Obstruction Kind = Obstruction::None;
    std::size_t Piece = 0;       // the obstructed piece (Path)
    std::uint32_t Rays = 0;
    bool Clear() const { return Kind == Obstruction::None; }
};

namespace Detail
{
template <class Vec, class Blocked>
bool Ray(Blocked& blocked, std::uint32_t& rays, Vec const& origin, Vec const& direction, float length)
{
    ++rays;
    return length > DegenerateYards && blocked(origin, direction, length);
}

// Radial rays from the axis at (x, y) out to `radius` at every level.
template <class Vec, class Blocked>
bool RadialClear(float x, float y, float low, float high, float radius, Blocked& blocked,
    std::uint32_t& rays)
{
    constexpr float TwoPi = 6.28318530717958647692f;
    for (float const z : Levels(low, high))
        for (int k = 0; k < RimDirections; ++k)
        {
            float const angle = TwoPi * float(k) / float(RimDirections);
            if (Ray(blocked, rays, Vec{ x, y, z }, Vec{ std::cos(angle), std::sin(angle), 0.0f }, radius))
                return false;
        }
    return true;
}

// The column the body fills standing anywhere from feet `low` to feet
// `high` over (x, y).
template <class Vec, class Blocked>
bool ColumnClear(float x, float y, float low, float high, Body const& body, Blocked& blocked,
    std::uint32_t& rays)
{
    Vec const down{ 0.0f, 0.0f, -1.0f };
    float const length = high - low + body.Top - body.Knee;
    for (Vec const& o : FootprintOffsets<Vec>(body.Radius))
        if (Ray(blocked, rays, Vec{ x + o.x, y + o.y, high + body.Top }, down, length))
            return false;
    return RadialClear<Vec>(x, y, low + body.Knee, high + body.Top, body.Radius, blocked, rays);
}

// The footprint grid moved along a non-vertical piece at every level.
template <class Vec, class Blocked>
bool TranslationClear(Vec const& a, Vec const& b, Body const& body, Blocked& blocked,
    std::uint32_t& rays)
{
    float const dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
    float const length = std::sqrt(dx * dx + dy * dy + dz * dz);
    if (!(length > DegenerateYards))
        return true;
    Vec const direction{ dx / length, dy / length, dz / length };
    std::vector<float> const lifts = Levels(body.Knee, body.Top);
    for (Vec const& o : FootprintOffsets<Vec>(body.Radius))
        for (float const lift : lifts)
            if (Ray(blocked, rays, Vec{ a.x + o.x, a.y + o.y, a.z + lift }, direction, length))
                return false;
    return true;
}
}

// The body standing with its feet at `feet`.
template <class Vec, class Blocked>
bool CylinderClear(Vec const& feet, Body const& body, Blocked& blocked, std::uint32_t& rays)
{
    return Detail::ColumnClear<Vec>(feet.x, feet.y, feet.z, feet.z, body, blocked, rays);
}

// `points` are the feet along the trajectory, points[0] where the unit is.
template <class Vec, class Blocked>
Proof ProveTrajectory(std::vector<Vec> const& points, Body const& body, Blocked&& blocked)
{
    Proof proof;
    if (points.size() < 2)
        return proof;
    if (!CylinderClear(points.back(), body, blocked, proof.Rays))
    {
        proof.Kind = Obstruction::Landing;
        proof.Piece = points.size() - 2;
        return proof;
    }
    for (std::size_t i = 0; i + 1 < points.size(); ++i)
    {
        Vec const& a = points[i];
        Vec const& b = points[i + 1];
        float const horizontal = std::hypot(b.x - a.x, b.y - a.y);
        bool clear = true;
        if (horizontal <= VerticalYards)
        {
            Body widened = body;
            widened.Radius += horizontal;
            clear = Detail::ColumnClear<Vec>(a.x, a.y, std::min(a.z, b.z), std::max(a.z, b.z),
                widened, blocked, proof.Rays);
        }
        else
        {
            float const length = std::sqrt(horizontal * horizontal + (b.z - a.z) * (b.z - a.z));
            int const cuts = std::max(1, int(std::ceil(length / LevelStepYards)));
            Vec previous = a;
            for (int s = 1; s <= cuts && clear; ++s)
            {
                float const t = float(s) / float(cuts);
                Vec const next{ a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t };
                clear = Detail::TranslationClear(previous, next, body, blocked, proof.Rays)
                    && CylinderClear(next, body, blocked, proof.Rays);
                previous = next;
            }
        }
        if (!clear)
        {
            proof.Kind = Obstruction::Path;
            proof.Piece = i;
            return proof;
        }
    }
    return proof;
}

// Distance of p from the segment a-b.
template <class Vec>
float OffChord(Vec const& a, Vec const& b, Vec const& p)
{
    float const dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
    float const lengthSq = dx * dx + dy * dy + dz * dz;
    float t = lengthSq > 0.0f
        ? ((p.x - a.x) * dx + (p.y - a.y) * dy + (p.z - a.z) * dz) / lengthSq : 0.0f;
    t = std::clamp(t, 0.0f, 1.0f);
    float const ex = a.x + dx * t - p.x, ey = a.y + dy * t - p.y, ez = a.z + dz * t - p.z;
    return std::sqrt(ex * ex + ey * ey + ez * ez);
}

struct Chords
{
    std::vector<std::size_t> Kept;   // indices into the samples
    float InflationYards = 0.0f;
};

// Greedy chords through `samples` within ChordToleranceYards; the inflation
// (a 3D distance, which MakeBody applies sideways, up and down alike) covers
// the samples' distance from their chord and the curve's bulge
// between consecutive samples: under constant acceleration the curve leaves
// a sample chord by a quarter of how far the middle of three samples lies
// off its neighbours' chord (a straight fall, even where it stops at the
// floor, bulges nowhere; at a knot the estimate only grows).
template <class Vec>
Chords ReduceToChords(std::vector<Vec> const& samples)
{
    Chords chords;
    if (samples.empty())
        return chords;
    float bulge = 0.0f;
    for (std::size_t i = 1; i + 1 < samples.size(); ++i)
        bulge = std::max(bulge, 0.25f * OffChord(samples[i - 1], samples[i + 1], samples[i]));
    float deviation = 0.0f;
    std::size_t anchor = 0;
    chords.Kept.push_back(0);
    while (anchor + 1 < samples.size())
    {
        std::size_t end = anchor + 1;
        float endDeviation = 0.0f;
        for (std::size_t next = end + 1; next < samples.size(); ++next)
        {
            float worst = 0.0f;
            for (std::size_t k = anchor + 1; k < next && worst <= ChordToleranceYards; ++k)
                worst = std::max(worst, OffChord(samples[anchor], samples[next], samples[k]));
            if (worst > ChordToleranceYards)
                break;
            end = next;
            endDeviation = worst;
        }
        deviation = std::max(deviation, endDeviation);
        chords.Kept.push_back(end);
        anchor = end;
    }
    chords.InflationYards = deviation + bulge;
    return chords;
}

// An initialized MoveSpline as the server runs it (ComputePosition over its
// whole duration), every SampleStepMs (coarser for a very long spline) and at
// every knot, in the spline's own frame.
template <class Vec, class Spline>
std::vector<Vec> SampleSpline(Spline const& spline)
{
    std::vector<Vec> samples;
    std::int32_t const duration = spline.Duration();
    if (duration <= 0)
        return samples;
    std::int32_t const step = std::max<std::int32_t>(SampleStepMs,
        std::int32_t(duration / std::int32_t(MaxSamples)) + 1);
    std::vector<std::int32_t> times;
    for (std::int32_t t = 0; t < duration; t += step)
        times.push_back(t);
    times.push_back(duration);
    auto const& knots = spline._Spline();
    for (std::int32_t i = knots.first() + 1; i < knots.last(); ++i)
        times.push_back(knots.length(i));
    std::sort(times.begin(), times.end());
    times.erase(std::unique(times.begin(), times.end()), times.end());
    samples.reserve(times.size());
    for (std::int32_t const t : times)
    {
        auto const p = spline.ComputePosition(t);
        samples.push_back(Vec{ p.x, p.y, p.z });
    }
    return samples;
}
}

#endif
