// Native 4.3.4 status semantics -> modern 64-bit questgiver categories.
#include "quests.hpp"

namespace bridge
{
namespace
{
std::uint64_t modern_status(unsigned native)
{
    // Pinned QuestDef.h categories. The legacy WPP 4x enum annotation is
    // contradicted by UI24: native Available=0x100 renders a blue repeatable !.
    // Retain native eligibility while translating the semantic category.
    static constexpr std::array<std::uint64_t,11> values={0,0x2,0x40,0x20,0x100,0x2000,
        0x4000,0x1000000,0x400000,0x200000000,0x400000000};
    std::uint64_t status=0;
    for(unsigned i=0;i<values.size();++i)if(native&(1u<<i))status|=values[i];
    return status;
}
Value const *giver(Protocol const &protocol,State const &owner,std::uint64_t guid)
{
    auto unit=owner.visible_units.find(guid);
    if(unit!=owner.visible_units.end() && integer(get(unit->second,"kind"))==3 &&
        (protocol.field(unit->second,"UNIT_NPC_FLAGS")&2))return &unit->second;
    auto object=owner.visible_gameobjects.find(guid);
    if(object!=owner.visible_gameobjects.end() && integer(get(object->second,"kind"))==5 &&
        ((protocol.field(object->second,"GAMEOBJECT_BYTES_1")>>8)&255)==2)return &object->second;
    return nullptr;
}
void require_owned_giver_identity(State const &owner,Array const &identity)
{
    auto low=integer(identity[0]),high=integer(identity[1]);auto type=high>>58;
    auto entry=(high>>6)&0x7fffffu;
    if((type!=8 && type!=11) || !low || low>0xffffffffu || !entry || entry>0xfffffu)
        throw std::runtime_error("invalid cached questgiver identity");
    auto native=((type==8 ? 0xf13ull : 0xf11ull)<<52) | (entry<<32) | low;
    if(identity!=Protocol::modern_guid(native,owner.map()))
        throw std::runtime_error("cached questgiver targets another realm or map");
}
}
Reply quest_status_request(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
    if(name=="CMSG_QUEST_GIVER_STATUS_TRACKED_QUERY")
    {
        Reader r(body);auto count=r.take<std::uint32_t>();
        if(count>1000)throw std::runtime_error("tracked quest status exceeds bound");
        for(unsigned i=0;i<count;++i)require_owned_giver_identity(owner,r.guid());
        r.end();
        if(!count)return Packet{"SMSG_QUEST_GIVER_STATUS_MULTIPLE",Writer().put<std::uint32_t>(0).finish()};
        // 4.3.4 has no subset request. Refresh all native-visible givers instead.
        // Do not queue a subset against the next multiple reply: native also
        // sends unsolicited multiple updates after quest-state changes.
        // Retired/cached identities grant no visibility or interaction access.
        return Packet{"CMSG_QUEST_GIVER_STATUS_MULTIPLE_QUERY",{}};
    }
    if(name=="CMSG_QUEST_GIVER_STATUS_MULTIPLE_QUERY")
    {
        Reader(body).end();return Packet{name,{}};
    }
    if(name!="CMSG_QUEST_GIVER_STATUS_QUERY")return {};
    Reader r(body);auto identity=r.guid();r.end();
    for(auto const *objects:{&owner.visible_units,&owner.visible_gameobjects})
        for(auto const &[guid,record]:*objects)
            if(identity==Protocol::modern_guid(guid,integer(get(record,"map"))) && giver(protocol,owner,guid))
                return Packet{name,Writer().put(guid).finish()};
    // Cached NPC status reads can precede creation or arrive after destruction.
    // Clear only a well-formed identity on the owned map. No native request or
    // visibility grant is produced, and hello/accept/reward keep their guards.
    require_owned_giver_identity(owner,identity);
    return Packet{"SMSG_QUEST_GIVER_STATUS",Writer().guid(identity).put<std::uint64_t>(0).finish()};
}
Reply quest_status_response(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
    bool multiple=name=="SMSG_QUEST_GIVER_STATUS_MULTIPLE";
    if(!multiple && name!="SMSG_QUEST_GIVER_STATUS")return {};
    Reader r(body);auto count=multiple?r.take<std::uint32_t>():1;
    if(count>1000)throw std::runtime_error("native quest status exceeds bound");
    Writer rows;unsigned accepted=0;std::unordered_set<std::uint64_t> seen;
    for(unsigned i=0;i<count;++i)
    {
        auto guid=r.take<std::uint64_t>();auto status=r.take<std::uint32_t>();
        if(status&~0x7ffu || !seen.insert(guid).second)
            throw std::runtime_error("invalid native Classic quest status");
        if(auto record=giver(protocol,owner,guid))
        {
            rows.guid(Protocol::modern_guid(guid,integer(get(*record,"map")))).put<std::uint64_t>(modern_status(status));
            ++accepted;
        }
    }
    r.end();
    if(!multiple && !accepted)return {};
    Writer w;if(multiple)w.put<std::uint32_t>(accepted);
    return Packet{name,w.raw(rows.finish()).finish()};
}
}
