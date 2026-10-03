// Owner watched-faction creation and deltas retain the native signed sentinel.
#include "reputation_fields.hpp"

namespace bridge
{
std::int32_t watched_faction_index(Protocol const &protocol,Value const &snapshot)
{
    auto value=protocol.field(snapshot,"PLAYER_FIELD_WATCHED_FACTION_INDEX");
    if(value==0xffffffffu)return -1;
    if(value>=256)throw std::runtime_error("native watched faction exceeds index bound");
    return static_cast<std::int32_t>(value);
}
Bytes watched_faction_block(Protocol const &protocol,Value const &snapshot,Value const &changed)
{
    if(!changed.as_object().contains(std::to_string(protocol.field_index("PLAYER_FIELD_WATCHED_FACTION_INDEX"))))
        return {};
    // Pinned ActivePlayerData::WriteUpdate: group 96, scalar 97. The field is
    // signed int32; native uint32 0xffffffff means no watched faction, not 0.
    Writer data;data.pack("BBBI",{1,0,3,1u<<7}).pack("I",{1u<<3})
        .bits(0,14).bits(3,32).flush().put(watched_faction_index(protocol,snapshot));
    return Writer().put<std::uint8_t>(0).guid(integer(get(snapshot,"guid")),player_high())
        .put<std::uint32_t>(data.data().size()).raw(data.data()).finish();
}
}
