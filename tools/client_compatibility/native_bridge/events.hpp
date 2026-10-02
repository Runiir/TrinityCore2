#pragma once
#include "buffer.hpp"
#include <mutex>

namespace bridge
{
class Events
{
    std::filesystem::path root_;
    std::mutex mutex_;
    void append(std::filesystem::path const &path, Object const &record);

  public:
    explicit Events(std::filesystem::path root) : root_(std::move(root)) {}
    void event(std::string kind, Object fields = {});
    void packet(std::string const &direction, std::string const &name, View body, std::string const &session);
};
} // namespace bridge
