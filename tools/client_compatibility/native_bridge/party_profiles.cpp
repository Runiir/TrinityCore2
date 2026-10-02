// Native and pinned modern CUF profile packets use different bit orders and options.
#include "protocol.hpp"
#include <array>

namespace bridge
{
namespace
{
constexpr std::array<unsigned,21> modern_options{0,1,2,5,6,7,8,10,9,24,25,26,13,14,15,16,17,18,19,22,23};
constexpr std::array<unsigned,25> load_order{26,16,15,18,3,23,10,19,14,4,7,13,9,2,25,21,8,6,20,5,0,24,17,1,22};
constexpr std::array<unsigned,25> save_order{21,16,26,3,20,22,6,17,19,1,15,5,13,25,9,2,4,14,7,8,24,23,10,18,0};
struct Profile
{
    std::string name;
    std::array<bool,27> options{};
    unsigned length=0;
    std::uint16_t height=0,width=0,top_offset=0,bottom_offset=0,left_offset=0;
    std::uint8_t sort=0,health=0,top=0,bottom=0,left=0;
};
void bounds(unsigned count)
{
    if(count>5)throw std::runtime_error("CUF profile count exceeds native bound");
}
void modern_fields(Writer &w,Profile const &p)
{
    w.pack("2H5B3H",{p.height,p.width,p.sort,p.health,p.top,p.bottom,p.left,
        p.top_offset,p.bottom_offset,p.left_offset}).raw(p.name);
}
}
Reply Protocol::party_profiles(std::string const &name,View body)
{
    bool load=name=="SMSG_LOAD_CUF_PROFILES",save=name=="CMSG_SAVE_CUF_PROFILES";
    if(!load && !save)return {};
    Reader r(body);Writer w;
    auto count=load ? r.bits(20) : r.take<std::uint32_t>();bounds(count);
    std::vector<Profile> profiles(count);
    if(load)
    {
        for(auto &p:profiles)
            for(unsigned i=0;i<load_order.size();++i)
            {
                if(i==19)p.length=r.bits(8);
                p.options[load_order[i]]=r.bits(1);
            }
        for(auto &p:profiles)
        {
            p.left_offset=r.take<std::uint16_t>();p.height=r.take<std::uint16_t>();
            p.bottom_offset=r.take<std::uint16_t>();p.bottom=r.take<std::uint8_t>();
            p.top_offset=r.take<std::uint16_t>();p.top=r.take<std::uint8_t>();
            p.health=r.take<std::uint8_t>();p.sort=r.take<std::uint8_t>();
            p.width=r.take<std::uint16_t>();p.left=r.take<std::uint8_t>();
            if(p.length>127)throw std::runtime_error("CUF profile name exceeds modern bound");
            auto text=r.raw(p.length);p.name.assign(text.begin(),text.end());
        }
        w.put<std::uint32_t>(count);
        for(auto const &p:profiles)
        {
            w.bits(p.name.size(),7);
            for(auto option:modern_options)w.bits(p.options[option],1);
            modern_fields(w,p);
        }
    }
    else
    {
        for(auto &p:profiles)
        {
            p.length=r.bits(7);
            for(auto option:modern_options)p.options[option]=r.bits(1);
            // These two activation gates were removed from modern CUF settings.
            // A modern profile applies to both native talent specializations.
            p.options[20]=p.options[21]=true;
            p.height=r.take<std::uint16_t>();p.width=r.take<std::uint16_t>();
            p.sort=r.take<std::uint8_t>();p.health=r.take<std::uint8_t>();
            p.top=r.take<std::uint8_t>();p.bottom=r.take<std::uint8_t>();p.left=r.take<std::uint8_t>();
            p.top_offset=r.take<std::uint16_t>();p.bottom_offset=r.take<std::uint16_t>();p.left_offset=r.take<std::uint16_t>();
            auto text=r.raw(p.length);p.name.assign(text.begin(),text.end());
        }
        w.bits(count,20);
        for(auto const &p:profiles)
            for(unsigned i=0;i<save_order.size();++i)
            {
                if(i==21)w.bits(p.name.size(),8);
                w.bits(p.options[save_order[i]],1);
            }
        for(auto const &p:profiles)
            w.pack("B",{p.top}).raw(p.name).pack("4H3BHB",{p.bottom_offset,p.height,p.width,p.top_offset,
                p.health,p.bottom,p.sort,p.left_offset,p.left});
    }
    r.end();return Packet{name,w.finish()};
}
} // namespace bridge
