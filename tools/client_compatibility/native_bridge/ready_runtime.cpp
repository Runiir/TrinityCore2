#include "service.hpp"

namespace bridge
{
// Callers hold only their own state mutex. Registry callbacks never read or lock
// another session's state; sends dispatch to each connection's strand.
void Service::ready_finish(std::uint64_t group,ReadyGroup &entry,std::string const &reason)
{
    if(!entry.check.finish())return;
    if(entry.timer)entry.timer->cancel();
    auto body=Writer().put<std::uint8_t>(0).guid(entry.guid).finish();
    for(auto const &[id,weak]:entry.listeners)
        if(auto peer=weak.lock())peer->send("SMSG_READY_CHECK_COMPLETED",body);
    events.event("ready_check_completed",{{"group",group},{"reason",reason}});
}
void Service::ready_roster(Session &session)
{
    std::lock_guard lock(ready_mutex);
    auto group=integer(session.state.party_guid[0]);
    for(auto it=ready_groups.begin();it!=ready_groups.end();)
    {
        bool departed=it->first!=group && it->second.listeners.contains(session.id);
        if(departed)ready_finish(it->first,it->second,"roster_changed");
        std::erase_if(it->second.listeners,[&](auto const &item)
        {return item.second.expired() || (item.first==session.id && it->first!=group);});
        if(it->second.listeners.empty() && it->first!=group)
        {if(it->second.timer)it->second.timer->cancel();it=ready_groups.erase(it);}
        else ++it;
    }
    if(!group)return;
    if(!ready_groups.contains(group) && ready_groups.size()>=256)
        throw std::runtime_error("ready check groups exceed bound");
    auto &entry=ready_groups[group];entry.guid=session.state.party_guid;
    entry.listeners[session.id]=session.shared_from_this();
}
void Service::ready_native(Session &session,std::string const &name,View body)
{
    std::lock_guard lock(ready_mutex);
    auto group=integer(session.state.party_guid[0]);
    if(!group)return;
    auto pos=ready_groups.find(group);
    if(pos==ready_groups.end())throw std::runtime_error("ready check without registered roster");
    auto &entry=pos->second;Reader r(body);
    if(name=="MSG_RAID_READY_CHECK")
    {
        auto starter=r.take<std::uint64_t>();r.end();
        // Native broadcasts the same start separately to every connection.
        // Coalesce those copies, even if the last answer already completed it.
        if(!entry.announced.empty() && !entry.announced.contains(session.id))
        {entry.announced.insert(session.id);return;}
        if(entry.check.active)return;
        entry.announced={session.id};entry.check.start(starter,session.state.party_members);
        auto packet=Protocol::party_response(session.state,name,body,{});
        for(auto const &[id,weak]:entry.listeners)if(auto peer=weak.lock())peer->send(*packet);
        events.event("ready_check_started",{{"group",group},{"starter",starter},{"duration_ms",30000}});
        entry.timer=std::make_shared<asio::steady_timer>(session.channel->strand,std::chrono::seconds(30));
        auto timer=entry.timer;
        timer->async_wait([this,group,timer](boost::system::error_code error)
        {
            if(error)return;
            std::lock_guard lock(ready_mutex);auto pos=ready_groups.find(group);
            if(pos!=ready_groups.end() && pos->second.timer==timer)
                ready_finish(group,pos->second,"timeout");
        });
        if(entry.check.complete())ready_finish(group,entry,"all_answered");
    }
    else if(name=="MSG_RAID_READY_CHECK_CONFIRM")
    {
        auto member=r.take<std::uint64_t>();auto ready=r.take<std::uint8_t>();r.end();
        if(ready>1)throw std::runtime_error("invalid native ready answer");
        if(!entry.check.answer(member))return;
        auto packet=Protocol::party_response(session.state,name,body,{});
        for(auto const &[id,weak]:entry.listeners)if(auto peer=weak.lock())peer->send(*packet);
        events.event("ready_check_native_answer",{{"group",group},{"member",member},{"ready",bool(ready)}});
        if(entry.check.complete())ready_finish(group,entry,"all_answered");
    }
    else if(name=="MSG_RAID_READY_CHECK_FINISHED")
    {r.end();ready_finish(group,entry,"native_finished");}
}
}
