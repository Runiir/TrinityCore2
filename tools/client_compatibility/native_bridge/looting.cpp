#include "protocol.hpp"
#include <unordered_set>

namespace bridge
{
namespace
{
Array loot_guid(std::uint64_t native, unsigned map)
{
    return {native & 0xffffffff, (15ull << 58) | (1ull << 42) | (static_cast<std::uint64_t>(map) << 29)};
}
} // namespace
Reply Protocol::loot_response(State &owner, std::string const &name, View body)
{
    Reader r(body);
    if (name == "SMSG_LOOT_RESPONSE")
    {
        auto native = r.take<std::uint64_t>();
        auto reason = r.take<std::uint8_t>();
        auto record = owner.visible_gameobjects.find(native);
        if (record == owner.visible_gameobjects.end())
            return {};
        auto map = integer(get(record->second, "map"));
        auto world = modern_guid(native, map), identity = loot_guid(native, map);
        auto failure = !reason ? r.take<std::uint8_t>() : 17;
        auto coins = reason ? r.take<std::uint32_t>() : 0;
        auto items = reason ? r.take<std::uint8_t>() : 0, currencies = reason ? r.take<std::uint8_t>() : 0;
        Writer w;
        w.guid(world)
            .guid(identity)
            .pack("BBBBIII", {failure, reason, 0, 2, coins, items, currencies})
            .bits(reason != 0, 1)
            .bits(0, 2)
            .flush();
        Object slots;
        for (unsigned i = 0; i < static_cast<unsigned>(items); ++i)
        {
            auto slot = r.take<std::uint8_t>();
            auto item = r.take<std::uint32_t>(), quantity = r.take<std::uint32_t>();
            r.take<std::int32_t>();
            auto seed = r.take<std::int32_t>(), prop = r.take<std::int32_t>();
            auto ui = r.take<std::uint8_t>();
            slots[std::to_string(slot)] = "CMSG_AUTOSTORE_LOOT_ITEM";
            w.bits(0, 2)
                .bits(ui, 3)
                .bits(0, 1)
                .flush()
                .pack("iii", {item, seed, prop})
                .bits(0, 1)
                .flush()
                .bits(0, 6)
                .flush()
                .pack("IBB", {quantity, 0, slot});
        }
        for (unsigned i = 0; i < static_cast<unsigned>(currencies); ++i)
        {
            auto slot = r.take<std::uint8_t>();
            auto kind = r.take<std::uint32_t>(), quantity = r.take<std::uint32_t>();
            slots[std::to_string(slot)] = "CMSG_LOOT_CURRENCY";
            w.pack("IIB", {kind, quantity, slot}).bits(0, 3).flush();
        }
        r.end();
        owner.loot = Object{{"native", native}, {"guid", identity}, {"owner", world}, {"slots", slots}};
        return Packet{name, w.finish()};
    }
    if (owner.loot.is_null())
        return {};
    auto &loot = owner.loot;
    if (name == "SMSG_LOOT_REMOVED" || name == "SMSG_CURRENCY_LOOT_REMOVED")
    {
        auto slot = r.take<std::uint8_t>();
        r.end();
        loot.as_object()["slots"].as_object().erase(std::to_string(slot));
        return Packet{"SMSG_LOOT_REMOVED",
                      Writer().guid(get(loot, "owner")).guid(get(loot, "guid")).pack("B", {slot}).finish()};
    }
    if (name == "SMSG_LOOT_RELEASE")
    {
        auto native = r.take<std::uint64_t>();
        r.take<std::uint8_t>();
        r.end();
        if (native != integer(get(loot, "native")))
            throw std::runtime_error("foreign loot release");
        auto reply = Writer().guid(get(loot, "guid")).guid(get(loot, "owner")).finish();
        owner.loot = nullptr;
        return Packet{name, reply};
    }
    return {};
}
std::vector<Packet> Protocol::loot_request(State const &owner, std::string const &name, View body)
{
    Reader r(body);
    std::vector<Packet> requests;
    if (name == "CMSG_GAME_OBJ_USE" || name == "CMSG_GAME_OBJ_REPORT_USE")
    {
        auto identity = r.guid();
        r.end();
        auto native = owned_gameobject(owner, identity);
        return {{name == "CMSG_GAME_OBJ_USE" ? "CMSG_GAMEOBJ_USE" : "CMSG_GAMEOBJ_REPORT_USE",
                 Writer().put(native).finish()}};
    }
    if (owner.loot.is_null())
        throw std::runtime_error("loot action without a native loot window");
    auto const &loot = owner.loot;
    if (name == "CMSG_LOOT_ITEM")
    {
        auto count = r.take<std::uint32_t>();
        if (count > 100)
            throw std::runtime_error("loot requests exceed bound");
        std::unordered_set<unsigned> seen;
        for (unsigned i = 0; i < count; ++i)
        {
            auto identity = r.guid();
            auto slot = r.take<std::uint8_t>();
            auto const &slots = get(loot, "slots").as_object();
            auto key = std::to_string(slot);
            if (identity != get(loot, "guid").as_array() || !slots.contains(key) || !seen.insert(slot).second)
                throw std::runtime_error("foreign/duplicate loot slot");
            requests.push_back({str(slots.at(key)), Bytes{slot}});
        }
        r.bits(1);
    }
    else if (name == "CMSG_LOOT_RELEASE")
    {
        auto identity = r.guid();
        if (identity != get(loot, "guid").as_array() && identity != get(loot, "owner").as_array())
            throw std::runtime_error("foreign loot release");
        requests.push_back({name, Writer().pack("Q", {get(loot, "native")}).finish()});
    }
    else if (name == "CMSG_LOOT_MONEY")
    {
        r.bits(1);
        requests.push_back({name, {}});
    }
    else
        throw std::runtime_error("unsupported loot request");
    r.end();
    return requests;
}
} // namespace bridge
