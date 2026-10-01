#ifndef TRINITY_BOT_ATRAMEDES_KITE_PATH_H
#define TRINITY_BOT_ATRAMEDES_KITE_PATH_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesAirGong.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesArenaFloor.h"
#include <algorithm>
#include <cmath>
#include <optional>
#include <vector>

// The air kite path around the shield ring under the kiter Sound bound (user
// decision 2026-09-30; BotAtramedesSoundBound.h). The chased player, and the
// striker running on before the flame re-tracks it, runs to the next ring
// waypoint ahead (NextRingWaypoint) unless that straight run crosses a Sonar
// Bomb zone or a fire patch. Then it takes, among the ring waypoints of the
// next two shields ahead on two lanes, the one whose run gains the least
// expected Sound:
//   Sonar Bomb  +20 for a run through a live marker's 6 yd zone (plus a
//               second per second inside, so a run out of one leaves it
//               soonest);
//   fire patch  +5 per second inside a patch's 3 yd, each patch on its own,
//               and at least half a tick for any crossing;
//   the breath  +3 per 0.5 s the flame would be on the runner before it
//               arrives, from the time to contact on that heading, so that
//               leaving a hazard never hands the kiter to the flame.
// Lanes: the rescue lane (4 yd inside the shield, the ring waypoint) and an
// inner lane 9 yd inside, still within spellclick reach; inner waypoints off
// the hall floor (pillar holes, ArenaFloor::Solid) are skipped. The flame's
// own trail lies behind the kiter, but earlier chases leave theirs on the
// ring (patches outlast the air phase), so later kiters meet them ahead.
namespace BotEncounter::Atramedes::KitePath
{
inline constexpr float InnerLaneInset = 9.0f;
inline constexpr float BombMarginYards = 1.5f;
inline constexpr float PatchMarginYards = 1.0f;
inline constexpr std::size_t ShieldsAhead = 2;

// Ring waypoint of `spawn` for a runner circling in `direction`: `inset` yd
// inside the shield toward the arena centre, then RingWaypointAheadArc onward.
inline Vector3 LaneWaypoint(ShieldSpawn const& spawn, int direction, float inset)
{
    Vector3 const shield{ spawn.X, spawn.Y, spawn.Z };
    Vector3 const inside = Geometry::PointAt(shield, Geometry::Bearing(shield, ArenaCenter),
        inset, ArenaCenter.Z);
    float const radius = std::max(1.0f, Geometry::Distance2d(ArenaCenter, inside));
    return Geometry::PointAt(ArenaCenter, Geometry::Bearing(ArenaCenter, inside)
        + float(direction) * RingWaypointAheadArc / radius, radius, ArenaCenter.Z);
}

// Seconds a straight run from `from` to `to` at `speed` spends within
// `radius` of `center`.
inline float SecondsInside(Vector3 const& from, Vector3 const& to, Vector3 const& center,
    float radius, float speed)
{
    float const dx = to.X - from.X;
    float const dy = to.Y - from.Y;
    float const length = std::sqrt(dx * dx + dy * dy);
    float const fx = from.X - center.X;
    float const fy = from.Y - center.Y;
    if (length < 0.01f)
        return fx * fx + fy * fy <= radius * radius ? 0.25f : 0.0f;
    // |from + s (to - from) - center|^2 = radius^2, s in [0, 1].
    float const a = length * length;
    float const b = 2.0f * (fx * dx + fy * dy);
    float const c = fx * fx + fy * fy - radius * radius;
    // Starting outside and heading away: never inside (the same 0 the roots
    // give, without the square root).
    if (c > 0.0f && b >= 0.0f)
        return 0.0f;
    float const discriminant = b * b - 4.0f * a * c;
    if (discriminant <= 0.0f)
        return 0.0f;
    float const root = std::sqrt(discriminant);
    float const enter = std::max(0.0f, (-b - root) / (2.0f * a));
    float const leave = std::min(1.0f, (-b + root) / (2.0f * a));
    return leave > enter ? (leave - enter) * length / std::max(speed, 0.1f) : 0.0f;
}

// Expected Sound from Sonar Bombs and fire patches on the run to `to`.
inline float HazardSound(Facts const& facts, ActorSnapshot const& self, Vector3 const& to)
{
    float const speed = Mobility::RunSpeed(self);
    float sound = 0.0f;
    for (ActorSnapshot const* bomb : facts.BombMarkers)
        if (float const inside = SecondsInside(self.Position, to, bomb->Position,
                SonarBombRadius + BombMarginYards, speed); inside > 0.0f)
            sound += float(SonarBombSound) + inside;
    for (ActorSnapshot const* patch : facts.FirePatches)
        if (float const inside = SecondsInside(self.Position, to, patch->Position,
                FirePatchRadius + PatchMarginYards, speed); inside > 0.0f)
            sound += float(FirePatchTickSound) * std::max(0.5f, inside / FirePatchTickSeconds);
    return sound;
}

// Expected breath Sound on the run to `to`: the ticks between contact on
// that heading (the run's share of speed away from the flame) and arrival.
inline float BreathSound(ActorSnapshot const& self, ActorSnapshot const* flame, Vector3 const& to)
{
    if (!flame)
        return 0.0f;
    float const speed = Mobility::RunSpeed(self);
    float const run = Geometry::Distance2d(self.Position, to);
    float const gap = Geometry::Distance2d(flame->Position, self.Position);
    float away = 1.0f;
    if (run > 0.01f && gap > 0.01f)
        away = ((to.X - self.Position.X) * (self.Position.X - flame->Position.X)
            + (to.Y - self.Position.Y) * (self.Position.Y - flame->Position.Y)) / (run * gap);
    float const seconds = run / speed;
    float const contact = FlameTimeToContact(*flame, self, speed * away);
    return contact < seconds
        ? float(BreathTickSound) * (seconds - contact) / BreathTickSeconds : 0.0f;
}

// Shield spawns ahead of `self` in `direction`, nearest first (by the bearing
// of their ring waypoint around the arena centre), skipping one whose
// waypoint it stands on; past half a turn the bearing wraps.
inline std::vector<ShieldSpawn const*> SpawnsAhead(Vector3 const& self, int direction,
    std::size_t count)
{
    float const selfBearing = Geometry::Bearing(ArenaCenter, self);
    std::vector<std::pair<float, ShieldSpawn const*>> ahead;
    for (ShieldSpawn const& spawn : ShieldSpawns)
    {
        if (Geometry::Distance2d(self, RingWaypoint(spawn, direction)) <= WaypointArrivalYards
            || Geometry::Distance2d(self, LaneWaypoint(spawn, direction, InnerLaneInset))
                <= WaypointArrivalYards)
            continue;
        float angle = Geometry::AngleDelta(Geometry::Bearing(ArenaCenter,
            RingWaypoint(spawn, direction)), selfBearing) * float(direction);
        if (angle <= 0.0f)
            angle += Geometry::TwoPi;
        ahead.emplace_back(angle, &spawn);
    }
    std::stable_sort(ahead.begin(), ahead.end(),
        [](auto const& left, auto const& right) { return left.first < right.first; });
    std::vector<ShieldSpawn const*> spawns;
    for (std::size_t index = 0; index < ahead.size() && index < count; ++index)
        spawns.push_back(ahead[index].second);
    return spawns;
}

// The kite destination: the next ring waypoint, or the least-Sound
// alternative when that run crosses a bomb zone or a fire patch.
inline std::optional<Vector3> ChooseWaypoint(Facts const& facts, ActorSnapshot const& self,
    ActorSnapshot const* flame, int direction)
{
    std::optional<Vector3> const next = NextRingWaypoint(self.Position, direction);
    if (!next || HazardSound(facts, self, *next) <= 0.0f)
        return next;
    std::optional<Vector3> best = next;
    float bestSound = HazardSound(facts, self, *next) + BreathSound(self, flame, *next);
    for (ShieldSpawn const* spawn : SpawnsAhead(self.Position, direction, ShieldsAhead))
        for (float inset : { ShieldStandInset, InnerLaneInset })
        {
            Vector3 const point = inset == ShieldStandInset ? RingWaypoint(*spawn, direction)
                : LaneWaypoint(*spawn, direction, inset);
            if (inset != ShieldStandInset && !ArenaFloor::Solid(point.X, point.Y))
                continue;
            float const sound = HazardSound(facts, self, point) + BreathSound(self, flame, point);
            if (sound + 0.01f < bestSound)
            {
                best = point;
                bestSound = sound;
            }
        }
    return best;
}
}

#endif
