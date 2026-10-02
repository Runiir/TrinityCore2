#include "protocol.hpp"
#include <queue>
#include <unordered_set>

namespace bridge
{
Packet Protocol::taxi_request(State &owner, std::string const &name, View body, Value const &paths)
{
    Reader r(body);
    auto native = owned_unit(owner, r.guid());
    if (name != "CMSG_ACTIVATE_TAXI")
    {
        r.end();
        std::unordered_map<std::string, std::string> const names = {
            {"CMSG_TAXI_NODE_STATUS_QUERY", "CMSG_TAXINODE_STATUS_QUERY"},
            {"CMSG_TAXI_QUERY_AVAILABLE_NODES", "CMSG_TAXIQUERYAVAILABLENODES"},
            {"CMSG_ENABLE_TAXI_NODE", "CMSG_ENABLETAXI"}};
        return {names.at(name), Writer().put(native).finish()};
    }
    auto destination = r.take<std::uint32_t>();
    r.raw(8);
    r.end();
    auto const &menu = owner.taxi_menu;
    if (menu.is_null() || integer(get(menu, "vendor")) != native)
        throw std::runtime_error("taxi selection does not belong to an owned native menu");
    std::unordered_set<unsigned> known;
    for (auto const &node : get(menu, "known").as_array())
        known.insert(integer(node));
    if (!known.contains(destination))
        throw std::runtime_error("taxi selection does not belong to an owned native menu");
    std::unordered_map<unsigned, std::vector<std::pair<unsigned, unsigned>>> graph;
    for (auto const &edge : paths.as_array())
    {
        auto source = integer(get(edge, "source")), dest = integer(get(edge, "destination"));
        if (known.contains(source) && known.contains(dest))
            graph[source].push_back({dest, integer(get(edge, "cost"))});
    }
    using Journey = std::tuple<std::uint64_t, unsigned, std::vector<unsigned>>;
    std::priority_queue<Journey, std::vector<Journey>, std::greater<Journey>> queue;
    auto source = static_cast<unsigned>(integer(get(menu, "source")));
    queue.push({0, source, {source}});
    std::unordered_set<unsigned> best;
    while (!queue.empty())
    {
        auto [cost, node, path] = queue.top();
        queue.pop();
        if (!best.insert(node).second)
            continue;
        if (node == destination)
        {
            if (path.size() < 2)
                throw std::runtime_error("taxi destination is the current node");
            Array journey;
            for (auto n : path)
                journey.push_back(n);
            return {"CMSG_ACTIVATETAXIEXPRESS", Writer()
                                                    .pack("QI", {native, path.size()})
                                                    .pack(std::string(path.size(), 'I'), journey)
                                                    .finish()};
        }
        for (auto const &[next, fare] : graph[node])
        {
            auto next_path = path;
            next_path.push_back(next);
            queue.push({cost + fare, next, next_path});
        }
    }
    throw std::runtime_error("destination has no known native taxi route");
}
Reply Protocol::taxi_response(State &owner, std::string const &name, View body)
{
    Reader r(body);
    Writer w;
    if (name == "SMSG_SHOWTAXINODES")
    {
        auto window = r.take<std::uint32_t>();
        auto native = r.take<std::uint64_t>();
        auto source = r.take<std::uint32_t>(), count = r.take<std::uint32_t>();
        if (window != 1 || count > 256)
            throw std::runtime_error("unexpected native taxi menu");
        auto record = owner.visible_units.find(native);
        if (record == owner.visible_units.end())
            return {};
        auto raw = r.raw(count);
        Bytes mask(raw.begin(), raw.end());
        r.end();
        Array known;
        for (unsigned i = 0; i < count; ++i)
            for (unsigned b = 0; b < 8; ++b)
                if (mask[i] & (1u << b))
                    known.push_back(i * 8 + b + 1);
        owner.taxi_menu = Object{{"vendor", native}, {"source", source}, {"known", known}};
        while (mask.size() % 8)
            mask.push_back(0);
        auto chunks = mask.size() / 8;
        return Packet{"SMSG_SHOW_TAXI_NODES",
                      w.bits(1, 1)
                          .pack("II", {chunks, chunks})
                          .guid(modern_guid(native, integer(get(record->second, "map"))))
                          .pack("I", {source})
                          .raw(mask)
                          .raw(mask)
                          .finish()};
    }
    if (name == "SMSG_TAXINODE_STATUS")
    {
        auto native = r.take<std::uint64_t>();
        auto status = r.take<std::uint8_t>();
        r.end();
        auto record = owner.visible_units.find(native);
        if (record == owner.visible_units.end())
            return {};
        return Packet{
            "SMSG_TAXI_NODE_STATUS",
            w.guid(modern_guid(native, integer(get(record->second, "map")))).bits(status, 2).finish()};
    }
    if (name == "SMSG_ACTIVATETAXIREPLY")
    {
        auto status = r.take<std::uint32_t>();
        r.end();
        return Packet{"SMSG_ACTIVATE_TAXI_REPLY", w.bits(status, 4).finish()};
    }
    if (name == "SMSG_NEW_TAXI_PATH")
    {
        r.end();
        return Packet{name, {}};
    }
    return {};
}
} // namespace bridge
