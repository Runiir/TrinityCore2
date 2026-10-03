// Ordinary NPC completion and plain reward choices. Native quest eligibility,
// prices, inventory checks and the actual reward remain server authoritative.
#include "quests.hpp"
#include "quest_rewards.hpp"

namespace bridge
{
namespace
{
bool active(Protocol const &p,State const &s,unsigned id)
{
    if(!id || id>0x7fffffff)throw std::runtime_error("invalid quest turn-in identity");
    for(unsigned slot=0;slot<25;++slot)
        if(p.field(s.self_snapshot,"PLAYER_QUEST_LOG_1_1",slot*5)==id)return true;
    return false;
}
Value const &giver(Protocol const &p,State const &s,std::uint64_t guid)
{
    auto found=s.visible_units.find(guid);
    if(found==s.visible_units.end() || integer(get(found->second,"kind"))!=3 ||
        !(p.field(found->second,"UNIT_NPC_FLAGS")&2))
        throw std::runtime_error("quest turn-in requires a visible native NPC questgiver");
    return found->second;
}
}
Reply quest_turnin_request(Protocol const &p,State &s,std::string const &name,View body)
{
    if(name!="CMSG_QUEST_GIVER_COMPLETE_QUEST" && name!="CMSG_QUEST_GIVER_REQUEST_REWARD" &&
        name!="CMSG_QUEST_GIVER_CHOOSE_REWARD")return {};
    Reader r(body);auto npc=owned_unit(s,r.guid());giver(p,s,npc);auto id=r.take<std::uint32_t>();
    if(!active(p,s,id))throw std::runtime_error("quest turn-in requires an owned active quest");
    Writer w;w.pack("QI",{npc,id});
    if(name=="CMSG_QUEST_GIVER_COMPLETE_QUEST")w.put<std::uint8_t>(r.bits(1));
    if(name=="CMSG_QUEST_GIVER_CHOOSE_REWARD")
    {
        auto type=r.bits(2);auto item=r.take<std::int32_t>();auto seed=r.take<std::uint32_t>(),suffix=r.take<std::uint32_t>();
        auto bonus=r.bits(1);r.align();auto modifiers=r.bits(6);r.align();auto quantity=r.take<std::int32_t>();
        auto const &offer=s.quest_reward_offer;
        if(type || item<0 || quantity<0 || seed || suffix || bonus || modifiers || offer.is_null() ||
            integer(get(offer,"guid"))!=npc || integer(get(offer,"quest"))!=id)
            throw std::runtime_error("reward choice does not belong to a supported native offer");
        auto const &choices=get(offer,"choices").as_array();Value index;
        if(choices.empty() && !item && !quantity)index=0;
        for(auto const &choice:choices)
            if(signed_integer(get(choice,"id"))==item && signed_integer(get(choice,"quantity"))==quantity)
            {
                if(!index.is_null())throw std::runtime_error("ambiguous native reward choice");
                index=get(choice,"index");
            }
        if(index.is_null())throw std::runtime_error("reward item is absent from the native offer");
        w.put<std::uint32_t>(integer(index));
    }
    r.end();return Packet{name,w.finish()};
}
Reply quest_turnin_response(Protocol const &p,State &s,std::string const &name,View body)
{
    if(name=="SMSG_QUEST_GIVER_QUEST_COMPLETE")
    {
        Reader r(body);r.take<std::uint32_t>();auto skillUps=r.take<std::uint32_t>();auto money=r.take<std::int32_t>();
        auto xp=r.take<std::uint32_t>(),id=r.take<std::uint32_t>(),skill=r.take<std::uint32_t>();
        auto launch=r.bits(1),use=r.bits(1);r.end();
        if(!id || id>0x7fffffff || xp>0x7fffffff || skill>0x7fffffff || skillUps>0x7fffffff)
            throw std::runtime_error("invalid native quest reward completion");
        s.quest_reward_offer=nullptr;
        return Packet{name,Writer().pack("IIqII",{id,xp,money,skill,skillUps})
            .bits(use,1).bits(launch,1).bits(0,2).flush()
            .pack("iII",{0,0,0}).bits(0,1).flush().bits(0,6).flush().finish()};
    }
    if(name!="SMSG_QUEST_GIVER_OFFER_REWARD_MESSAGE")return {};
    Reader r(body);auto npc=r.take<std::uint64_t>();auto id=r.take<std::uint32_t>();
    auto title=native_text(r),text=native_text(r),giverText=native_text(r),giverName=native_text(r),turnText=native_text(r),turnName=native_text(r);
    auto portrait=r.take<std::uint32_t>(),turnPortrait=r.take<std::uint32_t>();auto launched=r.take<std::uint8_t>();
    auto flags=r.take<std::uint32_t>(),party=r.take<std::uint32_t>(),count=r.take<std::uint32_t>();
    if(count>16 || launched>1 || title.size()>511 || text.size()>4095 || giverText.size()>1023 ||
        turnText.size()>1023 || giverName.size()>255 || turnName.size()>255)
        throw std::runtime_error("unsupported native quest offer text/emotes");
    auto emotes=r.unpack(std::string(count*2,'I'));Value choices;auto rewards=quest_rewards(r,&choices);r.end();
    auto const &unit=giver(p,s,npc);if(!active(p,s,id))return {};
    s.quest_reward_offer=Object{{"guid",npc},{"quest",id},{"choices",choices}};
    auto entry=(npc>>32)&0xfffff;Writer w;w.raw(rewards).put(count)
        .guid(Protocol::modern_guid(npc,integer(get(unit,"map"))))
        .pack("7I",{flags,0,0,entry,id,party,0});
    for(unsigned i=0;i<count;++i)w.pack("II",{emotes[i*2+1],emotes[i*2]});
    w.bits(launched,1).bits(0,2).flush().pack("7I",{0,portrait,0,0,turnPortrait,entry,0})
        .bits(title.size(),9).bits(text.size(),12).bits(giverText.size(),10).bits(giverName.size(),8)
        .bits(turnText.size(),10).bits(turnName.size(),8).flush()
        .raw(title).raw(text).raw(giverText).raw(giverName).raw(turnText).raw(turnName);
    return Packet{name,w.finish()};
}
}
