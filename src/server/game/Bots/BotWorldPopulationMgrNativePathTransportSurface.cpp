#include "Bots/BotWorldPopulationMgrNativePathTransportSurface.h"
#include "Bots/BotWorldPopulationMgrNativePathTransportLiquid.h"
#include "Bots/BotValidationRouteNativeFallSpline.h"
#include "Bots/BotValidationRouteNativeApproach.h"
#include "Bots/BotWorldPopulationMgrValidationRouteBoardingAction.h"

#include "GameObject.h"
#include "GameObjectModel.h"
#include "GridDefines.h"
#include "Map.h"
#include "ModelIgnoreFlags.h"
#include "MotionMaster.h"
#include "Movement/Spline/MoveSpline.h"
#include "Movement/Spline/MoveSplineInit.h"
#include "Player.h"
#include "SharedDefines.h"
#include "SpellAuraDefines.h"
#include "VehicleDefines.h"
#include "World.h"

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
namespace Route = BotValidationRouteNative;
namespace Boarding = BotValidationRouteBoardingAction;

constexpr float Pi = 3.14159265358979323846f;
// A launched spline ends at the requested point, and a finalized fall at
// the bot's position, within this distance.
constexpr float EndpointToleranceYards = 0.25f;

GameObject* ResolveTransport(Player* bot, ObjectGuid guid)
{
    Map* map = bot->GetMap();
    GameObject* object = map ? map->GetGameObject(guid) : nullptr;
    if (!object || !object->IsInWorld() || object->GetMap() != map
        || object->GetGoType() != GAMEOBJECT_TYPE_TRANSPORT || !object->ToTransportBase())
        return nullptr;
    return object;
}

bool ModelAvailable(GameObject const* transport)
{
    return transport && transport->m_model && transport->m_model->isCollisionEnabled();
}

// This transport's own model surface within `tolerance` of height `z`: a
// downward ray through the model, like the boarding floor proof.
bool TransportFloorAt(Player const* bot, GameObject const* transport, float x, float y,
    float z, float tolerance)
{
    if (!ModelAvailable(transport))
        return false;
    G3D::Vector3 const origin(x, y, z + tolerance);
    float distance = 2.0f * tolerance;
    return transport->m_model->intersectRay(
        G3D::Ray::fromOriginAndDirection(origin, G3D::Vector3(0.0f, 0.0f, -1.0f)),
        distance, true, bot->GetPhaseShift(), VMAP::ModelIgnoreFlags::Nothing);
}

bool StaticFloorAt(Map* map, PhaseShift const& phase, float x, float y, float z,
    float tolerance)
{
    float const floor = map->GetStaticHeight(phase, x, y, z + tolerance, true, 2.0f * tolerance);
    return floor > INVALID_HEIGHT && floor >= z - tolerance && floor <= z + tolerance;
}

struct SegmentProbe
{
    std::vector<Route::SurfaceSample> Samples;
    float Length = 0.0f;
    bool CollisionFree = false;
};

float BodyRadius(Player const* bot)
{
    return std::max(bot->GetFloatValue(UNIT_FIELD_BOUNDINGRADIUS),
        Route::PlayerBoundingRadiusYards);
}

// The body's sweep along the segment: line of sight through static geometry
// and every collidable gameobject on the centre line and at half and the full
// collision radius on both sides, from the knee to 0.9 of the collision
// height at most BodySweepLiftStepYards apart (a rail or a pillar corner
// beside the centre line blocks it; see BodySweepSideFractions for the
// sampling limit).
bool BodySweepClear(Player const* bot, G3D::Vector3 const& from, G3D::Vector3 const& to)
{
    Map* map = bot->GetMap();
    PhaseShift const& phase = bot->GetPhaseShift();
    float const length = std::hypot(to.x - from.x, to.y - from.y);
    float const radius = BodyRadius(bot);
    float const sideX = length > 0.0f ? -(to.y - from.y) / length * radius : 0.0f;
    float const sideY = length > 0.0f ? (to.x - from.x) / length * radius : 0.0f;
    for (float const lift : Route::BodySweepLifts(bot->GetCollisionHeight()))
        for (float const side : Route::BodySweepSideFractions)
            if (!map->isInLineOfSight(phase, from.x + side * sideX, from.y + side * sideY,
                    from.z + lift, to.x + side * sideX, to.y + side * sideY, to.z + lift,
                    LINEOFSIGHT_ALL_CHECKS, VMAP::ModelIgnoreFlags::Nothing))
                return false;
    return true;
}

