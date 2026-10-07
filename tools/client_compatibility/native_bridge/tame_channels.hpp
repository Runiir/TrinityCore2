#pragma once
#include "protocol.hpp"

namespace bridge
{
void arm_tame_channel(State &owner,unsigned counter);
Reply tame_channel_response(State &owner,std::string const &name,View body);
bool owned_tame_probe(std::filesystem::path const &root,std::string const &direction,
    std::string const &name,View body,std::string const &session,double now);
}
