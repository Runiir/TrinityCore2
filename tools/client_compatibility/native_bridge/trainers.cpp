// Native NPCPackets::TrainerList -> pinned 60895 TrainerList::Write.
#include "trainers.hpp"
#include <algorithm>

namespace bridge
{
struct TrainerState
{
    std::uint64_t owner=0,npc=0;
    std::uint32_t id=0;
    bool control_demon=false;
};
namespace
{
constexpr unsigned ControlLesson=80388,ControlAbility=93375;
bool control_binding(State const &owner,std::uint64_t npc)
{
    auto const &binding=owner.trainer_state;
    return binding && binding->owner==owner.guid() && binding->npc==npc && binding->control_demon;
}
}
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
        if(spell==ControlAbility)
        {
            if(!control_binding(owner,npc) || owner.trainer_state->id!=unsigned(id))
                throw std::runtime_error("Control Demon purchase requires its current native trainer catalog");
            spell=ControlLesson;
        }
        else if(spell==ControlLesson && control_binding(owner,npc))
            throw std::runtime_error("retired Control Demon display identity");
        w.pack("2I",{id,spell});
    }
    r.end();return Packet{name,w.finish()};
}
Reply trainer_response(Protocol const &protocol,State &owner,std::string const &name,View body)
{
    if(name=="SMSG_TRAINER_BUY_FAILED")
    {
        Reader r(body);auto npc=r.take<std::uint64_t>();auto spell=r.take<std::uint32_t>(),reason=r.take<std::uint32_t>();r.end();
        if(!spell || spell>0x7fffffff || reason>2)throw std::runtime_error("invalid native trainer failure");
        auto found=owner.visible_units.find(npc);
        if(found==owner.visible_units.end() || integer(get(found->second,"kind"))!=3 ||
            !(protocol.field(found->second,"UNIT_NPC_FLAGS")&16))return {};
        if(spell==ControlLesson && control_binding(owner,npc))spell=ControlAbility;
        // Modern FailReason has only unavailable/money; native skill rejection
        // is an unavailable lesson, not an undefined modern enum value.
        return Packet{name,Writer().guid(Protocol::modern_guid(npc,integer(get(found->second,"map")))).pack("2i",{spell,reason==1?1:0}).finish()};
    }
    if(name!="SMSG_TRAINER_LIST")return {};
    owner.trainer_state.reset();
    Reader r(body);auto npc=r.take<std::uint64_t>();auto type=r.take<std::uint32_t>(),id=r.take<std::uint32_t>(),count=r.take<std::uint32_t>();
    if(type>3 || !id || id>0x7fffffff || count>4096)throw std::runtime_error("invalid native trainer catalog header");
    auto found=owner.visible_units.find(npc);
    if(found==owner.visible_units.end() || integer(get(found->second,"kind"))!=3 ||
        !(protocol.field(found->second,"UNIT_NPC_FLAGS")&16))return {};
    Writer w;w.guid(Protocol::modern_guid(npc,integer(get(found->second,"map")))).pack("3I",{type,id,count});
    auto binding=std::make_shared<TrainerState>();binding->owner=owner.guid();binding->npc=npc;binding->id=id;
    bool native_control_ability=false;
    for(unsigned i=0;i<count;++i)
    {
        auto spell=r.take<std::uint32_t>();auto usable=r.take<std::uint8_t>();auto cost=r.take<std::uint32_t>();
        auto level=r.take<std::uint8_t>();auto skill=r.take<std::uint32_t>(),rank=r.take<std::uint32_t>();
        auto abilities=r.unpack("2i");auto dialog=r.take<std::uint32_t>(),button=r.take<std::uint32_t>();
        if(!spell || spell>0x7fffffff || usable>2 || dialog>1 || button>1)
            throw std::runtime_error("invalid native trainer spell");
        if(spell==ControlAbility)native_control_ability=true;
        if(spell==ControlLesson && integer(get(owner.character,"class"))==9)
        {
            if(binding->control_demon)throw std::runtime_error("duplicate native Control Demon lesson");
            // Owned UI116/117:80388 is a dummy in both base tables; the native
            // spell_learn_spell relation teaches actual ability93375. Publish
            // that existing ability and reverse only this catalog-bound buy.
            // Cost, native state and every requirement stay authoritative.
            spell=ControlAbility;binding->control_demon=true;
        }
        // Native has two prerequisites and two profession UI flags, totaling
        // 34 bytes. Modern has three prerequisites and Unk440; both extra fields
        // stay zero, as in pinned modern Trainer::SendSpells.
        w.pack("i3I3iIBB",{spell,cost,skill,rank,abilities[0],abilities[1],0,0,usable,level});
    }
    auto greeting=r.raw(r.remaining());r.end();
    if(greeting.empty() || greeting.size()>2048 || greeting.back()!=0 ||
        std::find(greeting.begin(),greeting.end()-1,0)!=greeting.end()-1)
        throw std::runtime_error("invalid native trainer greeting");
    if(binding->control_demon && native_control_ability)
        throw std::runtime_error("ambiguous native Control Demon lesson identities");
    owner.trainer_state=std::move(binding);
    return Packet{name,w.bits(greeting.size()-1,11).flush().raw(greeting.first(greeting.size()-1)).finish()};
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
