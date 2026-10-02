#pragma once
#include "protocol.hpp"

namespace bridge
{
// The legacy core emits initial gameplay before LOGIN_VERIFY_WORLD. The modern
// client needs that world packet first on every new instance connection.
struct LoginBarrier
{
    bool pending = false;
    std::deque<Packet> deferred;
    std::size_t bytes = 0;
    void begin();
    std::vector<Packet> accept(Packet packet);
};
void finish_logout(State &state);
}
