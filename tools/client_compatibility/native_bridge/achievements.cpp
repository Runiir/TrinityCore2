// Native AchievementMgr and pinned modern AchievementPackets wire contracts.
#include "protocol.hpp"
#include <array>

namespace bridge
{
namespace
{
std::uint64_t value(std::array<std::uint8_t,8> const &bytes)
{
    std::uint64_t result=0;for(unsigned i=0;i<8;++i)result|=static_cast<std::uint64_t>(bytes[i])<<(8*i);
    return result;
}
Writer &player(Writer &w,std::uint64_t guid)
{
    if(guid>0xffffffff)throw std::runtime_error("achievement owner is not a player");
    return w.guid(guid,guid ? player_high() : 0);
}
}
Reply Protocol::achievement_response(State const &owner,std::string const &name,View body)
{
    Reader r(body);Writer w;
    if(name=="SMSG_ALL_ACHIEVEMENT_DATA")
    {
        auto count=r.bits(21);
        if(count>20000)throw std::runtime_error("criteria count exceeds bound");
        struct Flags{std::array<std::uint8_t,8> guid{},quantity{};unsigned flags=0;};
        std::vector<Flags> flags(count);
        for(auto &f:flags)
        {
            f.guid[4]=r.bits(1);f.quantity[3]=r.bits(1);f.guid[5]=r.bits(1);f.quantity[0]=r.bits(1);
            f.quantity[6]=r.bits(1);f.guid[3]=r.bits(1);f.guid[0]=r.bits(1);f.quantity[4]=r.bits(1);
            f.guid[2]=r.bits(1);f.quantity[7]=r.bits(1);f.guid[7]=r.bits(1);f.flags=r.bits(2);
            f.guid[6]=r.bits(1);f.quantity[2]=r.bits(1);f.quantity[1]=r.bits(1);f.quantity[5]=r.bits(1);f.guid[1]=r.bits(1);
        }
        auto earned=r.bits(23);
        if(earned>5000)throw std::runtime_error("achievement count exceeds bound");
        Array progress;
        for(auto &f:flags)
        {
            auto byte=[&](std::array<std::uint8_t,8> &v,unsigned i){if(v[i])v[i]=r.take<std::uint8_t>()^1;};
            byte(f.guid,3);byte(f.quantity,5);byte(f.quantity,6);byte(f.guid,4);byte(f.guid,6);byte(f.quantity,2);
            auto create=r.take<std::uint32_t>();byte(f.guid,2);auto id=r.take<std::uint32_t>();byte(f.guid,5);
            for(auto i:{0,3,1,4})byte(f.quantity,i);
            byte(f.guid,0);byte(f.guid,7);byte(f.quantity,7);
            auto start=r.take<std::uint32_t>(), date=r.take<std::uint32_t>();byte(f.guid,1);
            progress.push_back(Array{id,value(f.quantity),value(f.guid),f.flags,date,start,create});
        }
        w.pack("II",{earned,count});
        for(unsigned i=0;i<earned;++i)
        {
            auto id=r.take<std::uint32_t>(), date=r.take<std::uint32_t>();
            w.pack("II",{id,date});player(w,owner.guid()).pack("II",{1,1});
        }
        for(auto const &row:progress)
        {
            auto const &v=row.as_array();w.pack("IQ",{v[0],v[1]});player(w,integer(v[2]));
            w.pack("5I",{0,v[3],v[4],v[5],v[6]}).bits(0,1).flush();
        }
        r.end();return Packet{name,w.finish()};
    }
    if(name=="SMSG_CRITERIA_UPDATE")
    {
        auto id=r.take<std::int32_t>();auto quantity=native_guid(r), guid=native_guid(r);
        auto flags=r.take<std::int32_t>();auto date=r.take<std::uint32_t>();
        auto start=r.take<std::uint32_t>(), create=r.take<std::uint32_t>();r.end();
        w.pack("IQ",{id,quantity});player(w,guid).pack("5I",{0,flags,date,start,create}).bits(0,1);
        return Packet{name,w.finish()};
    }
    if(name=="SMSG_ACHIEVEMENT_EARNED")
    {
        auto guid=native_guid(r);auto id=r.take<std::uint32_t>(), date=r.take<std::uint32_t>();
        auto hidden=r.take<std::uint32_t>();r.end();
        player(w,guid);player(w,guid).pack("4I",{id,date,1,1}).bits(hidden!=0,1);
        return Packet{name,w.finish()};
    }
    if(name=="SMSG_CRITERIA_DELETED" || name=="SMSG_ACHIEVEMENT_DELETED")
    {
        auto id=r.take<std::uint32_t>();r.end();w.put(id);
        if(name=="SMSG_ACHIEVEMENT_DELETED")w.put<std::uint32_t>(0);
        return Packet{name,w.finish()};
    }
    return {};
}
} // namespace bridge