// Floor samples every SurfaceSampleStepYards along the straight segment, at
// the segment's own linearly interpolated height (the height the spline
// moves at), plus the body's sweep along it.
SegmentProbe ProbeSegment(Player const* bot, GameObject const* transport,
    G3D::Vector3 const& from, G3D::Vector3 const& to, float tolerance)
{
    SegmentProbe probe;
    Map* map = bot->GetMap();
    PhaseShift const& phase = bot->GetPhaseShift();
    probe.Length = std::hypot(to.x - from.x, to.y - from.y);
    uint32 const steps = std::max<uint32>(1,
        uint32(std::ceil(probe.Length / Route::SurfaceSampleStepYards)));
    probe.Samples.reserve(steps + 1);
    for (uint32 i = 0; i <= steps; ++i)
    {
        float const t = float(i) / float(steps);
        G3D::Vector3 const point = from + (to - from) * t;
        Route::SurfaceSample sample;
        sample.Along = probe.Length * t;
        sample.StaticFloor = StaticFloorAt(map, phase, point.x, point.y, point.z, tolerance);
        sample.TransportFloor = TransportFloorAt(bot, transport, point.x, point.y, point.z,
            tolerance);
        probe.Samples.push_back(sample);
    }
    probe.CollisionFree = BodySweepClear(bot, from, to);
    return probe;
}

// Everything a step-off from the bot's feet to `stepOff` would do: the level
// walk off the lip, the footprint where the fall starts, and the floor
// MotionMaster::MoveFall lands on from there (its own Map::GetHeight query).
Route::LedgeDropProbe ProbeLedgeDrop(Player* bot, GameObject const* transport,
    G3D::Vector3 const& stepOff, float tolerance)
{
    Route::LedgeDropProbe probe;
    Map* map = bot->GetMap();
    PhaseShift const& phase = bot->GetPhaseShift();
    G3D::Vector3 const from(bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ());
    SegmentProbe step = ProbeSegment(bot, transport, from, stepOff, tolerance);
    probe.Step = std::move(step.Samples);
    probe.StepLengthYards = step.Length;
    probe.StepZ = stepOff.z;
    probe.StepCollisionFree = step.CollisionFree;
    // Past the lip the ground must fall away at once: any floor within a
    // walkable step-down under an unsupported sample makes it a slope.
    for (std::size_t i = 0; i < probe.Step.size(); ++i)
    {
        if (probe.Step[i].Supported())
            continue;
        float const t = step.Length > 0.0f ? probe.Step[i].Along / step.Length : 0.0f;
        G3D::Vector3 const point = from + (stepOff - from) * t;
        float const below = map->GetHeight(phase, point.x, point.y, point.z, true,
            Route::MinLedgeDropYards);
        probe.Step[i].ShallowFloorBelow = below > INVALID_HEIGHT
            && below > point.z - Route::MinLedgeDropYards;
    }

    // The whole body clears the lip: no floor under the centre or the
    // collision radius around it within a walkable step-down.
    float const radius = BodyRadius(bot);
    for (int32 i = -1; i < 8; ++i)
    {
        float const angle = float(i) * Pi / 4.0f;
        float const x = stepOff.x + (i < 0 ? 0.0f : radius * std::cos(angle));
        float const y = stepOff.y + (i < 0 ? 0.0f : radius * std::sin(angle));
        float const floor = map->GetHeight(phase, x, y, stepOff.z + tolerance, true,
            tolerance + Route::MinLedgeDropYards);
        if (floor > INVALID_HEIGHT && floor > stepOff.z - Route::MinLedgeDropYards)
            ++probe.FootprintSupported;
    }

    float const landing = bot->GetMapHeight(stepOff.x, stepOff.y, stepOff.z, true,
        MAX_FALL_DISTANCE);
    probe.LandingFound = landing > INVALID_HEIGHT;
    probe.LandingZ = landing;
    if (probe.LandingFound)
    {
        float const staticFloor = map->GetStaticHeight(phase, stepOff.x, stepOff.y,
            stepOff.z + Z_OFFSET_FIND_HEIGHT, true, MAX_FALL_DISTANCE);
        probe.LandingOnTransport = TransportFloorAt(bot, transport, stepOff.x, stepOff.y,
                landing, tolerance)
            && !(staticFloor > INVALID_HEIGHT && staticFloor >= landing - tolerance);
        probe.LandingOnStatic = staticFloor > INVALID_HEIGHT
            && std::fabs(staticFloor - landing) <= tolerance;
        probe.LandingInLiquid = map->IsInWater(phase, stepOff.x, stepOff.y, landing + 0.1f);
        probe.PredictedDamagePct = BotTransportSurfaceMovement::PredictFallDamagePct(bot,
            from.z - landing);
    }
    uint32 const maxHealth = bot->GetMaxHealth();
    probe.HealthPct = maxHealth ? float(bot->GetHealth()) / float(maxHealth) : 0.0f;
    return probe;
}

