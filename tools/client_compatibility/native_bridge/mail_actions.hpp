#pragma once
#include "protocol.hpp"

namespace bridge
{
Reply mail_action(Protocol const &,State const &,std::string const &,View);
Reply mail_command_result(Protocol const &,State &,View);
}
