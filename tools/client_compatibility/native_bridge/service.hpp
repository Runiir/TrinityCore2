#pragma once
#include "data.hpp"
#include "events.hpp"
#include "native.hpp"
#include <atomic>

namespace bridge
{
class Session;
struct Pending
{
    std::weak_ptr<Session> owner;
    std::chrono::steady_clock::time_point expires;
};
struct Service
{
    std::filesystem::path root, repo;
    Protocol protocol;
    PublicData data;
    Events events;
    asio::thread_pool database_workers{2};
    std::mutex pending_mutex;
    std::unordered_map<std::uint64_t, Pending> pending;
    std::atomic<unsigned> connections{0};
    Service(std::filesystem::path root, std::filesystem::path repo);
    Bytes redirect(std::shared_ptr<Session> const &owner);
    std::pair<std::shared_ptr<Session>, Bytes> continuation(View body, View challenge);
};
class Session : public std::enable_shared_from_this<Session>
{
    PacketCrypt crypt_;
    Bytes encryption_, challenge_ = random_bytes(32);
    std::shared_ptr<Session> realm_;
    bool authenticated_ = false;

  public:
    Service &service;
    std::shared_ptr<Channel> channel;
    std::shared_ptr<Native> native;
    std::weak_ptr<Session> world;
    std::mutex state_mutex;
    State state;
    Login login;
    std::string id = hex(random_bytes(4));
    Session(Service &service, Tcp::socket socket);
    Session &owner()
    {
        return realm_ ? *realm_ : *this;
    }
    Task<> run();
    Task<> handle(std::string const &name, Bytes body);
    Task<> native_packets();
    Task<> gameplay(std::string name, Bytes body);
    Task<> player_names(Bytes body);
    void gameplay_request(std::string const &name, View body, Session &owner,
                          std::shared_ptr<Session> const &world, bool in_world);
    void send(std::string const &name, View body = {});
    void send(Packet const &packet)
    {
        send(packet.first, packet.second);
    }
    void stop();
};
} // namespace bridge
