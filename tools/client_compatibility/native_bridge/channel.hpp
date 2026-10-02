#pragma once
#include "buffer.hpp"
#include <atomic>
#include <boost/asio.hpp>
#include <deque>
#include <memory>

namespace bridge
{
namespace asio = boost::asio;
using Tcp = asio::ip::tcp;
template <typename T = void> using Task = asio::awaitable<T>;
class Channel : public std::enable_shared_from_this<Channel>
{
    std::deque<Bytes> output_;
    std::size_t queued_ = 0;
    bool writing_ = false;
    std::atomic<bool> closed_{false};
    Task<> flush();

  public:
    asio::strand<asio::any_io_executor> strand;
    Tcp::socket socket;
    asio::steady_timer timeout;
    explicit Channel(Tcp::socket socket);
    explicit Channel(asio::any_io_executor executor);
    Task<Bytes> read(std::size_t size);
    void send(Bytes body);
    void deadline(std::chrono::seconds duration);
    void close();
    bool alive() const { return !closed_.load(); }
};

template <typename F> Task<std::invoke_result_t<F>> background(asio::thread_pool &pool, F function)
{
    using Result = std::invoke_result_t<F>;
    asio::use_awaitable_t<> token;
    co_return co_await asio::async_initiate<asio::use_awaitable_t<>, void(std::exception_ptr, Result)>(
        [&pool, function = std::move(function)](auto handler) mutable
        {
            auto executor = asio::get_associated_executor(handler);
            auto work = asio::make_work_guard(executor);
            asio::post(pool,
                       [handler = std::move(handler), executor, work = std::move(work),
                        function = std::move(function)]() mutable
                       {
                           try
                           {
                               auto value = function();
                               asio::post(executor, [handler = std::move(handler), work = std::move(work),
                                                     value = std::move(value)]() mutable
                                          { std::move(handler)(std::exception_ptr{}, std::move(value)); });
                           }
                           catch (...)
                           {
                               auto error = std::current_exception();
                               asio::post(executor,
                                          [handler = std::move(handler), work = std::move(work),
                                           error]() mutable { std::move(handler)(error, Result{}); });
                           }
                       });
        },
        token);
}
} // namespace bridge
