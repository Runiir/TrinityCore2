#include "protocol.hpp"

namespace bridge
{
Bytes Protocol::rest_block(Value const &snapshot, Value const &changed) const
{
    auto const &changes = changed.as_object();
    bool threshold = changes.contains(std::to_string(field_index("PLAYER_REST_STATE_EXPERIENCE")));
    bool state = changes.contains(std::to_string(field_index("PLAYER_BYTES_2")));
    if (!threshold && !state)
        return {};
    // Pinned ActivePlayerData::WriteUpdate: group 310, XP RestInfo element 311.
    // Honor rest has no counterpart in the 4.3.4 backend and is not updated here.
    Writer data;
    data.pack("BBBI", {1, 0, 3, 1u << 7})
        .pack("I", {1u << 9})
        .bits(0, 14)
        .bits((1u << (310 % 32)) | (1u << (311 % 32)), 32)
        .flush();
    data.bits(1u | (threshold ? 2u : 0u) | (state ? 4u : 0u), 3).flush();
    if (threshold)
        data.pack("I", {field(snapshot, "PLAYER_REST_STATE_EXPERIENCE")});
    if (state)
        data.pack("B", {field(snapshot, "PLAYER_BYTES_2") >> 24});
    return Writer()
        .pack("B", {0})
        .guid(integer(get(snapshot, "guid")), player_high())
        .put<std::uint32_t>(data.data().size())
        .raw(data.data())
        .finish();
}
} // namespace bridge
