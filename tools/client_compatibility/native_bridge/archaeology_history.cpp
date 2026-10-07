#include "archaeology.hpp"
#include <unordered_set>

namespace bridge
{
bool research_complete(std::string const &name,View body)
{
    if(name!="SMSG_RESEARCH_COMPLETE")return false;
    Reader r(body);auto time=r.take<std::uint32_t>(),count=r.take<std::uint32_t>(),project=r.take<std::uint32_t>();r.end();
    if(!time || !count || !project || project>65535)throw std::runtime_error("invalid native completed research");
    return true;
}
Reply research_history(State const &owner,std::string const &name,View body)
{
    if(name!="SMSG_SETUP_RESEARCH_HISTORY")return {};
    Reader r(body);auto count=r.bits(22);r.align();
    if(count>144)throw std::runtime_error("research history exceeds native project catalog");
    Array history;std::unordered_set<unsigned> seen;
    for(unsigned i=0;i<count;++i)
    {
        auto project=r.take<std::int32_t>(),times=r.take<std::int32_t>();auto time=r.take<std::uint32_t>();
        if(project<=0 || project>65535 || times<=0 || !time || !seen.insert(project).second)
            throw std::runtime_error("invalid native research history row");
        history.push_back(Array{project,time,times});
    }
    r.end();
    // Pinned ActivePlayerData bits 102/122 contain owner-only ResearchHistory.
    // The pinned 4.4.2 reader aligns on entering ResearchHistory after the
    // mandatory PetStable presence bit. Sharing that byte hides its mask.
    // Login can deliver the Hunter catalog first. Presence0 in this later
    // group102 update clears that cache, so preserve its current authority.
    Writer data;data.pack("BBBI",{1,0,3,1u<<7}).pack("I",{1u<<3})
        .bits(0,14).bits((1u<<6)|(1u<<26),32).flush().bits(owner.pet_stable.is_object(),1).flush();
    data.bits(3,2).bits(count,32);
    for(unsigned i=0;i<count;++i)data.bits(1,1);
    data.flush();
    for(auto const &row:history)
        data.bits(15,4).flush().pack("IqI",row.as_array());
    auto block=Writer().put<std::uint8_t>(0).guid(owner.guid(),player_high())
        .put<std::uint32_t>(data.data().size()).raw(data.data()).finish();
    return Packet{"SMSG_UPDATE_OBJECT",object_packet(owner.map(),{block})};
}
}
