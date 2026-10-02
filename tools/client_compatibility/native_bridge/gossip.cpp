#include "protocol.hpp"
#include <algorithm>

namespace bridge
{
Bytes native_text(Reader &r)
{
    Bytes result;
    for (unsigned i = 0; i <= 4096; ++i)
    {
        auto n = r.take<std::uint8_t>();
        if (!n)
            return result;
        result.push_back(n);
    }
    throw std::runtime_error("invalid native gossip string");
}
Packet Protocol::gossip_request(State &owner, std::string const &name, View body)
{
    Reader r(body);
    auto guid = owned_unit(owner, r.guid());
    if (name == "CMSG_TALK_TO_GOSSIP")
    {
        r.end();
        return {"CMSG_GOSSIP_HELLO", Writer().put(guid).finish()};
    }
    auto menu = r.take<std::uint32_t>();
    auto index = r.take<std::int32_t>();
    auto size = r.bits(8);
    auto promo = r.raw(size);
    r.end();
    auto const &state = owner.gossip_menu;
    if (state.is_null() || guid != integer(get(state, "guid")) || menu != integer(get(state, "menu")))
        throw std::runtime_error("gossip choice does not belong to native menu");
    bool found = false;
    for (auto const &option : get(state, "options").as_array())
        found |= signed_integer(option) == index;
    if (!found)
        throw std::runtime_error("gossip choice does not belong to native menu");
    return {"CMSG_GOSSIP_SELECT_OPTION",
            Writer().pack("QII", {guid, menu, index}).raw(promo).put<std::uint8_t>(0).finish()};
}
Reply Protocol::gossip_response(State &owner, std::string const &name, View body)
{
    Reader r(body);
    if (name == "SMSG_GOSSIP_COMPLETE")
    {
        r.end();
        owner.gossip_menu = nullptr;
        return Packet{name, Writer().bits(0, 1).finish()};
    }
    if (name != "SMSG_GOSSIP_MESSAGE")
        return {};
    auto guid = r.take<std::uint64_t>();
    auto menu = r.take<std::uint32_t>(), text_id = r.take<std::uint32_t>(), count = r.take<std::uint32_t>();
    auto record = owner.visible_units.find(guid);
    if (record == owner.visible_units.end())
        return {};
    if (count > 64)
        throw std::runtime_error("native gossip option count exceeds bound");
    struct Option
    {
        Array values;
        Bytes title, confirm;
    };
    std::vector<Option> options;
    Array indices;
    for (unsigned i = 0; i < count; ++i)
    {
        auto values = r.unpack("iBBI");
        auto title = native_text(r), confirm = native_text(r);
        indices.push_back(values[0]);
        options.push_back({values, title, confirm});
    }
    auto quests_count = r.take<std::uint32_t>();
    if (quests_count > 64)
        throw std::runtime_error("native gossip quest count exceeds bound");
    struct Quest
    {
        Array values;
        Bytes title;
    };
    std::vector<Quest> quests;
    for (unsigned i = 0; i < quests_count; ++i)
    {
        auto values = r.unpack("iiiiB");
        auto title = native_text(r);
        quests.push_back({values, title});
    }
    r.end();
    owner.gossip_menu = Object{{"guid", guid}, {"menu", menu}, {"text_id", text_id}, {"options", indices}};
    Writer w;
    w.guid(modern_guid(guid, integer(get(record->second, "map"))))
        .pack("5i", {menu, 0, 0, count, quests_count})
        .bits(text_id != 0, 1)
        .bits(0, 1);
    for (auto const &option : options)
    {
        auto const &v = option.values;
        w.pack("iBB4i", {v[0], v[1], v[2], v[3], 0, 0, v[0]});
        w.bits(option.title.size(), 12)
            .bits(option.confirm.size(), 12)
            .bits(0, 2)
            .bits(0, 2)
            .bits(1, 8)
            .pack("I", {0})
            .raw(option.title)
            .raw(option.confirm);
    }
    if (text_id)
        w.pack("I", {text_id});
    for (auto const &quest : quests)
    {
        auto const &v = quest.values;
        w.pack("9i", {v[0], 0, v[1], v[2], v[2], 0, v[3], 0, 0})
            .bits(truth(v[4]), 1)
            .bits(0, 3)
            .bits(quest.title.size(), 9)
            .raw(quest.title);
    }
    return Packet{name, w.finish()};
}
Reply Protocol::combat_request(State const &owner, std::string const &name, View body)
{
    Reader r(body);
    if (name == "CMSG_ATTACK_STOP")
    {
        r.end();
        return Packet{name, {}};
    }
    auto identity = r.guid();
    r.end();
    if (name == "CMSG_SET_SELECTION" && identity == Array{0, 0})
        return Packet{name, Writer().pack("Q", {0}).finish()};
    if(name=="CMSG_SET_SELECTION" && owner.guid() && identity==Array{owner.guid(),player_high()})
        return Packet{name,Writer().pack("Q",{owner.guid()}).finish()};
    for (auto const &[guid, record] : owner.visible_units)
        if (modern_guid(guid, integer(get(record, "map"))) == identity)
            return Packet{name, Writer().put(guid).finish()};
    return {};
}
Reply Protocol::combat_response(State const &owner, std::string const &name, View body)
{
    if (name != "SMSG_ATTACK_START" && name != "SMSG_ATTACK_STOP")
        return {};
    Reader r(body);
    std::uint64_t attacker, victim;
    Value dead;
    if (name == "SMSG_ATTACK_START")
    {
        attacker = r.take<std::uint64_t>();
        victim = r.take<std::uint64_t>();
    }
    else
    {
        attacker = native_guid(r);
        victim = native_guid(r);
        dead = r.take<std::uint32_t>();
    }
    r.end();
    Writer w;
    w.guid(modern_guid(attacker, owner.map())).guid(modern_guid(victim, owner.map()));
    if (!dead.is_null())
        w.bits(truth(dead), 1);
    return Packet{name, w.finish()};
}
} // namespace bridge
