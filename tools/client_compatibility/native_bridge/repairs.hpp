#pragma once
#include "protocol.hpp"

namespace bridge
{
Reply repair_request(Protocol const &protocol,State const &owner,std::string const &name,View body);
}
