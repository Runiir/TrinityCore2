#include "protocol.hpp"
#include <array>

namespace bridge
{
std::uint64_t native_guid(Reader &r)
{
    auto mask = r.take<std::uint8_t>();
    std::uint64_t result = 0;
    for (unsigned i = 0; i < 8; ++i)
        if (mask & (1u << i))
            result |= static_cast<std::uint64_t>(r.take<std::uint8_t>()) << (i * 8);
    return result;
}
Writer &packed(Writer &w, std::uint64_t guid)
{
    auto octets = Writer().put(guid).finish();
    std::uint8_t mask = 0;
    for (unsigned i = 0; i < 8; ++i)
        if (octets[i])
            mask |= 1u << i;
    w.put(mask);
    for (auto n : octets)
        if (n)
            w.put(n);
    return w;
}
namespace
{
Value values(Reader &r)
{
    auto count = r.take<std::uint8_t>();
    auto masks = r.unpack(std::string(count, 'I'));
    Object result;
    for (unsigned i = 0; i < count; ++i)
        for (unsigned bit = 0; bit < 32; ++bit)
            if (integer(masks[i]) & (1u << bit))
                result[std::to_string(i * 32 + bit)] = r.take<std::uint32_t>();
    return result;
}
std::pair<Value, Value> movement(Reader &r)
{
    Object flags;
    for (auto n : {"hover", "greeting", "rotation", "animkit", "victim", "self", "vehicle", "movement"})
        flags[n] = r.bits(1);
    auto pauses = r.bits(24);
    for (auto n : {"birth", "transport", "stationary", "area", "portals", "time"})
        flags[n] = r.bits(1);
    auto f = [&](auto name) { return truth(flags.at(name)); };
    if (f("transport"))
        throw std::runtime_error("unsupported native object transport");
    Object m{{"flags", 0}, {"flags2", 0}, {"position", Array{0, 0, 0, 0}}, {"pitch", 0}, {"time", 0}};
    std::array<bool, 8> present{};
    std::array<bool, 8> victim{};
    std::array<bool, 3> kits{};
    bool no_flags = false, no_o = false, no_pitch = false, spline = false, fall = false, no_elevation = false,
         no_time = false, fall_direction = false;
    bool active = false, effect = false, acceleration = false;
    unsigned nodes = 0, facing = 0, target_count = 0;
    if (f("movement"))
    {
        no_flags = r.bits(1);
        no_o = r.bits(1);
        for (unsigned i : {7, 3, 2})
            present[i] = r.bits(1);
        if (!no_flags)
            m["flags"] = r.bits(30);
        r.bits(1);
        no_pitch = r.bits(1);
        spline = r.bits(1);
        fall = r.bits(1);
        no_elevation = r.bits(1);
        present[5] = r.bits(1);
        auto transport = r.bits(1);
        no_time = r.bits(1);
        if (transport)
            throw std::runtime_error("unsupported native object transport");
        present[4] = r.bits(1);
        if (spline)
        {
            active = r.bits(1);
            if (active)
            {
                r.bits(2);
                effect = r.bits(1);
                nodes = r.bits(22);
                facing = r.bits(2);
                if (nodes > 10000)
                    throw std::runtime_error("native spline exceeds bound");
                if (facing == 2)
                    for (unsigned i = 0; i < 8; ++i)
                        target_count += r.bits(1);
                acceleration = r.bits(1);
                r.bits(25);
            }
        }
        present[6] = r.bits(1);
        fall_direction = fall ? r.bits(1) : false;
        present[0] = r.bits(1);
        present[1] = r.bits(1);
        r.bits(1);
        if (!r.bits(1))
            m["flags2"] = r.bits(12);
    }
    if (f("victim"))
        for (auto &v : victim)
            v = r.bits(1);
    if (f("animkit"))
        for (auto &v : kits)
            v = !r.bits(1);
    r.align();
    if (pauses > 10000)
        throw std::runtime_error("native pause times exceed bound");
    r.raw(pauses * 4);
    auto octet = [&](unsigned i)
    {
        if (present[i])
            r.raw(1);
    };
    if (f("movement"))
    {
        octet(4);
        auto run_back = r.take<float>();
        if (fall)
        {
            if (fall_direction)
                r.raw(12);
            r.raw(8);
        }
        auto swim_back = r.take<float>();
        if (!no_elevation)
            r.raw(4);
        if (spline)
        {
            if (active)
            {
                if (acceleration)
                    r.raw(4);
                r.raw(4);
                if (facing == 0)
                    r.raw(4);
                if (facing == 2)
                    r.raw(target_count);
                r.raw(nodes * 12);
                if (facing == 1)
                    r.raw(12);
                r.raw(8);
                if (effect)
                    r.raw(4);
                r.raw(4);
            }
            r.raw(16);
        }
        auto z = r.take<float>();
        octet(5);
        auto x = r.take<float>();
        auto pitch_rate = r.take<float>();
        octet(3);
        octet(0);
        auto swim = r.take<float>();
        auto y = r.take<float>();
        octet(7);
        octet(1);
        octet(2);
        auto walk = r.take<float>();
        if (!no_time)
            m["time"] = r.take<std::uint32_t>();
        auto turn = r.take<float>();
        octet(6);
        auto flight = r.take<float>();
        auto orientation = no_o ? 0 : r.take<float>();
        auto run = r.take<float>();
        if (!no_pitch)
            m["pitch"] = r.take<float>();
        auto flight_back = r.take<float>();
        m["position"] = Array{x, y, z, orientation};
        m["speeds"] = Array{walk, run, run_back, swim, swim_back, flight, flight_back, turn, pitch_rate};
    }
    if (f("vehicle"))
        r.raw(8);
    if (f("rotation"))
        m["rotation"] = r.take<std::uint64_t>();
    if (f("area"))
        r.raw(65);
    if (f("stationary"))
    {
        auto p = r.unpack("4f");
        m["position"] = Array{p[1], p[2], p[3], p[0]};
    }
    for (auto v : victim)
        if (v)
            r.raw(1);
    for (auto v : kits)
        if (v)
            r.raw(2);
    if (f("time"))
        r.raw(4);
    return {m, flags};
}
} // namespace
std::vector<Value> native_records(View body)
{
    Reader r(body);
    auto map = r.take<std::uint16_t>();
    auto count = r.take<std::uint32_t>();
    if (count > 10000)
        throw std::runtime_error("native update count exceeds bound");
    std::vector<Value> result;
    for (unsigned i = 0; i < count; ++i)
    {
        auto type = r.take<std::uint8_t>();
        if (type == 3)
        {
            auto removed_count = r.take<std::uint32_t>();
            if (removed_count > 10000)
                throw std::runtime_error("native removal count exceeds bound");
            Array removed;
            for (unsigned j = 0; j < removed_count; ++j)
                removed.push_back(native_guid(r));
            result.push_back(Object{{"update_type", 3}, {"removed", removed}, {"map", map}});
            continue;
        }
        Object record{{"guid", native_guid(r)}, {"map", map}, {"update_type", type}};
        if (type == 1 || type == 2)
        {
            record["kind"] = r.take<std::uint8_t>();
            auto [m, f] = movement(r);
            record["movement"] = m;
            record["flags"] = f;
        }
        else if (type != 0)
            throw std::runtime_error("unsupported native object update type");
        record["fields"] = values(r);
        result.push_back(std::move(record));
    }
    r.end();
    return result;
}
Bytes object_packet(unsigned map, std::vector<Bytes> const &blocks, std::vector<std::uint64_t> const &removed,
                    std::vector<std::uint64_t> const &destroyed)
{
    Writer data;
    for (auto const &block : blocks)
        data.raw(block);
    Writer w;
    w.pack("HI", {map, blocks.size()}).bits(1, 1).bits(!removed.empty() || !destroyed.empty(), 1);
    if (!removed.empty() || !destroyed.empty())
    {
        w.pack("HI", {destroyed.size(), removed.size() + destroyed.size()});
        for (auto guid : destroyed)
            w.guid(Protocol::modern_guid(guid, map));
        for (auto guid : removed)
            w.guid(Protocol::modern_guid(guid, map));
    }
    return w.put<std::uint32_t>(data.data().size()).raw(data.data()).finish();
}
} // namespace bridge
