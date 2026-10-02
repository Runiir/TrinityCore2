#include "guild_packets.hpp"

namespace bridge
{
Reply guild_roster_response(View body,Array const &identities);
Reply guild_request(State const &owner,std::string const &name,View body)
{
    Reader r(body);
    if(name=="CMSG_GUILD_GET_ROSTER")
    {r.end();return Packet{name,{}};}
    if(name=="CMSG_GUILD_PERMISSIONS_QUERY")
    {r.end();return Packet{name,{}};}
    if(name=="CMSG_GUILD_GET_RANKS")
    {
        auto guild=r.guid();r.end();auto low=integer(guild[0]);
        if(!low || low>0xffffffff || integer(guild[1])!=guild_high())
            throw std::runtime_error("invalid guild ranks identity");
        auto native=low|(0x1ffull<<52);std::array<std::uint8_t,8> octets{};
        std::memcpy(octets.data(),&native,8);Writer w;
        for(auto i:{2,3,0,6,4,7,5,1})w.bits(octets[i]!=0,1);
        for(auto i:{3,4,5,7,1,0,6,2})if(octets[i])w.put<std::uint8_t>(octets[i]^1);
        return Packet{"CMSG_GUILD_QUERY_RANKS",w.finish()};
    }
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
    if(name=="SMSG_GUILD_RANKS")
    {
        auto count=r.bits(18);if(count>10)throw std::runtime_error("native guild ranks exceed bound");
        std::vector<unsigned> lengths;for(unsigned i=0;i<count;++i)lengths.push_back(r.bits(7));r.align();
        w.put<std::uint32_t>(count);
        for(auto size:lengths)
        {
            auto id=r.take<std::uint32_t>();auto tabs=r.unpack("16I");
            auto money=r.take<std::uint32_t>(),flags=r.take<std::uint32_t>();auto title=r.raw(size);
            auto order=r.take<std::uint32_t>();if(id>255)throw std::runtime_error("guild rank ID exceeds bound");
            w.pack("BIII",{id,order,flags,money});
            for(unsigned i=0;i<8;++i)w.pack("II",{tabs[i*2+1],tabs[i*2]});
            w.bits(size,7).flush().raw(title);
        }
        r.end();return Packet{name,w.finish()};
    }
    if(name=="SMSG_GUILD_PERMISSIONS_QUERY_RESULTS")
    {
        auto rank=r.take<std::uint32_t>(),purchased=r.take<std::uint32_t>();
        auto flags=r.take<std::uint32_t>(),money=r.take<std::uint32_t>();auto count=r.bits(23);
        if(count>8 || purchased>8)throw std::runtime_error("native guild permissions exceed tab bound");
        r.align();w.pack("IIIII",{rank,flags,money,purchased,count});
        for(unsigned i=0;i<count;++i)w.pack("II",r.unpack("II"));
        r.end();return Packet{name,w.finish()};
    }
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
