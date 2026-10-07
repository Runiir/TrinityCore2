#pragma once
#include "protocol.hpp"

namespace bridge
{
Reply pet_request(Protocol const &protocol, State &owner, std::string const &name, View body);
Reply pet_aura_cancel(Protocol const &protocol, State &owner, View body);
struct PetActionTranslation
{
    Reply packet;
    std::string rejection;
};
PetActionTranslation translate_pet_action(Protocol const &protocol, State &owner, View body);
PetActionTranslation translate_pet_set_action(Protocol const &protocol, State &owner, View body);
PetActionTranslation translate_pet_rename(Protocol const &protocol, State &owner, View body);
PetActionTranslation translate_pet_abandon(Protocol const &protocol, State &owner, View body);
Reply pet_response(Protocol const &protocol, State &owner, std::string const &name, View body);
Reply pet_ready(Protocol const &protocol, State &owner);
void pet_removed(State &owner, std::uint64_t guid);
bool pet_cast_authority(Protocol const &protocol,State const &owner,std::uint64_t guid,unsigned spell);
bool pet_rename_authority(Protocol const &protocol,State const &owner,std::uint64_t guid,unsigned number);
bool pet_abandon_authority(Protocol const &protocol,State const &owner,std::uint64_t guid);
}
