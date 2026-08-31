#ifndef TRINITY_BOT_MAGMAW_RAID_PLAN_H
#define TRINITY_BOT_MAGMAW_RAID_PLAN_H

#include "Bots/BotEncounterBlackboard.h"

#include <array>
#include <vector>

namespace BotEncounter
{
enum class MagmawRaidAssignmentSlot : uint8
{
    FireMageBaiter,
    MarksmanshipHunterBaiter,
    HookOne,
    HookTwo,
    MainPullTank,
    MangleResponder,
    SemanticLaneOwner,
    BloodlustOwner,
    Count
};

enum class MagmawAssignmentRetirementKind : uint8
{
    None,
    Completed
};

struct MagmawAssignmentRetirementInput
{
    MagmawRaidAssignmentSlot Slot = MagmawRaidAssignmentSlot::Count;
    ObjectGuid AssigneeGuid;
    uint64 AssignmentEpoch = 0;
    MagmawAssignmentRetirementKind Kind =
        MagmawAssignmentRetirementKind::None;

    bool Active() const
    {
        return Slot != MagmawRaidAssignmentSlot::Count
            && !AssigneeGuid.IsEmpty() && AssignmentEpoch
            && Kind != MagmawAssignmentRetirementKind::None;
    }
};

struct MagmawRaidAssignment
{
    ObjectGuid AssigneeGuid;
    uint64 Epoch = 0;
};

struct MagmawRaidPlan
{
    static constexpr size_t AssignmentCount =
        size_t(MagmawRaidAssignmentSlot::Count);

    Scope Lifecycle;
    uint64 SourceRevision = 0;
    uint64 Generation = 0;
    bool Authoritative = false;
    std::array<MagmawRaidAssignment, AssignmentCount> Assignments;
    ObjectGuid MangleOwnerGuid;
    bool MangleOwnerAuthoritative = false;

    MagmawRaidAssignment const& Assignment(
        MagmawRaidAssignmentSlot slot) const
    {
        return Assignments[size_t(slot)];
    }

    bool Matches(Scope const& scope, uint64 sourceRevision) const
    {
        return Lifecycle == scope && SourceRevision == sourceRevision;
    }
};
}

#endif
