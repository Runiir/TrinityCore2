#pragma once
#include "protocol.hpp"

namespace bridge
{
Reply pet_request(Protocol const &protocol, State &owner, std::string const &name, View body);
struct PetActionTranslation
{
    Reply packet;
    std::string rejection;
};
PetActionTranslation translate_pet_action(Protocol const &protocol, State &owner, View body);
Reply pet_response(Protocol const &protocol, State &owner, std::string const &name, View body);
Reply pet_ready(Protocol const &protocol, State &owner);
void pet_removed(State &owner, std::uint64_t guid);
}
