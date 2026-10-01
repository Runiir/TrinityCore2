#ifndef TRINITY_BOT_ATRAMEDES_DODGE_H
#define TRINITY_BOT_ATRAMEDES_DODGE_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesKitePath.h"
#include <algorithm>
#include <cmath>
#include <optional>
#include <vector>

// Raid-wide dodging (user raid experience 2026-09-30, authoritative: "For
// atramedes ideally everyone is as close to 0 sound as possible, meaning the
// bots dodge everything"). In 10N every Sound source can be avoided
// (Modulation adds none, ledger client_spell_values.modulation):
//   Sonar Pulse disk    +3 per 0.5 s within 5 yd, along a lane from the boss
//   Sonic Breath        +20 per 1 s tick in a 15 degree cone from the boss
//   fire patch          +5 per 1 s within 3 yd, each patch on its own (a
//                       Roaring Flame trail is a band of overlapping patches)
//   Sonar Bomb          +20 within 6 yd where its marker stands
//   Roaring Flame Breath +3 per 0.5 s within 5 yd of the flame
// One hazard field per bot and snapshot holds every one of them. An exit
// keeps its own destination when that point is clear of the whole field;
// otherwise it takes the shortest safe step: the nearest point clear of every
// hazard (on the hall floor, inside the role's constraint: melee range for
// melee and the tank, click reach of its shield for an air relay), with the
// fire it would cross on the way priced in. So an exit never steps from one
// hazard into another, and the step stays short so damage and healing
// resume at once.
namespace BotEncounter::Atramedes
{
inline constexpr float HazardMargin = 2.5f;

// A player close to Devastation keeps a wider berth.
inline float SoundMargin(ActorSnapshot const& self)
{
    return SoundOf(self) >= 60 ? 1.5f : 0.0f;
}
}

namespace BotEncounter::Atramedes::Dodge
{
// The distances the exits trigger at (BombMarkerExit, FirePatchExit,
// FlameExit, SonarPulseExit): a chosen point clears each by SafetyPad more,
// so a bot on it never triggers the exit again.
inline constexpr float BombClearYards = SonarBombRadius + 1.5f;
inline constexpr float PatchClearYards = FirePatchRadius + 1.5f;
inline constexpr float FlameClearYards = FlameBreathRadius + 4.0f;
inline constexpr float LaneClearYards = SonarPulseRadius + HazardMargin;
inline constexpr float LaneReachYards = 60.0f;
inline constexpr float SafetyPad = 0.5f;
// A flame is where it will be within this time too: a bystander steps off
// its path, not along it.
inline constexpr float FlameLeadSeconds = 2.5f;
// The Sonic Breath band a step must stay out of: the cone plus this on both
// sides (the beam turns with its kiter).
inline constexpr float BeamPadRad = 10.0f * Geometry::Pi / 180.0f;
// Path pricing: a second inside fire costs as much as this many yards of
// extra walking (+5 Sound per second per patch), a crossed bomb zone this.
inline constexpr float FireSecondYards = 12.0f;
inline constexpr float BombCrossYards = 15.0f;
inline constexpr float DetourProgressYards = 1.5f;
// Sonar Pulse disks run at 7 yd/s (creature_template 41546 speed_run 1). A
// walk that meets one within DiskHitYards on the way costs DiskMeetYards.
inline constexpr float DiskSpeed = 7.0f;
inline constexpr float DiskHitYards = SonarPulseRadius + 1.0f;
inline constexpr float DiskMeetYards = 30.0f;
// On the melee ring an outer point is worth this much per yard: the disks
// come from the centre, so the outer edge meets them last.
inline constexpr float RingInnerYards = 0.5f;

struct Zone
{
    Vector3 Center;
    float Radius = 0.0f;
    bool Fire = false;
    // A Sonar Bomb marker's zone (BombEscape).
    bool Bomb = false;
};

// A moving Sonar Pulse disk: dangerous from HalfWidth behind it to
// LaneReachYards ahead, HalfWidth to either side.
struct Lane
{
    Vector3 Origin;
    float Heading = 0.0f;
    float HalfWidth = 0.0f;
};

// A flame from where it is to where it will be.
struct Capsule
{
    Vector3 From;
    Vector3 To;
    float Radius = 0.0f;
};

struct Beam
{
    Vector3 Origin;
    float Bearing = 0.0f;
};

struct Field
{
    std::vector<Zone> Zones;
    std::vector<Lane> Lanes;
    std::vector<Capsule> Flames;
    std::optional<Beam> SonicBreath;

