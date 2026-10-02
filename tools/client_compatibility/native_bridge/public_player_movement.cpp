#include "protocol.hpp"
#include <cmath>

namespace bridge
{
Reply Protocol::public_player_movement(State &owner, View body) const
{
    Reader r(body);
    std::array<std::uint8_t, 8> guid{}, transport_guid{};
    Object m{{"flags", 0}, {"flags2", 0}, {"time", 0}, {"position", Array{0, 0, 0, 0}},
             {"pitch", 0}, {"SplineElevation", 0}, {"fall", false}, {"fall_direction", false},
             {"fall_time", 0}, {"zspeed", 0}, {"sin", 0}, {"cos", 0}, {"xyspeed", 0}};
    std::unordered_map<std::string, bool> present;
    std::unordered_map<std::string, std::string> names{{"MovementFlags", "flags"},
        {"MovementFlags2", "flags2"}, {"Timestamp", "time"}, {"Pitch", "pitch"},
        {"SplineElevation", "SplineElevation"}, {"FallTime", "fall_time"},
        {"FallVerticalSpeed", "zspeed"}, {"FallSinAngle", "sin"},
        {"FallCosAngle", "cos"}, {"FallHorizontalSpeed", "xyspeed"}};
    // Decode the pinned native sequence. Its optional scalar presence bits are
    // inverted; GUID, fall and transport bits are positive.
    for (auto const &token : get(sequences, "SMSG_MOVE_UPDATE").as_array())
    {
        auto e = str(token).substr(3);
        if (e == "End") break;
        if (e == "FlushBits") { r.align(); continue; }
        if (e.starts_with("HasTransport") || e == "HasVehicleId")
        {
            if (e == "HasTransportData" || present["TransportData"])
                present[e.substr(3)] = r.bits(1);
            continue;
        }
        if (e.starts_with("HasGuidByte"))
            guid[e.back() - '0'] = r.bits(1);
        else if (e.starts_with("GuidByte"))
        {
            auto &octet = guid[e.back() - '0'];
            if (octet) octet = r.take<std::uint8_t>() ^ 1;
        }
        else if (e == "HasFallData") m["fall"] = static_cast<bool>(r.bits(1));
        else if (e == "HasFallDirection")
        {
            if (truth(m["fall"])) m["fall_direction"] = static_cast<bool>(r.bits(1));
        }
        else if (e == "HasSpline" || e == "HasHeightChangeFailed")
            present[e.substr(3)] = r.bits(1);
        else if (e.starts_with("Has")) present[e.substr(3)] = !r.bits(1);
        else if (e == "MovementFlags" || e == "MovementFlags2")
        {
            if (present[e]) m[names.at(e)] = r.bits(e == "MovementFlags" ? 30 : 12);
        }
        else if (e.starts_with("Transport"))
        {
            if (!present["TransportData"]) continue;
            if (e.starts_with("TransportGuidByte"))
            {
                if (present[e]) transport_guid[e.back() - '0'] = r.take<std::uint8_t>() ^ 1;
            }
            else if (e == "TransportSeat") r.take<std::int8_t>();
            else if (e == "TransportTime") r.take<std::uint32_t>();
            else if (e == "TransportTime2" || e == "TransportVehicleId")
            {
                if (present[e == "TransportTime2" ? "TransportTime2" : "VehicleId"])
                    r.take<std::uint32_t>();
            }
            else r.take<float>();
        }
        else if (e.starts_with("Position"))
            m["position"].as_array()[e.back() == 'X' ? 0 : e.back() == 'Y' ? 1 : 2] = r.take<float>();
        else if (e == "Orientation")
        {
            if (present[e]) m["position"].as_array()[3] = r.take<float>();
        }
        else if (names.contains(e))
        {
            bool has = e.starts_with("Fall") ? truth(m["fall"]) : present[e];
            if (e == "FallSinAngle" || e == "FallCosAngle" || e == "FallHorizontalSpeed")
                has = has && truth(m["fall_direction"]);
            if (has) m[names.at(e)] = e == "Timestamp" || e == "FallTime"
                ? Value(r.take<std::uint32_t>()) : Value(r.take<float>());
        }
        else throw std::runtime_error("unsupported native public movement element");
    }
    r.end();
    std::uint64_t identity = 0;
    for (unsigned i = 0; i < 8; ++i) identity |= std::uint64_t(guid[i]) << (i * 8);
    if (!identity || identity > 0xffffffff)
        throw std::runtime_error("invalid native public player movement identity");
    auto const &position = m["position"].as_array();
    for (unsigned i = 0; i < 4; ++i)
        if (!std::isfinite(number(position[i])) || (i < 3 && std::abs(number(position[i])) > 17067))
            throw std::runtime_error("invalid native public player movement coordinates");
    for (auto key : {"pitch", "SplineElevation", "zspeed", "sin", "cos", "xyspeed"})
        if (!std::isfinite(number(m[key])))
            throw std::runtime_error("invalid native public player movement coordinates");
    auto record = owner.visible_units.find(identity);
    if (record == owner.visible_units.end() || integer(get(record->second, "kind")) != 4 ||
        identity == owner.guid() || present["TransportData"])
        return {}; // Public visibility is required; transport motion remains unqualified.
    auto map = integer(get(record->second, "map"));
    auto &cached = record->second.as_object()["movement"].as_object();
    for (auto const &[key, value] : m) cached[key] = value;
    Writer w;
    w.guid(modern_guid(identity, map)).pack("IIII6fII", {m["flags"], modern_flags2(integer(m["flags2"])),
        0, m["time"], position[0], position[1], position[2], position[3], m["pitch"],
        m["SplineElevation"], 0, 0});
    // Modern transport, spline, height-failure, inertia and advanced flight are absent.
    w.bits(0, 2).bits(truth(m["fall"]), 1).bits(0, 5).flush();
    if (truth(m["fall"]))
    {
        w.pack("If", {m["fall_time"], m["zspeed"]}).bits(truth(m["fall_direction"]), 1).flush();
        if (truth(m["fall_direction"])) w.pack("3f", {m["sin"], m["cos"], m["xyspeed"]});
    }
    return Packet{"SMSG_MOVE_UPDATE", w.finish()};
}
} // namespace bridge
