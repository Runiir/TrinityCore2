#include "native.hpp"

namespace bridge
{
namespace
{
constexpr std::string_view SERVER_HELLO = "WORLD OF WARCRAFT CONNECTION - SERVER TO CLIENT";
constexpr std::string_view CLIENT_HELLO = "WORLD OF WARCRAFT CONNECTION - CLIENT TO SERVER";
Bytes frame(unsigned opcode, View body)
{
    if (body.size() + 4 > 65535)
        throw std::runtime_error("native outbound frame bound");
    auto size = body.size() + 4;
    return Writer()
        .raw(Bytes{static_cast<std::uint8_t>(size >> 8), static_cast<std::uint8_t>(size)})
        .put<std::uint32_t>(opcode)
        .raw(body)
        .finish();
}
} // namespace
Bytes native_authentication(std::string const &username, View key, View challenge, View local)
{
    auto digest = hash(concatenate({bytes(username), Bytes(4), local, challenge, key}), "SHA1");
    Writer w;
    w.pack("IIB", {0, 1, 0});
    auto shuffled = [&](std::initializer_list<unsigned> indices)
    {
        for (auto i : indices)
            w.put(digest[i]);
    };
    shuffled({10, 18, 12, 5});
    w.pack("Q", {0});
    shuffled({15, 9, 19, 4, 7, 16, 3});
    w.pack("H", {15595}).put(digest[8]).pack("IB", {1, 0});
    shuffled({17, 6, 0, 1, 11});
    w.raw(local).put(digest[2]).pack("I", {1});
    shuffled({14, 13});
    return w.pack("I", {0}).bits(0, 1).bits(username.size(), 12).raw(username).finish();
}
Bytes native_login(std::uint64_t guid, bool mover)
{
    auto octets = Writer().put(guid).finish();
    Writer w;
    std::array<unsigned, 8> masks = mover ? std::array<unsigned, 8>{7, 2, 1, 0, 4, 5, 6, 3}
                                          : std::array<unsigned, 8>{2, 3, 0, 6, 4, 5, 1, 7};
    std::array<unsigned, 8> values = mover ? std::array<unsigned, 8>{3, 2, 4, 0, 5, 1, 6, 7}
                                           : std::array<unsigned, 8>{2, 7, 0, 3, 5, 6, 1, 4};
    for (auto i : masks)
        w.bits(octets[i] != 0, 1);
    for (auto i : values)
        if (octets[i])
            w.put<std::uint8_t>(octets[i] ^ 1);
    return w.finish();
}
Native::Native(asio::any_io_executor executor, Protocol const &protocol, Events &events, std::string session)
    : channel_(std::make_shared<Channel>(executor)), protocol_(protocol), events_(events),
      session_(std::move(session))
{
    if (inflateInit(&inflate_) != Z_OK)
        throw std::runtime_error("native decompressor initialization failed");
}
Native::~Native() { inflateEnd(&inflate_); }
Task<> Native::connect(Login const &login)
{
    channel_->deadline(std::chrono::seconds(15));
    co_await channel_->socket.async_connect(Tcp::endpoint(asio::ip::make_address("127.0.0.1"), 18085),
                                            asio::use_awaitable);
    channel_->deadline(std::chrono::seconds(15));
    auto prefix = co_await channel_->read(2);
    auto size = (static_cast<unsigned>(prefix[0]) << 8) | prefix[1];
    auto hello = co_await channel_->read(size);
    if (size != SERVER_HELLO.size() || hello != bytes(SERVER_HELLO))
        throw std::runtime_error("native world initializer mismatch");
    channel_->send(
        Writer().raw(Bytes{0, static_cast<std::uint8_t>(CLIENT_HELLO.size())}).raw(CLIENT_HELLO).finish());
    auto challenge = co_await receive();
    if (challenge.first != "SMSG_AUTH_CHALLENGE" || challenge.second.size() != 37)
        throw std::runtime_error("native challenge mismatch");
    auto local = random_bytes(4);
    auto body =
        native_authentication(login.username, login.native_key, View(challenge.second).subspan(32, 4), local);
    auto opcode = integer(get(get(protocol_.opcodes, "legacy"), "CMSG_AUTH_SESSION"));
    channel_->send(frame(opcode, body));
    send_crypt_.emplace(login.native_key, unhex("c2b3723cc6aed9b5343c53ee2f4367ce"));
    receive_crypt_.emplace(login.native_key, unhex("cc98ae04e897eaca12ddc09342915357"));
    while (true)
    {
        auto packet = co_await receive();
        if (packet.first == "SMSG_AUTH_RESPONSE")
        {
            auto const &reply = packet.second;
            if (reply.size() != 17 || !(reply[0] & 0x40) || reply[16] != 12)
                throw std::runtime_error("native authentication rejected");
            connected_ = true;
            channel_->deadline(std::chrono::seconds(120));
            events_.event("native_authenticated", {{"session", session_}, {"account_id", login.account}});
            co_return;
        }
    }
}
void Native::send(std::string const &name, View body)
{
    auto self = shared_from_this();
    Bytes payload(body.begin(), body.end());
    asio::post(channel_->strand,
               [self, name, payload = std::move(payload)]
               {
                   try
                   {
                       auto const &table = get(self->protocol_.opcodes, "legacy").as_object();
                       auto pos = table.if_contains(name);
                       if (!pos)
                           throw std::runtime_error("undefined native opcode");
                       auto packet = frame(integer(*pos), payload);
                       auto header = View(packet).first(6);
                       if (self->send_crypt_)
                       {
                           auto encrypted = self->send_crypt_->transform(header);
                           std::copy(encrypted.begin(), encrypted.end(), packet.begin());
                       }
                       self->channel_->send(std::move(packet));
                       if (name.find("AUTH") == std::string::npos)
                       {
                           self->events_.event("native_packet", {{"session", self->session_},
                                                                 {"direction", "to_native"},
                                                                 {"name", name},
                                                                 {"bytes", payload.size()}});
                           self->events_.packet("to_native", name, payload, self->session_);
                       }
                   }
                   catch (...)
                   {
                       self->channel_->close();
                   }
               });
}
Task<Packet> Native::receive()
{
    channel_->deadline(std::chrono::seconds(connected_ ? 120 : 15));
    auto raw = co_await channel_->read(1);
    auto first = receive_crypt_ ? receive_crypt_->transform(raw)[0] : raw[0];
    raw = co_await channel_->read(first & 0x80 ? 4 : 3);
    auto tail = receive_crypt_ ? receive_crypt_->transform(raw) : raw;
    unsigned size, opcode;
    if (first & 0x80)
    {
        size = ((first & 0x7f) << 16) | (static_cast<unsigned>(tail[0]) << 8) | tail[1];
        opcode = tail[2] | (static_cast<unsigned>(tail[3]) << 8);
    }
    else
    {
        size = (static_cast<unsigned>(first) << 8) | tail[0];
        opcode = tail[1] | (static_cast<unsigned>(tail[2]) << 8);
    }
    if (size < 2 || size > 1024 * 1024)
        throw std::runtime_error("invalid native frame size");
    auto body = co_await channel_->read(size - 2);
    if (opcode & 0x8000)
    {
        Reader r(body);
        auto expected = r.take<std::uint32_t>();
        if (expected > 1024 * 1024)
            throw std::runtime_error("native compressed payload too large");
        auto input = r.raw(r.remaining());
        Bytes output(expected + 1);
        inflate_.next_in = const_cast<Bytef *>(input.data());
        inflate_.avail_in = input.size();
        inflate_.next_out = output.data();
        inflate_.avail_out = output.size();
        auto status = inflate(&inflate_, Z_SYNC_FLUSH);
        if ((status != Z_OK && status != Z_BUF_ERROR && status != Z_STREAM_END) || inflate_.avail_in ||
            output.size() - inflate_.avail_out != expected)
            throw std::runtime_error("native compressed payload mismatch");
        output.resize(expected);
        body = std::move(output);
        opcode &= 0x7fff;
    }
    std::string name = "unknown_" + hex(Writer().put<std::uint16_t>(opcode).finish());
    if (auto pos = protocol_.legacy_names.find(opcode); pos != protocol_.legacy_names.end())
        name = pos->second;
    events_.event(
        "native_packet",
        {{"session", session_}, {"direction", "from_native"}, {"name", name}, {"bytes", body.size()}});
    events_.packet("from_native", name, body, session_);
    co_return Packet{name, body};
}
} // namespace bridge
