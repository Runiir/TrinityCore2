// Native NPCHandler/PetHandler owns every mutation; modern cache follows its reply.
#include "stables.hpp"
#include <array>

namespace bridge
{
namespace
{
std::uint64_t authority(Protocol const &p,State const &owner,Array const &identity)
{
    // Reuse the read's current native Hunter, map, visibility and NPC flag guards.
    stable_request(p,owner,"CMSG_REQUEST_STABLED_PETS",Writer().guid(identity).finish());
    if(owner.stable_slots<1 || owner.stable_slots>16 || identity!=get(owner.pet_stable,"StableMaster"))
        throw std::runtime_error("stable slot authority differs from native owned catalog");
    return owned_unit(owner,identity);
}
unsigned slot_pet(Value const &stable,unsigned slot)
{
    unsigned found=0;
    for(auto const &pet:get(stable,"Pets").as_array())
        if(integer(get(pet,"PetSlot"))==slot)
        {
            if(found)throw std::runtime_error("duplicate native stable slot");
            found=integer(get(pet,"PetNumber"));
        }
    return found;
}
}
Reply stable_slot_request(Protocol const &p,State &owner,std::string const &name,View body)
{
    if(name!="CMSG_SET_PET_SLOT")return {};
    // Pinned 4.4.2 PetHandler: uint32 pet number, uint8 destination, PackedGuid128.
    Reader r(body);auto number=r.take<std::uint32_t>();auto destination=r.take<std::uint8_t>();
    auto identity=r.guid();r.end();auto guid=authority(p,owner,identity);
    if(!truth(get(owner.pet_stable,"interaction_open")) || get(owner.pet_stable,"pending_slot").is_object())
        throw std::runtime_error("stable slot requires open interaction without another pending mutation");
    if(!number || destination>4+owner.stable_slots)
        throw std::runtime_error("stable slot exceeds actual native capacity");
    std::optional<unsigned> source;
    for(auto const &pet:get(owner.pet_stable,"Pets").as_array())
        if(integer(get(pet,"PetNumber"))==number)source=integer(get(pet,"PetSlot"));
    if(!source || *source==destination)
        throw std::runtime_error("stable slot requires an owned catalog pet and a different destination");
    auto swap=slot_pet(owner.pet_stable,destination);
    // Native HandleSetPetSlot uses this legacy mask and XOR byte order.
    std::array<std::uint8_t,8> octets{};std::memcpy(octets.data(),&guid,8);
    Writer w;w.put(number).put(destination);
    for(auto i:{3,2,0,7,5,6,1,4})w.bits(octets[i]!=0,1);
    for(auto i:{5,3,1,7,4,0,6,2})if(octets[i])w.put<std::uint8_t>(octets[i]^1);
    auto packet=Packet{name,w.finish()};
    owner.pet_stable.as_object()["pending_slot"]=Object{{"number",number},{"source",*source},
        {"destination",destination},{"swap",swap},{"updated",false}};
    return packet;
}
Reply stable_slot_response(Protocol const &p,State &owner,std::string const &name,View body)
{
    if(name!="SMSG_PET_SLOT_UPDATED" && name!="SMSG_STABLE_RESULT")return {};
    auto const &pending=get(owner.pet_stable,"pending_slot");
    if(!pending.is_object())throw std::runtime_error("unsolicited native stable slot response");
    authority(p,owner,get(owner.pet_stable,"StableMaster").as_array());
    Reader r(body);
    if(name=="SMSG_STABLE_RESULT")
    {
        auto code=r.take<std::uint8_t>();r.end();bool success=code==8 || code==9;
        if(!(success || code==1 || code==3 || code==11 || code==12) ||
            success!=truth(get(pending,"updated")))
            throw std::runtime_error("native stable result differs from pending slot outcome");
        owner.pet_stable.as_object()["pending_slot"]=nullptr;
        return Packet{"SMSG_PET_STABLE_RESULT",Writer().put(code).finish()};
    }
    auto number=r.take<std::uint32_t>(),destination=r.take<std::uint32_t>();
    auto swap=r.take<std::uint32_t>(),source=r.take<std::uint32_t>();r.end();
    if(truth(get(pending,"updated")) || number!=integer(get(pending,"number")) ||
        destination!=integer(get(pending,"destination")) || swap!=integer(get(pending,"swap")) ||
        source!=integer(get(pending,"source")) || slot_pet(owner.pet_stable,source)!=number ||
        slot_pet(owner.pet_stable,destination)!=swap)
        throw std::runtime_error("native stable slot update differs from exact pending owned mutation");
    auto stable=owner.pet_stable;
    for(auto &pet:stable.as_object()["Pets"].as_array())
    {
        auto id=integer(get(pet,"PetNumber"));
        if(id!=number && (!swap || id!=swap))continue;
        unsigned slot=id==number ? destination : source;
        pet.as_object()["PetSlot"]=slot;pet.as_object()["PetFlags"]=slot>4 ? 3 : 1;
    }
    stable.as_object()["pending_slot"].as_object()["updated"]=true;
    auto packet=Packet{"SMSG_UPDATE_OBJECT",stable_block(owner,stable,owner.stable_slots)};
    owner.pet_stable=stable;owner.self_snapshot.as_object()["pet_stable"]=stable;
    return packet;
}
}
