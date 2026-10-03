#include "protocol.hpp"
#include "currency.hpp"

namespace bridge
{
Reply Protocol::initialize_response(State &owner, std::string const &name, View body)
{
    Reader r(body);
    Writer w;
    if (name == "SMSG_SEND_KNOWN_SPELLS")
    {
        auto initial = r.take<std::uint8_t>();
        auto count = r.take<std::uint16_t>();
        if (initial > 1 || count > 16000)
            throw std::runtime_error("invalid native spell list");
        Array spells;
        for (unsigned i = 0; i < count; ++i)
        {
            spells.push_back(r.take<std::uint32_t>());
            r.take<std::int16_t>();
        }
        auto cooldowns = r.take<std::uint16_t>();
        r.raw(cooldowns * 18);
        r.end();
        if (cooldowns)
            throw std::runtime_error("native initial cooldown translation is not implemented");
        w.bits(initial, 1).pack("II", {count, 0}).pack(std::string(count, 'I'), spells);
    }
    else if (name == "SMSG_LEARNED_SPELL")
    {
        auto spell=r.take<std::uint32_t>(),unused=r.take<std::uint32_t>();r.end();
        if(!spell || spell>0x7fffffff || unused)throw std::runtime_error("invalid native learned spell");
        // Pinned LearnedSpells: count, specialization, suppress-messaging bit,
        // followed by SpellID and four absent favorite/optional flags.
        w.pack("2I",{1,0}).bits(0,1).flush().pack("i",{spell}).bits(0,4).flush();
        return Packet{"SMSG_LEARNED_SPELLS",w.finish()};
    }
    else if (name == "SMSG_UPDATE_ACTION_BUTTONS")
    {
        if (body.size() != 577 || body.back() > 2)
            throw std::runtime_error("invalid native action buttons");
        owner.action_buttons = r.unpack("144I");
        for (unsigned i = 0; i < 36; ++i)
            owner.action_buttons.push_back(0);
        w.pack("180Q", owner.action_buttons).put(r.take<std::uint8_t>());
    }
    else if (name == "SMSG_SET_PROFICIENCY")
    {
        auto kind = r.take<std::uint8_t>();
        auto mask = r.take<std::uint32_t>();
        r.end();
        w.pack("IB", {mask, kind});
    }
    else if (name == "SMSG_SEND_UNLEARN_SPELLS")
    {
        auto count = r.take<std::uint32_t>();
        if (count > 16000)
            throw std::runtime_error("invalid unlearned spell count");
        r.raw(count * 4);
        r.end();
        w.raw(body);
    }
    else
        return {};
    return Packet{name, w.finish()};
}
Reply Protocol::currency_response(std::string const &name, View body)
{
    Reader r(body);
    Writer w;
    if (name == "SMSG_SETUP_CURRENCY")
    {
        auto count = r.bits(23);
        if (count > 1024)
            throw std::runtime_error("currency count exceeds bound");
        std::vector<Array> flags;
        for (unsigned i = 0; i < count; ++i)
            flags.push_back({r.bits(1), r.bits(4), r.bits(1), r.bits(1)});
        w.pack("I", {count});
        for (auto const &f : flags)
        {
            auto quantity = r.take<std::uint32_t>();
            Value maximum, tracked, weekly;
            if (truth(f[2]))
                maximum = r.take<std::uint32_t>();
            if (truth(f[3]))
                tracked = r.take<std::uint32_t>();
            auto kind = r.take<std::uint32_t>();
            if (truth(f[0]))
                weekly = r.take<std::uint32_t>();
            w.pack("ii", {modern_currency(kind), quantity})
                .bits(integer(f[0]), 1)
                .bits(integer(f[2]), 1)
                .bits(integer(f[3]), 1)
                .bits(0, 4)
                .bits(integer(f[1]), 5)
                .flush();
            for (auto const &value : {weekly, maximum, tracked})
                if (!value.is_null())
                    w.pack("I", {value});
        }
        r.end();
    }
    else if (name == "SMSG_SET_CURRENCY")
    {
        auto weekly = r.bits(1), tracked = r.bits(1), suppress = r.bits(1);
        Value tracked_value, weekly_value;
        if (tracked)
            tracked_value = r.take<std::int32_t>();
        auto quantity = r.take<std::int32_t>(), kind = r.take<std::int32_t>();
        if (weekly)
            weekly_value = r.take<std::int32_t>();
        r.end();
        w.pack("iiII", {modern_currency(kind), quantity, 0, 0});
        for (auto bit : std::array<std::uint64_t, 12>{weekly, tracked, 0, 0, suppress, 0, 0, 0, 0, 0, 0, 0})
            w.bits(bit, 1);
        w.flush();
        if (!weekly_value.is_null())
            w.pack("i", {weekly_value});
        if (!tracked_value.is_null())
            w.pack("i", {tracked_value});
    }
    else
        return {};
    return Packet{name, w.finish()};
}
} // namespace bridge
