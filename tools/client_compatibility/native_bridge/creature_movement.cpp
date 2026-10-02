#include "protocol.hpp"
#include <cmath>

namespace bridge
{
std::vector<Packet> Protocol::creature_movement(State &owner, View body)
{
    Reader r(body);
    auto guid = native_guid(r);
    auto exit = r.take<std::uint8_t>();
    auto position = r.unpack("3f");
    auto sequence = r.take<std::uint32_t>();
    auto face = r.take<std::uint8_t>();
    if (face > 4)
        throw std::runtime_error("invalid native creature spline face");
    Value facing;
    if (face == 2)
        facing = r.unpack("3f");
    else if (face == 3)
        facing = r.take<std::uint64_t>();
    else if (face == 4)
        facing = r.take<float>();
    auto flags = r.take<std::uint32_t>();
    if (flags & 0xff018000)
        return {};
    auto duration = r.take<std::uint32_t>(), count = r.take<std::uint32_t>();
    if (count > 10000)
        throw std::runtime_error("native creature spline exceeds point bound");
    auto uncompressed = flags & 0x400000;
    std::vector<Array> points;
    for (unsigned i = 0; i < (uncompressed ? count : std::min(count, 1u)); ++i)
        points.push_back(r.unpack("3f"));
    auto deltas = r.raw(!uncompressed && count ? (count - 1) * 4 : 0);
    r.end();
    auto check = [](Array const &p)
    {
        for (auto const &v : p)
            if (!std::isfinite(number(v)) || std::abs(number(v)) > 17067)
                throw std::runtime_error("invalid native creature spline coordinates");
    };
    check(position);
    for (auto const &p : points)
        check(p);
    auto record = owner.visible_units.find(guid);
    if (record == owner.visible_units.end())
        return {};
    auto map = integer(get(record->second, "map"));
    auto &movement = record->second.as_object()["movement"].as_object();
    auto orientation = movement["position"].as_array()[3];
    movement["position"] = Array{position[0], position[1], position[2], orientation};
    auto identity = modern_guid(guid, map);
    Writer update;
    update.guid(identity)
        .pack("IIII6fII", {0, 0, 0, movement["time"], position[0], position[1], position[2], orientation, 0,
                           0, 0, sequence})
        .bits(0, 8);
    Writer w;
    w.guid(identity).pack("3f", position).pack("I", {sequence}).bits(0, 1).bits(0, 3).flush();
    w.pack("IIIIB", {flags | (face == 1 ? 0x20u : 0u), 0, duration, 0, 0}).guid().pack("b", {-1});
    auto modern_face = face == 2 ? 1 : face == 3 ? 2 : face == 4 ? 3 : 0;
    w.bits(modern_face, 2)
        .bits(points.size(), 16)
        .bits(exit != 0, 1)
        .bits(0, 1)
        .bits(deltas.size() / 4, 16)
        .bits(0, 4)
        .flush();
    if (modern_face == 1)
        w.pack("3f", facing.as_array());
    else if (modern_face == 2)
        w.pack("f", {0}).guid(modern_guid(integer(facing), map));
    else if (modern_face == 3)
        w.pack("f", {facing});
    for (auto const &p : points)
        w.pack("3f", p);
    w.raw(deltas);
    return {{"SMSG_MOVE_UPDATE", update.finish()}, {"SMSG_ON_MONSTER_MOVE", w.finish()}};
}
} // namespace bridge
