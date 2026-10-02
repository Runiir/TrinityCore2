// Pinned modern PartyPackets::Read and the native 4.3.4 handlers.
#include "protocol.hpp"
#include <array>

namespace bridge
{
namespace
{
void party_index(Reader &r, bool present)
{
    if (present && r.take<std::uint8_t>() != 0) throw std::runtime_error("unsupported party category");
}
std::uint64_t player(Reader &r, bool empty = false)
{
    auto g = r.guid();auto low = integer(g[0]), high = integer(g[1]);
    if (empty && !low && !high) return 0;
    if (!low || low > 0xffffffff || high != player_high()) throw std::runtime_error("invalid party player GUID");
    return low;
}
}
Reply Protocol::party_request(std::string const &name, View body)
{
    Reader r(body);Writer w;std::string native;
    if (name == "CMSG_PARTY_INVITE")
    {
        bool has_index = r.bits(1);r.align();
        auto name_length = r.bits(9), realm_length = r.bits(9);
        auto roles = r.take<std::uint32_t>();auto guid = player(r, true);
        auto target = r.raw(name_length), realm = r.raw(realm_length);party_index(r, has_index);r.end();
        if (target.empty() || name_length > 127 || realm_length > 511 || roles > 15)
            throw std::runtime_error("invalid party invitation");
        auto octets = Writer().put(guid).finish();w.pack("II", {0, roles});
        w.bits(octets[2] != 0,1).bits(octets[7] != 0,1).bits(realm_length,9).bits(octets[3] != 0,1)
            .bits(name_length,10);
        for (auto i : {5,4,6,0,1}) w.bits(octets[i] != 0,1);
        w.flush();
        auto byte = [&](unsigned i) {if (octets[i]) w.put<std::uint8_t>(octets[i] ^ 1);};
        for (auto i : {4,7,6}) byte(i);
        w.raw(target).raw(realm);
        for (auto i : {1,0,5,3,2}) byte(i);
        return Packet{name,w.finish()};
    }
    if (name == "CMSG_PARTY_INVITE_RESPONSE")
    {
        bool has_index = r.bits(1), accept = r.bits(1), has_roles = r.bits(1);party_index(r,has_index);
        auto roles = has_roles ? r.take<std::uint32_t>() : 0;r.end();
        if (roles > 15) throw std::runtime_error("invalid party role mask");
        w.bits(has_roles,1).bits(accept,1);
        if (has_roles) w.put(roles);
        return Packet{name,w.finish()};
    }
    if (name == "CMSG_LEAVE_GROUP" || name == "CMSG_REQUEST_PARTY_JOIN_UPDATES" || name == "CMSG_DO_READY_CHECK")
    {
        bool present = r.bits(1);party_index(r,present);r.end();
        native = name == "CMSG_LEAVE_GROUP" ? "CMSG_GROUP_DISBAND" :
            name == "CMSG_DO_READY_CHECK" ? "MSG_RAID_READY_CHECK" : "CMSG_GROUP_REQUEST_JOIN_UPDATES";
        return Packet{native,{}};
    }
    if (name == "CMSG_CONVERT_RAID")
    {
        auto raid = r.bits(1);r.end();return Packet{"CMSG_GROUP_RAID_CONVERT",Writer().put<std::uint8_t>(raid).finish()};
    }
    if (name == "CMSG_SET_EVERYONE_IS_ASSISTANT")
    {
        bool present=r.bits(1),apply=r.bits(1);party_index(r,present);r.end();
        return Packet{name,Writer().bits(apply,1).finish()};
    }
    if (name == "CMSG_SET_ASSISTANT_LEADER")
    {
        bool present=r.bits(1),apply=r.bits(1);auto guid=player(r);party_index(r,present);r.end();
        return Packet{"CMSG_GROUP_ASSISTANT_LEADER",Writer().put(guid).put<std::uint8_t>(apply).finish()};
    }
    if (name == "CMSG_SET_PARTY_LEADER" || name == "CMSG_REQUEST_PARTY_MEMBER_STATS")
    {
        bool present = r.bits(1);auto guid = player(r);party_index(r,present);r.end();
        return Packet{name == "CMSG_SET_PARTY_LEADER" ? "CMSG_GROUP_SET_LEADER" : name,Writer().put(guid).finish()};
    }
    if (name == "CMSG_PARTY_UNINVITE")
    {
        bool present = r.bits(1);auto length = r.bits(8);auto guid = player(r);party_index(r,present);
        auto reason = r.raw(length);r.end();
        return Packet{"CMSG_GROUP_UNINVITE_GUID",Writer().put(guid).raw(reason).put<std::uint8_t>(0).finish()};
    }
    if (name == "CMSG_READY_CHECK_RESPONSE")
    {
        bool ready = r.bits(1), present = r.bits(1);party_index(r,present);r.end();
        return Packet{"MSG_RAID_READY_CHECK",Writer().put<std::uint8_t>(ready).finish()};
    }
    return {};
}
} // namespace bridge
