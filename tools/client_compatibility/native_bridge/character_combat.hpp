#pragma once
#include "protocol.hpp"
#include <map>

namespace bridge
{
void combat_creation(Protocol const &p, Value const &snapshot, Object &active);
struct CombatChanges
{
    std::map<unsigned, float> percentages;
    std::array<unsigned, 7> schools{};
    bool empty() const;
    void mask(std::array<std::uint32_t, 46> &mask) const;
    void write_percentages(Writer &w) const;
    void write_schools(Writer &w, Protocol const &p, Value const &snapshot) const;
};
CombatChanges combat_changes(Protocol const &p, Value const &snapshot, Value const &changed,
                             unsigned visibility);
}
