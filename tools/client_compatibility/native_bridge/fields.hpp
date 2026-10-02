#pragma once
#include "buffer.hpp"
#include <memory>
#include <unordered_map>

namespace bridge
{
// Compile the pinned declarative serializer once. No parsing on the packet path.
class Fields
{
    struct Program;
    std::shared_ptr<Program const> program_;

  public:
    explicit Fields(std::filesystem::path const &schema);
    void serialize(Writer &writer, std::string const &kind, Value values = Object{},
                   unsigned visibility = 1) const;
};
} // namespace bridge
