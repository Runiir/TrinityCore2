#pragma once
#include "channel.hpp"
#include "database.hpp"
#include "events.hpp"
#include "protocol.hpp"
#include <zlib.h>

namespace bridge
{
class Native : public std::enable_shared_from_this<Native>
{
    std::shared_ptr<Channel> channel_;
    std::optional<LegacyCrypt> send_crypt_, receive_crypt_;
    z_stream inflate_{};
    Protocol const &protocol_;
    Events &events_;
    std::string session_;
    bool connected_ = false;

  public:
    Native(asio::any_io_executor executor, Protocol const &protocol, Events &events, std::string session);
    ~Native();
    Task<> connect(Login const &login);
    Task<Packet> receive();
    void send(std::string const &name, View body = {});
    void close()
    {
        channel_->close();
    }
};
Bytes native_authentication(std::string const &username, View key, View challenge, View local);
Bytes native_login(std::uint64_t guid, bool mover = false);
} // namespace bridge
