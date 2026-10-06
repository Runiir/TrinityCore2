#include "pet_casts.hpp"
#include "cast_packets.hpp"
#include "spell_failures.hpp"
#include <chrono>

namespace bridge
{
struct PetCastState
{
    struct Cast
    {
        std::uint64_t pet,target;
        unsigned spell,map;
        Array identity;
        std::chrono::steady_clock::time_point expires;
    };
    std::optional<Cast> active,interrupted;
    bool failure_sent=false,other_sent=false;
};
namespace
{
using Clock=std::chrono::steady_clock;
unsigned visual(unsigned spell)
{
    // Positive public60895 SpellXSpellVisual records; native4.3.4 visual IDs
    // are a different table identity. No conditional visual is synthesized.
    return spell==3110 ? 238900 : 240306;
}
std::uint64_t field_guid(Protocol const &p,Value const &unit,char const *name)
{
    return static_cast<std::uint64_t>(p.field(unit,name)) |
        (static_cast<std::uint64_t>(p.field(unit,name,1))<<32);
}
bool visible_victim(Protocol const &p,State const &owner,std::uint64_t target)
{
    auto found=owner.visible_units.find(target);
    return target>>52==0xf13 && found!=owner.visible_units.end() &&
        integer(get(found->second,"kind"))==3 && integer(get(found->second,"map"))==owner.map() &&
        p.field(found->second,"UNIT_FIELD_HEALTH");
}
Reply response(Protocol const &p,State &owner,std::string const &name,View body)
{
    bool failed=name=="SMSG_SPELL_FAILURE" || name=="SMSG_SPELL_FAILED_OTHER";
    if(!failed && name!="SMSG_SPELL_START" && name!="SMSG_SPELL_GO")return {};
    Reader r(body);auto caster=native_guid(r);
    // Player/item and unrelated creature casts keep their existing path.
    if(caster>>52!=0xf14)return {};
    auto unit=failed ? caster : native_guid(r);
    auto counter=r.take<std::uint8_t>();auto spell=r.take<std::uint32_t>();
    if(caster!=unit || counter || !pet_cast_authority(p,owner,unit,spell))return {};
    if(failed)
    {
        auto native_reason=r.take<std::uint8_t>();r.end();
        if(!owner.pet_cast_state)return {};
        auto &s=*owner.pet_cast_state;
        auto context=s.active ? s.active : s.interrupted;
        if(!context || context->pet!=unit || context->spell!=spell || context->map!=owner.map() ||
           Clock::now()>context->expires)return {};
        auto reason=SPELL_FAILURES.find(native_reason);
        if(reason==SPELL_FAILURES.end())throw std::runtime_error("unmapped owned pet interruption");
        if(name=="SMSG_SPELL_FAILED_OTHER" && reason->second>255)
            throw std::runtime_error("owned pet interruption exceeds modern reason");
        bool &sent=name=="SMSG_SPELL_FAILURE" ? s.failure_sent : s.other_sent;
        if(sent)return {};
        Writer w;w.guid(Protocol::modern_guid(unit,owner.map())).guid(context->identity)
            .pack("iI",{spell,visual(spell)}).pack(name=="SMSG_SPELL_FAILURE" ? "H" : "B",{reason->second});
        s.interrupted=context;s.active.reset();sent=true;
        return Packet{name,w.finish()};
    }
    bool completed=name=="SMSG_SPELL_GO";
    CastPacket packet;packet.spell=spell;packet.visual=visual(spell);packet.map=owner.map();
    auto flags=r.take<std::uint32_t>();packet.extra=r.take<std::uint32_t>();packet.duration=r.take<std::uint32_t>();
    // Only the captured ordinary Firebolt/Blood Pact extensions. Native
    // NO_GCD is not modern FROM_CLIENT for a server-initiated pet autocast.
    if(packet.extra || (!completed && flags!=0x802) ||
       (completed && flags!=0x900 && !(spell==6307 && flags==0x40900)) ||
       (!completed && ((spell==6307 && packet.duration) || (spell==3110 && (!packet.duration || packet.duration>60000)))))
        throw std::runtime_error("unsupported owned pet cast flags or duration");
    packet.flags=flags&~0x40000u;
    if(completed)
    {
        auto count=r.take<std::uint8_t>();
        if(count!=1)throw std::runtime_error("unsupported owned pet hit count");
        packet.hits.push_back(r.take<std::uint64_t>());
        if(r.take<std::uint8_t>())throw std::runtime_error("owned pet misses require separate evidence");
    }
    packet.target_flags=r.take<std::uint32_t>();
    if(packet.target_flags&2)packet.target=native_guid(r);
    if(spell==3110)
    {
        if(packet.target_flags!=2 || !visible_victim(p,owner,packet.target) ||
           (completed && packet.hits[0]!=packet.target))
            throw std::runtime_error("owned Firebolt lacks its visible native victim");
        if(!completed && field_guid(p,owner.visible_units.at(unit),"UNIT_FIELD_TARGET")!=packet.target &&
           field_guid(p,owner.self_snapshot,"UNIT_FIELD_TARGET")!=packet.target)
            throw std::runtime_error("owned Firebolt victim differs from current native pet/owner target");
    }
    else if(packet.target_flags!=(completed ? 2u : 0u) || packet.target ||
            (completed && packet.hits[0]!=unit))
        throw std::runtime_error("unsupported owned Blood Pact targets");
    packet.remaining=r.take<std::uint32_t>();r.end();
    auto power=p.field(owner.visible_units.at(unit),"UNIT_FIELD_BYTES_0")>>24;
    if(power)throw std::runtime_error("owned pet spell requires the captured native mana power type");
    packet.remaining_type=0;
    if(!owner.pet_cast_state)owner.pet_cast_state=std::make_shared<PetCastState>();
    auto &s=*owner.pet_cast_state;
    if(completed)
    {
        if(!s.active || s.active->pet!=unit || s.active->spell!=spell || s.active->map!=owner.map() ||
           s.active->target!=packet.target || Clock::now()>s.active->expires)return {};
        packet.cast=s.active->identity;
    }
    else
    {
        auto high=(47ull<<58) | (1ull<<42) | (static_cast<std::uint64_t>(owner.map())<<29) |
            (static_cast<std::uint64_t>(spell)<<6) | 3;
        packet.cast={++owner.cast_serial,high};
    }
    packet.caster=packet.unit=Protocol::modern_guid(unit,owner.map());
    auto translated=cast_packet(packet,completed);
    if(completed)s.active.reset();
    else
    {
        s.active=PetCastState::Cast{unit,packet.target,spell,owner.map(),packet.cast,
            Clock::now()+std::chrono::milliseconds(packet.duration+5000)};
        s.interrupted.reset();s.failure_sent=s.other_sent=false;
    }
    return Packet{name,std::move(translated)};
}
}
PetActionTranslation translate_pet_cast(Protocol const &p,State &owner,std::string const &name,View body)
{
    try{return {response(p,owner,name,body),{}};}
    catch(std::exception const &e){return {{},e.what()};}
}
}
