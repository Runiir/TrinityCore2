#include "protocol.hpp"

namespace bridge
{
Reply Protocol::transfer_response(State &owner, std::string const &name, View body)
{
    Reader r(body);
    Writer w;
    if (name == "MSG_MOVE_TELEPORT")
    {
        std::array<bool, 8> present{};
        std::array<std::uint8_t, 8> octets{};
        for (unsigned i : {6, 0, 3, 2})
            present[i] = r.bits(1);
        if (r.bits(1))
            throw std::runtime_error("vehicle teleport is not implemented");
        auto transport = r.bits(1);
        present[1] = r.bits(1);
        if (transport)
            throw std::runtime_error("transport teleport is not implemented");
        for (unsigned i : {4, 7, 5})
            present[i] = r.bits(1);
        auto seq = r.take<std::uint32_t>();
        auto read = [&](std::initializer_list<unsigned> indices)
        {
            for (auto i : indices)
                if (present[i])
                    octets[i] = r.take<std::uint8_t>() ^ 1;
        };
        read({1, 2, 3, 5});
        auto x = r.take<float>();
        read({4});
        auto o = r.take<float>();
        read({7});
        auto z = r.take<float>();
        read({0, 6});
        auto y = r.take<float>();
        r.end();
        Reader gr(octets);
        auto guid = gr.take<std::uint64_t>();
        if (guid != owner.guid())
            return {};
        owner.pending_near = Object{{"sequence", seq}, {"position", Array{x, y, z, o}}};
        return Packet{"SMSG_MOVE_TELEPORT",
                      w.guid(guid, player_high()).pack("I4fB", {seq, x, y, z, o, 0}).bits(0, 2).finish()};
    }
    if (name == "SMSG_TRANSFER_PENDING")
    {
        auto spell = r.bits(1), ship = r.bits(1);
        Array vessel;
        Value spell_id;
        if (ship)
            vessel = r.unpack("iI");
        if (spell)
            spell_id = r.take<std::int32_t>();
        auto target = r.take<std::int32_t>();
        r.end();
        auto position = owner.latest_movement.empty()
                            ? get(get(owner.self_snapshot, "movement"), "position").as_array()
                            : owner.latest_movement;
        owner.pending_far = Object{{"map", target}, {"stage", "pending"}};
        w.pack("i3f", {target, position[0], position[1], position[2]}).bits(ship, 1).bits(spell, 1);
        if (ship)
            w.pack("Ii", {vessel[1], vessel[0]});
        if (spell)
            w.pack("i", {spell_id});
        return Packet{name, w.finish()};
    }
    if (name == "SMSG_SUSPEND_TOKEN")
    {
        auto seq = r.take<std::uint32_t>();
        auto reason = r.bits(1);
        r.end();
        if (owner.pending_far.is_null())
            throw std::runtime_error("suspend without a native transfer");
        auto &pending = owner.pending_far.as_object();
        pending["sequence"] = seq;
        pending["reason"] = reason;
        pending["stage"] = "suspended";
        return Packet{name, w.pack("I", {seq}).bits(reason, 2).finish()};
    }
    if (name == "SMSG_NEW_WORLD")
    {
        auto x = r.take<float>(), o = r.take<float>(), z = r.take<float>();
        auto target = r.take<std::int32_t>();
        auto y = r.take<float>();
        r.end();
        if (owner.pending_far.is_null() || signed_integer(get(owner.pending_far, "map")) != target ||
            str(get(owner.pending_far, "stage")) != "acknowledged")
            throw std::runtime_error("new world without a matching native transfer");
        auto &pending = owner.pending_far.as_object();
        pending["position"] = Array{x, y, z, o};
        pending["stage"] = "new_world";
        owner.character.as_object()["map"] = target;
        owner.created = false;
        owner.visible_gameobjects.clear();
        owner.visible_units.clear();
        owner.taxi_menu = nullptr;
        owner.gossip_menu = nullptr;
        owner.pending_near = nullptr;
        owner.latest_movement = Array{x, y, z, o};
        return Packet{name,
                      w.pack("i4fI3fi", {target, x, y, z, o, 16, 0, 0, 0, pending["sequence"]}).finish()};
    }
    return {};
}
Packet Protocol::transfer_request(State &owner, std::string const &name, View body)
{
    Reader r(body);
    Writer w;
    if (name == "CMSG_MOVE_TELEPORT_ACK")
    {
        auto identity = r.guid();
        auto seq = r.take<std::uint32_t>(), ticks = r.take<std::uint32_t>();
        r.end();
        if (identity != Array{owner.guid(), player_high()} || owner.pending_near.is_null() ||
            seq != integer(get(owner.pending_near, "sequence")))
            throw std::runtime_error("unmatched teleport acknowledgement");
        auto octets = Writer().put(owner.guid()).finish();
        w.pack("II", {seq, ticks});
        for (unsigned i : {5, 0, 1, 6, 3, 7, 2, 4})
            w.bits(octets[i] != 0, 1);
        for (unsigned i : {4, 2, 7, 6, 5, 1, 3, 0})
            if (octets[i])
                w.put<std::uint8_t>(octets[i] ^ 1);
        owner.latest_movement = get(owner.pending_near, "position").as_array();
        owner.pending_near = nullptr;
        return {"MSG_MOVE_TELEPORT_ACK", w.finish()};
    }
    if (name == "CMSG_SUSPEND_TOKEN_RESPONSE")
    {
        auto seq = r.take<std::uint32_t>();
        r.end();
        if (owner.pending_far.is_null() || seq != integer(get(owner.pending_far, "sequence")) ||
            str(get(owner.pending_far, "stage")) != "suspended")
            throw std::runtime_error("unmatched suspend acknowledgement");
        owner.pending_far.as_object()["stage"] = "acknowledged";
        return {name, Bytes(body.begin(), body.end())};
    }
    if (name == "CMSG_WORLD_PORT_RESPONSE")
    {
        r.end();
        if (owner.pending_far.is_null() || str(get(owner.pending_far, "stage")) != "new_world")
            throw std::runtime_error("unmatched world port acknowledgement");
        owner.pending_far.as_object()["stage"] = "entering";
        return {"MSG_MOVE_WORLDPORT_ACK", {}};
    }
    throw std::runtime_error("unknown transfer acknowledgement");
}
Reply Protocol::transfer_resume(State &owner)
{
    if (!owner.pending_far.is_null() && str(get(owner.pending_far, "stage")) == "entering")
    {
        auto result = Writer()
                          .pack("I", {get(owner.pending_far, "sequence")})
                          .bits(integer(get(owner.pending_far, "reason")), 2)
                          .finish();
        owner.pending_far = nullptr;
        return Packet{"SMSG_RESUME_TOKEN", result};
    }
    return {};
}
} // namespace bridge
