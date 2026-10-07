#pragma once
#include "buffer.hpp"
#include <filesystem>

namespace bridge
{
bool owned_pet_abandon_probe(std::filesystem::path const &root,std::string const &direction,
    std::string const &name,View body,std::string const &session,double now);
}
