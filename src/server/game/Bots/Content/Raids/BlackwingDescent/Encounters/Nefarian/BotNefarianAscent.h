#ifndef TRINITY_BOT_NEFARIAN_ASCENT_H
#define TRINITY_BOT_NEFARIAN_ASCENT_H

// The phase 2 pillar ascent and the phase 3 descent, one step per decision.
//
// Ascent (user raid experience 2026-09-26; geometry in BotNefarianMagma.h):
// 1. While the floor is up, each member walks to its pillar's foot on its
//    slot heading (PillarBase, the ordinary floor legs).
// 2. The floor sinks under the magma. Once the member's feet are
//    FloatDepthYards under the surface it floats: it stops standing on the
//    platform, as a client that starts swimming does (Float).
// 3. It swims to its swim station beside the wall, at the float depth (Swim),
//    and holds there while the platform goes down past it.
// 4. When the platform has stopped at the lowered stop, the pillar top is
//    0.286 yards above the surface. The member jumps from the station onto
//    the rim just above the waterline (Hop, the client's jump), boards the
//    platform there (Board) and walks up to its slot on the flat top.
// A swimmer that the rising floor reaches (a late floater when phase 3
// raises the platform) boards it where it stands.
//
// Descent (phase 3): Nefarian's Shadow of Cowardice (79355, every 2 s once
// he has landed) punishes any passenger above local z 9.5. Once the floor is
// back at the raised stop, a member on a pillar walks out to the rim, steps
// off past the wall, falls 7-8 yards onto the skirt or the ring (under the
// 14.57-yard fall-damage threshold) and lands: package T's StepOff, Fall and
// Land stages.
//
// Every step is a typed request; the executors re-prove it natively and only
// submit what a client could (a movement report, a straight swim spline, a
// jump, a fall). Nothing here moves a unit.

#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianMagma.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianMovement.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianPlatformBody.h"
#include <optional>
#include <string_view>

