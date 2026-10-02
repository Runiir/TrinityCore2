// Pinned legacy/modern NPCPackets::VendorInventory, with native catalog authority.
#include "merchants.hpp"
#include <array>

namespace bridge
{
Reply merchant_request(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
    if(name!="CMSG_LIST_INVENTORY" && name!="CMSG_SELL_ITEM" && name!="CMSG_BUY_BACK_ITEM" && name!="CMSG_BUY_ITEM")return {};
    Reader r(body);auto guid=owned_unit(owner,r.guid());auto const &vendor=owner.visible_units.at(guid);
    if(integer(get(vendor,"kind"))!=3 || !(protocol.field(vendor,"UNIT_NPC_FLAGS")&128))
        throw std::runtime_error("vendor request requires a native visible merchant");
    Writer w;w.put(guid);
    if(name=="CMSG_BUY_ITEM")
    {
        auto container=r.guid();auto quantity=r.take<std::uint32_t>(),muid=r.take<std::uint32_t>();
        auto slot=r.take<std::uint8_t>();auto type=r.take<std::int32_t>();
        auto item=r.take<std::int32_t>(),seed=r.take<std::int32_t>(),property=r.take<std::int32_t>();
        auto bonuses=r.bits(1);r.align();auto modifiers=r.bits(6);r.align();r.end();
        if(!quantity || !muid || muid>0x7fffffff || item<=0 || (type!=1 && type!=2) || seed || property || bonuses || modifiers)
            throw std::runtime_error("purchase has no supported native plain-item equivalent");
        std::uint64_t bag=0;std::uint8_t destination=255;
        if(container==Array{owner.guid(),player_high()})
        {
            bag=owner.guid();
            if(slot!=255)destination=Protocol::inventory_position(255,slot).second;
        }
        else if(container!=Array{0,0})
        {
            auto low=integer(container[0]);bag=(0x4000ull<<48)|low;
            auto found=owner.inventory_items.find(bag);
            if(!low || low>0xffffffff || integer(container[1])!=((3ull<<58)|(1ull<<42)) ||
                found==owner.inventory_items.end() || integer(get(found->second,"kind"))!=2 ||
                protocol.field(found->second,"ITEM_FIELD_OWNER")!=owner.guid() || protocol.field(found->second,"ITEM_FIELD_OWNER",1) ||
                (slot!=255 && slot>=36))throw std::runtime_error("purchase container is outside owned native bags");
            destination=slot;
        }
        else if(slot!=255)throw std::runtime_error("automatic purchase has an explicit unsupported slot");
        return Packet{name,w.pack("BIIIQB",{type,item,muid,quantity,bag,destination}).finish()};
    }
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
    if(name=="SMSG_BUY_ITEM" || name=="SMSG_BUY_FAILED")
    {
        Reader r(body);auto vendor=r.take<std::uint64_t>();auto muid=r.take<std::uint32_t>();
        Array identity{0,0};
        if(vendor)
        {
            auto found=owner.visible_units.find(vendor);
            if(found==owner.visible_units.end() || integer(get(found->second,"kind"))!=3)return {};
            identity=Protocol::modern_guid(vendor,integer(get(found->second,"map")));
        }
        Writer w;w.guid(identity).put(muid);
        if(name=="SMSG_BUY_ITEM")
        {
            auto available=r.take<std::int32_t>();auto quantity=r.take<std::uint32_t>();r.end();
            if(!vendor || !muid || available < -1 || !quantity)throw std::runtime_error("invalid native purchase success");
            return Packet{"SMSG_BUY_SUCCEEDED",w.put(available).put(quantity).finish()};
        }
        auto reason=r.take<std::uint8_t>();r.end();
        if(reason!=0 && reason!=1 && reason!=2 && reason!=4 && reason!=5 && reason!=7 && reason!=8 && reason!=11 && reason!=12)
            throw std::runtime_error("unmapped native purchase result");
        // Both pinned SendBuyError implementations put the item ID in Muid.
        return Packet{name,w.put<std::int32_t>(reason).finish()};
    }
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
