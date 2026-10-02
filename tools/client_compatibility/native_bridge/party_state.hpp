#pragma once
#include "buffer.hpp"
#include <array>
#include <map>

namespace bridge
{
struct PartyAura
{
    std::int32_t spell = 0;
    std::uint16_t flags = 0;
    std::vector<float> points;
};
struct PartyPet
{
    std::uint64_t guid = 0;
    std::string name;
    std::uint16_t model = 0;
    std::int32_t health = 0, max_health = 0;
    std::map<unsigned, PartyAura> auras;
};
struct PartyState
{
    bool initialized = false, requested = false, enemy = false;
    std::uint16_t status = 0, power = 0, max_power = 0, level = 0, zone = 0, wmo = 0;
    std::uint8_t power_type = 0;
    std::int32_t health = 0, max_health = 0, vehicle = 0;
    std::array<std::int16_t, 3> position{};
    std::uint32_t phase_flags = 0;
    std::vector<std::uint16_t> phases;
    std::map<unsigned, PartyAura> auras;
    PartyPet pet;
};
} // namespace bridge
