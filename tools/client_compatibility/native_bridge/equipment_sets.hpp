#pragma once
#include "buffer.hpp"
#include <deque>
#include <optional>
#include <string>
#include <unordered_map>

namespace bridge
{
struct State;
struct EquipmentSets
{
    std::unordered_map<std::uint64_t,std::uint32_t> owned;
    std::deque<std::uint32_t> saving;
    std::deque<std::uint64_t> using_sets;
};
std::optional<std::pair<std::string,Bytes>> equipment_request(State &owner,std::string const &name,View body);
std::optional<std::pair<std::string,Bytes>> equipment_response(State &owner,std::string const &name,View body);
}
