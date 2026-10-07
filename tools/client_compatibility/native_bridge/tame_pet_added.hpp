#pragma once
#include "protocol.hpp"

namespace bridge
{
Reply tame_pet_added_response(Protocol const &protocol,State &owner,std::string const &name,View body);
Reply tame_pet_added_ready(Protocol const &protocol,State &owner);
}