    bool Empty() const
    {
        return Zones.empty() && Lanes.empty() && Flames.empty() && !SonicBreath;
    }
};

struct FieldOptions
{
    // The Ice Block bait waits for the flame on purpose; the air kiter's own
    // flame is its kite's business (BotAtramedesKitePath.h).
    bool IgnoreFlames = false;
    // The Sonic Breath kiter keeps the beam behind it by kiting.
    bool IgnoreBeam = false;
};

// How close a snapshot shield must stand to a spawn-table position to be
// that spawn.
inline constexpr float ShieldSpawnMatchYards = 2.0f;

// Where the shield a Resonating Clash names stands. The aura's caster is the
// shield creature's runtime GUID, and native creature loading generates the
// GUID counter independently of the database spawn id
// (ShieldSpawn::SpawnId), so the two counters are never compared. The
// runtime identity resolves the position in two steps:
//   the snapshot     the shield creature itself, by GUID;
//   the GUID's entry a struck shield stops being a spellclick target and
//                    may leave the snapshot (usable shields only are listed
//                    in Facts::Shields); the GUID still carries the creature
//                    entry. Of the spawns of that entry, the ones a usable
//                    shield of the snapshot stands on are not it; if two
//                    are left (entries 42954 and 42956 have two spawns
//                    each), the one nearest the striker is, because the
//                    striker was within click reach of it.
// Nothing is returned for a caster that is no shield of the spawn table.
inline std::optional<Vector3> StruckShieldPosition(Blackboard const& board,
    Facts const& facts, ObjectGuid caster, Vector3 const& striker)
{
    if (caster.IsEmpty())
        return std::nullopt;
    if (ActorSnapshot const* shield = board.FindActor(caster))
        if (IsShieldEntry(shield->Entry))
            return shield->Position;
    std::optional<Vector3> best;
    float bestDistance = 0.0f;
    for (ShieldSpawn const& spawn : ShieldSpawns)
    {
        if (spawn.Entry != caster.GetEntry())
            continue;
        Vector3 const at{ spawn.X, spawn.Y, ArenaCenter.Z };
        bool const usable = std::any_of(facts.Shields.begin(), facts.Shields.end(),
            [&at](ShieldFact const& shield)
            {
                return Geometry::Distance2d(shield.Position, at) <= ShieldSpawnMatchYards;
            });
        if (usable)
            continue;
        float const distance = Geometry::Distance2d(striker, at);
        if (!best || distance < bestDistance)
        {
            best = at;
            bestDistance = distance;
        }
    }
    return best;
}

// Where a flame will be: toward the player it chases, or during a redirect
// toward the struck shield (the latest striker's Resonating Clash names it,
// StruckShieldPosition). A shield that cannot be resolved leaves the flame
// where it is.
inline Vector3 FlameHeadingPoint(Blackboard const& board, Facts const& facts,
    ActorSnapshot const& flame)
{
    if (ActorSnapshot const* kiter = FindLivingPlayer(board, facts.AirKiter))
        if (KiterFlame(facts, *kiter) == &flame)
            return kiter->Position;
    if (ActorSnapshot const* runner = AirRedirectRunner(board, facts))
        if (AuraSnapshot const* clash = FindAura(*runner, AirClashAura))
            if (std::optional<Vector3> const shield = StruckShieldPosition(board, facts,
                    clash->CasterGuid, runner->Position))
                return { shield->X, shield->Y, ArenaCenter.Z };
    return flame.Position;
}

inline Field BuildField(Blackboard const& board, Facts const& facts, ActorSnapshot const& self,
    FieldOptions const& options = {})
{
    Field field;
    float const margin = SoundMargin(self);
    for (ActorSnapshot const* bomb : facts.BombMarkers)
        field.Zones.push_back({ bomb->Position, BombClearYards + margin, false, true });
    for (ActorSnapshot const* patch : facts.FirePatches)
        field.Zones.push_back({ patch->Position, PatchClearYards + margin, true });
    if (facts.Boss)
        for (ActorSnapshot const* disk : facts.SonarPulses)
        {
            // Not moving yet: only its own footprint is known.
            if (Geometry::Distance2d(facts.Boss->Position, disk->Position) < 2.0f)
                field.Zones.push_back({ disk->Position, LaneClearYards + margin, false });
            else
                field.Lanes.push_back({ disk->Position,
                    Geometry::Bearing(facts.Boss->Position, disk->Position), LaneClearYards + margin });
        }
    if (!options.IgnoreFlames)
        for (ActorSnapshot const* flame : facts.ReverberatingFlames)
        {
            if (self.Guid == facts.AirKiter && KiterFlame(facts, self) == flame)
                continue;
            Vector3 const toward = FlameHeadingPoint(board, facts, *flame);
            float const speed = FlameBaseSpeed + FlameSpeedPerStack
                * float(std::min(BuildingSpeedStacks(*flame), BuildingSpeedMaxStacks));
            float const run = std::min(Geometry::Distance2d(flame->Position, toward),
                speed * FlameLeadSeconds);
            Vector3 const to = run > 0.05f ? Geometry::PointAt(flame->Position,
                Geometry::Bearing(flame->Position, toward), run, flame->Position.Z) : flame->Position;
            field.Flames.push_back({ flame->Position, to, FlameClearYards });
        }
    if (!options.IgnoreBeam && facts.Boss && facts.SonicBreathActive
        && self.Guid != facts.GroundKiter && !facts.TrackingFlames.empty())
    {
        ActorSnapshot const* marker = facts.TrackingFlames.front();
        if (ActorSnapshot const* kiter = FindLivingPlayer(board, facts.GroundKiter))
            if (ActorSnapshot const* own = MarkerOf(facts.TrackingFlames, *kiter))
                marker = own;
        field.SonicBreath = Beam{ facts.Boss->Position,
            Geometry::Bearing(facts.Boss->Position, marker->Position) };
    }
    return field;
}

inline float DistanceToSegment(Vector3 const& point, Vector3 const& from, Vector3 const& to)
{
    float const dx = to.X - from.X;
    float const dy = to.Y - from.Y;
    float const length = dx * dx + dy * dy;
    float s = 0.0f;
    if (length > 0.0001f)
        s = std::clamp(((point.X - from.X) * dx + (point.Y - from.Y) * dy) / length, 0.0f, 1.0f);
    Vector3 const nearest{ from.X + s * dx, from.Y + s * dy, point.Z };
    return Geometry::Distance2d(point, nearest);
}

inline bool InBeam(Beam const& beam, Vector3 const& point, float pad)
{
    float const radius = Geometry::Distance2d(beam.Origin, point);
    if (radius < 1.0f)
        return true;
    float const halfWidth = std::tan(SonicBreathHalfAngleRad) * radius + 1.0f + HazardMargin + pad;
    float const offset = std::fabs(Geometry::AngleDelta(Geometry::Bearing(beam.Origin, point),
        beam.Bearing));
    return offset <= std::atan2(halfWidth, radius) + BeamPadRad;
}

inline bool InLane(Lane const& lane, Vector3 const& point, float pad)
{
    Geometry::RayOffset const offset = Geometry::OffsetFromRay(lane.Origin, lane.Heading, point);
    return offset.Along >= -lane.HalfWidth && offset.Along <= LaneReachYards
        && offset.Lateral < lane.HalfWidth + pad;
}

// `point` is clear of every hazard, each by `pad` more than its trigger.
inline bool Clear(Field const& field, Vector3 const& point, float pad = SafetyPad)
{
    for (Zone const& zone : field.Zones)
        if (Geometry::Distance2d(zone.Center, point) < zone.Radius + pad)
            return false;
    for (Lane const& lane : field.Lanes)
        if (InLane(lane, point, pad))
            return false;
    for (Capsule const& flame : field.Flames)
        if (DistanceToSegment(point, flame.From, flame.To) < flame.Radius + pad)
            return false;
    return !(field.SonicBreath && InBeam(*field.SonicBreath, point, pad));
}

// Yards-equivalent cost of the straight walk: fire seconds and bomb zones
// crossed on the way (the destination itself is clear).
inline float PathCost(Field const& field, Vector3 const& from, Vector3 const& to, float speed)
{
    float cost = 0.0f;
    // Zones the walk's bounding box (widened by the largest radius) misses
    // cost nothing: skipped without the circle test.
    float const reach = std::max(FirePatchRadius + 0.5f, SonarBombRadius);
    float const minX = std::min(from.X, to.X) - reach;
    float const maxX = std::max(from.X, to.X) + reach;
    float const minY = std::min(from.Y, to.Y) - reach;
    float const maxY = std::max(from.Y, to.Y) + reach;
    for (Zone const& zone : field.Zones)
    {
        if (zone.Center.X < minX || zone.Center.X > maxX || zone.Center.Y < minY || zone.Center.Y > maxY)
            continue;
        float const inside = KitePath::SecondsInside(from, to, zone.Center,
            zone.Fire ? FirePatchRadius + 0.5f : SonarBombRadius, speed);
        if (inside > 0.0f)
            cost += zone.Fire ? inside * FireSecondYards : BombCrossYards;
    }
    return cost;
}

// The straight walk from `from` to `to` crosses no fire patch and no Sonar Bomb
// zone: the one predicate every walk that must not go through fire shares
// (DetourPoint, RunnerStep, ClearCircleStep). A clear destination alone says
// nothing about the chord that reaches it.
inline bool PathClear(Field const& field, Vector3 const& from, Vector3 const& to, float speed)
{
    return PathCost(field, from, to, speed) <= 0.0f;
}

// The straight walk from `from` to `to` at `speed` meets no moving Sonar
// Pulse disk within DiskHitYards (each disk keeps its heading at DiskSpeed).
// Lanes are radial, so a walk around the boss crosses them: it is safe when
// it crosses ahead of or behind the disk, not into it.
inline bool DiskSafeWalk(Field const& field, Vector3 const& from, Vector3 const& to, float speed)
{
    float const length = Geometry::Distance2d(from, to);
    float const seconds = length / std::max(speed, 0.1f);
    for (Lane const& lane : field.Lanes)
        for (float t = 0.0f; t <= seconds + 0.001f; t += 0.1f)
        {
            float const share = length > 0.01f ? std::min(1.0f, speed * t / length) : 1.0f;
            Vector3 const walker{ from.X + (to.X - from.X) * share, from.Y + (to.Y - from.Y) * share, from.Z };
            if (Geometry::Distance2d(walker, Geometry::PointAt(lane.Origin, lane.Heading,
                    DiskSpeed * t, from.Z)) < DiskHitYards)
                return false;
        }
    return true;
}

// Where a step may end.
struct Constraint
{
    // Melee and the tank on the ground: this far from the boss centre.
    std::optional<Vector3> RingCenter;
    float RingMin = 0.0f;
    float RingMax = 0.0f;
    // An air relay: within this 3D reach of its shield.
    std::optional<Vector3> Anchor;
    float AnchorReach = 0.0f;

