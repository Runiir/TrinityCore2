#include "channel.hpp"

namespace bridge
{
Channel::Channel(Tcp::socket source)
    : strand(asio::make_strand(source.get_executor())), socket(strand), timeout(strand)
{
    auto protocol = source.local_endpoint().protocol();
    auto handle = source.release();
    boost::system::error_code error;
    socket.assign(protocol, handle, error);
    if (error)
    {
        ::close(handle);
        throw boost::system::system_error(error);
    }
}
Channel::Channel(asio::any_io_executor executor)
    : strand(asio::make_strand(executor)), socket(strand), timeout(strand)
{
}
Task<Bytes> Channel::read(std::size_t size)
{
    if (size > 1024 * 1024)
        throw std::runtime_error("transport read exceeds bound");
    Bytes result(size);
    if (size)
        co_await asio::async_read(socket, asio::buffer(result), asio::use_awaitable);
    co_return result;
}
void Channel::send(Bytes body)
{
    auto self = shared_from_this();
    asio::dispatch(strand,
                   [self, body = std::move(body)]() mutable
                   {
                       if (!self->socket.is_open())
                           return;
                       if (self->queued_ + body.size() > 2 * 1024 * 1024 || self->output_.size() >= 2048)
                       {
                           self->close();
                           return;
                       }
                       self->queued_ += body.size();
                       self->output_.push_back(std::move(body));
                       if (!self->writing_)
                       {
                           self->writing_ = true;
                           asio::co_spawn(self->strand, self->flush(),
                                          [self](std::exception_ptr error)
                                          {
                                              self->writing_ = false;
                                              if (error)
                                                  self->close();
                                          });
                       }
                   });
}
Task<> Channel::flush()
{
    while (!output_.empty() && socket.is_open())
    {
        co_await asio::async_write(socket, asio::buffer(output_.front()), asio::use_awaitable);
        queued_ -= output_.front().size();
        output_.pop_front();
    }
}
void Channel::deadline(std::chrono::seconds duration)
{
    auto self = shared_from_this();
    timeout.expires_after(duration);
    timeout.async_wait(
        [self](boost::system::error_code error)
        {
            if (!error)
                self->close();
        });
}
void Channel::close()
{
    closed_.store(true);
    auto self = shared_from_this();
    asio::dispatch(strand,
                   [self]
                   {
                       boost::system::error_code ignored;
                       self->timeout.cancel();
                       self->socket.cancel(ignored);
                       self->socket.shutdown(Tcp::socket::shutdown_both, ignored);
                       self->socket.close(ignored);
                       // A pending async_write owns the front buffer until its completion.
                   });
}
} // namespace bridge
