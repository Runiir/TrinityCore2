#pragma once
#include "pet_packets.hpp"

namespace bridge
{
PetActionTranslation translate_pet_cast(Protocol const &protocol,State &owner,std::string const &name,View body);
}
