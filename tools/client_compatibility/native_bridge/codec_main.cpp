// Line-delimited synthetic/differential test interface. Never open a live socket.
#include "crypto.hpp"
#include "fields.hpp"
#include "protocol.hpp"
#include "events.hpp"
#include "ready_check.hpp"
#include <iostream>
#include <memory>

int main(int argc, char **argv)
{
    using namespace bridge;
    try
    {
        if (argc != 2)
            throw std::runtime_error("usage: bridge_codec <world-schema-directory>");
        Protocol protocol(argv[1]);
        std::string line;
        while (std::getline(std::cin, line))
        {
            try
            {
                auto request = json::parse(line);
                auto op = str(get(request, "op"));
                Value result;
                auto data = [&](std::string_view key) { return unhex(str(get(request, key))); };
                if (op == "pack")
                    result = hex(Writer()
                                     .pack(str(get(request, "format")), get(request, "values").as_array())
                                     .finish());
                else if(op=="event_diagnostic")
                {
                    Events events(str(get(request,"root")));
                    events.event(str(get(request,"kind")),get(request,"fields").as_object());result=true;
                }
                else if(op=="marker_diagnostic")
                {
                    Events events(str(get(request,"root")));events.marker_placed("fixture",get(request,"location"));result=true;
                }
                else if (op == "guid")
                    result = hex(Writer().guid(get(request, "value")).finish());
                else if (op == "fields")
                {
                    Writer w;
                    protocol.fields.serialize(w, str(get(request, "kind")), get(request, "values"),
                                              integer(get(request, "visibility")));
                    result = hex(w.finish());
                }
                else if (op == "player_names")
                    result = hex(Protocol::player_names_response(get(request,"requested").as_array(),get(request,"rows").as_array()));
                else if (op == "realm_name")
                    result = hex(Protocol::realm_name(data("body")));
                else if (op == "movement")
                {
                    auto state = movement_parse(data("body"), integer(get(request, "guid")));
                    auto [name, body] = protocol.movement_encode(str(get(request, "name")),
                                                                 integer(get(request, "guid")), state);
                    result = Array{name, hex(body)};
                }
                else if (op == "records")
                {
                    Array records;
                    for (auto const &record : native_records(data("body")))
                        records.push_back(record);
                    result = records;
                }
                else if(op=="raid_markers")
                {
                    RaidMarkers markers;Array output;
                    for(auto const &action:get(request,"actions").as_array())
                    {
                        if(str(get(action,"fn"))=="mask")markers.mask(integer(get(action,"value")));
                        else markers.location(integer(get(action,"slot")),get(action,"value"));
                        auto packet=markers.packet();output.push_back(packet ? Value(hex(*packet)) : Value(nullptr));
                    }
                    result=output;
                }
                else if(op=="marker_clear")
                {
                    Array output;for(auto const &p:Protocol::marker_clear(data("body")))output.push_back(Array{p.first,hex(p.second)});
                    result=output;
                }
                else if(op=="marker_permission")
                {
                    State owner;owner.character=Object{{"guid",get(request,"guid")}};owner.created=truth(get(request,"created"));
                    owner.party_guid=Array{get(request,"group"),0};owner.party_leader=integer(get(request,"leader"));
                    owner.party_flags=integer(get(request,"flags"));owner.party_member_flags=integer(get(request,"member_flags"));
                    Protocol::marker_permission(owner);result=true;
                }
                else if(op=="late_party_query")
                    result=Protocol::late_party_query(truth(get(request,"active")),str(get(request,"name")),data("body"));
                else if(op=="ready_check")
                {
                    ReadyCheck check;Array output;
                    for(auto const &action:get(request,"actions").as_array())
                    {
                        auto fn=str(get(action,"fn"));bool accepted=false;
                        if(fn=="start")
                        {
                            std::unordered_set<std::uint64_t> members;
                            for(auto const &member:get(action,"members").as_array())members.insert(integer(member));
                            check.start(integer(get(action,"starter")),members);accepted=true;
                        }
                        else if(fn=="answer")accepted=check.answer(integer(get(action,"member")));
                        else if(fn=="finish")accepted=check.finish();
                        else throw std::runtime_error("unknown ready check test action");
                        output.push_back(Object{{"accepted",accepted},{"active",check.active},
                            {"pending",check.pending.size()},{"complete",check.complete()}});
                    }
                    result=output;
                }
                else if (op == "object_values")
                    result = protocol.field_values(get(request, "snapshot"), get(request, "character"));
                else if (op == "rest_update")
                    result = hex(protocol.rest_block(get(request, "snapshot"), get(request, "changed")));
                else if (op == "unit_update")
                    result = hex(protocol.scalar_block(get(request, "snapshot"),get(request,"character"),get(request,"changed"),integer(get(request,"visibility"))));
                else if(op=="inventory_update")
                    result=hex(protocol.inventory_block(get(request,"snapshot"),get(request,"changed")));
                else if(op=="item_update")
                    result=hex(protocol.item_update(get(request,"snapshot"),get(request,"changed")));
                else if (op == "object_block")
                {
                    auto kind = str(get(request, "kind"));
                    auto const &snapshot = get(request, "snapshot");
                    auto const &character = get(request, "character");
                    result = hex(kind == "player" ? protocol.player_block(snapshot, character)
                                 : kind == "item" ? protocol.item_block(snapshot)
                                 : kind == "unit" ? protocol.unit_block(snapshot, character)
                                                  : protocol.gameobject_block(snapshot));
                }
                else if (op == "signature")
                    result = hex(enabled_signature(data("key")));
                else if (op == "derive")
                {
                    auto [session, key] = derive(data("material"), data("local"), data("server"),
                                                 data("proof"), str(get(request, "variant")));
                    result = Array{hex(session), hex(key)};
                }
                else if (op == "encode" || op == "decode")
                {
                    PacketCrypt crypt;
                    crypt.key = data("key");
                    crypt.send_counter = crypt.recv_counter = integer(get(request, "counter"));
                    if (op == "encode")
                        result = hex(crypt.encode(integer(get(request, "opcode")), data("body")));
                    else
                    {
                        auto [opcode, body] = crypt.decode(data("payload"), data("tag"));
                        result = Array{opcode, hex(body)};
                    }
                }
                else if (op == "legacy")
                {
                    LegacyCrypt crypt(data("key"), data("seed"));
                    result = hex(crypt.transform(data("body")));
                }
                else if (op == "stateful")
                {
                    State state;
                    state.character = get(request, "character");
                    state.self_snapshot = get(request, "snapshot");
                    state.created = !state.self_snapshot.is_null();
                    state.gossip_menu = get(request, "gossip_menu");
                    for (auto const &record : get(request, "gameobjects").as_array())
                        state.visible_gameobjects[integer(get(record, "guid"))] = record;
                    for (auto const &record : get(request, "units").as_array())
                        state.visible_units[integer(get(record, "guid"))] = record;
                    Array replies;
                    auto emit = [&](Packet const &packet)
                    { replies.push_back(Array{packet.first, hex(packet.second)}); };
                    state.native_send = [&](std::string const &name, View body)
                    { replies.push_back(Array{name, hex(body)}); };
                    for (auto const &action : get(request, "actions").as_array())
                    {
                        auto fn = str(get(action, "fn")), name = str(get(action, "name"));
                        auto body = unhex(str(get(action, "body")));
                        Reply reply;
                        try
                        {
                            if (fn == "cast_request")
                                reply = protocol.cast_request(state, body);
                            else if(fn=="extra_marker_go")
                                reply = protocol.extra_marker_go(state);
                            else if (fn == "cast_response")
                                reply = protocol.cast_response(state, name, body);
                            else if (fn == "cast_prepare")
                                reply = Protocol::cast_prepare(state, body);
                            else if (fn == "cast_cancel")
                                reply = Packet{name, Protocol::cast_cancel(state, body)};
                            else if (fn == "aura_response")
                                reply = Protocol::aura_response(state, name, body);
                            else if (fn == "aura_cancel")
                                reply = Packet{name, Protocol::aura_cancel(state, body)};
                            else if (fn == "initialize")
                                reply = Protocol::initialize_response(state, name, body);
                            else if (fn == "currency")
                                reply = Protocol::currency_response(name, body);
                            else if (fn == "reputation")
                                reply = Protocol::reputation_response(name, body, get(request, "factions").as_array());
                            else if (fn == "social_request")
                                reply = Protocol::social_request(name, body);
                            else if (fn == "social_response")
                                reply = Protocol::social_response(name, body);
                            else if (fn == "party_request")
                                reply = Protocol::party_request(name, body);
                            else if(fn=="inventory_request")
                                reply=Protocol::inventory_request(state,name,body);
                            else if(fn=="inventory_response")
                                reply=protocol.inventory_response(name,body);
                            else if (fn == "party_response")
                                reply = Protocol::party_response(state, name, body, get(request, "identities").as_array());
                            else if (fn == "party_state")
                                reply = Protocol::party_state(state, name, body);
                            else if (fn == "party_profiles")
                                reply = Protocol::party_profiles(name, body);
                            else if (fn == "party_roles")
                                reply = Protocol::party_roles(name, body);
                            else if (fn == "account_request")
                                reply = Protocol::account_request(state, name, body);
                            else if (fn == "account_response")
                                reply = Protocol::account_response(state, name, body);
                            else if (fn == "achievement")
                                reply = Protocol::achievement_response(state, name, body);
                            else if (fn == "reputation_request")
                                reply = Protocol::reputation_request(name, body);
                            else if (fn == "loot_response")
                                reply = Protocol::loot_response(state, name, body);
                            else if (fn == "loot_request")
                            {
                                for (auto const &packet : Protocol::loot_request(state, name, body))
                                    emit(packet);
                                continue;
                            }
                            else if (fn == "movement_control")
                                reply = protocol.movement_control(state, name, body);
                            else if (fn == "movement_ack")
                                reply = protocol.movement_ack(state, name, body);
                            else if (fn == "object_updates")
                                reply = protocol.object_updates(state, body);
                            else if (fn == "transfer_response")
                                reply = Protocol::transfer_response(state, name, body);
                            else if (fn == "transfer_request")
                                reply = Protocol::transfer_request(state, name, body);
                            else if (fn == "transfer_resume")
                                reply = Protocol::transfer_resume(state);
                            else if (fn == "gossip_response")
                                reply = Protocol::gossip_response(state, name, body);
                            else if (fn == "gossip_request")
                                reply = Protocol::gossip_request(state, name, body);
                            else if (fn == "taxi_response")
                                reply = Protocol::taxi_response(state, name, body);
                            else if (fn == "taxi_request")
                                reply = Protocol::taxi_request(state, name, body, get(request, "paths"));
                            else if (fn == "creature_movement")
                            {
                                for (auto const &packet : Protocol::creature_movement(state, body))
                                    emit(packet);
                                continue;
                            }
                            else if (fn == "gameobject_query")
                                reply = Packet{name, Protocol::gameobject_query(state, body)};
                            else if (fn == "gameobject_reply")
                                reply = Protocol::gameobject_reply(state, body);
                            else if (fn == "creature_query")
                            {
                                if (auto encoded = Protocol::creature_query(state, body))
                                    reply = Packet{name, *encoded};
                            }
                            else if (fn == "creature_reply")
                                reply = Protocol::creature_reply(state, body);
                            else if (fn == "npc_query")
                                reply = Packet{name, Protocol::npc_query(state, body)};
                            else if (fn == "npc_reply")
                            {
                                auto const &broadcasts = get(request, "broadcasts");
                                reply = Protocol::npc_reply(
                                    state, body, broadcasts.is_array() ? &broadcasts.as_array() : nullptr);
                            }
                            else if (fn == "destroy")
                                reply = Protocol::destroy_object(state, body);
                            else
                                throw std::runtime_error("unknown stateful codec function");
                            if (reply)
                                emit(*reply);
                            else
                                replies.push_back(nullptr);
                        }
                        catch (std::exception const &e)
                        {
                            replies.push_back(Object{{"error", e.what()}});
                        }
                    }
                    result = replies;
                }
                else
                    throw std::runtime_error("unknown codec operation");
                std::cout << json::serialize(Object{{"result", result}}) << '\n';
            }
            catch (std::exception const &error)
            {
                std::cout << json::serialize(Object{{"error", error.what()}}) << '\n';
            }
        }
    }
    catch (std::exception const &e)
    {
        std::cerr << e.what() << '\n';
        return 1;
    }
}
