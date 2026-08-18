#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_SCOPE_GUARD_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_SCOPE_GUARD_H

#include <functional>

namespace BotWorldPopulationMgrInternal
{
struct ReconcileOnScopeExit
{
    std::function<void()> Callback;

    ~ReconcileOnScopeExit()
    {
        if (Callback)
            Callback();
    }
};
}

#endif
