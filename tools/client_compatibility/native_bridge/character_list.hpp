#pragma once
#include "buffer.hpp"
#include <unordered_map>

namespace bridge
{
// Pure character-list serialization; database/account selection stays in Database.
Bytes character_list(Array const &characters, Array const &equipment,
                     std::unordered_map<unsigned, Array> const &item_displays, Array const &race_classes);
}
