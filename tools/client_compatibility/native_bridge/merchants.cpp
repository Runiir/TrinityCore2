// Pinned legacy/modern NPCPackets::VendorInventory, with native catalog authority.
#include "merchants.hpp"
#include <array>

namespace bridge
{
Reply merchant_request(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
    if(name!="CMSG_LIST_INVENTORY" && name!="CMSG_SELL_ITEM" && name!="CMSG_BUY_BACK_ITEM")return {};
    Reader r(body);auto guid=owned_unit(owner,r.guid());auto const &vendor=owner.visible_units.at(guid);
    if(integer(get(vendor,"kind"))!=3 || !(protocol.field(vendor,"UNIT_NPC_FLAGS")&128))
        throw std::runtime_error("vendor request requires a native visible merchant");
    Writer w;w.put(guid);
    if(name=="CMSG_SELL_ITEM")
    {
        auto identity=r.guid();auto amount=r.take<std::uint32_t>();r.end();
        std::uint64_t low=integer(identity[0]),item=(0x4000ull<<48)|low;
        if(!low || low>0xffffffff || integer(identity[1])!=((3ull<<58)|(1ull<<42)) ||
            !owner.inventory_items.contains(item))throw std::runtime_error("sold item is outside owned native inventory");
        auto const &snapshot=owner.inventory_items.at(item);
        if(protocol.field(snapshot,"ITEM_FIELD_OWNER")!=owner.guid() || protocol.field(snapshot,"ITEM_FIELD_OWNER",1))
            throw std::runtime_error("sold item has a different native owner");
        return Packet{name,w.put(item).put(amount).finish()};
    }
    if(name=="CMSG_BUY_BACK_ITEM")
    {
        auto slot=r.take<std::uint32_t>();r.end();
        if(slot<94 || slot>=106)throw std::runtime_error("buyback slot is outside the native twelve-slot window");
        return Packet{"CMSG_BUYBACK_ITEM",w.put<std::uint32_t>(slot-20).finish()};
    }
    r.end();return Packet{name,w.finish()};
}
Reply merchant_response(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
    if(name=="SMSG_SELL_ITEM")
    {
        Reader r(body);auto vendor=r.take<std::uint64_t>(),item=r.take<std::uint64_t>();auto reason=r.take<std::uint8_t>();r.end();
        if(reason<1 || reason>7)throw std::runtime_error("unmapped native sell result");
        Array identity{0,0};
        if(vendor)
        {
            auto found=owner.visible_units.find(vendor);
            if(found==owner.visible_units.end() || integer(get(found->second,"kind"))!=3)return {};
            identity=Protocol::modern_guid(vendor,integer(get(found->second,"map")));
        }
        Writer w;w.guid(identity).pack("Ii",{item?1:0,reason});
        if(item)w.guid(Protocol::inventory_guid(item));
        return Packet{"SMSG_SELL_RESPONSE",w.finish()};
    }
    if(name!="SMSG_VENDOR_INVENTORY")return {};
    Reader r(body);std::array<bool,8> present{};
    present[1]=r.bits(1);present[0]=r.bits(1);auto count=r.bits(21);
    if(count>255)throw std::runtime_error("native vendor count exceeds bound");
    for(unsigned i:{3,6,5,2,7})present[i]=r.bits(1);
    struct Item {bool extended,condition;std::int32_t muid,id,type,quantity,stack,ext=0,cond=0;std::uint32_t price;};
    std::vector<Item> items;
    for(unsigned i=0;i<count;++i){Item item{};item.extended=!r.bits(1);item.condition=!r.bits(1);items.push_back(item);}
    present[4]=r.bits(1);r.align();
    for(auto &item:items)
    {
        item.muid=r.take<std::int32_t>();r.take<std::int32_t>(); // Static durability is in modern item data.
        if(item.extended)item.ext=r.take<std::int32_t>();
        item.id=r.take<std::int32_t>();item.type=r.take<std::int32_t>();item.price=r.take<std::uint32_t>();
        r.take<std::uint32_t>(); // Static display ID is in modern item data.
        if(item.condition)item.cond=r.take<std::int32_t>();
        item.quantity=r.take<std::int32_t>();auto stack=r.take<std::uint32_t>();
        if(item.muid<=0 || item.id<=0 || (item.type!=1 && item.type!=2) || item.quantity < -1 ||
            stack>0x7fffffff || (item.type==1 && !stack) || item.ext<0 || item.cond<0)
            throw std::runtime_error("invalid native vendor item");
        item.stack=stack;
    }
    std::uint64_t guid=0;
    auto octet=[&](unsigned i){if(present[i])guid|=std::uint64_t(r.take<std::uint8_t>()^1)<<(8*i);};
    for(unsigned i:{5,4,1,0,6})octet(i);
    auto reason=r.take<std::uint8_t>();for(unsigned i:{2,3,7})octet(i);r.end();
    auto found=owner.visible_units.find(guid);
    if(found==owner.visible_units.end() || integer(get(found->second,"kind"))!=3 ||
        !(protocol.field(found->second,"UNIT_NPC_FLAGS")&128))return {};
    Writer w;w.guid(Protocol::modern_guid(guid,integer(get(found->second,"map"))))
        .pack("iI",{reason,count});
    for(auto const &item:items)
        w.pack("QI5i",{item.price,item.muid,item.type,item.stack,item.quantity,item.ext,item.cond})
            .bits(0,3).flush().pack("3i",{item.id,0,0}).bits(0,1).flush().bits(0,6).flush();
    return Packet{name,w.finish()};
}
} // namespace bridge
