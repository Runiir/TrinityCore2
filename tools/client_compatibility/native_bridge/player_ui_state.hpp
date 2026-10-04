#pragma once
#include "protocol.hpp"

namespace bridge
{
std::optional<Packet> actionbar_toggle_request(View body, bool in_world);
}
