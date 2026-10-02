// Pinned 60895 RepairItem::Read -> native NPCHandler::HandleRepairItemOpcode.
#include "repairs.hpp"

namespace bridge
{
Reply repair_request(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
    if(name!="CMSG_REPAIR_ITEM")return {};
    Reader r(body);auto npc=owned_unit(owner,r.guid());auto const &unit=owner.visible_units.at(npc);
    if(integer(get(unit,"kind"))!=3 || !(protocol.field(unit,"UNIT_NPC_FLAGS")&4096))
        throw std::runtime_error("repair requires a native visible repair service");
    auto identity=r.guid();auto guild=r.bits(1);r.align();r.end();
    std::uint64_t item=0;
    if(identity!=Array{0,0})
    {
        auto low=integer(identity[0]);item=(0x4000ull<<48)|low;
        auto found=owner.inventory_items.find(item);
        if(!low || low>0xffffffff || integer(identity[1])!=((3ull<<58)|(1ull<<42)) ||
            found==owner.inventory_items.end() || protocol.field(found->second,"ITEM_FIELD_OWNER")!=owner.guid() ||
            protocol.field(found->second,"ITEM_FIELD_OWNER",1))
            throw std::runtime_error("repair item is outside native owned inventory");
    }
    // Native authority validates price, distance, durability and guild permission.
    return Packet{name,Writer().pack("QQB",{npc,item,guild}).finish()};
}
}
