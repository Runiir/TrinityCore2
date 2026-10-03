// Native handlers remain authoritative for auction mutations and outcomes.
#include "auctions.hpp"

namespace bridge
{
Reply auction_transaction(Protocol const &p,State const &s,std::string const &name,View body,AuctionItems const &items)
{
    if(name!="CMSG_AUCTION_SELL_ITEM" && name!="CMSG_AUCTION_REMOVE_ITEM" && name!="CMSG_AUCTION_PLACE_BID")return {};
    Reader r(body);auto target=owned_unit(s,r.guid());
    auto const &unit=s.visible_units.at(target);
    if(target!=s.auction_target || integer(get(unit,"kind"))!=3 || !(p.field(unit,"UNIT_NPC_FLAGS")&2097152))
        throw std::runtime_error("auction transaction requires native opening authority");
    Writer w;w.put(target);
    if(name=="CMSG_AUCTION_SELL_ITEM")
    {
        auto minimum=r.take<std::int64_t>(),buyout=r.take<std::int64_t>();auto duration=r.take<std::int32_t>();
        auto tainted=r.bits(1),count=r.bits(6);r.align();
        if(tainted)return {}; // Optional addon metadata has no native equivalent.
        std::uint64_t item=0;bool supported=count==1;
        for(unsigned i=0;i<count;++i)
        {
            auto identity=r.guid();auto amount=r.take<std::uint32_t>();auto low=integer(identity[0]);
            auto guid=(0x4000ull<<48)|low;auto found=s.inventory_items.find(guid);
            if(!low || low>0xffffffff || integer(identity[1])!=((3ull<<58)|(1ull<<42)) ||
               found==s.inventory_items.end() || p.field(found->second,"ITEM_FIELD_OWNER")!=s.guid() ||
               p.field(found->second,"ITEM_FIELD_OWNER",1))throw std::runtime_error("auction item is outside owned inventory");
            auto entry=p.field(found->second,"OBJECT_FIELD_ENTRY");auto metadata=items.find(entry);
            supported&=amount==1 && p.field(found->second,"ITEM_FIELD_STACK_COUNT")==1 &&
                metadata!=items.end() && integer(get(metadata->second,"stackable"))==1;
            item=guid;
        }
        r.end();
        if(minimum<0 || buyout<0 || (!minimum && !buyout) ||
            (duration!=720 && duration!=1440 && duration!=2880))throw std::runtime_error("invalid auction sale price or duration");
        if(!supported)return {};
        // Legacy cannot represent a zero minimum. A minimum equal to buyout
        // permits only a buyout and is rendered without a bidding price.
        auto native_minimum=minimum?minimum:buyout;
        return Packet{name,w.put<std::uint32_t>(1).put(item).put<std::uint32_t>(1)
            .put<std::uint64_t>(native_minimum).put<std::uint64_t>(buyout).put<std::uint32_t>(duration).finish()};
    }
    auto id=r.take<std::uint32_t>();
    if(!id || id>0x7fffffff)throw std::runtime_error("invalid auction transaction ID");
    if(name=="CMSG_AUCTION_REMOVE_ITEM")
    {
        auto entry=r.take<std::uint32_t>();auto tainted=r.bits(1);r.end();
        if(!entry || entry>0x7fffffff)throw std::runtime_error("invalid auction removal item ID");
        if(tainted)return {};
        // Native verifies the actual auction owner and item; no DB mutation.
        return Packet{name,w.put(id).finish()};
    }
    auto amount=r.take<std::uint64_t>();auto tainted=r.bits(1);r.end();
    if(!amount)throw std::runtime_error("invalid auction bid amount");
    if(tainted)return {};
    return Packet{name,w.put(id).put(amount).finish()};
}

Reply auction_command_result(Protocol const &p,std::string const &name,View body)
{
    if(name!="SMSG_AUCTION_COMMAND_RESULT")return {};
    Reader r(body);auto id=r.take<std::uint32_t>(),command=r.take<std::uint32_t>(),error=r.take<std::uint32_t>();
    if(id>0x7fffffff || command>2 || !(error<=5 || error==7 || error==10 || error==13))
        throw std::runtime_error("unsupported native auction command result");
    Value bag=0;std::uint64_t bidder=0,money=0,increment=0;
    if(error==0 && command==2)increment=r.take<std::uint64_t>();
    else if(error==1)
    {
        auto native=r.take<std::uint32_t>();auto mapped=p.inventory_results.as_object().if_contains(std::to_string(native));
        if(!mapped)throw std::runtime_error("unmapped native auction inventory result");
        bag=*mapped;
    }
    else if(error==5)
    {
        bidder=r.take<std::uint64_t>();money=r.take<std::uint64_t>();increment=r.take<std::uint64_t>();
        if(bidder>0xffffffff)throw std::runtime_error("invalid native auction bidder identity");
    }
    r.end();
    return Packet{name,Writer().pack("4I",{id,command,error,bag}).guid(bidder,bidder?player_high():0)
        .pack("QQI",{increment,money,0}).finish()};
}
}
