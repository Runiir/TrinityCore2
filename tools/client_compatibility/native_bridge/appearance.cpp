#include "appearance.hpp"

namespace bridge
{
Reply appearance_request(std::string const &name, View body)
{
    if(name!="CMSG_SHOWING_HELM" && name!="CMSG_SHOWING_CLOAK")return {};
    // Pinned WPP CharacterHandler::HandleShowingCloakAndHelm434 and native
    // CharacterPackets both read one byte boolean. Preserve the native meaning.
    Reader r(body);r.take<std::uint8_t>();r.end();
    return Packet{name,Bytes(body.begin(),body.end())};
}
}
