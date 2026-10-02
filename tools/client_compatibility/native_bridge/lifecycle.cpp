#include "lifecycle.hpp"

namespace bridge
{
void LoginBarrier::begin()
{
    if(pending || !deferred.empty() || !quest_reads.empty() || mail_read)throw std::runtime_error("repeated native login barrier");
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
void LoginBarrier::defer_quest_read(Packet packet)
{
    if(packet.first!="CMSG_QUERY_QUEST_INFO" || packet.second.size()!=4)
        throw std::runtime_error("only static quest reads may wait for player creation");
    Reader r(packet.second);auto id=r.take<std::uint32_t>();r.end();
    if(!id || id>0x7fffffff)throw std::runtime_error("invalid deferred quest identity");
    for(auto const &existing:quest_reads)if(existing.second==packet.second)return;
    if(quest_reads.size()>=64)throw std::runtime_error("deferred quest reads exceed bound");
    quest_reads.push_back(std::move(packet));
}
std::vector<Packet> LoginBarrier::release_quest_reads()
{
    std::vector<Packet> ready;ready.swap(quest_reads);
    if(mail_read){ready.push_back({"MSG_QUERY_NEXT_MAIL_TIME",{}});mail_read=false;}
    return ready;
}
void LoginBarrier::defer_mail_read(Packet packet)
{
    if(packet.first!="MSG_QUERY_NEXT_MAIL_TIME" || !packet.second.empty())
        throw std::runtime_error("only the empty mail-time read may wait for player creation");
    mail_read=true;
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
