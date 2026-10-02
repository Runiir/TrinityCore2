// Ordinary client caches stay in native account_data / character_account_data.
// Cache contents are never written to the packet diagnostic journal.
#include "protocol.hpp"
#include <limits>

namespace bridge
{
namespace
{
void identity(State const &owner, Array const &guid, std::int32_t type)
{
    bool global = type >= 0 && type < 8 && (0x15 & (1u << type));
    auto low = integer(guid[0]), high = integer(guid[1]);
    if (global && !low && !high) return;
    if (!owner.created || !low || low != owner.guid() || high != player_high())
        throw std::runtime_error("account cache character ownership mismatch");
}
}
Reply Protocol::account_request(State const &owner, std::string const &name, View body)
{
    Reader r(body);
    if (name == "CMSG_REQUEST_ACCOUNT_DATA")
    {
        auto guid = r.guid();auto type = r.take<std::int32_t>();r.end();
        if (type < 0 || type >= 8) return {};
        identity(owner,guid,type);return Packet{name,Writer().put(type).finish()};
    }
    if (name == "CMSG_UPDATE_ACCOUNT_DATA")
    {
        auto time = r.take<std::int64_t>();auto size = r.take<std::uint32_t>();auto guid = r.guid();
        auto type = r.take<std::int32_t>();auto count = r.take<std::uint32_t>();auto compressed = r.raw(count);r.end();
        if (type < 0 || type >= 8) return {};
        identity(owner,guid,type);
        if(time<0 || time>std::numeric_limits<std::uint32_t>::max() || size>65535 || count>65535 || (!size && count))
            throw std::runtime_error("native cache size or time exceeds bound");
        return Packet{name,Writer().pack("III",{type,time,size}).raw(compressed).finish()};
    }
    return {};
}
Reply Protocol::account_response(State &owner, std::string const &name, View body)
{
    Reader r(body);Writer w;
    if (name == "SMSG_ACCOUNT_DATA_TIMES")
    {
        auto time = r.take<std::uint32_t>();auto enabled = r.take<std::uint8_t>();auto mask = r.take<std::uint32_t>();
        if(enabled>1 || mask & ~255u)throw std::runtime_error("invalid native cache time mask");
        for(unsigned i=0;i<8;++i)if(mask & (1u<<i))owner.account_times[i]=r.take<std::uint32_t>();
        r.end();w.guid(owner.guid(),owner.guid() ? player_high() : 0).put<std::int64_t>(time);
        for(auto t:owner.account_times)w.put<std::int64_t>(t);
        return Packet{name,w.finish()};
    }
    if (name == "SMSG_UPDATE_ACCOUNT_DATA")
    {
        auto guid = r.take<std::uint64_t>();auto type = r.take<std::uint32_t>();
        auto time = r.take<std::uint32_t>(), size = r.take<std::uint32_t>();auto data=r.raw(r.remaining());r.end();
        if(type>=8 || size>65535 || (guid && guid!=owner.guid()))throw std::runtime_error("invalid native cache response");
        if(!size)data={};
        w.pack("qI",{time,size}).guid(guid,guid ? player_high() : 0).pack("iI",{type,data.size()}).raw(data);
        return Packet{name,w.finish()};
    }
    return {};
}
} // namespace bridge
