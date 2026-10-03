#pragma once
#include "protocol.hpp"

namespace bridge
{
Array archaeology_weights(Reader &reader, unsigned count);
Reply research_history(State const &owner, std::string const &name, View body);
bool research_complete(std::string const &name, View body);
}
