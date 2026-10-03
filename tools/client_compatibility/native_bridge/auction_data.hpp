#pragma once
#include "database.hpp"
#include <unordered_map>

namespace bridge
{
using AuctionItems=std::unordered_map<unsigned,Value>;
AuctionItems auction_sparse(View data);
AuctionItems load_auction_items(std::filesystem::path const &root);
}
