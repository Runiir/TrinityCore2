#include "service.hpp"
#include "who.hpp"

namespace bridge
{
Task<> Session::who_reply(Bytes body)
{
    auto rows=native_who(body);std::shared_ptr<WhoState> pending;
    std::uint64_t actor=0,serial=0;
    {
        std::lock_guard lock(state_mutex);
        if(!state.created || world.expired() || !state.who_state || !state.who_state->pending)co_return;
        pending=state.who_state;actor=state.guid();serial=pending->serial;
    }
    Array identities;
    if(!rows.empty())
    {
        auto root=service.root;
        identities=co_await background(service.database_workers,[root,rows]
        {
            Database db(root);std::string names;
            for(auto const &row:rows)
            {if(!names.empty())names+=',';names+=db.quote(str(get(row,"name")));}
            return db.query("SELECT p.guid,p.name,p.race,p.gender,p.class,p.level,"
                "COALESCE(g.guildid,0) AS guild_id,COALESCE(g.name,'') AS guild_name "
                "FROM client442_characters.characters p "
                "LEFT JOIN client442_characters.guild_member m ON m.guid=p.guid "
                "LEFT JOIN client442_characters.guild g ON g.guildid=m.guildid "
                "WHERE p.deleteDate IS NULL AND p.name IN ("+names+")");
        });
    }
    std::lock_guard lock(state_mutex);auto instance=world.lock();
    if(!state.created || !instance || state.guid()!=actor || state.who_state!=pending ||
       !pending->pending || pending->serial!=serial)
    {
        service.events.event("stale_who_identity_lookup_ignored",{{"session",id}});co_return;
    }
    auto reply=who_response(*pending,rows,identities);
    pending->pending=false;send("SMSG_WHO",reply);
}
}
