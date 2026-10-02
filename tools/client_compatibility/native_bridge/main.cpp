#include "service.hpp"
#include <iostream>
#include <thread>

namespace bridge
{
Task<> listener(Service &service, Tcp::acceptor &acceptor, std::mutex &mutex,
                std::unordered_set<std::shared_ptr<Session>> &sessions, unsigned maximum)
{
    while (acceptor.is_open())
    {
        boost::system::error_code error;
        auto socket = co_await acceptor.async_accept(asio::redirect_error(asio::use_awaitable, error));
        if (error)
        {
            if (error == asio::error::operation_aborted || !acceptor.is_open())
                co_return;
            throw boost::system::system_error(error);
        }
        if (!socket.remote_endpoint().address().is_loopback() || service.connections.load() >= maximum)
        {
            socket.close();
            continue;
        }
        socket.set_option(Tcp::no_delay(true));
        auto session = std::make_shared<Session>(service, std::move(socket));
        {
            std::lock_guard lock(mutex);
            sessions.insert(session);
        }
        ++service.connections;
        asio::co_spawn(session->channel->strand, session->run(),
                       [session, &service, &mutex, &sessions](std::exception_ptr error)
                       {
                           if (error)
                           {
                               try
                               {
                                   std::rethrow_exception(error);
                               }
                               catch (std::exception const &e)
                               {
                                   service.events.event("world_connection_closed",
                                                        {{"session", session->id},
                                                         {"error", std::string(e.what()).substr(0, 512)}});
                               }
                           }
                           session->stop();
                           {
                               std::lock_guard lock(mutex);
                               sessions.erase(session);
                           }
                           --service.connections;
                       });
    }
}
} // namespace bridge
int main(int argc, char **argv)
{
    using namespace bridge;
    try
    {
        std::filesystem::path root, repo;
        unsigned workers = 4, maximum = 64;
        bool self_check = false;
        for (int i = 1; i < argc; ++i)
        {
            std::string arg = argv[i];
            if (arg == "--self-check")
                self_check = true;
            else if (i + 1 < argc && arg == "--root")
                root = argv[++i];
            else if (i + 1 < argc && arg == "--repo")
                repo = argv[++i];
            else if (i + 1 < argc && arg == "--workers")
                workers = std::stoul(argv[++i]);
            else if (i + 1 < argc && arg == "--maximum-connections")
                maximum = std::stoul(argv[++i]);
            else
                throw std::runtime_error("unknown or incomplete bridge argument");
        }
        if (root.empty() || repo.empty() || workers < 1 || workers > 32 || maximum < 2 || maximum > 1024)
            throw std::runtime_error(
                "usage: client442_bridge --root <private-lab-root> --repo <compatibility-worktree> "
                "[--workers 4] [--maximum-connections 64] [--self-check]");
        Service service(root, repo);
        if (self_check)
        {
            std::cout << json::serialize(Object{{"engine", "cpp"},
                                                {"client_build", 60895},
                                                {"native_build", 15595},
                                                {"taxi_paths", service.data.taxi_paths.size()},
                                                {"public_broadcasts", service.data.broadcasts.size()},
                                                {"item_displays", service.data.item_displays.size()},
                                                {"python_packet_path", false}})
                      << '\n';
            return 0;
        }
        asio::io_context io;
        Tcp::acceptor acceptor(io, Tcp::endpoint(asio::ip::make_address("127.0.0.1"), 18087));
        asio::signal_set signals(io, SIGINT, SIGTERM);
        std::mutex mutex;
        std::unordered_set<std::shared_ptr<Session>> sessions;
        signals.async_wait(
            [&](boost::system::error_code error, int)
            {
                if (error)
                    return;
                acceptor.close();
                std::lock_guard lock(mutex);
                for (auto const &session : sessions)
                    session->stop();
            });
        service.events.event("world_listener", {{"port", 18087}});
        asio::co_spawn(io, listener(service, acceptor, mutex, sessions, maximum),
                       [&](std::exception_ptr error)
                       {
                           if (error)
                               io.stop();
                       });
        std::vector<std::thread> threads;
        for (unsigned i = 1; i < workers; ++i)
            threads.emplace_back([&] { io.run(); });
        io.run();
        for (auto &thread : threads)
            thread.join();
        service.database_workers.join();
        return 0;
    }
    catch (std::exception const &error)
    {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
