// Native AuctionHouseHandler::SendAuctionHello and pinned 4.4.2 AuctionHelloResponse.
#include "auctions.hpp"
#include <algorithm>

namespace bridge
{
namespace
{
bool auctioneer(Protocol const &protocol,Value const &unit)
{
    return integer(get(unit,"kind"))==3 && (protocol.field(unit,"UNIT_NPC_FLAGS")&2097152);
}
}
Reply auction_request(Protocol const &protocol,State &owner,std::string const &name,View body)
{
    if(name=="CMSG_AUCTION_BROWSE_QUERY")return auction_browse_request(protocol,owner,name,body);
    if(name!="CMSG_AUCTION_HELLO_REQUEST" && name!="CMSG_AUCTION_LIST_BIDDED_ITEMS" &&
       name!="CMSG_AUCTION_LIST_OWNED_ITEMS")return {};
    Reader r(body);auto guid=owned_unit(owner,r.guid());
    if(!auctioneer(protocol,owner.visible_units.at(guid)))
        throw std::runtime_error("auction request requires a visible native auctioneer");
    if(name=="CMSG_AUCTION_HELLO_REQUEST")
    {r.end();return Packet{"MSG_AUCTION_HELLO",Writer().put(guid).finish()};}
    if(guid!=owner.auction_target)throw std::runtime_error("auction catalog requires native opening authority");
    auto offset=r.take<std::uint32_t>();auto tainted=r.bits(1);
    auto count=name=="CMSG_AUCTION_LIST_BIDDED_ITEMS"?r.bits(7):0;
    auto sorts=r.bits(2);r.align();
    if(tainted)throw std::runtime_error("tainted auction catalog metadata is not yet translated");
    std::vector<std::uint32_t> ids;
    for(unsigned i=0;i<count;++i)
    {
        auto id=r.take<std::uint32_t>();
        if(!id || std::find(ids.begin(),ids.end(),id)!=ids.end())throw std::runtime_error("invalid auction catalog ID");
        ids.push_back(id);
    }
    for(unsigned i=0;i<sorts;++i)
    {r.align();r.take<std::uint8_t>();r.bits(1);}
    r.end();Writer w;w.put(guid).put(offset);
    if(name=="CMSG_AUCTION_LIST_BIDDED_ITEMS")
    {w.put<std::uint32_t>(ids.size());for(auto id:ids)w.put(id);}
    // Native catalogs do not sort or paginate these two lists. Row ordering
    // remains a separate qualification; all native rows are retained.
    return Packet{name=="CMSG_AUCTION_LIST_BIDDED_ITEMS"?"CMSG_AUCTION_LIST_BIDDER_ITEMS":"CMSG_AUCTION_LIST_OWNER_ITEMS",w.finish()};
}
Reply auction_response(Protocol const &protocol,State &owner,std::string const &name,View body,AuctionItems const &items)
{
    if(name=="SMSG_AUCTION_LIST_RESULT")return auction_browse_response(protocol,owner,name,body,items);
    if(name!="MSG_AUCTION_HELLO")return auction_catalog(protocol,owner,name,body);
    Reader r(body);auto guid=r.take<std::uint64_t>();auto house=r.take<std::uint32_t>();
    auto enabled=r.take<std::uint8_t>();r.end();
    if(!house || house>0x7fffffff || enabled>1)throw std::runtime_error("invalid native auction opening");
    auto found=owner.visible_units.find(guid);
    if(found==owner.visible_units.end() || !auctioneer(protocol,found->second))return {};
    owner.auction_target=enabled?guid:0;
    owner.auction_browse=nullptr;
    // Native won-item and cancellation mail are immediate. Delayed seller
    // proceeds are a separate auction notification, not either opening delay.
    return Packet{"SMSG_AUCTION_HELLO_RESPONSE",Writer()
        .guid(Protocol::modern_guid(guid,integer(get(found->second,"map"))))
        .pack("IIi",{0,0,house}).bits(enabled,1).finish()};
}
}
