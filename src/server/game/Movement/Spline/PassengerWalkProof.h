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

#ifndef TRINITYSERVER_PASSENGER_WALK_PROOF_H
#define TRINITYSERVER_PASSENGER_WALK_PROOF_H

// The whole body along a passenger's swept walk or chase spline.
//
// ClipPath (PassengerSplineCollision.h) ends a path a radius short of the
// first hit of rays cast along each segment. Those rays measure along the
// segment, not across the body: walking up the ring toward a pillar skirt of
// the Nefarian elevator (BWD 10N round 3, transport-local (33.2555, -0.0625,
// 1.4060) toward (34.7555, -0.0625, 2.1166)) the clipped end (34.5815,
// -0.0625, 2.0341) left 0.044 yd of the body in the skirt: the stop distance
// on a rising segment shrinks by its slope, and a skirt sloped between the
// ray levels comes nearer still.
//
// SettleWalk proves the kept path with the body cylinder of
// PassengerBodyTrajectory.h (knee to head, at the ProofBody radius) and
// moves its end back until it is proved, or refuses:
// - each piece: the footprint grid (centre, 8 at half the radius, 16 on the
//   rim) swept along the whole piece at every LevelStepYards from the knee
//   to the head (one ray per offset and level, whatever its length: the
//   union of ProveTrajectory's per-cut translations), vertical footprint
//   columns from the head to the knee at every ColumnStepYards along it
//   (surfaces parallel to a level walk between two ray levels), and the full
//   cylinder at its end (every knot and the terminal body);
// - an obstructed piece: its end is moved back BackOffYards at a time
//   (BackOffSteps), then bisected (BisectSteps) between its start and the
//   nearest obstructed end, and the longest proved prefix is kept (only a
//   proved end is ever kept); with nothing proved the path ends at the
//   piece's start, a proved knot, or is refused (Blocked) when that is the
//   unit's own position or leaves less than MinMoveYards.
// A unit whose own body already overlaps a surface (it stands in it) may
// still walk out, never further in: in the first piece a ray from the
// trailing half of the footprint whose origin is behind a surface as seen
// from the body's axis says nothing about moving on and is skipped, as
// ClipPath's side rays are; the leading half, the knots and the terminal
// body are proved in full, so the walk ends clear or not at all.
// Cost, 6 levels at a 2.03 yd collision height: 150 + 121 rays per piece and
// 25 per ColumnStepYards of it (a clear 20-yard level walk: 1,696); an
// obstructed piece at most 11 more piece proofs. Randomized walks around
// the elevator's pillars: about 690 rays per launch on average, 5,100 at
// most, against the sweep's 56 (tests/test_passenger_walk_body_clearance.py).
// ProveWalk is the launch's whole proof (ClipPath, then SettleWalk). A path
// that moves nothing (a facing: Unit::SetFacingTo* launches a spline from where
// the unit stands to where it stands) skips both: it has no translation to
// prove, casts no ray, and is never refused, however the body overlaps a wall.
// Model-only and pure, as ClipPath: the caller supplies the ray query.

#include "PassengerBodyTrajectory.h"
#include "PassengerSplineCollision.h"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <vector>

