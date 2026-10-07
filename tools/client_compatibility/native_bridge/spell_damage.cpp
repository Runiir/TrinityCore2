#include "spell_damage.hpp"
#include <limits>

namespace bridge
{
Reply owned_spell_damage(State const &owner, View body)
{
    Reader r(body);
    auto target=native_guid(r),caster=native_guid(r);
    if(!owner.guid() || caster!=owner.guid() ||
       integer(get(owner.self_snapshot,"guid"))!=caster)
        return {};
    auto visible=owner.visible_units.find(target);
    if(visible==owner.visible_units.end() ||
       integer(get(visible->second,"kind"))!=3 ||
       integer(get(visible->second,"map"))!=owner.map())
        return {};
    auto spell=r.take<std::uint32_t>();
    // Native has no cast ID. Bind direct damage to the newest exact owned
    // request for this spell and visible target, using its native server ID.
    Value const *cast=nullptr;
    std::uint64_t newest=0;
    for(auto const &[counter,row]:owner.casts)
    {
        if(integer(get(row,"spell"))!=spell ||
           integer(get(row,"native_target"))!=target)
            continue;
        auto serial=integer(get(row,"server_guid").as_array().at(0));
        if(serial>newest){newest=serial;cast=&row;}
    }
    if(!cast)return {};
    auto damage=r.take<std::uint32_t>(),overkill=r.take<std::uint32_t>();
    auto school=r.take<std::uint8_t>();
    auto absorbed=r.take<std::uint32_t>(),resisted=r.take<std::uint32_t>();
    auto periodic=r.take<std::uint8_t>(),unused=r.take<std::uint8_t>();
    auto blocked=r.take<std::uint32_t>(),flags=r.take<std::uint32_t>();
    auto debug=r.take<std::uint8_t>();
    r.end();
    constexpr auto maximum=static_cast<std::uint32_t>(std::numeric_limits<std::int32_t>::max());
    if(damage>maximum || overkill>damage || absorbed>maximum ||
       resisted>maximum || blocked>maximum || !school || school>127 ||
       periodic || unused || debug || (flags&~2u))
        throw std::runtime_error("unsupported owned direct spell damage layout");
    // Pinned WPP442 CombatLogHandler.HandleSpellNonMeleeDmgLog. Native lacks
    // OriginalDamage and optional debug/log/scaling data; preserve defaults.
    Writer w;
    w.guid(Protocol::modern_guid(target,owner.map()))
        .guid(Protocol::modern_guid(caster,owner.map())).guid(get(*cast,"server_guid"))
        .pack("IIIII",{spell,get(*cast,"visual"),damage,0,overkill})
        .put(school).pack("III",{absorbed,resisted,blocked})
        .bits(0,1).bits(flags,7).bits(0,1).bits(0,1).bits(0,1);
    return Packet{"SMSG_SPELL_NON_MELEE_DAMAGE_LOG",w.finish()};
}
}
