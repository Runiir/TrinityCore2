// Pinned 60895 Item/QueryPackets and native HandleReadItem/HandlePageTextQueryOpcode.
#include "item_text.hpp"

namespace bridge
{
namespace
{
constexpr unsigned QUEUE_LIMIT=16,PAGE_LIMIT=64,TEXT_LIMIT=4095;
ItemTextState &text_state(State &owner)
{
    if(!owner.item_text_state)owner.item_text_state=std::make_shared<ItemTextState>();
    return *owner.item_text_state;
}
void owned_item(Protocol const &protocol,State const &owner,std::uint64_t guid)
{
    auto item=owner.inventory_items.find(guid);
    if((guid>>48)!=0x4000 || !(guid&0xffffffff) || item==owner.inventory_items.end() ||
       protocol.field(item->second,"ITEM_FIELD_OWNER")!=owner.guid() ||
       protocol.field(item->second,"ITEM_FIELD_OWNER",1))
        throw std::runtime_error("readable item is outside owned native inventory");
}
std::uint64_t slot_item(Protocol const &protocol,State const &owner,unsigned bag,unsigned index)
{
    if((bag==255 && index>=39) || (bag!=255 && (bag<19 || bag>22)))
        throw std::runtime_error("readable item is outside carried inventory");
    auto pair=[&](Value const &snapshot,std::string_view field,unsigned slot)
    {return static_cast<std::uint64_t>(protocol.field(snapshot,field,slot*2)) |
        (static_cast<std::uint64_t>(protocol.field(snapshot,field,slot*2+1))<<32);};
    std::uint64_t guid;
    if(bag==255)guid=pair(owner.self_snapshot,"PLAYER_FIELD_INV_SLOT_HEAD",index);
    else
    {
        auto container=pair(owner.self_snapshot,"PLAYER_FIELD_INV_SLOT_HEAD",bag);
        owned_item(protocol,owner,container);
        auto const &snapshot=owner.inventory_items.at(container);
        if(index>=protocol.field(snapshot,"CONTAINER_FIELD_NUM_SLOTS"))
            throw std::runtime_error("readable item exceeds its owned container size");
        guid=pair(snapshot,"CONTAINER_FIELD_SLOT_1",index);
    }
    owned_item(protocol,owner,guid);return guid;
}
}
Reply item_text_request(Protocol const &protocol,State &owner,std::string const &name,View body)
{
    if(name!="CMSG_READ_ITEM" && name!="CMSG_QUERY_PAGE_TEXT")return {};
    if(!owner.created || !owner.guid())throw std::runtime_error("item text request outside owned active character");
    Reader r(body);
    if(name=="CMSG_READ_ITEM")
    {
        auto pack=r.take<std::uint8_t>(),slot=r.take<std::uint8_t>();r.end();
        auto [bag,index]=Protocol::inventory_position(pack,slot);
        auto guid=slot_item(protocol,owner,bag,index);auto &state=text_state(owner);
        if(state.reads.size()>=QUEUE_LIMIT && !state.reads.contains(guid))
            throw std::runtime_error("pending item reads exceed bound");
        state.reads.insert(guid);
        return Packet{name,Writer().pack("BB",{bag,index}).finish()};
    }
    auto page=r.take<std::uint32_t>();auto identity=r.guid();r.end();
    if(!page || page&0x80000000)throw std::runtime_error("invalid public page-text identity");
    std::uint64_t guid=0;
    if(identity!=Array{0,0})
    {
        auto low=integer(identity[0]);guid=(0x4000ull<<48)|low;
        if(!low || low>0xffffffff || identity!=Protocol::inventory_guid(guid))
            throw std::runtime_error("page-text item identity mismatch");
        owned_item(protocol,owner,guid);
    }
    // Native page queries serve public static text and ignore GUID. A zero
    // cached-query GUID grants no item use, ownership or object visibility.
    auto &state=text_state(owner);
    if(state.chains.size()>=QUEUE_LIMIT)throw std::runtime_error("pending page-text chains exceed bound");
    state.chains.push_back({page,page,{}});
    return Packet{"CMSG_PAGE_TEXT_QUERY",Writer().pack("IQ",{page,guid}).finish()};
}
Reply item_text_response(Protocol const &protocol,State &owner,std::string const &name,View body)
{
    if(name=="SMSG_READ_ITEM_OK" || name=="SMSG_READ_ITEM_FAILED")
    {
        Reader r(body);auto guid=r.take<std::uint64_t>();r.end();
        if(!owner.item_text_state || !owner.item_text_state->reads.erase(guid))return {};
        owned_item(protocol,owner,guid);
        // The native failure carries no modern Subcode/Delay. Its separate
        // authoritative equipment error remains translated by inventory_response.
        if(name=="SMSG_READ_ITEM_FAILED")return {};
        return Packet{"SMSG_READ_ITEM_RESULT_OK",Writer().guid(Protocol::inventory_guid(guid)).finish()};
    }
    if(name!="SMSG_PAGE_TEXT_QUERY_RESPONSE")return {};
    Reader r(body);auto id=r.take<std::uint32_t>();auto encoded=native_text(r);
    std::string text(encoded.begin(),encoded.end());auto next=r.take<std::uint32_t>();r.end();
    if(!owner.item_text_state || owner.item_text_state->chains.empty())return {};
    auto &state=*owner.item_text_state;auto &chain=state.chains.front();
    bool repeated=false;
    for(auto const &page:chain.pages)if(page.id==next)repeated=true;
    if(id!=chain.expected || text.size()>TEXT_LIMIT || chain.pages.size()>=PAGE_LIMIT ||
       next&0x80000000 || (next && (next==id || repeated)))
    {
        state.chains.clear();throw std::runtime_error("native page-text chain is invalid or exceeds bound");
    }
    chain.pages.push_back({id,next,std::move(text)});chain.expected=next;
    if(next)return {};
    Writer w;w.put(chain.root).bits(1,1).flush().put<std::uint32_t>(chain.pages.size());
    for(auto const &page:chain.pages)
        w.put(page.id).put(page.next).put<std::int32_t>(0).put<std::uint8_t>(0)
            .bits(page.text.size(),12).flush().raw(page.text);
    state.chains.pop_front();return Packet{"SMSG_QUERY_PAGE_TEXT_RESPONSE",w.finish()};
}
}
