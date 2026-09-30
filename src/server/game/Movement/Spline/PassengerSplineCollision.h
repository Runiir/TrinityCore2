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

#ifndef TRINITYSERVER_PASSENGER_SPLINE_COLLISION_H
#define TRINITYSERVER_PASSENGER_SPLINE_COLLISION_H

// A transport passenger's server spline against its transport's own model.
//
// A passenger's path is built on the static navmesh (PathGenerator), which
// holds no gameobject model, and WorldObject::UpdateAllowedPositionZ leaves a
// passenger's path heights untouched ("TODO: Allow transports to be part of
// dynamic vmap tree"). MoveSplineInit then moves those world points into the
// transport's frame with no collision test, so a chase or point spline of a
// passenger walks straight through the transport's walls and floors (BWD 10N
// round 2: the rogue and both tanks inside the hollow pillar shafts of the
// Nefarian elevator, GO 207834). A client cannot: its collision stops it at
// the wall.
//
// ClipPath sweeps the emitted path with the body sweep the transport-surface
// executor proves its walks with (BotValidationRouteNativeApproach.h): rays
// along the centre line and at half and the full collision radius on both
// sides, from the knee to 0.9 of the collision height. The body stops its
// collision radius short of the nearest hit, as a client stops at a wall; the
// rays reach that radius past each segment's end, so a short segment cannot
// end with the body in a wall just beyond it. A side ray whose start is
// already behind a surface (a member standing against a wall) says nothing
// about moving on and is skipped; the centre rays still hold. A path dipping
// through a floor or a pillar top ends where the knee ray meets that surface,
// the feet less than the knee height under it (within the executor's own
// floor tolerance for a walk, 0.6 yd); the next spline's knee ray then starts
// just above that surface and meets it at once, so splines launched one after
// another cannot sink step by step.
// The sweep proves the straight segments between the path's points, so a
// swept spline is emitted with linear interpolation (EmitProvedPath).
// The sweep's rays measure along a segment, not across the body (a rising
// segment toward a sloped skirt ends inside it), so what it keeps is then
// proved with the whole body and moved back or refused (PassengerWalkProof.h).
// Pure: the caller supplies the nearest-hit ray query.

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <vector>