bool BotMoving(Player const* bot)
{
    return bot->isMoving() || bot->HasUnitState(UNIT_STATE_MOVING);
}

float NativeGroundSpeed(Player const* bot)
{
    return bot->GetSpeed(bot->HasUnitMovementFlag(MOVEMENTFLAG_WALKING) ? MOVE_WALK : MOVE_RUN);
}

// A player who starts walking abandons a cast that forbids movement.
void AbandonMovementPreventingCast(Player* bot)
{
    if (bot->HasUnitState(UNIT_STATE_CASTING) && bot->IsMovementPreventedByCasting())
        bot->InterruptNonMeleeSpells(false);
}

// One straight spline in a movement generator that ends as soon as its
// spline is stopped or replaced: GenericMovementGenerator::Reset is a no-op
// and its Update ends on a finalized spline. PointMovementGenerator instead
// keeps UNIT_STATE_ROAMING_MOVE through a stun or root and re-launches its
// line from wherever the member then is (also after a fear or knockback
// expires), which would walk an unchecked line. A passenger's spline is
// transport-local (MoveSplineInit transforms it).
void LaunchCheckedLine(Player* bot, G3D::Vector3 const& destination)
{
    Movement::MoveSplineInit init(bot);
    init.MoveTo(destination.x, destination.y, destination.z, false);
    bot->GetMotionMaster()->LaunchMoveSpline(std::move(init), 0, MOTION_SLOT_ACTIVE,
        POINT_MOTION_TYPE);
}

// A finished MoveFall spline keeps its falling attribute (Unit::IsFalling)
// until another spline replaces it. Turning in place, as Unit::SetFacingTo
// does (with the passenger transform kept), replaces it with a zero-length
// spline, so shared code reads the landed member as grounded. SetFacingTo
// then finalizes it at once (the private Unit::UpdateSplineMovement(1));
// Unit::StopMoving does the same through the public path: the spline becomes
// a finished stop spline and MOVEMENTFLAG_FORWARD clears before the next
// observation.
void SettleAfterLanding(Player* bot)
{
    Movement::MoveSplineInit init(bot);
    init.MoveTo(bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), false);
    init.SetFacing(bot->GetOrientation());
    init.Launch();
    bot->StopMoving();
}

