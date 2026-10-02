#pragma once
#include <boost/json.hpp>
#include <cstdint>
#include <filesystem>
#include <string>

namespace bridge
{
namespace json = boost::json;
using Value = json::value;
using Object = json::object;
using Array = json::array;
Value load_json(std::filesystem::path const &path);
Value const &get(Value const &value, std::string_view key);
std::uint64_t integer(Value const &value);
std::int64_t signed_integer(Value const &value);
double number(Value const &value);
bool truth(Value const &value);
std::string str(Value const &value);
} // namespace bridge
