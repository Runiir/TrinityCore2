// Pinned ItemPackets::{Read} / InvUpdate and native ItemHandler contracts.
#include "protocol.hpp"

namespace bridge
{
namespace
{
std::uint8_t slot(std::uint8_t modern)
{
    if(modern<19)return modern;
    if(modern>=30 && modern<34)return modern-11;
    if(modern>=35 && modern<51)return modern-12;
    if(modern>=59 && modern<106)return modern-20;
    throw std::runtime_error("inventory slot has no native equivalent");
}
std::uint8_t bag(std::uint8_t modern)
{
    if(modern==255)return modern;
    if((modern>=30 && modern<34) || (modern>=87 && modern<94))return slot(modern);
    throw std::runtime_error("container slot has no native bag equivalent");
}
std::pair<std::uint8_t,std::uint8_t> position(std::uint8_t pack,std::uint8_t index)
{
    auto container=bag(pack);
    if(pack==255)return {container,slot(index)};
    if(index>=36)throw std::runtime_error("bag item slot exceeds native bound");
    return {container,index};
}
void inv(Reader &r)
{
    auto count=r.bits(2);r.align();
    // The optional optimistic UI hint has no legacy equivalent. Native handlers
    // validate the actual move against their authoritative owned inventory.
    for(unsigned i=0;i<count;++i){auto pack=r.take<std::uint8_t>(),index=r.take<std::uint8_t>();position(pack,index);}
}
}
std::pair<std::uint8_t,std::uint8_t> Protocol::inventory_position(std::uint8_t bag,std::uint8_t slot)
{
    return position(bag,slot);
}
Reply Protocol::inventory_request(State const &owner,std::string const &name,View body)
{
    Reader r(body);Writer w;
    if(name=="CMSG_AUTOBANK_ITEM" || name=="CMSG_AUTOSTORE_BANK_ITEM")
    {
        inv(r);
        if(name=="CMSG_AUTOBANK_ITEM" && r.take<std::int8_t>()!=0)
            throw std::runtime_error("only native character banking is supported");
        auto pack=r.take<std::uint8_t>(),index=r.take<std::uint8_t>();r.end();
        auto [b,s]=position(pack,index);
        if(!owner.bank_target || !owner.visible_units.contains(owner.bank_target))
            throw std::runtime_error("bank move without a native visible banker grant");
        return Packet{name,w.pack("2B",{b,s}).finish()};
    }
    if(name=="CMSG_SWAP_INV_ITEM")
    {
        inv(r);auto dst=slot(r.take<std::uint8_t>()),src=slot(r.take<std::uint8_t>());r.end();
        return Packet{name,w.pack("2B",{dst,src}).finish()};
    }
    if(name=="CMSG_SWAP_ITEM")
    {
        inv(r);auto dst=r.take<std::uint8_t>(),src=r.take<std::uint8_t>();
        auto dstslot=r.take<std::uint8_t>(),srcslot=r.take<std::uint8_t>();r.end();
        auto [db,ds]=position(dst,dstslot);auto [sb,ss]=position(src,srcslot);
        return Packet{name,w.pack("4B",{db,ds,sb,ss}).finish()};
    }
    if(name=="CMSG_SPLIT_ITEM")
    {
        inv(r);auto src=r.take<std::uint8_t>(),srcslot=r.take<std::uint8_t>();
        auto dst=r.take<std::uint8_t>(),dstslot=r.take<std::uint8_t>();auto count=r.take<std::int32_t>();r.end();
        if(count<=0)throw std::runtime_error("invalid split quantity");
        auto [sb,ss]=position(src,srcslot);auto [db,ds]=position(dst,dstslot);
        return Packet{name,w.pack("4BI",{sb,ss,db,ds,count}).finish()};
    }
    if(name=="CMSG_AUTO_EQUIP_ITEM")
    {
        inv(r);auto pack=r.take<std::uint8_t>(),index=r.take<std::uint8_t>();r.end();
        auto [b,s]=position(pack,index);
        return Packet{"CMSG_AUTOEQUIP_ITEM",w.pack("2B",{b,s}).finish()};
    }
    if(name=="CMSG_AUTO_STORE_BAG_ITEM")
    {
        inv(r);auto dst=bag(r.take<std::uint8_t>()),src=r.take<std::uint8_t>(),index=r.take<std::uint8_t>();r.end();
        auto [b,s]=position(src,index);
        return Packet{"CMSG_AUTOSTORE_BAG_ITEM",w.pack("3B",{b,s,dst}).finish()};
    }
    if(name=="CMSG_AUTO_EQUIP_ITEM_SLOT")
    {
        inv(r);auto identity=r.guid();auto dst=slot(r.take<std::uint8_t>());r.end();
        auto low=integer(identity[0]);auto native_guid=(0x4000ull<<48)|low;
        if(!low || low>0xffffffff || integer(identity[1])!=((3ull<<58)|(1ull<<42)) || !owner.inventory_items.contains(native_guid))
            throw std::runtime_error("auto-equipped item is outside owned native inventory");
        return Packet{"CMSG_AUTOEQUIP_ITEM_SLOT",w.put(native_guid).put(dst).finish()};
    }
    return {};
}
Reply Protocol::inventory_response(std::string const &name,View body) const
{
    if(name!="SMSG_INVENTORY_CHANGE_FAILURE")return {};
    Reader r(body);auto result=r.take<std::uint8_t>();Writer w;
    auto target=inventory_results.as_object().if_contains(std::to_string(result));
    if(!target)throw std::runtime_error("unmapped native inventory result");
    w.pack("i",{*target});
    if(result==0){r.end();return Packet{name,w.guid().guid().put<std::uint8_t>(0).finish()};}
    auto first=r.take<std::uint64_t>(),second=r.take<std::uint64_t>();auto subclass=r.take<std::uint8_t>();
    w.guid(inventory_guid(first)).guid(inventory_guid(second)).put(subclass);
    if(result==1 || result==87 || result==84 || result==85 || result==89)w.put(r.take<std::uint32_t>());
    else if(result==81)
    {w.guid(inventory_guid(r.take<std::uint64_t>())).put(r.take<std::uint32_t>()).guid(inventory_guid(r.take<std::uint64_t>()));}
    r.end();return Packet{name,w.finish()};
}
}