// The checked line owns the active slot and its spline ends at the requested
// world point (a passenger's spline is transport-local).
bool PointSplineLaunched(Player const* bot, G3D::Vector3 const& destination)
{
    if (!bot->movespline->Initialized() || bot->movespline->Finalized()
        || bot->GetMotionMaster()->GetMotionSlotType(MOTION_SLOT_ACTIVE) != POINT_MOTION_TYPE)
        return false;
    G3D::Vector3 end = bot->movespline->FinalDestination();
    if (bot->movespline->onTransport)
        if (TransportBase const* transport = bot->GetDirectTransport())
            transport->CalculatePassengerPosition(end.x, end.y, end.z);
    return (end - destination).length() <= EndpointToleranceYards;
}

Outcome ExecuteWalk(Player* bot, GameObject* transport, TransportSurfaceMove const& action)
{
    if (TransportBase const* current = bot->GetTransport();
        current && current->GetTransportGUID() != transport->GetGUID())
        return Outcome::Retryable("native_surface_walk_on_other_transport");
    if (Boarding::NativeFallInProgress(bot) || bot->IsFlying())
        return Outcome::Retryable("native_surface_walk_airborne");
    if (bot->HasUnitState(UNIT_STATE_NOT_MOVE))
        return Outcome::Retryable("native_surface_walk_immobilized");
    // A controlled effect (fear, knockback, jump) owns the member: a walk
    // queued beneath it would start later from wherever the effect leaves
    // it, unchecked.
    if (bot->GetMotionMaster()->GetMotionSlot(MOTION_SLOT_CONTROLLED))
        return Outcome::Retryable("native_surface_walk_controlled_motion");
    // A new walk may replace a running one (a player changes direction): it
    // is checked, and its spline starts, from where the member is now.

    G3D::Vector3 const from(bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ());
    G3D::Vector3 const to(action.X, action.Y, action.Z);
    SegmentProbe const probe = ProbeSegment(bot, transport, from, to,
        action.FloorToleranceYards);
    Route::ApproachVerdict const verdict = Route::ValidateSurfaceWalk(probe.Samples,
        probe.Length, probe.CollisionFree, action.EndOnTransport, bot->GetTransport() != nullptr);
    if (!verdict.Ok)
        return Outcome::Retryable("native_" + verdict.Reason);
    // The platform keeps still for the whole walk and the boarding after it.
    if (Boarding::TransportStationaryMs(transport)
        < Route::WalkTimeMs(probe.Length, NativeGroundSpeed(bot)) + Route::ApproachBoardLatencyMs)
        return Outcome::Retryable("native_surface_walk_transport_moving");

    AbandonMovementPreventingCast(bot);
    LaunchCheckedLine(bot, to);
    return PointSplineLaunched(bot, to)
        ? Outcome::Submitted("native_surface_walk_submitted")
        : Outcome::Retryable("native_surface_walk_not_launched");
}

