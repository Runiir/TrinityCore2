#pragma once
#include "json.hpp"
#include <bit>
#include <cstring>
#include <span>
#include <stdexcept>
#include <vector>

namespace bridge
{
using Bytes = std::vector<std::uint8_t>;
using View = std::span<std::uint8_t const>;
constexpr std::uint64_t player_high()
{
    return (2ull << 58) | (1ull << 42);
}
Bytes unhex(std::string_view hex);
std::string hex(View bytes);
Bytes bytes(std::string_view text);
Bytes concatenate(std::initializer_list<View> inputs);

class Writer
{
    Bytes data_;
    unsigned bit_ = 0;

  public:
    Writer &bits(std::uint64_t value, unsigned width);
    Writer &flush()
    {
        bit_ = 0;
        return *this;
    }
    Writer &raw(View value);
    Writer &raw(std::string_view value)
    {
        return raw(bytes(value));
    }
    Writer &zeros(std::size_t size)
    {
        return raw(Bytes(size));
    }
    template <typename T> Writer &put(T value)
    {
        static_assert(std::endian::native == std::endian::little);
        return raw(View(reinterpret_cast<std::uint8_t const *>(&value), sizeof(T)));
    }
    Writer &pack(std::string_view format, Array const &values);
    Writer &guid(std::uint64_t low = 0, std::uint64_t high = 0);
    Writer &guid(Value const &value);
    Bytes finish()
    {
        flush();
        return data_;
    }
    Bytes const &data() const
    {
        return data_;
    }
};
class Reader
{
    View data_;
    std::size_t pos_ = 0;
    unsigned bit_ = 0;

  public:
    explicit Reader(View data) : data_(data) {}
    std::uint64_t bits(unsigned width);
    void align();
    View raw(std::size_t count);
    template <typename T> T take()
    {
        T result;
        auto view = raw(sizeof(T));
        std::memcpy(&result, view.data(), sizeof(T));
        return result;
    }
    Array unpack(std::string_view format);
    Array guid();
    std::size_t remaining()
    {
        align();
        return data_.size() - pos_;
    }
    void end();
};
} // namespace bridge
