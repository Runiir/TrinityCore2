#ifndef TRINITY_BOT_ATRAMEDES_MOVEMENT_POLICY_H
#define TRINITY_BOT_ATRAMEDES_MOVEMENT_POLICY_H

#include "Bots/BotActionArbiter.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesGongPolicy.h"
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
inline constexpr float HazardMargin = 2.5f;
// A Sonic Breath lasts 2 s cast + 6 s channel; a kiter circles the boss at
// ~13 degrees per second, so the beam can only reach players it would sweep
// within that time.
inline constexpr float BeamSweepHorizonRad = 110.0f * Geometry::Pi / 180.0f;
inline constexpr float BeamPadRad = 12.0f * Geometry::Pi / 180.0f;

inline float SoundMargin(ActorSnapshot const& self)
{
    return SoundOf(self) >= 60 ? 1.5f : 0.0f;
}

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
    return Survival(Geometry::TangentialStep(boss, self.Position, radius,
        KiteStep, direction), "sonic_breath_kite", 540.0f);
}

// Players the Sonic Breath beam will sweep. The beam points from the boss
// at the Tracking Flames and follows the kiter; those ahead of it within the
// sweep horizon run on with the sweep, those at the beam step back behind it.
inline std::optional<MoveProposal> SonicBreathBeamExit(Blackboard const& board,
    Facts const& facts, DutyPlan const& duties, ActorSnapshot const& self)
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
    if (offset <= beamHalfAngle)
        return Survival(Geometry::PointAt(boss, beam - float(sweep)
            * (beamHalfAngle + BeamPadRad), radius, z), "sonic_breath_beam_exit",
            520.0f);
    if (offset > BeamSweepHorizonRad)
        return std::nullopt;
    return Survival(Geometry::TangentialStep(boss, self.Position, radius,
        KiteStep, sweep), "sonic_breath_run_ahead", 515.0f);
}

// Sonar Pulse disks leave the boss centre and travel straight out; step
// sideways out of the lane of any disk still heading toward `self`.
inline std::optional<MoveProposal> SonarPulseExit(Facts const& facts,
    ActorSnapshot const& self)
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
                return Survival(Geometry::RadialExit(disk->Position, self.Position,
                    clearance + 1.0f, Geometry::Bearing(boss, ArenaCenter)),
                    "sonar_pulse_exit", 480.0f);
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
            best = Survival(Geometry::LateralExit(disk->Position, heading,
                self.Position, clearance), "sonar_pulse_exit", 480.0f);
        }
    }
    return best;
}

inline std::optional<MoveProposal> NearestFootprintExit(
    std::vector<ActorSnapshot const*> const& hazards, ActorSnapshot const& self,
    float clearance, std::string_view mechanic, float utility)
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
    return Survival(Geometry::RadialExit(nearest->Position, self.Position,
        clearance + 1.5f, Geometry::Bearing(nearest->Position, ArenaCenter)),
        mechanic, utility);
}

inline std::optional<MoveProposal> BombMarkerExit(Facts const& facts,
    ActorSnapshot const& self)
{
    return NearestFootprintExit(facts.BombMarkers, self,
        SonarBombRadius + 1.5f + SoundMargin(self), "sonar_bomb_exit", 510.0f);
}

inline std::optional<MoveProposal> FirePatchExit(Facts const& facts,
    ActorSnapshot const& self)
{
    return NearestFootprintExit(facts.FirePatches, self,
        FirePatchRadius + 1.5f + SoundMargin(self), "roaring_flame_exit", 500.0f);
}

inline std::optional<MoveProposal> FlameExit(Facts const& facts,
    ActorSnapshot const& self)
{
    if (self.Guid == facts.AirKiter)
        return std::nullopt;
    return NearestFootprintExit(facts.ReverberatingFlames, self,
        FlameBreathRadius + 4.0f, "reverberating_flame_exit", 515.0f);
}

// Waypoints of the air kite: every shield spawn pulled toward the arena
// centre, so the kiter passes each shield inside spellclick reach and lays
// its fire trail along the outer edge.
inline Vector3 RingWaypoint(ShieldSpawn const& spawn)
{
    Vector3 const shield{ spawn.X, spawn.Y, spawn.Z };
    return Geometry::PointAt(shield, Geometry::Bearing(shield, ArenaCenter),
        ShieldStandInset, ArenaCenter.Z);
}

inline std::optional<MoveProposal> AirKiteMove(Facts const& facts,
    ActorSnapshot const& self)
{
    if (self.Guid != facts.AirKiter)
        return std::nullopt;
    float const selfBearing = Geometry::Bearing(ArenaCenter, self.Position);
    int const direction = AirKiteDirection(facts, self);
    // Next ring waypoint at least KiteStep of arc ahead in `direction`.
    std::optional<Vector3> best;
    float bestAhead = 0.0f;
    for (ShieldSpawn const& spawn : ShieldSpawns)
    {
        Vector3 const waypoint = RingWaypoint(spawn);
        float const radius = std::max(1.0f, Geometry::Distance2d(ArenaCenter, waypoint));
        float ahead = Geometry::AngleDelta(Geometry::Bearing(ArenaCenter, waypoint),
            selfBearing) * float(direction);
        if (ahead < 0.0f)
            ahead += Geometry::TwoPi;
        if (ahead * radius < KiteStep)
            continue;
        if (!best || ahead < bestAhead)
        {
            best = waypoint;
            bestAhead = ahead;
        }
    }
    if (!best)
        return std::nullopt;
    return Survival(*best, "roaring_flame_breath_kite", 540.0f);
}
}

#endif
