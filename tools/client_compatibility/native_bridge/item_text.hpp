#pragma once
#include "protocol.hpp"

namespace bridge
{
struct ItemTextPage
{
    std::uint32_t id=0,next=0;
    std::string text;
};
struct ItemTextChain
{
    std::uint32_t root=0,expected=0;
    std::vector<ItemTextPage> pages;
};
struct ItemTextState
{
    std::deque<ItemTextChain> chains;
    std::unordered_set<std::uint64_t> reads;
};
Reply item_text_request(Protocol const &protocol,State &owner,std::string const &name,View body);
Reply item_text_response(Protocol const &protocol,State &owner,std::string const &name,View body);
}
