#pragma once
#include <cstdint>
#include <stdexcept>
#include <unordered_set>

namespace bridge
{
// Native 4.3.4 broadcasts answers but never completes its ready check.
// Count only native-confirmed answers. The initiator is already checked.
struct ReadyCheck
{
    bool active = false;
    std::unordered_set<std::uint64_t> pending;
    void start(std::uint64_t starter, std::unordered_set<std::uint64_t> const &members)
    {
        if (!members.contains(starter) || members.empty() || members.size() > 40)
            throw std::runtime_error("ready check starter is outside bounded roster");
        pending = members;pending.erase(starter);active = true;
    }
    bool answer(std::uint64_t member)
    {
        return active && pending.erase(member);
    }
    bool complete() const { return active && pending.empty(); }
    bool finish()
    {
        bool previous = active;active = false;pending.clear();return previous;
    }
};
}
