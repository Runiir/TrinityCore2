#include "chat_ignore.hpp"
#include <array>

namespace bridge
{
namespace
{
std::string owned_name(std::uint64_t guid)
{
    if (guid == 1) return "Harnessone";
    if (guid == 2) return "Harnesstwo";
    return {};
}
bool local_player(Array const &guid)
{
    return guid.size() == 2 && integer(guid[0]) > 0 &&
        integer(guid[0]) <= 0xffffffff && integer(guid[1]) == player_high();
}
bool owned_guid(Array const &guid)
{
    return local_player(guid) && !owned_name(integer(guid[0])).empty();
}
bool exact_text(Reader &r, unsigned size, std::string const &expected)
{
    if (size != expected.size()) return false;
    auto value = r.raw(size);
    return std::string(value.begin(), value.end()) == expected;
}
bool owned_notice(std::string const &name, View body)
{
    Reader r(body);
    if (r.take<std::uint8_t>() != 25 || r.take<std::int32_t>() != 0) return false;
    if (name == "SMSG_MESSAGECHAT" || name == "SMSG_GM_MESSAGECHAT")
    {
        auto guid = r.take<std::uint64_t>();auto expected = owned_name(guid);
        if (expected.empty() || r.take<std::uint32_t>() != 0) return false;
        expected.push_back('\0');
        if (name == "SMSG_GM_MESSAGECHAT" && !exact_text(r, r.take<std::uint32_t>(), expected)) return false;
        if (r.take<std::uint64_t>() != guid || !exact_text(r, r.take<std::uint32_t>(), expected)) return false;
        r.take<std::uint8_t>();r.end();return true;
    }
    if (name != "SMSG_CHAT") return false;
    auto sender = r.guid();
    if (!owned_guid(sender)) return false;
    auto expected = owned_name(integer(sender[0]));
    auto guild = r.guid(), account = r.guid(), target = r.guid();
    if (integer(guild[0]) || integer(guild[1]) || integer(account[0]) ||
        integer(account[1]) || target != sender) return false;
    if (r.take<std::uint32_t>() != 0x01010001 || r.take<std::uint32_t>() != 0x01010001 ||
        r.take<std::int32_t>() != 0) return false;
    r.take<std::uint16_t>();
    if (r.take<float>() != 0 || r.take<std::int32_t>() != 0) return false;
    auto sender_size = r.bits(11), target_size = r.bits(11), prefix_size = r.bits(5),
        channel_size = r.bits(7), message_size = r.bits(12);
    for (unsigned i = 0; i < 4; ++i) if (r.bits(1)) return false;
    if (target_size || prefix_size || channel_size ||
        (sender_size && !exact_text(r, sender_size, expected)) ||
        !exact_text(r, message_size, expected)) return false;
    r.end();return true;
}
}

Reply ignored_chat_request(std::string const &name, View body)
{
    if (name != "CMSG_CHAT_REPORT_IGNORED") return {};
    // Pinned modern ChatReportIgnored::Read: packed ObjectGuid, uint8 Reason.
    Reader r(body);auto guid = r.guid();auto reason = r.take<std::uint8_t>();r.end();
    if (!local_player(guid)) throw std::runtime_error("ignored chat sender outside the local player realm");
    auto low = integer(guid[0]);std::array<std::uint8_t, 8> octets{};
    for (unsigned i = 0; i < octets.size(); ++i) octets[i] = std::uint8_t(low >> (i * 8));
    Writer w;w.put(reason);
    // Native HandleChatIgnoredOpcode: Reason, these presence bits, XOR bytes.
    for (auto i : {5, 2, 6, 4, 7, 0, 1, 3}) w.bits(octets[i] != 0, 1);
    w.flush();
    for (auto i : {0, 6, 5, 1, 4, 3, 7, 2}) if (octets[i]) w.put<std::uint8_t>(octets[i] ^ 1);
    return Packet{"CMSG_CHAT_IGNORED", w.finish()};
}

bool owned_ignore_probe(std::string const &name, View body)
{
    try
    {
        if (name == "CMSG_CHAT_REPORT_IGNORED")
        {
            Reader r(body);auto guid = r.guid();auto reason = r.take<std::uint8_t>();r.end();
            return owned_guid(guid) && reason == 0;
        }
        if (name == "CMSG_CHAT_IGNORED")
            return body.size() == 3 && body[0] == 0 && body[1] == 4 && (body[2] == 0 || body[2] == 3);
        if (name == "SMSG_MESSAGECHAT" || name == "SMSG_GM_MESSAGECHAT" || name == "SMSG_CHAT")
            return owned_notice(name, body);
    }
    catch (std::exception const &) { return false; }
    return false;
}
}
