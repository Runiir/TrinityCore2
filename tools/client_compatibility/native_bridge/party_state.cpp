// Native 4.3.4 change masks to pinned 4.4.2 PartyMemberFullState.
// Partial native updates merge into a per-session snapshot before serialization.
#include "protocol.hpp"

namespace bridge
{
namespace
{
void auras(Reader &r, std::map<unsigned, PartyAura> &out)
{
    bool full = r.take<std::uint8_t>();
    auto mask = r.take<std::uint64_t>();
    auto count = r.take<std::uint32_t>();
    if (count > 64 || (count < 64 && (mask >> count)))
        throw std::runtime_error("native party aura mask exceeds its bound");
    if (full) out.clear();
    for (unsigned slot = 0; slot < count; ++slot)
    {
        if (!(mask & (1ull << slot))) continue;
        PartyAura aura;
        aura.spell = r.take<std::int32_t>();aura.flags = r.take<std::uint16_t>();
        if (aura.flags & 64)
            for (unsigned effect = 0; effect < 3; ++effect)
            {
                auto amount = r.take<std::int32_t>();
                if (aura.flags & (1u << effect)) aura.points.push_back(static_cast<float>(amount));
            }
        if (aura.spell) out[slot] = std::move(aura);
        else out.erase(slot);
    }
}
void write_auras(Writer &w, std::map<unsigned, PartyAura> const &list)
{
    for (auto const &[slot, aura] : list)
    {
        (void)slot;
        auto flags = aura.flags;
        auto modern = (flags & 8 ? 1 : 0) | (flags & 16 ? 0x102 : 0) |
            (flags & 32 ? 4 : 0) | (flags & 64 ? 8 : 0) | (flags & 128 ? 16 : 0);
        w.pack("iHII", {aura.spell, modern, flags & 7, aura.points.size()});
        for (auto point : aura.points) w.put(point);
    }
}
Bytes encode(std::uint64_t guid, PartyState const &s)
{
    Writer w;w.bits(s.enemy,1).flush();
    // Only the home party is supported by the native realm. Modern-only tuning,
    // specialization and WMO placement fields have no native wire counterpart.
    w.pack("2BHBHii4H2HI3hiI", {1,0,s.status,s.power_type,0,s.health,s.max_health,
        s.power,s.max_power,s.level,0,s.zone,s.wmo,0,
        s.position[0],s.position[1],s.position[2],s.vehicle,s.auras.size()});
    w.pack("II", {s.phase_flags,s.phases.size()}).guid();
    for (auto phase : s.phases) w.pack("IH", {0,phase});
    w.zeros(12); // CTROptions, absent from the native protocol.
    write_auras(w,s.auras);
    w.bits(s.pet.guid != 0,1).flush();
    if (s.pet.guid)
    {
        if ((s.pet.guid>>52)!=0xf14) throw std::runtime_error("invalid native party pet GUID");
        // Native out-of-range pet stats contain no map identifier. Preserve the
        // counter and Pet type; map-specific visible pet objects are separate.
        w.guid(s.pet.guid&0xffffffff,(10ull<<58)|(1ull<<42))
            .pack("iiiI", {s.pet.model,s.pet.health,s.pet.max_health,s.pet.auras.size()});
        write_auras(w,s.pet.auras);
        if (s.pet.name.size()>255) throw std::runtime_error("native party pet name exceeds bound");
        w.bits(s.pet.name.size(),8).raw(s.pet.name);
    }
    return w.guid(guid,player_high()).finish();
}
}
Reply Protocol::party_state(State &owner, std::string const &name, View body)
{
    bool full = name == "SMSG_PARTY_MEMBER_FULL_STATE";
    if (!full && name != "SMSG_PARTY_MEMBER_STATE") return {};
    Reader r(body);bool enemy = full && r.take<std::uint8_t>();
    auto guid = native_guid(r);auto mask = r.take<std::uint32_t>();
    if (!guid || guid>0xffffffff) throw std::runtime_error("invalid native party member GUID");
    if (!owner.party_states.contains(guid) && owner.party_states.size()>=40)
        throw std::runtime_error("party state cache exceeds roster bound");
    auto &cached = owner.party_states[guid];
    auto s = full ? PartyState{} : cached;
    s.enemy = enemy;
    if (mask&1) s.status=r.take<std::uint16_t>();
    if (mask&2) s.health=r.take<std::int32_t>();
    if (mask&4) s.max_health=r.take<std::int32_t>();
    if (mask&8) s.power_type=r.take<std::uint8_t>();
    if (mask&16) s.power=r.take<std::uint16_t>();
    if (mask&32) s.max_power=r.take<std::uint16_t>();
    if (mask&64) s.level=r.take<std::uint16_t>();
    if (mask&128) s.zone=r.take<std::uint16_t>();
    if (mask&256) s.wmo=r.take<std::uint16_t>();
    if (mask&512) for (auto &p : s.position) p=r.take<std::int16_t>();
    if (mask&1024) auras(r,s.auras);
    if (mask&2048) s.pet.guid=r.take<std::uint64_t>();
    if (mask&4096) {auto text=native_text(r);s.pet.name.assign(text.begin(),text.end());}
    if (mask&8192) s.pet.model=r.take<std::uint16_t>();
    if (mask&16384) s.pet.health=r.take<std::int32_t>();
    if (mask&32768) s.pet.max_health=r.take<std::int32_t>();
    if (mask&65536) r.take<std::uint8_t>(); // Modern pet stats carry health, not power.
    if (mask&131072) r.take<std::uint16_t>();
    if (mask&262144) r.take<std::uint16_t>();
    if (mask&524288) auras(r,s.pet.auras);
    if (mask&1048576) s.vehicle=r.take<std::int32_t>();
    if (mask&2097152)
    {
        s.phase_flags=r.take<std::uint32_t>();auto count=r.take<std::uint32_t>();
        if (count>256) throw std::runtime_error("native party phase list exceeds bound");
        s.phases.clear();for (unsigned i=0;i<count;++i) s.phases.push_back(r.take<std::uint16_t>());
    }
    // The legacy builder sets reserved high mask bits without emitting fields.
    r.end();
    if (full) {s.initialized=true;s.requested=false;}
    cached=std::move(s);
    if (!cached.initialized)
    {
        if (!cached.requested && owner.native_send)
        {
            cached.requested=true;
            owner.native_send("CMSG_REQUEST_PARTY_MEMBER_STATS",Writer().put(guid).finish());
        }
        return {};
    }
    return Packet{"SMSG_PARTY_MEMBER_FULL_STATE",encode(guid,cached)};
}
} // namespace bridge
