#pragma once
#include "buffer.hpp"

namespace bridge
{
// Only an expiring, session-bound synthetic owned Hunter fixture is retained.
bool owned_pet_rename_probe(std::filesystem::path const &root, std::string const &direction,
    std::string const &name, View body, std::string const &session, double now);
}
