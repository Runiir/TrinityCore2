#include "Bots/BotWorldPopulationMgrValidationRouteBoardingAction.h"

#include "Creature.h"
#include "DataStores/DBCStores.h"
#include "GameClient.h"
#include "GameObject.h"
#include "GameObjectModel.h"
#include "GameTime.h"
#include "Map.h"
#include "ModelIgnoreFlags.h"
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
    if (!bot->IsAlive() || bot->GetVehicle() || bot->IsFlying() || bot->IsFalling())
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