    bool Allows(Vector3 const& point) const
    {
        if (RingCenter)
        {
            float const radius = Geometry::Distance2d(*RingCenter, point);
            if (radius < RingMin - 0.01f || radius > RingMax + 0.01f)
                return false;
        }
        if (Anchor)
        {
            Vector3 const at{ point.X, point.Y, ArenaFloor::OnFloor(point).Z };
            if (Geometry::Distance3d(at, *Anchor) > AnchorReach)
                return false;
        }
        return true;
    }
};

inline bool Usable(Field const& field, Constraint const& constraint, Vector3 const& point)
{
    return constraint.Allows(point) && ArenaFloor::Solid(point.X, point.Y) && Clear(field, point);
}

// The shortest safe step from `self`: the clear, allowed point with the
// least walk plus path cost (and, as a tie-break, the nearest to `home`, the
// bot's slot or station, so it does not drift). Nothing when no candidate
// within 24 yd is clear.
inline std::optional<Vector3> SafeStep(Field const& field, ActorSnapshot const& self,
    Constraint const& constraint, std::optional<Vector3> const& home = std::nullopt)
{
    float const speed = Mobility::RunSpeed(self);
    Vector3 const& from = self.Position;
    std::optional<Vector3> best;
    float bestScore = 0.0f;
    auto consider = [&](Vector3 const& point)
    {
        // Every other term is at least 0 (the ring term at least -0.005): a
        // candidate whose walk alone reaches the best score cannot win, so
        // the costly checks are skipped (the choice is unchanged).
        float const walk = Geometry::Distance2d(from, point);
        if (best && walk - 0.01f >= bestScore)
            return;
        if (!Usable(field, constraint, point))
            return;
        float score = walk + PathCost(field, from, point, speed)
            + (home ? 0.25f * Geometry::Distance2d(point, *home) : 0.0f);
        if (!DiskSafeWalk(field, from, point, speed))
            score += DiskMeetYards;
        if (constraint.RingCenter)
            score += RingInnerYards * (constraint.RingMax - Geometry::Distance2d(*constraint.RingCenter, point));
        if (!best || score < bestScore)
        {
            best = point;
            bestScore = score;
        }
    };
    if (constraint.RingCenter)
    {
        // Around the boss at melee distances, up to half a turn either way.
        float const bearing = Geometry::Bearing(*constraint.RingCenter, from);
        for (float radius : { constraint.RingMax, (constraint.RingMin + constraint.RingMax) / 2.0f,
                 constraint.RingMin })
            for (int step = 0; step <= 45; ++step)
                for (int side : { 1, -1 })
                    consider(Geometry::PointAt(*constraint.RingCenter,
                        bearing + float(side * step) * 4.0f * Geometry::Pi / 180.0f, radius, from.Z));
        return best;
    }
    for (float radius : { 1.5f, 3.0f, 4.5f, 6.0f, 7.5f, 9.0f, 10.5f, 12.0f, 14.0f, 16.0f, 18.0f, 21.0f, 24.0f })
        for (int step = 0; step < 32; ++step)
            consider(Geometry::PointAt(from, float(step) * Geometry::TwoPi / 32.0f, radius, from.Z));
    return best;
}

// Sonar Bomb escape (round 4; live r03 batch 1: bombs landed on a gong
// relay and on the striker the redirected flame re-tracks, whose first chase
// sample was then 20 Sound). A marker is summoned on a random player and its
// bomb lands 2.5 s later (+20 Sound within 6 yd, from any Sound), so a bot in
// a bomb zone leaves every bomb blast by the walk that spends the least time
// inside one: straight out, never through a marker toward some other goal.
// The walk heading is a fixed 32-way grid from the bot, and the best one out
// of a single blast is the radial one, so successive snapshots keep one
// heading (the round-3 relay step and redirect run switched between points on
// both sides of the marker and stayed inside). Seconds inside a blast weigh
// most; an end the rest of the field covers, or one outside the constraint
// (a relay's click reach), costs BombEscapeCoveredYards; then the shorter
// walk, fire crossed and the distance to `home`.
// A second inside a blast is worth BombSecondYards of walking (+20 Sound,
// priced as fire: FireSecondYards per +5).
inline constexpr float BombSecondYards = FireSecondYards * 4.0f;
inline constexpr float BombEscapeCoveredYards = 15.0f;

// `point` stands in a Sonar Bomb zone (the trigger BombMarkerExit uses).
inline bool InBombZone(Field const& field, Vector3 const& point)
{
    for (Zone const& zone : field.Zones)
        if (zone.Bomb && Geometry::Distance2d(zone.Center, point) < zone.Radius)
            return true;
    return false;
}

// How far a walk from `from` along `heading` goes before it leaves `center`'s
// circle of `radius` (0 when `from` is outside it).
inline float ExitAlong(Vector3 const& from, float heading, Vector3 const& center, float radius)
{
    float const px = from.X - center.X;
    float const py = from.Y - center.Y;
    float const c = px * px + py * py - radius * radius;
    if (c >= 0.0f)
        return 0.0f;
    float const b = px * std::cos(heading) + py * std::sin(heading);
    return -b + std::sqrt(b * b - c);
}

inline std::optional<Vector3> BombEscape(Field const& field, ActorSnapshot const& self,
    Constraint const& constraint = {}, std::optional<Vector3> const& home = std::nullopt)
{
    if (!InBombZone(field, self.Position))
        return std::nullopt;
    float const speed = Mobility::RunSpeed(self);
    Vector3 const& from = self.Position;
    std::optional<Vector3> best;
    float bestScore = 0.0f;
    for (int step = 0; step < 32; ++step)
    {
        float const heading = float(step) * Geometry::TwoPi / 32.0f;
        // Out of every bomb zone on the way (overlapping zones chain).
        float run = 0.0f;
        for (int pass = 0; pass < 4; ++pass)
        {
            Vector3 const at = Geometry::PointAt(from, heading, run, from.Z);
            float further = run;
            for (Zone const& zone : field.Zones)
                if (zone.Bomb)
                    further = std::max(further, run + ExitAlong(at, heading, zone.Center,
                        zone.Radius + SafetyPad));
            if (further <= run + 0.01f)
                break;
            run = further + 0.05f;
        }
        Vector3 const point = Geometry::PointAt(from, heading, run, from.Z);
        if (!ArenaFloor::Solid(point.X, point.Y) || InBombZone(field, point))
            continue;
        float blast = 0.0f;
        for (Zone const& zone : field.Zones)
            if (zone.Bomb)
                blast += KitePath::SecondsInside(from, point, zone.Center, SonarBombRadius, speed);
        float score = BombSecondYards * blast + run + PathCost(field, from, point, speed)
            + (home ? 0.25f * Geometry::Distance2d(point, *home) : 0.0f);
        if (!Clear(field, point))
            score += BombEscapeCoveredYards;
        if (!constraint.Allows(point))
            score += BombEscapeCoveredYards;
        if (!best || score < bestScore)
        {
            best = point;
            bestScore = score;
        }
    }
    return best;
}

// An exit's own destination when it is clear and allowed, else the shortest
// safe step, else the exit's destination after all.
inline Vector3 Resolve(Field const& field, ActorSnapshot const& self, Vector3 const& exit,
    Constraint const& constraint = {}, std::optional<Vector3> const& home = std::nullopt)
{
    if (Usable(field, constraint, exit))
        return exit;
    std::optional<Vector3> const step = SafeStep(field, self, constraint, home);
    return step ? *step : exit;
}

// Melee and the tank dodge on the ground inside melee range (user raid
// experience 2026-09-25: melee at maximum melee range to dodge the rings).
inline Constraint MeleeRing(Facts const& facts)
{
    Constraint constraint;
    if (facts.Boss && facts.CurrentPhase == Phase::Ground)
    {
        constraint.RingCenter = facts.Boss->Position;
        constraint.RingMax = MeleeRangeYards - 1.25f;
        constraint.RingMin = constraint.RingMax - 4.0f;
    }
    return constraint;
}

// The next point of a walk to `destination` (a slot, a relay station, a
// shield): the destination while the straight walk crosses no fire or bomb
// zone, else the nearby clear point that the walk reaches without crossing
// any and that leaves the least way on (a trail is walked around, not
// through). Each detour point gains DetourProgressYards on the destination,
// so two snapshots never send the walker back and forth. Nothing when no
// such point exists.
inline std::optional<Vector3> DetourPoint(Field const& field, ActorSnapshot const& self,
    Vector3 const& destination)
{
    float const speed = Mobility::RunSpeed(self);
    if (PathClear(field, self.Position, destination, speed))
        return destination;
    float const remaining = Geometry::Distance2d(self.Position, destination);
    std::optional<Vector3> best;
    float bestScore = 0.0f;
    for (float radius : { 4.0f, 8.0f, 12.0f })
        for (int step = 0; step < 32; ++step)
        {
            Vector3 const point = Geometry::PointAt(self.Position,
                float(step) * Geometry::TwoPi / 32.0f, radius, self.Position.Z);
            // Cheapest test first; a point whose walk and way on alone reach
            // the best score cannot win (the choice is unchanged).
            float const left = Geometry::Distance2d(point, destination);
            if (left > remaining - DetourProgressYards || (best && radius + left >= bestScore)
                || !ArenaFloor::Solid(point.X, point.Y) || !Clear(field, point, 0.0f)
                || !PathClear(field, self.Position, point, speed))
                continue;
            float const score = radius + left + 0.5f * PathCost(field, point, destination, speed);
            if (!best || score < bestScore)
            {
                best = point;
                bestScore = score;
            }
        }
    return best;
}

// The next point of a walk that must go on (the redirect runner, a striker
// walking to its shield): the clear nearby point, gaining
// DetourProgressYards, or the destination itself, whichever prices least
// (walk plus fire and bomb zones crossed now, plus half of those still
// ahead), so fire that cannot be walked around is crossed where it is
// thinnest.
inline Vector3 LeastCostStep(Field const& field, ActorSnapshot const& self, Vector3 const& destination)
{
    float const speed = Mobility::RunSpeed(self);
    float const remaining = Geometry::Distance2d(self.Position, destination);
    Vector3 best = destination;
    float bestScore = remaining + PathCost(field, self.Position, destination, speed);
    for (float radius : { 4.0f, 8.0f, 12.0f })
        for (int step = 0; step < 32; ++step)
        {
            Vector3 const point = Geometry::PointAt(self.Position,
                float(step) * Geometry::TwoPi / 32.0f, radius, self.Position.Z);
            // As in DetourPoint: cheapest first, and radius plus the way on
            // bounds the score from below.
            float const left = Geometry::Distance2d(point, destination);
            if (left > remaining - DetourProgressYards || radius + left >= bestScore
                || !ArenaFloor::Solid(point.X, point.Y) || !Clear(field, point, 0.0f))
                continue;
            float const score = radius + PathCost(field, self.Position, point, speed)
                + left + 0.5f * PathCost(field, point, destination, speed);
            if (score < bestScore)
            {
                best = point;
                bestScore = score;
            }
        }
    return best;
}

// The redirect runner's step toward its kite waypoint (the striker the flame
// will track next: its Sound opens the next chase under the kiter Sound
// bound, so fire costs more than distance gained). Out of a bomb zone first;
// then a detour around the fire
// when one exists; else, standing clear, the clear point nearest the
// waypoint reached without crossing fire and no closer to the flame, or
// holding; else, standing in fire, the least-cost step out.
inline Vector3 RunnerStep(Field const& field, ActorSnapshot const& self, Vector3 const& waypoint,
    Vector3 const& flame)
{
    // In a bomb zone the runner leaves it first (BombEscape): a bomb that
    // lands on it opens the next chase at 20 Sound.
    if (std::optional<Vector3> const escape = BombEscape(field, self, {}, waypoint))
        return *escape;
    if (std::optional<Vector3> const detour = DetourPoint(field, self, waypoint))
        return *detour;
    if (!Clear(field, self.Position, 0.0f))
        return LeastCostStep(field, self, waypoint);
    float const speed = Mobility::RunSpeed(self);
    float const fromFlame = Geometry::Distance2d(self.Position, flame);
    Vector3 best = self.Position;
    float bestLeft = Geometry::Distance2d(self.Position, waypoint);
    for (float radius : { 3.0f, 6.0f, 9.0f })
        for (int step = 0; step < 32; ++step)
        {
            Vector3 const point = Geometry::PointAt(self.Position,
                float(step) * Geometry::TwoPi / 32.0f, radius, self.Position.Z);
            float const left = Geometry::Distance2d(point, waypoint);
            if (left >= bestLeft || Geometry::Distance2d(point, flame) < fromFlame - 0.5f
                || !ArenaFloor::Solid(point.X, point.Y) || !Clear(field, point, 0.0f)
                || !PathClear(field, self.Position, point, speed))
                continue;
            best = point;
            bestLeft = left;
        }
    return best;
}

// A circling step's segment from `from` to `to` ends somewhere usable: clear
// of the whole field, on the hall floor, and reached without meeting a moving
// Sonar Pulse disk (DiskSafeWalk).
inline bool SegmentEndUsable(Field const& field, Vector3 const& from, Vector3 const& to, float speed)
{
    return Clear(field, to, 0.0f) && ArenaFloor::Solid(to.X, to.Y)
        && DiskSafeWalk(field, from, to, speed);
}

// The one predicate for a circling step, whichever candidate it is: a usable
// end (SegmentEndUsable) and a chord that crosses no fire patch or Sonar Bomb
// zone (PathClear). A clear end is not enough: the walk to it is fire too (+5
// Sound per second per patch).
inline bool SafeSegment(Field const& field, Vector3 const& from, Vector3 const& to, float speed)
{
    return SegmentEndUsable(field, from, to, speed) && PathClear(field, from, to, speed);
}

// A circling step (the Sonic Breath kite, a run ahead of its sweep) that
// avoids the rest of the field: the first SafeSegment, the plain step first,
// then at about the same arc length on nearby radii within [minRadius,
// maxRadius]; every candidate is judged by the same predicate.
// No such step: with `mayHold` (a run ahead: the beam is still behind),
// standing still while that is clear; else the usable-ended step that crosses
// the least fire and bomb (PathCost); else the plain step.
inline Vector3 ClearCircleStep(Field const& field, Vector3 const& center, Vector3 const& self,
    float radius, float arc, int direction, float minRadius, float maxRadius,
    float speed = Mobility::BaseRunSpeed, bool mayHold = false)
{
    std::optional<Vector3> crossing;
    float crossingCost = 0.0f;
    // True: a step to take at once. A usable-ended step that crosses fire is
    // kept as the fallback when it crosses the least.
    auto taken = [&](Vector3 const& point)
    {
        if (SafeSegment(field, self, point, speed))
            return true;
        if (SegmentEndUsable(field, self, point, speed))
        {
            float const cost = PathCost(field, self, point, speed);
            if (!crossing || cost < crossingCost)
            {
                crossing = point;
                crossingCost = cost;
            }
        }
        return false;
    };
    Vector3 const plain = Geometry::TangentialStep(center, self, radius, arc, direction);
    if (taken(plain))
        return plain;
    for (float shift : { 0.0f, 3.0f, -3.0f, 6.0f, -6.0f, 9.0f, -9.0f })
        for (float step : { arc, arc * 1.5f, arc * 0.66f, arc * 0.33f })
        {
            float const r = radius + shift;
            if (r < minRadius || r > maxRadius)
                continue;
            Vector3 const point = Geometry::TangentialStep(center, self, r, step, direction);
            if (taken(point))
                return point;
        }
    if (mayHold && Clear(field, self, 0.0f))
        return self;
    return crossing ? *crossing : plain;
}
}

#endif
