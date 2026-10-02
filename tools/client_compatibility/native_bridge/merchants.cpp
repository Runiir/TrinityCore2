// Pinned legacy/modern NPCPackets::VendorInventory, with native catalog authority.
#include "merchants.hpp"
#include <array>

namespace bridge
{
Reply merchant_request(State const &owner,std::string const &name,View body)
{
    if(name!="CMSG_LIST_INVENTORY")return {};
    Reader r(body);auto guid=owned_unit(owner,r.guid());r.end();
    if(integer(get(owner.visible_units.at(guid),"kind"))!=3)
        throw std::runtime_error("vendor request requires a visible creature");
    return Packet{name,Writer().put(guid).finish()};
}
Reply merchant_response(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
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
