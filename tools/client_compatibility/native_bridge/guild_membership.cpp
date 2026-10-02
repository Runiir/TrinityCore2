#include "guild_packets.hpp"
#include <algorithm>

namespace bridge
{
namespace
{
std::uint64_t member(Reader &r)
{
    auto guid=r.guid();auto low=integer(guid[0]);
    if(!low || low>0xffffffff || integer(guid[1])!=player_high())
        throw std::runtime_error("invalid guild member identity");
    return low;
}
Bytes legacy_guid(std::uint64_t guid,std::initializer_list<unsigned> mask,std::initializer_list<unsigned> order)
{
    std::array<std::uint8_t,8> octets{};std::memcpy(octets.data(),&guid,8);Writer w;
    for(auto i:mask)w.bits(octets[i]!=0,1);
    for(auto i:order)if(octets[i])w.put<std::uint8_t>(octets[i]^1);
    return w.finish();
}
}
Reply guild_membership_request(std::string const &name,View body)
{
    Reader r(body);Writer w;
    if(name=="CMSG_GUILD_INVITE_BY_NAME")
    {
        auto size=r.bits(9),extra=r.bits(1);auto text=r.raw(size);if(extra)r.take<std::int32_t>();r.end();
        auto dash=std::find(text.begin(),text.end(),'-');text=text.first(dash-text.begin());
        if(text.empty() || text.size()>127 || std::find(text.begin(),text.end(),0)!=text.end())
            throw std::runtime_error("invalid native guild invite name");
        return Packet{"CMSG_GUILD_INVITE",w.bits(text.size(),7).raw(text).finish()};
    }
    if(name=="CMSG_ACCEPT_GUILD_INVITE" || name=="CMSG_GUILD_DECLINE_INVITATION")
    {
        auto guild=r.guid();if(!integer(guild[0]) || integer(guild[0])>0xffffffff || integer(guild[1])!=guild_high())
            throw std::runtime_error("invalid guild invitation identity");
        if(name=="CMSG_GUILD_DECLINE_INVITATION")r.bits(1);
        r.end();
        return Packet{name=="CMSG_ACCEPT_GUILD_INVITE" ? "CMSG_GUILD_ACCEPT" : "CMSG_GUILD_DECLINE",{}};
    }
    if(name=="CMSG_GUILD_LEAVE" || name=="CMSG_GUILD_DELETE")
    {r.end();return Packet{name=="CMSG_GUILD_DELETE" ? "CMSG_GUILD_DISBAND" : name,{}};}
    if(name=="CMSG_GUILD_UPDATE_MOTD_TEXT" || name=="CMSG_GUILD_UPDATE_INFO_TEXT")
    {
        auto size=r.bits(11);auto text=r.raw(size);r.end();
        if(name=="CMSG_GUILD_UPDATE_MOTD_TEXT")w.bits(size,11);
        else w.bits(size,12);
        return Packet{name=="CMSG_GUILD_UPDATE_MOTD_TEXT" ? "CMSG_GUILD_MOTD" : "CMSG_GUILD_INFO_TEXT",w.raw(text).finish()};
    }
    if(name=="CMSG_GUILD_PROMOTE_MEMBER" || name=="CMSG_GUILD_DEMOTE_MEMBER" || name=="CMSG_GUILD_OFFICER_REMOVE_MEMBER")
    {
        auto guid=member(r);r.end();
        if(name=="CMSG_GUILD_PROMOTE_MEMBER")return Packet{"CMSG_GUILD_PROMOTE",legacy_guid(guid,{7,2,5,6,1,0,3,4},{0,5,2,3,6,4,1,7})};
        if(name=="CMSG_GUILD_DEMOTE_MEMBER")return Packet{"CMSG_GUILD_DEMOTE",legacy_guid(guid,{7,1,5,6,2,3,0,4},{1,2,7,5,6,0,4,3})};
        return Packet{"CMSG_GUILD_REMOVE",legacy_guid(guid,{6,5,4,0,1,3,7,2},{2,6,5,7,1,4,3,0})};
    }
    return {};
}
Reply guild_membership_response(std::string const &name,View body)
{
    if(name!="SMSG_GUILD_INVITE")return {};
    Reader r(body);r.take<std::uint32_t>();auto border=r.take<std::uint32_t>(),border_color=r.take<std::uint32_t>();
    auto style=r.take<std::uint32_t>(),background=r.take<std::uint32_t>(),color=r.take<std::uint32_t>();
    std::array<std::uint8_t,8> fresh{},old{};
    fresh[3]=r.bits(1);fresh[2]=r.bits(1);auto old_name_size=r.bits(8);fresh[1]=r.bits(1);
    for(auto i:{6,4,1,5,7,2})old[i]=r.bits(1);
    for(auto i:{7,0,6})fresh[i]=r.bits(1);
    auto guild_name_size=r.bits(8);old[3]=r.bits(1);old[0]=r.bits(1);fresh[5]=r.bits(1);
    auto inviter_size=r.bits(7);fresh[4]=r.bits(1);r.align();
    auto byte=[&](auto &guid,unsigned i){if(guid[i])guid[i]=r.take<std::uint8_t>()^1;};
    byte(fresh,1);byte(old,3);byte(fresh,6);byte(old,2);byte(old,1);byte(fresh,0);
    auto old_name=r.raw(old_name_size);byte(fresh,7);byte(fresh,2);auto inviter=r.raw(inviter_size);
    for(auto i:{7,6,5,0})byte(old,i);
    byte(fresh,4);auto title=r.raw(guild_name_size);
    byte(fresh,5);byte(fresh,3);byte(old,4);r.end();
    std::uint64_t fresh_id=0,old_id=0;std::memcpy(&fresh_id,fresh.data(),8);std::memcpy(&old_id,old.data(),8);
    if(inviter_size>63 || guild_name_size>127 || old_name_size>127)throw std::runtime_error("guild invite string exceeds modern bound");
    Writer w;w.bits(inviter_size,6).bits(guild_name_size,7).bits(old_name_size,7).flush()
        .pack("II",{1,1}).guid(guild_identity(fresh_id)).pack("I",{old_id ? 1 : 0}).guid(guild_identity(old_id))
        .pack("6I",{style,color,border,border_color,background,0}).raw(inviter).raw(title).raw(old_name);
    return Packet{name,w.finish()};
}
}