namespace Movement::PassengerWalk
{
namespace Body = Movement::BodyTrajectory;
namespace Collision = Movement::PassengerCollision;

constexpr float ColumnStepYards = Body::LevelStepYards;
constexpr float BackOffYards = 0.1f;
constexpr int BackOffSteps = 4;
constexpr int BisectSteps = 6;
// Added to the circumscribing radius (ProofBody).
constexpr float MarginYards = 0.02f;
// A path none of whose points lies farther than this from its first moves
// nothing (a millimetre: below every ray spacing and the proof's margin; the
// world-to-transport round trip of a standing unit's own position is an order
// of magnitude under it). Horizontal and vertical motion count alike.
constexpr float StationaryYards = Body::VerticalYards;

// The rays run through the vertices of a RimDirections-gon: proved at the
// radius of the polygon circumscribing the body (a flat surface cutting the
// body's circle leaves a vertex on its far side, so a ray meets it), plus
// MarginYards for what lies between two ray levels or across a triangle's
// edge.
inline Body::Body ProofBody(Body::Body body)
{
    constexpr float HalfStep = 3.14159265358979f / float(Body::RimDirections);
    body.Radius = body.Radius / std::cos(HalfStep) + MarginYards;
    return body;
}

struct Settled
{
    Collision::Result Clip;      // what is emitted: Clear, Clipped or Blocked
    std::uint32_t Rays = 0;      // the body proof's rays (ProveWalk: not the sweep's)
    std::uint32_t PieceProofs = 0;
    bool BackedOff = false;      // the proof moved the end back
    bool Escape = false;         // the unit's own body overlapped a surface
    // ProveWalk: the path moves nothing, nothing was cast or proved.
    bool Stationary = false;
    // ProveWalk: the sweep (ClipPath) itself refused the path, SweepYards
    // being how far it would have let it go.
    bool SweepBlocked = false;
    float SweepYards = 0.0f;
};

namespace Detail
{
template <class Vec>
Vec Lerp(Vec const& a, Vec const& b, float t)
{
    return Vec{ a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t };
}

template <class Vec>
float Distance(Vec const& a, Vec const& b)
{
    return std::sqrt((b.x - a.x) * (b.x - a.x) + (b.y - a.y) * (b.y - a.y) + (b.z - a.z) * (b.z - a.z));
}

// The footprint grid swept from `a` to `b` at every level. `buried`: a ray
// from the trailing half of the footprint (moving away from its offset)
// whose origin is behind a surface as seen from the axis is skipped; the
// leading half is never skipped, so the body does not go further in.
template <class Vec, class Blocked>
bool Translation(Vec const& a, Vec const& b, Body::Body const& body, Blocked& blocked,
    std::uint32_t& rays, bool buried)
{
    float const length = Distance(a, b);
    if (!(length > Body::DegenerateYards))
        return true;
    Vec const direction{ (b.x - a.x) / length, (b.y - a.y) / length, (b.z - a.z) / length };
    std::vector<Vec> const offsets = Body::FootprintOffsets<Vec>(body.Radius);
    for (float const lift : Body::Levels(body.Knee, body.Top))
    {
        Vec const centre{ a.x, a.y, a.z + lift };
        for (Vec const& o : offsets)
        {
            float const reach = std::hypot(o.x, o.y);
            if (buried && o.x * direction.x + o.y * direction.y < 0.0f
                && Body::Detail::Ray(blocked, rays, centre, Vec{ o.x / reach, o.y / reach, 0.0f }, reach))
                continue;
            if (Body::Detail::Ray(blocked, rays, Vec{ centre.x + o.x, centre.y + o.y, centre.z }, direction, length))
                return false;
        }
    }
    return true;
}

// Vertical footprint columns, head to knee, at every ColumnStepYards
// strictly between `a` and `b` (the end's own cylinder covers `b`).
template <class Vec, class Blocked>
bool Columns(Vec const& a, Vec const& b, Body::Body const& body, Blocked& blocked, std::uint32_t& rays)
{
    int const cuts = int(std::ceil(Distance(a, b) / ColumnStepYards));
    if (cuts < 2)
        return true;
    std::vector<Vec> const offsets = Body::FootprintOffsets<Vec>(body.Radius);
    Vec const down{ 0.0f, 0.0f, -1.0f };
    for (int s = 1; s < cuts; ++s)
    {
        Vec const p = Lerp(a, b, float(s) / float(cuts));
        for (Vec const& o : offsets)
            if (Body::Detail::Ray(blocked, rays, Vec{ p.x + o.x, p.y + o.y, p.z + body.Top }, down,
                body.Top - body.Knee))
                return false;
    }
    return true;
}

// The body walking the straight piece from `a` (where it stands, not
// re-proved) to `b`, and standing at `b`.
template <class Vec, class Blocked>
bool PieceClear(Vec const& a, Vec const& b, Body::Body const& body, Blocked& blocked,
    std::uint32_t& rays, bool buried)
{
    if (std::hypot(b.x - a.x, b.y - a.y) <= Body::VerticalYards)
    {
        if (buried)
            return Body::CylinderClear(b, body, blocked, rays);
        Body::Body widened = body;
        widened.Radius += std::hypot(b.x - a.x, b.y - a.y);
        return Body::Detail::ColumnClear<Vec>(a.x, a.y, std::min(a.z, b.z), std::max(a.z, b.z), widened,
            blocked, rays);
    }
    return Translation(a, b, body, blocked, rays, buried)
        && (buried || Columns(a, b, body, blocked, rays))
        && Body::CylinderClear(b, body, blocked, rays);
}

// The largest t in (0, 1) with the piece a -> a + (b - a) t proved and at
// least MinMoveYards long, or 0: fine steps back from the end, then a
// bisection below the nearest obstructed end.
template <class Vec, class Blocked>
float BackOff(Vec const& a, Vec const& b, Body::Body const& body, Blocked& blocked, Settled& settled,
    bool buried)
{
    float const length = Distance(a, b);
    if (!(length > Collision::MinMoveYards))
        return 0.0f;
    auto proved = [&](float t)
    {
        ++settled.PieceProofs;
        return PieceClear(a, Lerp(a, b, t), body, blocked, settled.Rays, buried);
    };
    float const shortest = Collision::MinMoveYards / length;
    float failed = 1.0f;
    for (int k = 1; k <= BackOffSteps; ++k)
    {
        float const t = 1.0f - float(k) * BackOffYards / length;
        if (t < shortest)
            return 0.0f;
        if (proved(t))
            return t;
        failed = t;
    }
    float good = 0.0f;
    for (int k = 0; k < BisectSteps; ++k)
    {
        float const t = 0.5f * (good + failed);
        if (t < shortest)
            break;
        if (proved(t))
            good = t;
        else
            failed = t;
    }
    return good;
}
}

// `path` is the swept path in world coordinates (path[0] the unit's own
// position) and `clip` ClipPath's verdict on it. Returns what may be
// emitted, in the same terms (ApplyClip applies it to the path in any
// rigidly related frame): the kept path unchanged when the body is proved
// along it, else ended at its longest proved prefix, else Blocked.
// `blocked(origin, unitDirection, length)` is true for any surface within
// length.
template <class Vec, class Blocked>
Settled SettleWalk(std::vector<Vec> const& path, Collision::Result const& clip, Body::Body body,
    Blocked&& blocked)
{
    Settled settled;
    settled.Clip = clip;
    if (clip.Kind == Collision::Verdict::Blocked)
        return settled;
    body = ProofBody(body);
    std::vector<Vec> kept = path;
    Collision::ApplyClip(kept, clip);
    if (kept.size() < 2)
    {
        settled.Clip.Kind = Collision::Verdict::Blocked;
        return settled;
    }
    // A kept piece i is path segment i up to `scale` of its length.
    bool const clippedTail = clip.Kind == Collision::Verdict::Clipped && kept.size() == clip.LastSegment + 2;
    auto scale = [&](std::size_t i) { return clippedTail && i == clip.LastSegment ? clip.EndFraction : 1.0f; };
    bool buried = false;
    float walked = 0.0f;
    for (std::size_t i = 0; i + 1 < kept.size(); ++i)
    {
        Vec const& a = kept[i];
        Vec const& b = kept[i + 1];
        ++settled.PieceProofs;
        bool clear = Detail::PieceClear(a, b, body, blocked, settled.Rays, false);
        if (!clear && i == 0 && !Body::CylinderClear(a, body, blocked, settled.Rays))
        {
            buried = true;
            settled.Escape = true;
            ++settled.PieceProofs;
            clear = Detail::PieceClear(a, b, body, blocked, settled.Rays, true);
        }
        float const length = Detail::Distance(a, b);
        if (clear)
        {
            walked += length;
            continue;
        }
        settled.BackedOff = true;
        float const t = Detail::BackOff(a, b, body, blocked, settled, buried && i == 0);
        Collision::Result& result = settled.Clip;
        if (t > 0.0f)
        {
            result.Kind = Collision::Verdict::Clipped;
            result.LastSegment = i;
            result.EndFraction = t * scale(i);
            result.KeptYards = walked + t * length;
        }
        else if (i > 0)
        {
            // The piece's start is a knot, proved as the previous piece's end.
            result.Kind = Collision::Verdict::Clipped;
            result.LastSegment = i - 1;
            result.EndFraction = 1.0f;
            result.KeptYards = walked;
        }
        else
            result.KeptYards = 0.0f;
        if (result.KeptYards < Collision::MinMoveYards || !(t > 0.0f || i > 0))
            result.Kind = Collision::Verdict::Blocked;
        return settled;
    }
    return settled;
}

// True when every point of `path` (two or more, in any one rigid frame:
// distances do not depend on it) lies within StationaryYards of the first,
// in all three axes. A facing (Unit::SetFacingTo*) launches such a path: from
// where the unit stands to where it stands, to turn it. NaN is not stationary.
template <class Vec>
bool IsStationary(std::vector<Vec> const& path)
{
    if (path.size() < 2)
        return false;
    for (std::size_t i = 1; i < path.size(); ++i)
        if (!(Detail::Distance(path[0], path[i]) <= StationaryYards))
            return false;
    return true;
}

// The whole proof of a passenger's swept spline (path[0] the unit's own
// position, in world coordinates): the sweep (ClipPath) and then the body
// along what it keeps (SettleWalk), as MoveSplineInit launches it.
// A path that moves nothing (IsStationary: an orientation-only spline) has no
// translation to prove and casts no ray: a unit whose body already overlaps a
// surface (standing in it) must still be able to turn, and a turn must not
// cost the body proof's 121 rays (a facing precedes nearly every cast). It
// is emitted as it is. Any motion, a facing that also corrects the unit's
// position by more than StationaryYards included, is swept and proved in full.
// `hit` is ClipPath's nearest-hit query and `blocked` SettleWalk's boolean ray.
template <class Vec, class Hit, class Blocked>
Settled ProveWalk(std::vector<Vec> const& path, float radius, float collisionHeight, Hit&& hit,
    Blocked&& blocked)
{
    Settled settled;
    if (IsStationary(path))
    {
        settled.Stationary = true;
        return settled;
    }
    Collision::Result const sweep = Collision::ClipPath(path, radius, collisionHeight, hit);
    if (sweep.Kind == Collision::Verdict::Blocked)
    {
        settled.Clip = sweep;
        settled.SweepBlocked = true;
        settled.SweepYards = sweep.KeptYards;
        return settled;
    }
    settled = SettleWalk(path, sweep, Body::MakeBody(radius, collisionHeight), blocked);
    settled.SweepYards = sweep.KeptYards;
    return settled;
}
}

#endif
