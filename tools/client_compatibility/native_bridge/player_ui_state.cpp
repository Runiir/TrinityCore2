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
Packet stand_state_request(View body, bool in_world)
{
    if (!in_world) throw std::runtime_error("stand-state request outside owned active world");
    Reader reader(body);auto state=reader.take<std::uint8_t>();reader.end();
    // Match the native client's permitted player requests, excluding chairs/death.
    if (state!=0 && state!=1 && state!=3 && state!=8)
        throw std::runtime_error("unsupported player stand-state request");
    return {"CMSG_STANDSTATECHANGE",Writer().pack("I",{state}).finish()};
}
Packet stand_state_update(View body)
{
    Reader reader(body);auto state=reader.take<std::uint8_t>();reader.end();
    if (state>9)throw std::runtime_error("invalid native stand state");
    // Native has no animation-kit field. Preserve its state with the neutral kit.
    return {"SMSG_STAND_STATE_UPDATE",Writer().pack("BI",{state,0}).finish()};
}
Packet sheath_request(View body, bool in_world)
{
    if (!in_world) throw std::runtime_error("sheath request outside owned active world");
    Reader reader(body);auto state=reader.take<std::uint32_t>();
    auto animation=reader.take<std::uint8_t>();reader.end();
    if (state>2 || (animation&0x7f))
        throw std::runtime_error("invalid player sheath request");
    // The pinned modern packet adds one Animate bit. Native takes only the state;
    // its authoritative UNIT_FIELD_BYTES_2 update drives the resulting weapon pose.
    return {"CMSG_SET_SHEATHED",Writer().pack("I",{state}).finish()};
}
}
