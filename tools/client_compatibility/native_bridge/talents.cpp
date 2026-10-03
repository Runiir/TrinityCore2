// Native Player::BuildPlayerTalentsInfoData -> pinned Classic 60895 layout.
// Counts and rank widths changed; native allocation and glyphs stay authoritative.
#include "talents.hpp"
#include <set>

namespace bridge
{
Reply talent_response(std::string const &name,View body)
{
    if(name!="SMSG_TALENTS_INFO")return {};
    Reader r(body);auto pet=r.take<std::uint8_t>(),points=r.take<std::uint32_t>();
    if(pet>1 || points>100)throw std::runtime_error("invalid native talent header");
    // Pet talents have a separate native layout and require their own actor
    // qualification. Never interpret that layout as a player specialization.
    if(pet)throw std::runtime_error("native pet talent update is not yet translated");
    auto count=r.take<std::uint8_t>(),active=r.take<std::uint8_t>();
    if(count>2 || (count && active>=count) || (!count && active))
        throw std::runtime_error("invalid native talent specialization identity");
    Writer w;w.pack("IBI",{points,active,count});
    for(unsigned group=0;group<count;++group)
    {
        auto tree=r.take<std::uint32_t>();auto talents=r.take<std::uint8_t>();
        if(tree>0x7fffffff || talents>100)throw std::runtime_error("native talent group exceeds bounds");
        Array rows;std::set<std::uint32_t> seen;
        for(unsigned i=0;i<talents;++i)
        {
            auto id=r.take<std::uint32_t>();auto rank=r.take<std::uint8_t>();
            if(!id || id>0x7fffffff || rank>4 || !seen.insert(id).second)
                throw std::runtime_error("invalid native learned talent");
            rows.push_back(id);rows.push_back(rank);
        }
        auto glyphs=r.take<std::uint8_t>();
        if(glyphs!=9)throw std::runtime_error("native player talent update requires nine Classic glyph slots");
        auto glyphRows=r.unpack(std::string(glyphs,'H'));
        // The modern duplicate byte counts are retained along with the real
        // uint32 counts. SpecID is zero for single-spec, 1/2 for dual-spec.
        w.pack("BIBIBI",{talents,talents,glyphs,glyphs,count==1?0:group+1,tree})
            .pack(std::string(talents*2,'I'),rows).pack(std::string(glyphs,'H'),glyphRows);
    }
    r.end();return Packet{"SMSG_UPDATE_TALENT_DATA",w.bits(0,1).flush().finish()};
}
Reply talent_request(std::string const &name,View body)
{
    if(name=="CMSG_LEARN_TALENT")
    {
        Reader r(body);auto id=r.take<std::uint32_t>();auto rank=r.take<std::uint16_t>();r.end();
        if(!id || id>0x7fffffff || rank>4)throw std::runtime_error("invalid Classic talent learning request");
        return Packet{name,Writer().pack("II",{id,rank}).finish()};
    }
    if(name=="CMSG_SET_PRIMARY_TALENT_TREE")
    {
        Reader r(body);auto tree=r.take<std::int32_t>();r.end();
        if(tree<0 || tree>2)throw std::runtime_error("invalid Classic talent tree index");
        return Packet{name,Writer().put(tree).finish()};
    }
    return {};
}
}
