// Native NPCPackets::TrainerList -> pinned 60895 TrainerList::Write.
#include "trainers.hpp"
#include <algorithm>

namespace bridge
{
Reply trainer_request(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
    if(name!="CMSG_TRAINER_LIST" && name!="CMSG_TRAINER_BUY_SPELL")return {};
    Reader r(body);auto npc=owned_unit(owner,r.guid());auto const &unit=owner.visible_units.at(npc);
    if(integer(get(unit,"kind"))!=3 || !(protocol.field(unit,"UNIT_NPC_FLAGS")&16))
        throw std::runtime_error("trainer query requires a native visible trainer");
    Writer w;w.put(npc);
    if(name=="CMSG_TRAINER_BUY_SPELL")
    {
        auto id=r.take<std::int32_t>(),spell=r.take<std::int32_t>();
        if(id<=0 || spell<=0)throw std::runtime_error("invalid trainer learning identity");
        w.pack("2I",{id,spell});
    }
    r.end();return Packet{name,w.finish()};
}
Reply trainer_response(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
    if(name=="SMSG_TRAINER_BUY_FAILED")
    {
        Reader r(body);auto npc=r.take<std::uint64_t>();auto spell=r.take<std::uint32_t>(),reason=r.take<std::uint32_t>();r.end();
        if(!spell || spell>0x7fffffff || reason>2)throw std::runtime_error("invalid native trainer failure");
        auto found=owner.visible_units.find(npc);
        if(found==owner.visible_units.end() || integer(get(found->second,"kind"))!=3 ||
            !(protocol.field(found->second,"UNIT_NPC_FLAGS")&16))return {};
        // Modern FailReason has only unavailable/money; native skill rejection
        // is an unavailable lesson, not an undefined modern enum value.
        return Packet{name,Writer().guid(Protocol::modern_guid(npc,integer(get(found->second,"map")))).pack("2i",{spell,reason==1?1:0}).finish()};
    }
    if(name!="SMSG_TRAINER_LIST")return {};
    Reader r(body);auto npc=r.take<std::uint64_t>();auto type=r.take<std::uint32_t>(),id=r.take<std::uint32_t>(),count=r.take<std::uint32_t>();
    if(type>3 || !id || id>0x7fffffff || count>4096)throw std::runtime_error("invalid native trainer catalog header");
    auto found=owner.visible_units.find(npc);
    if(found==owner.visible_units.end() || integer(get(found->second,"kind"))!=3 ||
        !(protocol.field(found->second,"UNIT_NPC_FLAGS")&16))return {};
    auto encode=[&](unsigned width)
    {
        Reader fields=r;Writer w;
        w.guid(Protocol::modern_guid(npc,integer(get(found->second,"map")))).pack("3I",{type,id,count});
        for(unsigned i=0;i<count;++i)
        {
            auto spell=fields.take<std::uint32_t>();auto usable=fields.take<std::uint8_t>();auto cost=fields.take<std::uint32_t>();
            auto level=fields.take<std::uint8_t>();auto skill=fields.take<std::uint32_t>(),rank=fields.take<std::uint32_t>();
            auto abilities=fields.unpack("3i");auto extra=fields.take<std::uint32_t>();
            if(!spell || spell>0x7fffffff || usable>2)throw std::runtime_error("invalid native trainer spell");
            if(width==38)
            {
                auto button=fields.take<std::uint32_t>();
                if(extra>1 || button>1)throw std::runtime_error("invalid legacy trainer profession flags");
                // The current checkout's legacy dialog/button pair has no modern
                // fields. Pinned modern Trainer::SendSpells leaves Unk440 at zero.
                extra=0;
            }
            // The live backend's captured 34-byte rows carry one uint32 tail.
            w.pack("i3I3iIBB",{spell,cost,skill,rank,abilities[0],abilities[1],abilities[2],extra,usable,level});
        }
        auto greeting=fields.raw(fields.remaining());fields.end();
        if(greeting.empty() || greeting.size()>2048 || greeting.back()!=0 ||
            std::find(greeting.begin(),greeting.end()-1,0)!=greeting.end()-1)
            throw std::runtime_error("invalid native trainer greeting");
        return w.bits(greeting.size()-1,11).flush().raw(greeting.first(greeting.size()-1)).finish();
    };
    std::vector<Bytes> candidates;
    for(unsigned width:{34u,38u})
    {
        if(!count && width==38)continue;
        try{candidates.push_back(encode(width));}catch(std::runtime_error const &){}
    }
    if(candidates.size()!=1)throw std::runtime_error("invalid or ambiguous native trainer row layout");
    return Packet{name,std::move(candidates.front())};
}
bool trainer_completion(std::string const &name,View body)
{
    if(name!="SMSG_TRAINER_BUY_SUCCEEDED")return false;
    Reader r(body);auto npc=r.take<std::uint64_t>();auto spell=r.take<std::uint32_t>();r.end();
    if(!npc || !spell || spell>0x7fffffff)throw std::runtime_error("invalid native trainer completion");
    // Modern has no trainer-success opcode. The actual learned-spell message
    // updates its spellbook and trainer; consume only this legacy acknowledgement.
    return true;
}
}
