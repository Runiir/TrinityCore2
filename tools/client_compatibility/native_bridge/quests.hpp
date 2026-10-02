#pragma once
#include "protocol.hpp"

namespace bridge
{
Reply quest_query_response(std::string const &name,View body);
Reply quest_request(Protocol const &protocol,State const &owner,std::string const &name,View body);
Reply quest_response(Protocol const &protocol,State const &owner,std::string const &name,View body);
}
