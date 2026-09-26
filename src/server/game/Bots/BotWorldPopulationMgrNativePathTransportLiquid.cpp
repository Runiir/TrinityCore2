#include "Bots/BotWorldPopulationMgrNativePathTransportLiquid.h"
#include "Bots/BotValidationRouteNativeLiquid.h"
#include "Bots/BotWorldPopulationMgrValidationRouteBoardingAction.h"

#include "GameObject.h"
#include "GameObjectModel.h"
#include "Map.h"
#include "MapDefines.h"
#include "ModelIgnoreFlags.h"
#include "MotionMaster.h"
#include "Movement/Spline/MoveSpline.h"
#include "Movement/Spline/MoveSplineInit.h"
#include "Player.h"
#include "Transport.h"

#include <G3D/Ray.h>
#include <G3D/Vector3.h>

#include <algorithm>
#include <cmath>
#include <string>

namespace
{
using BotActionArbitration::Outcome;
using BotNativeAction::TransportSurfaceMove;
namespace Liquid = BotValidationRouteNativeLiquid;
namespace Boarding = BotValidationRouteBoardingAction;

constexpr float EndpointToleranceYards = 0.25f;

GameObject* ResolveTransport(Player* bot, ObjectGuid guid)
{
    Map* map = bot->GetMap();
    GameObject* object = map ? map->GetGameObject(guid) : nullptr;
    if (!object || !object->IsInWorld() || object->GetMap() != map
        || object->GetGoType() != GAMEOBJECT_TYPE_TRANSPORT || !object->ToTransportBase()
        || !object->m_model || !object->m_model->isCollisionEnabled())
        return nullptr;
    return object;
}

// The core's own liquid query at a point (Map::GetLiquidStatus with the
// member's collision height): true inside the liquid.
bool InLiquidAt(Player const* bot, float x, float y, float z, LiquidData& data)
{
    ZLiquidStatus const status = bot->GetMap()->GetLiquidStatus(bot->GetPhaseShift(),
        x, y, z, map_liquidHeaderTypeFlags::AllLiquids, &data, bot->GetCollisionHeight());
    return Liquid::InLiquid(status);
}

// Motion that owns the member now: a fall, a controlled effect, a root or
// stun, a spline still running.
char const* Busy(Player const* bot)
{
    if (Boarding::NativeFallInProgress(bot) || bot->IsFlying())
        return "native_liquid_airborne";
    if (bot->HasUnitState(UNIT_STATE_NOT_MOVE))
        return "native_liquid_immobilized";
    if (bot->GetMotionMaster()->GetMotionSlot(MOTION_SLOT_CONTROLLED))
        return "native_liquid_controlled_motion";
    return nullptr;
}

bool SplineRunning(Player const* bot)
{
    return bot->movespline->Initialized() && !bot->movespline->Finalized();
}

// A submitted hop still in the air: the controlled jump spline runs. It is
// reported as progress (not a retry), so its candidate keeps the movement,
// GCD and cast lanes: no heal or cast in the same tick stops the jump short
// of the platform (a cast-time heal stops the member first).
bool HopInFlight(Player const* bot)
{
    return SplineRunning(bot) && bot->movespline->isParabolic()
        && bot->GetMotionMaster()->GetMotionSlotType(MOTION_SLOT_CONTROLLED) == EFFECT_MOTION_TYPE;
}

// The body's straight sweep: static and dynamic line of sight at the feet,
// the waist and the head.
bool SweepClear(Player const* bot, G3D::Vector3 const& from, G3D::Vector3 const& to)
{
    Map* map = bot->GetMap();
    float const height = bot->GetCollisionHeight();
    for (float const lift : { 0.15f, 0.5f * height, 0.9f * height })
        if (!map->isInLineOfSight(bot->GetPhaseShift(), from.x, from.y, from.z + lift,
                to.x, to.y, to.z + lift, LINEOFSIGHT_ALL_CHECKS, VMAP::ModelIgnoreFlags::Nothing))
            return false;
    return true;
}

// This platform's own model surface within `tolerance` of height `z` at a
// point: a downward ray through the model.
bool TransportFloorAt(Player const* bot, GameObject const* transport, float x, float y,
    float z, float tolerance)
{
    G3D::Vector3 const origin(x, y, z + tolerance);
    float distance = 2.0f * tolerance;
    return transport->m_model->intersectRay(
        G3D::Ray::fromOriginAndDirection(origin, G3D::Vector3(0.0f, 0.0f, -1.0f)),
        distance, true, bot->GetPhaseShift(), VMAP::ModelIgnoreFlags::Nothing);
}

bool StaticFloorAt(Player const* bot, float x, float y, float z, float tolerance)
{
    float const floor = bot->GetMap()->GetStaticHeight(bot->GetPhaseShift(), x, y,
        z + tolerance, true, 2.0f * tolerance);
    return floor > INVALID_HEIGHT && floor >= z - tolerance && floor <= z + tolerance;
}

Outcome ExecuteFloat(Player* bot, GameObject* transport, TransportSurfaceMove const& action)
{
    TransportBase const* current = bot->GetTransport();
    if (!current || current->GetTransportGUID() != transport->GetGUID())
        return Outcome::NotApplicable("native_liquid_float_not_aboard");
    if (char const* busy = Busy(bot))
        return Outcome::Retryable(busy);
    if (SplineRunning(bot))
        return Outcome::Retryable("native_liquid_float_moving");
    LiquidData liquid;
    if (!InLiquidAt(bot, bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), liquid))
        return Outcome::Retryable("native_liquid_float_not_in_liquid");
    if (!Liquid::FloatDepthReached(liquid.level, bot->GetPositionZ(), action.FloatDepthYards))
        return Outcome::Retryable("native_liquid_float_too_shallow");
    if (!Boarding::ReportSwimState(bot, true, nullptr))
        return Outcome::Unsafe("native_liquid_float_report_not_applied");
    return bot->GetTransport()
        ? Outcome::Retryable("native_liquid_float_not_observed")
        : Outcome::Submitted("native_liquid_float_submitted");
}

