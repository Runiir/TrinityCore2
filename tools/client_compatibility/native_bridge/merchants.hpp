#pragma once
#include "protocol.hpp"

namespace bridge
{
Reply merchant_request(State const &owner,std::string const &name,View body);
Reply merchant_response(Protocol const &protocol,State const &owner,std::string const &name,View body);
}
