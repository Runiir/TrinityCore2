#pragma once
#include "protocol.hpp"

namespace bridge
{
std::int32_t watched_faction_index(Protocol const &protocol,Value const &snapshot);
Bytes watched_faction_block(Protocol const &protocol,Value const &snapshot,Value const &changed);
}
