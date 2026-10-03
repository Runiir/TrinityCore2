#pragma once
#include "protocol.hpp"

namespace bridge
{
std::uint64_t visible_mailbox(Protocol const &,State const &,Array const &);
Reply mail_request(Protocol const &,State &,std::string const &,View);
Reply mail_response(Protocol const &,State &,std::string const &,View);
}
