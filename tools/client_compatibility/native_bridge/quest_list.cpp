// Native offered quests, serialized for the stock Classic quest greeting panel.
#include "quests.hpp"

namespace bridge
{
Reply quest_list_response(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
    if(name!="SMSG_QUEST_GIVER_QUEST_LIST_MESSAGE")return {};
    Reader r(body);auto guid=r.take<std::uint64_t>();auto greeting=native_text(r);
    auto delay=r.take<std::uint32_t>(),emote=r.take<std::uint32_t>();auto count=r.take<std::uint8_t>();
    if(count>64 || greeting.size()>2047)throw std::runtime_error("native quest list exceeds bound");
    Writer rows;std::unordered_set<unsigned> seen;
    for(unsigned i=0;i<count;++i)
    {
        auto id=r.take<std::uint32_t>(),type=r.take<std::uint32_t>();auto level=r.take<std::int32_t>();
        auto flags=r.take<std::uint32_t>();auto repeatable=r.take<std::uint8_t>();auto title=native_text(r);
        if(!id || id>0x7fffffff || repeatable>1 || title.size()>511 || !seen.insert(id).second)
            throw std::runtime_error("invalid native offered quest");
        rows.pack("3I2i4I",{id,0,type,level,level,0,flags,0,0})
            .bits(repeatable,1).bits(0,3).bits(title.size(),9).raw(title);
    }
    r.end();auto found=owner.visible_units.find(guid);
    if(found==owner.visible_units.end() || integer(get(found->second,"kind"))!=3 ||
        !(protocol.field(found->second,"UNIT_NPC_FLAGS")&2))return {};
    Writer w;w.guid(Protocol::modern_guid(guid,integer(get(found->second,"map"))))
        .pack("3I",{delay,emote,count}).bits(greeting.size(),11).flush().raw(rows.finish()).raw(greeting);
    return Packet{name,w.finish()};
}
}
