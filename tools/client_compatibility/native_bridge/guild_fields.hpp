#pragma once
#include "protocol.hpp"

namespace bridge
{
constexpr std::uint64_t guild_high() { return (28ull<<58)|(1ull<<42); }
Array guild_identity(std::uint64_t native);
void guild_fields(Protocol const &protocol,Value const &snapshot,Object &unit,Object &player);
}
