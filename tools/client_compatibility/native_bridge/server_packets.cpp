#include "service.hpp"
#include <ctime>

namespace bridge
{
Task<> Session::gameplay(std::string name, Bytes body)
{
    if (name == "SMSG_ACCOUNT_DATA_TIMES" || name == "SMSG_UPDATE_ACCOUNT_DATA")
    {
        std::lock_guard lock(state_mutex);
        if (auto reply = Protocol::account_response(state,name,body)) this->send(*reply);
        co_return;
    }
    if (name == "SMSG_UPDATE_ACCOUNT_DATA_COMPLETE")
    {
        Reader r(body);auto type=r.take<std::uint32_t>(), status=r.take<std::uint32_t>();r.end();
        if(type>=8 || status)throw std::runtime_error("native account cache update failed");
        co_return; // Modern clients use no equivalent acknowledgement packet.
    }
    if (name == "SMSG_ENUM_CHARACTERS_RESULT")
    {
        auto root = service.root;
        auto account = login.account;
        auto data = co_await background(service.database_workers,
                                        [root, account]
                                        {
                                            Database db(root);
                                            return Object{{"characters", db.characters(account)},
                                                          {"equipment", db.equipment(account)}};
                                        });
        send(name, service.data.enumeration(data["characters"].as_array(), data["equipment"].as_array()));
        co_return;
    }
    Array party_identities;
    if (name == "SMSG_PARTY_UPDATE")
    {
        auto members = Protocol::party_members(body);
        {
            std::lock_guard lock(state_mutex);
            if (state.character.is_null()) co_return;
            members.push_back(state.guid());
        }
        std::string ids;
        for (auto const &guid : members)
        {
            if (!ids.empty()) ids += ',';
            ids += std::to_string(integer(guid));
        }
        auto root = service.root;
        party_identities = co_await background(service.database_workers, [root, ids]
        {
            Database db(root);
            return db.query("SELECT guid,class,race FROM client442_characters.characters WHERE guid IN (" + ids + ")");
        });
    }
    std::lock_guard lock(state_mutex);
    auto instance = world.lock();
    if (!instance || state.character.is_null())
        co_return;
    auto send = [&](Packet const &p) { instance->send(p); };
    auto &protocol = service.protocol;
    Reply reply;
    if (name == "SMSG_PARTY_MEMBER_FULL_STATE" || name == "SMSG_PARTY_MEMBER_STATE")
    {
        if ((reply = Protocol::party_state(state,name,body))) this->send(*reply);
        co_return;
    }
    if ((reply = Protocol::achievement_response(state,name,body)))
    {
        this->send(*reply);co_return;
    }
    if ((reply = Protocol::party_response(state, name, body, party_identities)))
    {
        this->send(*reply);co_return;
    }
    if ((reply = Protocol::social_response(name, body)))
    {
        this->send(*reply);co_return;
    }
    if ((reply = Protocol::reputation_response(name, body, service.data.factions)))
    {
        send(*reply);co_return;
    }
    if (name == "SMSG_ON_MONSTER_MOVE")
    {
        auto packets = Protocol::creature_movement(state, body);
        if (!packets.empty())
        {
            for (auto const &p : packets)
                send(p);
            co_return;
        }
    }
    if ((reply = Protocol::combat_response(state, name, body)))
    {
        send(*reply);
        co_return;
    }
    if (name == "SMSG_NPC_TEXT_UPDATE")
    {
        Reader r(body);
        auto entry = r.take<std::uint32_t>();
        auto pos = service.data.npc_broadcasts.find(entry);
        if ((reply = Protocol::npc_reply(state, body,
                                         pos == service.data.npc_broadcasts.end() ? nullptr : &pos->second)))
            send(*reply);
        co_return;
    }
    if (name == "SMSG_CREATURE_QUERY_RESPONSE")
    {
        if ((reply = Protocol::creature_reply(state, body)))
            send(*reply);
        co_return;
    }
    if ((reply = Protocol::gossip_response(state, name, body)))
    {
        send(*reply);
        co_return;
    }
    if ((reply = Protocol::taxi_response(state, name, body)))
    {
        send(*reply);
        co_return;
    }
    if ((reply = Protocol::transfer_response(state, name, body)))
    {
        send(*reply);
        co_return;
    }
    if (name == "SMSG_SPELL_START")
        if ((reply = Protocol::cast_prepare(state, body)))
            send(*reply);
    if (name == "SMSG_GAMEOBJECT_QUERY_RESPONSE")
    {
        if ((reply = Protocol::gameobject_reply(state, body)))
            send(*reply);
        co_return;
    }
    if (name == "SMSG_DESTROY_OBJECT")
    {
        if ((reply = Protocol::destroy_object(state, body)))
            send(*reply);
        co_return;
    }
    if ((reply = Protocol::aura_response(state, name, body)))
    {
        send(*reply);
        co_return;
    }
    reply = Protocol::initialize_response(state, name, body);
    if (!reply)
        reply = protocol.movement_control(state, name, body);
    if (!reply)
        reply = protocol.cast_response(state, name, body);
    if (!reply)
        reply = Protocol::currency_response(name, body);
    if (auto loot = Protocol::loot_response(state, name, body))
        {
            send(*loot);
            co_return;
        }
    if (reply)
    {
        send(*reply);
        co_return;
    }
    if (name == "SMSG_LOGIN_VERIFY_WORLD")
    {
        if (body.size() != 20)
            throw std::runtime_error("invalid native login world");
        instance->send(name, Writer().raw(body).zeros(4).finish());
        Writer caches;caches.guid(state.guid(),player_high()).put<std::int64_t>(std::time(nullptr));
        for(auto time:state.account_times)caches.put<std::int64_t>(time);
        instance->send("SMSG_ACCOUNT_DATA_TIMES",caches.finish());
        instance->send("SMSG_INITIAL_SETUP", Bytes{3, 0});
        instance->send("SMSG_WORLD_SERVER_INFO", Writer().pack("I", {0}).bits(0, 5).finish());
    }
    else if (name == "SMSG_UPDATE_OBJECT")
    {
        bool was_created = state.created;
        if (auto reply = protocol.object_updates(state, body))
            send(*reply);
        if (!was_created && state.created)
        {
            instance->send("SMSG_MOVE_SET_ACTIVE_MOVER", Writer().guid(state.guid(), player_high()).finish());
            instance->send("SMSG_CONTROL_UPDATE",
                           Writer().guid(state.guid(), player_high()).bits(1, 1).finish());
            if (auto resume = Protocol::transfer_resume(state))
                send(*resume);
            service.events.event("native_player_created",
                                 {{"session", id},
                                  {"guid", state.guid()},
                                  {"map", get(state.self_snapshot, "map")},
                                  {"position", get(get(state.self_snapshot, "movement"), "position")}});
        }
    }
    else if (name == "SMSG_BIND_POINT_UPDATE")
    {
        if (body.size() == 20)
            instance->send(name, body);
    }
    else if (name == "SMSG_TIME_SYNC_REQ")
        instance->send("SMSG_TIME_SYNC_REQUEST", body);
    else if (name == "SMSG_LOGIN_SETTIMESPEED")
    {
        Reader r(body);
        auto speed = r.take<float>();
        auto time = r.take<std::uint32_t>();
        r.raw(8);
        r.end();
        instance->send("SMSG_LOGIN_SET_TIME_SPEED",
                       Writer().pack("IIfII", {time, time, speed, 0, 0}).finish());
    }
    else if (name == "SMSG_LOGOUT_COMPLETE")
    {
        this->send(name, Bytes{0});
        state.character = nullptr;
        state.created = false;
        world.reset();
    }
    else if (name == "SMSG_LOGOUT_RESPONSE")
    {
        Reader r(body);
        auto result = r.take<std::uint32_t>();
        auto instant = r.take<std::uint8_t>();
        r.end();
        this->send(name, Writer().pack("i", {result}).bits(instant != 0, 1).finish());
    }
    else if (name == "SMSG_LOGOUT_CANCEL_ACK")
        instance->send(name);
}
} // namespace bridge
