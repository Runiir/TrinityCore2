#pragma once
#include "database.hpp"
#include "protocol.hpp"
#include "auction_data.hpp"

namespace bridge
{
struct PublicData
{
    std::unordered_map<unsigned, Array> item_displays, npc_broadcasts;
    std::unordered_map<unsigned, Bytes> broadcasts;
    Array taxi_paths, hotfixes, factions;
    AuctionItems auction_items;
    PublicData(std::filesystem::path const &root, std::filesystem::path const &repo);
    Bytes available() const;
    Bytes hotfix_request(View body) const;
    std::vector<Packet> bulk_query(View body) const;
    Bytes enumeration(Array const &characters, Array const &equipment) const;
};
Bytes auth_success();
std::vector<Packet> bootstrap_packets(PublicData const &data);
} // namespace bridge
