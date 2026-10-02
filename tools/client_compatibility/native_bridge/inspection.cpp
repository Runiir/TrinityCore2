// Pinned modern InspectPackets/TalentPackets and native MiscHandler/Player serializers.
#include "peer_identity.hpp"
#include "guild_fields.hpp"

namespace bridge
{
Reply Protocol::inspect_request(State &owner,std::string const &name,View body)
{
    if(name!="CMSG_INSPECT")return {};
    Reader r(body);auto guid=visible_player(owner,r.guid());r.end();
    if(!guid)return {};
    owner.inspect_target=guid;
    return Packet{name,Writer().put(guid).finish()};
}
Reply Protocol::inspect_response(State &owner,std::string const &name,View body) const
{
    if(name!="SMSG_INSPECT_TALENT")return {};
    Reader r(body);auto guid=r.take<std::uint64_t>();
    auto peer=owner.visible_units.find(guid);
    if(guid!=owner.inspect_target || peer==owner.visible_units.end() || integer(get(peer->second,"kind"))!=4)return {};
    auto free=r.take<std::uint32_t>();auto groups=r.take<std::uint8_t>(),active=r.take<std::uint8_t>();
    if(groups>2 || (groups && active>=groups))throw std::runtime_error("invalid native inspect talent groups");
    Writer talents;talents.pack("IBI",{free,active,groups});unsigned primary=0;
    for(unsigned i=0;i<groups;++i)
    {
        auto tree=r.take<std::uint32_t>();auto count=r.take<std::uint8_t>();Array ranks;
        if(i==active)primary=tree;
        if(count>128)throw std::runtime_error("invalid native inspect talent count");
        for(unsigned j=0;j<count;++j)
        {
            auto id=r.take<std::uint32_t>();auto rank=r.take<std::uint8_t>();
            if(!id || rank>4)throw std::runtime_error("invalid native inspect talent");
            ranks.push_back(id);ranks.push_back(rank);
        }
        auto glyph_count=r.take<std::uint8_t>();
        if(glyph_count>9)throw std::runtime_error("invalid native inspect glyph count");
        auto glyphs=r.unpack(std::string(glyph_count,'H'));
        talents.pack("BIBIBI",{count,count,glyph_count,glyph_count,i,tree})
            .pack(std::string(count*2,'I'),ranks).pack(std::string(glyph_count,'H'),glyphs);
    }
    talents.bits(0,1).flush();
    auto mask=r.take<std::uint32_t>();
    if(mask>=1u<<19)throw std::runtime_error("invalid native inspect equipment mask");
    std::vector<Bytes> items;
    for(unsigned i=0;i<19;++i)if(mask&(1u<<i))
    {
        auto entry=r.take<std::uint32_t>();auto enchants=r.take<std::uint16_t>();Array values;
        if(!entry || enchants>=1u<<13)throw std::runtime_error("invalid native inspect equipment");
        for(unsigned j=0;j<13;++j)if(enchants&(1u<<j))
        {values.push_back(r.take<std::uint16_t>());values.push_back(j);}
        auto property=r.take<std::int16_t>();auto creator=native_guid(r);auto seed=r.take<std::uint32_t>();
        if(creator>0xffffffff)throw std::runtime_error("invalid native inspect creator");
        Writer item;item.guid(creator,creator?player_high():0).pack("BII",{i,0,0})
            .pack("iii",{entry,static_cast<std::int32_t>(seed),property}).bits(0,1).flush().bits(0,6).flush()
            .bits(1,1).bits(values.size()/2,4).bits(0,2).flush();
        for(unsigned j=0;j<values.size();j+=2)item.pack("IB",{values[j],values[j+1]});
        items.push_back(item.finish());
    }
    Array guild;Value members=0;
    if(r.remaining())
    {
        guild=guild_identity(r.take<std::uint64_t>());r.take<std::uint32_t>();r.take<std::uint64_t>();
        members=r.take<std::uint32_t>();
    }
    r.end();
    auto const &profile=get(peer->second,"public_character");auto label=str(get(profile,"name"));
    if(label.empty() || label.size()>63 || !profile.as_object().contains("gender"))
        throw std::runtime_error("missing public inspection profile");
    auto identity=field(peer->second,"UNIT_FIELD_BYTES_0");Writer w;
    w.guid(guid,player_high()).pack("iI",{primary,items.size()}).bits(label.size(),6)
        .pack("BBBI",{get(profile,"gender"),identity&255,(identity>>8)&255,0}).raw(label);
    for(auto const &item:items)w.raw(item);
    // Native inspection carries no PvP statistics. Their separate request is pending.
    w.pack("IiBHHII3H",{3,0,0,0,0,0,0,0,0,0}).raw(talents.finish())
        .bits(!guild.empty(),1).bits(0,1).flush();
    for(unsigned i=0;i<9;++i)w.pack("B",{i}).zeros(16*4).bits(0,1).flush();
    if(!guild.empty())w.guid(guild).pack("ii",{members,0});
    owner.inspect_target=0;
    return Packet{"SMSG_INSPECT_RESULT",w.finish()};
}
} // namespace bridge
