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
    std::vector<Packet> quest_reads;
    std::vector<Packet> template_reads;
    bool mail_read = false;
    bool awaiting_player = false;
    bool mover_ack = false;
    void begin();
    std::vector<Packet> accept(Packet packet);
    void defer_quest_read(Packet packet);
    void defer_mail_read(Packet packet);
    void defer_template_read(Packet packet);
    std::vector<Packet> release_quest_reads();
    bool accept_active_mover(State const &state, View body, bool active_instance);
    bool release_active_mover(State const &state);
};
void finish_logout(State &state);
}