Outcome ExecuteStepOff(Player* bot, GameObject* transport, TransportSurfaceMove const& action)
{
    // A ledge is static ground, or a raised part of this transport (a pillar
    // top) under one of its passengers.
    TransportBase const* current = bot->GetTransport();
    if (current && current->GetTransportGUID() != transport->GetGUID())
        return Outcome::Retryable("native_ledge_drop_on_other_transport");
    if (Boarding::NativeFallInProgress(bot) || bot->IsFlying())
        return Outcome::Retryable("native_ledge_drop_airborne");
    if (BotMoving(bot) || bot->GetMotionMaster()->GetMotionSlot(MOTION_SLOT_CONTROLLED))
        return Outcome::Retryable("native_ledge_drop_moving");
    if (bot->HasUnitState(UNIT_STATE_NOT_MOVE))
        return Outcome::Retryable("native_ledge_drop_immobilized");
    bool modelAvailable = false;
    if (!(current ? Boarding::TransportFloorUnderfoot(bot, transport, action.FloorToleranceYards,
            modelAvailable) : Boarding::StaticFloorUnderfoot(bot, action.FloorToleranceYards)))
        return Outcome::Retryable("native_ledge_drop_edge_floor_unverified");

    Route::ApproachContract drop;
    drop.Mode = Route::ApproachMode::LedgeDrop;
    drop.LandingZ = action.LandingZ;
    drop.LandingToleranceYards = action.LandingToleranceYards;
    drop.LandOnTransport = action.LandOnTransport;
    drop.MinHealthAfterFallPct = action.MinHealthAfterFallPct;

    // The step is level at the bot's own feet toward the declared step-off
    // point. Like a client, the member falls as soon as its whole body has
    // left the lip over a proven landing: the first candidate along that
    // heading whose footprint is over the void and under which the native
    // fall lands on the declared floor starts the fall (never beyond
    // MaxStepOffYards; see Route::ChooseStepOff).
    float const fromX = bot->GetPositionX();
    float const fromY = bot->GetPositionY();
    float const fromZ = bot->GetPositionZ();
    float headingX = action.X - fromX;
    float headingY = action.Y - fromY;
    float const declared = std::hypot(headingX, headingY);
    if (!(declared > 0.05f))
        return Outcome::Retryable("native_ledge_drop_step_off_at_member");
    headingX /= declared;
    headingY /= declared;
    auto candidateAt = [=](float step)
    {
        return G3D::Vector3(fromX + headingX * step, fromY + headingY * step, fromZ);
    };
    Route::StepOffChoice const choice = Route::ChooseStepOff(drop, [&](float step)
    {
        return ProbeLedgeDrop(bot, transport, candidateAt(step), action.FloorToleranceYards);
    });
    if (!choice.Verdict.Ok)
        return Outcome::Retryable("native_" + choice.Verdict.Reason);
    G3D::Vector3 const chosen = candidateAt(choice.StepYards);
    // The landing was proven against the platform where it is now: it must
    // keep still for the step, the whole native fall and the boarding after.
    if (Boarding::TransportStationaryMs(transport)
        < Route::WalkTimeMs(std::hypot(chosen.x - fromX, chosen.y - fromY), NativeGroundSpeed(bot))
            + Route::NativeFallTimeMs(fromZ - action.LandingZ) + Route::ApproachBoardLatencyMs)
        return Outcome::Retryable("native_ledge_drop_transport_moving");

    // Stand at the lip like a client: the report sets Player::m_lastFallZ
    // to the height the fall starts from, as every client packet does.
    if (!Boarding::ReportStandingPosition(bot))
        return Outcome::Unsafe("native_ledge_drop_position_report_not_applied");
    AbandonMovementPreventingCast(bot);
    LaunchCheckedLine(bot, chosen);
    return PointSplineLaunched(bot, chosen)
        ? Outcome::Submitted("native_ledge_drop_step_off_submitted")
        : Outcome::Retryable("native_ledge_drop_step_off_not_launched");
}

// MotionMaster::MoveFall from where the member is now; a fall continued
// after a landing without floor is progress of the same drop. A root or stun
// holds a unit where it is (MoveFall declines): nothing was submitted and
// nothing failed, so that is not a counted rejection.
Outcome LaunchNativeFall(Player* bot, bool fallingOn)
{
    bot->GetMotionMaster()->MoveFall();
    if (Boarding::NativeFallSplineActive(bot)
        && bot->GetMotionMaster()->GetMotionSlotType(MOTION_SLOT_CONTROLLED) == EFFECT_MOTION_TYPE)
        return fallingOn ? Outcome::Progressed("native_ledge_drop_fell_again")
            : Outcome::Submitted("native_ledge_drop_fall_submitted");
    if (bot->HasUnitState(UNIT_STATE_ROOT | UNIT_STATE_STUNNED))
        return Outcome::NotApplicable("native_ledge_drop_fall_held_by_root");
    return Outcome::Retryable("native_ledge_drop_fall_not_launched");
}

