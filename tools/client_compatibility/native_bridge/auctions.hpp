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
NativeAuctionRow read_auction_item(Reader &r,AuctionItems const &items={});
Reply auction_request(Protocol const &protocol,State &owner,std::string const &name,View body,AuctionItems const &items={});
Reply auction_response(Protocol const &protocol,State &owner,std::string const &name,View body,AuctionItems const &items={});
Reply auction_catalog(Protocol const &protocol,State const &owner,std::string const &name,View body,AuctionItems const &items={});
Reply auction_browse_request(Protocol const &protocol,State &owner,std::string const &name,View body);
Reply auction_browse_response(Protocol const &protocol,State &owner,std::string const &name,View body,AuctionItems const &items);
Reply auction_item_request(Protocol const &protocol,State &owner,std::string const &name,View body,AuctionItems const &items);
Reply auction_item_result(State &owner,AuctionItems const &items,unsigned delay);
Reply auction_transaction(Protocol const &protocol,State const &owner,std::string const &name,View body,AuctionItems const &items);
Reply auction_command_result(Protocol const &protocol,std::string const &name,View body);
}
