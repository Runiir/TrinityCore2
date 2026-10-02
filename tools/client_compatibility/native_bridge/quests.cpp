// Ordinary questgiver reads. Native eligibility and quest data remain authoritative.
#include "quests.hpp"

namespace bridge
{
Reply quest_request(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
    if(name=="CMSG_QUERY_QUEST_INFO")
    {
        Reader r(body);auto id=r.take<std::int32_t>();r.guid();r.end();
        if(id<=0)throw std::runtime_error("invalid quest information identity");
        // Modern also carries the public query's questgiver; native reads only ID.
        return Packet{name,Writer().pack("I",{id}).finish()};
    }
    if(name!="CMSG_QUEST_GIVER_HELLO" && name!="CMSG_QUEST_GIVER_QUERY_QUEST")return {};
    Reader r(body);auto npc=owned_unit(owner,r.guid());auto const &unit=owner.visible_units.at(npc);
    if(integer(get(unit,"kind"))!=3 || !(protocol.field(unit,"UNIT_NPC_FLAGS")&2))
        throw std::runtime_error("questgiver query requires a native visible questgiver");
    Writer w;w.put(npc);
    if(name=="CMSG_QUEST_GIVER_QUERY_QUEST")
    {
        auto id=r.take<std::int32_t>();auto respond=r.bits(1);r.align();
        if(id<=0)throw std::runtime_error("invalid questgiver quest identity");
        w.pack("IB",{id,respond});
    }
    r.end();return Packet{name,w.finish()};
}
}
