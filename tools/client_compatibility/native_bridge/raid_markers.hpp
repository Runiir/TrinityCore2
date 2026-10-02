#pragma once
#include "buffer.hpp"
#include <array>
#include <optional>

namespace bridge
{
// Native masks arrive before dynamic-object creates. Emit only complete snapshots.
struct RaidMarkers
{
    unsigned active=0;
    std::array<Value,5> locations;
    void mask(unsigned value);
    void location(unsigned slot, Value const &value);
    std::optional<Bytes> packet() const;
};
}
