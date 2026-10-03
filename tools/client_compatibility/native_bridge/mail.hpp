#pragma once
#include "protocol.hpp"

namespace bridge
{
inline void require_mail_character(bool created,bool active_world)
{
    // SendMail uses the authenticated Realm channel. Its associated owned
    // instance must still have an authoritative player, and mailbox provenance
    // is independently required by the packet translator.
    if(!created || !active_world)throw std::runtime_error("mail without owned active character");
}
std::uint64_t visible_mailbox(Protocol const &,State const &,Array const &);
Reply mail_request(Protocol const &,State &,std::string const &,View);
Reply mail_response(Protocol const &,State &,std::string const &,View);
}
