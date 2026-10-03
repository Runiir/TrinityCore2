// Native AuctionHouseHandler::SendAuctionHello and pinned 4.4.2 AuctionHelloResponse.
#include "auctions.hpp"

namespace bridge
{
namespace
{
bool auctioneer(Protocol const &protocol,Value const &unit)
{
    return integer(get(unit,"kind"))==3 && (protocol.field(unit,"UNIT_NPC_FLAGS")&2097152);
}
}
Reply auction_request(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
    if(name!="CMSG_AUCTION_HELLO_REQUEST")return {};
    Reader r(body);auto guid=owned_unit(owner,r.guid());r.end();
    if(!auctioneer(protocol,owner.visible_units.at(guid)))
        throw std::runtime_error("auction request requires a visible native auctioneer");
    return Packet{"MSG_AUCTION_HELLO",Writer().put(guid).finish()};
}
Reply auction_response(Protocol const &protocol,State const &owner,std::string const &name,View body)
{
    if(name!="MSG_AUCTION_HELLO")return {};
    Reader r(body);auto guid=r.take<std::uint64_t>();auto house=r.take<std::uint32_t>();
    auto enabled=r.take<std::uint8_t>();r.end();
    if(!house || house>0x7fffffff || enabled>1)throw std::runtime_error("invalid native auction opening");
    auto found=owner.visible_units.find(guid);
    if(found==owner.visible_units.end() || !auctioneer(protocol,found->second))return {};
    // Native won-item and cancellation mail are immediate. Delayed seller
    // proceeds are a separate auction notification, not either opening delay.
    return Packet{"SMSG_AUCTION_HELLO_RESPONSE",Writer()
        .guid(Protocol::modern_guid(guid,integer(get(found->second,"map"))))
        .pack("IIi",{0,0,house}).bits(enabled,1).finish()};
}
}
