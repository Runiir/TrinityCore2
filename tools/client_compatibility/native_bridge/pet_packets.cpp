#include "pet_packets.hpp"

namespace bridge
{
struct PetState
{
    struct NameQuery {std::uint64_t guid; unsigned map;};
    std::unordered_map<unsigned, std::deque<NameQuery>> names;
    unsigned name_count=0;
    std::uint64_t pending_guid=0;
    Bytes pending_spells;
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
Bytes spell_message(View body, unsigned map, std::uint64_t &guid)
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
    if(react>2 || command>3 || flags>255)throw std::runtime_error("unsupported native pet mode");
    auto buttons=r.unpack("10I");
    auto count=r.take<std::uint8_t>();auto actions=r.unpack(std::string(count,'I'));
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
    // A session's native catalog grants no commands or fabricated ownership.
    // Creation and both native owner/summon links must first agree.
    if(integer(get(unit,"kind"))!=3 || s.pending_guid>>52!=0xf14 ||
       field_guid(p,unit,"UNIT_FIELD_SUMMONEDBY")!=owner.guid() ||
       !p.field(unit,"UNIT_FIELD_PETNUMBER") || owner.self_snapshot.is_null() ||
       field_guid(p,owner.self_snapshot,"UNIT_FIELD_SUMMON")!=s.pending_guid)return {};
    Bytes message;message.swap(s.pending_spells);s.pending_guid=0;
    return Packet{"SMSG_PET_SPELLS_MESSAGE",std::move(message)};
}
Reply pet_request(Protocol const &p, State &owner, std::string const &name, View body)
{
    if(name!="CMSG_REQUEST_PET_INFO" && name!="CMSG_QUERY_PET_NAME")return {};
    if(!owner.created || owner.character.is_null())throw std::runtime_error("pet read without owned character");
    if(name=="CMSG_REQUEST_PET_INFO")
    {
        Reader(body).end();return Packet{name,{}};
    }
    Reader r(body);auto guid=owned_unit(owner,r.guid());r.end();
    auto const &unit=owner.visible_units.at(guid);
    auto number=p.field(unit,"UNIT_FIELD_PETNUMBER");
    if(guid>>52!=0xf14 || !number)throw std::runtime_error("name query requires a visible numbered pet");
    for(auto const &[other,record]:owner.visible_units)
        if(other!=guid && other>>52==0xf14 && p.field(record,"UNIT_FIELD_PETNUMBER")==number)
            throw std::runtime_error("ambiguous visible pet number");
    auto &s=pet_state(owner);
    if(s.name_count>=64)throw std::runtime_error("pet name queries exceed bound");
    s.names[number].push_back({guid,static_cast<unsigned>(integer(get(unit,"map")))});++s.name_count;
    return Packet{"CMSG_PET_NAME_QUERY",Writer().pack("IQ",{number,guid}).finish()};
}
Reply pet_response(Protocol const &p, State &owner, std::string const &name, View body)
{
    if(name=="SMSG_PET_SPELLS")
    {
        std::uint64_t guid=0;auto message=spell_message(body,owner.map(),guid);
        auto &s=pet_state(owner);s.pending_spells.clear();s.pending_guid=0;
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
}
