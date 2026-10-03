#include "protocol.hpp"

namespace bridge
{
namespace
{
constexpr unsigned CREATURE_IN_FLIGHT=64,CREATURE_PENDING=4096;
Bytes creature_request(State const &owner,unsigned entry)
{
    for(auto const &[guid,record]:owner.visible_units)
        if(((guid>>32)&0xfffff)==entry)return Writer().pack("IQ",{entry,get(record,"guid")}).finish();
    return Writer().pack("IQ",{entry,0}).finish();
}
void drain_creature_query(State &owner)
{
    if(owner.creature_query_queue.empty())return;
    auto entry=owner.creature_query_queue.front();owner.creature_query_queue.pop_front();
    owner.creature_query_waiting.erase(entry);owner.creature_queries.insert(entry);
    owner.native_send("CMSG_CREATURE_QUERY",creature_request(owner,entry));
}
}
Bytes Protocol::gameobject_query(State &owner, View body)
{
    Reader r(body);
    auto entry = r.take<std::uint32_t>();
    auto identity = r.guid();
    r.end();
    auto native = owned_gameobject(owner, identity);
    if (entry != ((native >> 32) & 0xfffff))
        throw std::runtime_error("game-object template identity mismatch");
    if (owner.gameobject_queries.size() >= 256 || owner.gameobject_queries[entry].size() >= 64)
        throw std::runtime_error("game object queries exceed bound");
    owner.gameobject_queries[entry].push_back(identity);
    return Writer().pack("IQ", {entry, native}).finish();
}
Reply Protocol::gameobject_reply(State &owner, View body)
{
    Reader r(body);
    auto marker = r.take<std::uint32_t>();
    auto entry = marker & 0x7fffffff;
    bool allow = !(marker & 0x80000000);
    auto pos = owner.gameobject_queries.find(entry);
    if (pos == owner.gameobject_queries.end() || pos->second.empty())
        return {};
    auto identity = pos->second.front();
    pos->second.pop_front();
    if (pos->second.empty())
        owner.gameobject_queries.erase(pos);
    Writer stats;
    if (allow)
    {
        stats.raw(r.raw(8));
        for (unsigned i = 0; i < 7; ++i)
            stats.raw(native_text(r)).put<std::uint8_t>(0);
        stats.raw(r.raw(32 * 4)).zeros(3 * 4).raw(r.raw(4));
        Array quests;
        for (auto const &item : r.unpack("6I"))
            if (truth(item))
                quests.push_back(item);
        stats.pack("B", {quests.size()}).pack(std::string(quests.size(), 'I'), quests);
        r.take<std::int32_t>();
        stats.pack("i", {0});
    }
    r.end();
    return Packet{"SMSG_QUERY_GAME_OBJECT_RESPONSE", Writer()
                                                         .pack("I", {entry})
                                                         .guid(identity)
                                                         .bits(allow, 1)
                                                         .put<std::uint32_t>(stats.data().size())
                                                         .raw(stats.data())
                                                         .finish()};
}
std::optional<Bytes> Protocol::creature_query(State &owner, View body)
{
    Reader r(body);
    auto entry = r.take<std::uint32_t>();
    r.end();
    if(!entry || entry&0x80000000)throw std::runtime_error("invalid public creature template identity");
    if(owner.creature_queries.contains(entry) || owner.creature_query_waiting.contains(entry))return {};
    if(owner.creature_queries.size()+owner.creature_query_waiting.size()>=CREATURE_PENDING)
        throw std::runtime_error("creature queries exceed bounded pending queue");
    if(owner.creature_queries.size()>=CREATURE_IN_FLIGHT)
    {
        owner.creature_query_waiting.insert(entry);owner.creature_query_queue.push_back(entry);return {};
    }
    // Quest objectives and mail senders can reference unspawned creatures.
    // Native HandleCreatureQueryOpcode serves public templates by entry; GUID
    // is diagnostic only. Native data, including a missing-template reply,
    // remains authoritative. This grants no interaction with an unseen unit.
    owner.creature_queries.insert(entry);
    return creature_request(owner,entry);
}
Reply Protocol::creature_reply(State &owner, View body)
{
    Reader r(body);
    auto marker = r.take<std::uint32_t>();
    auto entry = marker & 0x7fffffff;
    bool allow = !(marker & 0x80000000);
    if (!owner.creature_queries.erase(entry))
        return {};
    Writer w;
    w.pack("I", {entry}).bits(allow, 1).flush();
    if (!allow)
    {
        r.end();
        drain_creature_query(owner);
        return Packet{"SMSG_QUERY_CREATURE_RESPONSE", w.finish()};
    }
    std::array<Bytes, 4> names, alternate;
    for (auto &n : names)
        n = native_text(r);
    for (auto &n : alternate)
        n = native_text(r);
    auto title = native_text(r), cursor = native_text(r);
    auto flags = r.unpack("2I"), kfr = r.unpack("3i"), credits = r.unpack("2I");
    Array displays;
    for (auto const &display : r.unpack("4I"))
        if (truth(display))
            displays.push_back(display);
    auto hp = r.take<float>(), mana = r.take<float>();
    auto leader = r.take<std::uint8_t>();
    Array quests;
    for (auto const &quest : r.unpack("6I"))
        if (truth(quest))
            quests.push_back(quest);
    auto move = r.take<std::uint32_t>(), expansion = r.take<std::uint32_t>();
    r.end();
    w.bits(title.size() + 1, 11).bits(1, 11).bits(cursor.size() + 1, 6).bits(0, 1).bits(leader != 0, 1);
    for (unsigned i = 0; i < 4; ++i)
        w.bits(names[i].size() + 1, 11).bits(alternate[i].size() + 1, 11);
    w.flush();
    for (unsigned i = 0; i < 4; ++i)
    {
        if (!names[i].empty())
            w.raw(names[i]).put<std::uint8_t>(0);
        if (!alternate[i].empty())
            w.raw(alternate[i]).put<std::uint8_t>(0);
    }
    w.pack("2I3iI2IIf", {flags[0], flags[1], kfr[0], kfr[1], kfr[2], 0, credits[0], credits[1],
                         displays.size(), static_cast<double>(displays.size())});
    for (auto const &display : displays)
        w.pack("Iff", {display, 1, 1});
    w.pack("ff2I8i", {hp, mana, quests.size(), 0, move, expansion, expansion, 0, 0, 0, 0, 0});
    if (!title.empty())
        w.raw(title).put<std::uint8_t>(0);
    if (!cursor.empty())
        w.raw(cursor).put<std::uint8_t>(0);
    w.pack(std::string(quests.size(), 'I'), quests);
    drain_creature_query(owner);
    return Packet{"SMSG_QUERY_CREATURE_RESPONSE", w.finish()};
}
Bytes Protocol::npc_query(State &owner, View body)
{
    Reader r(body);
    auto entry = r.take<std::uint32_t>();
    auto guid = owned_unit(owner, r.guid());
    r.end();
    if (owner.gossip_menu.is_null() || guid != integer(get(owner.gossip_menu, "guid")) ||
        entry != integer(get(owner.gossip_menu, "text_id")))
        throw std::runtime_error("NPC text query does not belong to the visible gossip menu");
    if (owner.npc_text_queries.size() >= 256)
        throw std::runtime_error("NPC text queries exceed bound");
    owner.npc_text_queries.insert(entry);
    return Writer().pack("IQ", {entry, guid}).finish();
}
Reply Protocol::npc_reply(State &owner, View body, Array const *broadcasts)
{
    Reader r(body);
    auto entry = r.take<std::uint32_t>();
    if (!owner.npc_text_queries.erase(entry))
        return {};
    Array probabilities;
    for (unsigned i = 0; i < 8; ++i)
    {
        probabilities.push_back(r.take<float>());
        native_text(r);
        native_text(r);
        r.raw(28);
    }
    r.end();
    Writer w;
    w.pack("I", {entry}).bits(broadcasts != nullptr, 1);
    Writer data;
    if (broadcasts)
        data.pack("8f", probabilities).pack("8I", *broadcasts);
    return Packet{"SMSG_QUERY_NPC_TEXT_RESPONSE",
                  w.put<std::uint32_t>(data.data().size()).raw(data.data()).finish()};
}
Reply Protocol::destroy_object(State &owner, View body)
{
    Reader r(body);
    auto native = r.take<std::uint64_t>();
    r.take<std::uint8_t>();
    r.end();
    Value record;
    if (auto pos = owner.visible_gameobjects.find(native); pos != owner.visible_gameobjects.end())
    {
        record = pos->second;
        owner.visible_gameobjects.erase(pos);
    }
    else if (auto pos = owner.visible_units.find(native); pos != owner.visible_units.end())
    {
        record = pos->second;
        owner.visible_units.erase(pos);
    }
    else if(auto pos=owner.inventory_items.find(native);pos!=owner.inventory_items.end())
    {record=pos->second;owner.inventory_items.erase(pos);}
    if (record.is_null())
        return {};
    if (!owner.taxi_menu.is_null() && integer(get(owner.taxi_menu, "vendor")) == native)
        owner.taxi_menu = nullptr;
    if (!owner.gossip_menu.is_null() && integer(get(owner.gossip_menu, "guid")) == native)
        owner.gossip_menu = nullptr;
    return Packet{"SMSG_UPDATE_OBJECT", object_packet(integer(get(record, "map")), {}, {}, {native})};
}
} // namespace bridge
