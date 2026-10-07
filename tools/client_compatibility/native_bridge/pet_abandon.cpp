// Pinned WPP 4.4.0 PetHandler: PackedGuid128; native PetHandler: uint64 GUID.
#include "pet_packets.hpp"
#include <algorithm>

namespace bridge
{
PetActionTranslation translate_pet_abandon(Protocol const &p,State &owner,View body)
{
    try
    {
        Reader r(body);auto submitted=r.guid();r.end();
        auto guid=owned_unit(owner,submitted);
        auto canonical=Writer().guid(Protocol::modern_guid(guid,owner.map())).finish();
        if(body.size()!=canonical.size() || !std::equal(body.begin(),body.end(),canonical.begin()) ||
           !pet_abandon_authority(p,owner,guid))
            throw std::runtime_error("pet Abandon without current owned Hunter permission and control authority");
        return {Packet{"CMSG_PET_ABANDON",Writer().put(guid).finish()},{}};
    }
    catch(std::exception const &error) {return {{},error.what()};}
}
}