// A stationary member over the void after its step falls at once, onto the
// floor MoveFall's own query finds under it now. A passenger's fall spline
// runs in the transport's own frame (MoveSplineInit transforms it).
Outcome ExecuteFall(Player* bot, TransportSurfaceMove const& action)
{
    if (Boarding::NativeFallSplineActive(bot))
        return Outcome::Submitted("native_ledge_drop_fall_in_progress");
    // Another spline (a knockback arc, say) still owns the member: gravity
    // resumes when it ends. Not a failed submission.
    if (bot->movespline->Initialized() && !bot->movespline->Finalized())
        return Outcome::NotApplicable("native_ledge_drop_fall_waiting_for_motion");
    // MoveFall's own grounding rule: its floor is already under the feet.
    float const floor = bot->GetMapHeight(bot->GetPositionX(), bot->GetPositionY(),
        bot->GetPositionZ(), true, MAX_FALL_DISTANCE);
    if (floor > INVALID_HEIGHT && std::fabs(bot->GetPositionZ() - floor) < 0.1f)
        return Outcome::Committed("native_ledge_drop_already_grounded");
    // The step-off proved the landing only where the step was to end. A step
    // cut short or displaced over the void can stand where that same query
    // does not find the declared floor (under the Nefarian platform's north
    // half it finds the model's underside): refuse, counted, instead of a
    // fall through the platform. The node then ends typed on exhaustion.
    if (!Route::FallLandsOnDeclaredFloor(floor > INVALID_HEIGHT, floor, action.LandingZ,
            action.LandingToleranceYards))
        return Outcome::Retryable("native_ledge_drop_fall_landing_mismatch");

    // No generator may resume a line through the air after the fall.
    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    // The fall starts here: the client's standing report sets the fall origin
    // (also when encounter code falls without a step-off first).
    if (!Boarding::ReportStandingPosition(bot))
        return Outcome::Unsafe("native_ledge_drop_position_report_not_applied");
    return LaunchNativeFall(bot, false);
}

Outcome ExecuteLand(Player* bot, GameObject const* transport, TransportSurfaceMove const& action)
{
    if (!Boarding::NativeFallInProgress(bot))
        return Outcome::Committed("native_ledge_drop_landing_already_reported");
    if (!Boarding::NativeFallLandingPending(bot))
        return Outcome::Retryable("native_ledge_drop_land_fall_running");
    // A finished fall spline ends where the member is; a stop mid-air cleared
    // the spline (no end to compare), and the member is where it stopped.
    if (BotValidationRouteNativeFall::EndpointKnown(*bot->movespline))
    {
        G3D::Vector3 const position(bot->GetPositionX(), bot->GetPositionY(),
            bot->GetPositionZ());
        G3D::Vector3 end = bot->movespline->FinalDestination();
        if (bot->movespline->onTransport)
            if (TransportBase const* carrier = bot->GetDirectTransport())
                carrier->CalculatePassengerPosition(end.x, end.y, end.z);
        if ((end - position).length() > EndpointToleranceYards)
            return Outcome::Retryable("native_ledge_drop_land_not_at_fall_end");
    }
    // The floor the fall aimed at may have moved away during it (a platform
    // leaving its stop). With no floor under the feet the member keeps
    // falling from here; the landing is reported only onto a verified floor,
    // and continuing a fall is never a failed submission.
    bool modelAvailable = false;
    bool const onTransport = transport && Boarding::TransportFloorUnderfoot(bot, transport,
        action.FloorToleranceYards, modelAvailable);
    float const floor = bot->GetMapHeight(bot->GetPositionX(), bot->GetPositionY(),
        bot->GetPositionZ(), true, MAX_FALL_DISTANCE);
    bool const onFloor = onTransport || Boarding::StaticFloorUnderfoot(bot, action.FloorToleranceYards)
        || (floor > INVALID_HEIGHT && std::fabs(bot->GetPositionZ() - floor) <= action.FloorToleranceYards);
    if (!onFloor)
        return LaunchNativeFall(bot, true);

    // The client's own landing report: Player::HandleFall applies native fall
    // damage from the reported fall origin and the falling flags clear.
    if (!Boarding::ReportFallLanding(bot,
            uint32(BotValidationRouteNativeFall::ReportedFallTimeMs(*bot->movespline))))
        return Outcome::Unsafe("native_ledge_drop_position_report_not_applied");
    if (Boarding::NativeFallInProgress(bot))
        return Outcome::Retryable("native_ledge_drop_landing_not_observed");
    SettleAfterLanding(bot);
    return Outcome::Submitted("native_ledge_drop_landed");
}
}

