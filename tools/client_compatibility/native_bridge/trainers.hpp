#pragma once
#include "protocol.hpp"

namespace bridge
{
Reply trainer_request(Protocol const &protocol,State const &owner,std::string const &name,View body);
Reply trainer_response(Protocol const &protocol,State const &owner,std::string const &name,View body);
}
