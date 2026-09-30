#include "Bots/BotWorldPopulationMgrNativePathTransportLiquid.h"
#include "Bots/BotLiquidBodyClearance.h"
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
#include <vector>

namespace
{
using BotActionArbitration::Outcome;
using BotNativeAction::TransportSurfaceMove;
namespace Liquid = BotValidationRouteNativeLiquid;
namespace Boarding = BotValidationRouteBoardingAction;
namespace Clear = BotLiquidBodyClearance;

constexpr float EndpointToleranceYards = 0.25f;
// A running swim is the requested one when it ends here at this speed.
constexpr float SwimSpeedToleranceYardsPerSecond = 0.05f;
constexpr float TwoPi = 6.28318530717958647692f;

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

// The body's ray query, the step-off fall's own (ProbeFallBody): static and
// dynamic line of sight, and the platform's model directly (the dynamic tree
// leaves it out while CONFIG_CHECK_GOBJECT_LOS is off). Used by the whole
// body proofs of BotLiquidBodyClearance.h.
struct BodyQuery
{
    Player const* Bot;
    GameObject const* Transport;

    bool operator()(G3D::Vector3 const& origin, G3D::Vector3 const& direction, float length) const
    {
        G3D::Vector3 const end = origin + direction * length;
        if (!Bot->GetMap()->isInLineOfSight(Bot->GetPhaseShift(), origin.x, origin.y, origin.z,
                end.x, end.y, end.z, LINEOFSIGHT_ALL_CHECKS, VMAP::ModelIgnoreFlags::Nothing))
            return true;
        float distance = length;
        return Transport && Transport->m_model->intersectRay(
            G3D::Ray::fromOriginAndDirection(origin, direction), distance, true,
            Bot->GetPhaseShift(), VMAP::ModelIgnoreFlags::Nothing);
    }
};

float BodyRadius(Player const* bot)
{
    return std::max(bot->GetFloatValue(UNIT_FIELD_BOUNDINGRADIUS),
        Clear::Body::MinBodyRadiusYards);
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

// The height of that surface (its nearest hit from above), if any.
bool TransportFloorZ(Player const* bot, GameObject const* transport, float x, float y,
    float z, float tolerance, float& floorZ)
{
    G3D::Vector3 const origin(x, y, z + tolerance);
    float distance = 2.0f * tolerance;
    if (!transport->m_model->intersectRay(
            G3D::Ray::fromOriginAndDirection(origin, G3D::Vector3(0.0f, 0.0f, -1.0f)),
            distance, false, bot->GetPhaseShift(), VMAP::ModelIgnoreFlags::Nothing))
        return false;
    floorZ = origin.z - distance;
    return true;
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

Outcome ExecuteSwim(Player* bot, GameObject const* transport, TransportSurfaceMove const& action)
{
    if (bot->GetTransport())
        return Outcome::Retryable("native_liquid_swim_still_aboard");
    if (char const* busy = Busy(bot))
        return Outcome::Retryable(busy);
    G3D::Vector3 const from(bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ());
    G3D::Vector3 const to(action.X, action.Y, action.Z);
    // Slower than the native swim speed when asked (riding up with a rising
    // floor); never faster.
    float const swimSpeed = bot->GetSpeed(MOVE_SWIM);
    float const speed = action.SwimSpeedYardsPerSecond > 0.0f
        ? std::min(action.SwimSpeedYardsPerSecond, swimSpeed) : swimSpeed;
    // The swim already running there at that speed was proven at its launch:
    // re-proving it every decision would cost its whole ray budget again.
    if (SplineRunning(bot) && !bot->movespline->isParabolic()
        && (bot->movespline->FinalDestination() - to).length() <= EndpointToleranceYards
        && std::fabs(bot->movespline->Velocity() - speed) <= SwimSpeedToleranceYardsPerSecond)
        return Outcome::Submitted("native_liquid_swim_in_progress");
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
    // The whole body along the segment and standing at its end
    // (BotLiquidBodyClearance.h), not only its centre line.
    Clear::TrajectoryProof const body = Clear::ProveSwim(from, to, BodyRadius(bot),
        bot->GetCollisionHeight(), BodyQuery{ bot, transport });
    if (!body.Clear())
        return Outcome::Retryable(Clear::SwimBodyObstructedReason);

    Movement::MoveSplineInit init(bot);
    init.MoveTo(to.x, to.y, to.z, false);
    if (action.SwimSpeedYardsPerSecond > 0.0f)
        init.SetVelocity(speed);
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
        // The jump runs to the requested landing or to the nearby one the
        // body proof chose (ChooseClearHop, within MaxLandingShiftYards).
        G3D::Vector3 const end = bot->movespline->FinalDestination();
        G3D::Vector3 const to(action.X, action.Y, action.Z);
        return (end - to).length() <= Clear::MaxLandingShiftYards
            ? Outcome::Progressed("native_liquid_hop_in_flight")
            : Outcome::Retryable("native_liquid_hop_other_jump_in_flight");
    }
    if (char const* busy = Busy(bot))
        return Outcome::Retryable(busy);
    if (SplineRunning(bot))
        return Outcome::Retryable("native_liquid_hop_moving");
    G3D::Vector3 const from(bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ());
    G3D::Vector3 const requested(action.X, action.Y, action.Z);
    LiquidData liquid;
    if (!InLiquidAt(bot, from.x, from.y, from.z, liquid))
        return Outcome::Retryable("native_liquid_hop_not_in_liquid");

    // The requested landing, then the nearby ones on the same rim, until the
    // whole jump is proven (BotLiquidBodyClearance.h): the body along the
    // spline MoveJumpWithGravity will run (its duration from the 3D segment
    // and the velocity passed, its arc the chord plus the parabola,
    // BotValidationRouteNativeLiquid::PlanSplineJump), sampled every 5 ms and
    // reduced to chords, clear of static geometry, every gameobject and the
    // platform's model, standing clear at the landing with half its inner
    // footprint on the surface.
    // A platform that is moving now is refused before any ray is cast.
    if (!Boarding::TransportStationaryMs(transport))
        return Outcome::Retryable("native_liquid_hop_transport_moving");
    float const radius = BodyRadius(bot);
    float const height = bot->GetCollisionHeight();
    float const tolerance = action.FloorToleranceYards;
    BodyQuery const blocked{ bot, transport };
    // The requested landing is the strategy's; a nearby one stands on the
    // model's own surface there, out of the liquid.
    auto landingAt = [&](std::size_t index, G3D::Vector3& landing) -> char const*
    {
        landing = Clear::OffsetLanding(from, requested, Clear::HopLandingOffsets[index]);
        bool onSurface = false;
        if (index == 0)
            onSurface = TransportFloorAt(bot, transport, landing.x, landing.y, landing.z, tolerance);
        else
        {
            LiquidData wet;
            onSurface = TransportFloorZ(bot, transport, landing.x, landing.y, landing.z,
                    2.0f * tolerance, landing.z)
                && !InLiquidAt(bot, landing.x, landing.y, landing.z, wet);
        }
        if (!onSurface)
            return "native_liquid_hop_landing_off_platform";
        if (StaticFloorAt(bot, landing.x, landing.y, landing.z, tolerance))
            return "native_liquid_hop_landing_static_floor";
        return nullptr;
    };
    auto jumpTo = [&](G3D::Vector3 const& landing)
    {
        return Liquid::PlanSplineJump(std::hypot(landing.x - from.x, landing.y - from.y),
            landing.z - from.z, bot->GetSpeed(MOVE_RUN));
    };
    Clear::HopChoice const choice = Clear::ChooseClearHop([&](std::size_t index)
    {
        Clear::HopCandidate candidate;
        G3D::Vector3 landing;
        if (char const* reason = landingAt(index, landing))
        {
            candidate.Reason = reason;
            return candidate;
        }
        Liquid::SplineJump const jump = jumpTo(landing);
        if (!jump.Ok)
        {
            candidate.Reason = "native_" + jump.Reason;
            return candidate;
        }
        candidate.Admissible = true;
        Clear::TrajectoryProof const proof = Clear::ProveHop(from, landing, jump, radius,
            height, blocked);
        candidate.BodyClear = proof.Clear();
        candidate.Rays = proof.Proof.Rays;
        for (int32 k = 0; k < Clear::Body::InnerDirections; ++k)
        {
            float const angle = TwoPi * float(k) / float(Clear::Body::InnerDirections);
            ++candidate.InnerPoints;
            if (TransportFloorAt(bot, transport, landing.x + 0.5f * radius * std::cos(angle),
                    landing.y + 0.5f * radius * std::sin(angle), landing.z, tolerance))
                ++candidate.InnerSupported;
        }
        return candidate;
    });
    if (!choice.Ok)
        return Outcome::Retryable(choice.Reason);
    G3D::Vector3 to;
    landingAt(choice.Index, to);
    Liquid::SplineJump const jump = jumpTo(to);
    // The platform keeps still for the jump and the boarding report after it.
    if (Boarding::TransportStationaryMs(transport)
        < uint64(jump.DurationMs) + Liquid::BoardLatencyMs)
        return Outcome::Retryable("native_liquid_hop_transport_moving");

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
    // The body standing here, knee to head, is empty: a rising surface that
    // has already passed the knee (or a pillar skirt beside it) is inside the
    // body, and boarding there would carry the body inside the platform.
    std::uint32_t rays = 0;
    if (!Clear::BodyClearAt(G3D::Vector3(bot->GetPositionX(), bot->GetPositionY(),
            bot->GetPositionZ()), BodyRadius(bot), bot->GetCollisionHeight(),
            BodyQuery{ bot, transport }, rays))
        return Outcome::Retryable(Clear::EmergeBodyObstructedReason);
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
    GameObject* transport = ResolveTransport(bot, action.Transport);
    // A swim needs no platform, but one it names is proven against: a named
    // platform that does not resolve is refused, not left out of the proof.
    if (action.Kind == TransportSurfaceMove::Stage::Swim)
        return !transport && !action.Transport.IsEmpty()
            ? Outcome::Unsafe("native_liquid_transport_invalid")
            : ExecuteSwim(bot, transport, action);
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
