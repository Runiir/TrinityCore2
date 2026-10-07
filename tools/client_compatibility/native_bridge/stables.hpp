#pragma once
#include "protocol.hpp"

namespace bridge
{
Bytes stable_block(State const &owner,Value const &stable,unsigned slots);
Value native_stable_list(View body);
void stable_catalog_started(Protocol const &protocol,State &owner,View body);
Reply stable_request(Protocol const &protocol, State const &owner, std::string const &name, View body);
Reply stable_response(Protocol const &protocol, State &owner, std::string const &name, View body,
                      Array const &models);
Reply stable_open_response(State &owner);
Reply stable_slot_request(Protocol const &protocol,State &owner,std::string const &name,View body);
Reply stable_slot_response(Protocol const &protocol,State &owner,std::string const &name,View body);
}
