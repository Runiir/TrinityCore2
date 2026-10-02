// Native Player::SendNewItem -> pinned 60895 ItemPackets::ItemPushResult.
#include "item_notifications.hpp"

namespace bridge
{
Reply item_notification(std::string const &name,View body)
{
    if(name!="SMSG_ITEM_PUSH_RESULT")return {};
    Reader r(body);auto player=r.take<std::uint64_t>();
    auto pushed=r.take<std::uint32_t>(),created=r.take<std::uint32_t>(),chat=r.take<std::uint32_t>();
    auto bag=r.take<std::uint8_t>();auto slot=r.take<std::uint32_t>();
    auto id=r.take<std::uint32_t>(),seed=r.take<std::uint32_t>();auto property=r.take<std::int32_t>();
    auto quantity=r.take<std::uint32_t>(),total=r.take<std::uint32_t>();r.end();
    if(!player || player>0xffffffff || pushed>1 || created>1 || chat>1 || !id || id>0x7fffffff ||
        !quantity || quantity>0x7fffffff || total>0x7fffffff || total<quantity)
        throw std::runtime_error("invalid native item notification");
    std::int32_t destination=-1;
    if(bag==255)
    {
        if(slot!=0xffffffff)
        {
            if(slot>=86)throw std::runtime_error("notification root slot has no modern inventory equivalent");
            destination=slot<19?slot:slot<23?slot+11:slot<39?slot+12:slot+20;
        }
    }
    else
    {
        if(bag>=19 && bag<23)bag+=11;
        else if(bag>=67 && bag<74)bag+=20;
        else throw std::runtime_error("notification container has no modern inventory equivalent");
        if(slot!=0xffffffff)
        {
            if(slot>=36)throw std::runtime_error("notification item exceeds the native bag bound");
            destination=slot;
        }
    }
    Writer w;w.guid({player,player_high()}).put(bag)
        .pack("7iBi",{destination,0,quantity,total,0,0,0,0,0});
    // Legacy notifications do not carry an item GUID and can precede its create.
    // Preserve that absence rather than guessing an identity from an item ID.
    w.guid({0,0}).bits(pushed,1).bits(created,1).bits(0,1).bits(chat?1:0,3)
        .bits(0,1).bits(0,1).flush().put<std::int32_t>(id).put(seed).put(property)
        .bits(0,1).flush().bits(0,6).flush();
    return Packet{name,w.finish()};
}
}
