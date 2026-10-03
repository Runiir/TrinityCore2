#pragma once
#include "protocol.hpp"

namespace bridge
{
Reply appearance_request(std::string const &name, View body);
void appearance_fields(std::uint32_t native_flags, Object &player);
}
