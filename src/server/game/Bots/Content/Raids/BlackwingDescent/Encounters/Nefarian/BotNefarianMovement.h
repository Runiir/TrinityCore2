#ifndef TRINITY_BOT_NEFARIAN_MOVEMENT_H
#define TRINITY_BOT_NEFARIAN_MOVEMENT_H

// Movement goals for Nefarian's End. Every goal is a destination on the
// GO 207834 transport surface, published twice: as an ordinary world point
// (BotNativeAction::Move, today's executor) and as a SurfaceGoal in the
// transport frame for the transport-surface movement owned by package T
// (boarding, pillar ascent, ledge drop). This file never manufactures a
// position, a jump or a fall; it only chooses destinations.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianLayout.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianTactics.h"
#include <optional>

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

// A bot stands on a pillar top when its transport offset (or, without the
// native placement, its height over the observed origin) exceeds the native
// Shadow of Cowardice threshold.
inline bool OnPillarTop(MovementContext const& context)
{
    if (context.Facts)
        if (TransportPlacement const* placement =
                context.Facts->FindPlacement(context.Bot.Guid))
            return placement->Offset.Z > PlatformFrame::CowardiceLocalZ;
    return context.Bot.Position.Z - context.View.Elevator.OriginZ
        > PlatformFrame::CowardiceLocalZ - 1.5f;
}

inline SurfaceGoal MakeGoal(MovementContext const& context, MovePurpose purpose,
    Surface surface, LocalPoint local, float tolerance, bool urgent,
    int pillar = -1)
{
    SurfaceGoal goal;
    goal.Purpose = purpose;
    goal.Target = surface;
    goal.Local = local;
    goal.LocalZ = surface == Surface::Floor ? FloorLocalZAt(local)
        : SurfaceLocalZ(surface);
    goal.World = LocalToWorld(local, goal.LocalZ, context.View.Elevator.OriginZ);
    goal.Transport = context.View.Elevator.Guid;
    goal.ArrivalToleranceYards = tolerance;
    goal.Pillar = pillar;
    goal.Urgent = urgent;
    return goal;
}

// Danger rules at a floor point. Onyxia's flank is only avoided while she is
// discharging, and her rear is then the intended refuge (the tank turns her).
inline bool FloorPointSafe(MovementContext const& context, LocalPoint point,
    bool isTank)
{
    if (!OnFloorArea(point))
        return false;
    for (ActorSnapshot const* fire : context.View.Fires)
        if (Distance(WorldToLocal(fire->Position), point)
            < ShadowblazeRadius + 4.0f)
            return false;
    if (isTank)
        return true;
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
            12.0f, false);
        if (point)
            return MakeGoal(context, MovePurpose::BreathEscape, Surface::Floor,
                *point, 2.0f, true);
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
        if (FloorPointSafe(context, point, false))
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
