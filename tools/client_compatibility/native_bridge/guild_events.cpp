#include "guild_packets.hpp"

namespace bridge
{
Value native_guild_event(View body)
{
    Reader r(body);auto event=r.take<std::uint8_t>(),count=r.take<std::uint8_t>();
    if(count>3)throw std::runtime_error("native guild event exceeds parameter bound");
    Array parameters;
    for(unsigned i=0;i<count;++i){auto text=native_text(r);parameters.emplace_back(std::string(text.begin(),text.end()));}
    auto guid=r.take<std::uint64_t>();r.end();
    return Object{{"event",event},{"parameters",parameters},{"guid",guid}};
}
Reply guild_event_response(std::string const &name,View body,Array const &identities)
{
    if(name!="SMSG_GUILD_EVENT")return {};
    auto record=native_guild_event(body);auto event=integer(get(record,"event")),guid=integer(get(record,"guid"));
    auto const &parameters=get(record,"parameters").as_array();auto count=parameters.size();Writer w;
    auto text=[&](unsigned i,unsigned maximum)
    {
        if(i>=count || parameters[i].as_string().size()>maximum)throw std::runtime_error("invalid native guild event text");
        auto const &value=parameters[i].as_string();return Bytes(value.begin(),value.end());
    };
    auto player=[&](Bytes const &text)
    {
        std::string name(text.begin(),text.end());std::uint64_t found=0;
        for(auto const &row:identities)if(get(row,"name")==Value(name))
        {
            auto id=integer(get(row,"guid"));
            if(!id || id>0xffffffff || found)throw std::runtime_error("ambiguous guild event player identity");
            found=id;
        }
        if(!found)throw std::runtime_error("guild event player identity unavailable");
        return found;
    };
    if(event==1 || event==2)
    {
        if(count!=3 || guid)throw std::runtime_error("invalid native guild rank event");
        auto officer=player(text(0,63)),other=player(text(1,63));auto title=text(2,15);
        std::optional<unsigned> rank;
        for(auto const &row:identities)if(get(row,"rank_name")==Value(std::string(title.begin(),title.end())))
        {
            auto id=integer(get(row,"rank_id"));
            if(id>=10 || rank)throw std::runtime_error("ambiguous guild event rank identity");
            rank=id;
        }
        if(!rank)throw std::runtime_error("guild event rank identity unavailable");
        return Packet{"SMSG_GUILD_SEND_RANK_CHANGE",w.guid(officer,player_high()).guid(other,player_high())
            .pack("I",{*rank}).bits(event==1,1).finish()};
    }
    if(event==6)
    {
        if(count!=2 || guid)throw std::runtime_error("invalid native guild removal event");
        auto leaver=text(0,63),remover=text(1,63);
        return Packet{"SMSG_GUILD_EVENT_PLAYER_LEFT",w.bits(1,1).bits(leaver.size(),6).bits(remover.size(),6).flush()
            .guid(player(remover),player_high()).pack("I",{1}).raw(remover)
            .guid(player(leaver),player_high()).pack("I",{1}).raw(leaver).finish()};
    }
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
