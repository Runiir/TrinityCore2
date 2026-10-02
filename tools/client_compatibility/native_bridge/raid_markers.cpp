#include "protocol.hpp"
#include <bit>
#include <cmath>

namespace bridge
{
void RaidMarkers::mask(unsigned value)
{
    if(value&~255u)throw std::runtime_error("unsupported raid marker mask");
    active=value;
    for(unsigned i=0;i<8;++i)if(!(active&(1u<<i)))locations[i]=nullptr;
}
void RaidMarkers::location(unsigned slot,Value const &value)
{
    if(slot>=8)throw std::runtime_error("unsupported raid marker slot");
    auto const &position=get(value,"position").as_array();
    if(position.size()!=3 || integer(get(value,"map"))>65535)throw std::runtime_error("invalid raid marker location");
    for(auto const &v:position)if(!std::isfinite(number(v)) || std::abs(number(v))>17066.667)
        throw std::runtime_error("invalid raid marker location");
    // The native core can publish the dynamic create before its marker mask.
    locations[slot]=value;
}
std::optional<Bytes> RaidMarkers::packet() const
{
    for(unsigned i=0;i<8;++i)if((active&(1u<<i)) && locations[i].is_null())return {};
    Writer w;w.put<std::uint8_t>(0).put<std::uint32_t>(active).bits(std::popcount(active),4).flush();
    for(unsigned i=0;i<8;++i)if(active&(1u<<i))
        w.guid().put<std::uint32_t>(integer(get(locations[i],"map"))).pack("3f",get(locations[i],"position").as_array());
    return w.finish();
}
std::vector<Packet> Protocol::marker_clear(View body)
{
    Reader r(body);auto id=r.take<std::uint8_t>();r.end();
    std::vector<Packet> packets;
    if(id==8)for(unsigned i=0;i<5;++i)packets.emplace_back("CMSG_CLEAR_RAID_MARKER",Bytes{static_cast<std::uint8_t>(i)});
    else if(id<5)packets.emplace_back("CMSG_CLEAR_RAID_MARKER",Bytes{id});
    else if(id>8)throw std::runtime_error("invalid raid marker slot");
    return packets;
}
Array Protocol::marker_objects(State const &owner,View body) const
{
    Array result;
    for(auto const &record:native_records(body))
    {
        if(integer(get(record,"kind"))!=6 || integer(get(record,"guid"))>>48!=0xf100)continue;
        auto spell=field(record,"DYNAMICOBJECT_SPELLID");
        if(spell<84996 || spell>85000 || field(record,"DYNAMICOBJECT_BYTES")>>28!=3)continue;
        auto caster=static_cast<std::uint64_t>(field(record,"DYNAMICOBJECT_CASTER")) |
            (static_cast<std::uint64_t>(field(record,"DYNAMICOBJECT_CASTER",1))<<32);
        if(!owner.party_members.contains(caster))continue;
        auto position=get(get(record,"movement"),"position").as_array();position.resize(3);
        result.push_back(Object{{"slot",spell-84996},{"map",get(record,"map")},{"position",position}});
    }
    return result;
}
}
