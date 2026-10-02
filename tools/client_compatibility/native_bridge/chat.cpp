#include "chat.hpp"

namespace bridge
{
namespace
{
std::string text(Reader &r,unsigned size,unsigned maximum)
{
    if(size>maximum)throw std::runtime_error("chat string exceeds protocol bound");
    auto raw=r.raw(size);std::string value(raw.begin(),raw.end());
    if(value.find('\0')!=std::string::npos)throw std::runtime_error("embedded chat terminator");
    return value;
}
std::string terminated(Reader &r,unsigned maximum)
{
    std::string value;
    while(true)
    {
        auto c=r.take<std::uint8_t>();if(!c)return value;
        if(value.size()>=maximum)throw std::runtime_error("native chat string exceeds bound");
        value.push_back(c);
    }
}
std::string counted(Reader &r,unsigned maximum)
{
    auto count=r.take<std::uint32_t>();if(!count || count>maximum+1)throw std::runtime_error("invalid native chat count");
    auto value=text(r,count-1,maximum);
    if(r.take<std::uint8_t>())throw std::runtime_error("missing native chat terminator");
    return value;
}
}
Reply chat_request(State const &,std::string const &name,View body)
{
    static std::unordered_map<std::string,std::string> const names={
        {"CMSG_CHAT_MESSAGE_SAY","CMSG_MESSAGECHAT_SAY"},{"CMSG_CHAT_MESSAGE_YELL","CMSG_MESSAGECHAT_YELL"},
        {"CMSG_CHAT_MESSAGE_PARTY","CMSG_MESSAGECHAT_PARTY"},{"CMSG_CHAT_MESSAGE_RAID","CMSG_MESSAGECHAT_RAID"},
        {"CMSG_CHAT_MESSAGE_RAID_WARNING","CMSG_MESSAGECHAT_RAID_WARNING"},{"CMSG_CHAT_MESSAGE_GUILD","CMSG_MESSAGECHAT_GUILD"},
        {"CMSG_CHAT_MESSAGE_OFFICER","CMSG_MESSAGECHAT_OFFICER"},{"CMSG_CHAT_MESSAGE_INSTANCE_CHAT","CMSG_MESSAGECHAT_BATTLEGROUND"},
        {"CMSG_CHAT_MESSAGE_AFK","CMSG_MESSAGECHAT_AFK"},{"CMSG_CHAT_MESSAGE_DND","CMSG_MESSAGECHAT_DND"},
        {"CMSG_CHAT_MESSAGE_EMOTE","CMSG_MESSAGECHAT_EMOTE"},{"CMSG_CHAT_MESSAGE_WHISPER","CMSG_MESSAGECHAT_WHISPER"},
        {"CMSG_CHAT_MESSAGE_CHANNEL","CMSG_MESSAGECHAT_CHANNEL"}};
    auto found=names.find(name);if(found==names.end())return {};
    Reader r(body);Writer w;
    bool plain=name=="CMSG_CHAT_MESSAGE_AFK" || name=="CMSG_CHAT_MESSAGE_DND" || name=="CMSG_CHAT_MESSAGE_EMOTE";
    auto language=plain ? 0 : r.take<std::int32_t>();
    if(!plain)w.pack("i",{language});
    std::string target,message;
    if(name=="CMSG_CHAT_MESSAGE_WHISPER")
    {
        auto guid=r.guid();auto realm=r.take<std::uint32_t>();
        if((realm && realm!=1 && realm!=0x01010001) || (integer(guid[1]) && integer(guid[1])!=player_high()))
            throw std::runtime_error("whisper outside the local realm");
        // Installed Whitemane 60895 uses nine bits here; the pinned upstream
        // snapshot used seven. This layout is backed by the captured UI request.
        auto target_size=r.bits(9),message_size=r.bits(11);
        if(target_size<2 || message_size<2)throw std::runtime_error("whisper requires a name and text");
        target=text(r,target_size-1,126);if(r.take<std::uint8_t>())throw std::runtime_error("invalid whisper target terminator");
        message=text(r,message_size-1,511);if(r.take<std::uint8_t>())throw std::runtime_error("invalid whisper message terminator");
        // Legacy names are realm-local. A modern same-realm suffix is presentation only.
        if(auto pos=target.find('-');pos!=std::string::npos)target.resize(pos);
        if(target.empty())throw std::runtime_error("empty local whisper name");
        w.bits(target.size(),10).bits(message.size(),9).raw(target).raw(message);
    }
    else if(name=="CMSG_CHAT_MESSAGE_CHANNEL")
    {
        r.guid();auto target_size=r.bits(9),message_size=r.bits(11);
        if(r.bits(1))r.bits(1);
        target=text(r,target_size,127);message=text(r,message_size,511);
        if(target.empty())throw std::runtime_error("empty native channel name");
        w.bits(target.size(),10).bits(message.size(),9).raw(message).raw(target);
    }
    else
    {
        auto size=r.bits(11);
        if(name=="CMSG_CHAT_MESSAGE_SAY" || name=="CMSG_CHAT_MESSAGE_PARTY" || name=="CMSG_CHAT_MESSAGE_RAID" ||
            name=="CMSG_CHAT_MESSAGE_RAID_WARNING" || name=="CMSG_CHAT_MESSAGE_INSTANCE_CHAT")r.bits(1);
        message=text(r,size,511);w.bits(message.size(),9).raw(message);
    }
    r.end();return Packet{found->second,w.finish()};
}
Reply chat_response(State const &owner,std::string const &name,View body)
{
    if(name!="SMSG_MESSAGECHAT" && name!="SMSG_GM_MESSAGECHAT")return {};
    Reader r(body);Writer w;
    auto kind=r.take<std::uint8_t>();auto language=r.take<std::int32_t>();auto sender=r.take<std::uint64_t>();
    r.take<std::uint32_t>();std::string sender_name,target_name,channel,prefix;
    // Native BuildChatPacket variants, including NPC speech and system messages.
    bool monster=kind==12 || kind==13 || kind==14 || kind==15 || kind==16 || kind==41 || kind==42 || kind==47;
    bool foreign=kind==8;bool battleground=kind>=36 && kind<=38;
    if(monster || foreign || (!battleground && name=="SMSG_GM_MESSAGECHAT"))sender_name=counted(r,2047);
    if(kind==17)channel=terminated(r,127);
    auto target=r.take<std::uint64_t>();
    if((monster && target && target>>48!=0 && target>>52!=0xf14) || (battleground && target && target>>48!=0))target_name=counted(r,2047);
    if(language==-1)prefix=terminated(r,31);
    auto message=counted(r,4095);auto flags=r.take<std::uint8_t>();std::uint32_t achievement=0;float display=0;bool hide=false;
    if(kind==48 || kind==49)achievement=r.take<std::uint32_t>();
    else if(kind==41 || kind==42){display=r.take<float>();hide=r.take<std::uint8_t>()!=0;}
    r.end();
    w.pack("Bi",{kind,language}).guid(Protocol::modern_guid(sender,owner.map())).guid().guid()
        .guid(Protocol::modern_guid(target,owner.map())).pack("IIiHfi",{0x01010001,0x01010001,achievement,flags,display,0});
    w.bits(sender_name.size(),11).bits(target_name.size(),11).bits(prefix.size(),5).bits(channel.size(),7).bits(message.size(),12)
        .bits(hide,1).bits(0,1).bits(0,1).bits(0,1).flush();
    w.raw(sender_name).raw(target_name).raw(prefix).raw(channel).raw(message);
    return Packet{"SMSG_CHAT",w.finish()};
}
} // namespace bridge
