#include "guild_packets.hpp"

namespace bridge
{
Reply guild_event_response(std::string const &name,View body)
{
    if(name!="SMSG_GUILD_EVENT")return {};
    Reader r(body);auto event=r.take<std::uint8_t>(),count=r.take<std::uint8_t>();
    if(count>3)throw std::runtime_error("native guild event exceeds parameter bound");
    std::vector<Bytes> parameters;for(unsigned i=0;i<count;++i)parameters.push_back(native_text(r));
    auto guid=r.take<std::uint64_t>();r.end();Writer w;
    auto text=[&](unsigned i,unsigned maximum)->Bytes const &
    {
        if(i>=parameters.size() || parameters[i].size()>maximum)throw std::runtime_error("invalid native guild event text");
        return parameters[i];
    };
    if(event==3)
    {
        auto const &motd=text(0,2047);w.bits(motd.size(),11).raw(motd);
        return Packet{"SMSG_GUILD_EVENT_MOTD",w.finish()};
    }
    if(event==9){if(count || guid)throw std::runtime_error("invalid guild disband event");return Packet{"SMSG_GUILD_EVENT_DISBANDED",{}};}
    if(event==4 || event==5 || event==16 || event==17)
    {
        auto const &player=text(0,63);
        if(!guid || guid>0xffffffff)throw std::runtime_error("invalid native guild event player");
        if(event==5)
            w.bits(0,1).bits(player.size(),6).flush().guid(guid,player_high()).pack("I",{1}).raw(player);
        else
        {
            w.guid(guid,player_high()).pack("I",{1}).bits(player.size(),6);
            if(event==16 || event==17)w.bits(event==16,1);
            w.raw(player);
        }
        return Packet{event==4 ? "SMSG_GUILD_EVENT_PLAYER_JOINED" : event==5 ? "SMSG_GUILD_EVENT_PLAYER_LEFT" :
            "SMSG_GUILD_EVENT_PRESENCE_CHANGE",w.finish()};
    }
    // Other legacy events need their own semantic translation; never emit the
    // legacy generic event opcode with a modern or guessed body.
    return {};
}
}
