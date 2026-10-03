// Native AuctionEntry::BuildAuctionInfo and the pinned 60895 AuctionItem layout.
#include "auctions.hpp"
#include <unordered_map>

namespace bridge
{
NativeAuctionRow read_auction_item(Reader &r,AuctionItems const &items)
{
    auto id=r.take<std::uint32_t>(),entry=r.take<std::uint32_t>();std::vector<Array> enchants;
    for(unsigned slot=0;slot<10;++slot)
    {
        auto values=r.unpack("3I");
        if(truth(values[0]))enchants.push_back(Array{values[0],values[1],values[2],slot});
        else if(truth(values[1]) || truth(values[2]))throw std::runtime_error("native auction enchant metadata without enchant");
    }
    auto property=r.take<std::int32_t>();auto seed=r.take<std::uint32_t>(),count=r.take<std::uint32_t>();
    auto charges=r.take<std::int32_t>();auto flags=r.take<std::uint32_t>();auto owner=r.take<std::uint64_t>();
    auto minimum=r.take<std::uint64_t>(),increment=r.take<std::uint64_t>(),buyout=r.take<std::uint64_t>();
    auto duration=r.take<std::int32_t>();auto bidder=r.take<std::uint64_t>(),bid=r.take<std::uint64_t>();
    if(!id || id>0x7fffffff || !entry || entry>0x7fffffff || !count || count>0x7fffffff ||
       flags || owner>0xffffffff || bidder>0xffffffff || (bidder==0)!=(bid==0))
        throw std::runtime_error("invalid native auction row");
    auto metadata=items.find(entry);bool key=metadata!=items.end() && !property;
    auto level=key?integer(get(metadata->second,"level")):0;
    if(key && (entry>0xfffff || level>2047))throw std::runtime_error("native auction bucket key exceeds modern bounds");
    bool can_bid=minimum && (!buyout || minimum<buyout);
    Writer w;w.bits(1,1).bits(enchants.size(),4).bits(0,2).bits(can_bid,1).bits(can_bid && increment,1)
        .bits(buyout!=0,1).bits(0,1).bits(1,1).bits(0,1).bits(key,1).bits(0,1)
        .bits(bidder!=0,1).bits(bid!=0,1).flush();
    // Native socket enchant IDs lack underlying gem item IDs. Preserve native
    // enchant data; gem instances and unavailable server-only identities stay absent.
    w.pack("iIi",{entry,seed,property}).bits(0,1).flush().bits(0,6).flush();
    w.pack("iiiI",{count,charges,flags,id}).guid(owner,owner?player_high():0).put(duration)
        .put<std::uint8_t>(0).put<std::uint32_t>(0);
    for(auto const &enchant:enchants)w.pack("3IB",enchant);
    if(can_bid)w.put(minimum);
    if(can_bid && increment)w.put(increment);
    if(buyout)w.put(buyout);
    if(bidder)w.guid(bidder,player_high());
    if(bid)w.put(bid);
    if(key)w.bits(entry,20).bits(0,1).bits(level,11).bits(0,1).flush();
    return {id,entry,count,owner,minimum,increment,buyout,bid,property,w.finish()};
}
Reply auction_catalog(Protocol const &protocol,State const &owner,std::string const &name,View body,AuctionItems const &items)
{
    if(name!="SMSG_AUCTION_BIDDER_LIST_RESULT" && name!="SMSG_AUCTION_OWNER_LIST_RESULT")return {};
    auto found=owner.visible_units.find(owner.auction_target);
    if(!owner.auction_target || found==owner.visible_units.end() || integer(get(found->second,"kind"))!=3 ||
       !(protocol.field(found->second,"UNIT_NPC_FLAGS")&2097152))return {};
    Reader r(body);auto count=r.take<std::uint32_t>();
    if(count>4096 || r.remaining()<8 || count>(r.remaining()-8)/200)throw std::runtime_error("native auction catalog exceeds body bounds");
    std::vector<Bytes> rows;std::unordered_map<unsigned,Bytes> seen;
    for(unsigned i=0;i<count;++i)
    {
        auto parsed=read_auction_item(r,items);auto id=parsed.id;auto row=std::move(parsed.encoded);auto found=seen.find(id);
        if(found!=seen.end())
        {
            // Native bidder reads append requested IDs and then all current
            // bids, so the same auction can legitimately appear twice.
            if(found->second!=row)throw std::runtime_error("conflicting duplicate native auction row");
            continue;
        }
        seen.emplace(id,row);rows.push_back(std::move(row));
    }
    auto total=r.take<std::uint32_t>(),delay=r.take<std::uint32_t>();r.end();
    if(total<count || total>0x7fffffff)throw std::runtime_error("invalid native auction catalog total");
    Writer w;w.put<std::uint32_t>(rows.size());
    if(name=="SMSG_AUCTION_OWNER_LIST_RESULT")w.put<std::uint32_t>(0); // Native pending-sale mail is separate.
    w.put(delay).bits(total>count,1).flush();for(auto const &row:rows)w.raw(row);
    return Packet{name=="SMSG_AUCTION_BIDDER_LIST_RESULT"?"SMSG_AUCTION_LIST_BIDDED_ITEMS_RESULT":"SMSG_AUCTION_LIST_OWNED_ITEMS_RESULT",w.finish()};
}
}
