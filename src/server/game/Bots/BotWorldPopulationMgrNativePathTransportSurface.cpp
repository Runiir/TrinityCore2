#include "Bots/BotWorldPopulationMgrNativePathTransportSurface.h"
#include "Bots/BotValidationRouteNativeApproach.h"
#include "Bots/BotWorldPopulationMgrValidationRouteBoardingAction.h"

#include "GameObject.h"
#include "GameObjectModel.h"
#include "GridDefines.h"
#include "Map.h"
#include "ModelIgnoreFlags.h"
#include "MotionMaster.h"
#include "Movement/Spline/MoveSpline.h"
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

// Floor samples every SurfaceSampleStepYards along the straight segment, at
// the segment's own linearly interpolated height (the height the point
// spline moves at), plus line of sight along it at knee, waist and head
// height through static geometry and every collidable gameobject.
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
    float const height = std::max(bot->GetCollisionHeight(), 1.0f);
    probe.CollisionFree = true;
    for (float const lift : { std::max(0.6f, 0.3f * height), 0.6f * height, 0.9f * height })
        if (!map->isInLineOfSight(phase, from.x, from.y, from.z + lift, to.x, to.y,
                to.z + lift, LINEOFSIGHT_ALL_CHECKS, VMAP::ModelIgnoreFlags::Nothing))
            probe.CollisionFree = false;
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

    // The whole body clears the lip: no floor under the centre or the
    // collision radius around it within a walkable step-down.
    float const radius = std::max(bot->GetFloatValue(UNIT_FIELD_BOUNDINGRADIUS),
        Route::PlayerBoundingRadiusYards);
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

// The ordinary point generator owns the active slot and its spline ends at
// the requested world point (a passenger's spline is transport-local).
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
    if (BotMoving(bot))
        return Outcome::Retryable("native_surface_walk_moving");
    if (bot->HasUnitState(UNIT_STATE_NOT_MOVE))
        return Outcome::Retryable("native_surface_walk_immobilized");

    G3D::Vector3 const from(bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ());
    G3D::Vector3 const to(action.X, action.Y, action.Z);
    SegmentProbe const probe = ProbeSegment(bot, transport, from, to,
        action.FloorToleranceYards);
    Route::ApproachVerdict const verdict = Route::ValidateSurfaceWalk(probe.Samples,
        probe.Length, probe.CollisionFree, action.EndOnTransport);
    if (!verdict.Ok)
        return Outcome::Retryable("native_" + verdict.Reason);
    // The platform keeps still for the whole walk and the boarding after it.
    if (Boarding::TransportStationaryMs(transport)
        < Route::WalkTimeMs(probe.Length, NativeGroundSpeed(bot)) + Route::ApproachBoardLatencyMs)
        return Outcome::Retryable("native_surface_walk_transport_moving");

    AbandonMovementPreventingCast(bot);
    bot->GetMotionMaster()->MovePoint(0, to.x, to.y, to.z, false);
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
    if (BotMoving(bot))
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
    // left the lip: the first candidate along that heading whose footprint
    // is over the void starts the fall (never beyond MaxStepOffYards).
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
    Route::ApproachVerdict verdict{ false, "ledge_drop_step_length_invalid" };
    G3D::Vector3 chosen;
    for (float step = Route::SurfaceSampleStepYards; step <= Route::MaxStepOffYards + 1e-3f;
        step += Route::SurfaceSampleStepYards)
    {
        G3D::Vector3 const candidate(fromX + headingX * step, fromY + headingY * step, fromZ);
        verdict = Route::ValidateLedgeDrop(drop,
            ProbeLedgeDrop(bot, transport, candidate, action.FloorToleranceYards));
        if (verdict.Ok)
        {
            chosen = candidate;
            break;
        }
        if (!Route::StepOffCandidateAdvances(verdict.Reason))
            break;
    }
    if (!verdict.Ok)
        return Outcome::Retryable("native_" + verdict.Reason);
    // The landing was proven against the platform where it is now: it must
    // keep still for the step, the whole native fall and the boarding after.
    if (Boarding::TransportStationaryMs(transport)
        < Route::WalkTimeMs(std::hypot(chosen.x - fromX, chosen.y - fromY), NativeGroundSpeed(bot))
            + Route::NativeFallTimeMs(fromZ - action.LandingZ) + Route::ApproachBoardLatencyMs)
        return Outcome::Retryable("native_ledge_drop_transport_moving");

    // Stand at the lip like a client: the report sets Player::m_lastFallZ
    // to the height the fall starts from, as every client packet does.
    if (!Boarding::ReportStandingPosition(bot))
        return Outcome::Unsafe("native_ledge_drop_active_mover_unavailable");
    AbandonMovementPreventingCast(bot);
    bot->GetMotionMaster()->MovePoint(0, chosen.x, chosen.y, chosen.z, false);
    return PointSplineLaunched(bot, chosen)
        ? Outcome::Submitted("native_ledge_drop_step_off_submitted")
        : Outcome::Retryable("native_ledge_drop_step_off_not_launched");
}

