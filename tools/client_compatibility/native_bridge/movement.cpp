#include "protocol.hpp"
#include <cmath>
#include <unordered_set>

namespace bridge
{
std::uint32_t modern_flags2(std::uint32_t native)
{
    return (native & 0x3f) | (native & 0x400 ? 0x100 : 0);
}
bool movement_supported(std::string const &name)
{
    static std::unordered_set<std::string> const names = []
    {
        std::unordered_set<std::string> result;
        for (auto suffix : {"START_FORWARD",
                            "START_BACKWARD",
                            "STOP",
                            "START_STRAFE_LEFT",
                            "START_STRAFE_RIGHT",
                            "STOP_STRAFE",
                            "START_TURN_LEFT",
                            "START_TURN_RIGHT",
                            "STOP_TURN",
                            "JUMP",
                            "FALL_LAND",
                            "HEARTBEAT",
                            "SET_FACING",
                            "SET_PITCH",
                            "SET_RUN_MODE",
                            "SET_WALK_MODE",
                            "START_PITCH_UP",
                            "START_PITCH_DOWN",
                            "STOP_PITCH",
                            "START_SWIM",
                            "STOP_SWIM",
                            "START_ASCEND",
                            "START_DESCEND",
                            "STOP_ASCEND",
                            "SET_FLY"})
            result.insert(std::string("CMSG_MOVE_") + suffix);
        return result;
    }();
    return names.contains(name);
}
Value movement_parse(View body, std::uint64_t wanted)
{
    Reader r(body);
    if (r.guid() != Array{wanted, player_high()})
        throw std::runtime_error("movement GUID is not the active player");
    auto flags = r.take<std::uint32_t>(), flags2 = r.take<std::uint32_t>(), flags3 = r.take<std::uint32_t>(),
         timestamp = r.take<std::uint32_t>();
    auto coordinates = r.unpack("6f");
    auto forces = r.take<std::uint32_t>();
    r.take<std::uint32_t>();
    if (forces > 16)
        throw std::runtime_error("excessive movement forces");
    for (unsigned i = 0; i < forces; ++i)
        r.guid();
    std::array<bool, 8> presence;
    for (auto &p : presence)
        p = r.bits(1);
    constexpr unsigned allowed = 0x3f | 0x100 | 0x200 | 0x400 | 0x8000;
    if (presence[1] || presence[3] || presence[6] || presence[7] || flags3 || flags >= (1u << 30) ||
        (flags2 & ~allowed))
        throw std::runtime_error("unsupported movement transport/spline/advanced flags");
    if ((flags2 & 0x8000) && !((flags & 0x800) && presence[2]))
        throw std::runtime_error("falling movement hint without fall state");
    flags2 = (flags2 & 0x3f) | (flags2 & 0x100 ? 0x400 : 0);
    Object result{{"flags", flags},
                  {"flags2", flags2},
                  {"time", timestamp},
                  {"position", Array{coordinates[0], coordinates[1], coordinates[2], coordinates[3]}},
                  {"pitch", coordinates[4]},
                  {"fall", presence[2]},
                  {"fall_direction", false},
                  {"fall_time", 0},
                  {"zspeed", 0},
                  {"sin", 0},
                  {"cos", 0},
                  {"xyspeed", 0},
                  {"standing_gameobject", nullptr}};
    if (presence[0])
    {
        auto identity = r.guid();
        if (!integer(identity[0]) || integer(identity[1]) >> 58 != 11)
            throw std::runtime_error("standing movement identity is not a game object");
        result["standing_gameobject"] = identity;
    }
    if (presence[2])
    {
        result["fall_time"] = r.take<std::uint32_t>();
        result["zspeed"] = r.take<float>();
        result["fall_direction"] = static_cast<bool>(r.bits(1));
        if (truth(result["fall_direction"]))
        {
            result["sin"] = r.take<float>();
            result["cos"] = r.take<float>();
            result["xyspeed"] = r.take<float>();
        }
    }
    r.end();
    for (auto const &v : coordinates)
        if (!std::isfinite(number(v)))
            throw std::runtime_error("invalid movement coordinates");
    for (auto name : {"zspeed", "xyspeed"})
        if (!std::isfinite(number(result[name])))
            throw std::runtime_error("invalid movement coordinates");
    for (unsigned i = 0; i < 3; ++i)
        if (std::abs(number(coordinates[i])) > 17067)
            throw std::runtime_error("invalid movement coordinates");
    return result;
}
void Protocol::validate_standing(State const &owner, Value const &movement) const
{
    auto const &identity = get(movement, "standing_gameobject");
    if (identity.is_null() || !truth(identity))
        return;
    for (auto const &[guid, record] : owner.visible_gameobjects)
    {
        if (modern_guid(guid, integer(get(record, "map"))) != identity.as_array())
            continue;
        auto kind = (field(record, "GAMEOBJECT_BYTES_1") >> 8) & 255;
        if (kind == 11 || kind == 15)
            throw std::runtime_error("standing movement on transports is unsupported");
        return;
    }
    throw std::runtime_error("standing game object is not visible to the owned character");
}
Packet Protocol::movement_encode(std::string name, std::uint64_t guid, Value const &m, bool ack) const
{
    std::string native = name == "CMSG_MOVE_SET_FLY" ? "CMSG_MOVE_SET_CAN_FLY"
                         : ack                       ? name
                                                     : "MSG_" + name.substr(5);
    if ((!ack && !movement_supported(name)) || !sequences.as_object().contains(native))
        throw std::runtime_error("unsupported movement opcode");
    auto octets = Writer().put(guid).finish();
    auto flags = integer(get(m, "flags")), flags2 = integer(get(m, "flags2"));
    auto const &position = get(m, "position").as_array();
    std::unordered_map<std::string, bool> present = {
        {"MovementFlags", flags != 0},
        {"MovementFlags2", flags2 != 0},
        {"Timestamp", true},
        {"Orientation", std::abs(number(position[3])) > 1e-6},
        {"Pitch", (flags & (0x200000 | 0x1000000)) || (flags2 & 0x10)},
        {"SplineElevation", false}};
    std::unordered_map<std::string, std::pair<char, Value>> values = {
        {"Timestamp", {'I', get(m, "time")}},
        {"Orientation", {'f', position[3]}},
        {"Pitch", {'f', get(m, "pitch")}},
        {"FallTime", {'I', get(m, "fall_time")}},
        {"FallVerticalSpeed", {'f', get(m, "zspeed")}},
        {"FallSinAngle", {'f', get(m, "sin")}},
        {"FallCosAngle", {'f', get(m, "cos")}},
        {"FallHorizontalSpeed", {'f', get(m, "xyspeed")}}};
    Writer w;
    for (auto const &item : get(sequences, native).as_array())
    {
        auto e = str(item).substr(3);
        if (e == "End")
            break;
        if (e == "FlushBits")
            w.flush();
        else if (e.starts_with("HasGuidByte"))
            w.bits(octets[e.back() - '0'] != 0, 1);
        else if (e.starts_with("GuidByte"))
        {
            auto n = octets[e.back() - '0'];
            if (n)
                w.put<std::uint8_t>(n ^ 1);
        }
        else if (e == "ZeroBit" || e == "HasTransportData" || e == "HasSpline" ||
                 e == "HasHeightChangeFailed")
            w.bits(0, 1);
        else if (e == "Counter" && ack)
            w.put<std::uint32_t>(integer(get(m, "ack_index")));
        else if (e == "ExtraElement" && ack)
            w.put<float>(number(get(m, "ack_speed")));
        else if (e.find("Transport") != std::string::npos || e == "HasVehicleId")
            continue;
        else if (e == "HasFallData")
            w.bits(truth(get(m, "fall")), 1);
        else if (e == "HasFallDirection")
        {
            if (truth(get(m, "fall")))
                w.bits(truth(get(m, "fall_direction")), 1);
        }
        else if (e.starts_with("Has") && present.contains(e.substr(3)))
            w.bits(!present.at(e.substr(3)), 1);
        else if (e == "MovementFlags")
        {
            if (flags)
                w.bits(flags, 30);
        }
        else if (e == "MovementFlags2")
        {
            if (flags2)
                w.bits(flags2, 12);
        }
        else if (e.starts_with("Position"))
            w.put<float>(number(position[std::string("XYZ").find(e.back())]));
        else if (e == "SplineElevation")
            continue;
        else if (values.contains(e))
        {
            if (e.starts_with("Fall"))
            {
                if (!truth(get(m, "fall")) ||
                    ((e == "FallSinAngle" || e == "FallCosAngle" || e == "FallHorizontalSpeed") &&
                     !truth(get(m, "fall_direction"))))
                    continue;
            }
            else if (!present.at(e))
                continue;
            auto const &[fmt, value] = values.at(e);
            w.pack(std::string(1, fmt), {value});
        }
        else
            throw std::runtime_error("unsupported movement sequence element: " + e);
    }
    return {native, w.finish()};
}
namespace
{
std::unordered_map<std::string, std::string> controls()
{
    std::unordered_map<std::string, std::string> result = {
        {"SMSG_MOVE_SET_CAN_FLY", "CMSG_MOVE_SET_CAN_FLY_ACK"},
        {"SMSG_MOVE_UNSET_CAN_FLY", "CMSG_MOVE_SET_CAN_FLY_ACK"},
        {"SMSG_MOVE_SET_CAN_TRANSITION_BETWEEN_SWIM_AND_FLY", "CMSG_MOVE_ENABLE_SWIM_TO_FLY_TRANS_ACK"},
        {"SMSG_MOVE_UNSET_CAN_TRANSITION_BETWEEN_SWIM_AND_FLY", "CMSG_MOVE_ENABLE_SWIM_TO_FLY_TRANS_ACK"}};
    for (auto suffix : {"RUN_SPEED", "RUN_BACK_SPEED", "FLIGHT_SPEED", "FLIGHT_BACK_SPEED", "SWIM_SPEED",
                        "SWIM_BACK_SPEED", "WALK_SPEED"})
        result[std::string("SMSG_MOVE_SET_") + suffix] =
            std::string("CMSG_MOVE_FORCE_") + suffix + "_CHANGE_ACK";
    return result;
}
auto const CONTROLS = controls();
} // namespace
Reply Protocol::movement_control(State &owner, std::string const &name, View body) const
{
    if (!CONTROLS.contains(name))
        return {};
    Reader r(body);
    std::array<std::uint8_t, 8> octets{};
    std::array<bool, 8> present{};
    Value counter, speed;
    for (auto const &item : get(sequences, name).as_array())
    {
        auto e = str(item).substr(3);
        if (e == "End")
            break;
        if (e.starts_with("HasGuidByte"))
            present[e.back() - '0'] = r.bits(1);
        else if (e.starts_with("GuidByte"))
        {
            auto i = e.back() - '0';
            if (present[i])
                octets[i] = r.take<std::uint8_t>() ^ 1;
        }
        else if (e == "Counter")
            counter = r.take<std::uint32_t>();
        else if (e == "ExtraElement")
            speed = r.take<float>();
        else if (e == "FlushBits")
            r.align();
        else
            throw std::runtime_error("unsupported native movement control");
    }
    r.end();
    Reader gr(octets);
    if (gr.take<std::uint64_t>() != owner.guid())
        return {};
    if (counter.is_null() ||
        (!speed.is_null() && (!std::isfinite(number(speed)) || number(speed) <= 0 || number(speed) > 100)))
        throw std::runtime_error("invalid native movement control");
    if (owner.pending_movement.size() > 64)
        throw std::runtime_error("unacknowledged movement controls exceed bound");
    owner.pending_movement[integer(counter)] = Object{{"ack", CONTROLS.at(name)}, {"speed", speed}};
    Writer w;
    w.guid(owner.guid(), player_high()).pack("I", {counter});
    if (!speed.is_null())
        w.pack("f", {speed});
    auto modern = name == "SMSG_MOVE_SET_CAN_TRANSITION_BETWEEN_SWIM_AND_FLY"
                      ? "SMSG_MOVE_ENABLE_TRANSITION_BETWEEN_SWIM_AND_FLY"
                  : name == "SMSG_MOVE_UNSET_CAN_TRANSITION_BETWEEN_SWIM_AND_FLY"
                      ? "SMSG_MOVE_DISABLE_TRANSITION_BETWEEN_SWIM_AND_FLY"
                      : name;
    return Packet{modern, w.finish()};
}
Packet Protocol::movement_ack(State &owner, std::string const &name, View body) const
{
    auto suffix = name.find("SPEED") != std::string::npos ? 8u : 4u;
    if (body.size() < suffix)
        throw std::runtime_error("truncated movement acknowledgement");
    Reader r(body.last(suffix));
    auto counter = r.take<std::uint32_t>();
    Value speed;
    if (suffix == 8)
        speed = r.take<float>();
    auto p = owner.pending_movement.find(counter);
    if (p == owner.pending_movement.end() || str(get(p->second, "ack")) != name ||
        (!speed.is_null() &&
         (!std::isfinite(number(speed)) || std::abs(number(speed) - number(get(p->second, "speed"))) > .001)))
        throw std::runtime_error("foreign or mismatched movement acknowledgement");
    auto state = movement_parse(body.first(body.size() - suffix), owner.guid());
    validate_standing(owner, state);
    state.as_object()["ack_index"] = counter;
    state.as_object()["ack_speed"] = speed;
    auto result = movement_encode(name == "CMSG_MOVE_ENABLE_SWIM_TO_FLY_TRANS_ACK"
                                      ? "CMSG_MOVE_SET_CAN_TRANSITION_BETWEEN_SWIM_AND_FLY_ACK"
                                      : name,
                                  owner.guid(), state, true);
    owner.pending_movement.erase(p);
    return result;
}
} // namespace bridge
