// Public character cache lookup on the database pool; no account credentials.
#include "service.hpp"

namespace bridge
{
Task<> Session::player_names(Bytes body)
{
    Reader r(body);auto count = r.take<std::uint32_t>();
    if (!count || count > 64) throw std::runtime_error("player name query count exceeds bound");
    Array requested;
    std::string ids;
    for (unsigned i = 0; i < count; ++i)
    {
        auto guid = r.guid();auto low = integer(guid[0]);
        if (!low || low > 0xffffffff || integer(guid[1]) != player_high())
            throw std::runtime_error("name query is not a local player GUID");
        requested.push_back(guid);
        if (!ids.empty()) ids += ',';
        ids += std::to_string(low);
    }
    r.end();auto &own = owner();std::uint64_t actor = 0;
    {
        std::lock_guard lock(own.state_mutex);
        if (!own.state.created || own.world.expired()) throw std::runtime_error("name query without owned world");
        actor = own.state.guid();
    }
    auto root = service.root;
    auto rows = co_await background(service.database_workers, [root, ids]
    {
        Database db(root);
        return db.query("SELECT guid,name,race,gender,class,level FROM client442_characters.characters "
                        "WHERE deleteDate IS NULL AND guid IN (" + ids + ")");
    });
    {
        std::lock_guard lock(own.state_mutex);
        if (!own.state.created || own.state.guid() != actor) throw std::runtime_error("actor changed during name lookup");
    }
    own.send("SMSG_QUERY_PLAYER_NAMES_RESPONSE", Protocol::player_names_response(requested, rows));
}
} // namespace bridge
