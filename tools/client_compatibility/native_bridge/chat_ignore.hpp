#pragma once
#include "protocol.hpp"
namespace bridge
{
Reply ignored_chat_request(std::string const &name, View body);
bool owned_ignore_probe(std::string const &name, View body);
}
