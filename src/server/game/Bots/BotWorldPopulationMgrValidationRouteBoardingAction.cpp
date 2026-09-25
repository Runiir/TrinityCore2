#include "Bots/BotWorldPopulationMgrValidationRouteBoardingAction.h"
#include "Bots/BotValidationRouteNativeFallSpline.h"

#include "Creature.h"
#include "DataStores/DBCStores.h"
#include "GameClient.h"
#include "GameObject.h"
#include "GameObjectModel.h"
#include "GameTime.h"
#include "Map.h"
#include "ModelIgnoreFlags.h"
#include "Movement/Spline/MoveSpline.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Transport.h"
#include "TransportMgr.h"
#include "Vehicle.h"
#include "WorldPacket.h"
#include "WorldSession.h"
#include "Server/Packets/MovementPackets.h"

#include <G3D/Ray.h>
#include <G3D/Vector3.h>

#include <cmath>

namespace
{
using BotActionArbitration::Outcome;

bool BotIsMoving(Player const* bot)
{
    return bot->isMoving() || bot->HasUnitState(UNIT_STATE_MOVING);
}

// A client always reports its own movement as the active mover. Bots are
// allowed movers from login; claim the active-mover slot the way a client
// does (CMSG_SET_ACTIVE_MOVER) before sending a movement report.
bool EnsureActiveMover(Player* bot)
{
    WorldSession* session = bot->GetSession();
    GameClient* client = session ? session->GetGameClient() : nullptr;
    if (!client || !client->IsAllowedToMove(bot))
        return false;
    if (client->GetActivelyMovedUnit() != bot)
    {
        WorldPackets::Movement::SetActiveMover request(
            WorldPacket(CMSG_SET_ACTIVE_MOVER, 8));
        request.ActiveMover = bot->GetGUID();
        session->HandleSetActiveMoverOpcode(request);
    }
    return client->GetActivelyMovedUnit() == bot;
}

// The heartbeat reports exactly the bot's current world position. Only the
// transport block differs between boarding and leaving.
//
// Bot sessions never answer SMSG_TIME_SYNC_REQ, so their clock delta stays 0
// and WorldSession::HandleMovementOpcode logs one "computed movement time
// using clockDelta is erronous" warning per report before falling back to
// GameTime::GetGameTimeMS() (the value reported here). That fallback is the
// correct server time; the warning is expected and bounded by
// TransportContract::MaxSubmissions per member and node.
MovementInfo CurrentPositionReport(Player* bot)
{
    MovementInfo info = bot->m_movementInfo;
    info.guid = bot->GetGUID();
    info.RemoveMovementFlag(MOVEMENTFLAG_MASK_MOVING);
    info.pos.Relocate(bot->GetPositionX(), bot->GetPositionY(),
        bot->GetPositionZ(), bot->GetOrientation());
    info.time = GameTime::GetGameTimeMS();
    info.ResetTransport();
    return info;
}

GameObject* ResolveTransport(Player* bot, ObjectGuid guid)
{
    GameObject* object = bot->GetMap() ? bot->GetMap()->GetGameObject(guid) : nullptr;
    if (!object || !object->IsInWorld() || object->GetMap() != bot->GetMap()
        || object->GetGoType() != GAMEOBJECT_TYPE_TRANSPORT || !object->ToTransportBase())
        return nullptr;
    return object;
}
}