// Gravity does not wait for the platform: a stationary member over the void
// after its step falls whatever the transport does now. A passenger's fall
// spline runs in the transport's own frame (MoveSplineInit transforms it).
Outcome ExecuteFall(Player* bot)
{
    if (Boarding::NativeFallSplineActive(bot))
        return Outcome::Submitted("native_ledge_drop_fall_in_progress");
    if (bot->movespline->Initialized() && !bot->movespline->Finalized())
        return Outcome::Retryable("native_ledge_drop_step_still_running");
    // MoveFall's own grounding rule: its floor is already under the feet.
    float const floor = bot->GetMapHeight(bot->GetPositionX(), bot->GetPositionY(),
        bot->GetPositionZ(), true, MAX_FALL_DISTANCE);
    if (floor > INVALID_HEIGHT && std::fabs(bot->GetPositionZ() - floor) < 0.1f)
        return Outcome::Committed("native_ledge_drop_already_grounded");

    bot->GetMotionMaster()->MoveFall();
    if (Boarding::NativeFallSplineActive(bot)
        && bot->GetMotionMaster()->GetMotionSlotType(MOTION_SLOT_CONTROLLED) == EFFECT_MOTION_TYPE)
        return Outcome::Submitted("native_ledge_drop_fall_submitted");
    return Outcome::Retryable(bot->HasUnitState(UNIT_STATE_ROOT | UNIT_STATE_STUNNED)
        ? "native_ledge_drop_fall_rooted" : "native_ledge_drop_fall_not_launched");
}

Outcome ExecuteLand(Player* bot, GameObject const* transport, TransportSurfaceMove const& action)
{
    if (!Boarding::NativeFallInProgress(bot))
        return Outcome::Committed("native_ledge_drop_landing_already_reported");
    if (!Boarding::NativeFallLandingPending(bot))
        return Outcome::Retryable("native_ledge_drop_land_fall_running");
    G3D::Vector3 const position(bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ());
    G3D::Vector3 end = bot->movespline->FinalDestination();
    if (bot->movespline->onTransport)
        if (TransportBase const* carrier = bot->GetDirectTransport())
            carrier->CalculatePassengerPosition(end.x, end.y, end.z);
    if ((end - position).length() > EndpointToleranceYards)
        return Outcome::Retryable("native_ledge_drop_land_not_at_fall_end");
    bool modelAvailable = false;
    bool const onTransport = transport && Boarding::TransportFloorUnderfoot(bot, transport,
        action.FloorToleranceYards, modelAvailable);
    if (!onTransport && !Boarding::StaticFloorUnderfoot(bot, action.FloorToleranceYards))
        return Outcome::Retryable("native_ledge_drop_land_no_floor");

    // The client's own landing report: Player::HandleFall applies native fall
    // damage from the reported fall origin and the falling flags clear.
    if (!Boarding::ReportFallLanding(bot, uint32(std::max(0, bot->movespline->Duration()))))
        return Outcome::Unsafe("native_ledge_drop_active_mover_unavailable");
    return Boarding::NativeFallInProgress(bot)
        ? Outcome::Retryable("native_ledge_drop_landing_not_observed")
        : Outcome::Submitted("native_ledge_drop_landed");
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
    if (action.Kind == TransportSurfaceMove::Stage::Fall)
        return ExecuteFall(bot);

    GameObject* transport = ResolveTransport(bot, action.Transport);
    if (action.Kind == TransportSurfaceMove::Stage::Land)
        return ExecuteLand(bot, transport, action);
    if (!transport)
        return Outcome::Unsafe("native_surface_move_transport_invalid");
    if (!ModelAvailable(transport))
        return Outcome::Unsafe("native_transport_model_unavailable");
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
