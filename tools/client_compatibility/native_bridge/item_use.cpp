// Pinned modern/native SpellPackets::UseItem, using authoritative inventory.
#include "protocol.hpp"

namespace bridge
{
Packet Protocol::item_use(State &owner,View body) const
{
    Reader r(body);
    auto pack=r.take<std::uint8_t>(),slot=r.take<std::uint8_t>();auto identity=r.guid();
    auto [bag,index]=inventory_position(pack,slot);
    if((bag==255 && index>=39) || (bag!=255 && (bag<19 || bag>22)))
        throw std::runtime_error("item use is outside carried inventory");
    auto low=integer(identity[0]);auto native=(0x4000ull<<48)|low;
    auto item=owner.inventory_items.find(native);
    if(!low || low>0xffffffff || identity!=inventory_guid(native) || item==owner.inventory_items.end() ||
       field(item->second,"ITEM_FIELD_OWNER")!=owner.guid() || field(item->second,"ITEM_FIELD_OWNER",1))
        throw std::runtime_error("used item is outside owned native inventory");
    auto pair=[&](Value const &snapshot,std::string_view field_name,unsigned slot)
    {return static_cast<std::uint64_t>(field(snapshot,field_name,slot*2)) |
            (static_cast<std::uint64_t>(field(snapshot,field_name,slot*2+1))<<32);};
    std::uint64_t actual=0;
    if(bag==255)actual=pair(owner.self_snapshot,"PLAYER_FIELD_INV_SLOT_HEAD",index);
    else
    {
        auto container=owner.inventory_items.find(pair(owner.self_snapshot,"PLAYER_FIELD_INV_SLOT_HEAD",bag));
        if(container==owner.inventory_items.end() || field(container->second,"ITEM_FIELD_OWNER")!=owner.guid() ||
           field(container->second,"ITEM_FIELD_OWNER",1) || index>=field(container->second,"CONTAINER_FIELD_NUM_SLOTS"))
            throw std::runtime_error("item use container is absent or does not belong to the player");
        actual=pair(container->second,"CONTAINER_FIELD_SLOT_1",index);
    }
    if(actual!=native)throw std::runtime_error("used item GUID does not match its native inventory position");
    auto cast=cast_request(owner,r.raw(r.remaining()));r.end();
    owner.casts.at(owner.cast_counter).as_object()["item_guid"]=native;
    // Legacy inserts the item GUID between CastID/SpellID and Misc/Flags/Target.
    return {"CMSG_USE_ITEM",Writer().pack("BB",{bag,index}).raw(View(cast.second).first(5)).put(native)
            .raw(View(cast.second).subspan(5)).finish()};
}
Bytes Protocol::item_use_rejected(View body)
{
    Reader r(body);r.raw(2);r.guid();return cast_rejected(r.raw(r.remaining()));
}
}