Outcome ExecuteSwim(Player* bot, TransportSurfaceMove const& action)
{
    if (bot->GetTransport())
        return Outcome::Retryable("native_liquid_swim_still_aboard");
    if (char const* busy = Busy(bot))
        return Outcome::Retryable(busy);
    G3D::Vector3 const from(bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ());
    G3D::Vector3 const to(action.X, action.Y, action.Z);
    float const length = (to - from).length();
    if (!(length > 0.05f) || length > Liquid::MaxSwimYards)
        return Outcome::Retryable("native_liquid_swim_length_invalid");
    uint32 const steps = std::max<uint32>(1,
        uint32(std::ceil(length / Liquid::SwimSampleStepYards)));
    for (uint32 i = 0; i <= steps; ++i)
    {
        G3D::Vector3 const point = from + (to - from) * (float(i) / float(steps));
        LiquidData liquid;
        if (!InLiquidAt(bot, point.x, point.y, point.z, liquid))
            return Outcome::Retryable(i == 0 ? "native_liquid_swim_not_in_liquid"
                : "native_liquid_swim_leaves_liquid");
    }
    if (!SweepClear(bot, from, to))
        return Outcome::Retryable("native_liquid_swim_blocked");

    Movement::MoveSplineInit init(bot);
    init.MoveTo(to.x, to.y, to.z, false);
    // Slower than the native swim speed when asked (riding up with a rising
    // floor); never faster.
    float const swimSpeed = bot->GetSpeed(MOVE_SWIM);
    if (action.SwimSpeedYardsPerSecond > 0.0f)
        init.SetVelocity(std::min(action.SwimSpeedYardsPerSecond, swimSpeed));
    bot->GetMotionMaster()->LaunchMoveSpline(std::move(init), 0, MOTION_SLOT_ACTIVE,
        POINT_MOTION_TYPE);
    if (!SplineRunning(bot) || (bot->movespline->FinalDestination() - to).length()
            > EndpointToleranceYards)
        return Outcome::Retryable("native_liquid_swim_not_launched");
    return Outcome::Submitted("native_liquid_swim_submitted");
}

Outcome ExecuteHop(Player* bot, GameObject* transport, TransportSurfaceMove const& action)
{
    if (bot->GetTransport())
        return Outcome::Retryable("native_liquid_hop_still_aboard");
    if (HopInFlight(bot))
    {
        G3D::Vector3 const end = bot->movespline->FinalDestination();
        G3D::Vector3 const to(action.X, action.Y, action.Z);
        return (end - to).length() <= EndpointToleranceYards
            ? Outcome::Progressed("native_liquid_hop_in_flight")
            : Outcome::Retryable("native_liquid_hop_other_jump_in_flight");
    }
    if (char const* busy = Busy(bot))
        return Outcome::Retryable(busy);
    if (SplineRunning(bot))
        return Outcome::Retryable("native_liquid_hop_moving");
    G3D::Vector3 const from(bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ());
    G3D::Vector3 const to(action.X, action.Y, action.Z);
    LiquidData liquid;
    if (!InLiquidAt(bot, from.x, from.y, from.z, liquid))
        return Outcome::Retryable("native_liquid_hop_not_in_liquid");
    if (!TransportFloorAt(bot, transport, to.x, to.y, to.z, action.FloorToleranceYards))
        return Outcome::Retryable("native_liquid_hop_landing_off_platform");
    if (StaticFloorAt(bot, to.x, to.y, to.z, action.FloorToleranceYards))
        return Outcome::Retryable("native_liquid_hop_landing_static_floor");

    float const horizontal = std::hypot(to.x - from.x, to.y - from.y);
    // The jump as the spline MoveJumpWithGravity will run: its duration from
    // the 3D segment and the velocity passed, its arc the chord plus the
    // parabola (BotValidationRouteNativeLiquid::PlanSplineJump).
    Liquid::SplineJump const jump = Liquid::PlanSplineJump(horizontal, to.z - from.z,
        bot->GetSpeed(MOVE_RUN));
    if (!jump.Ok)
        return Outcome::Retryable("native_" + jump.Reason);
    // The platform keeps still for the jump and the boarding report after it.
    if (Boarding::TransportStationaryMs(transport)
        < uint64(jump.DurationMs) + Liquid::BoardLatencyMs)
        return Outcome::Retryable("native_liquid_hop_transport_moving");
    // That arc, segment by segment, clear of the platform and static geometry.
    G3D::Vector3 previous = from;
    for (uint32 i = 1; i <= Liquid::JumpSamples; ++i)
    {
        float const t = jump.DurationSeconds * float(i) / float(Liquid::JumpSamples);
        float const along = t / jump.DurationSeconds;
        G3D::Vector3 const point(from.x + (to.x - from.x) * along,
            from.y + (to.y - from.y) * along,
            Liquid::SplineJumpFeetZ(from.z, to.z - from.z, jump.DurationSeconds, t));
        if (!SweepClear(bot, previous, point))
            return Outcome::Retryable("native_liquid_hop_arc_blocked");
        previous = point;
    }

    bot->GetMotionMaster()->MoveJumpWithGravity(Position(to.x, to.y, to.z,
        bot->GetOrientation()), jump.Velocity, Liquid::JumpGravity);
    if (SplineRunning(bot) && bot->movespline->Duration() != jump.DurationMs)
        return Outcome::Unsafe("native_liquid_hop_spline_duration_mismatch");
    if (!SplineRunning(bot)
        || bot->GetMotionMaster()->GetMotionSlotType(MOTION_SLOT_CONTROLLED) != EFFECT_MOTION_TYPE)
        return Outcome::Retryable("native_liquid_hop_not_launched");
    return Outcome::Submitted("native_liquid_hop_submitted");
}

