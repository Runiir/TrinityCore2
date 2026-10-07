#pragma once
#include "protocol.hpp"

namespace bridge
{
Value native_stable_list(View body);
Reply stable_request(Protocol const &protocol, State const &owner, std::string const &name, View body);
Reply stable_response(Protocol const &protocol, State &owner, std::string const &name, View body,
                      Array const &models);
}
