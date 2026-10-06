#include "lifecycle.hpp"

namespace bridge
{
void LoginBarrier::begin()
{
    if(pending || awaiting_player || mover_ack || !deferred.empty() || !quest_reads.empty() || !template_reads.empty() || mail_read)
        throw std::runtime_error("repeated native login barrier");
    pending = true;
    bytes = 0;
    awaiting_player = true;
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
    for(auto &packet:template_reads)ready.push_back(std::move(packet));
    template_reads.clear();
    if(mail_read){ready.push_back({"MSG_QUERY_NEXT_MAIL_TIME",{}});mail_read=false;}
    return ready;
}
void LoginBarrier::defer_template_read(Packet packet)
{
    if((packet.first!="CMSG_GAMEOBJECT_QUERY" && packet.first!="CMSG_CREATURE_QUERY") || packet.second.size()!=12)
        throw std::runtime_error("only static template reads may wait for player creation");
    Reader r(packet.second);auto entry=r.take<std::uint32_t>();auto guid=r.take<std::uint64_t>();r.end();
    if(!entry || entry&0x80000000 || (packet.first=="CMSG_GAMEOBJECT_QUERY" && entry>0xfffff) ||
       (guid && ((guid>>32)&0xfffff)!=entry))throw std::runtime_error("invalid deferred template identity");
    for(auto const &existing:template_reads)if(existing==packet)return;
    if(template_reads.size()>=512)throw std::runtime_error("deferred template reads exceed bound");
    template_reads.push_back(std::move(packet));
}
void LoginBarrier::defer_mail_read(Packet packet)
{
    if(packet.first!="MSG_QUERY_NEXT_MAIL_TIME" || !packet.second.empty())
        throw std::runtime_error("only the empty mail-time read may wait for player creation");
    mail_read=true;
}
bool LoginBarrier::accept_active_mover(State const &state, View body, bool active_instance)
{
    if(body.size()!=4)throw std::runtime_error("invalid active mover acknowledgement");
    if(!active_instance || !state.guid())
        throw std::runtime_error("active mover acknowledgement outside owned instance");
    if(state.created)return true;
    if(!awaiting_player)throw std::runtime_error("active mover acknowledgement outside owned login");
    // One acknowledgement can arrive immediately after RESUME_COMMS. Keep it
    // bounded and wait for the authoritative native player, even after WORLD.
    mover_ack=true;
    return false;
}
bool LoginBarrier::release_active_mover(State const &state)
{
    if(!state.created || !state.guid())throw std::runtime_error("active mover release before owned player creation");
    bool ready=awaiting_player && mover_ack;
    awaiting_player=false;
    mover_ack=false;
    return ready;
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
