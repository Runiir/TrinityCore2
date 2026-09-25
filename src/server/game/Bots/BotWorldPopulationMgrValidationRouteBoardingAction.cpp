#include "Bots/BotWorldPopulationMgrValidationRouteBoardingAction.h"

#include "Creature.h"
#include "DataStores/DBCStores.h"
#include "GameClient.h"
#include "GameObject.h"
#include "GameTime.h"
#include "Map.h"
#include "ObjectAccessor.h"
#include "Player.h"
#include "Transport.h"
#include "Vehicle.h"
#include "WorldPacket.h"
#include "WorldSession.h"
#include "Server/Packets/MovementPackets.h"

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
bool DisplayFootprint(GameObject const* transport,
    BotValidationRouteNative::LocalBox& box)
{
    box = BotValidationRouteNative::LocalBox();
    if (!transport)
        return false;
    GameObjectDisplayInfoEntry const* display =
        sGameObjectDisplayInfoStore.LookupEntry(transport->GetDisplayId());
    if (!display)
        return false;
    float const scale = transport->GetObjectScale() > 0.0f ? transport->GetObjectScale() : 1.0f;
    box.MinX = display->GeoBoxMin.X * scale;
    box.MinY = display->GeoBoxMin.Y * scale;
    box.MinZ = display->GeoBoxMin.Z * scale;
    box.MaxX = display->GeoBoxMax.X * scale;
    box.MaxY = display->GeoBoxMax.Y * scale;
    box.MaxZ = display->GeoBoxMax.Z * scale;
    box.Valid = box.MaxX > box.MinX && box.MaxY > box.MinY && box.MaxZ >= box.MinZ;
    return box.Valid;
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

    BotValidationRouteNative::LocalBox box;
    if (!DisplayFootprint(object, box))
        return Outcome::Unsafe("native_transport_footprint_unknown");
    TransportBase* transport = object->ToTransportBase();
    float x = bot->GetPositionX();
    float y = bot->GetPositionY();
    float z = bot->GetPositionZ();
    float o = bot->GetOrientation();
    transport->CalculatePassengerOffset(x, y, z, &o);
    // The bot must already stand on the platform: boarding reports the
    // current position, it never moves the bot onto the transport.
    if (!BotValidationRouteNative::InsideFootprint({ x, y, z, true }, box,
            action.FootprintMarginYards))
        return Outcome::Retryable("native_transport_board_outside_footprint");
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
    Map* map = bot->GetMap();
    float const staticFloor = map->GetStaticHeight(bot->GetPhaseShift(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ() + 1.0f,
        true, 4.0f);
    if (staticFloor <= INVALID_HEIGHT
        || std::fabs(bot->GetPositionZ() - staticFloor) > 1.5f)
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
