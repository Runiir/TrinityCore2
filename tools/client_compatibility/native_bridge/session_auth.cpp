#include "service.hpp"

namespace bridge
{
Task<> Session::handle(std::string const &name, Bytes body)
{
    if (name == "CMSG_AUTH_SESSION" && !authenticated_)
    {
        if (realm_)
            throw std::runtime_error("authentication on an instance connection");
        service.events.event("world_auth_packet_parsed", {{"session", id}});
        auto challenge = challenge_;
        auto root = service.root;
        login = co_await background(service.database_workers,
                                    [root, body, challenge]
                                    {
                                        Database db(root);
                                        auto login = db.consume(body, challenge);
                                        Database::native_key(db, login);
                                        return login;
                                    });
        if (!channel->socket.is_open())
            throw std::runtime_error("connection closed during authentication");
        native = std::make_shared<Native>(channel->strand, service.protocol, service.events, id);
        co_await native->connect(login);
        authenticated_ = true;
        encryption_ = login.encryption;
        state.native_send = [n = native](std::string const &name, View body) { n->send(name, body); };
        send("SMSG_ENTER_ENCRYPTED_MODE", enabled_signature(encryption_));
        co_return;
    }
    if (name == "CMSG_AUTH_CONTINUED_SESSION" && !authenticated_)
    {
        auto [owner, key] = service.continuation(body, challenge_);
        realm_ = owner;
        login.account = owner->login.account;
        authenticated_ = true;
        encryption_ = key;
        send("SMSG_ENTER_ENCRYPTED_MODE", enabled_signature(encryption_));
        co_return;
    }
    if (name == "CMSG_ENTER_ENCRYPTED_MODE_ACK" && !encryption_.empty() && crypt_.key.empty())
    {
        if (!body.empty())
            throw std::runtime_error("encryption acknowledgement has trailing bytes");
        crypt_.key = encryption_;
        if (realm_)
        {
            std::lock_guard lock(realm_->state_mutex);
            if (realm_->state.character.is_null())
                throw std::runtime_error("instance without owned character");
            if (auto existing = realm_->world.lock(); existing && existing->channel->alive())
                throw std::runtime_error("repeated instance connection");
            realm_->world = shared_from_this();
            realm_->login_barrier.begin();
            send("SMSG_RESUME_COMMS");
            realm_->native->send("CMSG_PLAYER_LOGIN", native_login(realm_->state.guid()));
            service.events.event("instance_authenticated", {{"session", id}, {"account_id", login.account}});
            co_return;
        }
        send("SMSG_AUTH_RESPONSE", auth_success(service.data.race_classes));
        send("SMSG_TUTORIAL_FLAGS", Bytes(32));
        for (auto const &packet : bootstrap_packets(service.data))
            send(packet);
        service.events.event("world_authenticated", {{"session", id}, {"account_id", login.account}});
        auto self = shared_from_this();
        asio::co_spawn(channel->strand, native_packets(),
                       [self](std::exception_ptr error)
                       {
                           if (error)
                               self->stop();
                       });
        co_return;
    }
    if (crypt_.key.empty())
        throw std::runtime_error("request before world authentication");
    if (name == "CMSG_PING")
    {
        if (body.size() != 8)
            throw std::runtime_error("malformed ping");
        // A lobby can produce no native traffic for minutes. Keep its receive
        // deadline alive with the realm's normal pings. Instance pings share
        // this native session and must not double its ping frequency.
        if (!realm_) native->send(name,body);
        send("SMSG_PONG", View(body).first(4));
        co_return;
    }
    if (name == "CMSG_KEEP_ALIVE" || name == "CMSG_ENABLE_NAGLE" || name == "CMSG_LOG_DISCONNECT")
        co_return;
    if (name == "CMSG_ENUM_CHARACTERS")
    {
        if (realm_)
            throw std::runtime_error("character enumeration outside realm");
        native->send(name);
        co_return;
    }
    if (name == "CMSG_DB_QUERY_BULK")
    {
        for (auto const &packet : service.data.bulk_query(body))
            send(packet);
        co_return;
    }
    if (name == "CMSG_HOTFIX_REQUEST")
    {
        send("SMSG_HOTFIX_CONNECT", service.data.hotfix_request(body));
        co_return;
    }
    if (name == "CMSG_SERVER_TIME_OFFSET_REQUEST")
    {
        send("SMSG_SERVER_TIME_OFFSET", Writer().pack("q", {0}).finish());
        co_return;
    }
    if (name == "CMSG_GET_UNDELETE_CHARACTER_COOLDOWN_STATUS")
    {
        send("SMSG_UNDELETE_COOLDOWN_STATUS_RESPONSE", Writer().bits(0, 1).pack("II", {0, 0}).finish());
        co_return;
    }
    if (name == "CMSG_PLAYER_LOGIN")
    {
        if (realm_)
            throw std::runtime_error("player login outside realm");
        Reader r(body);
        auto identity = r.guid();
        r.take<float>();
        r.end();
        auto root = service.root;
        auto account = login.account;
        auto rows = co_await background(service.database_workers,
                                        [root, account]
                                        {
                                            Database db(root);
                                            return db.characters(account);
                                        });
        std::lock_guard lock(state_mutex);
        if (integer(identity[1]) != player_high() || !state.character.is_null())
            throw std::runtime_error("invalid or repeated character login");
        for (auto const &row : rows)
            if (get(row, "guid") == identity[0])
                state.character = row;
        if (state.character.is_null())
            throw std::runtime_error("character does not belong to authenticated account");
        send("SMSG_CONNECT_TO", service.redirect(shared_from_this()));
        co_return;
    }
    auto &own = owner();
    if (name == "CMSG_QUERY_PLAYER_NAMES")
    {
        co_await player_names(std::move(body));co_return;
    }
    std::lock_guard lock(own.state_mutex);
    auto world = own.world.lock();
    bool in_world = world.get() == this && own.state.created;
    // Dispatch is synchronous under the character lock. It never awaits IO/SQL.
    gameplay_request(name, body, own, world, in_world);
}
} // namespace bridge
