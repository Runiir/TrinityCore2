#pragma once
#include "protocol.hpp"

namespace bridge
{
struct WhoState
{
    std::uint32_t request_id=0;
    std::uint64_t serial=0;
    bool pending=false,exact=false;
    std::string name;
};
Reply who_request(State &owner,std::string const &name,View body);
Array native_who(View body);
Bytes who_response(WhoState const &request,Array const &rows,Array const &identities);
Reply who_complete(State &owner,View body,Array const &identities);
}
