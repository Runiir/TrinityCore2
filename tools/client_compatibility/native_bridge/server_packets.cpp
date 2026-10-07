#include "service.hpp"
#include "chat.hpp"
#include "chat_channels.hpp"
#include "guild_packets.hpp"
#include "merchants.hpp"
#include "item_notifications.hpp"
#include "trainers.hpp"
#include "mail.hpp"
#include "auctions.hpp"
#include "quests.hpp"
#include "talents.hpp"
#include "archaeology.hpp"
#include "player_ui_state.hpp"
#include "item_text.hpp"
#include "pet_packets.hpp"
#include "pet_casts.hpp"
#include "stables.hpp"
#include "tame_channels.hpp"
#include <ctime>

namespace bridge
{
Task<> Session::gameplay(std::string name, Bytes body)
{
    if(name=="SMSG_WHO"){co_await who_reply(std::move(body));co_return;}
    if (name=="SMSG_STAND_STATE_UPDATE")
    {
        send(stand_state_update(body));
        co_return;
    }
    if(name=="SMSG_PONG")
    {
        Reader r(body);r.take<std::uint32_t>();r.end();
        co_return; // Modern latency was already acknowledged on its own socket.
    }
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
    Array guild_identities;
    if(name=="SMSG_GUILD_ROSTER")
    {
        auto members=guild_member_guids(body);std::string ids;
        for(auto const &guid:members){if(!ids.empty())ids+=',';ids+=std::to_string(integer(guid));}
        if(!ids.empty())
        {
            auto root=service.root;
            guild_identities=co_await background(service.database_workers,[root,ids]
            {Database db(root);return db.query("SELECT guid,race FROM client442_characters.characters WHERE guid IN ("+ids+")");});
        }
    }
    if(name=="SMSG_GUILD_EVENT")
    {
        auto event=native_guild_event(body);auto kind=integer(get(event,"event"));
        if(kind==1 || kind==2 || kind==6)
        {
            auto parameters=get(event,"parameters").as_array();std::uint64_t own;
            {std::lock_guard lock(state_mutex);if(state.character.is_null())co_return;own=state.guid();}
            auto root=service.root;
            guild_identities=co_await background(service.database_workers,[root,parameters,own]
            {
                if(parameters.size()<2 || str(parameters[0]).size()>63 || str(parameters[1]).size()>63)
                    throw std::runtime_error("invalid guild event identity query");
                Database db(root);
                auto rows=db.query("SELECT guid,name FROM client442_characters.characters WHERE name IN ("+
                    db.quote(str(parameters[0]))+","+db.quote(str(parameters[1]))+")");
                auto ranks=db.query("SELECT rid AS rank_id,rname AS rank_name FROM client442_characters.guild_rank WHERE guildid IN ("
                    "SELECT guildid FROM client442_characters.guild_member WHERE guid="+std::to_string(own)+")");
                rows.insert(rows.end(),ranks.begin(),ranks.end());return rows;
            });
        }
    }
    Array visible_players;
    if(name=="SMSG_UPDATE_OBJECT")
    {
        std::uint64_t own;
        {std::lock_guard lock(state_mutex);if(state.character.is_null())co_return;own=state.guid();}
        std::unordered_set<std::uint64_t> guids;
        for(auto const &record:native_records(body))
            if(integer(get(record,"kind"))==4 && integer(get(record,"guid"))!=own)
            {
                auto guid=integer(get(record,"guid"));
                if(!guid || guid>0xffffffff)throw std::runtime_error("invalid visible player query identity");
                guids.insert(guid);
            }
        if(!guids.empty())
        {
            std::string ids;for(auto guid:guids){if(!ids.empty())ids+=',';ids+=std::to_string(guid);}
            auto root=service.root;
            visible_players=co_await background(service.database_workers,[root,ids]
            {Database db(root);return db.query("SELECT guid,name,gender FROM client442_characters.characters WHERE guid IN ("+ids+")");});
        }
    }
    Array stable_models;std::uint64_t stable_owner=0;
    if(name=="MSG_LIST_STABLED_PETS")
    {
        {
            std::lock_guard lock(state_mutex);
            if(state.character.is_null() || integer(get(state.character,"class"))!=3)co_return;
            stable_owner=state.guid();
        }
        auto catalog=native_stable_list(body);std::string ids;
        {std::lock_guard lock(state_mutex);stable_catalog_started(service.protocol,state,body);}
        for(auto const &pet:get(catalog,"Pets").as_array())
        {if(!ids.empty())ids+=',';ids+=std::to_string(integer(get(pet,"PetNumber")));}
        if(!ids.empty())
        {
            auto root=service.root;
            stable_models=co_await background(service.database_workers,[root,stable_owner,ids]
            {Database db(root);return db.query("SELECT id,owner,entry,modelid,PetType FROM client442_characters.character_pet WHERE owner="+
                std::to_string(stable_owner)+" AND id IN ("+ids+")");});
        }
    }
    std::lock_guard lock(state_mutex);
    auto instance = world.lock();
    if (!instance || state.character.is_null())
        co_return;
    auto send = [&](Packet const &p) { instance->send(p); };
    auto &protocol = service.protocol;
    Reply reply;
    if(name=="MSG_CHANNEL_START" || name=="MSG_CHANNEL_UPDATE")
    {
        try {if(auto channel=tame_channel_response(state,name,body))send(*channel);}
        catch(std::exception const &error)
        {service.events.event("tame_channel_response_rejected",{{"session",id},{"name",name},{"error",error.what()}});}
        co_return;
    }
    if(name=="MSG_LIST_STABLED_PETS")
    {
        if(state.guid()!=stable_owner)co_return;
        if(auto stable=stable_response(protocol,state,name,body,stable_models))send(*stable);
        if(auto open=stable_open_response(state))send(*open);
        co_return;
    }
    if(name=="SMSG_PET_SLOT_UPDATED" || name=="SMSG_STABLE_RESULT")
    {
        try {if(auto stable=stable_slot_response(protocol,state,name,body))send(*stable);}
        catch(std::exception const &error)
        {service.events.event("stable_slot_response_rejected",{{"session",id},{"name",name},{"error",error.what()}});}
        co_return;
    }
    if(name=="SMSG_PET_SPELLS" || name=="SMSG_PET_NAME_QUERY_RESPONSE")
    {
        if(auto pet=pet_response(protocol,state,name,body))send(*pet);
        co_return;
    }
    if(auto pet=translate_pet_cast(protocol,state,name,body);pet.packet || !pet.rejection.empty())
    {
        if(pet.packet)send(*pet.packet);
        else service.events.event("pet_cast_translation_rejected",{{"session",id},{"name",name},{"reason",pet.rejection}});
        co_return;
    }
    if(research_complete(name,body))
    {
        // The completion packet reports count 1 even on repeats. Fetch native
        // canonical history to preserve the first time and accumulated count.
        native->send("CMSG_REQUEST_RESEARCH_HISTORY",{});co_return;
    }
    if((reply=research_history(state,name,body)))
    {send(*reply);co_return;}
    if((reply=equipment_response(state,name,body)))
    {send(*reply);co_return;}
    if((reply=protocol.inventory_response(name,body)))
    {send(*reply);co_return;}
    if((reply=protocol.inspect_response(state,name,body)))
    {send(*reply);co_return;}
    if((reply=protocol.trade_response(name,body)))
    {send(*reply);co_return;}
    if ((reply = Protocol::party_roles(name,body)))
    {
        this->send(*reply);co_return;
    }
    if ((reply = Protocol::party_profiles(name,body)))
    {
        this->send(*reply);co_return;
    }
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
        if(name.starts_with("MSG_RAID_READY_CHECK"))
            service.ready_native(*this,name,body);
        else this->send(*reply);
        if(name=="SMSG_PARTY_UPDATE") {service.markers(*this);service.ready_roster(*this);}
        co_return;
    }
    if(name=="SMSG_RAID_MARKERS_CHANGED")
    {
        Reader r(body);auto mask=r.take<std::uint32_t>();r.end();service.markers(*this,mask);co_return;
    }
    if ((reply = Protocol::social_response(name, body)))
    {
        this->send(*reply);co_return;
    }
    if((reply=guild_response(name,body,guild_identities)))
    {this->send(*reply);co_return;}
    if ((reply = Protocol::reputation_response(name, body, service.data.factions)))
    {
        send(*reply);co_return;
    }
    if (name == "SMSG_MOVE_UPDATE")
    {
        if ((reply = protocol.public_player_movement(state, body)))
        { send(*reply); co_return; }
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
    if(name=="SMSG_ATTACKER_STATE_UPDATE")
    {
        // An uncaptured optional hit layout is a diagnostic gap. Keep the
        // gameplay connection healthy while retaining the exact native packet.
        try
        {
            if(auto hit=Protocol::combat_response(state,name,body))send(*hit);
        }
        catch(std::exception const &error)
        {
            service.events.event("native_melee_result_rejected",{{"session",id},
                {"name",name},{"error",std::string(error.what()).substr(0,512)}});
        }
        co_return;
    }
    if(name=="SMSG_SPELLNONMELEEDAMAGELOG")
    {
        // Retain unsupported native variants for diagnosis without losing the
        // owned gameplay connection, as for melee-result observations above.
        try
        {
            if(auto damage=Protocol::combat_response(state,name,body))send(*damage);
        }
        catch(std::exception const &error)
        {
            service.events.event("native_spell_damage_rejected",{{"session",id},
                {"name",name},{"error",std::string(error.what()).substr(0,512)}});
        }
        co_return;
    }
    if ((reply = Protocol::combat_response(state, name, body)))
    {
        if(reply->first=="SMSG_ATTACK_SWING_ERROR")this->send(*reply);
        else send(*reply);
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
    if(name=="SMSG_READ_ITEM_OK" || name=="SMSG_READ_ITEM_FAILED" || name=="SMSG_PAGE_TEXT_QUERY_RESPONSE")
    {
        if(auto text=item_text_response(protocol,state,name,body))send(*text);
        co_return;
    }
    if ((reply = protocol.bank_response(state, name, body)))
    {send(*reply);co_return;}
    if ((reply = merchant_response(protocol,state,name,body)))
    {send(*reply);co_return;}
    if ((reply = auction_response(protocol,state,name,body,service.data.auction_items)))
    {
        // Auction replies are realm opcodes in the 60895 connection contract.
        this->send(*reply);co_return;
    }
    if ((reply = item_notification(name,body)))
    {send(*reply);co_return;}
    if ((reply = trainer_response(protocol,state,name,body)))
    {send(*reply);co_return;}
    if (trainer_completion(name,body))co_return;
    if ((reply = quest_response(protocol,state,name,body)))
    {send(*reply);co_return;}
    if ((reply = talent_response(name,body)))
    {send(*reply);co_return;}
    if ((reply = mail_response(protocol,state,name,body)))
    {send(*reply);co_return;}
    reply=Protocol::gossip_response(state,name,body);
    if(reply || name=="SMSG_GOSSIP_COMPLETE")
    {
        if(reply)send(*reply);
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
    // The pinned 60895 channel opcode contract uses the authenticated realm
    // connection. The client silently discards a list delivered on instance.
    if(auto channel_reply=chat_channel_response(state,name,body))
    {this->send(*channel_reply);co_return;}
    reply = chat_response(state,name,body);
    if(!reply)reply = Protocol::initialize_response(state, name, body);
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
        auto locations=protocol.marker_objects(state,body);
        if(!locations.empty())service.markers(*this,{},locations);
        bool was_created = state.created;
        if (auto reply = protocol.object_updates(state, body,visible_players))
            send(*reply);
        if(auto pet=pet_ready(protocol,state))send(*pet);
        if (!was_created && state.created)
        {
            native->send("CMSG_REQUEST_RESEARCH_HISTORY",{});
            for(auto const &request:login_barrier.release_quest_reads())native->send(request.first,request.second);
            instance->send("SMSG_MOVE_SET_ACTIVE_MOVER", Writer().guid(state.guid(), player_high()).finish());
            instance->send("SMSG_CONTROL_UPDATE",
                           Writer().guid(state.guid(), player_high()).bits(1, 1).finish());
            if(login_barrier.release_active_mover(state))
            {
                native->send("CMSG_SET_ACTIVE_MOVER",native_login(state.guid(),true));
                service.events.event("native_active_mover_confirmed",{{"session",id},{"guid",state.guid()}});
            }
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
        finish_logout(state);
        login_barrier={};
        world.reset();
        // A logout retires the instance socket; the realm socket stays open.
        // Leaving it alive makes the client reject the next RESUME_COMMS.
        instance->channel->close();
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
