#pragma once
#include "protocol.hpp"
namespace bridge
{
Reply chat_channel_request(State &owner,std::string const &name,View body);
Reply chat_channel_response(State &owner,std::string const &name,View body);
bool public_channel_probe(std::string const &name,View body);
}
