#pragma once
#include "protocol.hpp"

namespace bridge
{
// Installed 60895 CurrencyTypes A0DA38E0: 392 is deprecated; 1901 is Honor.
inline std::uint32_t modern_currency(std::uint32_t id) { return id == 392 ? 1901 : id; }
inline std::uint32_t native_currency(std::uint32_t id) { return id == 1901 ? 392 : id; }
Reply currency_request(std::string const &name, View body);
}
