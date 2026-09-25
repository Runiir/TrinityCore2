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
        Vector3 const station = AirStationPoint(relays.front());
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
    return Geometry::PointAt(boss, behind + offset, MeleeSlotRadius, ArenaCenter.Z);
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
            Vector3 const station = AirStationPoint(*relay);
            if (Geometry::Distance2d(station, self.Position) <= RelayStationTolerance)
                return std::nullopt;
            return Positioning(station, StationInRange(station) ? "air_relay_station"
                : "air_relay_station_out_of_range", 300.0f);
        }
        std::optional<Vector3> const slot = AirSlot(facts, duties, self);
        // Healers keep slack so native healing movement can reach the kiter.
        float const tolerance = self.Role == "healer" ? HealerAirTolerance
            : HoldSlotTolerance;
        if (!slot || Geometry::Distance2d(*slot, self.Position) <= tolerance)
            return std::nullopt;
        // Melee and the tank cannot reach a flying boss; their slot keeps
        // them spread instead of under him (offense is suppressed as well).
        return Positioning(*slot, melee || tank ? "air_phase_hold"
            : "air_phase_spread", 260.0f);
    }
    // The pull is left to native combat: everyone targets the boss and the
    // tank's threat takes him. Only the ground phase has fixed spots.
    if (facts.CurrentPhase != Phase::Ground)
        return std::nullopt;
    if (tank)
        return TankAnchorDrag(facts, self);
    if (melee)
    {
        std::optional<Vector3> const slot = MeleeSlot(board, facts, duties, self);
        if (!slot || Geometry::Distance2d(*slot, self.Position) <= MeleeSlotTolerance)
            return std::nullopt;
        return Positioning(*slot, "melee_max_range", 250.0f);
    }
    std::optional<std::size_t> const index = IndexOf(duties.RangedOrder, self.Guid);
    if (!index)
        return std::nullopt;
    float const radius = self.Role == "healer" ? HealerArcRadius : RangedArcRadius;
    Vector3 const slot = ArcSlot(facts.Boss->Position, *index,
        duties.RangedOrder.size(), radius);
    if (Geometry::Distance2d(slot, self.Position) <= GroundSlotTolerance)
        return std::nullopt;
    return Positioning(slot, "ranged_arc", 240.0f);
}
}

#endif
