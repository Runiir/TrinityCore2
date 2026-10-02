#pragma once
#include "guild_fields.hpp"

namespace bridge
{
Reply guild_request(State const &owner,std::string const &name,View body);
Reply guild_response(std::string const &name,View body,Array const &identities);
Array guild_member_guids(View body);
Value native_guild_roster(View body);
}
