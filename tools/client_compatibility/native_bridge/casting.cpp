#include "protocol.hpp"
#include "spell_failures.hpp"
#include <unordered_set>
#include <cmath>

namespace bridge
{
namespace
{
unsigned reason(unsigned native)
{
    auto pos = SPELL_FAILURES.find(native);
    if (pos == SPELL_FAILURES.end())
        throw std::runtime_error("unmapped native cast failure");
    return pos->second;
}
} // namespace
Packet Protocol::cast_request(State &owner, View body) const
{
    Reader r(body);
    auto cast = r.guid();
    auto misc0 = r.take<std::int32_t>(), misc1 = r.take<std::int32_t>(), spell = r.take<std::int32_t>();
    auto visual = r.take<std::uint32_t>();
    auto pitch = r.take<float>(), speed = r.take<float>();
    auto crafting = r.guid();
    auto craft_fields = r.unpack("IIIB");
    if (crafting != Array{0, 0} || misc1 || pitch || speed || truth(craft_fields[0]) ||
        truth(craft_fields[1]) || truth(craft_fields[2]) || truth(craft_fields[3]))
        throw std::runtime_error("unsupported crafting/trajectory cast");
    auto flags = r.bits(5), moving = r.bits(1), weights = r.bits(2), order = r.bits(1);
    r.align();
    auto target_flags = r.bits(28);
    auto source = r.bits(1), dest = r.bits(1), orientation = r.bits(1), map = r.bits(1), name_len = r.bits(7);
    auto unit = r.guid(), item = r.guid();
    bool marker=spell>=84996 && spell<=85000 && target_flags==64;
    Array destination;
    if(marker)
    {
        if(source || !dest || unit!=Array{0,0})throw std::runtime_error("invalid raid marker ground target");
        if(r.guid()!=Array{0,0})throw std::runtime_error("transport raid marker is unsupported");
        destination=r.unpack("3f");
        for(auto const &coordinate:destination)
            if(!std::isfinite(number(coordinate)) || std::abs(number(coordinate))>17066.667)
                throw std::runtime_error("invalid raid marker destination");
        if(orientation && !std::isfinite(r.take<float>()))throw std::runtime_error("invalid ground orientation");
        if(map)
        {
            auto target_map=r.take<std::int32_t>();
            if(target_map!=-1 && target_map!=static_cast<std::int32_t>(owner.map()))
                throw std::runtime_error("raid marker targets another map");
        }
    }
    if (source || (!marker && (dest || orientation || map)) || name_len || weights || order || item != Array{0, 0})
        throw std::runtime_error("unsupported cast target");
    auto target = (target_flags & 2) ? owner.guid() : 0;
    if (target_flags == 2048 && spell == 73979)
    {
        target = owned_gameobject(owner, unit);
        static std::unordered_set<unsigned> const finds = {203071, 203078, 204282, 206836, 202655,
                                                           207187, 207188, 207189, 207190};
        if (!finds.contains((target >> 32) & 0xfffff))
            throw std::runtime_error("gather target is not an archaeology find");
    }
    else if (!marker && ((unit != Array{0, 0} && unit != Array{owner.guid(), player_high()}) || (target_flags & ~2u)))
        throw std::runtime_error("unsupported or foreign cast target");
    if (moving)
    {
        auto state = movement_parse(r.raw(r.remaining()), owner.guid());
        auto [name, encoded] = movement_encode("CMSG_MOVE_HEARTBEAT", owner.guid(), state);
        owner.native_send(name, encoded);
    }
    r.end();
    if (spell <= 0 || integer(cast[1]) >> 58 != 47 || (flags & (marker ? 2 : 10)))
        throw std::runtime_error("invalid cast identity/flags");
    owner.cast_counter = owner.cast_counter % 255 + 1;
    auto high = (47ull << 58) | (1ull << 42) | (static_cast<std::uint64_t>(owner.map()) << 29) |
                (static_cast<std::uint64_t>(spell) << 6) | 3;
    owner.casts[owner.cast_counter] = Object{{"guid", cast},
                                             {"server_guid", Array{++owner.cast_serial, high}},
                                             {"spell", spell},
                                             {"visual", visual},
                                             {"native_target", target}};
    Writer w;
    w.pack("BiiBI", {owner.cast_counter, spell, misc0, flags, target_flags});
    if (target_flags & (2 | 2048))
        packed(w, target);
    if(marker)w.put<std::uint8_t>(0).pack("3f",destination);
    return {"CMSG_CAST_SPELL", w.finish()};
}
Reply Protocol::cast_prepare(State &owner, View body)
{
    Reader r(body);
    auto caster = native_guid(r), unit = native_guid(r);
    auto counter = r.take<std::uint8_t>();
    auto spell = r.take<std::int32_t>();
    auto p = owner.casts.find(counter);
    if (caster == unit && unit == owner.guid() && p != owner.casts.end() &&
        signed_integer(get(p->second, "spell")) == spell)
    {
        p->second.as_object()["prepared"] = true;
        return Packet{"SMSG_SPELL_PREPARE",
                      Writer().guid(get(p->second, "guid")).guid(get(p->second, "server_guid")).finish()};
    }
    return {};
}
Reply Protocol::cast_response(State &owner, std::string const &name, View body) const
{
    if (name != "SMSG_SPELL_START" && name != "SMSG_SPELL_GO" && name != "SMSG_CAST_FAILED" &&
        name != "SMSG_SPELL_FAILURE" && name != "SMSG_SPELL_FAILED_OTHER")
        return {};
    Reader r(body);
    if (name == "SMSG_SPELL_FAILURE" || name == "SMSG_SPELL_FAILED_OTHER")
    {
        auto caster = native_guid(r);
        auto counter = r.take<std::uint8_t>();
        auto spell = r.take<std::int32_t>();
        auto failed = r.take<std::uint8_t>();
        r.end();
        auto p = owner.casts.find(counter);
        if (caster != owner.guid() || p == owner.casts.end() ||
            signed_integer(get(p->second, "spell")) != spell)
            return {};
        auto modern = reason(failed);
        if (name == "SMSG_SPELL_FAILED_OTHER" && modern > 255)
            throw std::runtime_error("cast interruption does not fit modern reason");
        Writer w;
        w.guid(caster, player_high())
            .guid(get(p->second, "server_guid"))
            .pack("iI", {spell, get(p->second, "visual")});
        return Packet{name, w.pack(name == "SMSG_SPELL_FAILURE" ? "H" : "B", {modern}).finish()};
    }
    if (name == "SMSG_CAST_FAILED")
    {
        auto counter = r.take<std::uint8_t>();
        auto spell = r.take<std::int32_t>();
        auto failed = r.take<std::uint8_t>();
        auto p = owner.casts.find(counter);
        if (p == owner.casts.end() || signed_integer(get(p->second, "spell")) != spell)
            return {};
        auto args = r.unpack(std::string(r.remaining() / 4, 'i'));
        r.end();
        args.push_back(0);
        args.push_back(0);
        auto const &cast = p->second;
        return Packet{name,
                      Writer()
                          .guid(truth(get(cast, "prepared")) ? get(cast, "server_guid") : get(cast, "guid"))
                          .pack("iIiii", {spell, get(cast, "visual"), reason(failed), args[0], args[1]})
                          .finish()};
    }
    auto caster = native_guid(r), unit = native_guid(r);
    auto counter = r.take<std::uint8_t>();
    auto spell = r.take<std::int32_t>();
    auto flags = r.take<std::uint32_t>(), extra = r.take<std::uint32_t>(), duration = r.take<std::uint32_t>();
    auto p = owner.casts.find(counter);
    if (caster != owner.guid() || unit != caster || p == owner.casts.end() ||
        signed_integer(get(p->second, "spell")) != spell)
        return {};
    auto const &cast = p->second;
    std::vector<std::uint64_t> hits;
    if (name == "SMSG_SPELL_GO")
    {
        auto count = r.take<std::uint8_t>();
        for (unsigned i = 0; i < count; ++i)
            hits.push_back(r.take<std::uint64_t>());
        if (r.take<std::uint8_t>())
            throw std::runtime_error("missed self-cast targets are unsupported");
    }
    auto target_flags = r.take<std::uint32_t>();
    auto target = (target_flags & (2 | 2048)) ? native_guid(r) : 0;
    Value source, dest;
    if (target_flags & 32)
    {
        if (native_guid(r))
            throw std::runtime_error("transport source is unsupported");
        source = r.unpack("3f");
    }
    if (target_flags & 64)
    {
        if (native_guid(r))
            throw std::runtime_error("transport destination is unsupported");
        dest = r.unpack("3f");
    }
    std::unordered_set<std::uint64_t> allowed = {0, caster, integer(get(cast, "native_target"))};
    if ((target_flags & ~(98u | 2048u)) || !allowed.contains(target))
        throw std::runtime_error("unexpected self-cast result targets");
    for (auto hit : hits)
        if (!allowed.contains(hit))
            throw std::runtime_error("unexpected self-cast result targets");
    Value remaining;
    if (flags & 0x800)
        remaining = r.take<std::uint32_t>();
    auto dest_index = !dest.is_null() && name == "SMSG_SPELL_GO" ? r.take<std::uint8_t>() : 0;
    auto immunity = flags & 0x4000000 ? r.unpack("ii") : Array{0, 0};
    r.end();
    Writer w;
    w.guid(caster, player_high()).guid(unit, player_high()).guid(get(cast, "server_guid")).guid();
    w.pack("iIIII", {spell, get(cast, "visual"), flags | 0x40000, extra, duration})
        .pack("IfBii", {0, 0, dest_index, immunity[0], immunity[1]});
    w.pack("iB", {0, 0})
        .guid()
        .bits(hits.size(), 16)
        .bits(0, 16)
        .bits(0, 16)
        .bits(!remaining.is_null(), 9)
        .bits(0, 1)
        .bits(0, 16)
        .bits(0, 2)
        .flush();
    w.bits(target_flags, 28)
        .bits(!source.is_null(), 1)
        .bits(!dest.is_null(), 1)
        .bits(0, 2)
        .bits(0, 7)
        .guid(modern_guid(target, owner.map()))
        .guid();
    if (!source.is_null())
        w.guid().pack("3f", source.as_array());
    if (!dest.is_null())
        w.guid().pack("3f", dest.as_array());
    for (auto hit : hits)
        w.guid(modern_guid(hit, owner.map()));
    if (!remaining.is_null())
        w.pack("bi", {1, remaining});
    if (name == "SMSG_SPELL_GO")
        w.bits(0, 1).flush();
    return Packet{name, w.finish()};
}
Bytes Protocol::cast_rejected(View body)
{
    Reader r(body);
    auto identity = r.guid();
    r.take<std::int32_t>();
    r.take<std::int32_t>();
    auto spell = r.take<std::int32_t>();
    auto visual = r.take<std::uint32_t>();
    if (integer(identity[1]) >> 58 != 47 || spell <= 0)
        return {};
    return Writer().guid(identity).pack("iIiii", {spell, visual, reason(13), 0, 0}).finish();
}
Bytes Protocol::cast_cancel(State const &owner, View body)
{
    Reader r(body);
    auto identity = r.guid();
    auto spell = r.take<std::uint32_t>();
    r.end();
    for (auto const &[counter, cast] : owner.casts)
        if ((identity == get(cast, "guid").as_array() || identity == get(cast, "server_guid").as_array()) &&
            integer(get(cast, "spell")) == spell)
            return Writer().pack("BI", {counter, spell}).finish();
    throw std::runtime_error("cancel does not match an owned cast");
}
} // namespace bridge
