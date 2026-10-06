#include "chat_probe.hpp"
#include "chat_ignore.hpp"

namespace bridge
{
namespace
{
// One reviewed, stock-generated public fixture. Match the complete message,
// not a substring that could retain arbitrary text beside the owned item link.
constexpr std::string_view owned_item_link =
    "|cffffffff|Hitem:49778::::::::85:::::::::|h[Worn Greatsword]|h|r";

bool item_link_probe(std::string const &name, View body)
{
    try
    {
        Reader r(body);
        unsigned size = 0;
        bool native_response = false;
        if (name == "CMSG_CHAT_MESSAGE_SAY" || name == "CMSG_MESSAGECHAT_SAY")
        {
            if (r.take<std::int32_t>() != 7) return false;
            size = r.bits(name == "CMSG_CHAT_MESSAGE_SAY" ? 11 : 9);
            if (name == "CMSG_CHAT_MESSAGE_SAY") r.bits(1);
        }
        else if (name == "SMSG_MESSAGECHAT")
        {
            if (r.take<std::uint8_t>() != 1 || r.take<std::int32_t>() != 7 ||
                r.take<std::uint64_t>() != 1) return false;
            r.take<std::uint32_t>();
            auto target = r.take<std::uint64_t>();
            if (target != 0 && target != 1) return false;
            auto count = r.take<std::uint32_t>();
            if (count != owned_item_link.size() + 1) return false;
            size = count - 1;
            native_response = true;
        }
        else if (name == "SMSG_CHAT")
        {
            if (r.take<std::uint8_t>() != 1 || r.take<std::int32_t>() != 7) return false;
            auto sender = r.guid();
            if (integer(sender[0]) != 1) return false;
            r.guid(); r.guid(); r.guid();
            r.unpack("IIiHfi");
            for (auto bits : {11, 11, 5, 7}) if (r.bits(bits)) return false;
            size = r.bits(12);
            for (unsigned i = 0; i < 4; ++i) if (r.bits(1)) return false;
        }
        else return false;
        if (size != owned_item_link.size()) return false;
        auto raw = r.raw(size);
        if (std::string_view(reinterpret_cast<char const *>(raw.data()), raw.size()) != owned_item_link) return false;
        if (native_response)
        {
            if (r.take<std::uint8_t>()) return false;
            r.take<std::uint8_t>();
        }
        r.end();
        return true;
    }
    catch (std::exception const &) { return false; }
}
}

bool public_chat_probe(std::string const &name, View body)
{
    if (owned_ignore_probe(name, body)) return true;
    if (!(name.starts_with("CMSG_CHAT_MESSAGE_") || name.starts_with("CMSG_MESSAGECHAT_") ||
          name == "SMSG_CHAT" || name == "SMSG_MESSAGECHAT")) return false;
    if (item_link_probe(name, body)) return true;
    // Preserve the existing synthetic-marker policy. No trailing arbitrary text.
    std::string value(body.begin(), body.end());
    auto p = value.find("TC442UI:");
    if (p == std::string::npos) return false;
    auto start = p + 8, end = start;
    while (end < value.size() && ((value[end] >= 'a' && value[end] <= 'z') ||
           (value[end] >= 'A' && value[end] <= 'Z') || (value[end] >= '0' && value[end] <= '9') ||
           value[end] == '_' || value[end] == '-')) ++end;
    if (end <= start || end - start > 64) return false;
    if (end == value.size()) return true;
    if (value[end] != '\0') return false;
    if (name == "SMSG_MESSAGECHAT") return end + 2 == value.size();
    return end + 1 == value.size();
}
}
