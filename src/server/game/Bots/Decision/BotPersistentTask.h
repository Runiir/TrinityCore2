#ifndef TRINITY_BOT_PERSISTENT_TASK_H
#define TRINITY_BOT_PERSISTENT_TASK_H

#include "Define.h"

namespace BotDecision
{
enum class PersistentTaskState : uint8
{
    Running,
    Suspended,
    Succeeded,
    Failed,
    Aborted
};

enum class PersistentTaskSuspension : uint8
{
    None,
    ObservationUnavailable,
    SafetyPreempted,
    MovementLeaseExpired
};

constexpr bool IsTerminal(PersistentTaskState state)
{
    return state == PersistentTaskState::Succeeded
        || state == PersistentTaskState::Failed
        || state == PersistentTaskState::Aborted;
}
}

#endif
