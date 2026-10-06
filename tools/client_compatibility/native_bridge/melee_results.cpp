#include "melee_results.hpp"
#include <cmath>

namespace bridge
{
Reply owned_melee_result(State const &owner, View body)
{
    Reader r(body);
    auto flags=r.take<std::uint32_t>();
    auto attacker=native_guid(r),victim=native_guid(r);
    if(!owner.guid() || attacker!=owner.guid() ||
       integer(get(owner.self_snapshot,"guid"))!=attacker)
        return {};
    auto visible=owner.visible_units.find(victim);
    if(visible==owner.visible_units.end() ||
       integer(get(visible->second,"kind"))!=3 ||
       integer(get(visible->second,"map"))!=owner.map())
        return {};
    // Native and pinned60895 share these non-mitigation swing flags. Optional
    // absorb/resist/block and unknown layouts remain explicit unsupported cases.
    constexpr std::uint32_t rage=0x00800000;
    constexpr std::uint32_t supported=0x00000002|0x00000004|0x00000010|
        0x00000200|0x00010000|0x00020000|0x00040000|rage|0x01000000;
    if(flags&~supported)
        throw std::runtime_error("unsupported owned melee hit flags");
    auto damage=r.take<std::int32_t>(),overkill=r.take<std::int32_t>();
    auto count=r.take<std::uint8_t>();
    if(damage<0 || overkill< -1 || count>1)
        throw std::runtime_error("unsupported owned melee damage header");
    Writer round;
    round.put(flags).guid(Protocol::modern_guid(attacker,owner.map()))
        .guid(Protocol::modern_guid(victim,owner.map())).put(damage)
        // OriginalDamage is absent in native442. Preserve the modern struct's
        // default0; never invent a pre-mitigation amount from calculated damage.
        .put<std::int32_t>(0).put(overkill).put(count);
    if(count)
    {
        auto school=r.take<std::int32_t>();
        auto amount=r.take<float>();
        auto subdamage=r.take<std::int32_t>();
        if(school!=1 || !std::isfinite(amount) || amount<0 ||
           subdamage!=damage || amount!=static_cast<float>(subdamage))
            throw std::runtime_error("unsupported owned physical melee subdamage");
        round.put(school).put(amount).put(subdamage);
    }
    else if(damage)
        throw std::runtime_error("owned melee damage lacks its subdamage");
    auto victim_state=r.take<std::uint8_t>();
    auto attacker_state=r.take<std::uint32_t>(),spell=r.take<std::uint32_t>();
    if(victim_state>8 || attacker_state || spell || ((flags&0x10) && damage))
        throw std::runtime_error("unsupported owned melee state or spell");
    round.put(victim_state).put(attacker_state).put(spell);
    if(flags&rage)
    {
        auto gained=r.take<std::int32_t>();
        if(gained<0)throw std::runtime_error("negative owned melee rage gain");
        round.put(gained);
    }
    r.end();
    // ContentTuningParams is mandatory in60895. Native442 has no scaling
    // metadata; serialize every field with the pinned default, including bits.
    round.put<std::uint16_t>(0).put<std::int16_t>(0).put<std::uint32_t>(0)
        .zeros(5).bits(0,4).bits(0,1).flush();
    auto payload=round.finish();
    return Packet{"SMSG_ATTACKER_STATE_UPDATE",Writer().bits(0,1).flush()
        .put<std::uint32_t>(payload.size()).raw(payload).finish()};
}
} // namespace bridge
