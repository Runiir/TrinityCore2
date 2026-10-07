#pragma once
#include "protocol.hpp"

namespace bridge
{
bool owned_entry_probe(std::filesystem::path const &root,std::string const &direction,
    std::string const &name,View body,std::string const &session,double now);
}
