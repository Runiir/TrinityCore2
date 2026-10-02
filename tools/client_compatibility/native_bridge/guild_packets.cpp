#include "guild_packets.hpp"

namespace bridge
{
Reply guild_roster_response(View body,Array const &identities);
Reply guild_request(State const &owner,std::string const &name,View body)
{
    Reader r(body);
    if(name=="CMSG_GUILD_GET_ROSTER")
    {r.end();return Packet{name,{}};}
    if(name=="CMSG_QUERY_GUILD_INFO")
    {
        auto guild=r.guid(),player=r.guid();r.end();auto low=integer(guild[0]),who=integer(player[0]);
        // Installed 60895 queries the guild with an empty player GUID. The
        // legacy handler requires a member identity, so use the owned player.
        if(!who && !integer(player[1])){who=owner.guid();player[1]=player_high();}
        if(!low || low>0xffffffff || integer(guild[1])!=guild_high() || !who || who>0xffffffff || integer(player[1])!=player_high())
            throw std::runtime_error("invalid guild query identity");
        return Packet{"CMSG_GUILD_QUERY",Writer().pack("QQ",{low|(0x1ffull<<52),who}).finish()};
    }
    return {};
}
Reply guild_response(std::string const &name,View body,Array const &identities)
{
    if(name=="SMSG_GUILD_ROSTER")return guild_roster_response(body,identities);
    Reader r(body);Writer w;
    if(name=="SMSG_QUERY_GUILD_INFO_RESPONSE")
    {
        auto guild=guild_identity(r.take<std::uint64_t>());auto title=native_text(r);
        std::array<Bytes,10> ranks;for(auto &rank:ranks)rank=native_text(r);
        auto orders=r.unpack("10I"),ids=r.unpack("10I"),emblem=r.unpack("5I");auto count=r.take<std::uint32_t>();r.end();
        if(count>10 || title.size()>127)throw std::runtime_error("invalid native guild query ranks");
        w.guid(guild).bits(1,1).flush().guid(guild).pack("II",{1,count}).pack("5I",emblem).bits(title.size(),7).flush();
        for(unsigned i=0;i<count;++i)
        {
            if(ranks[i].size()>127)throw std::runtime_error("native guild rank name exceeds bound");
            w.pack("II",{ids[i],orders[i]}).bits(ranks[i].size(),7).flush().raw(ranks[i]);
        }
        return Packet{name,w.raw(title).finish()};
    }
    if(name=="SMSG_GUILD_COMMAND_RESULT")
    {
        auto command=r.take<std::uint32_t>();auto target=native_text(r);auto error=r.take<std::uint32_t>();r.end();
        if(target.size()>255)throw std::runtime_error("native guild command target exceeds bound");
        return Packet{name,w.pack("ii",{error,command}).bits(target.size(),8).flush().raw(target).finish()};
    }
    return {};
}
}
