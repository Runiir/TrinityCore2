#include "json.hpp"
#include <boost/json/src.hpp>
#include <fstream>
#include <stdexcept>

namespace bridge
{
Value load_json(std::filesystem::path const &path)
{
    std::ifstream file(path);
    if (!file)
        throw std::runtime_error("cannot open JSON file: " + path.string());
    std::string data((std::istreambuf_iterator<char>(file)), {});
    return json::parse(data);
}
Value const &get(Value const &value, std::string_view key)
{
    static Value const zero = 0;
    if (!value.is_object())
        return zero;
    auto p = value.as_object().if_contains(key);
    return p ? *p : zero;
}
std::uint64_t integer(Value const &v)
{
    if (v.is_uint64())
        return v.as_uint64();
    if (v.is_int64())
        return static_cast<std::uint64_t>(v.as_int64());
    if (v.is_bool())
        return v.as_bool();
    if (v.is_double())
        return static_cast<std::uint64_t>(v.as_double());
    if (v.is_null())
        return 0;
    throw std::runtime_error("expected integer");
}
std::int64_t signed_integer(Value const &v)
{
    return static_cast<std::int64_t>(integer(v));
}
double number(Value const &v)
{
    if (v.is_double())
        return v.as_double();
    if (v.is_int64())
        return static_cast<double>(v.as_int64());
    return static_cast<double>(integer(v));
}
bool truth(Value const &v)
{
    if (v.is_array())
        return !v.as_array().empty();
    if (v.is_object())
        return !v.as_object().empty();
    if (v.is_string())
        return !v.as_string().empty();
    return number(v) != 0;
}
std::string str(Value const &v)
{
    if (v.is_string())
        return std::string(v.as_string());
    throw std::runtime_error("expected string");
}
} // namespace bridge
