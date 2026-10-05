#pragma once
#include "protocol.hpp"
namespace bridge
{
Reply chat_request(State &owner,std::string const &name,View body);
Reply chat_response(State &owner,std::string const &name,View body);
inline void require_chat_character(bool created,bool active_world)
{
    // Chat is sent on the authenticated Realm channel. Both channel types share
    // the same owned character; an active instance must exist, but need not be this.
    if(!created || !active_world)throw std::runtime_error("chat without owned active character");
}
}
