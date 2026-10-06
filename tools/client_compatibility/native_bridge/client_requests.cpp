#include "service.hpp"
#include "chat.hpp"
#include "guild_packets.hpp"
#include "merchants.hpp"
#include "repairs.hpp"
#include "trainers.hpp"
#include "quests.hpp"
#include "talents.hpp"
#include "mail.hpp"
#include "auctions.hpp"
#include "currency.hpp"
#include "appearance.hpp"
#include "player_ui_state.hpp"
#include "item_text.hpp"
#include "who.hpp"
#include "pet_packets.hpp"

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
    if(name=="CMSG_QUERY_GAME_OBJECT" || name=="CMSG_QUERY_CREATURE")
    {
        if(active_world.get()!=this || !state.guid())
        {service.events.event("late_template_query_ignored",{{"session",owner.id},{"name",name}});return;}
        std::optional<Packet> request;
        if(name=="CMSG_QUERY_GAME_OBJECT")
            request=Packet{"CMSG_GAMEOBJECT_QUERY",Protocol::gameobject_query(state,body)};
        else if(auto query=Protocol::creature_query(state,body))request=Packet{"CMSG_CREATURE_QUERY",*query};
        if(request)
        {
            if(!state.created)owner.login_barrier.defer_template_read(*request);
            else native_send(*request);
        }
        return;
    }
    if(name=="CMSG_QUERY_NEXT_MAIL_TIME")
    {
        auto request=mail_request(protocol,state,name,body);
        if(active_world.get()!=this || !state.guid())
        {service.events.event("late_mail_query_ignored",{{"session",owner.id},{"name",name}});return;}
        if(!state.created)owner.login_barrier.defer_mail_read(*request);
        else native_send(*request);
        return;
    }
    if(name=="CMSG_QUERY_QUEST_INFO")
    {
        auto request=quest_request(protocol,state,name,body);
        if(active_world.get()!=this || !state.guid())
        {
            service.events.event("late_quest_query_ignored",{{"session",owner.id},{"name",name}});return;
        }
        // The client can read its quest cache immediately after RESUME_COMMS.
        // Native STATUS_LOGGEDIN reads wait for authoritative player creation.
        if(!state.created)
        {
            owner.login_barrier.defer_quest_read(*request);
            service.events.event("quest_query_deferred_until_player_create",{{"session",owner.id},{"name",name}});
        }
        else native_send(*request);
        return;
    }
    if(name=="CMSG_WHO")
    {
        // Like other social reads, WHO travels on the authenticated Realm
        // socket while character authority belongs to the active instance.
        if(!state.created || !active_world)throw std::runtime_error("Who request without owned character");
        native_send(*who_request(state,name,body));return;
    }
    if(Protocol::bank_close(state,name,body))return;
    if(name=="CMSG_PET_ACTION" || name=="CMSG_PET_SET_ACTION")
    {
        if(!state.created || !active_world)throw std::runtime_error("pet action without active owned world");
        auto translation=name=="CMSG_PET_ACTION" ? translate_pet_action(protocol,state,body) :
            translate_pet_set_action(protocol,state,body);
        if(!translation.rejection.empty())
            service.events.event(name=="CMSG_PET_ACTION" ? "pet_action_translation_rejected" :
                "pet_autocast_translation_rejected",{{"session",owner.id},{"error",translation.rejection}});
        else if(translation.packet)native_send(*translation.packet);
        return;
    }
    if(name=="CMSG_REQUEST_PET_INFO" || name=="CMSG_QUERY_PET_NAME")
    {
        if(!state.created || !active_world)throw std::runtime_error("pet read without active owned world");
        native_send(*pet_request(protocol,state,name,body));return;
    }
    if(name=="CMSG_READ_ITEM" || name=="CMSG_QUERY_PAGE_TEXT")
    {require_world();native_send(*item_text_request(protocol,state,name,body));return;}
    if(auto request=appearance_request(name,body))
    {require_world();native_send(*request);return;}
    if(auto request=talent_request(name,body))
    {require_world();native_send(*request);return;}
    if(auto request=currency_request(name,body))
    {require_world();native_send(*request);return;}
    if(auto request=Protocol::bank_request(state,name,body))
    {require_world();native_send(*request);return;}
    if(auto request=merchant_request(protocol,state,name,body))
    {require_world();native_send(*request);return;}
    if(auto request=auction_request(protocol,state,name,body,service.data.auction_items))
    {require_world();native_send(*request);return;}
    if(auto request=repair_request(protocol,state,name,body))
    {require_world();native_send(*request);return;}
    if(auto request=trainer_request(protocol,state,name,body))
    {require_world();native_send(*request);return;}
    if(name=="CMSG_QUEST_GIVER_STATUS_QUERY" || name=="CMSG_QUEST_GIVER_STATUS_TRACKED_QUERY")
    {
        auto request=quest_status_request(protocol,state,name,body);
        if(active_world.get()!=this || !state.guid())
        {service.events.event("late_quest_query_ignored",{{"session",owner.id},{"name",name}});return;}
        bool tracked=name=="CMSG_QUEST_GIVER_STATUS_TRACKED_QUERY";
        if(tracked)require_world();
        if(request->first=="SMSG_QUEST_GIVER_STATUS" || request->first=="SMSG_QUEST_GIVER_STATUS_MULTIPLE")
        {
            send(*request);
            service.events.event(tracked?"empty_tracked_quest_status":"cached_quest_status_cleared",
                {{"session",owner.id},{"name",name}});
        }
        else
        {
            require_world();native_send(*request);
            if(tracked)service.events.event("tracked_quest_status_refreshed",{{"session",owner.id},{"name",name}});
        }
        return;
    }
    if(auto request=quest_request(protocol,state,name,body))
    {require_world();native_send(*request);return;}
    if(auto request=mail_request(protocol,state,name,body))
    {
        require_mail_character(name,state.created,bool(active_world),in_world);
        native_send(*request);return;
    }
    if(auto packet=chat_request(state,name,body))
    {
        require_chat_character(state.created,bool(active_world));native_send(*packet);return;
    }
    if (name == "CMSG_QUERY_REALM_NAME")
    {
        // The authenticated Realm connection asks before character selection.
        // This public metadata does not require an active player/world instance.
        owner.send("SMSG_REALM_QUERY_RESPONSE", Protocol::realm_name(body));return;
    }
    if(name=="CMSG_CLEAR_RAID_MARKER")
    {
        if(!state.created || !active_world)throw std::runtime_error("raid marker request without owned character");
        auto requests=Protocol::marker_clear(body);Protocol::marker_permission(state);
        if(body[0]>=5)service.markers(owner,{},{},body[0]);
        for(auto const &packet:requests)native_send(packet);
        return;
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
    if(auto request=guild_request(state,name,body))
    {
        if(!state.created || !active_world)throw std::runtime_error("guild request without owned character");
        native_send(*request);return;
    }
    if(Protocol::late_party_query(state.created && bool(active_world),name,body))
    {
        service.events.event("late_party_query_ignored",{{"session",owner.id},{"name",name}});return;
    }
    if(auto request=equipment_request(state,name,body))
    {
        require_world();native_send(*request);return;
    }
    if(auto request=Protocol::inventory_request(state,name,body))
    {
        require_world();native_send(*request);return;
    }
    if(name=="CMSG_INSPECT")
    {
        require_world();if(auto request=Protocol::inspect_request(state,name,body))native_send(*request);return;
    }
    if(name=="CMSG_CANCEL_TRADE" && !in_world)
    {
        Reader r(body);r.end();
        // The native handler explicitly accepts this empty cleanup after logout.
        // No gameplay state remains on the modern endpoint at that point.
        service.events.event("late_trade_cancel_ignored",{{"session",owner.id},{"name",name}});return;
    }
    if(auto request=Protocol::trade_request(state,name,body))
    {require_world();native_send(*request);return;}
    if (auto request = Protocol::party_request(name, body))
    {
        if (!state.created || !active_world) throw std::runtime_error("party request without owned character");
        native_send(*request);return;
    }
    if (auto request = Protocol::party_profiles(name, body))
    {
        if (!state.created || !active_world) throw std::runtime_error("CUF settings without owned character");
        native_send(*request);return;
    }
    if (auto request = Protocol::party_roles(name, body))
    {
        if (!state.created || !active_world) throw std::runtime_error("role request without owned character");
        native_send(*request);return;
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
        if(!owner.login_barrier.accept_active_mover(state,body,active_world.get()==this))
        {
            service.events.event("active_mover_deferred_until_player_create",{{"session",owner.id},{"guid",state.guid()}});
            return;
        }
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
        Reply translated;
        try
        {
            translated=pet_aura_cancel(protocol,state,body);
            if(!translated)translated=Packet{name,Protocol::aura_cancel(state,body)};
        }
        catch(std::exception const &error)
        {
            service.events.event("aura_cancel_translation_rejected",{{"session",owner.id},{"error",error.what()}});
            return;
        }
        native_send(*translated);
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
    if (name == "CMSG_SET_SHEATHED")
    {
        require_world();native_send(sheath_request(body,in_world));return;
    }
    if (name == "CMSG_STAND_STATE_CHANGE")
    {
        require_world();
        native_send(stand_state_request(body,in_world));
        return;
    }
    if (name == "CMSG_SET_ACTION_BAR_TOGGLES")
    {
        if (auto packet = actionbar_toggle_request(body, in_world))
        {
            require_world();
            native_send(*packet);
        }
        else
            service.events.event("preworld_actionbar_zero_ignored", {{"session", id}});
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
        auto cancelled=Protocol::cast_cancel(state,body);
        if(!cancelled.empty())owner.native->send(name,cancelled);
        return;
    }
    if(name=="CMSG_USE_ITEM")
    {
        require_world();
        try {native_send(protocol.item_use(state,body));service.events.event("item_use_forwarded",{{"session",id}});}
        catch(std::exception const &e)
        {
            service.events.event("item_use_translation_rejected",{{"session",id},{"error",e.what()}});
            try {auto failure=Protocol::item_use_rejected(body);if(!failure.empty())send("SMSG_CAST_FAILED",failure);}
            catch(...) {}
        }
        return;
    }
    if (name == "CMSG_CAST_SPELL")
    {
        require_world();
        try
        {
            auto request=protocol.cast_request(state, body);
            auto const &cast=state.casts.at(state.cast_counter);
            if(auto extra=Protocol::extra_marker(state))
            {
                Protocol::marker_permission(state);
                auto const &location=*extra;
                auto const &position=get(location,"position").as_array();
                auto const &origin=state.latest_movement.empty() ? get(get(state.self_snapshot,"movement"),"position").as_array() : state.latest_movement;
                double distance=0;for(unsigned i=0;i<3;++i){auto d=number(position[i])-number(origin.at(i));distance+=d*d;}
                if(distance>10000)throw std::runtime_error("raid marker is outside the 100-yard placement range");
                service.markers(owner,{},Array{location});
                active_world->send("SMSG_SPELL_PREPARE",Writer().guid(get(cast,"guid")).guid(get(cast,"server_guid")).finish());
                if(auto result=protocol.extra_marker_go(state))active_world->send(*result);
                service.events.marker_placed(owner.id,location);
                return;
            }
            else native_send(request);
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
