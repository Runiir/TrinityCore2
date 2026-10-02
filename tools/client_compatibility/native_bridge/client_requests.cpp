#include "service.hpp"

namespace bridge
{
void Session::gameplay_request(std::string const &name, View body, Session &owner,
                               std::shared_ptr<Session> const &active_world, bool in_world)
{
    auto &state = owner.state;
    auto &protocol = service.protocol;
    auto require_world = [&]
    {
        if (!in_world)
            throw std::runtime_error("gameplay request outside owned active world");
    };
    auto native_send = [&](Packet const &packet) { owner.native->send(packet.first, packet.second); };
    if (name == "CMSG_QUERY_REALM_NAME")
    {
        // The authenticated Realm connection asks before character selection.
        // This public metadata does not require an active player/world instance.
        owner.send("SMSG_REALM_QUERY_RESPONSE", Protocol::realm_name(body));return;
    }
    if (auto request = Protocol::account_request(state,name,body))
    {
        native_send(*request);return;
    }
    if (name == "CMSG_SOCIAL_CONTRACT_REQUEST")
    {
        if (!body.empty()) throw std::runtime_error("invalid social contract request");
        send("SMSG_SOCIAL_CONTRACT_REQUEST_RESPONSE", Bytes{0});
        return;
    }
    if (auto request = Protocol::social_request(name, body))
    {
        if (!state.created || !active_world) throw std::runtime_error("social request without owned character");
        native_send(*request);return;
    }
    if (auto request = Protocol::party_request(name, body))
    {
        if (!state.created || !active_world) throw std::runtime_error("party request without owned character");
        native_send(*request);return;
    }
    if (auto request = Protocol::party_profiles(name, body))
    {
        require_world();native_send(*request);return;
    }
    if (auto request = Protocol::reputation_request(name, body))
    {
        if (!state.created || !active_world) throw std::runtime_error("reputation request without owned character");
        native_send(*request);return;
    }
    if (name == "CMSG_TIME_SYNC_RESPONSE")
    {
        if (body.size() != 8)
            throw std::runtime_error("invalid time synchronization");
        owner.native->send("CMSG_TIME_SYNC_RESP", body);
        return;
    }
    if (name == "CMSG_MOVE_INIT_ACTIVE_MOVER_COMPLETE")
    {
        require_world();
        if (body.size() != 4)
            throw std::runtime_error("invalid active mover acknowledgement");
        owner.native->send("CMSG_SET_ACTIVE_MOVER", native_login(state.guid(), true));
        service.events.event("native_active_mover_confirmed", {{"session", id}, {"guid", state.guid()}});
        return;
    }
    if (name == "CMSG_LOGOUT_REQUEST")
    {
        Reader r(body);
        r.bits(1);
        r.end();
        if (!state.created)
            throw std::runtime_error("logout before world entry");
        owner.native->send(name);
        return;
    }
    if (name == "CMSG_LOGOUT_CANCEL")
    {
        if (!body.empty())
            throw std::runtime_error("invalid logout cancellation");
        owner.native->send(name);
        return;
    }
    if (name == "CMSG_ATTACK_STOP" || name == "CMSG_SET_SELECTION" || name == "CMSG_ATTACK_SWING")
    {
        require_world();
        if (auto request = Protocol::combat_request(state, name, body))
            native_send(*request);
        return;
    }
    if (name == "CMSG_QUERY_CREATURE")
    {
        require_world();
        auto query = Protocol::creature_query(state, body);
        if (query)
            owner.native->send("CMSG_CREATURE_QUERY", *query);
        else
            send("SMSG_QUERY_CREATURE_RESPONSE", Writer().raw(body).bits(0, 1).finish());
        return;
    }
    if (name == "CMSG_QUERY_NPC_TEXT")
    {
        require_world();
        owner.native->send("CMSG_NPC_TEXT_QUERY", Protocol::npc_query(state, body));
        return;
    }
    if (name == "CMSG_AREA_TRIGGER")
    {
        require_world();
        Reader r(body);
        auto trigger = r.take<std::uint32_t>();
        auto entered = r.bits(1);
        r.bits(1);
        r.end();
        if (!trigger)
            throw std::runtime_error("invalid area trigger ID");
        if (entered)
            owner.native->send("CMSG_AREATRIGGER", Writer().put(trigger).finish());
        return;
    }
    if (name == "CMSG_TALK_TO_GOSSIP" || name == "CMSG_GOSSIP_SELECT_OPTION")
    {
        require_world();
        native_send(Protocol::gossip_request(state, name, body));
        return;
    }
    if (name == "CMSG_TAXI_NODE_STATUS_QUERY" || name == "CMSG_TAXI_QUERY_AVAILABLE_NODES" ||
        name == "CMSG_ENABLE_TAXI_NODE" || name == "CMSG_ACTIVATE_TAXI")
    {
        require_world();
        native_send(Protocol::taxi_request(state, name, body, service.data.taxi_paths));
        return;
    }
    if (name == "CMSG_MOVE_TELEPORT_ACK" || name == "CMSG_SUSPEND_TOKEN_RESPONSE" ||
        name == "CMSG_WORLD_PORT_RESPONSE")
    {
        bool realm_port = name == "CMSG_WORLD_PORT_RESPONSE" && &owner == this;
        if ((!active_world || active_world.get() != this) && !realm_port)
            throw std::runtime_error("transfer acknowledgement outside owned world");
        if (state.character.is_null() || !active_world)
            throw std::runtime_error("transfer acknowledgement without owned character");
        native_send(Protocol::transfer_request(state, name, body));
        return;
    }
    static std::unordered_set<std::string> const acks = {"CMSG_MOVE_SET_CAN_FLY_ACK",
                                                         "CMSG_MOVE_ENABLE_SWIM_TO_FLY_TRANS_ACK",
                                                         "CMSG_MOVE_FORCE_RUN_SPEED_CHANGE_ACK",
                                                         "CMSG_MOVE_FORCE_RUN_BACK_SPEED_CHANGE_ACK",
                                                         "CMSG_MOVE_FORCE_FLIGHT_SPEED_CHANGE_ACK",
                                                         "CMSG_MOVE_FORCE_FLIGHT_BACK_SPEED_CHANGE_ACK",
                                                         "CMSG_MOVE_FORCE_SWIM_SPEED_CHANGE_ACK",
                                                         "CMSG_MOVE_FORCE_SWIM_BACK_SPEED_CHANGE_ACK",
                                                         "CMSG_MOVE_FORCE_WALK_SPEED_CHANGE_ACK"};
    if (acks.contains(name))
    {
        require_world();
        native_send(protocol.movement_ack(state, name, body));
        return;
    }
    if (name == "CMSG_CANCEL_MOUNT_AURA")
    {
        require_world();
        if (!body.empty())
            throw std::runtime_error("invalid dismount request");
        owner.native->send(name);
        return;
    }
    if (name == "CMSG_CANCEL_AURA")
    {
        require_world();
        owner.native->send(name, Protocol::aura_cancel(state, body));
        return;
    }
    if (movement_supported(name) || name == "CMSG_MOVE_SET_FACING_HEARTBEAT")
    {
        require_world();
        auto move = movement_parse(body, state.guid());
        protocol.validate_standing(state, move);
        state.latest_movement = get(move, "position").as_array();
        native_send(protocol.movement_encode(
            name == "CMSG_MOVE_SET_FACING_HEARTBEAT" ? "CMSG_MOVE_SET_FACING" : name, state.guid(), move));
        service.events.event(
            "movement_forwarded",
            {{"session", id}, {"name", name}, {"guid", state.guid()}, {"position", get(move, "position")}});
        return;
    }
    if (name == "CMSG_SET_ACTION_BUTTON")
    {
        require_world();
        Reader r(body);
        auto action = r.take<std::uint32_t>();
        auto index = r.take<std::uint8_t>();
        r.end();
        if (index >= 144)
            throw std::runtime_error("action bar slot has no native equivalent");
        owner.native->send(name, Writer().pack("BI", {index, action}).finish());
        return;
    }
    if (name == "CMSG_QUERY_GAME_OBJECT")
    {
        require_world();
        owner.native->send("CMSG_GAMEOBJECT_QUERY", Protocol::gameobject_query(state, body));
        return;
    }
    if (name == "CMSG_GAME_OBJ_USE" || name == "CMSG_GAME_OBJ_REPORT_USE" || name == "CMSG_LOOT_ITEM" ||
        name == "CMSG_LOOT_RELEASE" || name == "CMSG_LOOT_MONEY")
    {
        require_world();
        for (auto const &packet : Protocol::loot_request(state, name, body))
            native_send(packet);
        return;
    }
    if (name == "CMSG_CANCEL_CAST")
    {
        require_world();
        owner.native->send(name, Protocol::cast_cancel(state, body));
        return;
    }
    if (name == "CMSG_CAST_SPELL")
    {
        require_world();
        try
        {
            native_send(protocol.cast_request(state, body));
            service.events.event("cast_forwarded", {{"session", id}});
        }
        catch (std::exception const &e)
        {
            service.events.event("cast_translation_rejected", {{"session", id}, {"error", e.what()}});
            try
            {
                auto failure = Protocol::cast_rejected(body);
                if (!failure.empty())
                    send("SMSG_CAST_FAILED", failure);
            }
            catch (...)
            {
            }
        }
        return;
    }
    service.events.event("unmapped_client_packet", {{"session", id}, {"name", name}, {"bytes", body.size()}});
}
} // namespace bridge
