#pragma once
#include "protocol.hpp"

namespace bridge
{
Reply auction_request(Protocol const &protocol,State const &owner,std::string const &name,View body);
Reply auction_response(Protocol const &protocol,State const &owner,std::string const &name,View body);
}
