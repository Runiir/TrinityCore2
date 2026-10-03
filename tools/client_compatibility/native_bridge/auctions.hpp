#pragma once
#include "protocol.hpp"
#include "auction_data.hpp"

namespace bridge
{
struct NativeAuctionRow
{
    unsigned id,entry,count;
    std::uint64_t owner,minimum,increment,buyout,bid;
    std::int32_t property;
    Bytes encoded;
};
NativeAuctionRow read_auction_item(Reader &r);
Reply auction_request(Protocol const &protocol,State &owner,std::string const &name,View body);
Reply auction_response(Protocol const &protocol,State &owner,std::string const &name,View body,AuctionItems const &items={});
Reply auction_catalog(Protocol const &protocol,State const &owner,std::string const &name,View body);
Reply auction_browse_request(Protocol const &protocol,State &owner,std::string const &name,View body);
Reply auction_browse_response(Protocol const &protocol,State &owner,std::string const &name,View body,AuctionItems const &items);
}
