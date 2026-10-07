#include "pet_packets.hpp"
#include <algorithm>
#include <cmath>
#include <unordered_set>

namespace bridge
{
struct PetState
{
    struct NameQuery {std::uint64_t guid; unsigned map;};
    std::unordered_map<unsigned, std::deque<NameQuery>> names;
    unsigned name_count=0;
    std::uint64_t pending_guid=0;
    std::uint64_t controlled_guid=0; // Granted by a released native control catalog.
    Bytes pending_spells;
    std::array<std::uint32_t,10> pending_buttons{},controlled_buttons{};
    std::unordered_set<unsigned> pending_autocast,controlled_autocast;
};
namespace
{
PetState &pet_state(State &owner)
{
    if(!owner.pet_state)owner.pet_state=std::make_shared<PetState>();
    return *owner.pet_state;
}
std::uint64_t field_guid(Protocol const &p, Value const &s, char const *name)
{
    return static_cast<std::uint64_t>(p.field(s,name)) |
        (static_cast<std::uint64_t>(p.field(s,name,1))<<32);
}
std::uint32_t modern_pet_action(std::uint32_t native)
{
    auto action=native&0x00ffffffu;
    if(action>0x007fffffu)throw std::runtime_error("native pet action exceeds modern value width");
    unsigned type=native>>24;
    // Native ActiveStates are eight bits; the pinned Cata ReadPetAction uses
    // nine bits above the23-bit value. Castable/autocast flags also move.
    switch(type)
    {
        case 0:case 1:case 6:case 7:break;
        case 0x81:type=0x101;break;
        case 0xc1:type=0x181;break;
        default:throw std::runtime_error("unsupported native pet action type");
    }
    return (type<<23)|action;
}
Bytes spell_message(View body, unsigned map, std::uint64_t &guid, PetState &state)
{
    Reader r(body);guid=r.take<std::uint64_t>();
    Writer w;w.guid(Protocol::modern_guid(guid,map));
    if(!guid)
    {
        r.end();return w.zeros(2+2+4+3+40+12).finish();
    }
    if(guid>>52!=0xf14)throw std::runtime_error("unsupported non-pet spell catalog");
    auto family=r.take<std::uint16_t>();auto duration=r.take<std::uint32_t>();
    auto react=r.take<std::uint8_t>(),command=r.take<std::uint8_t>();
    auto flags=r.take<std::uint16_t>();
    if(react>3 || command>4 || flags>255)throw std::runtime_error("unsupported native pet mode");
    auto buttons=r.unpack("10I");
    auto count=r.take<std::uint8_t>();auto actions=r.unpack(std::string(count,'I'));
    for(unsigned i=0;i<buttons.size();++i)state.pending_buttons[i]=static_cast<std::uint32_t>(integer(buttons[i]));
    for(auto const &action:actions)
    {
        auto word=static_cast<std::uint32_t>(integer(action));auto type=word>>24;
        if(type==0x81 || type==0xc1)state.pending_autocast.insert(word&0x00ffffffu);
    }
    for(auto &button:buttons)button=modern_pet_action(static_cast<std::uint32_t>(integer(button)));
    for(auto &action:actions)action=modern_pet_action(static_cast<std::uint32_t>(integer(action)));
    auto cooldown_count=r.take<std::uint8_t>();
    w.pack("HHIBBB",{family,0,duration,command,flags,react}).pack("10I",buttons)
        .pack("III",{count,cooldown_count,0}).pack(std::string(count,'I'),actions);
    for(unsigned i=0;i<cooldown_count;++i)
    {
        auto spell=r.take<std::int32_t>();auto category=r.take<std::uint16_t>();
        auto spell_duration=r.take<std::int32_t>(),category_duration=r.take<std::int32_t>();
        w.pack("iiifH",{spell,spell_duration,category_duration,1.0,category});
    }
    r.end();return w.finish();
}
}
Reply pet_ready(Protocol const &p, State &owner)
{
    if(!owner.pet_state || owner.pet_state->pending_spells.empty() || !owner.created)return {};
    auto &s=*owner.pet_state;auto found=owner.visible_units.find(s.pending_guid);
    if(found==owner.visible_units.end())return {};
    auto const &unit=found->second;
    // Creation and both native owner/summon links must first agree before
    // the native control catalog becomes visible and grants command authority.
    if(integer(get(unit,"kind"))!=3 || s.pending_guid>>52!=0xf14 ||
       field_guid(p,unit,"UNIT_FIELD_SUMMONEDBY")!=owner.guid() ||
       !p.field(unit,"UNIT_FIELD_PETNUMBER") || owner.self_snapshot.is_null() ||
       field_guid(p,owner.self_snapshot,"UNIT_FIELD_SUMMON")!=s.pending_guid)return {};
    Bytes message;message.swap(s.pending_spells);s.controlled_guid=s.pending_guid;s.pending_guid=0;
    s.controlled_buttons=s.pending_buttons;s.controlled_autocast.swap(s.pending_autocast);
    return Packet{"SMSG_PET_SPELLS_MESSAGE",std::move(message)};
}
Reply pet_request(Protocol const &p, State &owner, std::string const &name, View body)
{
    if(name!="CMSG_REQUEST_PET_INFO" && name!="CMSG_QUERY_PET_NAME" && name!="CMSG_PET_ACTION" &&
       name!="CMSG_PET_SET_ACTION")return {};
    if(!owner.created || owner.character.is_null())throw std::runtime_error("pet read without owned character");
    if(name=="CMSG_REQUEST_PET_INFO")
    {
        Reader(body).end();return Packet{name,{}};
    }
    Reader r(body);auto guid=owned_unit(owner,r.guid());
    auto const &unit=owner.visible_units.at(guid);
    auto number=p.field(unit,"UNIT_FIELD_PETNUMBER");
    if(name=="CMSG_PET_SET_ACTION")
    {
        auto slot=r.take<std::uint32_t>(),word=r.take<std::uint32_t>();
        auto tail=r.take<std::uint8_t>();r.end();auto spell=word&0x007fffffu,type=word>>23;
        // Only the four remotely reviewed UI130 autocast forms. The final
        // byte is held to captured zero; bar drag/removal is not admitted.
        if(tail || (type!=0x101 && type!=0x181) ||
           !((slot==3 && spell==3110) || (slot==4 && spell==6307)))
            throw std::runtime_error("unsupported pet autocast shape");
        if(!owner.pet_state || owner.pet_state->controlled_guid!=guid ||
           integer(get(unit,"kind"))!=3 || guid>>52!=0xf14 || !number ||
           field_guid(p,unit,"UNIT_FIELD_SUMMONEDBY")!=owner.guid() || owner.self_snapshot.is_null() ||
           field_guid(p,owner.self_snapshot,"UNIT_FIELD_SUMMON")!=guid)
            throw std::runtime_error("pet autocast without current native control authority");
        auto const &s=*owner.pet_state;auto native=s.controlled_buttons[slot],native_type=native>>24;
        if((native&0x00ffffffu)!=spell || (native_type!=0x81 && native_type!=0xc1) ||
           !s.controlled_autocast.contains(spell))
            throw std::runtime_error("pet autocast without current native spell and slot authority");
        auto native_word=((type==0x181?0xc1u:0x81u)<<24)|spell;
        return Packet{name,Writer().pack("QII",{guid,slot,native_word}).finish()};
    }
    if(name=="CMSG_PET_ACTION")
    {
        auto command=r.take<std::uint32_t>();auto target=r.guid();auto position=r.unpack("3f");r.end();
        // Captured stock commands, reactions, UI131 idle Blood Pact, UI135
        // Move To and UI137 selected-victim Attack. Preserve submitted GUIDs.
        bool command_action=command==0x03800000u || command==0x03800001u || command==0x03800003u;
        bool react_action=command==0x03000000u || command==0x03000001u || command==0x03000003u;
        bool blood_pact=command==0xc08018a3u;
        bool move_to=command==0x03800004u;
        bool attack=command==0x03800002u;
        bool nonzero=std::any_of(position.begin(),position.end(),[](Value const &v){return bridge::number(v)!=0;});
        bool invalid_position=std::any_of(position.begin(),position.end(),[](Value const &v)
        {auto n=bridge::number(v);return !std::isfinite(n) || std::abs(n)>17067;});
        if((!command_action && !react_action && !blood_pact && !move_to && !attack) ||
           (attack ? target==Array{0,0} : target!=Array{0,0}) ||
           invalid_position || (move_to ? !nonzero : nonzero))
            throw std::runtime_error("unsupported pet action shape");
        if(!owner.pet_state || owner.pet_state->controlled_guid!=guid ||
           integer(get(unit,"kind"))!=3 || guid>>52!=0xf14 || !number ||
           field_guid(p,unit,"UNIT_FIELD_SUMMONEDBY")!=owner.guid() || owner.self_snapshot.is_null() ||
           field_guid(p,owner.self_snapshot,"UNIT_FIELD_SUMMON")!=guid)
            throw std::runtime_error("pet action without current native control authority");
        if(blood_pact && (owner.pet_state->controlled_buttons[4]!=0xc10018a3u ||
                         !owner.pet_state->controlled_autocast.contains(6307)))
            throw std::runtime_error("pet spell without current enabled native spell and slot authority");
        if(move_to && (owner.pet_state->controlled_buttons[2]!=0x07000004u ||
                      !p.field(unit,"UNIT_FIELD_HEALTH") ||
                      !p.field(owner.self_snapshot,"UNIT_FIELD_HEALTH") ||
                      integer(get(unit,"map"))!=owner.map()))
            throw std::runtime_error("pet Move To without current live native command and map authority");
        std::uint64_t victim=0;
        if(attack)
        {
            victim=owned_unit(owner,target);auto const &selected=owner.visible_units.at(victim);
            if(owner.pet_state->controlled_buttons[0]!=0x07000002u ||
               !p.field(unit,"UNIT_FIELD_HEALTH") || !p.field(owner.self_snapshot,"UNIT_FIELD_HEALTH") ||
               integer(get(unit,"map"))!=owner.map() || victim>>52!=0xf13 ||
               integer(get(selected,"kind"))!=3 || !p.field(selected,"UNIT_FIELD_HEALTH") ||
               integer(get(selected,"map"))!=owner.map() ||
               field_guid(p,owner.self_snapshot,"UNIT_FIELD_TARGET")!=victim)
                throw std::runtime_error("pet Attack without current live command and selected native victim authority");
            // The core remains authoritative for faction, pacify and attack
            // validity. This bridge does not choose or replace the victim.
        }
        auto native_command=blood_pact?0xc10018a3u:
            (react_action?0x06000000u:0x07000000u) | (command&0x007fffffu);
        return Packet{name,Writer().pack("QIQfff",{guid,native_command,victim,position[0],position[1],position[2]}).finish()};
    }
    r.end();
    if(guid>>52!=0xf14 || !number)throw std::runtime_error("name query requires a visible numbered pet");
    for(auto const &[other,record]:owner.visible_units)
        if(other!=guid && other>>52==0xf14 && p.field(record,"UNIT_FIELD_PETNUMBER")==number)
            throw std::runtime_error("ambiguous visible pet number");
    auto &s=pet_state(owner);
    if(s.name_count>=64)throw std::runtime_error("pet name queries exceed bound");
    s.names[number].push_back({guid,static_cast<unsigned>(integer(get(unit,"map")))});++s.name_count;
    return Packet{"CMSG_PET_NAME_QUERY",Writer().pack("IQ",{number,guid}).finish()};
}
Reply pet_aura_cancel(Protocol const &p, State &owner, View body)
{
    Reader r(body);auto spell=r.take<std::uint32_t>();
    if(spell!=6307)return {};
    Value const *aura=nullptr;
    for(auto const &[slot,entry]:owner.visible_auras)
        if(integer(get(entry,"spell"))==spell)
        {
            if(aura)throw std::runtime_error("ambiguous visible Blood Pact aura");
            aura=&entry;
        }
    if(!aura)return {};
    auto guid=integer(get(*aura,"caster"));
    if(guid==owner.guid())return {};
    auto caster=r.guid();r.end();
    // UI133 stock owner-buff cancellation submits the player GUID. Resolve
    // its native area-aura owner only through current pet/control authority.
    auto canonical=Writer().put(spell).guid(owner.guid(),player_high()).finish();
    if(caster!=Array{owner.guid(),player_high()} ||
       body.size()!=canonical.size() || !std::equal(body.begin(),body.end(),canonical.begin()))
        throw std::runtime_error("unsupported pet-owned aura cancellation shape");
    auto found=owner.visible_units.find(guid);
    if(!owner.created || owner.character.is_null() || !owner.pet_state ||
       owner.pet_state->controlled_guid!=guid || found==owner.visible_units.end() ||
       integer(get(found->second,"kind"))!=3 || guid>>52!=0xf14 ||
       !p.field(found->second,"UNIT_FIELD_PETNUMBER") ||
       !p.field(found->second,"UNIT_FIELD_HEALTH") ||
       field_guid(p,found->second,"UNIT_FIELD_SUMMONEDBY")!=owner.guid() ||
       owner.self_snapshot.is_null() || field_guid(p,owner.self_snapshot,"UNIT_FIELD_SUMMON")!=guid ||
       !(integer(get(*aura,"flags"))&16) ||
       owner.pet_state->controlled_buttons[4]!=0xc10018a3u ||
       !owner.pet_state->controlled_autocast.contains(spell))
        throw std::runtime_error("pet-owned aura cancellation lacks current native authority");
    return Packet{"CMSG_PET_CANCEL_AURA",Writer().pack("QI",{guid,spell}).finish()};
}
PetActionTranslation translate_pet_action(Protocol const &p, State &owner, View body)
{
    // A rejected translation sends no native command and keeps the healthy
    // session available. Native transport failures remain outside this guard.
    try {return {pet_request(p,owner,"CMSG_PET_ACTION",body),{}};}
    catch(std::exception const &e) {return {{},e.what()};}
}
PetActionTranslation translate_pet_set_action(Protocol const &p, State &owner, View body)
{
    try {return {pet_request(p,owner,"CMSG_PET_SET_ACTION",body),{}};}
    catch(std::exception const &e) {return {{},e.what()};}
}
Reply pet_response(Protocol const &p, State &owner, std::string const &name, View body)
{
    if(name=="SMSG_PET_SPELLS")
    {
        auto &s=pet_state(owner);auto previous=s.controlled_guid;
        s.pending_spells.clear();s.pending_guid=0;s.controlled_guid=0;
        s.pending_buttons.fill(0);s.controlled_buttons.fill(0);
        s.pending_autocast.clear();s.controlled_autocast.clear();
        std::uint64_t guid=0;auto message=spell_message(body,owner.map(),guid,s);
        if(!guid || guid!=previous)owner.pet_cast_state.reset();
        if(!guid)return Packet{"SMSG_PET_SPELLS_MESSAGE",std::move(message)};
        s.pending_guid=guid;s.pending_spells=std::move(message);
        return pet_ready(p,owner);
    }
    if(name!="SMSG_PET_NAME_QUERY_RESPONSE")return {};
    Reader r(body);auto number=r.take<std::uint32_t>();auto pet_name=native_text(r);
    auto timestamp=r.take<std::uint32_t>();auto declined=r.take<std::uint8_t>();
    if(declined>1 || pet_name.size()>255)throw std::runtime_error("invalid native pet name");
    std::array<Bytes,5> names;
    if(declined)for(auto &n:names)
    {
        n=native_text(r);if(n.size()>127)throw std::runtime_error("native declined pet name exceeds bound");
    }
    r.end();auto &s=pet_state(owner);auto pending=s.names.find(number);
    if(pending==s.names.end() || pending->second.empty())return {};
    auto query=pending->second.front();pending->second.pop_front();--s.name_count;
    if(pending->second.empty())s.names.erase(pending);
    auto visible=owner.visible_units.find(query.guid);
    if(visible==owner.visible_units.end() || p.field(visible->second,"UNIT_FIELD_PETNUMBER")!=number ||
       integer(get(visible->second,"map"))!=query.map)return {};
    Writer w;w.guid(Protocol::modern_guid(query.guid,query.map)).bits(!pet_name.empty(),1);
    if(!pet_name.empty())
    {
        w.bits(pet_name.size(),8).bits(declined,1);
        for(auto const &n:names)w.bits(n.size(),7);
        for(auto const &n:names)w.raw(n);
        // QueryPetNameResponse uses Timestamp<> (signed64). UnitData's separate
        // PetNameTimestamp field remains uint32 on this pinned client.
        w.pack("q",{timestamp}).raw(pet_name);
    }
    return Packet{"SMSG_QUERY_PET_NAME_RESPONSE",w.finish()};
}
void pet_removed(State &owner, std::uint64_t guid)
{
    if(!owner.pet_state)return;
    auto &s=*owner.pet_state;
    if(s.controlled_guid==guid)
    {s.controlled_guid=0;s.controlled_buttons.fill(0);s.controlled_autocast.clear();owner.pet_cast_state.reset();}
    if(s.pending_guid==guid)
    {s.pending_guid=0;s.pending_spells.clear();s.pending_buttons.fill(0);s.pending_autocast.clear();}
    for(auto it=s.names.begin();it!=s.names.end();)
    {
        s.name_count-=std::erase_if(it->second,[guid](auto const &query){return query.guid==guid;});
        if(it->second.empty())it=s.names.erase(it);else ++it;
    }
}
bool pet_cast_authority(Protocol const &p,State const &owner,std::uint64_t guid,unsigned spell)
{
    if(!owner.created || owner.character.is_null() || owner.self_snapshot.is_null() ||
       !owner.pet_state || owner.pet_state->controlled_guid!=guid || guid>>52!=0xf14 ||
       (spell!=3110 && spell!=6307))return false;
    auto found=owner.visible_units.find(guid);
    if(found==owner.visible_units.end())return false;
    auto const &unit=found->second;auto slot=spell==3110 ? 3 : 4;
    auto button=owner.pet_state->controlled_buttons[slot];auto type=button>>24;
    return integer(get(unit,"kind"))==3 && integer(get(unit,"map"))==owner.map() &&
        p.field(unit,"UNIT_FIELD_PETNUMBER") && p.field(unit,"UNIT_FIELD_HEALTH") &&
        p.field(owner.self_snapshot,"UNIT_FIELD_HEALTH") &&
        field_guid(p,unit,"UNIT_FIELD_SUMMONEDBY")==owner.guid() &&
        field_guid(p,owner.self_snapshot,"UNIT_FIELD_SUMMON")==guid &&
        (button&0x00ffffffu)==spell && (type==0x81 || type==0xc1) &&
        owner.pet_state->controlled_autocast.contains(spell);
}
bool pet_rename_authority(Protocol const &p,State const &owner,std::uint64_t guid,unsigned number)
{
    if(!owner.created || owner.character.is_null() || owner.self_snapshot.is_null() ||
       !owner.pet_state || owner.pet_state->controlled_guid!=guid || guid>>52!=0xf14 || !number ||
       ((p.field(owner.self_snapshot,"UNIT_FIELD_BYTES_0")>>8)&255)!=3)return false;
    auto found=owner.visible_units.find(guid);
    if(found==owner.visible_units.end())return false;
    auto const &unit=found->second;
    return integer(get(unit,"kind"))==3 && integer(get(unit,"map"))==owner.map() &&
        p.field(unit,"UNIT_FIELD_PETNUMBER")==number &&
        ((p.field(unit,"UNIT_FIELD_BYTES_2")>>16)&1) &&
        field_guid(p,unit,"UNIT_FIELD_SUMMONEDBY")==owner.guid() &&
        field_guid(p,owner.self_snapshot,"UNIT_FIELD_SUMMON")==guid;
}
bool pet_abandon_authority(Protocol const &p,State const &owner,std::uint64_t guid)
{
    if(!owner.created || owner.character.is_null() || owner.self_snapshot.is_null() ||
       !owner.pet_state || owner.pet_state->controlled_guid!=guid || guid>>52!=0xf14 ||
       ((p.field(owner.self_snapshot,"UNIT_FIELD_BYTES_0")>>8)&255)!=3)return false;
    auto found=owner.visible_units.find(guid);
    if(found==owner.visible_units.end())return false;
    auto const &unit=found->second;
    // Native UNIT_CAN_BE_ABANDONED is bit2 of the pet flag byte. The native
    // handler accepts a visible Pet GUID, so ownership must be checked here.
    return integer(get(unit,"kind"))==3 && integer(get(unit,"map"))==owner.map() &&
        p.field(unit,"UNIT_FIELD_PETNUMBER") &&
        ((p.field(unit,"UNIT_FIELD_BYTES_2")>>16)&2) &&
        field_guid(p,unit,"UNIT_FIELD_SUMMONEDBY")==owner.guid() &&
        field_guid(p,owner.self_snapshot,"UNIT_FIELD_SUMMON")==guid;
}
}
