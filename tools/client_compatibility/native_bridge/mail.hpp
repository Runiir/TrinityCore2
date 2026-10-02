#pragma once
#include "protocol.hpp"

namespace bridge
{
Reply mail_request(Protocol const &,State const &,std::string const &,View);
Reply mail_response(Protocol const &,State const &,std::string const &,View);
}
