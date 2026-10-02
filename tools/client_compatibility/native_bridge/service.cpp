#include "service.hpp"
#include <ctime>

namespace bridge
{
namespace
{
constexpr std::string_view SERVER_HELLO = "WORLD OF WARCRAFT CONNECTION - SERVER TO CLIENT - V2\n";
constexpr std::string_view CLIENT_HELLO = "WORLD OF WARCRAFT CONNECTION - CLIENT TO SERVER - V2\n";
} // namespace
Service::Service(std::filesystem::path base, std::filesystem::path checkout)
    : root(std::move(base)), repo(std::move(checkout)), protocol(repo / "tools/client_compatibility/world"),
      data(root, repo), events(root)
{
}
Bytes Service::redirect(std::shared_ptr<Session> const &owner)
{
    std::lock_guard lock(pending_mutex);
    auto now = std::chrono::steady_clock::now();
    for (auto it = pending.begin(); it != pending.end();)
        if (it->second.expires <= now || it->second.owner.expired())
            it = pending.erase(it);
        else
            ++it;
    if (pending.size() > 256)
        throw std::runtime_error("instance redirects exceed bound");
    auto random = random_bytes(4);
    Reader r(random);
    auto key = static_cast<std::uint64_t>(owner->login.account) | (1ull << 32) |
               (static_cast<std::uint64_t>(r.take<std::uint32_t>() & 0x7fffffff) << 33);
    pending[key] = Pending{owner, now + std::chrono::seconds(30)};
    Bytes where{1, 127, 0, 0, 1};
    auto signed_data = Writer().raw(where).pack("IH", {1, 18087}).finish();
    auto signature = rsa_signature(protocol.directory / "upstream-development-connect-to.pem", signed_data);
    if (signature.size() != 256)
        throw std::runtime_error("unexpected redirect signature size");
    return Writer().raw(signature).raw(where).pack("HIBQ", {18087, 17, 1, key}).finish();
}
std::pair<std::shared_ptr<Session>, Bytes> Service::continuation(View body, View challenge)
{
    Reader r(body);
    r.take<std::uint64_t>();
    auto key = r.take<std::uint64_t>();
    auto local = r.raw(32), proof = r.raw(24);
    r.end();
    std::lock_guard lock(pending_mutex);
    auto pos = pending.find(key);
    auto owner = pos != pending.end() ? pos->second.owner.lock() : nullptr;
    if (!owner || pos->second.expires <= std::chrono::steady_clock::now() || !owner->channel->alive())
        throw std::runtime_error("unknown or expired instance continuation");
    auto prefix = Writer().put(key).raw(local).raw(challenge).raw(continued_seed()).finish();
    auto expected = mac(owner->login.session, prefix);
    if (!constant_equal(proof, View(expected).first(24)))
        throw std::runtime_error("instance authentication proof rejected");
    auto encryption = mac(owner->login.session, concatenate({local, challenge, encryption_seed()}));
    encryption.resize(32);
    pending.erase(pos);
    return {owner, encryption};
}
Session::Session(Service &svc, Tcp::socket socket)
    : service(svc), channel(std::make_shared<Channel>(std::move(socket)))
{
}
void Session::send(std::string const &name, View body)
{
    auto self = shared_from_this();
    Bytes payload(body.begin(), body.end());
    asio::dispatch(channel->strand,
                   [self, name, payload = std::move(payload)]
                   {
                       try
                       {
                           auto const &table = get(self->service.protocol.opcodes, "modern").as_object();
                           auto opcode = table.if_contains(name);
                           if (!opcode)
                               throw std::runtime_error("undefined modern opcode");
                           self->channel->send(self->crypt_.encode(integer(*opcode), payload));
                           self->service.events.event("modern_packet", {{"session", self->id},
                                                                        {"direction", "to_client"},
                                                                        {"name", name},
                                                                        {"bytes", payload.size()}});
                           self->service.events.packet("to_client", name, payload, self->owner().id);
                       }
                       catch (...)
                       {
                           self->stop();
                       }
                   });
}
Task<> Session::run()
{
    service.events.event("world_connection", {{"session", id}});
    channel->send(bytes(SERVER_HELLO));
    channel->deadline(std::chrono::seconds(10));
    if (co_await channel->read(CLIENT_HELLO.size()) != bytes(CLIENT_HELLO))
        throw std::runtime_error("modern world initializer mismatch");
    send("SMSG_AUTH_CHALLENGE", concatenate({random_bytes(32), challenge_, Bytes{1}}));
    while (channel->socket.is_open())
    {
        channel->deadline(std::chrono::seconds(120));
        auto raw_size = co_await channel->read(4);
        Reader r(raw_size);
        auto size = r.take<std::uint32_t>();
        if (size < 4 || size > 65536)
            throw std::runtime_error("invalid modern frame size");
        auto tag = co_await channel->read(12);
        auto payload = co_await channel->read(size);
        auto packet = crypt_.decode(payload, tag);
        auto opcode = packet.first;
        auto body = std::move(packet.second);
        auto pos = service.protocol.modern_names.find(opcode);
        auto name =
            pos == service.protocol.modern_names.end() ? "unknown_" + std::to_string(opcode) : pos->second;
        service.events.event(
            "modern_packet",
            {{"session", id}, {"direction", "from_client"}, {"name", name}, {"bytes", body.size()}});
        service.events.packet("from_client", name, body, owner().id);
        co_await handle(name, std::move(body));
    }
}
void Session::stop()
{
    channel->close();
    if (realm_)
    {
        auto self = shared_from_this(), realm = realm_;
        asio::post(realm->channel->strand,
                   [self, realm]
                   {
                       bool active;
                       {
                           std::lock_guard lock(realm->state_mutex);
                           active = realm->world.lock().get() == self.get();
                       }
                       if (active)
                           realm->stop();
                   });
    }
    else
    {
        auto self = shared_from_this();
        asio::post(channel->strand,
                   [self]
                   {
                       if (self->native)
                           self->native->close();
                       std::lock_guard lock(self->state_mutex);
                       if (auto instance = self->world.lock())
                           instance->channel->close();
                   });
    }
}
Task<> Session::native_packets()
{
    try
    {
        while (channel->socket.is_open())
        {
            auto packet = co_await native->receive();
            co_await gameplay(packet.first, std::move(packet.second));
        }
    }
    catch (std::exception const &error)
    {
        service.events.event("native_stream_closed",
                             {{"session", id}, {"error", std::string(error.what()).substr(0, 512)}});
        stop();
    }
}
} // namespace bridge
