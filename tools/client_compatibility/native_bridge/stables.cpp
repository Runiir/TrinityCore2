// Native Hunter catalog to pinned 60895 owner-only optional StableInfo fields.
#include "stables.hpp"
#include <unordered_set>

namespace bridge
{
namespace
{
bool hunter(Protocol const &protocol,State const &owner)
{
    return owner.guid() && (owner.self_snapshot.is_null() ? integer(get(owner.character,"class")) :
        (protocol.field(owner.self_snapshot,"UNIT_FIELD_BYTES_0")>>8)&255)==3;
}
std::uint64_t master(Protocol const &protocol,State const &owner,Array const &identity)
{
    auto guid=owned_unit(owner,identity);auto const &unit=owner.visible_units.at(guid);
    if(integer(get(unit,"kind"))!=3 || integer(get(unit,"map"))!=owner.map() ||
        !(protocol.field(unit,"UNIT_NPC_FLAGS")&4194304u))
        throw std::runtime_error("stable read requires a visible native stable master");
    return guid;
}
Bytes stable_block(State const &owner,Value const &stable,unsigned slots)
{
    // ActivePlayer group102, optional129 and scalar130. StableInfo and each
    // StablePetInfo use complete nested masks, replacing the native catalog.
    Writer data;data.pack("BBBI",{1,0,3,1u<<7}).put<std::uint32_t>(24).bits(0,14)
        .bits(1u<<6,32).bits(6,32).flush().put<std::uint8_t>(slots).bits(1,1);
    auto const &pets=get(stable,"Pets").as_array();data.bits(7,3).bits(pets.size(),32);
    for(unsigned i=0;i<pets.size();++i)data.bits(1,1);
    data.flush();
    for(auto const &pet:pets)
    {
        data.bits(511,9).flush().pack("5I",{get(pet,"PetSlot"),get(pet,"PetNumber"),get(pet,"CreatureID"),
            get(pet,"DisplayID"),get(pet,"ExperienceLevel")})
            .pack("BB",{get(pet,"PetFlags"),0}).bits(str(get(pet,"Name")).size(),8)
            .raw(str(get(pet,"Name"))).flush();
    }
    data.guid(get(stable,"StableMaster"));auto fields=data.finish();
    auto block=Writer().put<std::uint8_t>(0).guid(owner.guid(),player_high())
        .put<std::uint32_t>(fields.size()).raw(fields).finish();
    return object_packet(owner.map(),{block},{});
}
}
Value native_stable_list(View body)
{
    Reader r(body);auto guid=r.take<std::uint64_t>();auto count=r.take<std::uint8_t>(),last=r.take<std::uint8_t>();
    if(last<5 || last>20 || count>last+1)throw std::runtime_error("native stable capacity exceeds supported slots");
    Array pets;std::unordered_set<unsigned> numbers,slots;
    for(unsigned i=0;i<count;++i)
    {
        auto slot=r.take<std::int32_t>();auto number=r.take<std::uint32_t>(),entry=r.take<std::uint32_t>(),level=r.take<std::uint32_t>();
        auto name=native_text(r);auto flags=r.take<std::uint8_t>();
        if(slot<0 || slot>last || !number || !entry || !level || level>85 || name.empty() || name.size()>255 ||
            flags!=(slot>4?3:1) || !numbers.insert(number).second || !slots.insert(slot).second)
            throw std::runtime_error("invalid native stable pet catalog");
        pets.push_back(Object{{"PetSlot",slot},{"PetNumber",number},{"CreatureID",entry},
            {"ExperienceLevel",level},{"Name",std::string(name.begin(),name.end())},{"PetFlags",flags},{"Field_96",0}});
    }
    r.end();return Object{{"native_master",guid},{"native_last_slot",last},{"Pets",pets}};
}
Reply stable_request(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
    if(name!="CMSG_REQUEST_STABLED_PETS")return {};
    if(!owner.created || !hunter(protocol,owner))throw std::runtime_error("stable read requires an active native Hunter");
    Reader r(body);auto guid=master(protocol,owner,r.guid());r.end();
    return Packet{"MSG_LIST_STABLED_PETS",Writer().put(guid).finish()};
}
Reply stable_response(Protocol const &protocol,State &owner,std::string const &name,View body,Array const &models)
{
    if(name!="MSG_LIST_STABLED_PETS")return {};
    if(!hunter(protocol,owner))return {};
    auto catalog=native_stable_list(body);auto guid=integer(get(catalog,"native_master"));
    auto identity=Array{0,0};
    if(guid)
    {
        identity=Protocol::modern_guid(guid,owner.map());
        if(master(protocol,owner,identity)!=guid)throw std::runtime_error("native stable master identity differs");
    }
    auto pets=get(catalog,"Pets").as_array();
    for(auto &pet:pets)
    {
        Value display;
        for(auto const &row:models)
            if(integer(get(row,"id"))==integer(get(pet,"PetNumber")))
            {
                if(!display.is_null() || integer(get(row,"owner"))!=owner.guid() ||
                    get(row,"entry")!=get(pet,"CreatureID") || integer(get(row,"PetType"))!=1 ||
                    !integer(get(row,"modelid")) || integer(get(row,"modelid"))>0xffffffffu)
                    throw std::runtime_error("native stable pet model binding differs");
                display=get(row,"modelid");
            }
        if(display.is_null())throw std::runtime_error("owned native stable pet model is absent");
        pet.as_object()["DisplayID"]=display;
    }
    Value stable=Object{{"Pets",pets},{"StableMaster",identity}};
    auto slots=integer(get(catalog,"native_last_slot"))-4;
    owner.pet_stable=stable;owner.stable_slots=slots;
    if(!owner.created)return {};
    owner.self_snapshot.as_object()["pet_stable"]=stable;
    owner.self_snapshot.as_object()["stable_slots"]=slots;
    return Packet{"SMSG_UPDATE_OBJECT",stable_block(owner,stable,slots)};
}
}