namespace BotTransportSurfaceMovement
{
BotActionArbitration::Outcome Execute(Player* bot, TransportSurfaceMove const& action)
{
    if (!bot || !bot->IsInWorld() || !bot->GetMap() || !bot->GetSession())
        return Outcome::Retryable("native_surface_move_bot_unavailable");
    if (!bot->IsAlive())
        return Outcome::Retryable("native_surface_move_member_dead");
    if (bot->GetVehicle())
        return Outcome::Retryable("native_surface_move_member_in_vehicle");
    // The swimmer's stages (a platform sinking into liquid).
    if (action.Kind == TransportSurfaceMove::Stage::Float
        || action.Kind == TransportSurfaceMove::Stage::Swim
        || action.Kind == TransportSurfaceMove::Stage::Hop
        || action.Kind == TransportSurfaceMove::Stage::Emerge)
        return BotTransportLiquidMovement::Execute(bot, action);
    if (action.Kind == TransportSurfaceMove::Stage::Fall)
        return ExecuteFall(bot, action);

    GameObject* transport = ResolveTransport(bot, action.Transport);
    if (action.Kind == TransportSurfaceMove::Stage::Land)
        return ExecuteLand(bot, transport, action);
    if (!transport)
        return Outcome::Unsafe("native_surface_move_transport_invalid");
    if (!ModelAvailable(transport))
        return Outcome::Unsafe("native_transport_model_unavailable");
    // Stationarity is judged from the animation's height keys: only a
    // platform whose path never moves sideways or turns qualifies.
    if (!Boarding::TransportAnimatesOnlyVertically(transport))
        return Outcome::Unsafe("native_surface_move_transport_not_vertical");
    if (action.Kind == TransportSurfaceMove::Stage::StepOff)
        return ExecuteStepOff(bot, transport, action);
    return ExecuteWalk(bot, transport, action);
}

float PredictFallDamagePct(Player const* bot, float height)
{
    if (!bot)
        return 0.0f;
    bool const negated = bot->IsGameMaster() || bot->HasAuraType(SPELL_AURA_HOVER)
        || bot->HasAuraType(SPELL_AURA_FEATHER_FALL) || bot->HasAuraType(SPELL_AURA_FLY)
        || bot->IsImmunedToDamage(SPELL_SCHOOL_MASK_NORMAL);
    return Route::NativeFallDamageFraction(height,
        float(bot->GetTotalAuraModifier(SPELL_AURA_SAFE_FALL)),
        sWorld->getRate(RATE_DAMAGE_FALL), negated);
}

bool FloorNear(Player const* bot, float band)
{
    Map* map = bot && bot->IsInWorld() ? bot->GetMap() : nullptr;
    if (!map)
        return false;
    float const z = bot->GetPositionZ();
    float const floor = map->GetHeight(bot->GetPhaseShift(), bot->GetPositionX(),
        bot->GetPositionY(), z + band, true, 2.0f * band);
    return floor > INVALID_HEIGHT && floor >= z - band;
}
}
