// Wire contracts: pinned Trinity cata_classic SocialPackets and native SocialMgr.
#include "protocol.hpp"
#include <algorithm>

namespace bridge
{
namespace
{
std::string text(View v, unsigned maximum)
{
    if (v.size() > maximum || std::find(v.begin(), v.end(), 0) != v.end())
        throw std::runtime_error("invalid social text");
    return std::string(v.begin(), v.end());
}
std::uint64_t player(Reader &r)
{
    auto g = r.guid();auto low = integer(g[0]), high = integer(g[1]);
    if (!low || low > 0xffffffff || high != player_high())
        throw std::runtime_error("invalid social player GUID");
    return low;
}
void identity(Writer &w, std::uint64_t guid)
{
    w.guid(guid, guid ? player_high() : 0).guid().pack("II", {1, 1});
}
}
Reply Protocol::social_request(std::string const &name, View body)
{
    Reader r(body);Writer w;std::string native;
    if (name == "CMSG_SEND_CONTACT_LIST")
    {
        auto flags = r.take<std::uint32_t>();r.end();
        if (flags & ~7u) throw std::runtime_error("invalid contact flags");
        return Packet{"CMSG_CONTACT_LIST", Writer().put(flags).finish()};
    }
    if (name == "CMSG_ADD_FRIEND" || name == "CMSG_ADD_IGNORE")
    {
        auto length = r.bits(9);auto notes = name == "CMSG_ADD_FRIEND" ? r.bits(9) : 0;
        if (name == "CMSG_ADD_IGNORE") r.guid();
        auto value = text(r.raw(length), 127);auto note = text(r.raw(notes), 511);r.end();
        if (value.empty()) throw std::runtime_error("empty contact name");
        w.raw(value).put<std::uint8_t>(0);
        if (name == "CMSG_ADD_FRIEND") w.raw(note).put<std::uint8_t>(0);
        return Packet{name, w.finish()};
    }
    if (name == "CMSG_DEL_FRIEND" || name == "CMSG_DEL_IGNORE" || name == "CMSG_SET_CONTACT_NOTES")
    {
        auto realm = r.take<std::uint32_t>();
        if (realm != 1) throw std::runtime_error("contact belongs to another realm");
        w.put(player(r));
        if (name == "CMSG_SET_CONTACT_NOTES")
        {
            auto length = r.bits(10);w.raw(text(r.raw(length), 511)).put<std::uint8_t>(0);
        }
        r.end();return Packet{name, w.finish()};
    }
    return {};
}
Reply Protocol::social_response(std::string const &name, View body)
{
    if (name != "SMSG_CONTACT_LIST" && name != "SMSG_FRIEND_STATUS") return {};
    Reader r(body);Writer w;
    if (name == "SMSG_CONTACT_LIST")
    {
        auto flags = r.take<std::uint32_t>(), count = r.take<std::uint32_t>();
        if (flags & ~7u || count > 255) throw std::runtime_error("invalid native contact list");
        w.put(flags).bits(count, 8).flush();
        for (unsigned i = 0; i < count; ++i)
        {
            auto guid = r.take<std::uint64_t>();auto type = r.take<std::uint32_t>();
            auto note = native_text(r);std::uint8_t status = 0;std::uint32_t area = 0, level = 0, cls = 0;
            if (type & 1)
            {
                status = r.take<std::uint8_t>();
                if (status) {area = r.take<std::uint32_t>();level = r.take<std::uint32_t>();cls = r.take<std::uint32_t>();}
            }
            if (guid > 0xffffffff || note.size() > 1023) throw std::runtime_error("invalid contact entry");
            identity(w, guid);w.pack("IBIII", {type, status, area, level, cls}).bits(note.size(), 10).raw(note);
        }
    }
    else
    {
        auto result = r.take<std::uint8_t>();auto guid = r.take<std::uint64_t>();
        Bytes note;std::uint8_t status = 0;std::uint32_t area = 0, level = 0, cls = 0;
        if (result == 6 || result == 7) note = native_text(r);
        if (result == 6 || result == 2)
        {status = r.take<std::uint8_t>();area = r.take<std::uint32_t>();level = r.take<std::uint32_t>();cls = r.take<std::uint32_t>();}
        if (guid > 0xffffffff || note.size() > 1023) throw std::runtime_error("invalid friend status");
        w.put(result).guid(guid, guid ? player_high() : 0).guid().pack("IBIII", {1, status, area, level, cls})
            .bits(note.size(), 10).raw(note);
    }
    r.end();return Packet{name, w.finish()};
}
} // namespace bridge
