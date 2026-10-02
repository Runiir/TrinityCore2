#include "guild_packets.hpp"

namespace bridge
{
Reply guild_note_request(std::string const &name,View body)
{
    if(name!="CMSG_GUILD_SET_MEMBER_NOTE")return {};
    Reader r(body);auto identity=r.guid();auto guid=integer(identity[0]);
    if(!guid || guid>0xffffffff || integer(identity[1])!=player_high())throw std::runtime_error("invalid guild note identity");
    auto size=r.bits(8),is_public=r.bits(1);auto note=r.raw(size);r.end();
    std::array<std::uint8_t,8> octets{};std::memcpy(octets.data(),&guid,8);Writer w;
    for(auto i:{1,4,5,3,0,7})w.bits(octets[i]!=0,1);
    // This backend's handler calls HandleSetMemberNote's `officer` argument
    // with the wire `ispublic` bit unchanged. Adapt to the implemented native
    // semantics so public and officer notes land in the correct DB column.
    w.bits(!is_public,1).bits(octets[6]!=0,1).bits(size,8).bits(octets[2]!=0,1).flush();
    auto byte=[&](unsigned i){if(octets[i])w.put<std::uint8_t>(octets[i]^1);};
    for(auto i:{4,5,0,3,1,6,7})byte(i);
    w.raw(note);byte(2);return Packet{"CMSG_GUILD_SET_NOTE",w.finish()};
}
Reply guild_note_response(std::string const &name,View body)
{
    if(name!="SMSG_GUILD_MEMBER_UPDATE_NOTE")return {};
    Reader r(body);std::array<std::uint8_t,8> octets{};
    for(auto i:{7,2,3})octets[i]=r.bits(1);
    auto size=r.bits(8);
    for(auto i:{5,0,6,4})octets[i]=r.bits(1);
    auto is_public=r.bits(1);octets[1]=r.bits(1);r.align();
    auto byte=[&](unsigned i){if(octets[i])octets[i]=r.take<std::uint8_t>()^1;};
    for(auto i:{3,0,2,5})byte(i);
    auto note=r.raw(size);for(auto i:{7,6,1,4})byte(i);r.end();
    std::uint64_t guid=0;std::memcpy(&guid,octets.data(),8);
    if(!guid || guid>0xffffffff)throw std::runtime_error("invalid native guild note identity");
    // The same native implementation broadcasts its officer flag in this bit.
    return Packet{name,Writer().guid(guid,player_high()).bits(size,8).bits(!is_public,1).raw(note).finish()};
}
}
