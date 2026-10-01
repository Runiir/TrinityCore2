#ifndef TRINITY_BOT_ATRAMEDES_MOVEMENT_POLICY_H
#define TRINITY_BOT_ATRAMEDES_MOVEMENT_POLICY_H

#include "Bots/BotActionArbiter.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesAirGong.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesDodge.h"
#include <optional>
#include <string_view>

// Movement proposals for one bot. Each producer answers one mechanic; the
// strategy keeps the first applicable proposal in its fixed urgency order,
// so a bot submits at most one Atramedes movement per decision.
namespace BotEncounter::Atramedes
{
struct MoveProposal
{
    Vector3 Destination;
    std::string_view Mechanic;
    BotActionArbitration::Priority ActionPriority =
        BotActionArbitration::Priority::Mechanic;
    float Utility = 0.0f;
    // Survival moves own cast/GCD so a hard cast cannot root the escape.
    bool PreemptCasting = false;
};

inline MoveProposal Survival(Vector3 destination, std::string_view mechanic,
    float utility)
{
    return { destination, mechanic, BotActionArbitration::Priority::Survival,
        utility, true };
}

inline MoveProposal Positioning(Vector3 destination, std::string_view mechanic,
    float utility)
{
    return { destination, mechanic, BotActionArbitration::Priority::Mechanic,
        utility, false };
}

inline constexpr float GroundKiteMinRadius = 28.0f;
inline constexpr float GroundKiteMaxRadius = 42.0f;
inline constexpr float KiteStep = 12.0f;
// A Sonic Breath lasts 2 s cast + 6 s channel; a kiter circles the boss at
// ~13 degrees per second, so the beam can only reach players it would sweep
// within that time.
inline constexpr float BeamSweepHorizonRad = 110.0f * Geometry::Pi / 180.0f;
inline constexpr float BeamPadRad = 12.0f * Geometry::Pi / 180.0f;
// A run ahead of the sweep may wait out a disk while the beam is this far
// behind (about 2.5 s of sweep).
inline constexpr float RunAheadHoldRad = 30.0f * Geometry::Pi / 180.0f;

// Centroid of other living players (the kiter and tank excluded).
inline std::optional<Vector3> RaidCentroid(Blackboard const& board,
    ObjectGuid self, ObjectGuid tank)
{
    float x = 0.0f;
    float y = 0.0f;
    uint32 count = 0;
    for (ActorSnapshot const& player : board.Players)
    {
        if (!player.Alive || player.Guid == self || player.Guid == tank)
            continue;
        x += player.Position.X;
        y += player.Position.Y;
        ++count;
    }
    if (!count)
        return std::nullopt;
    return Vector3{ x / float(count), y / float(count), ArenaCenter.Z };
}

// Direction (+1 counter-clockwise, -1 clockwise) that carries `self` around
// `center` away from `away`. Without a reference it is clockwise, the
// direction the guides use.
inline int AwayDirection(Vector3 const& center, Vector3 const& self,
    std::optional<Vector3> const& away)
{
    if (!away || Geometry::Distance2d(center, *away) < 1.0f)
        return -1;
    float const delta = Geometry::AngleDelta(Geometry::Bearing(center, *away),
        Geometry::Bearing(center, self));
    return delta > 0.0f ? -1 : 1;
}

// Sonic Breath kite direction around the boss. The Tracking Flames marker
// follows the kiter in a straight line, so its bearing always trails the
// kiter's: running away from it holds one direction for the whole breath.
// Only while the marker still sits on the kiter (its summon snapshot) does
// the raid side choose (away from the raid centroid, clockwise without one).
inline int GroundKiteDirection(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties, ActorSnapshot const& kiter)
{
    Vector3 const& boss = facts.Boss->Position;
    if (ActorSnapshot const* marker = MarkerOf(facts.TrackingFlames, kiter))
        if (int const away = Geometry::AwayFromChaser(boss, kiter.Position,
                marker->Position))
            return away;
    return AwayDirection(boss, kiter.Position,
        RaidCentroid(board, kiter.Guid, duties.Tank));
}

// Sonic Breath target: circle the boss while the breath is cast or channelled
// so the lagging beam trails behind on the floor already crossed.
inline std::optional<MoveProposal> GroundKiteMove(Blackboard const& board,
    Facts const& facts, DutyPlan const& duties, ActorSnapshot const& self)
{
    if (self.Guid != facts.GroundKiter || !facts.Boss || !facts.SonicBreathActive)
        return std::nullopt;
    Vector3 const& boss = facts.Boss->Position;
    float const radius = std::clamp(Geometry::Distance2d(boss, self.Position),
        GroundKiteMinRadius, GroundKiteMaxRadius);
    int const direction = GroundKiteDirection(board, facts, duties, self);
    // The kite keeps its direction; its radius and stride bend around disk
    // lanes and fire patches on the way (BotAtramedesDodge.h).
    Dodge::Field const field = Dodge::BuildField(board, facts, self, { false, true });
    return Survival(Dodge::ClearCircleStep(field, boss, self.Position, radius, KiteStep, direction,
        GroundKiteMinRadius, GroundKiteMaxRadius), "sonic_breath_kite", 540.0f);
}

// Players the Sonic Breath beam will sweep. The beam points from the boss
// at the Tracking Flames and follows the kiter; those ahead of it within the
// sweep horizon run on with the sweep, those at the beam step back behind it.
inline std::optional<MoveProposal> SonicBreathBeamExit(Blackboard const& board,
    Facts const& facts, DutyPlan const& duties, ActorSnapshot const& self, bool melee = false)
{
    if (!facts.Boss || !facts.SonicBreathActive || facts.TrackingFlames.empty()
        || self.Guid == facts.GroundKiter)
        return std::nullopt;
    Vector3 const& boss = facts.Boss->Position;
    float const radius = Geometry::Distance2d(boss, self.Position);
    if (radius < 1.0f)
        return std::nullopt;
    ActorSnapshot const* kiter = FindLivingPlayer(board, facts.GroundKiter);
    ActorSnapshot const* marker = kiter ? MarkerOf(facts.TrackingFlames, *kiter) : nullptr;
    if (!marker)
        marker = facts.TrackingFlames.front();
    float const beam = Geometry::Bearing(boss, marker->Position);
    // The beam sweeps the way the kiter runs (the same rule the kiter uses).
    int const sweep = kiter ? GroundKiteDirection(board, facts, duties, *kiter) : -1;
    float const offset = Geometry::AngleDelta(Geometry::Bearing(boss, self.Position), beam)
        * float(sweep);
    float const halfWidth = std::tan(SonicBreathHalfAngleRad) * radius + 1.0f
        + HazardMargin + SoundMargin(self);
    float const beamHalfAngle = std::atan2(halfWidth, radius);
    float const z = self.Position.Z;
    if (offset < -beamHalfAngle)
        return std::nullopt;
    // Behind the beam or ahead of it, clear of the disk lanes and fire too;
    // melee and the tank stay inside melee range.
    Dodge::Field const field = Dodge::BuildField(board, facts, self);
    Dodge::Constraint const ring = melee ? Dodge::MeleeRing(facts) : Dodge::Constraint{};
    if (offset <= beamHalfAngle)
        return Survival(Dodge::Resolve(field, self, Geometry::PointAt(boss, beam - float(sweep)
            * (beamHalfAngle + BeamPadRad), radius, z), ring), "sonic_breath_beam_exit",
            520.0f);
    if (offset > BeamSweepHorizonRad)
        return std::nullopt;
    Dodge::Field ahead = field;
    ahead.SonicBreath.reset();
    float const low = ring.RingCenter ? ring.RingMin : std::max(2.0f, radius - 9.0f);
    float const high = ring.RingCenter ? ring.RingMax : radius + 9.0f;
    // Far enough ahead of the sweep, a run that would meet a disk waits.
    bool const mayHold = offset > beamHalfAngle + RunAheadHoldRad;
    return Survival(Dodge::ClearCircleStep(ahead, boss, self.Position, radius,
        KiteStep, sweep, low, high, Mobility::RunSpeed(self), mayHold), "sonic_breath_run_ahead", 515.0f);
}

// A melee player in melee range steps around the boss at its own distance
// (at most the melee slot radius) until the lane is `clearance` to its side:
// it dodges the disk and stays in melee range.
inline Vector3 MeleeLaneExit(Vector3 const& boss, float heading, Vector3 const& self,
    float clearance)
{
    Geometry::RayOffset const offset = Geometry::OffsetFromRay(boss, heading, self);
    float const radius = std::clamp(Geometry::Distance2d(boss, self),
        clearance + 1.5f, MeleeSlotRadius);
    float const angle = std::asin(std::min(1.0f, (clearance + 0.5f) / radius));
    return Geometry::PointAt(boss, heading + float(offset.Side) * angle, radius,
        self.Z);
}

// Sonar Pulse disks leave the boss centre and travel straight out; step
// sideways out of the lane of any disk still heading toward `self` (melee in
// melee range around the boss, see MeleeLaneExit).
inline std::optional<MoveProposal> SonarPulseExit(Blackboard const& board, Facts const& facts,
    ActorSnapshot const& self, bool melee = false)
{
    if (!facts.Boss)
        return std::nullopt;
    Vector3 const& boss = facts.Boss->Position;
    float const clearance = SonarPulseRadius + HazardMargin + SoundMargin(self);
    std::optional<MoveProposal> best;
    float bestAlong = 0.0f;
    for (ActorSnapshot const* disk : facts.SonarPulses)
    {
        if (Geometry::Distance2d(boss, disk->Position) < 2.0f)
        {
            // Not moving yet: only its own footprint is known.
            if (Geometry::Distance2d(disk->Position, self.Position) < clearance)
            {
                best = Survival(Geometry::RadialExit(disk->Position, self.Position,
                    clearance + 1.0f, Geometry::Bearing(boss, ArenaCenter)),
                    "sonar_pulse_exit", 480.0f);
                break;
            }
            continue;
        }
        float const heading = Geometry::Bearing(boss, disk->Position);
        Geometry::RayOffset const offset =
            Geometry::OffsetFromRay(disk->Position, heading, self.Position);
        if (offset.Along < -clearance || offset.Along > 60.0f
            || offset.Lateral >= clearance)
            continue;
        if (!best || offset.Along < bestAlong)
        {
            bestAlong = offset.Along;
            bool const inMelee = melee
                && Geometry::Distance2d(boss, self.Position) <= MeleeRangeYards;
            best = Survival(inMelee
                ? MeleeLaneExit(boss, heading, self.Position, clearance)
                : Geometry::LateralExit(disk->Position, heading, self.Position, clearance),
                inMelee ? "sonar_pulse_melee_exit" : "sonar_pulse_exit", 480.0f);
        }
    }
    // Out of every lane at once (four disks per pulse fan out from the
    // boss), and out of the beam and fire; melee around the boss in range.
    bool const ringed = melee && Geometry::Distance2d(boss, self.Position) <= MeleeRangeYards;
    if (best)
        best->Destination = Dodge::Resolve(Dodge::BuildField(board, facts, self), self,
            best->Destination, ringed ? Dodge::MeleeRing(facts) : Dodge::Constraint{});
    return best;
}

// Out of the nearest footprint, to a point clear of every other hazard too
// (the shortest safe step, BotAtramedesDodge.h): a radial exit alone steps
// from one bomb zone into the next or along a fire trail.
inline std::optional<MoveProposal> NearestFootprintExit(Blackboard const& board, Facts const& facts,
    std::vector<ActorSnapshot const*> const& hazards, ActorSnapshot const& self,
    float clearance, std::string_view mechanic, float utility,
    Dodge::Constraint const& constraint = {}, Dodge::FieldOptions const& options = {})
{
    ActorSnapshot const* nearest = nullptr;
    float nearestDistance = 0.0f;
    for (ActorSnapshot const* hazard : hazards)
    {
        float const distance = Geometry::Distance2d(hazard->Position, self.Position);
        if (distance < clearance && (!nearest || distance < nearestDistance))
        {
            nearest = hazard;
            nearestDistance = distance;
        }
    }
    if (!nearest)
        return std::nullopt;
    Vector3 const radial = Geometry::RadialExit(nearest->Position, self.Position,
        clearance + 1.5f, Geometry::Bearing(nearest->Position, ArenaCenter));
    return Survival(Dodge::Resolve(Dodge::BuildField(board, facts, self, options), self, radial,
        constraint), mechanic, utility);
}

// Out of a Sonar Bomb zone: the radial exit from the nearest marker when it
// is clear and allowed, else the escape that spends the least time in any
// blast (Dodge::BombEscape), never the shortest safe step through a marker.
inline std::optional<MoveProposal> BombMarkerExit(Blackboard const& board, Facts const& facts,
    ActorSnapshot const& self, Dodge::Constraint const& constraint = {},
    Dodge::FieldOptions const& options = {})
{
    float const clearance = Dodge::BombClearYards + SoundMargin(self);
    ActorSnapshot const* nearest = nullptr;
    for (ActorSnapshot const* marker : facts.BombMarkers)
        if (Geometry::Distance2d(marker->Position, self.Position) < clearance
            && (!nearest || Geometry::Distance2d(marker->Position, self.Position)
                < Geometry::Distance2d(nearest->Position, self.Position)))
            nearest = marker;
    if (!nearest)
        return std::nullopt;
    Vector3 const radial = Geometry::RadialExit(nearest->Position, self.Position,
        clearance + 1.5f, Geometry::Bearing(nearest->Position, ArenaCenter));
    Dodge::Field const field = Dodge::BuildField(board, facts, self, options);
    if (Dodge::Usable(field, constraint, radial))
        return Survival(radial, "sonar_bomb_exit", 510.0f);
    if (std::optional<Vector3> const escape = Dodge::BombEscape(field, self, constraint))
        return Survival(*escape, "sonar_bomb_exit", 510.0f);
    return Survival(Dodge::Resolve(field, self, radial, constraint), "sonar_bomb_exit", 510.0f);
}

inline std::optional<MoveProposal> FirePatchExit(Blackboard const& board, Facts const& facts,
    ActorSnapshot const& self, Dodge::Constraint const& constraint = {},
    Dodge::FieldOptions const& options = {})
{
    return NearestFootprintExit(board, facts, facts.FirePatches, self,
        Dodge::PatchClearYards + SoundMargin(self), "roaring_flame_exit", 500.0f, constraint, options);
}

// Bystanders leave the flame and the path it is about to take (toward the
// player it chases, or during a redirect toward the struck shield): a flame
// at ten Building Speed stacks runs 15 yd/s, so a step straight away from it
// along its path is caught.
inline std::optional<MoveProposal> FlameExit(Blackboard const& board, Facts const& facts,
    ActorSnapshot const& self, Dodge::Constraint const& constraint = {})
{
    if (self.Guid == facts.AirKiter || facts.ReverberatingFlames.empty())
        return std::nullopt;
    Dodge::Field const field = Dodge::BuildField(board, facts, self);
    for (Dodge::Capsule const& flame : field.Flames)
        if (Dodge::DistanceToSegment(self.Position, flame.From, flame.To) < flame.Radius)
            return Survival(Dodge::Resolve(field, self, Geometry::RadialExit(flame.From,
                self.Position, flame.Radius + 1.5f, Geometry::Bearing(flame.From, ArenaCenter)),
                constraint), "reverberating_flame_exit", 515.0f);
    return std::nullopt;
}

// Air kite: the next ring waypoint ahead, away from the chasing flame. The
// waypoints lie inside spellclick reach of every shield, so a rescue always
// finds a shield ahead within one waypoint. A run through a Sonar Bomb zone
// or a fire patch takes the least-Sound waypoint instead (BotAtramedesKitePath.h).
inline std::optional<MoveProposal> AirKiteMove(Facts const& facts,
    ActorSnapshot const& self)
{
    if (self.Guid != facts.AirKiter)
        return std::nullopt;
    std::optional<Vector3> const next = KitePath::ChooseWaypoint(facts, self,
        KiterFlame(facts, self), AirKiteDirection(facts, self));
    if (!next)
        return std::nullopt;
    return Survival(*next, "roaring_flame_breath_kite", 540.0f);
}

// The striker of an air gong runs on before the flame comes back for it: the
// flame waits 2 s, flies to the struck shield beside the striker and then
// tracks it, so every yard gained now delays the next catch. Its Sound when
// the flame takes it opens the next chase, so its run avoids the hazards too.
inline std::optional<MoveProposal> AirRedirectRun(Blackboard const& board,
    Facts const& facts, ActorSnapshot const& self)
{
    ActorSnapshot const* runner = AirRedirectRunner(board, facts);
    if (!runner || runner->Guid != self.Guid)
        return std::nullopt;
    std::optional<Vector3> const next = KitePath::ChooseWaypoint(facts, self, nullptr,
        RingDirectionAwayFrom(self.Position, facts.ReverberatingFlames.front()->Position));
    if (!next)
        return std::nullopt;
    // Every waypoint lies on the ring, where earlier chases left their fire
    // trails: the run walks around them (the striker's Sound opens the next
    // chase under the kiter Sound bound).
    return Survival(Dodge::RunnerStep(Dodge::BuildField(board, facts, self), self, *next,
        facts.ReverberatingFlames.front()->Position), "air_redirect_run", 535.0f);
}
}

#endif
