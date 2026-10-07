// Line-delimited synthetic/differential test interface. Never open a live socket.
#include "crypto.hpp"
#include "fields.hpp"
#include "protocol.hpp"
#include "currency.hpp"
#include "archaeology.hpp"
#include "reputation_fields.hpp"
#include "events.hpp"
#include "pet_rename_probe.hpp"
#include "stable_probe.hpp"
#include "stables.hpp"
#include "ready_check.hpp"
#include "chat.hpp"
#include "chat_channels.hpp"
#include "chat_probe.hpp"
#include "lifecycle.hpp"
#include "guild_packets.hpp"
#include "merchants.hpp"
#include "item_notifications.hpp"
#include "repairs.hpp"
#include "trainers.hpp"
#include "quests.hpp"
#include "talents.hpp"
#include "mail.hpp"
#include "auctions.hpp"
#include "appearance.hpp"
#include "character_list.hpp"
#include "data.hpp"
#include "player_ui_state.hpp"
#include "item_text.hpp"
#include "who.hpp"
#include "pet_packets.hpp"
#include "pet_casts.hpp"
#include "control_skill_metadata.hpp"
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
                if (op == "public_chat_probe")
                    result = public_chat_probe(str(get(request, "name")), data("body"));
                else if (op == "control_skill_hotfixes")
                    result = control_skill_hotfixes(data("native"),get(request,"config"));
                else if (op == "public_channel_probe")
                    result = public_channel_probe(str(get(request, "name")), data("body"));
                else if (op == "actionbar_toggle_request")
                {
                    if (auto packet = actionbar_toggle_request(data("body"), truth(get(request, "in_world"))))
                        result = Array{packet->first, hex(packet->second)};
                    else
                        result = nullptr;
                }
                else if (op == "sheath_request")
                {
                    auto packet=sheath_request(data("body"),truth(get(request,"in_world")));
                    result=Array{packet.first,hex(packet.second)};
                }
                else if (op == "stand_state_request" || op == "stand_state_update")
                {
                    auto packet=op=="stand_state_request" ?
                        stand_state_request(data("body"),truth(get(request,"in_world"))) :
                        stand_state_update(data("body"));
                    result=Array{packet.first,hex(packet.second)};
                }
                else if (op == "pack")
                    result = hex(Writer()
                                     .pack(str(get(request, "format")), get(request, "values").as_array())
                                     .finish());
                else if(op=="event_diagnostic")
                {
                    Events events(str(get(request,"root")));
                    events.event(str(get(request,"kind")),get(request,"fields").as_object());result=true;
                }
                else if(op=="packet_diagnostic")
                {
                    Events events(str(get(request,"root")));
                    events.packet("from_client",str(get(request,"name")),data("body"),"fixture");result=true;
                }
                else if(op=="owned_stable_request_probe")
                    result=owned_stable_request_probe(str(get(request,"root")),str(get(request,"direction")),
                        str(get(request,"name")),data("body"),str(get(request,"session")),number(get(request,"now")));
                else if(op=="owned_pet_rename_probe")
                    result=owned_pet_rename_probe(str(get(request,"root")),str(get(request,"direction")),
                        str(get(request,"name")),data("body"),str(get(request,"session")),
                        number(get(request,"now")));
                else if(op=="chat_context")
                {
                    require_chat_character(truth(get(request,"created")),truth(get(request,"active_world")));result=true;
                }
                else if(op=="mail_context")
                {
                    require_mail_character(str(get(request,"name")),truth(get(request,"created")),
                        truth(get(request,"active_world")),truth(get(request,"in_world")));result=true;
                }
                else if(op=="native_guild_roster")
                    result=native_guild_roster(data("body"));
                else if(op=="login_quest_reads")
                {
                    LoginBarrier barrier;Array output;
                    for(auto const &a:get(request,"actions").as_array())
                    {
                        auto fn=str(get(a,"fn"));Array packets;
                        if(fn=="begin")barrier.begin();
                        else if(fn=="read")barrier.defer_quest_read({str(get(a,"name")),unhex(str(get(a,"body")))});
                        else if(fn=="mail")barrier.defer_mail_read({str(get(a,"name")),unhex(str(get(a,"body")))});
                        else if(fn=="template")barrier.defer_template_read({str(get(a,"name")),unhex(str(get(a,"body")))});
                        else if(fn=="release")for(auto const &p:barrier.release_quest_reads())packets.push_back(Array{p.first,hex(p.second)});
                        else throw std::runtime_error("unknown login quest read action");
                        output.push_back(Object{{"queued",barrier.quest_reads.size()+barrier.template_reads.size()+barrier.mail_read},{"packets",packets}});
                    }
                    result=output;
                }
                else if(op=="login_active_mover")
                {
                    LoginBarrier barrier;State state;Array output;
                    state.character=Object{{"guid",get(request,"guid")}};
                    for(auto const &a:get(request,"actions").as_array())
                    {
                        auto fn=str(get(a,"fn"));bool forward=false;
                        if(fn=="begin")
                        {state.character=Object{{"guid",get(request,"guid")}};barrier.begin();}
                        else if(fn=="world")barrier.accept({"SMSG_LOGIN_VERIFY_WORLD",Bytes(20)});
                        else if(fn=="ack")forward=barrier.accept_active_mover(state,unhex(str(get(a,"body"))),truth(get(a,"active_instance")));
                        else if(fn=="create")
                        {state.created=true;forward=barrier.release_active_mover(state);}
                        else if(fn=="logout"){finish_logout(state);barrier={};}
                        else throw std::runtime_error("unknown active mover login action");
                        output.push_back(Object{{"forward",forward},{"deferred",barrier.mover_ack},
                            {"awaiting_player",barrier.awaiting_player}});
                    }
                    result=output;
                }
                else if(op=="login_barrier")
                {
                    LoginBarrier barrier;Array output;
                    for(auto const &action:get(request,"actions").as_array())
                    {
                        if(str(get(action,"fn"))=="begin")barrier.begin();
                        else
                        {
                            Array packets;
                            for(auto const &packet:barrier.accept({str(get(action,"name")),unhex(str(get(action,"body")))}))
                                packets.push_back(Array{packet.first,hex(packet.second)});
                            output.push_back(Object{{"packets",packets},{"pending",barrier.pending},
                                {"queued",barrier.deferred.size()},{"bytes",barrier.bytes}});
                        }
                    }
                    result=output;
                }
                else if(op=="logout_reset")
                {
                    State state;state.character=Object{{"guid",2}};state.created=true;
                    state.self_snapshot=Object{{"guid",2}};state.visible_units[3]=true;
                    state.visible_gameobjects[4]=true;state.inventory_items[5]=true;
                    state.casts[6]=true;state.visible_auras[7]=true;state.pending_movement[8]=true;
                    state.party_members.insert(9);state.party_leader=2;state.latest_movement={1,2};
                    state.account_times[3]=123;bool callback=false;
                    state.creature_queries.insert(10);state.creature_query_waiting.insert(11);
                    state.creature_query_queue.push_back(11);
                    state.native_send=[&](std::string const &,View){callback=true;};
                    finish_logout(state);state.native_send("fixture",{});
                    result=Object{{"last_guid",state.last_logout_guid},{"account_time",state.account_times[3]},
                        {"callback",callback},{"created",state.created},{"character",state.character},
                        {"snapshot",state.self_snapshot},{"world_entries",state.visible_units.size()+
                            state.visible_gameobjects.size()+state.inventory_items.size()+state.casts.size()+
                            state.visible_auras.size()+state.pending_movement.size()+state.party_members.size()+
                            state.latest_movement.size()+state.party_leader+state.creature_queries.size()+
                            state.creature_query_waiting.size()+state.creature_query_queue.size()}};
                }
                else if(op=="marker_diagnostic")
                {
                    Events events(str(get(request,"root")));events.marker_placed("fixture",get(request,"location"));result=true;
                }
                else if (op == "auth_success")
                    result = hex(auth_success(get(request, "race_classes").as_array()));
                else if (op == "character_list")
                {
                    std::unordered_map<unsigned, Array> displays;
                    for (auto const &row : get(request, "displays").as_array())
                    {
                        auto const &v = row.as_array();
                        displays[integer(v.at(0))] = Array{v.at(1), v.at(2), v.at(3)};
                    }
                    result = hex(character_list(get(request, "characters").as_array(),
                                                get(request, "equipment").as_array(), displays,
                                                get(request, "race_classes").as_array()));
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
                else if(op=="auction_sparse")
                {
                    Object rows;for(auto const &[id,row]:auction_sparse(data("body")))rows[std::to_string(id)]=row;
                    result=rows;
                }
                else if(op=="auction_metadata")
                {
                    auto items=load_auction_items(str(get(request,"root")));Object selected;
                    for(auto const &id:get(request,"ids").as_array())
                        if(auto found=items.find(integer(id));found!=items.end())selected[std::to_string(integer(id))]=found->second;
                    result=Object{{"count",items.size()},{"items",selected}};
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
                else if(op=="watched_faction_update")
                    result=hex(watched_faction_block(protocol,get(request,"snapshot"),get(request,"changed")));
                else if (op == "quest_update")
                    result = hex(protocol.quest_block(get(request, "snapshot"), get(request, "changed")));
                else if (op == "glyph_update")
                    result = hex(protocol.glyph_block(get(request, "snapshot"), get(request, "changed")));
                else if (op == "guild_update")
                    result=hex(protocol.guild_block(get(request,"snapshot"),get(request,"character"),get(request,"changed"),
                        request.as_object().contains("visibility")?integer(get(request,"visibility")):1));
                else if (op == "unit_update")
                    result = hex(protocol.scalar_block(get(request, "snapshot"),get(request,"character"),get(request,"changed"),integer(get(request,"visibility"))));
                else if(op=="inventory_update")
                    result=hex(protocol.inventory_block(get(request,"snapshot"),get(request,"changed"),
                        request.as_object().contains("visibility")?integer(get(request,"visibility")):1));
                else if(op=="item_update")
                    result=hex(protocol.item_update(get(request,"snapshot"),get(request,"changed")));
                else if (op == "object_block")
                {
                    auto kind = str(get(request, "kind"));
                    auto const &snapshot = get(request, "snapshot");
                    auto const &character = get(request, "character");
                    result = hex(kind == "player" ? protocol.player_block(snapshot, character)
                                 : kind == "public_player" ? protocol.public_player_block(snapshot,character)
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
                    AuctionItems auction_items;
                    if(auto const &items=get(request,"auction_items");items.is_object())
                        for(auto const &[id,item]:items.as_object())auction_items[std::stoul(std::string(id))]=item;
                    State state;
                    state.character = get(request, "character");
                    state.self_snapshot = get(request, "snapshot");
                    state.created = !state.self_snapshot.is_null();
                    state.last_logout_guid = integer(get(request,"last_logout_guid"));
                    state.gossip_menu = get(request, "gossip_menu");
                    if(auto const &items=get(request,"inventory_items");items.is_array())
                        for(auto const &record:items.as_array())state.inventory_items[integer(get(record,"guid"))]=record;
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
                            if(fn=="pet_request")reply=pet_request(protocol,state,name,body);
                            else if(fn=="translate_pet_cast")
                            {
                                auto translation=translate_pet_cast(protocol,state,name,body);
                                replies.push_back(Object{{"packet",translation.packet ?
                                    Value(Array{translation.packet->first,hex(translation.packet->second)}) : Value(nullptr)},
                                    {"rejection",translation.rejection}});
                                continue;
                            }
                            else if(fn=="translate_pet_action" || fn=="translate_pet_set_action" || fn=="translate_pet_rename")
                            {
                                auto translation=fn=="translate_pet_rename" ? translate_pet_rename(protocol,state,body) :
                                    fn=="translate_pet_action" ? translate_pet_action(protocol,state,body) :
                                    translate_pet_set_action(protocol,state,body);
                                replies.push_back(Object{{"packet",translation.packet ?
                                    Value(Array{translation.packet->first,hex(translation.packet->second)}) : Value(nullptr)},
                                    {"rejection",translation.rejection}});
                                continue;
                            }
                            else if(fn=="pet_response")reply=pet_response(protocol,state,name,body);
                            else if(fn=="pet_ready")reply=pet_ready(protocol,state);
                            else if(fn=="combat_request")
                                reply=Protocol::combat_request(state,name,body);
                            else if(fn=="combat_response")
                                reply=Protocol::combat_response(state,name,body);
                            else if (fn == "cast_request")
                                reply = protocol.cast_request(state, body);
                            else if(fn=="item_use")reply=protocol.item_use(state,body);
                            else if(fn=="item_text_request")reply=item_text_request(protocol,state,name,body);
                            else if(fn=="item_text_response")reply=item_text_response(protocol,state,name,body);
                            else if(fn=="who_request")reply=who_request(state,name,body);
                            else if(fn=="who_response")reply=who_complete(state,body,get(request,"identities").as_array());
                            else if(fn=="item_use_rejected")reply=Packet{"SMSG_CAST_FAILED",Protocol::item_use_rejected(body)};
                            else if(fn=="extra_marker_go")
                                reply = protocol.extra_marker_go(state);
                            else if (fn == "cast_response")
                                reply = protocol.cast_response(state, name, body);
                            else if (fn == "cast_prepare")
                                reply = Protocol::cast_prepare(state, body);
                            else if (fn == "cast_cancel")
                            {
                                auto cancelled=Protocol::cast_cancel(state,body);
                                if(!cancelled.empty())reply=Packet{name,cancelled};
                            }
                            else if (fn == "aura_response")
                                reply = Protocol::aura_response(state, name, body);
                            else if (fn == "aura_cancel")
                            {
                                reply=pet_aura_cancel(protocol,state,body);
                                if(!reply)reply=Packet{name,Protocol::aura_cancel(state,body)};
                            }
                            else if (fn == "initialize")
                                reply = Protocol::initialize_response(state, name, body);
                            else if (fn == "currency")
                                reply = Protocol::currency_response(name, body);
                            else if (fn == "currency_request")
                                reply = currency_request(name, body);
                            else if (fn == "appearance_request")
                                reply = appearance_request(name, body);
                            else if (fn == "research_history")
                                reply = research_history(state,name,body);
                            else if (fn == "research_complete")
                                research_complete(name,body);
                            else if (fn == "reputation")
                                reply = Protocol::reputation_response(name, body, get(request, "factions").as_array());
                            else if (fn == "social_request")
                                reply = Protocol::social_request(name, body);
                            else if(fn=="guild_request")
                                reply=guild_request(state,name,body);
                            else if(fn=="guild_response")
                                reply=guild_response(name,body,get(request,"identities").as_array());
                            else if (fn == "chat_request")
                                reply = chat_request(state,name,body);
                            else if (fn == "chat_response")
                                reply = chat_response(state,name,body);
                            else if (fn == "social_response")
                                reply = Protocol::social_response(name, body);
                            else if (fn == "party_request")
                                reply = Protocol::party_request(name, body);
                            else if(fn=="equipment_request")
                                reply=equipment_request(state,name,body);
                            else if(fn=="equipment_response")
                                reply=equipment_response(state,name,body);
                            else if(fn=="inventory_request")
                                reply=Protocol::inventory_request(state,name,body);
                            else if(fn=="bank_request")
                                reply=Protocol::bank_request(state,name,body);
                            else if(fn=="bank_response")
                                reply=protocol.bank_response(state,name,body);
                            else if(fn=="bank_close")
                                Protocol::bank_close(state,name,body);
                            else if(fn=="stable_request")
                                reply=stable_request(protocol,state,name,body);
                            else if(fn=="stable_response")
                                reply=stable_response(protocol,state,name,body,get(action,"models").as_array());
                            else if(fn=="stable_open_response")
                                reply=stable_open_response(state);
                            else if(fn=="merchant_request")
                                reply=merchant_request(protocol,state,name,body);
                            else if(fn=="merchant_response")
                                reply=merchant_response(protocol,state,name,body);
                            else if(fn=="auction_request")
                                reply=auction_request(protocol,state,name,body,auction_items);
                            else if(fn=="auction_response")
                                reply=auction_response(protocol,state,name,body,auction_items);
                            else if(fn=="item_notification")
                                reply=item_notification(name,body);
                            else if(fn=="repair_request")
                                reply=repair_request(protocol,state,name,body);
                            else if(fn=="trainer_request")
                                reply=trainer_request(protocol,state,name,body);
                            else if(fn=="trainer_response")
                                reply=trainer_response(protocol,state,name,body);
                            else if(fn=="trainer_completion")
                                trainer_completion(name,body);
                            else if(fn=="quest_request")
                                reply=quest_request(protocol,state,name,body);
                            else if(fn=="quest_response")
                                reply=quest_response(protocol,state,name,body);
                            else if(fn=="talent_response")
                                reply=talent_response(name,body);
                            else if(fn=="talent_request")
                                reply=talent_request(name,body);
                            else if(fn=="mail_request")
                                reply=mail_request(protocol,state,name,body);
                            else if(fn=="mail_response")
                                reply=mail_response(protocol,state,name,body);
                            else if(fn=="inspect_request")
                                reply=Protocol::inspect_request(state,name,body);
                            else if(fn=="inspect_response")
                                reply=protocol.inspect_response(state,name,body);
                            else if(fn=="trade_request")
                                reply=Protocol::trade_request(state,name,body);
                            else if(fn=="trade_response")
                                reply=protocol.trade_response(name,body);
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
                            else if(fn=="logout_complete")
                                finish_logout(state);
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
                                reply = protocol.object_updates(state, body,get(request,"players").is_array()?
                                    get(request,"players").as_array():Array{});
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
                            else if (fn == "public_player_movement")
                                reply = protocol.public_player_movement(state, body);
                            else if (fn == "creature_movement")
                            {
                                for (auto const &packet : Protocol::creature_movement(state, body))
                                    emit(packet);
                                continue;
                            }
                            else if (fn == "gameobject_query")
                                reply = Packet{"CMSG_GAMEOBJECT_QUERY", Protocol::gameobject_query(state, body)};
                            else if (fn == "gameobject_reply")
                                reply = Protocol::gameobject_reply(state, body);
                            else if (fn == "creature_query")
                            {
                                if (auto encoded = Protocol::creature_query(state, body))
                                    reply = Packet{"CMSG_CREATURE_QUERY", *encoded};
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
