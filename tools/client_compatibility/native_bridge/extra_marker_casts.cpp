#include "protocol.hpp"

namespace bridge
{
void Protocol::marker_permission(State const &owner)
{
    if(!owner.created || !integer(owner.party_guid[0]))throw std::runtime_error("raid marker requires an active group");
    if((owner.party_flags&1) && owner.party_leader!=owner.guid() && !(owner.party_member_flags&1))
        throw std::runtime_error("raid marker requires leader or assistant permission");
}
Reply Protocol::extra_marker_go(State &owner) const
{
    auto const &cast=owner.casts.at(owner.cast_counter);auto const &location=get(cast,"extra_marker");
    if(location.is_null())return {};
    // The C++ compatibility endpoint owns the three marker annotations added
    // after 4.3.4. This completion is generated here, not attributed to native.
    Writer w;packed(w,owner.guid());packed(w,owner.guid());
    w.pack("BiIII",{owner.cast_counter,get(cast,"spell"),0,0,0}).pack("BBI",{0,0,64})
        .put<std::uint8_t>(0).pack("3f",get(location,"position").as_array()).put<std::uint8_t>(0);
    return cast_response(owner,"SMSG_SPELL_GO",w.finish());
}
}
