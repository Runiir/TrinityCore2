#include "guild_packets.hpp"
#include <cstring>

namespace bridge
{
Value native_guild_roster(View body)
{
    Reader r(body);auto welcome=r.bits(11),count=r.bits(18);
    if(count>4096)throw std::runtime_error("native guild roster exceeds bound");
    struct Member
    {
        std::array<std::uint8_t,8> guid{};
        bool authenticated=false;
        unsigned note=0,officer=0,name=0;
    };
    std::vector<Member> members(count);
    for(auto &m:members)
    {
        m.guid[3]=r.bits(1);m.guid[4]=r.bits(1);m.authenticated=r.bits(1);r.bits(1);
        m.note=r.bits(8);m.officer=r.bits(8);m.guid[0]=r.bits(1);m.name=r.bits(7);
        for(auto i:{1,2,6,5,7})m.guid[i]=r.bits(1);
    }
    auto info=r.bits(12);r.align();Array result;
    for(auto &m:members)
    {
        auto byte=[&](unsigned i){if(m.guid[i])m.guid[i]=r.take<std::uint8_t>()^1;};
        Object row;row["class"]=r.take<std::uint8_t>();row["reputation"]=r.take<std::uint32_t>();
        byte(0);r.take<std::uint64_t>();row["rank"]=r.take<std::uint32_t>();
        row["achievements"]=r.take<std::uint32_t>();Array professions;
        for(unsigned i=0;i<2;++i)
        {
            auto step=r.take<std::uint32_t>(),rank=r.take<std::uint32_t>(),skill=r.take<std::uint32_t>();
            professions.push_back(Array{skill,rank,step});
        }
        row["professions"]=professions;byte(2);row["status"]=r.take<std::uint8_t>();
        row["area"]=r.take<std::uint32_t>();r.take<std::uint64_t>();byte(7);r.take<std::uint32_t>();
        auto note=r.raw(m.note);row["note"]=std::string(note.begin(),note.end());
        byte(3);row["level"]=r.take<std::uint8_t>();r.take<std::uint32_t>();byte(5);byte(4);
        row["gender"]=r.take<std::uint8_t>();byte(1);row["last_save"]=r.take<float>();
        auto text=[&](unsigned size){auto v=r.raw(size);return std::string(v.begin(),v.end());};
        row["officer_note"]=text(m.officer);byte(6);row["name"]=text(m.name);
        std::uint64_t guid=0;std::memcpy(&guid,m.guid.data(),8);
        if(!guid || guid>0xffffffff || m.name>63)throw std::runtime_error("invalid native guild roster member");
        row["guid"]=guid;row["authenticated"]=m.authenticated;result.push_back(row);
    }
    auto text=[&](unsigned size){auto v=r.raw(size);return std::string(v.begin(),v.end());};
    auto information=text(info),motd=text(welcome);
    auto accounts=r.take<std::uint32_t>();r.take<std::uint32_t>();auto date=r.take<std::uint32_t>(),flags=r.take<std::uint32_t>();r.end();
    if(info>2047)throw std::runtime_error("guild information exceeds modern bound");
    return Object{{"members",result},{"info",information},{"motd",motd},{"accounts",accounts},{"date",date},{"flags",flags}};
}
Array guild_member_guids(View body)
{
    auto roster=native_guild_roster(body);Array ids;
    for(auto const &member:get(roster,"members").as_array())ids.push_back(get(member,"guid"));
    return ids;
}
Reply guild_roster_response(View body,Array const &identities)
{
    auto roster=native_guild_roster(body);auto const &members=get(roster,"members").as_array();
    Writer w;w.pack("iIiI",{get(roster,"accounts"),get(roster,"date"),get(roster,"flags"),members.size()});
    auto motd=str(get(roster,"motd")),info=str(get(roster,"info"));w.bits(motd.size(),11).bits(info.size(),11).flush();
    for(auto const &member:members)
    {
        auto guid=integer(get(member,"guid"));unsigned race=0;
        for(auto const &identity:identities)if(integer(get(identity,"guid"))==guid)race=integer(get(identity,"race"));
        w.guid(guid,player_high()).pack("iiiif",{get(member,"rank"),get(member,"area"),get(member,"achievements"),get(member,"reputation"),get(member,"last_save")});
        for(auto const &profession:get(member,"professions").as_array())w.pack("iii",profession.as_array());
        w.pack("IBBBBQB",{1,get(member,"status"),get(member,"level"),get(member,"class"),get(member,"gender"),0,race});
        auto name=str(get(member,"name")),note=str(get(member,"note")),officer=str(get(member,"officer_note"));
        w.bits(name.size(),6).bits(note.size(),8).bits(officer.size(),8).bits(truth(get(member,"authenticated")),1).flush();
        w.pack("ffI",{0,0,0}).raw(name).raw(note).raw(officer);
    }
    return Packet{"SMSG_GUILD_ROSTER",w.raw(motd).raw(info).finish()};
}
}
