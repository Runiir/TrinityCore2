#pragma once
#include "protocol.hpp"

namespace bridge
{
inline std::uint64_t visible_player(State const &owner, Array const &identity)
{
    auto guid=integer(identity[0]);
    if(!guid || guid>0xffffffff || integer(identity[1])!=player_high())
        throw std::runtime_error("invalid public player request identity");
    auto peer=owner.visible_units.find(guid);
    if(peer==owner.visible_units.end() || integer(get(peer->second,"kind"))!=4 || guid==owner.guid())return 0;
    return guid;
}
} // namespace bridge
