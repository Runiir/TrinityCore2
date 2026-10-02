#include "protocol.hpp"

namespace bridge
{
Reply Protocol::aura_response(State &owner, std::string const &name, View body)
{
    if (name != "SMSG_AURA_UPDATE" && name != "SMSG_AURA_UPDATE_ALL")
        return {};
    Reader r(body);
    auto unit = native_guid(r);
    if (unit != owner.guid())
        return {};
    std::vector<Value> entries;
    while (r.remaining())
    {
        auto slot = r.take<std::uint8_t>();
        auto spell = r.take<std::int32_t>();
        Object entry{{"slot", slot}, {"spell", spell}};
        if (spell > 0)
        {
            auto flags = r.take<std::uint16_t>();
            auto level = r.take<std::uint8_t>(), applications = r.take<std::uint8_t>();
            auto caster = flags & 8 ? unit : native_guid(r);
            Value duration;
            if (flags & 32)
                duration = r.unpack("ii");
            Array points;
            for (auto bit : {1, 2, 4})
                if ((flags & 64) && (flags & bit))
                    points.push_back(r.take<std::int32_t>());
            entry["flags"] = flags;
            entry["level"] = level;
            entry["applications"] = applications;
            entry["caster"] = caster;
            entry["duration"] = duration;
            entry["points"] = points;
        }
        entries.push_back(entry);
        if (entries.size() > 255)
            throw std::runtime_error("excessive native aura count");
    }
    r.end();
    bool all = name == "SMSG_AURA_UPDATE_ALL";
    if (all)
        owner.visible_auras.clear();
    Writer w;
    w.bits(all, 1).bits(entries.size(), 9).flush();
    for (auto const &entry : entries)
    {
        auto slot = integer(get(entry, "slot"));
        auto spell = signed_integer(get(entry, "spell"));
        w.pack("B", {slot}).bits(spell > 0, 1).flush();
        if (spell <= 0)
        {
            owner.visible_auras.erase(slot);
            continue;
        }
        owner.visible_auras[slot] = entry;
        auto flags = integer(get(entry, "flags")), caster = integer(get(entry, "caster"));
        auto modern = (caster == unit ? 1 : 0) | (flags & 16 ? 0x102 : 0) | (flags & 32 ? 4 : 0) |
                      (flags & 64 ? 8 : 0) | (flags & 128 ? 16 : 0);
        auto high = (47ull << 58) | (1ull << 42) | (static_cast<std::uint64_t>(owner.map()) << 29) |
                    (static_cast<std::uint64_t>(spell) << 6) | 13;
        w.guid(++owner.aura_serial, high)
            .pack("iiHIHBi",
                  {spell, 0, modern, flags & 7, get(entry, "level"), get(entry, "applications"), 0});
        bool has_caster = (caster == 0 || caster == unit) && caster != unit;
        auto const &duration = get(entry, "duration");
        auto const &points = get(entry, "points").as_array();
        w.bits(has_caster, 1)
            .bits(!duration.is_null(), 1)
            .bits(!duration.is_null(), 1)
            .bits(0, 1)
            .bits(points.size(), 6)
            .bits(0, 6)
            .bits(0, 1)
            .flush();
        if (has_caster)
            w.guid();
        if (!duration.is_null())
            w.pack("ii", duration.as_array());
        for (auto const &point : points)
            w.pack("f", {point});
    }
    return Packet{"SMSG_AURA_UPDATE", w.guid(unit, player_high()).finish()};
}
Bytes Protocol::aura_cancel(State const &owner, View body)
{
    Reader r(body);
    auto spell = r.take<std::uint32_t>();
    auto caster = r.guid();
    r.end();
    if (caster != Array{0, 0} && caster != Array{owner.guid(), player_high()})
        throw std::runtime_error("aura cancellation caster is not owned");
    for (auto const &[slot, aura] : owner.visible_auras)
        if (integer(get(aura, "spell")) == spell)
            return Writer().put(spell).finish();
    throw std::runtime_error("aura cancellation is not visible");
}
} // namespace bridge
