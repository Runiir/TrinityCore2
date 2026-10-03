#pragma once
#include "protocol.hpp"
namespace bridge
{
Reply talent_response(std::string const &name,View body);
Reply talent_request(std::string const &name,View body);
}
