// Ordinary questgiver reads. Native eligibility and quest data remain authoritative.
#include "quests.hpp"
#include "quest_rewards.hpp"

namespace bridge
{
Reply quest_request(Protocol const &protocol,State &owner,std::string const &name,View body)
{
    if(auto reply=quest_turnin_request(protocol,owner,name,body))return reply;
    if(auto reply=quest_status_request(protocol,owner,name,body))return reply;
    if(name=="CMSG_QUERY_QUEST_INFO")
    {
        Reader r(body);auto id=r.take<std::int32_t>();r.guid();r.end();
        if(id<=0)throw std::runtime_error("invalid quest information identity");
        // Modern also carries the public query's questgiver; native reads only ID.
        return Packet{name,Writer().pack("I",{id}).finish()};
    }
    if(name=="CMSG_QUEST_LOG_REMOVE_QUEST")
    {
        Reader r(body);auto slot=r.take<std::uint8_t>();r.end();
        if(slot>=25 || !protocol.field(owner.self_snapshot,"PLAYER_QUEST_LOG_1_1",slot*5))
            throw std::runtime_error("quest abandonment requires an active owned slot");
        return Packet{name,Writer().pack("B",{slot}).finish()};
    }
    if(name!="CMSG_QUEST_GIVER_HELLO" && name!="CMSG_QUEST_GIVER_QUERY_QUEST" && name!="CMSG_QUEST_GIVER_ACCEPT_QUEST")return {};
    Reader r(body);auto npc=owned_unit(owner,r.guid());auto const &unit=owner.visible_units.at(npc);
    if(integer(get(unit,"kind"))!=3 || !(protocol.field(unit,"UNIT_NPC_FLAGS")&2))
        throw std::runtime_error("questgiver query requires a native visible questgiver");
    Writer w;w.put(npc);
    if(name=="CMSG_QUEST_GIVER_QUERY_QUEST" || name=="CMSG_QUEST_GIVER_ACCEPT_QUEST")
    {
        auto id=r.take<std::int32_t>();auto respond=r.bits(1);r.align();
        if(id<=0)throw std::runtime_error("invalid questgiver quest identity");
        // Native QueryQuest reads a bool, but AcceptQuest::StartCheat is uint32.
        // Both are a single bit in the modern request.
        w.pack(name=="CMSG_QUEST_GIVER_ACCEPT_QUEST"?"II":"IB",{id,respond});
    }
    r.end();return Packet{name,w.finish()};
}
Reply quest_response(Protocol const &protocol,State &owner,std::string const &name,View body)
{
    if(auto reply=quest_turnin_response(protocol,owner,name,body))return reply;
    if(auto reply=quest_progress_response(protocol,owner,name,body))return reply;
    if(auto reply=quest_status_response(protocol,owner,name,body))return reply;
    if(auto reply=quest_list_response(protocol,owner,name,body))return reply;
    if(name=="SMSG_QUEST_QUERY_RESPONSE")return quest_query_response(name,body);
    if(name!="SMSG_QUEST_GIVER_QUEST_DETAILS")return {};
    Reader r(body);auto npc=r.take<std::uint64_t>(),inform=r.take<std::uint64_t>();auto id=r.take<std::uint32_t>();
    auto title=native_text(r),description=native_text(r),summary=native_text(r);
    auto giverText=native_text(r),giverName=native_text(r),turnText=native_text(r),turnName=native_text(r);
    auto giverPortrait=r.take<std::uint32_t>(),turnPortrait=r.take<std::uint32_t>();auto launched=r.take<std::uint8_t>();
    auto flags=r.take<std::uint32_t>(),party=r.take<std::uint32_t>();auto cheat=r.take<std::uint8_t>(),popup=r.take<std::uint8_t>();
    auto requiredSpell=r.take<std::uint32_t>();auto rewards=quest_rewards(r);auto count=r.take<std::uint32_t>();
    if(!id || id>0x7fffffff || launched>1 || cheat>1 || popup>1 || count>16 || requiredSpell ||
        title.size()>511 || description.size()>4095 || summary.size()>4095 || giverText.size()>1023 ||
        turnText.size()>1023 || giverName.size()>255 || turnName.size()>255)
        throw std::runtime_error("unsupported or invalid native quest details");
    auto emotes=r.unpack(std::string(count*2,'I'));r.end();
    auto found=owner.visible_units.find(npc);
    if(found==owner.visible_units.end() || integer(get(found->second,"kind"))!=3 ||
        !(protocol.field(found->second,"UNIT_NPC_FLAGS")&2))return {};
    if(inform>0xffffffff)throw std::runtime_error("invalid native quest sharing player");
    Writer w;w.guid(Protocol::modern_guid(npc,integer(get(found->second,"map")))).guid({inform,inform?player_high():0});
    // Native details are narrative, native Objectives is the concise log text.
    // This packet has no structured objectives; query-info supplies those later.
    w.pack("18I",{id,0,giverPortrait,0,0,turnPortrait,flags,0,0,party,0,count,0,0,0,0,
        (npc>>32)&0xfffff,0}).pack(std::string(count*2,'I'),emotes)
        .bits(title.size(),9).bits(description.size(),12).bits(summary.size(),12)
        .bits(giverText.size(),10).bits(giverName.size(),8).bits(turnText.size(),10).bits(turnName.size(),8)
        .bits(launched,1).bits(0,1).bits(0,1).bits(0,1).bits(cheat,1).bits(popup,1).flush()
        .raw(rewards).raw(title).raw(description).raw(summary).raw(giverText).raw(giverName).raw(turnText).raw(turnName);
    return Packet{name,w.finish()};
}
}
