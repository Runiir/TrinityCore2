#include "lifecycle.hpp"

namespace bridge
{
void LoginBarrier::begin()
{
    if(pending || !deferred.empty())throw std::runtime_error("repeated native login barrier");
    pending = true;
    bytes = 0;
}
std::vector<Packet> LoginBarrier::accept(Packet packet)
{
    auto const &name = packet.first;
    if(!pending || name=="SMSG_ACCOUNT_DATA_TIMES" || name=="SMSG_UPDATE_ACCOUNT_DATA" ||
       name=="SMSG_UPDATE_ACCOUNT_DATA_COMPLETE")return {std::move(packet)};
    if(name=="SMSG_LOGIN_VERIFY_WORLD")
    {
        pending = false;
        std::vector<Packet> ready;
        ready.reserve(deferred.size()+1);
        ready.push_back(std::move(packet));
        while(!deferred.empty())
        {
            ready.push_back(std::move(deferred.front()));
            deferred.pop_front();
        }
        bytes = 0;
        return ready;
    }
    if(deferred.size()>=512 || packet.second.size()>2*1024*1024-bytes)
        throw std::runtime_error("native login initialization exceeds bounded queue");
    bytes += packet.second.size();
    deferred.push_back(std::move(packet));
    return {};
}
void finish_logout(State &state)
{
    State next;
    next.last_logout_guid = state.guid();
    next.account_times = state.account_times;
    next.native_send = std::move(state.native_send);
    state = std::move(next);
}
}
