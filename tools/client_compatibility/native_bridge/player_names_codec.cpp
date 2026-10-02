#include "protocol.hpp"

namespace bridge
{
Bytes Protocol::player_names_response(Array const &requested, Array const &rows)
{
    std::unordered_map<std::uint64_t, Value> names;
    for (auto const &row : rows) names[integer(get(row, "guid"))] = row;
    Writer w;w.put<std::uint32_t>(requested.size());
    for (auto const &guid : requested)
    {
        auto pos = names.find(integer(guid.as_array()[0]));bool exists = pos != names.end();
        w.put<std::uint8_t>(exists ? 0 : 1).guid(guid).bits(exists, 1).bits(0, 1).flush();
        if (!exists) continue;
        auto const &row = pos->second;auto name = str(get(row, "name"));
        if (name.empty() || name.size() > 63) throw std::runtime_error("invalid public player name");
        w.bits(0, 1).bits(name.size(), 6);
        for (unsigned i = 0; i < 5; ++i) w.bits(0, 7);
        w.guid().guid().guid(guid).pack("QI5Bi", {0, 1, get(row, "race"), get(row, "gender"),
            get(row, "class"), get(row, "level"), 0, 0}).raw(name);
    }
    return w.finish();
}
} // namespace bridge
