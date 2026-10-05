// Native ChannelHandler/ChannelAppenders versus cata_classic 6426c2bd packets.
#include "chat_channels.hpp"
#include <cctype>

namespace bridge
{
namespace
{
std::string text(Reader &r,unsigned size)
{
    if(size>127)throw std::runtime_error("channel string exceeds bound");
    auto raw=r.raw(size);std::string value(raw.begin(),raw.end());
    if(value.find('\0')!=std::string::npos)throw std::runtime_error("embedded channel terminator");
    return value;
}
std::string terminated(Reader &r)
{
    std::string value;
    while(auto c=r.take<std::uint8_t>())
    {
        if(value.size()==127)throw std::runtime_error("native channel string exceeds bound");
        value.push_back(c);
    }
    return value;
}
void require_name(std::string const &value)
{
    if(value.empty())throw std::runtime_error("empty channel name");
}
Array channel_guid(State const &owner,std::string const &name,unsigned id,unsigned flags)
{
    // Native channels are identified by name. Give that identity a stable local
    // modern GUID; the counter is independent of process lifetime and player.
    std::uint64_t counter=14695981039346656037ull;
    for(unsigned char c:name){counter^=std::tolower(c);counter*=1099511628211ull;}
    unsigned race=integer(get(owner.character,"race"));
    bool horde=race==2 || race==5 || race==6 || race==8 || race==9 || race==10;
    std::uint64_t high=(26ull<<58)|(1ull<<42)|(std::uint64_t(id!=0)<<25)|
        (std::uint64_t(bool(flags&4))<<24)|(std::uint64_t(horde?5:3)<<4);
    return {counter,high};
}
bool fixture(std::string const &name)
{
    if(name.size()!=22 || !name.starts_with("TC442UIChannel"))return false;
    for(unsigned char c:std::string_view(name).substr(14))if(!std::isxdigit(c))return false;
    return true;
}
}

Reply chat_channel_request(std::string const &name,View body)
{
    Reader r(body);Writer w;std::string channel,password,native;
    if(name=="CMSG_CHAT_JOIN_CHANNEL")
    {
        auto id=r.take<std::uint32_t>();auto voice=r.bits(1),internal=r.bits(1);
        auto size=r.bits(7),pass_size=r.bits(7);channel=text(r,size);password=text(r,pass_size);
        w.put(id).bits(voice,1).bits(internal,1).bits(size,8).bits(pass_size,8).raw(channel).raw(password);
        native="CMSG_JOIN_CHANNEL";
    }
    else if(name=="CMSG_CHAT_LEAVE_CHANNEL")
    {
        auto id=r.take<std::uint32_t>();channel=text(r,r.bits(7));
        w.put(id).bits(channel.size(),8).raw(channel);native="CMSG_LEAVE_CHANNEL";
    }
    else if(name=="CMSG_CHAT_CHANNEL_LIST" || name=="CMSG_CHAT_CHANNEL_DISPLAY_LIST" || name=="CMSG_CHAT_CHANNEL_OWNER")
    {
        channel=text(r,r.bits(7));w.bits(channel.size(),8).raw(channel);
        native=name;
    }
    else return {};
    r.end();require_name(channel);return Packet{native,w.finish()};
}

Reply chat_channel_response(State const &owner,std::string const &name,View body)
{
    Reader r(body);Writer w;
    if(name=="SMSG_CHANNEL_NOTIFY")
    {
        auto kind=r.take<std::uint8_t>();auto channel=terminated(r);require_name(channel);
        if(kind==2)
        {
            auto flags=r.take<std::uint8_t>();auto id=r.take<std::uint32_t>();
            auto instance=r.take<std::uint32_t>();r.end();
            w.bits(channel.size(),7).bits(0,11).put<std::uint32_t>(flags).put<std::uint8_t>(0)
                .put(id).put<std::uint64_t>(instance).guid(channel_guid(owner,channel,id,flags)).raw(channel);
            return Packet{"SMSG_CHANNEL_NOTIFY_JOINED",w.finish()};
        }
        if(kind==3)
        {
            auto id=r.take<std::uint32_t>();auto suspended=r.take<std::uint8_t>();r.end();
            if(suspended>1)throw std::runtime_error("invalid native channel suspension");
            w.bits(channel.size(),7).bits(suspended,1).put(id).raw(channel);
            return Packet{"SMSG_CHANNEL_NOTIFY_LEFT",w.finish()};
        }
        std::uint64_t sender=0,target=0;std::string sender_name;unsigned old_flags=0,new_flags=0;
        switch(kind)
        {
            case 0:case 1:case 7:case 8:case 13:case 14:case 23:case 24:case 34:case 35:
                sender=r.take<std::uint64_t>();break;
            case 12:sender=r.take<std::uint64_t>();old_flags=r.take<std::uint8_t>();new_flags=r.take<std::uint8_t>();break;
            case 18:case 20:case 21:target=r.take<std::uint64_t>();sender=r.take<std::uint64_t>();break;
            case 9:case 11:case 22:case 29:case 30:sender_name=terminated(r);break;
            case 4:case 5:case 6:case 10:case 15:case 16:case 17:case 19:case 25:case 26:
            case 27:case 28:case 31:case 32:case 33:break;
            default:throw std::runtime_error("unsupported native channel notification");
        }
        r.end();if(sender_name.size()>63)throw std::runtime_error("channel sender name exceeds bound");
        w.bits(kind,6).bits(channel.size(),7).bits(sender_name.size(),6)
            .guid(Protocol::modern_guid(sender,owner.map())).guid().put<std::uint32_t>(0x01010001)
            .guid(Protocol::modern_guid(target,owner.map())).put<std::uint32_t>(0x01010001).put<std::uint32_t>(0);
        if(kind==12)w.put<std::uint8_t>(old_flags).put<std::uint8_t>(new_flags);
        w.raw(channel).raw(sender_name);return Packet{"SMSG_CHANNEL_NOTIFY",w.finish()};
    }
    if(name=="SMSG_CHANNEL_LIST")
    {
        auto display=r.take<std::uint8_t>();auto channel=terminated(r);auto flags=r.take<std::uint8_t>();
        auto count=r.take<std::uint32_t>();require_name(channel);
        if(display>1 || count>4096 || r.remaining()!=count*9)throw std::runtime_error("invalid native channel list");
        w.bits(display,1).bits(channel.size(),7).put<std::uint32_t>(flags).put(count).raw(channel);
        for(unsigned i=0;i<count;++i)
        {auto guid=r.take<std::uint64_t>();auto role=r.take<std::uint8_t>();w.guid(Protocol::modern_guid(guid,owner.map())).put<std::uint32_t>(0x01010001).put(role);}
        r.end();return Packet{"SMSG_CHANNEL_LIST",w.finish()};
    }
    if(name=="SMSG_USERLIST_ADD" || name=="SMSG_USERLIST_UPDATE" || name=="SMSG_USERLIST_REMOVE")
    {
        auto guid=r.take<std::uint64_t>();unsigned role=0;
        if(name!="SMSG_USERLIST_REMOVE")role=r.take<std::uint8_t>();
        auto flags=r.take<std::uint8_t>();auto count=r.take<std::uint32_t>();auto channel=terminated(r);r.end();require_name(channel);
        w.guid(Protocol::modern_guid(guid,owner.map()));
        if(name!="SMSG_USERLIST_REMOVE")w.put<std::uint8_t>(role);
        w.put<std::uint32_t>(flags).put(count).bits(channel.size(),7).raw(channel);
        return Packet{name,w.finish()};
    }
    return {};
}

bool public_channel_probe(std::string const &name,View body)
{
    try
    {
        Reader r(body);std::string channel,password;
        if(name=="CMSG_CHAT_JOIN_CHANNEL" || name=="CMSG_JOIN_CHANNEL")
        {
            if(r.take<std::uint32_t>()!=0)return false;
            r.bits(1);r.bits(1);
            unsigned width=name=="CMSG_JOIN_CHANNEL"?8:7;
            auto size=r.bits(width),pass=r.bits(width);channel=text(r,size);password=text(r,pass);r.end();
            return fixture(channel) && password.empty();
        }
        if(name=="CMSG_CHAT_LEAVE_CHANNEL" || name=="CMSG_LEAVE_CHANNEL")
        {r.take<std::uint32_t>();channel=text(r,r.bits(name=="CMSG_LEAVE_CHANNEL"?8:7));r.end();return fixture(channel);}
        if(name=="CMSG_CHAT_CHANNEL_LIST" || name=="CMSG_CHAT_CHANNEL_DISPLAY_LIST" || name=="CMSG_CHAT_CHANNEL_OWNER")
        {
            // Modern/native requests share opcode names but use seven/eight
            // length bits. Admit only a complete exact fixture under either.
            for(unsigned width:{7,8})
            {
                try{Reader request(body);auto value=text(request,request.bits(width));request.end();if(fixture(value))return true;}
                catch(std::exception const &){}
            }
            return false;
        }
        if(name=="SMSG_CHANNEL_NOTIFY")
        {
            if(!body.empty() && body[0]==11)
            {r.take<std::uint8_t>();channel=terminated(r);auto owner=terminated(r);r.end();return fixture(channel) && (owner=="Harnessone" || owner=="Harnesstwo");}
            if(!body.empty() && body[0]>35)
            {
                if(r.bits(6)!=11)return false;
                auto size=r.bits(7),owner_size=r.bits(6);
                r.guid();r.guid();r.raw(4);r.guid();r.raw(8);channel=text(r,size);auto owner=text(r,owner_size);r.end();
                return fixture(channel) && (owner=="Harnessone" || owner=="Harnesstwo");
            }
            auto kind=r.take<std::uint8_t>();channel=terminated(r);
            if(kind==2)r.raw(9);else if(kind==3)r.raw(5);else if(kind==0 || kind==8 || kind==23)r.raw(8);else return false;
            r.end();return fixture(channel);
        }
        if(name=="SMSG_CHANNEL_NOTIFY_JOINED")
        {auto size=r.bits(7);if(r.bits(11))return false;r.raw(17);r.guid();channel=text(r,size);r.end();return fixture(channel);}
        if(name=="SMSG_CHANNEL_NOTIFY_LEFT")
        {auto size=r.bits(7);r.bits(1);r.raw(4);channel=text(r,size);r.end();return fixture(channel);}
        if(name=="SMSG_CHANNEL_LIST")
        {
            bool native=!body.empty() && body[0]<=1;unsigned count;
            if(native){r.take<std::uint8_t>();channel=terminated(r);r.raw(1);count=r.take<std::uint32_t>();}
            else{r.bits(1);auto size=r.bits(7);r.raw(4);count=r.take<std::uint32_t>();channel=text(r,size);}
            if(!fixture(channel) || count>2)return false;
            for(unsigned i=0;i<count;++i)
            {
                std::uint64_t guid;
                if(native)guid=r.take<std::uint64_t>();
                else{auto pair=r.guid();guid=integer(pair[0]);if(integer(pair[1])!=player_high() || r.take<std::uint32_t>()!=0x01010001)return false;}
                if(guid!=1 && guid!=2)return false;
                r.raw(1);
            }
            r.end();return true;
        }
    }
    catch(std::exception const &){}
    return false;
}
}
