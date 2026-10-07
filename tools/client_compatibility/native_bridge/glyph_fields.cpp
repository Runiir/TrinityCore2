// Owner-only glyph slots, values and enablement follow pinned WriteUpdate masks.
#include "protocol.hpp"
#include "glyph_slots.hpp"
namespace bridge
{
Bytes Protocol::glyph_block(Value const &snapshot,Value const &changed) const
{
    auto has=[&](char const *name,unsigned i=0)
    {return changed.as_object().contains(std::to_string(field_index(name)+i));};
    bool enabled=has("PLAYER_GLYPHS_ENABLED"),any=enabled;
    std::array<std::uint32_t,46> mask{};
    auto set=[&](unsigned bit){mask.at(bit/32)|=1u<<(bit%32);};
    if(enabled){set(102);set(127);}
    for(unsigned i=0;i<9;++i)
    {
        if(has("PLAYER_FIELD_GLYPH_SLOTS_1",i)){set(1410);set(1411+i);any=true;}
        if(has("PLAYER_FIELD_GLYPHS_1",i)){set(1410);set(1420+i);any=true;}
    }
    if(!any)return {};
    Writer data;data.pack("BBBI",{1,0,3,1u<<7});
    std::uint64_t present=0;for(unsigned i=0;i<46;++i)if(mask[i])present|=1ull<<i;
    data.put<std::uint32_t>(present).bits(present>>32,14);
    for(auto value:mask)if(value)data.bits(value,32);
    data.flush();
    if(enabled)
    {
        auto value=field(snapshot,"PLAYER_GLYPHS_ENABLED");
        if(value&~511u)throw std::runtime_error("native glyph enablement exceeds nine Classic slots");
        data.put<std::uint16_t>(value);
        // Group 102 writes optional presence even without member129. Preserve
        // the native stable catalog while glyph enablement changes.
        data.bits(!get(snapshot,"pet_stable").is_null(),1).flush();
    }
    for(unsigned i=0;i<9;++i)
    {
        if(has("PLAYER_FIELD_GLYPH_SLOTS_1",i))data.put(modern_glyph_slot(field(snapshot,"PLAYER_FIELD_GLYPH_SLOTS_1",i)));
        if(has("PLAYER_FIELD_GLYPHS_1",i))data.put(field(snapshot,"PLAYER_FIELD_GLYPHS_1",i));
    }
    return Writer().put<std::uint8_t>(0).guid(integer(get(snapshot,"guid")),player_high())
        .put<std::uint32_t>(data.data().size()).raw(data.data()).finish();
}
}
