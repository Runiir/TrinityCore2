#pragma once
#include "protocol.hpp"

namespace bridge
{
inline void require_mail_character(std::string const &name,bool created,bool active_world,bool in_world)
{
    // SendMail and ReturnToSender use the authenticated Realm channel. Its owned
    // instance must still have an authoritative player, and mailbox provenance
    // is independently required by the packet translator.
    bool realm_mail=name=="CMSG_SEND_MAIL" || name=="CMSG_MAIL_RETURN_TO_SENDER";
    if(!created || !active_world || (!in_world && !realm_mail))
        throw std::runtime_error("mail outside owned active character channel");
}
std::uint64_t visible_mailbox(Protocol const &,State const &,Array const &);
Reply mail_request(Protocol const &,State &,std::string const &,View);
Reply mail_response(Protocol const &,State &,std::string const &,View);
}
