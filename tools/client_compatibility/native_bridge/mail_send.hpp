#pragma once
#include "protocol.hpp"

namespace bridge
{
Reply mail_send(Protocol const &,State const &,std::string const &,View);
}
