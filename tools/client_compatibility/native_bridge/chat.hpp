#pragma once
#include "protocol.hpp"
namespace bridge
{
Reply chat_request(State const &owner,std::string const &name,View body);
Reply chat_response(State const &owner,std::string const &name,View body);
}
