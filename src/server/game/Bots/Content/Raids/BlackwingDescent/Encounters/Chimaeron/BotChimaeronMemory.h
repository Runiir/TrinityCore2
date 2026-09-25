#ifndef TRINITY_BOT_CHIMAERON_MEMORY_H
#define TRINITY_BOT_CHIMAERON_MEMORY_H

#include "ObjectGuid.h"

#include <string>

namespace BotEncounter
{
// Per-bot encounter memory that one blackboard revision cannot express.
// The runtime keeps one per bot (WorldBotState::ChimaeronMemory); every bot
// reads the same cohort blackboard, so the latches agree across the raid.
// Bind() resets the memory on a new attempt, wipe, route generation or node
// (the scope key) and on a new boss object.
struct ChimaeronEncounterMemory
{
    std::string ScopeKey;
    ObjectGuid BossGuid;
    // The burn window released once (ready raid, lust, floor or Mortality):
    // the hold never re-engages in this scope, and the Mortality handoff
    // taunt is allowed only after it.
    bool BurnReleased = false;
    // Pain Suppression (3 min cooldown, not on the blackboard) was seen on a
    // raid member in this scope; it is not proposed again.
    bool PainSuppressionObserved = false;

    void Bind(std::string const& scopeKey, ObjectGuid bossGuid)
    {
        if (scopeKey == ScopeKey && bossGuid == BossGuid)
            return;
        *this = ChimaeronEncounterMemory();
        ScopeKey = scopeKey;
        BossGuid = bossGuid;
    }
};
}

#endif