namespace BotEncounter::Nefarian
{
enum class AscentStage : uint8
{
    Float, // stop standing on the sinking platform, start swimming
    Swim,  // straight swim at the float depth to the swim station
    Hop,   // the client's jump from the station onto the rim
    Board  // report standing on the platform (the rim, or the rising floor)
};

inline std::string_view AscentStageName(AscentStage stage)
{
    switch (stage)
    {
        case AscentStage::Float: return "pillar_ascent_float";
        case AscentStage::Swim: return "pillar_ascent_swim";
        case AscentStage::Hop: return "pillar_ascent_hop";
        case AscentStage::Board: return "pillar_ascent_board";
    }
    return "pillar_ascent";
}

struct AscentStep
{
    AscentStage Stage = AscentStage::Float;
    ObjectGuid Transport;
    Vector3 World;              // Swim destination or Hop landing point
    float FloatDepthYards = Nefarian::FloatDepthYards;
    float FloorToleranceYards = 0.3f;
    float HopSpeedXY = 0.0f;    // Hop: horizontal speed of the planned jump
    float SwimSpeedYardsPerSecond = 0.0f; // Swim: 0 = the native swim speed
    int Pillar = -1;
    uint8 Slot = 0;
};

struct AscentDecision
{
    std::optional<AscentStep> Step;
    std::string_view Hold;
};

constexpr float SwimStationToleranceYards = 0.75f;
constexpr float SwimDepthToleranceYards = 0.15f;
constexpr float MaxSwimLegYards = 12.0f; // BotValidationRouteNativeLiquid::MaxSwimYards
constexpr float SwimLegMarginYards = 0.25f;
// A swimmer the rising floor will reach (phase 3 raises the platform at
// FloorRiseYardsPerSecond) goes to meet it instead of waiting for a contact a
// decision could miss: it swims down to just above the floor, then rises
// with it slightly slower than the floor (RideCloseYardsPerSecond), so the
// floor closes on its feet slowly and the boarding band is open for about
// two seconds whatever the decision cadence. Then it boards where it stands.
constexpr float FloorRiseYardsPerSecond = RaisedOffset * 1000.0f / (LinearToMs - LinearFromMs);
constexpr float RideCloseYardsPerSecond = 0.25f;
constexpr float RisingFloorBoardMaxYards = 0.45f; // feet at most this above the floor
constexpr float RisingFloorBoardMinYards = -0.3f; // or this far into it (the
// swimmer's emerge report, made at its actual position, accepts the floor
// within 0.5 of its feet, like the surface walk's own 0.6 floor tolerance).
// Nothing lifts a swimmer the floor has passed: no native code moves a unit
// that is not a registered passenger, so a floor past the band is a typed
// miss, never a rewritten position.
constexpr float RisingFloorEmergeToleranceYards = 0.5f;
constexpr float RisingFloorRideRoomYards = 0.5f;
constexpr float RisingFloorArmYards = 2.0f;
constexpr float RisingFloorMeetYards = 1.5f;
// The ride closes on the floor no slower than RideCloseYardsPerSecond, and
// fast enough that the swimmer runs out of room under the surface no earlier
// than the floor reaches the bottom of the boarding band (round 3, packet
// liquid_clearance): a ride that reached the surface first left the floor to
// close at the full rise speed, a 0.7 s band, and a late decision then left
// the floor passing through the body.
constexpr float RisingFloorRideTargetGapYards = RisingFloorBoardMinYards + 0.05f;
constexpr float RideSurfaceMarginYards = 0.05f;

inline float RideClosingYardsPerSecond(float gap, float room)
{
    float const closeBy = std::max(gap - RisingFloorRideTargetGapYards, 0.0f);
    if (closeBy <= 0.0f)
        return RideCloseYardsPerSecond;
    float const needed = FloorRiseYardsPerSecond * closeBy / (std::max(room, 0.0f) + closeBy);
    return std::clamp(needed, RideCloseYardsPerSecond, FloorRiseYardsPerSecond);
}

// A rising pillar passes through a swimmer whose body reaches its wall or
// skirt: the skirt stands 0.81 above the ring out to about 5.97 yards (the
// model; PillarSkirtRadius 6.05 bounds it), so a swimmer riding the ring
// nearer than this would board with the skirt inside its body. It moves
// out to its swim station's radius first (round 3, packet liquid_clearance).
constexpr float RisingFloorPillarClearRadius = PillarSkirtRadius + BodyRadiusYards + 0.1f;
// The hop leaves from no nearer the pillar than this: from the inner part of
// the station tolerance the jump's body meets the wall edge on the real model
// (tests/test_liquid_body_clearance.py), and the executor refuses it.
constexpr float HopOriginInnerSlackYards = 0.25f;

// A passenger of the elevator standing on a pillar (top or rim): its
// placement is above the ring and skirt and within the pillar's reach, and
// not inside the pillar's hollow shaft (round 3, BotNefarianPlatformBody.h).
inline bool OnPillarStructure(MovementContext const& context)
{
    if (!context.Facts)
        return false;
    TransportPlacement const* placement =
        context.Facts->FindPlacement(context.Bot.Guid);
    if (!placement || placement->TransportEntry != ElevatorEntry
        || placement->Offset.Z <= PillarSkirtLocalZ + 1.5f)
        return false;
    float distance = 0.0f;
    NearestPillar(BotLocal(context), distance);
    return distance <= DescentStepOffRadius + 0.5f
        && !InsidePillarShaft(BotLocal(context), placement->Offset.Z);
}

inline bool IsElevatorPassenger(MovementContext const& context)
{
    if (!context.Facts)
        return false;
    TransportPlacement const* placement =
        context.Facts->FindPlacement(context.Bot.Guid);
    return placement && placement->TransportEntry == ElevatorEntry;
}

inline AscentDecision PlanPillarAscent(MovementContext const& context,
    int pillar, uint8 slot)
{
    AscentDecision decision;
    if (!context.Facts)
    {
        // The walk to the foot needs no placement; every later step does.
        if (context.View.Elevator.State != ElevatorState::Raised)
            decision.Hold = "nefarian_ascent_needs_native_facts";
        return decision;
    }
    if (pillar < 0)
        return decision;
    uint8 const p = uint8(pillar);
    ElevatorView const& elevator = context.View.Elevator;
    Vector3 const position = context.Bot.Position;
    LocalPoint const local = WorldToLocal(position);
    auto step = [&](AscentStage stage)
    {
        AscentStep result;
        result.Stage = stage;
        result.Transport = elevator.Guid;
        result.Pillar = pillar;
        result.Slot = slot;
        return result;
    };

    // Inside a pillar's hollow shaft (round 2: native chase put melee members
    // there): no swim, float or walk proven by the executors leaves it
    // (BotNefarianPlatformBody.h), so name it rather than propose one.
    if (InsidePillarShaft(local, BotLocalZ(context)))
    {
        decision.Hold = "nefarian_inside_pillar_column";
        return decision;
    }

    if (IsElevatorPassenger(context))
    {
        if (OnPillarStructure(context))
            return decision; // walks to its slot on the top
        if (position.Z <= MagmaSurfaceZ - FloatDepthYards)
        {
            decision.Step = step(AscentStage::Float);
            return decision;
        }
        // Standing on the floor: walk to the foot while the platform keeps
        // still, then wait for the magma to lift it.
        if (elevator.State != ElevatorState::Raised)
            decision.Hold = position.Z < MagmaSurfaceZ
                ? "nefarian_wading_until_float_depth" : "nefarian_magma_rising";
        return decision;
    }

    float const floatZ = MagmaSurfaceZ - FloatDepthYards;
    // The hop in flight keeps its request (and with it the movement, GCD and
    // cast lanes, so no heal stops the jump short of the pillar) until it
    // lands: the executor answers it with progress while the jump runs.
    Vector3 const landing = LocalToWorld(PillarRadial(p, slot, HopLandingRadius(p, slot)),
        HopLandingLocalZ, elevator.OriginZ);
    if (MovementState const* motion = context.Facts->FindMotion(context.Bot.Guid);
        motion && motion->Moving
        && std::hypot(motion->Destination.X - landing.X, motion->Destination.Y - landing.Y) <= 0.6f
        && std::fabs(motion->Destination.Z - landing.Z) <= 0.6f)
    {
        decision.Step = step(AscentStage::Hop);
        decision.Step->World = motion->Destination;
        return decision;
    }
    if (position.Z < MagmaSurfaceZ)
    {
        // A swimmer over the rising floor meets it and boards it.
        float nearest = 0.0f;
        int const nearPillar = NearestPillar(local, nearest);
        if (context.View.CurrentPhase == Phase::PlatformReturn
            && nearest <= RisingFloorPillarClearRadius && Length(local) <= OuterFloorLimit)
        {
            // Beside a rising pillar: straight out from its centre to the
            // swim station's radius at the same depth, before its skirt
            // reaches the knee (then the floor is met and boarded there).
            LocalPoint const centre = PillarCenters[nearPillar];
            LocalPoint const away{ local.X - centre.X, local.Y - centre.Y };
            LocalPoint const out = Offset(centre, Length(away) > 0.01f ? AngleOf(away)
                : PillarSlotHeading(uint8(nearPillar), slot), SwimStationRadius);
            Vector3 clear = LocalToWorld(out, 0.0f, 0.0f);
            clear.Z = position.Z;
            decision.Step = step(AscentStage::Swim);
            decision.Step->World = clear;
            return decision;
        }
        if (context.View.CurrentPhase == Phase::PlatformReturn
            && nearest > RisingFloorPillarClearRadius && Length(local) <= OuterFloorLimit)
        {
            float const floorZ = elevator.OriginZ + FloorLocalZAt(local);
            float const gap = position.Z - floorZ;
            if (gap >= RisingFloorBoardMinYards && gap <= RisingFloorBoardMaxYards)
            {
                decision.Step = step(AscentStage::Board);
                decision.Step->FloorToleranceYards = RisingFloorEmergeToleranceYards;
                return decision;
            }
            if (gap < RisingFloorBoardMinYards)
            {
                // The floor passed the feet: no lawful way up remains (a
                // swimmer cannot pass through the platform, and nothing
                // lifts it). Typed, for the trace.
                decision.Hold = "nefarian_rising_floor_missed";
                return decision;
            }
            decision.Step = step(AscentStage::Swim);
            Vector3 target = position;
            if (gap <= RisingFloorArmYards)
            {
                // Ride: rise just slower than the floor, up to the surface,
                // closing fast enough to reach the band before the surface.
                target.Z = MagmaSurfaceZ - RideSurfaceMarginYards;
                // (Never 0: the executor reads 0 as the native swim speed.)
                decision.Step->SwimSpeedYardsPerSecond = std::max(FloorRiseYardsPerSecond
                    - RideClosingYardsPerSecond(gap, target.Z - position.Z), 0.05f);
            }
            else
            {
                // Meet: straight down to where the rising floor will be
                // RisingFloorMeetYards under the feet (swimmer and floor close
                // at the swim speed plus the rise speed), one leg at most.
                float const closeSeconds = (gap - RisingFloorMeetYards)
                    / (SwimSpeedYardsPerSecond + FloorRiseYardsPerSecond);
                target.Z = std::max(floorZ + FloorRiseYardsPerSecond * closeSeconds
                        + RisingFloorMeetYards,
                    position.Z - (MaxSwimLegYards - SwimLegMarginYards));
            }
            if (gap <= RisingFloorArmYards
                && MagmaSurfaceZ - 0.05f - position.Z < RisingFloorRideRoomYards)
            {
                // At the surface: no room left to ride up. The floor under the
                // feet closes at the rise speed less what swimming does to it.
                // Over the ramp (0.1763 per yard, lower toward the centre) an
                // inward swim at the surface drops the floor under the feet
                // about 0.83 yd/s while it rises 1.075, so it closes at about
                // a quarter of the rise speed and the band stays open about
                // three seconds. Outside the ramp's end the swimmer also swims
                // inward, toward that ramp (the flat ring closes no faster for
                // it). Over the flat centre, inside the ramp, no swim helps: it
                // holds still, armed. Where the floor closes at the full rise
                // the band is open 0.7 s; a decision that falls outside it is
                // a typed miss. (Only a member that already missed its pillar
                // hop gets here.)
                if (Length(local) <= RampStartRadius)
                {
                    decision.Step.reset();
                    decision.Hold = "nefarian_rising_floor_armed";
                    return decision;
                }
                LocalPoint const inward = Offset(local, AngleOf(local) + Pi,
                    MaxSwimLegYards - SwimLegMarginYards);
                Vector3 across = LocalToWorld(inward, 0.0f, 0.0f);
                across.Z = position.Z;
                decision.Step->World = across;
                decision.Step->SwimSpeedYardsPerSecond = 0.0f;
                return decision;
            }
            decision.Step->World = target;
            return decision;
        }
        // Under the walk surface, inside the closed body: every swim to the
        // station crosses the surface from below and is refused.
        if (InsidePlatformBody(local, position.Z - elevator.OriginZ))
        {
            decision.Hold = "nefarian_inside_platform_body";
            return decision;
        }
        LocalPoint const station = PillarRadial(p, slot, SwimStationRadius);
        float const off = Distance(local, station);
        if (off > SwimStationToleranceYards
            || Distance(local, PillarCenters[p]) < SwimStationRadius - HopOriginInnerSlackYards
            || std::fabs(position.Z - floatZ) > SwimDepthToleranceYards)
        {
            // One swim leg: the whole 3D displacement (horizontal and the
            // depth correction) within the executor's limit.
            Vector3 target = LocalToWorld(station, 0.0f, 0.0f);
            target.Z = floatZ;
            float const dx = target.X - position.X;
            float const dy = target.Y - position.Y;
            float const dz = target.Z - position.Z;
            float const length = std::sqrt(dx * dx + dy * dy + dz * dz);
            if (length > MaxSwimLegYards - SwimLegMarginYards)
            {
                float const scale = (MaxSwimLegYards - SwimLegMarginYards) / length;
                target = { position.X + dx * scale, position.Y + dy * scale,
                    position.Z + dz * scale };
            }
            decision.Step = step(AscentStage::Swim);
            decision.Step->World = target;
            return decision;
        }
        if (elevator.State != ElevatorState::Lowered)
        {
            decision.Hold = "nefarian_float_hold_for_pillar";
            return decision;
        }
        HopPlan const hop = PlanHop(p, slot, Distance(local, PillarCenters[p]),
            position.Z, elevator.OriginZ);
        if (!hop.Ok)
        {
            decision.Hold = hop.Reason;
            return decision;
        }
        decision.Step = step(AscentStage::Hop);
        decision.Step->World = LocalToWorld(PillarRadial(p, slot, hop.LandingRadius),
            hop.LandingLocalZ, elevator.OriginZ);
        decision.Step->HopSpeedXY = hop.SpeedXY;
        return decision;
    }

    // Above the magma without being a passenger: landed from the hop (or, in
    // round 2, stood on the top without boarding). It boards before the
    // platform rises: nothing native lifts a unit that is not a passenger.
    float distance = 0.0f;
    int const nearestPillar = NearestPillar(local, distance);
    bool const topMoving = context.View.CurrentPhase == Phase::PlatformReturn
        || elevator.State == ElevatorState::Moving;
    if (topMoving && distance < PillarShaftRadius)
    {
        // The top or rim rising under the feet (the rise starts inside the
        // lowered stop's tolerance): board while it is within the swimmer's
        // emerge band (the report is made where the member stands), a typed
        // miss once it has passed them.
        float const surface = elevator.OriginZ
            + PillarSurfaceLowest(uint8(nearestPillar), distance);
        float const gap = position.Z - surface;
        if (gap < -RisingFloorEmergeToleranceYards)
        {
            decision.Hold = "nefarian_rising_top_missed";
            return decision;
        }
        if (gap <= RisingFloorBoardMaxYards)
        {
            decision.Step = step(AscentStage::Board);
            decision.Step->FloorToleranceYards = RisingFloorEmergeToleranceYards;
            return decision;
        }
    }
    if (distance <= PillarSkirtRadius
        && position.Z >= elevator.OriginZ + PillarSkirtLocalZ + 1.5f)
    {
        decision.Step = step(AscentStage::Board);
        return decision;
    }
    decision.Hold = "nefarian_not_on_platform";
    return decision;
}

struct DescentDecision
{
    std::optional<BotNativeAction::TransportSurfaceMove> Move;
    std::string_view Mechanic;
    std::string_view Hold;
};

// The member's own heading from its pillar's centre (the slot heading when it
// stands on the centre).
inline float DescentHeading(LocalPoint local, int pillar, uint8 slot)
{
    LocalPoint const centre = PillarCenters[pillar % 3];
    LocalPoint const delta{ local.X - centre.X, local.Y - centre.Y };
    return Length(delta) < 0.5f ? PillarSlotHeading(uint8(pillar), slot)
        : AngleOf(delta);
}

inline DescentDecision PlanPillarDescent(MovementContext const& context, uint8 slot)
{
    DescentDecision decision;
    if (!context.Facts)
        return decision;
    ElevatorView const& elevator = context.View.Elevator;
    LocalPoint const local = BotLocal(context);
    float distance = 0.0f;
    int const pillar = NearestPillar(local, distance);
    // The model floor under the member: the ring below every pillar rim, and
    // the floor under a stranded member's fall (BotNefarianStranded.h).
    float const landingZ = elevator.OriginZ + FloorLocalZAt(local);

    BotNativeAction::TransportSurfaceMove move;
    move.Transport = elevator.Guid;
    move.LandingZ = landingZ;
    move.LandingToleranceYards = 1.0f;
    move.LandOnTransport = true;
    move.MinHealthAfterFallPct = 0.2f;
    move.FloorToleranceYards = 0.6f;

    if (FallState const* fall = context.Facts->FindFall(context.Bot.Guid);
        fall && (fall->Falling || fall->LandingPending))
    {
        move.Kind = BotNativeAction::TransportSurfaceMove::Stage::Land;
        decision.Move = move;
        decision.Mechanic = "pillar_descent_land";
        return decision;
    }
    if (!OnPillarStructure(context))
        return decision;
    if (elevator.State != ElevatorState::Raised)
    {
        decision.Hold = "nefarian_descent_wait_for_raised_floor";
        return decision;
    }
    float const heading = DescentHeading(local, pillar, slot);
    uint8 const profileSlot = slot;
    if (distance < DescentRimRadius - 0.3f)
    {
        // Out to the rim; its height on this heading is within 0.1 of the
        // slot profile's (flat radius 3.5-3.9, slope 0.465).
        float const rimZ = PlatformFrame::PillarTopLocalZ - PillarRimSlope
            * (DescentRimRadius - SlotProfile(uint8(pillar), profileSlot).FlatRadius);
        Vector3 const rim = LocalToWorld(Offset(PillarCenters[pillar], heading,
            DescentRimRadius), rimZ, elevator.OriginZ);
        move.Kind = BotNativeAction::TransportSurfaceMove::Stage::Walk;
        move.X = rim.X;
        move.Y = rim.Y;
        move.Z = rim.Z;
        move.EndOnTransport = true;
        decision.Move = move;
        decision.Mechanic = "pillar_descent_rim";
        return decision;
    }
    if (distance < DescentOverVoidRadius(uint8(pillar), profileSlot) - 0.15f)
    {
        Vector3 const off = LocalToWorld(Offset(PillarCenters[pillar], heading,
            DescentStepOffRadius), 0.0f, 0.0f);
        move.Kind = BotNativeAction::TransportSurfaceMove::Stage::StepOff;
        move.X = off.X;
        move.Y = off.Y;
        move.Z = context.Bot.Position.Z;
        decision.Move = move;
        decision.Mechanic = "pillar_descent_step_off";
        return decision;
    }
    move.Kind = BotNativeAction::TransportSurfaceMove::Stage::Fall;
    decision.Move = move;
    decision.Mechanic = "pillar_descent_fall";
    return decision;
}
}

#endif
