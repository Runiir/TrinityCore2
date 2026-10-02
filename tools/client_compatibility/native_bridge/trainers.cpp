// Native NPCPackets::TrainerList -> pinned 60895 TrainerList::Write.
#include "trainers.hpp"
#include <algorithm>

namespace bridge
{
Reply trainer_request(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
    if(name!="CMSG_TRAINER_LIST")return {};
    Reader r(body);auto npc=owned_unit(owner,r.guid());r.end();auto const &unit=owner.visible_units.at(npc);
    if(integer(get(unit,"kind"))!=3 || !(protocol.field(unit,"UNIT_NPC_FLAGS")&16))
        throw std::runtime_error("trainer query requires a native visible trainer");
    return Packet{name,Writer().put(npc).finish()};
}
Reply trainer_response(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
    if(name!="SMSG_TRAINER_LIST")return {};
    Reader r(body);auto npc=r.take<std::uint64_t>();auto type=r.take<std::uint32_t>(),id=r.take<std::uint32_t>(),count=r.take<std::uint32_t>();
    if(type>3 || !id || id>0x7fffffff || count>4096)throw std::runtime_error("invalid native trainer catalog header");
    auto found=owner.visible_units.find(npc);
    if(found==owner.visible_units.end() || integer(get(found->second,"kind"))!=3 ||
        !(protocol.field(found->second,"UNIT_NPC_FLAGS")&16))return {};
    Writer w;w.guid(Protocol::modern_guid(npc,integer(get(found->second,"map")))).pack("3I",{type,id,count});
    for(unsigned i=0;i<count;++i)
    {
        auto spell=r.take<std::uint32_t>();auto usable=r.take<std::uint8_t>();auto cost=r.take<std::uint32_t>();
        auto level=r.take<std::uint8_t>();auto skill=r.take<std::uint32_t>(),rank=r.take<std::uint32_t>();
        auto abilities=r.unpack("3i");auto dialog=r.take<std::uint32_t>(),button=r.take<std::uint32_t>();
        if(!spell || spell>0x7fffffff || usable>2 || dialog>1 || button>1)
            throw std::runtime_error("invalid native trainer spell");
        // Modern Trainer::SendSpells has no legacy profession dialog/button fields;
        // it derives their UI from spell data and leaves Unk440 at its zero default.
        w.pack("i3I3iIBB",{spell,cost,skill,rank,abilities[0],abilities[1],abilities[2],0,usable,level});
    }
    auto greeting=r.raw(r.remaining());r.end();
    if(greeting.empty() || greeting.size()>2048 || greeting.back()!=0 ||
        std::find(greeting.begin(),greeting.end()-1,0)!=greeting.end()-1)
        throw std::runtime_error("invalid native trainer greeting");
    w.bits(greeting.size()-1,11).flush().raw(greeting.first(greeting.size()-1));
    return Packet{name,w.finish()};
}
}
