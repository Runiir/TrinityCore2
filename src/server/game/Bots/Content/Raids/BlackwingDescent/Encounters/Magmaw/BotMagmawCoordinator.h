#ifndef TRINITY_BOT_MAGMAW_COORDINATOR_H
#define TRINITY_BOT_MAGMAW_COORDINATOR_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawRaidPlan.h"

#include <memory>

namespace BotEncounter
{
// Value-only shadow coordinator. No live strategy consumes this plan yet.
class MagmawCoordinator
{
public:
    static std::shared_ptr<MagmawCoordinator const> Reconcile(
        std::shared_ptr<MagmawCoordinator const> const& current,
        MagmawFacts const& facts, Blackboard const& board,
        MagmawRosterView const& roster);

    bool Matches(Scope const& scope, uint64 sourceRevision,
        uint64 rosterGeneration) const
    {
        return _plan.Matches(scope, sourceRevision, rosterGeneration);
    }

    MagmawRaidPlan const& Plan() const { return _plan; }

private:
    MagmawCoordinator() = default;

    MagmawRaidPlan _plan;
};
}

#endif
