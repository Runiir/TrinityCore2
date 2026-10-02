#include "service.hpp"

namespace bridge
{
// Called with this session's state mutex held. Never lock another session's state.
void Service::markers(Session &session,std::optional<unsigned> mask,Array const &locations,std::optional<unsigned> clear)
{
    std::lock_guard lock(markers_mutex);
    auto group=integer(session.state.party_guid[0]);
    for(auto it=marker_groups.begin();it!=marker_groups.end();)
    {
        std::erase_if(it->second.listeners,[&](auto const &entry)
        {
            return entry.second.expired() || (entry.first==session.id && it->first!=group);
        });
        if(it->second.listeners.empty() && it->first!=group)it=marker_groups.erase(it);else ++it;
    }
    if(!group)return;
    if(!marker_groups.contains(group) && marker_groups.size()>=256)throw std::runtime_error("raid marker groups exceed bound");
    auto &entry=marker_groups[group];entry.listeners[session.id]=session.shared_from_this();
    if(mask)
    {
        if(*mask&~31u)throw std::runtime_error("unsupported native raid marker mask");
        entry.markers.mask((entry.markers.active&224u)|*mask);
    }
    if(clear)entry.markers.mask(*clear==8 ? entry.markers.active&31u : entry.markers.active&~(1u<<*clear));
    for(auto const &location:locations)
    {
        auto slot=integer(get(location,"slot"));
        if(slot>=5)entry.markers.mask(entry.markers.active|(1u<<slot));
        entry.markers.location(slot,location);
    }
    auto packet=entry.markers.packet();
    if(!packet)return;
    if(mask || clear || !locations.empty())
    {
        for(auto const &[id,weak]:entry.listeners)if(auto member=weak.lock())member->send("SMSG_RAID_MARKERS_CHANGED",*packet);
    }
    else session.send("SMSG_RAID_MARKERS_CHANGED",*packet);
}
}
