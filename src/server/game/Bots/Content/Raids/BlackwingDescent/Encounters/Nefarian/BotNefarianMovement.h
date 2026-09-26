#ifndef TRINITY_BOT_NEFARIAN_MOVEMENT_H
#define TRINITY_BOT_NEFARIAN_MOVEMENT_H

// Movement goals for Nefarian's End. Every goal is a standing spot on the
// GO 207834 transport surface, expressed in the transport frame
// (SurfaceGoal). The strategy walks to it in short legs (BotNefarianPath.h),
// each submitted as package T's BotNativeAction::TransportSurfaceMove Walk
// (BotNefarianSurfaceIntent.h). This file never manufactures a position, a
// jump or a fall; it only chooses destinations.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianLayout.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianTactics.h"
#include <optional>
#include <vector>

namespace BotEncounter::Nefarian
{
enum class MovePurpose : uint8
{
    None,
    FireEscape,
    BreathEscape,
    PillarAscent,
    PillarHold,
    PillarFoot,
    PillarDescent,
    TankLead,
    TankHold,
    DischargeTurn,
    WarriorPen,
    Kite,
    Stage,
    Formation
};

inline std::string_view MovePurposeName(MovePurpose purpose)
{
    switch (purpose)
    {
        case MovePurpose::None: return "none";
        case MovePurpose::FireEscape: return "shadowblaze_escape";
        case MovePurpose::BreathEscape: return "breath_escape";
        case MovePurpose::PillarAscent: return "pillar_ascent";
        case MovePurpose::PillarHold: return "pillar_hold";
        case MovePurpose::PillarFoot: return "pillar_foot_no_ascent";
        case MovePurpose::PillarDescent: return "pillar_descent";
        case MovePurpose::TankLead: return "dragon_lead";
        case MovePurpose::TankHold: return "dragon_hold";
        case MovePurpose::DischargeTurn: return "discharge_turn";
        case MovePurpose::WarriorPen: return "bone_warrior_pen";
        case MovePurpose::Kite: return "bone_warrior_kite";
        case MovePurpose::Stage: return "pre_pull_stage";
        case MovePurpose::Formation: return "formation";
    }
    return "unknown";
}

// The interface package T's transport-surface movement consumes.
struct SurfaceGoal
{
    MovePurpose Purpose = MovePurpose::None;
    Surface Target = Surface::Floor;
    LocalPoint Local;
    float LocalZ = PlatformFrame::FloorLocalZ;
    Vector3 World;
    ObjectGuid Transport;
    uint32 TransportEntry = ElevatorEntry;
    float ArrivalToleranceYards = 3.0f;
    int Pillar = -1;
    bool Urgent = false;
    // A bot leading warriors held where it stands (the handler cornered with
    // no lawful kite or pen point): the plan renews the warrior hold every
    // decision while this goal stands, moving or not.
    bool WarriorHold = false;
    // A caster or healer spot: whom it must see past the pillars, and within
    // what range (the arrival tolerance applies only while both still hold
    // from where the bot actually stands).
    std::vector<LocalPoint> Sight;
    float SightRangeYards = 0.0f;
};

struct MovementContext
{
    Blackboard const& Board;
    EncounterView const& View;
    DutyPlan const& Plan;
    ArenaLayout const& Layout;
    ActorSnapshot const& Bot;
    NativeFacts const* Facts = nullptr;
};

inline LocalPoint BotLocal(MovementContext const& context)
{
    return WorldToLocal(context.Bot.Position);
}

// A bot stands on a pillar top only when its native transport placement says
// so: a passenger of the elevator whose offset Z exceeds the native Shadow of
// Cowardice threshold. Without a placement (no facts, or not a passenger, for
// example in the magma over the lowered platform) it is not on a pillar top.
inline bool OnPillarTop(MovementContext const& context)
{
    if (!context.Facts)
        return false;
    TransportPlacement const* placement =
        context.Facts->FindPlacement(context.Bot.Guid);
    return placement && placement->TransportEntry == ElevatorEntry
        && placement->Offset.Z > PlatformFrame::CowardiceLocalZ;
}

// The bot's height in the platform frame, from its transport placement when
// published, otherwise from the observed origin.
inline float BotLocalZ(MovementContext const& context)
{
    if (context.Facts)
        if (TransportPlacement const* placement =
                context.Facts->FindPlacement(context.Bot.Guid))
            return placement->Offset.Z;
    return context.Bot.Position.Z - context.View.Elevator.OriginZ;
}

// Stands on the platform floor or ring (not on the ledge above, not in the
// magma below, not on a pillar top). With native facts it must also be a
// passenger of the elevator.
inline bool OnPlatformFloor(MovementContext const& context)
{
    if (context.Facts)
    {
        TransportPlacement const* placement =
            context.Facts->FindPlacement(context.Bot.Guid);
        if (!placement || placement->TransportEntry != ElevatorEntry)
            return false;
    }
    float const localZ = BotLocalZ(context);
    return localZ > PlatformFrame::FloorLocalZ - 1.5f
        && localZ < RingLocalZ + 2.0f;
}

inline SurfaceGoal MakeGoal(MovementContext const& context, MovePurpose purpose,
    Surface surface, LocalPoint local, float tolerance, bool urgent,
    int pillar = -1)
{
    SurfaceGoal goal;
    goal.Purpose = purpose;
    goal.Target = surface;
    // Floor goals stand on the centre floor or the ring, clear of pillars.
    goal.Local = surface == Surface::Floor ? SnapToStandingArea(local) : local;
    local = goal.Local;
    goal.LocalZ = surface == Surface::Floor ? FloorLocalZAt(local)
        : SurfaceLocalZ(surface);
    goal.World = LocalToWorld(local, goal.LocalZ, context.View.Elevator.OriginZ);
    goal.Transport = context.View.Elevator.Guid;
    goal.ArrivalToleranceYards = tolerance;
    goal.Pillar = pillar;
    goal.Urgent = urgent;
    return goal;
}

// A point a bone warrior may be led to: well outside Nefarian's front cone
// (his breath wakes, refills and empowers warriors; confirmed by the user) and
// outside his tail.
constexpr float WarriorFrontMarginDeg = 15.0f;
constexpr float HandlerKiteTriggerYards = 6.0f;
// The movement hold that stops a running walk no lawful leg replaces (the
// submission claims the movement lane and stops the spline).
constexpr float DragonCoreClearanceYards = 4.0f;
// The damage dealers' hold fire before Onyxia is tanked (pre-pull and until
// a tank has her): the suppression also claims the Target lane, so no
// trained damage opens on her (BotWorldPopulationMgrNefarianCandidates.cpp).
constexpr std::string_view HoldFirePreEngage = "nefarian_pre_engage_hold";
constexpr std::string_view HoldFireForOnyxiaTank = "nefarian_wait_for_onyxia_tank";
// The Onyxia tank's pickup budget is spent (BotNefarianPickupMemory.h).
constexpr std::string_view PickupExhaustedHold = "nefarian_pickup_exhausted";
constexpr std::string_view WarriorStopHold = "nefarian_warrior_path_stop";
// The platform hold (round 7): a bot on the raised platform with no leg of
// the plan stands where it is, its native generator stopped and a Mechanic
// movement lease renewed, so native combat range, chase and route movement
// (static navmesh paths under the transport) cannot walk it off. A leg in
// flight (nefarian_leg_in_flight) renews the lease without being stopped.
constexpr std::string_view PlatformHold = "nefarian_platform_hold";
constexpr std::string_view LegInFlightHold = "nefarian_leg_in_flight";

// A platform hold keeps the diagnostic it replaces visible in the trace:
// "nefarian_platform_hold:<diagnostic>" (static literals, as every hold is a
// string_view into static storage).
inline std::string_view PlatformHoldWith(std::string_view diagnostic)
{
    static constexpr std::string_view Composed[] = {
        "nefarian_platform_hold:nefarian_elevator_unobserved",
        "nefarian_platform_hold:nefarian_movement_stunned",
        "nefarian_platform_hold:nefarian_no_surface_path",
        "nefarian_platform_hold:nefarian_not_on_platform",
        "nefarian_platform_hold:nefarian_pickup_exhausted",
    };
    for (std::string_view composed : Composed)
        if (composed.substr(PlatformHold.size() + 1) == diagnostic)
            return composed;
    return PlatformHold;
}

inline bool IsPlatformHold(std::string_view hold)
{
    return hold.substr(0, PlatformHold.size()) == PlatformHold;
}

// The diagnostic a hold carries: the hold itself, or what a platform hold
// replaced.
inline std::string_view HoldReason(std::string_view hold)
{
    if (IsPlatformHold(hold) && hold.size() > PlatformHold.size() + 1)
        return hold.substr(PlatformHold.size() + 1);
    return hold;
}
constexpr float HandlerKiteReleaseYards = 10.0f; // hysteresis: kiting ends past this
constexpr float HandlerPenRadius = 24.0f;
constexpr float WarriorLeadRangeYards = 25.0f;

// How deep a point lies in the warrior exclusion (radians past its edge; 0
// outside it): the breath cone widened by WarriorFrontMarginDeg, and the tail
// cone, both within the cones' 60-yard radius.
inline float WarriorDanger(EncounterView const& view, LocalPoint point)
{
    if (!view.Nefarian || !view.Nefarian->Alive || !view.NefarianLanded())
        return 0.0f;
    DragonPose const nefarian = PoseOf(*view.Nefarian);
    if (Distance(nefarian.Position, point) > DragonConeRadius)
        return 0.0f;
    float const off = OffFacing(nefarian.Position, nefarian.Facing, point);
    float const front = DegToRad(BreathHalfAngleDeg + WarriorFrontMarginDeg) - off;
    float const rear = off - (Pi - DegToRad(TailLashHalfAngleDeg + 8.0f));
    return std::max(0.0f, std::max(front, rear));
}

inline bool WarriorPointSafe(EncounterView const& view, LocalPoint point)
{
    return WarriorDanger(view, point) <= 0.0f;
}

// A straight walk a following warrior may take: it ends outside the
// exclusion, and along it (sampled at most a yard apart) the depth in the
// exclusion never grows. From a safe start that means every point is safe;
// from a start already inside (Nefarian turned onto the walker, or it stands
// in the margin) it allows only a monotonic way out, never deeper in.
// Along a straight walk the depth in the exclusion never grows (a leg may
// stop short of leaving it; from a safe start every point stays safe).
inline bool WarriorPathNoDeeper(EncounterView const& view, LocalPoint from, LocalPoint to)
{
    float const length = Distance(from, to);
    int const steps = std::max(1, int(std::ceil(length)));
    float previous = WarriorDanger(view, from);
    for (int i = 1; i <= steps; ++i)
    {
        float const t = float(i) / float(steps);
        float const danger = WarriorDanger(view, { from.X + (to.X - from.X) * t,
            from.Y + (to.Y - from.Y) * t });
        if (danger > previous + 1e-4f)
            return false;
        previous = danger;
    }
    return true;
}

inline bool WarriorPathSafe(EncounterView const& view, LocalPoint from, LocalPoint to)
{
    if (!WarriorPointSafe(view, to))
        return false;
    float const length = Distance(from, to);
    int const steps = std::max(1, int(std::ceil(length)));
    float previous = WarriorDanger(view, from);
    for (int i = 1; i <= steps; ++i)
    {
        float const t = float(i) / float(steps);
        float const danger = WarriorDanger(view, { from.X + (to.X - from.X) * t,
            from.Y + (to.Y - from.Y) * t });
        if (danger > previous + 1e-4f)
            return false;
        previous = danger;
    }
    return true;
}

// The dragon's current tank: Nefarian (landed) or Onyxia is attacking it, or
// it is Nefarian's duty tank once he is on the ground. It keeps its tank hold
// whatever warrior is on it: moving would turn the dragon and sweep his
// breath over the raid. A warrior on it is the handler's (taunt) or the
// controls' (shackle, Nature's Grasp), never the tank's to kite.
inline bool IsDragonTank(MovementContext const& context)
{
    ObjectGuid const guid = context.Bot.Guid;
    EncounterView const& view = context.View;
    if (view.NefarianLanded()
        && (view.Nefarian->VictimGuid == guid || guid == context.Plan.NefarianTank))
        return true;
    return view.OnyxiaAlive() && view.Onyxia->InCombat
        && view.Onyxia->VictimGuid == guid;
}

// The bot leads bone warriors where it walks: it is the warrior handler once
// Nefarian is on the ground, or an active, unheld warrior near it attacks it.
// A dragon's tank never leads them (IsDragonTank).
inline bool LeadsWarriors(MovementContext const& context)
{
    ActorSnapshot const& bot = context.Bot;
    if (IsDragonTank(context))
        return false;
    if (bot.Guid == context.Plan.WarriorHandler
        && (context.View.CurrentPhase == Phase::NefarianGround
            || context.View.CurrentPhase == Phase::NefarianLanding))
        return true;
    for (ActorSnapshot const* warrior : context.View.BoneWarriors)
        if (IsActiveBoneWarrior(*warrior) && !IsBoneWarriorHeld(*warrior)
            && warrior->VictimGuid == bot.Guid
            && Distance3(warrior->Position, bot.Position) <= WarriorLeadRangeYards)
            return true;
    return false;
}

// A non-tank within DragonCoreClearanceYards of a living dragon's centre:
// Spell.cpp skips the breath's cone check for a target inside its own
// bounding radius (at least 2 yards), so there the breath hits whatever the
// dragon's facing.
inline bool InDragonCore(MovementContext const& context, LocalPoint point)
{
    if (context.Plan.IsTank(context.Bot.Guid))
        return false;
    for (ActorSnapshot const* dragon : { context.View.Onyxia, context.View.Nefarian })
        if (dragon && dragon->Alive
            && Distance(WorldToLocal(dragon->Position), point) < DragonCoreClearanceYards)
            return true;
    return false;
}

// Danger rules at a floor point. Onyxia's flank is only avoided while she is
// discharging, and her rear is then the intended refuge (the tank turns her).
inline bool FloorPointSafe(MovementContext const& context, LocalPoint point,
    bool isTank)
{
    if (!OnFloorArea(point))
        return false;
    // Whoever leads warriors (tank or not) never walks them past Nefarian's
    // front on the way there.
    if (LeadsWarriors(context)
        && !WarriorPathSafe(context.View, BotLocal(context), point))
        return false;
    for (ActorSnapshot const* fire : context.View.Fires)
        if (Distance(WorldToLocal(fire->Position), point)
            < ShadowblazeRadius + 4.0f)
            return false;
    if (isTank)
        return true;
    // Spell.cpp's cone check skips a target within its own bounding radius
    // (at least 2 yards) of the breathing dragon's centre: non-tanks keep
    // DragonCoreClearanceYards from both.
    for (ActorSnapshot const* dragon : { context.View.Onyxia, context.View.Nefarian })
        if (dragon && dragon->Alive
            && Distance(WorldToLocal(dragon->Position), point) < DragonCoreClearanceYards)
            return false;
    if (context.View.OnyxiaAlive() && context.View.Onyxia->InCombat)
    {
        DragonPose const onyxia = PoseOf(*context.View.Onyxia);
        if (InFrontCone(onyxia, point))
            return false;
        if (!context.View.OnyxiaDischarging() && InRearCone(onyxia, point))
            return false;
    }
    if (context.View.NefarianLanded())
    {
        DragonPose const nefarian = PoseOf(*context.View.Nefarian);
        if (InFrontCone(nefarian, point) || InRearCone(nefarian, point))
            return false;
    }
    return true;
}

// First safe point on rings around an anchor, starting at the preferred
// bearing and alternating sides.
inline std::optional<LocalPoint> SafeNear(MovementContext const& context,
    LocalPoint anchor, float bearing, float radius, bool isTank)
{
    for (float step : { 0.0f, 20.0f, -20.0f, 40.0f, -40.0f, 60.0f, -60.0f,
            90.0f, -90.0f, 135.0f, -135.0f, 180.0f })
    {
        LocalPoint const point = Offset(anchor, bearing + DegToRad(step), radius);
        if (FloorPointSafe(context, point, isTank))
            return point;
    }
    return std::nullopt;
}

inline std::optional<SurfaceGoal> FireEscape(MovementContext const& context)
{
    LocalPoint const self = BotLocal(context);
    ActorSnapshot const* nearest = nullptr;
    float nearestDistance = ShadowblazeRadius + 3.0f;
    for (ActorSnapshot const* fire : context.View.Fires)
    {
        float const distance = Distance(WorldToLocal(fire->Position), self);
        if (distance < nearestDistance)
        {
            nearest = fire;
            nearestDistance = distance;
        }
    }
    if (!nearest)
        return std::nullopt;
    LocalPoint const fire = WorldToLocal(nearest->Position);
    float const away = Length({ self.X - fire.X, self.Y - fire.Y }) < 0.1f
        ? AngleOf(self) + Pi : AngleOf({ self.X - fire.X, self.Y - fire.Y });
    bool const isTank = context.Plan.IsTank(context.Bot.Guid);
    std::optional<LocalPoint> const point = SafeNear(context, fire, away,
        ShadowblazeRadius + 8.0f, isTank);
    if (!point)
        return std::nullopt;
    return MakeGoal(context, MovePurpose::FireEscape, Surface::Floor, *point,
        2.0f, true);
}

inline std::optional<SurfaceGoal> BreathEscape(MovementContext const& context)
{
    if (context.Plan.IsTank(context.Bot.Guid))
        return std::nullopt;
    LocalPoint const self = BotLocal(context);
    // Inside a dragon's core the cone does not protect: leave it whatever the
    // dragon is casting.
    for (ActorSnapshot const* dragon : { context.View.Onyxia, context.View.Nefarian })
    {
        if (!dragon || !dragon->Alive)
            continue;
        LocalPoint const body = WorldToLocal(dragon->Position);
        if (Distance(body, self) >= DragonCoreClearanceYards)
            continue;
        float const away = Distance(body, self) < 0.1f ? AngleOf(self)
            : AngleOf({ self.X - body.X, self.Y - body.Y });
        if (std::optional<LocalPoint> const point = SafeNear(context, body, away,
                DragonCoreClearanceYards + 4.0f, false))
            return MakeGoal(context, MovePurpose::BreathEscape, Surface::Floor, *point, 1.5f,
                true);
    }
    for (ActorSnapshot const* dragon : { context.View.Onyxia,
            context.View.Nefarian })
    {
        if (!dragon || !dragon->Alive || !dragon->Cast
            || !IsShadowflameBreath(dragon->Cast->SpellId))
            continue;
        DragonPose const pose = PoseOf(*dragon);
        if (!InFrontCone(pose, self, 4.0f))
            continue;
        LocalPoint const delta{ self.X - pose.Position.X,
            self.Y - pose.Position.Y };
        float const side = NormalizeSigned(AngleOf(delta) - pose.Facing) >= 0.0f
            ? 1.0f : -1.0f;
        float const out = pose.Facing + side * DegToRad(90.0f);
        std::optional<LocalPoint> const point = SafeNear(context, self, out,
            9.0f, false);
        if (point)
            return MakeGoal(context, MovePurpose::BreathEscape, Surface::Floor,
                *point, 2.0f, true);
    }
    return std::nullopt;
}

// A bot leading warriors from inside the exclusion walks straight out of it:
// to the nearer edge's safe side, sweeping around Nefarian on the side it is
// already on, at about its own distance from him (the first floor spot, clear
// of fires, whose path leaves the exclusion monotonically).
inline std::optional<SurfaceGoal> WarriorEscape(MovementContext const& context)
{
    LocalPoint const self = BotLocal(context);
    if (!LeadsWarriors(context) || WarriorPointSafe(context.View, self))
        return std::nullopt;
    DragonPose const nefarian = PoseOf(*context.View.Nefarian);
    LocalPoint const delta{ self.X - nefarian.Position.X, self.Y - nefarian.Position.Y };
    float const side = NormalizeSigned(AngleOf(delta) - nefarian.Facing) >= 0.0f ? 1.0f : -1.0f;
    float const off = OffFacing(nefarian.Position, nefarian.Facing, self);
    bool const inFront = off < Pi / 2.0f;
    float const safeOff = inFront
        ? DegToRad(BreathHalfAngleDeg + WarriorFrontMarginDeg + 8.0f)
        : Pi - DegToRad(TailLashHalfAngleDeg + 8.0f + 8.0f);
    float const radius = std::clamp(Length(delta), 16.0f, 30.0f);
    for (float extra : { 0.0f, 10.0f, 20.0f, 30.0f })
        for (float scale : { 1.0f, 0.8f, 1.2f })
        {
            float const bearing = nefarian.Facing + side
                * (inFront ? safeOff + DegToRad(extra) : safeOff - DegToRad(extra));
            LocalPoint const point = Offset(nefarian.Position, bearing, radius * scale);
            if (FloorPointSafe(context, point, context.Plan.IsTank(context.Bot.Guid)))
                return MakeGoal(context, MovePurpose::Kite, Surface::Floor, point, 1.5f, true);
        }
    return std::nullopt;
}

inline std::optional<SurfaceGoal> KiteGoal(MovementContext const& context)
{
    if (context.Plan.IsTank(context.Bot.Guid))
        return std::nullopt;
    ActorSnapshot const* warrior = ChasingBoneWarrior(context.View, context.Bot);
    if (!warrior || IsBoneWarriorHeld(*warrior))
        return std::nullopt;
    LocalPoint const self = BotLocal(context);
    LocalPoint const from = WorldToLocal(warrior->Position);
    // Ring kite around the arena centre, away from the warrior.
    float const selfAngle = Length(self) < 1.0f ? 0.0f : AngleOf(self);
    float const warriorAngle = Length(from) < 1.0f ? selfAngle + Pi
        : AngleOf(from);
    float const direction = NormalizeSigned(selfAngle - warriorAngle) >= 0.0f
        ? 1.0f : -1.0f;
    float const radius = std::clamp(Length(self), 16.0f, 26.0f);
    for (float step : { 0.45f, 0.3f, 0.6f })
    {
        LocalPoint const point = Polar(selfAngle + direction * step, radius);
        if (FloorPointSafe(context, point, false)
            && WarriorPointSafe(context.View, point))
            return MakeGoal(context, MovePurpose::Kite, Surface::Floor, point,
                2.5f, true);
    }
    std::optional<LocalPoint> const fallback = SafeNear(context, self,
        AngleOf({ self.X - from.X, self.Y - from.Y }), 10.0f, false);
    if (!fallback)
        return std::nullopt;
    return MakeGoal(context, MovePurpose::Kite, Surface::Floor, *fallback, 2.5f,
        true);
}
}

#endif
