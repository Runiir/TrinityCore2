#include "player_ui_state.hpp"

namespace bridge
{
std::optional<Packet> actionbar_toggle_request(View body, bool in_world)
{
    Reader reader(body);
    auto toggles = reader.take<std::uint8_t>();
    reader.end();
    // Native STATUS_AUTHED permits the harmless zero initialization before login.
    if (!in_world && toggles == 0)
        return std::nullopt;
    if (!in_world)
        throw std::runtime_error("action-bar toggle outside owned active world");
    return Packet{"CMSG_SET_ACTIONBAR_TOGGLES", Writer().pack("B", {toggles}).finish()};
}
}
