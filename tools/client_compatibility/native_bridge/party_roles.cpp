#include "protocol.hpp"
#include <array>

namespace bridge
{
namespace
{
std::uint64_t low(std::array<std::uint8_t,8> const &octets)
{
    std::uint64_t value=0;for(unsigned i=0;i<8;++i)value|=static_cast<std::uint64_t>(octets[i])<<(8*i);
    if(!value || value>0xffffffff)throw std::runtime_error("invalid group role player identity");
    return value;
}
}
Reply Protocol::party_roles(std::string const &name,View body)
{
    Reader r(body);Writer w;
    if(name=="CMSG_INITIATE_ROLE_POLL")
    {
        bool present=r.bits(1);
        if(present && r.take<std::uint8_t>()!=0)throw std::runtime_error("unsupported role poll party category");
        r.end();return Packet{"CMSG_ROLE_POLL_BEGIN",{}};
    }
    if(name=="CMSG_SET_ROLE")
    {
        bool present=r.bits(1);auto guid=r.guid();auto role=r.take<std::uint8_t>();
        if(present && r.take<std::uint8_t>()!=0)throw std::runtime_error("unsupported role party category");
        r.end();auto id=integer(guid[0]);
        if(!id || id>0xffffffff || integer(guid[1])!=player_high() || (role&~15))
            throw std::runtime_error("invalid role selection");
        auto octets=Writer().put(id).finish();w.put<std::uint32_t>(role);
        for(auto i:{2,6,3,7,5,1,0,4})w.bits(octets[i]!=0,1);
        for(auto i:{6,4,1,3,0,5,2,7})if(octets[i])w.put<std::uint8_t>(octets[i]^1);
        return Packet{name,w.finish()};
    }
    if(name=="SMSG_ROLE_POLL_BEGIN")
    {
        std::array<std::uint8_t,8> guid{};
        for(auto i:{1,5,7,3,2,4,0,6})guid[i]=r.bits(1);
        for(auto i:{4,7,0,5,1,6,2,3})if(guid[i])guid[i]=r.take<std::uint8_t>()^1;
        r.end();return Packet{"SMSG_ROLE_POLL_INFORM",w.put<std::uint8_t>(0).guid(low(guid),player_high()).finish()};
    }
    if(name=="SMSG_ROLE_CHANGED_INFORM")
    {
        std::array<std::uint8_t,8> from{},changed{};
        from[1]=r.bits(1);
        for(auto i:{0,2,4,7,3})changed[i]=r.bits(1);
        from[7]=r.bits(1);changed[5]=r.bits(1);
        for(auto i:{5,4,3})from[i]=r.bits(1);
        changed[6]=r.bits(1);from[2]=r.bits(1);from[6]=r.bits(1);changed[1]=r.bits(1);from[0]=r.bits(1);
        auto byte=[&](auto &a,unsigned i){if(a[i])a[i]=r.take<std::uint8_t>()^1;};
        byte(from,7);byte(changed,3);byte(from,6);byte(changed,4);byte(changed,0);
        auto next=r.take<std::uint32_t>();
        byte(changed,5);byte(changed,2);byte(from,0);byte(from,4);byte(changed,1);
        byte(from,3);byte(from,5);byte(from,2);byte(changed,6);byte(changed,7);byte(from,1);
        auto previous=r.take<std::uint32_t>();r.end();
        if((next|previous)&~15u)throw std::runtime_error("invalid native group role mask");
        return Packet{name,w.put<std::uint8_t>(0).guid(low(from),player_high()).guid(low(changed),player_high())
            .pack("2B",{previous,next}).finish()};
    }
    return {};
}
} // namespace bridge