Outcome ExecuteEmerge(Player* bot, GameObject* transport, TransportSurfaceMove const& action)
{
    if (TransportBase const* current = bot->GetTransport())
        return current->GetTransportGUID() == transport->GetGUID()
            ? Outcome::Committed("native_liquid_emerge_already_aboard")
            : Outcome::Retryable("native_liquid_emerge_on_other_transport");
    if (HopInFlight(bot))
        return Outcome::Progressed("native_liquid_emerge_hop_in_flight");
    if (char const* busy = Busy(bot))
        return Outcome::Retryable(busy);
    // The platform's own surface within the tolerance of the feet, above or
    // below them. The report is made where the swimmer actually is: nothing
    // native lifts a unit that is not a registered passenger, so a floor that
    // has passed the feet is the strategy's typed miss, never a new height.
    if (!TransportFloorAt(bot, transport, bot->GetPositionX(), bot->GetPositionY(),
            bot->GetPositionZ(), action.FloorToleranceYards))
        return Outcome::Retryable("native_liquid_emerge_no_platform_floor");
    if (Boarding::StaticFloorUnderfoot(bot, action.FloorToleranceYards))
        return Outcome::Retryable("native_liquid_emerge_static_floor_underfoot");
    // A swimmer riding up with the rising floor stops where it is, as a
    // client does, before it reports standing on the floor.
    if (SplineRunning(bot))
        bot->StopMoving();
    // Still under the surface (standing on a sunken floor): still swimming.
    LiquidData liquid;
    bool const submerged = InLiquidAt(bot, bot->GetPositionX(), bot->GetPositionY(),
        bot->GetPositionZ(), liquid) && liquid.level - bot->GetPositionZ() > 0.5f;
    if (!Boarding::ReportSwimState(bot, submerged, transport))
        return Outcome::Unsafe("native_liquid_emerge_report_not_applied");
    TransportBase const* boarded = bot->GetTransport();
    return boarded && boarded->GetTransportGUID() == transport->GetGUID()
        ? Outcome::Submitted("native_liquid_emerge_submitted")
        : Outcome::Retryable("native_liquid_emerge_not_observed");
}
}

namespace BotTransportLiquidMovement
{
BotActionArbitration::Outcome Execute(Player* bot, TransportSurfaceMove const& action)
{
    if (!bot || !bot->IsInWorld() || !bot->GetMap() || !bot->GetSession())
        return Outcome::Retryable("native_liquid_bot_unavailable");
    if (!bot->IsAlive())
        return Outcome::Retryable("native_liquid_member_dead");
    if (bot->GetVehicle())
        return Outcome::Retryable("native_liquid_member_in_vehicle");
    if (action.Kind == TransportSurfaceMove::Stage::Swim)
        return ExecuteSwim(bot, action);
    GameObject* transport = ResolveTransport(bot, action.Transport);
    if (!transport)
        return Outcome::Unsafe("native_liquid_transport_invalid");
    if (!Boarding::TransportAnimatesOnlyVertically(transport))
        return Outcome::Unsafe("native_liquid_transport_not_vertical");
    switch (action.Kind)
    {
        case TransportSurfaceMove::Stage::Float:
            return ExecuteFloat(bot, transport, action);
        case TransportSurfaceMove::Stage::Hop:
            return ExecuteHop(bot, transport, action);
        case TransportSurfaceMove::Stage::Emerge:
            return ExecuteEmerge(bot, transport, action);
        default:
            return Outcome::Unsafe("native_liquid_stage_invalid");
    }
}
}
