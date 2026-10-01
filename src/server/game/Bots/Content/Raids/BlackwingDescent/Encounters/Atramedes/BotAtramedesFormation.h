#ifndef TRINITY_BOT_ATRAMEDES_FORMATION_H
#define TRINITY_BOT_ATRAMEDES_FORMATION_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesMovementPolicy.h"
#include <optional>

// Standing positions: the gong owner's shield, the tank anchor drag, melee
// at maximum melee range behind the boss and the ranged/healer arc on the
// ground; in the air the relay stations (in reach of a shield and, for the
// ranged ones, in range of the hovering boss) and the spread ring.
namespace BotEncounter::Atramedes
{
inline constexpr float RangedArcRadius = 32.0f;
inline constexpr float HealerArcRadius = 26.0f;
inline constexpr float ArcSpacingRad = 18.0f * Geometry::Pi / 180.0f;
inline constexpr float GroundSlotTolerance = 7.0f;
inline constexpr float HoldSlotTolerance = 4.0f;
inline constexpr float HealerAirTolerance = 12.0f;
inline constexpr float AirRingInner = 17.0f;
inline constexpr float AirRingOuter = 25.0f;
inline constexpr float TankAnchorTolerance = 14.0f;
// Melee slots behind the boss (away from the tank), this far apart, held
// within MeleeSlotTolerance.
inline constexpr float MeleeSpacingRad = 20.0f * Geometry::Pi / 180.0f;
inline constexpr float MeleeSlotTolerance = 1.5f;
inline constexpr float TankDragOvershoot = 10.0f;
// The tank holds Atramedes from maximum melee range like melee do (user raid
// tactic 2026-09-30: everyone dodges everything): every Sonar Pulse disk
// leaves the boss centre, so a tank close to it has no time to leave a lane.
// It backs out once it is this far inside the melee slot radius.
inline constexpr float TankRangeSlack = 2.5f;
// Melee walking to their slot go around the boss, never through its centre
// (the disk lanes converge and the Sonic Breath cone starts there).
inline constexpr float MeleeDetourStepRad = 40.0f * Geometry::Pi / 180.0f;

inline std::optional<std::size_t> IndexOf(std::vector<ObjectGuid> const& order,
    ObjectGuid guid)
{
    auto itr = std::find(order.begin(), order.end(), guid);
    if (itr == order.end())
        return std::nullopt;
    return std::size_t(itr - order.begin());
}

// Arc slot `index` of `count`, centred on the bearing from `center` toward
// the arena centre (west when `center` is the centre itself).
inline Vector3 ArcSlot(Vector3 const& center, std::size_t index, std::size_t count,
    float radius)
{
    float facing = Geometry::Pi;
    if (Geometry::Distance2d(center, ArenaCenter) > 5.0f)
        facing = Geometry::Bearing(center, ArenaCenter);
    float const offset = (float(index) - float(count - 1) / 2.0f) * ArcSpacingRad;
    return Geometry::PointAt(center, facing + offset, radius, ArenaCenter.Z);
}

inline bool FootprintClear(Facts const& facts, Vector3 const& point)
{
    for (ActorSnapshot const* marker : facts.BombMarkers)
        if (Geometry::Distance2d(marker->Position, point) < SonarBombRadius + 1.5f)
            return false;
    for (ActorSnapshot const* patch : facts.FirePatches)
        if (Geometry::Distance2d(patch->Position, point) < FirePatchRadius + 1.5f)
            return false;
    for (ActorSnapshot const* flame : facts.ReverberatingFlames)
        if (Geometry::Distance2d(flame->Position, point) < FlameBreathRadius + 5.0f)
            return false;
    return true;
}

// Air: one spread slot per roster member (ten 36-degree sectors, >= 10 yd
// apart) with an outer alternate 8 yd further out, the "two spots" the
// guides move between to leave Sonar Bomb markers.
inline std::optional<Vector3> AirSlot(Facts const& facts, DutyPlan const& duties,
    ActorSnapshot const& self)
{
    std::optional<std::size_t> const index = IndexOf(duties.RosterOrder, self.Guid);
    if (!index)
        return std::nullopt;
    float const base = (float(*index) + 0.5f) * Geometry::TwoPi
        / float(std::max<std::size_t>(duties.RosterOrder.size(), 1));
    for (float shift : { 0.0f, 0.3f, -0.3f, 0.6f, -0.6f })
        for (float radius : { AirRingInner, AirRingOuter })
        {
            Vector3 const slot = Geometry::PointAt(ArenaCenter, base + shift,
                radius, ArenaCenter.Z);
            if (FootprintClear(facts, slot))
                return slot;
        }
    return Geometry::PointAt(ArenaCenter, base, AirRingInner, ArenaCenter.Z);
}

// A point clear of every fire patch (the static ground hazard).
inline bool FireFree(Facts const& facts, Vector3 const& point)
{
    for (ActorSnapshot const* patch : facts.FirePatches)
        if (Geometry::Distance2d(patch->Position, point) < Dodge::PatchClearYards + Dodge::SafetyPad)
            return false;
    return true;
}

// `slot` on its circle around `center`, or the nearest point along the
// circle (and, with `radialShift`, that much in or out) clear of fire.
inline Vector3 FireFreeSlot(Facts const& facts, Vector3 const& center, Vector3 const& slot,
    float radialShift = 0.0f)
{
    if (FireFree(facts, slot))
        return slot;
    float const bearing = Geometry::Bearing(center, slot);
    float const radius = Geometry::Distance2d(center, slot);
    for (int step = 1; step <= 10; ++step)
        for (int side : { 1, -1 })
            for (float shift : { 0.0f, -radialShift, radialShift })
            {
                Vector3 const point = Geometry::PointAt(center,
                    bearing + float(side * step) * 6.0f * Geometry::Pi / 180.0f,
                    std::max(1.0f, radius + shift), slot.Z);
                if (FireFree(facts, point) && ArenaFloor::Solid(point.X, point.Y))
                    return point;
            }
    return slot;
}

// A relay this much beyond click reach of its shield is still "at" it.
inline constexpr float RelayNearYards = 6.0f;

// Click reach of an air relay's shield, for its dodges.
inline Dodge::Constraint RelayReach(ShieldFact const& shield)
{
    Dodge::Constraint constraint;
    constraint.Anchor = shield.Position;
    constraint.AnchorReach = ShieldClickDistance - RelayStationTolerance;
    return constraint;
}

// An air relay that a Sonar Bomb zone, fire patch or the flame's path
// reaches takes the shortest safe step that keeps its own shield in click
// reach (BotAtramedesDodge.h), nearest its station, instead of stepping away
// from it: the kiter Sound bound needs its strike at the catch.
inline std::optional<MoveProposal> RelayHazardStep(Blackboard const& board,
    Facts const& facts, DutyPlan const& duties, ActorSnapshot const& self)
{
    if (facts.CurrentPhase != Phase::Air || self.Guid == facts.AirKiter)
        return std::nullopt;
    std::optional<ShieldFact> const relay = AirRelayShieldFor(board, facts, duties, self.Guid);
    if (!relay)
        return std::nullopt;
    // Near its shield only: a relay walking to a new station far away
    // takes the ordinary exits and walks around the fire (WalkPoint).
    if (Geometry::Distance3d(self.Position, relay->Position) > ShieldClickDistance + RelayNearYards)
        return std::nullopt;
    Dodge::Field const field = Dodge::BuildField(board, facts, self);
    if (Dodge::Clear(field, self.Position, 0.0f))
        return std::nullopt;
    Vector3 const station = AirStationFor(facts, *relay);
    // In a bomb zone: out of every blast soonest, in reach when that costs
    // no more (Dodge::BombEscape); the shortest safe step can cross a marker.
    std::optional<Vector3> step = Dodge::BombEscape(field, self, RelayReach(*relay), station);
    if (!step)
        step = Dodge::SafeStep(field, self, RelayReach(*relay), station);
    if (!step && StationHazardFree(facts, station))
        step = station;
    if (!step)
        return std::nullopt;
    return Survival(*step, "air_relay_hazard_step", 512.0f);
}

// Ground standby of the gong owner. Until this ground phase's Searing Flame
// is spent (or while the schedule is unknown): beside the shield nearest the
// tank anchor that is not an air relay shield, so that strike keeps the few
// in-range relay shields for the air. Afterwards, while the boss stays in
// spell range: at the first air relay station, so the next air phase's first
// catch has a relay in reach from the flame's spawn on.
inline std::optional<MoveProposal> GongStandby(Facts const& facts,
    DutyPlan const& duties, ActorSnapshot const& self)
{
    if (self.Guid != duties.GongOwner)
        return std::nullopt;
    bool const searingPending = facts.SearingFlameChannel || facts.SearingFlameInMs
        || !facts.GroundTimersPublished;
    std::vector<ShieldFact> const relays = RelayShields(facts);
    if (!searingPending && !relays.empty() && facts.Boss)
    {
        Vector3 const station = AirStationFor(facts, relays.front());
        if (Geometry::Distance3d(station, facts.Boss->Position) + RelayStationTolerance
                <= RangedEnvelope - RelayRangeMargin)
        {
            if (Geometry::Distance2d(station, self.Position) <= RelayStationTolerance)
                return std::nullopt;
            return Positioning(station, "gong_owner_air_standby", 320.0f);
        }
    }
    std::optional<ShieldFact> const shield = GroundDutyShield(facts);
    if (!shield)
        return std::nullopt;
    Vector3 const stand = ShieldStandPoint(*shield);
    if (Geometry::Distance2d(stand, self.Position) <= HoldSlotTolerance)
        return std::nullopt;
    return Positioning(stand, "gong_owner_standby", 320.0f);
}

// Ground: once Atramedes stands at the anchor, the tank backs out to the
// melee slot radius along its own bearing from him (he stays put: the tank
// is still inside his melee range).
inline std::optional<MoveProposal> TankMaxRange(Facts const& facts, ActorSnapshot const& self)
{
    if (facts.CurrentPhase != Phase::Ground || !facts.Boss || facts.Boss->VictimGuid != self.Guid)
        return std::nullopt;
    Vector3 const& boss = facts.Boss->Position;
    if (Geometry::Distance2d(boss, TankAnchor) > TankAnchorTolerance
        || Geometry::Distance2d(boss, self.Position) >= MeleeSlotRadius - TankRangeSlack)
        return std::nullopt;
    // On top of him: toward the arena centre, the side the anchor drag ends
    // on (the ranged arc faces it too), so melee keep the far side.
    float bearing = Geometry::Pi;
    if (Geometry::Distance2d(boss, self.Position) > 1.0f)
        bearing = Geometry::Bearing(boss, self.Position);
    else if (Geometry::Distance2d(boss, ArenaCenter) > 1.0f)
        bearing = Geometry::Bearing(boss, ArenaCenter);
    return Positioning(FireFreeSlot(facts, boss, Geometry::PointAt(boss, bearing, MeleeSlotRadius,
        ArenaCenter.Z)), "tank_max_range", 300.0f);
}

// Ground: drag Atramedes onto the anchor. He follows his victim until the
// tank is inside his 20 yd combat reach, so the tank stands past the anchor.
inline std::optional<MoveProposal> TankAnchorDrag(Facts const& facts,
    ActorSnapshot const& self)
{
    if (facts.CurrentPhase != Phase::Ground || !facts.Boss
        || facts.Boss->VictimGuid != self.Guid)
        return std::nullopt;
    Vector3 const& boss = facts.Boss->Position;
    if (Geometry::Distance2d(boss, TankAnchor) <= TankAnchorTolerance)
        return std::nullopt;
    Vector3 const target = Geometry::PointAt(TankAnchor,
        Geometry::Bearing(boss, TankAnchor), TankDragOvershoot, ArenaCenter.Z);
    if (Geometry::Distance2d(target, self.Position) <= 3.0f)
        return std::nullopt;
    return Positioning(target, "tank_anchor_drag", 300.0f);
}

// The tank is still dragging Atramedes onto the anchor (the pull, and every
// landing west of the centre): he is grounded, on the living tank and
// outside the anchor tolerance, so he is walking.
inline bool AnchorDragInProgress(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties)
{
    if (facts.CurrentPhase != Phase::Ground || !facts.Boss || duties.Tank.IsEmpty()
        || facts.Boss->VictimGuid != duties.Tank || !FindLivingPlayer(board, duties.Tank))
        return false;
    return Geometry::Distance2d(facts.Boss->Position, TankAnchor) > TankAnchorTolerance;
}

// Ground melee slot: MeleeSlotRadius from the boss centre (just inside melee
// range), behind him as seen from the tank, melee in GUID order (dead
// included, so slots do not shift).
inline std::optional<Vector3> MeleeSlot(Blackboard const& board, Facts const& facts,
    DutyPlan const& duties, ActorSnapshot const& self)
{
    if (!facts.Boss)
        return std::nullopt;
    std::vector<ObjectGuid> order;
    for (ActorSnapshot const& player : board.Players)
        if (IsMelee(player) && player.Guid != duties.Tank)
            order.push_back(player.Guid);
    std::sort(order.begin(), order.end());
    std::optional<std::size_t> const index = IndexOf(order, self.Guid);
    if (!index)
        return std::nullopt;
    Vector3 const& boss = facts.Boss->Position;
    float behind = Geometry::Bearing(ArenaCenter, boss);
    if (ActorSnapshot const* tank = FindLivingPlayer(board, duties.Tank))
        if (Geometry::Distance2d(tank->Position, boss) > 1.0f)
            behind = Geometry::Bearing(tank->Position, boss);
    float const offset = (float(*index) - float(order.size() - 1) / 2.0f) * MeleeSpacingRad;
    return FireFreeSlot(facts, boss, Geometry::PointAt(boss, behind + offset, MeleeSlotRadius,
        ArenaCenter.Z));
}

// The next point toward a melee slot: the slot itself, or, when the straight
// walk would cut inside the dodge ring (through the boss centre), a point on
// the melee slot circle at most MeleeDetourStepRad around toward it.
inline Vector3 MeleeWalkPoint(Vector3 const& boss, Vector3 const& self, Vector3 const& slot)
{
    float const inner = MeleeSlotRadius - 4.0f;
    if (Dodge::DistanceToSegment(boss, self, slot) >= inner - 0.5f)
        return slot;
    float const from = Geometry::Bearing(boss, self);
    float const delta = Geometry::AngleDelta(Geometry::Bearing(boss, slot), from);
    float const turn = std::clamp(delta, -MeleeDetourStepRad, MeleeDetourStepRad);
    return Geometry::PointAt(boss, from + turn, MeleeSlotRadius, slot.Z);
}

// A formation walk around fire and bomb zones (a Roaring Flame trail is a
// band of overlapping patches, each +5 Sound a second): the next clear
// point of the detour (Dodge::DetourPoint), or nothing, when no detour
// exists and the bot stands clear, so it holds.
inline std::optional<Vector3> WalkPoint(Blackboard const& board, Facts const& facts,
    ActorSnapshot const& self, Vector3 const& destination)
{
    Dodge::Field const field = Dodge::BuildField(board, facts, self);
    if (std::optional<Vector3> const next = Dodge::DetourPoint(field, self, destination))
        return next;
    if (Dodge::Clear(field, self.Position, 0.0f))
        return std::nullopt;
    return destination;
}

inline std::optional<MoveProposal> FormationMove(Blackboard const& board,
    Facts const& facts, DutyPlan const& duties, ActorSnapshot const& self, bool tank,
    bool melee)
{
    if (facts.CurrentPhase == Phase::Air)
    {
        if (self.Guid == facts.AirKiter)
            return std::nullopt;
        // The gong owner (and the backup, when a second station is in range)
        // waits at a relay station: in reach of a shield and in spell range
        // of the hovering boss, so a strike is at hand without losing damage.
        if (std::optional<ShieldFact> const relay =
                AirRelayShieldFor(board, facts, duties, self.Guid))
        {
            // Off a Sonar Bomb zone or fire patch covering the station, but
            // still in reach of the relay shield (AirStationFor).
            Vector3 const station = AirStationFor(facts, *relay);
            if (Geometry::Distance2d(station, self.Position) <= RelayStationTolerance)
                return std::nullopt;
            std::optional<Vector3> const next = WalkPoint(board, facts, self, station);
            if (!next)
                return std::nullopt;
            return Positioning(*next, StationInRange(station) ? "air_relay_station"
                : "air_relay_station_out_of_range", 300.0f);
        }
        std::optional<Vector3> const slot = AirSlot(facts, duties, self);
        // Healers keep slack so native healing movement can reach the kiter.
        float const tolerance = self.Role == "healer" ? HealerAirTolerance
            : HoldSlotTolerance;
        if (!slot || Geometry::Distance2d(*slot, self.Position) <= tolerance)
            return std::nullopt;
        std::optional<Vector3> const next = WalkPoint(board, facts, self, *slot);
        if (!next)
            return std::nullopt;
        // Melee and the tank cannot reach a flying boss; their slot keeps
        // them spread instead of under him (offense is suppressed as well).
        return Positioning(*next, melee || tank ? "air_phase_hold"
            : "air_phase_spread", 260.0f);
    }
    // The pull is left to native combat: everyone targets the boss and the
    // tank's threat takes him. Only the ground phase has fixed spots.
    if (facts.CurrentPhase != Phase::Ground)
        return std::nullopt;
    if (tank)
    {
        if (std::optional<MoveProposal> drag = TankAnchorDrag(facts, self))
            return drag;
        return TankMaxRange(facts, self);
    }
    if (melee)
    {
        // During the drag the slot "behind him as seen from the tank" is the
        // trailing side of a boss walking ~7.8 yd/s toward the tank, 20 yd
        // back: r01 (blackwing_descent_10n-r01-553da85c98) melee flipped to
        // it at the pull and lost 6-15 s of swings before he stopped at the
        // anchor. Native melee chase keeps contact until he settles; the
        // hazard exits above still apply.
        if (AnchorDragInProgress(board, facts, duties))
            return std::nullopt;
        std::optional<Vector3> const slot = MeleeSlot(board, facts, duties, self);
        if (!slot || Geometry::Distance2d(*slot, self.Position) <= MeleeSlotTolerance)
            return std::nullopt;
        std::optional<Vector3> const next = WalkPoint(board, facts, self,
            MeleeWalkPoint(facts.Boss->Position, self.Position, *slot));
        if (!next)
            return std::nullopt;
        return Positioning(*next, "melee_max_range", 250.0f);
    }
    std::optional<std::size_t> const index = IndexOf(duties.RangedOrder, self.Guid);
    if (!index)
        return std::nullopt;
    float const radius = self.Role == "healer" ? HealerArcRadius : RangedArcRadius;
    Vector3 const slot = FireFreeSlot(facts, facts.Boss->Position, ArcSlot(facts.Boss->Position,
        *index, duties.RangedOrder.size(), radius), 4.0f);
    if (Geometry::Distance2d(slot, self.Position) <= GroundSlotTolerance)
        return std::nullopt;
    std::optional<Vector3> const next = WalkPoint(board, facts, self, slot);
    if (!next)
        return std::nullopt;
    return Positioning(*next, "ranged_arc", 240.0f);
}
}

#endif
