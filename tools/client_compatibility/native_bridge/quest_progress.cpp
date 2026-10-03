// Native credit events -> modern Classic notifications. Quest slot updates
// remain the authority for counters; these packets do not create quest progress.
#include "quests.hpp"

namespace bridge
{
Reply quest_progress_response(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
    if(name!="SMSG_QUEST_UPDATE_ADD_CREDIT" && name!="SMSG_QUEST_UPDATE_COMPLETE")return {};
    Reader r(body);auto id=r.take<std::uint32_t>();
    if(!id || id>0x7fffffff)throw std::runtime_error("invalid native quest progress identity");
    bool active=false;
    for(unsigned slot=0;slot<25;++slot)
        active|=protocol.field(owner.self_snapshot,"PLAYER_QUEST_LOG_1_1",slot*5)==id;
    if(name=="SMSG_QUEST_UPDATE_COMPLETE")
    {
        r.end();
        if(!active)return {};
        return Packet{name,Writer().put(id).finish()};
    }
    auto object=r.take<std::uint32_t>(),count=r.take<std::uint32_t>(),required=r.take<std::uint32_t>();
    auto victim=r.take<std::uint64_t>();r.end();
    auto entry=object&0x7fffffff;auto gameobject=bool(object&0x80000000);
    if(!entry || !count || !required || count>required || required>65535)
        throw std::runtime_error("invalid native quest objective credit");
    if(victim && (victim>>52!=(gameobject?0xf11u:0xf13u)))
        throw std::runtime_error("native quest credit victim type differs from objective");
    if(!active)return {};
    Writer w;w.guid(Protocol::modern_guid(victim,owner.map())).pack("IIHHB",{id,entry,count,required,gameobject?2:0});
    return Packet{name,w.finish()};
}
}
