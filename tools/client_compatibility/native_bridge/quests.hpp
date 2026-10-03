#pragma once
#include "protocol.hpp"

namespace bridge
{
Reply quest_query_response(std::string const &name,View body);
Reply quest_status_request(Protocol const &protocol,State const &owner,std::string const &name,View body);
Reply quest_status_response(Protocol const &protocol,State const &owner,std::string const &name,View body);
Reply quest_list_response(Protocol const &protocol,State const &owner,std::string const &name,View body);
Reply quest_progress_response(Protocol const &protocol,State const &owner,std::string const &name,View body);
Reply quest_turnin_request(Protocol const &protocol,State &owner,std::string const &name,View body);
Reply quest_turnin_response(Protocol const &protocol,State &owner,std::string const &name,View body);
Reply quest_request(Protocol const &protocol,State &owner,std::string const &name,View body);
Reply quest_response(Protocol const &protocol,State &owner,std::string const &name,View body);
}
