#ifndef TRINITY_BOT_MAGMAW_COORDINATOR_H
#define TRINITY_BOT_MAGMAW_COORDINATOR_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawRaidPlan.h"

#include <array>
#include <memory>
#include <set>

namespace BotEncounter
{
// Value-only shadow coordinator. No live strategy consumes this plan yet.
class MagmawCoordinator
{
public:
    static std::shared_ptr<MagmawCoordinator const> Reconcile(
        std::shared_ptr<MagmawCoordinator const> const& current,
        MagmawFacts const& facts, Blackboard const& board,
        std::vector<MagmawAssignmentRetirementInput> const& retirements = {});

    bool Matches(Scope const& scope, uint64 sourceRevision) const
    {
        return _plan.Matches(scope, sourceRevision);
    }

    MagmawRaidPlan const& Plan() const { return _plan; }

private:
    using RetiredAssignments = std::array<std::set<uint64>,
        MagmawRaidPlan::AssignmentCount>;

    MagmawCoordinator() = default;

    MagmawRaidPlan _plan;
    RetiredAssignments _retired;
};
}

#endif
