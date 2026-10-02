// Wire contracts: pinned Trinity cata_classic 6426c2bd and native ReputationMgr.
#include "protocol.hpp"

namespace bridge
{
Reply Protocol::reputation_request(std::string const &name, View body)
{
    if(name!="CMSG_SET_FACTION_AT_WAR" && name!="CMSG_SET_FACTION_NOT_AT_WAR" &&
       name!="CMSG_SET_FACTION_INACTIVE" && name!="CMSG_SET_WATCHED_FACTION")return {};
    Reader r(body);auto index=r.take<std::int32_t>();Writer w;w.put(index);
    if(name=="CMSG_SET_WATCHED_FACTION")
    {
        if(index < -1 || index >= 256)throw std::runtime_error("invalid watched reputation index");
        r.end();return Packet{name,w.finish()};
    }
    if(index<0 || index>=256)throw std::runtime_error("reputation index exceeds native bound");
    if(name=="CMSG_SET_FACTION_INACTIVE")w.put<std::uint8_t>(r.bits(1));
    else w.put<std::uint8_t>(name=="CMSG_SET_FACTION_AT_WAR");
    r.end();return Packet{name=="CMSG_SET_FACTION_INACTIVE" ? name : "CMSG_SET_FACTION_ATWAR",w.finish()};
}
Reply Protocol::reputation_response(std::string const &name, View body, Array const &factions)
{
    if (name != "SMSG_INITIALIZE_FACTIONS" && name != "SMSG_SET_FACTION_STANDING" &&
        name != "SMSG_SET_FACTION_VISIBLE" && name != "SMSG_SET_FACTION_NOT_VISIBLE")
        return {};
    std::unordered_map<unsigned, unsigned> ids;
    for (auto const &row : factions)
        ids[integer(get(row, "index"))] = integer(get(row, "id"));
    auto id = [&](unsigned index)
    {
        auto pos = ids.find(index);
        if (pos == ids.end()) throw std::runtime_error("unknown native reputation index");
        return pos->second;
    };
    Reader r(body);Writer w;
    if (name == "SMSG_INITIALIZE_FACTIONS")
    {
        auto count = r.take<std::uint32_t>();
        if (count > 1024) throw std::runtime_error("native faction count exceeds bound");
        Array rows;
        for (unsigned index = 0; index < count; ++index)
        {
            auto flags = r.take<std::uint8_t>();auto standing = r.take<std::int32_t>();
            if (ids.contains(index)) rows.push_back(Array{id(index), flags, standing});
            else if (flags || standing) throw std::runtime_error("unmapped native faction state");
        }
        r.end();w.pack("II", {rows.size(), 0});
        for (auto const &row : rows) w.pack("iHi", row.as_array());
    }
    else if (name == "SMSG_SET_FACTION_STANDING")
    {
        auto bonus = r.take<float>();auto visual = r.take<std::uint8_t>();
        auto count = r.take<std::uint32_t>();
        if (visual > 1 || count > 1024) throw std::runtime_error("invalid native faction update");
        w.pack("fI", {bonus, count});
        for (unsigned i = 0; i < count; ++i)
        {
            auto index = r.take<std::uint32_t>();auto standing = r.take<std::int32_t>();
            w.pack("iii", {index, standing, id(index)});
        }
        r.end();w.bits(visual, 1);
    }
    else
    {
        auto index = r.take<std::uint32_t>();r.end();
        id(index);w.pack("i", {index});
    }
    return Packet{name, w.finish()};
}
} // namespace bridge
