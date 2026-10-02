#pragma once
#include "guild_fields.hpp"

namespace bridge
{
Reply guild_request(State const &owner,std::string const &name,View body);
Reply guild_response(std::string const &name,View body,Array const &identities);
Reply guild_membership_request(std::string const &name,View body);
Reply guild_membership_response(std::string const &name,View body);
Reply guild_event_response(std::string const &name,View body);
Reply guild_note_request(std::string const &name,View body);
Reply guild_note_response(std::string const &name,View body);
Array guild_member_guids(View body);
Value native_guild_roster(View body);
}