namespace Movement::PassengerCollision
{
constexpr float FirstLiftYards = 0.5f;
constexpr float LiftStepYards = 0.35f;
constexpr float SideFractions[] = { 0.0f, 0.5f, -0.5f, 1.0f, -1.0f };
// DEFAULT_PLAYER_BOUNDING_RADIUS.
constexpr float MinBodyRadiusYards = 0.389f;
// Less movement than this is no movement: the spline is not launched.
constexpr float MinMoveYards = 0.1f;
constexpr float DegenerateYards = 1e-4f;

inline std::vector<float> Lifts(float collisionHeight)
{
    float const top = 0.9f * std::max(collisionHeight, 1.0f);
    std::vector<float> lifts;
    for (float lift = FirstLiftYards; lift < top; lift += LiftStepYards)
        lifts.push_back(lift);
    lifts.push_back(top);
    return lifts;
}

enum class Verdict
{
    Clear,    // the path is emitted unchanged
    Clipped,  // the path ends at the first surface in its way
    Blocked   // a surface is in the way at once: nothing is emitted
};

struct Result
{
    Verdict Kind = Verdict::Clear;
    // The kept path: points [0, LastSegment] and then LastSegment's segment
    // up to EndFraction of its length (Clipped only).
    std::size_t LastSegment = 0;
    float EndFraction = 1.0f;
    float KeptYards = 0.0f;
};

// How far the body's centre may travel from `a` toward `b` (at most the
// segment's length) before its collision radius meets the nearest surface.
// The rays search the length plus that radius: a surface just past `b` but
// within the radius of it still stops the body short of `b`.
// `hit(origin, direction, maxDistance)` returns the distance of the nearest
// surface along the unit direction within maxDistance, or a negative value
// for none.
template <class Vec, class Hit>
float SegmentClearance(Vec const& a, Vec const& b, float radius,
    std::vector<float> const& lifts, Hit&& hit)
{
    float const dx = b.x - a.x;
    float const dy = b.y - a.y;
    float const dz = b.z - a.z;
    float const length = std::sqrt(dx * dx + dy * dy + dz * dz);
    if (!(length > DegenerateYards))
        return length;
    Vec const direction{ dx / length, dy / length, dz / length };
    float const horizontal = std::hypot(dx, dy);
    float const search = length + radius;
    float allowed = length;
    for (float const lift : lifts)
    {
        Vec const centre{ a.x, a.y, a.z + lift };
        for (float const side : SideFractions)
        {
            Vec origin = centre;
            if (side != 0.0f)
            {
                if (!(horizontal > DegenerateYards))
                    continue;
                float const offset = std::fabs(side) * radius;
                Vec const outward{ -dy / horizontal * (side > 0.0f ? 1.0f : -1.0f),
                    dx / horizontal * (side > 0.0f ? 1.0f : -1.0f), 0.0f };
                if (hit(centre, outward, offset) >= 0.0f)
                    continue;
                origin = Vec{ centre.x + outward.x * offset, centre.y + outward.y * offset,
                    centre.z };
            }
            float const distance = hit(origin, direction, search);
            if (distance >= 0.0f)
                allowed = std::min(allowed, std::max(0.0f, distance - radius));
        }
    }
    return allowed;
}

// `path` in world coordinates, path[0] the unit's own position.
template <class Vec, class Hit>
Result ClipPath(std::vector<Vec> const& path, float radius, float collisionHeight, Hit&& hit)
{
    Result result;
    if (path.size() < 2)
        return result;
    radius = std::max(radius, MinBodyRadiusYards);
    std::vector<float> const lifts = Lifts(collisionHeight);
    float kept = 0.0f;
    for (std::size_t i = 0; i + 1 < path.size(); ++i)
    {
        Vec const& a = path[i];
        Vec const& b = path[i + 1];
        float const length = std::sqrt((b.x - a.x) * (b.x - a.x) + (b.y - a.y) * (b.y - a.y)
            + (b.z - a.z) * (b.z - a.z));
        float const allowed = SegmentClearance(a, b, radius, lifts, hit);
        if (allowed + DegenerateYards < length)
        {
            kept += allowed;
            result.LastSegment = i;
            result.EndFraction = length > 0.0f ? allowed / length : 0.0f;
            result.KeptYards = kept;
            result.Kind = kept < MinMoveYards ? Verdict::Blocked : Verdict::Clipped;
            return result;
        }
        kept += length;
    }
    result.LastSegment = path.size() - 2;
    result.KeptYards = kept;
    return result;
}

// Applies a Clipped result to the same path in any frame related to the swept
// one by a rigid transform (a passenger's transport-local spline points).
template <class Vec>
void ApplyClip(std::vector<Vec>& path, Result const& result)
{
    if (result.Kind != Verdict::Clipped || result.LastSegment + 1 >= path.size())
        return;
    Vec const a = path[result.LastSegment];
    Vec const b = path[result.LastSegment + 1];
    float const f = result.EndFraction;
    float const tail = f * std::sqrt((b.x - a.x) * (b.x - a.x) + (b.y - a.y) * (b.y - a.y)
        + (b.z - a.z) * (b.z - a.z));
    // A tail shorter than a spline segment may be (MoveSplineInitArgs::
    // _checkPathLengths) ends the path at the last whole point instead.
    if (tail < MinMoveYards && result.LastSegment > 0)
    {
        path.resize(result.LastSegment + 1);
        return;
    }
    path.resize(result.LastSegment + 2);
    path.back() = Vec{ a.x + (b.x - a.x) * f, a.y + (b.y - a.y) * f, a.z + (b.z - a.z) * f };
}

// Emits a swept (Clear or Clipped) spline as proved. ClipPath proves the
// straight segments between the points; a Catmullrom spline through the same
// points is a curve that can leave them (control points (10,0), (0.5,1),
// (0.5,2), (10,3) reach x = -0.6875 between the middle two), so the spline
// is interpolated linearly and the unit walks exactly the proved polyline.
// No further ray is cast. `args` is a MoveSplineInitArgs.
template <class Args>
void EmitProvedPath(Args& args, Result const& result)
{
    ApplyClip(args.path, result);
    args.flags.Catmullrom = false;
}
}

#endif