namespace BotValidationRouteBoardingAction
{
// Floors are probed from just above the feet straight down: a surface above
// the feet (a ledge or step the bot is not standing on) never counts.
constexpr float FloorProbeLiftYards = 0.1f;

bool StaticFloorUnderfoot(Player const* bot, float tolerance)
{
    Map* map = bot ? bot->GetMap() : nullptr;
    if (!map)
        return false;
    float const feet = bot->GetPositionZ();
    float const floor = map->GetStaticHeight(bot->GetPhaseShift(),
        bot->GetPositionX(), bot->GetPositionY(), feet + FloorProbeLiftYards,
        true, FloorProbeLiftYards + tolerance);
    return floor > INVALID_HEIGHT && floor <= feet + FloorProbeLiftYards
        && feet - floor <= tolerance;
}

bool TransportFloorUnderfoot(Player const* bot, GameObject const* transport,
    float tolerance, bool& modelAvailable)
{
    modelAvailable = transport && transport->m_model
        && transport->m_model->isCollisionEnabled();
    if (!bot || !modelAvailable)
        return false;
    G3D::Vector3 const origin(bot->GetPositionX(), bot->GetPositionY(),
        bot->GetPositionZ() + FloorProbeLiftYards);
    float distance = FloorProbeLiftYards + tolerance;
    return transport->m_model->intersectRay(
        G3D::Ray::fromOriginAndDirection(origin, G3D::Vector3(0.0f, 0.0f, -1.0f)),
        distance, true, bot->GetPhaseShift(), VMAP::ModelIgnoreFlags::Nothing);
}

std::uint64_t RestRemainingAtLevelMs(GameObject const* transport, float levelZ,
    float tolerance)
{
    using namespace BotValidationRouteNative;
    if (!transport || std::fabs(transport->GetPositionZ() - levelZ) > tolerance)
        return 0;
    GameObjectTemplate const* info = transport->GetGOInfo();
    // Stop-frame transports only move when a script changes their state:
    // the rest is unbounded once a stop state is set and its arrival time
    // (GAMEOBJECT_LEVEL) has passed; while travelling there is no rest.
    if (info && info->transport.Timeto2ndfloor > 0)
        return transport->GetGoState() >= GO_STATE_TRANSPORT_STOPPED
            && GameTime::GetGameTimeMS() >= transport->GetUInt32Value(GAMEOBJECT_LEVEL)
            ? UnboundedRestMs : 0;
    TransportAnimation const* animation =
        sTransportMgr->GetTransportAnimInfo(transport->GetEntry());
    if (!animation || !animation->TotalTime)
        return 0;
    TransportTimeline timeline;
    timeline.PeriodMs = animation->TotalTime;
    for (auto const& [time, node] : animation->Path)
        if (node)
            timeline.ZKeys.emplace_back(time, node->Pos.Z);
    // Cycling transports advance as game time modulo their period.
    std::uint32_t const progress = GameTime::GetGameTimeMS() % timeline.PeriodMs;
    return RestRemainingMs(timeline, progress, levelZ - transport->GetStationaryZ(),
        tolerance);
}

bool TransportAnimatesOnlyVertically(GameObject const* transport)
{
    if (!transport)
        return false;
    TransportAnimation const* animation =
        sTransportMgr->GetTransportAnimInfo(transport->GetEntry());
    // Without an animation GameObjectType::Transport never moves.
    if (!animation)
        return true;
    TransportAnimationEntry const* firstNode = nullptr;
    for (auto const& [time, node] : animation->Path)
    {
        if (!node)
            continue;
        if (!firstNode)
            firstNode = node;
        else if (std::fabs(node->Pos.X - firstNode->Pos.X) > 1e-3f
            || std::fabs(node->Pos.Y - firstNode->Pos.Y) > 1e-3f)
            return false;
    }
    TransportRotationEntry const* firstRotation = nullptr;
    for (auto const& [time, rotation] : animation->Rotations)
    {
        if (!rotation)
            continue;
        if (!firstRotation)
            firstRotation = rotation;
        else if (std::fabs(rotation->X - firstRotation->X) > 1e-4f
            || std::fabs(rotation->Y - firstRotation->Y) > 1e-4f
            || std::fabs(rotation->Z - firstRotation->Z) > 1e-4f
            || std::fabs(rotation->W - firstRotation->W) > 1e-4f)
            return false;
    }
    return true;
}

std::uint64_t TransportStationaryMs(GameObject const* transport)
{
    if (!TransportAnimatesOnlyVertically(transport))
        return 0;
    return RestRemainingAtLevelMs(transport, transport->GetPositionZ(),
        BotValidationRouteNative::StationaryLevelToleranceYards);
}

bool NativeFallSplineActive(Player const* bot)
{
    return bot && BotValidationRouteNativeFall::SplineActive(*bot->movespline);
}

bool NativeFallInProgress(Player const* bot)
{
    return bot && (bot->HasUnitMovementFlag(MOVEMENTFLAG_FALLING | MOVEMENTFLAG_FALLING_FAR)
        || NativeFallSplineActive(bot));
}

// The falling flags still set with no spline running (the fall finished, or a
// stop mid-air cleared it: a stun, a root or a cast path's StopMoving) mean
// the landing is owed: the landing step either finds a floor and reports it
// (native fall damage from the unchanged fall origin) or falls on from here.
bool NativeFallLandingPending(Player const* bot)
{
    return bot && BotValidationRouteNativeFall::LandingPending(
        bot->HasUnitMovementFlag(MOVEMENTFLAG_FALLING | MOVEMENTFLAG_FALLING_FAR),
        *bot->movespline);
}

// A passenger reports its current transport block, as a client standing on
// a transport does, so the report never leaves or changes the transport.
static MovementInfo CurrentStandingReport(Player* bot)
{
    MovementInfo info = CurrentPositionReport(bot);
    if (bot->GetTransport())
    {
        info.transport = bot->m_movementInfo.transport;
        info.transport.time = GameTime::GetGameTimeMS();
    }
    return info;
}

// The movement handler returns silently in several cases (a teleport in
// progress, a transport offset beyond 75 yd, a position a grid away): a
// report counts only when the mover's movement info now carries it. Bot
// sessions never answer time sync, so the handler stamps the report with
// GameTime::GetGameTimeMS(), the time it was built with.
static bool ReportApplied(Player const* bot, MovementInfo const& report)
{
    MovementInfo const& now = bot->m_movementInfo;
    return now.time == report.time && !now.HasMovementFlag(MOVEMENTFLAG_MASK_MOVING)
        && now.transport.guid == report.transport.guid
        && now.pos.GetExactDist(&report.pos) < 0.01f;
}

bool ReportStandingPosition(Player* bot)
{
    if (!bot || !bot->IsInWorld() || !EnsureActiveMover(bot))
        return false;
    MovementInfo report = CurrentStandingReport(bot);
    report.jump.fallTime = 0;
    bot->GetSession()->HandleMovementOpcode(MSG_MOVE_HEARTBEAT, report);
    return ReportApplied(bot, report);
}

bool ReportFallLanding(Player* bot, std::uint32_t fallTimeMs)
{
    if (!bot || !bot->IsInWorld() || !EnsureActiveMover(bot))
        return false;
    MovementInfo report = CurrentStandingReport(bot);
    report.jump.fallTime = fallTimeMs;
    bot->GetSession()->HandleMovementOpcode(MSG_MOVE_FALL_LAND, report);
    return ReportApplied(bot, report);
}

BotValidationRouteNative::TransportFact ObserveTransport(GameObject const* transport)
{
    BotValidationRouteNative::TransportFact fact;
    if (!transport || !transport->IsInWorld()
        || transport->GetGoType() != GAMEOBJECT_TYPE_TRANSPORT)
        return fact;
    fact.Present = true;
    fact.Entry = transport->GetEntry();
    fact.SpawnId = transport->GetSpawnId();
    fact.GoState = uint32(transport->GetGoState());
    // GAMEOBJECT_LEVEL carries the native arrival time of a stop-frame move.
    fact.ArrivedAtStop = fact.GoState >= BotValidationRouteNative::GoStateTransportStopped
        && GameTime::GetGameTimeMS() >= transport->GetUInt32Value(GAMEOBJECT_LEVEL);
    fact.PositionX = transport->GetPositionX();
    fact.PositionY = transport->GetPositionY();
    fact.PositionZ = transport->GetPositionZ();
    fact.Orientation = transport->GetOrientation();
    fact.StationaryZ = transport->GetStationaryZ();
    return fact;
}

BotActionArbitration::Outcome EnterVehicle(Player* bot,
    BotNativeAction::VehicleEnter const& action)
{
    Creature* vehicleCreature =
        ObjectAccessor::GetCreatureOrPetOrVehicle(*bot, action.Target);
    Vehicle* kit = vehicleCreature ? vehicleCreature->GetVehicleKit() : nullptr;
    if (!vehicleCreature || !vehicleCreature->IsInWorld() || !kit)
        return Outcome::Unsafe("native_vehicle_enter_target_invalid");
    if (action.Seat >= 0 && kit->Seats.find(action.Seat) == kit->Seats.end())
        return Outcome::Unsafe("native_vehicle_enter_seat_unknown");

    if (bot->GetVehicleBase() == vehicleCreature)
    {
        if (action.Seat < 0 || bot->GetTransSeat() == action.Seat)
            return Outcome::Committed("native_vehicle_enter_already_seated");
        // Switching seats uses the passenger's own seat request.
        VehicleSeatEntry const* seat = kit->GetSeatForPassenger(bot);
        if (!seat || !seat->CanSwitchFromSeat())
            return Outcome::Unsafe("native_vehicle_seat_switch_forbidden");
        if (!kit->HasEmptySeat(int8(action.Seat)))
            return Outcome::Retryable("native_vehicle_seat_occupied");
        WorldPacket request(CMSG_REQUEST_VEHICLE_SWITCH_SEAT, 9);
        request << vehicleCreature->GetGUID().WriteAsPacked();
        request << int8(action.Seat);
        bot->GetSession()->HandleChangeSeatsOnControlledVehicle(request);
        return bot->GetVehicleBase() == vehicleCreature && bot->GetTransSeat() == action.Seat
            ? Outcome::Submitted("native_vehicle_seat_switch_submitted")
            : Outcome::Retryable("native_vehicle_seat_switch_not_observed");
    }
    if (bot->GetVehicle())
        return Outcome::Retryable("native_vehicle_enter_on_other_vehicle");
    if (!vehicleCreature->HasFlag(UNIT_NPC_FLAGS, UNIT_NPC_FLAG_SPELLCLICK))
        return Outcome::Unsafe("native_spellclick_target_invalid");
    if (!bot->IsWithinDistInMap(vehicleCreature, INTERACTION_DISTANCE))
        return Outcome::Retryable("native_vehicle_enter_out_of_range");
    if (action.Seat >= 0 && !kit->HasEmptySeat(int8(action.Seat)))
        return Outcome::Retryable("native_vehicle_seat_occupied");

    // The native spellclick chooses the entry seat; a declared seat is then
    // reached with the ordinary seat-switch request on a later tick.
    WorldPacket click(CMSG_SPELLCLICK, sizeof(uint64));
    click << action.Target;
    bot->GetSession()->HandleSpellClick(click);
    return Outcome::Submitted("native_vehicle_enter_spellclick_submitted");
}

BotActionArbitration::Outcome BoardTransport(Player* bot,
    BotNativeAction::TransportBoard const& action)
{
    GameObject* object = ResolveTransport(bot, action.Transport);
    if (!object)
        return Outcome::Unsafe("native_transport_target_invalid");
    if (TransportBase* current = bot->GetTransport())
        return current->GetTransportGUID() == object->GetGUID()
            ? Outcome::Committed("native_transport_already_aboard")
            : Outcome::Retryable("native_transport_on_other_transport");
    // A finalized native fall keeps its spline's falling attribute until the
    // next spline; only a running fall or the falling flags block boarding.
    if (!bot->IsAlive() || bot->GetVehicle() || bot->IsFlying() || NativeFallInProgress(bot))
        return Outcome::Retryable("native_transport_board_state_invalid");
    if (BotIsMoving(bot))
        return Outcome::Retryable("native_transport_board_moving");

    // The bot must already stand on this platform's own surface: boarding
    // reports the current position and never moves the bot onto it. Static
    // ground that merely lies inside the model's bounding box is not enough,
    // and a closer static floor means the bot is not standing on the platform.
    bool modelAvailable = false;
    bool const onPlatform = TransportFloorUnderfoot(bot, object,
        action.FloorToleranceYards, modelAvailable);
    if (!modelAvailable)
        return Outcome::Unsafe("native_transport_model_unavailable");
    if (!onPlatform)
        return Outcome::Retryable("native_transport_board_no_platform_floor");
    if (StaticFloorUnderfoot(bot, action.FloorToleranceYards))
        return Outcome::Retryable("native_transport_board_static_floor_underfoot");
    TransportBase* transport = object->ToTransportBase();
    float x = bot->GetPositionX();
    float y = bot->GetPositionY();
    float z = bot->GetPositionZ();
    float o = bot->GetOrientation();
    transport->CalculatePassengerOffset(x, y, z, &o);
    if (!EnsureActiveMover(bot))
        return Outcome::Unsafe("native_transport_active_mover_unavailable");

    MovementInfo report = CurrentPositionReport(bot);
    report.transport.guid = object->GetGUID();
    report.transport.pos.Relocate(x, y, z, o);
    report.transport.time = GameTime::GetGameTimeMS();
    bot->GetSession()->HandleMovementOpcode(MSG_MOVE_HEARTBEAT, report);

    TransportBase* boarded = bot->GetTransport();
    return boarded && boarded->GetTransportGUID() == object->GetGUID()
        ? Outcome::Submitted("native_transport_board_submitted")
        : Outcome::Retryable("native_transport_board_not_observed");
}

BotActionArbitration::Outcome LeaveTransport(Player* bot,
    BotNativeAction::TransportLeave const& action)
{
    TransportBase* current = bot->GetTransport();
    if (!current || current->GetTransportGUID() != action.Transport)
        return Outcome::NotApplicable("native_transport_not_aboard");
    if (BotIsMoving(bot))
        return Outcome::Retryable("native_transport_leave_moving");

    // Leave only where static ground is directly underfoot, so the report
    // cannot leave the bot standing in the air once the platform moves on.
    if (!StaticFloorUnderfoot(bot, action.FloorToleranceYards))
        return Outcome::Retryable("native_transport_leave_no_static_floor");
    if (!EnsureActiveMover(bot))
        return Outcome::Unsafe("native_transport_active_mover_unavailable");

    MovementInfo report = CurrentPositionReport(bot);
    bot->GetSession()->HandleMovementOpcode(MSG_MOVE_HEARTBEAT, report);
    return bot->GetTransport()
        ? Outcome::Retryable("native_transport_leave_not_observed")
        : Outcome::Submitted("native_transport_leave_submitted");
}
}
