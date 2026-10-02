#include "buffer.hpp"
#include <cctype>
#include <charconv>
#include <limits>

namespace bridge
{
Bytes unhex(std::string_view text)
{
    if (text.size() % 2)
        throw std::runtime_error("odd hex input");
    Bytes result;
    for (std::size_t i = 0; i < text.size(); i += 2)
    {
        unsigned value;
        auto [p, error] = std::from_chars(text.data() + i, text.data() + i + 2, value, 16);
        if (error != std::errc() || p != text.data() + i + 2)
            throw std::runtime_error("bad hex input");
        result.push_back(value);
    }
    return result;
}
std::string hex(View data)
{
    std::string result;
    result.reserve(data.size() * 2);
    constexpr char alphabet[] = "0123456789abcdef";
    for (auto n : data)
    {
        result += alphabet[n >> 4];
        result += alphabet[n & 15];
    }
    return result;
}
Bytes bytes(std::string_view text)
{
    return Bytes(text.begin(), text.end());
}
Bytes concatenate(std::initializer_list<View> inputs)
{
    Bytes result;
    for (auto v : inputs)
        result.insert(result.end(), v.begin(), v.end());
    return result;
}
Writer &Writer::bits(std::uint64_t value, unsigned width)
{
    if (!width || width > 64 || (width < 64 && value >= (1ull << width)))
        throw std::runtime_error("bit field overflow");
    for (unsigned shift = width; shift-- > 0;)
    {
        if (!bit_)
            data_.push_back(0);
        data_.back() |= ((value >> shift) & 1) << (7 - bit_);
        bit_ = (bit_ + 1) % 8;
    }
    return *this;
}
Writer &Writer::raw(View value)
{
    flush();
    data_.insert(data_.end(), value.begin(), value.end());
    return *this;
}
namespace
{
template <typename T> T checked_integer(Value const &v)
{
    if (!v.is_int64() && !v.is_uint64() && !v.is_bool() && !v.is_null())
        throw std::runtime_error("pack requires an integer");
    if constexpr (std::is_unsigned_v<T>)
    {
        if ((v.is_int64() && v.as_int64() < 0) || integer(v) > std::numeric_limits<T>::max())
            throw std::runtime_error("unsigned pack overflow");
        return static_cast<T>(integer(v));
    }
    else
    {
        if (v.is_uint64() && v.as_uint64() > static_cast<std::uint64_t>(std::numeric_limits<T>::max()))
            throw std::runtime_error("signed pack overflow");
        auto n = signed_integer(v);
        if (n < std::numeric_limits<T>::min() || n > std::numeric_limits<T>::max())
            throw std::runtime_error("signed pack overflow");
        return static_cast<T>(n);
    }
}
template <typename F> void formats(std::string_view text, F f)
{
    std::size_t count = 0;
    for (char c : text)
    {
        if (std::isdigit(static_cast<unsigned char>(c)))
        {
            count = count * 10 + c - '0';
            if (count > 1000000)
                throw std::runtime_error("format count bound");
            continue;
        }
        if (count == 0)
            count = 1;
        for (std::size_t i = 0; i < count; ++i)
            f(c);
        count = 0;
    }
    if (count)
        throw std::runtime_error("incomplete format");
}
} // namespace
Writer &Writer::pack(std::string_view format, Array const &values)
{
    std::size_t index = 0;
    formats(format,
            [&](char c)
            {
                if (index >= values.size())
                    throw std::runtime_error("too few pack values");
                auto const &v = values[index++];
                switch (c)
                {
                case 'B':
                    put(checked_integer<std::uint8_t>(v));
                    break;
                case 'b':
                    put(checked_integer<std::int8_t>(v));
                    break;
                case 'H':
                    put(checked_integer<std::uint16_t>(v));
                    break;
                case 'h':
                    put(checked_integer<std::int16_t>(v));
                    break;
                case 'I':
                    put(checked_integer<std::uint32_t>(v));
                    break;
                case 'i':
                    put(checked_integer<std::int32_t>(v));
                    break;
                case 'Q':
                    put(checked_integer<std::uint64_t>(v));
                    break;
                case 'q':
                    put(checked_integer<std::int64_t>(v));
                    break;
                case 'f':
                    put<float>(number(v));
                    break;
                default:
                    throw std::runtime_error("unsupported pack type");
                }
            });
    if (index != values.size())
        throw std::runtime_error("too many pack values");
    return *this;
}
Writer &Writer::guid(std::uint64_t low, std::uint64_t high)
{
    auto octets = Writer().pack("QQ", {low, high}).finish();
    std::uint16_t mask = 0;
    for (unsigned i = 0; i < 16; ++i)
        if (octets[i])
            mask |= 1u << i;
    put(mask);
    for (auto n : octets)
        if (n)
            put(n);
    return *this;
}
Writer &Writer::guid(Value const &value)
{
    if (!truth(value))
        return guid();
    auto const &a = value.as_array();
    return guid(integer(a.at(0)), integer(a.at(1)));
}
std::uint64_t Reader::bits(unsigned width)
{
    if (width > 64)
        throw std::runtime_error("bit field bound");
    std::uint64_t result = 0;
    for (unsigned i = 0; i < width; ++i)
    {
        if (pos_ >= data_.size())
            throw std::runtime_error("truncated bit field");
        result = result * 2 + ((data_[pos_] >> (7 - bit_)) & 1);
        if (++bit_ == 8)
        {
            bit_ = 0;
            ++pos_;
        }
    }
    return result;
}
void Reader::align()
{
    if (bit_)
    {
        ++pos_;
        bit_ = 0;
    }
}
View Reader::raw(std::size_t count)
{
    align();
    if (count > data_.size() - pos_)
        throw std::runtime_error("truncated value");
    auto result = data_.subspan(pos_, count);
    pos_ += count;
    return result;
}
Array Reader::unpack(std::string_view format)
{
    Array values;
    formats(format,
            [&](char c)
            {
                switch (c)
                {
                case 'B':
                    values.push_back(take<std::uint8_t>());
                    break;
                case 'b':
                    values.push_back(take<std::int8_t>());
                    break;
                case 'H':
                    values.push_back(take<std::uint16_t>());
                    break;
                case 'h':
                    values.push_back(take<std::int16_t>());
                    break;
                case 'I':
                    values.push_back(take<std::uint32_t>());
                    break;
                case 'i':
                    values.push_back(take<std::int32_t>());
                    break;
                case 'Q':
                    values.push_back(take<std::uint64_t>());
                    break;
                case 'q':
                    values.push_back(take<std::int64_t>());
                    break;
                case 'f':
                    values.push_back(take<float>());
                    break;
                default:
                    throw std::runtime_error("unsupported unpack type");
                }
            });
    return values;
}
Array Reader::guid()
{
    auto mask = take<std::uint16_t>();
    std::uint64_t low = 0, high = 0;
    for (unsigned i = 0; i < 16; ++i)
        if (mask & (1u << i))
        {
            auto n = static_cast<std::uint64_t>(take<std::uint8_t>());
            (i < 8 ? low : high) |= n << ((i % 8) * 8);
        }
    return {low, high};
}
void Reader::end()
{
    align();
    if (pos_ != data_.size())
        throw std::runtime_error("unexpected trailing bytes");
}
} // namespace bridge
