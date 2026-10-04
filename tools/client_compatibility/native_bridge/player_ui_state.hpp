#pragma once
#include "protocol.hpp"

namespace bridge
{
std::optional<Packet> actionbar_toggle_request(View body, bool in_world);
Packet stand_state_request(View body, bool in_world);
Packet stand_state_update(View body);
}
