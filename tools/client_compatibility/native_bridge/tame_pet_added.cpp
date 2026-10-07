// UI160's actual native PetAdded has no 60895 opcode equivalent. Deliver
// the new owned pet through the already verified ActivePlayer StableInfo.
#include "tame_pet_added.hpp"
#include "stables.hpp"

namespace bridge
{
namespace
{
std::uint64_t guid(Protocol const &p,Value const &unit,char const *name)
{
    return p.field(unit,name) | (static_cast<std::uint64_t>(p.field(unit,name,1))<<32);
}
bool hunter(Protocol const &p,State const &owner)
{
    return owner.created && !owner.character.is_null() && !owner.self_snapshot.is_null() &&
        integer(get(owner.character,"class"))==3 && integer(get(owner.self_snapshot,"guid"))==owner.guid() &&
        ((p.field(owner.self_snapshot,"UNIT_FIELD_BYTES_0")>>8)&255)==3;
}
Value *pending(State &owner)
{
    Value *result=nullptr;
    for(auto &[id,cast]:owner.casts)
        if(signed_integer(get(cast,"spell"))==1515 && truth(get(cast,"tame_pet_added_pending")))
        {
            if(result)throw std::runtime_error("ambiguous native Tame pet outcome");
            result=&cast;
        }
    return result;
}
}
Reply tame_pet_added_ready(Protocol const &p,State &owner)
{
    if(!hunter(p,owner))return {};
    auto cast=pending(owner);if(!cast)return {};
    auto const &added=get(*cast,"native_tame_added");if(!added.is_object())return {};
    auto number=integer(get(added,"PetNumber")),entry=integer(get(added,"CreatureID"));
    Value const *pet=nullptr;std::uint64_t identity=0;
    for(auto const &[id,unit]:owner.visible_units)
        if(id>>52==0xf14 && p.field(unit,"UNIT_FIELD_PETNUMBER")==number)
        {
            if(pet)throw std::runtime_error("ambiguous native newly tamed pet number");
            pet=&unit;identity=id;
        }
    if(!pet || integer(get(*pet,"kind"))!=3 || integer(get(*pet,"map"))!=owner.map() ||
        p.field(*pet,"OBJECT_FIELD_ENTRY")!=entry || guid(p,*pet,"UNIT_FIELD_CREATEDBY")!=owner.guid() ||
        guid(p,*pet,"UNIT_FIELD_SUMMONEDBY")!=owner.guid() ||
        guid(p,owner.self_snapshot,"UNIT_FIELD_SUMMON")!=identity || !p.field(*pet,"UNIT_FIELD_HEALTH") ||
        !p.field(owner.self_snapshot,"UNIT_FIELD_HEALTH"))return {};
    auto display=p.field(*pet,"UNIT_FIELD_DISPLAYID"),level=p.field(*pet,"UNIT_FIELD_LEVEL");
    if(!display || !level || level>85 || level<integer(get(added,"native_initial_level")))return {};
    if(!owner.pet_stable.is_object() || !get(owner.pet_stable,"Pets").is_array())return {};
    // Do not invent a catalog or open an NPC interaction. Preserve the actual
    // login/native stable catalog and add only the newly owned native outcome.
    auto stable=owner.pet_stable;auto &pets=stable.as_object()["Pets"].as_array();
    auto slot=integer(get(added,"PetSlot"));
    if(truth(get(stable,"interaction_open")) || get(stable,"StableMaster")!=Array{0,0} || !owner.stable_slots)
        return {};
    // Once complete authority exists, a conflicting catalog is a closed
    // rejection rather than a repeated error on every later object update.
    cast->as_object()["tame_pet_added_pending"]=false;
    for(auto const &row:pets)
        if(integer(get(row,"PetNumber"))==number || integer(get(row,"PetSlot"))==slot)
            throw std::runtime_error("native newly tamed pet conflicts with existing stable catalog");
    pets.push_back(Object{{"PetSlot",slot},{"PetNumber",number},{"CreatureID",entry},{"DisplayID",display},
        {"ExperienceLevel",level},{"PetFlags",get(added,"PetFlags")},{"Name",get(added,"Name")},{"Field_96",0}});
    // Native Added reports the original wild level1. UI160's later native
    // unit/owner links establish the resulting pet's canonical level10.
    auto packet=stable_block(owner,stable,owner.stable_slots);
    owner.pet_stable=stable;owner.self_snapshot.as_object()["pet_stable"]=stable;
    cast->as_object()["native_tame_added"]=nullptr;
    return Packet{"SMSG_UPDATE_OBJECT",std::move(packet)};
}
Reply tame_pet_added_response(Protocol const &p,State &owner,std::string const &name,View body)
{
    if(name!="SMSG_PET_ADDED")return {};
    Reader r(body);auto level=r.take<std::int32_t>(),slot=r.take<std::int32_t>();
    auto flags=r.take<std::uint8_t>();auto entry=r.take<std::int32_t>(),number=r.take<std::int32_t>();
    auto length=r.bits(8);auto bytes=r.raw(length);auto terminator=r.take<std::uint8_t>();r.end();
    std::string text(reinterpret_cast<char const *>(bytes.data()),bytes.size());
    if(level<1 || level>85 || slot<0 || slot>4 || flags!=1 || entry<=0 || number<=0 ||
        text.empty() || text.find('\0')!=std::string::npos || terminator)
        throw std::runtime_error("invalid native newly tamed pet record");
    if(!hunter(p,owner))return {};
    auto cast=pending(owner);if(!cast)return {};
    if(get(*cast,"native_tame_added").is_object())throw std::runtime_error("duplicate pending native Tame pet outcome");
    cast->as_object()["native_tame_added"]=Object{{"native_initial_level",level},{"PetSlot",slot},
        {"PetNumber",number},{"CreatureID",entry},{"PetFlags",flags},{"Name",text}};
    return tame_pet_added_ready(p,owner);
}
}
