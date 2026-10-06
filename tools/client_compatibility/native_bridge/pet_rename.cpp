#include "pet_packets.hpp"
#include <algorithm>

namespace bridge
{
PetActionTranslation translate_pet_rename(Protocol const &p,State &owner,View body)
{
    try
    {
        // UI143's ordinary Yes confirmation sends PackedGuid128, int32 pet
        // number, eight-bit name length, no-declension bit, then the name.
        Reader r(body);auto submitted=r.guid();auto number=r.take<std::int32_t>();
        auto length=r.bits(8),declined=r.bits(1),padding=r.bits(7);
        if(number<=0 || length<2 || length>12 || declined || padding)
            throw std::runtime_error("unsupported pet Rename shape");
        auto name=r.raw(length);r.end();
        if(!std::all_of(name.begin(),name.end(),[](unsigned char c)
            {return (c>='A' && c<='Z') || (c>='a' && c<='z');}))
            throw std::runtime_error("unsupported pet Rename alphabet");
        auto guid=owned_unit(owner,submitted);
        if(!pet_rename_authority(p,owner,guid,number))
            throw std::runtime_error("pet Rename without current native Hunter permission and control authority");
        // The native core checks validity/reserved names and performs the
        // one-time persistence and permission removal. Never replace the pet.
        return {Packet{"CMSG_PET_RENAME",Writer().put(guid).raw(name).zeros(2).finish()},{}};
    }
    catch(std::exception const &e) {return {{},e.what()};}
}
}
