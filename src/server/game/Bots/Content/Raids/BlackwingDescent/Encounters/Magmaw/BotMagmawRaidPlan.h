#ifndef TRINITY_BOT_MAGMAW_RAID_PLAN_H
#define TRINITY_BOT_MAGMAW_RAID_PLAN_H

#include "Bots/BotEncounterBlackboard.h"

#include <algorithm>
#include <array>
#include <string>
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
    SemanticLaneOwner,
    BloodlustOwner,
    Count
};

enum class MagmawRaidMode : uint8
{
    Unknown,
    Normal10,
    Heroic10,
    Normal25,
    Heroic25
};

struct MagmawRosterMember
{
    ObjectGuid Guid;
    std::string RosterSlotId;
    std::string Role;
    std::string ClassSpec;
    bool Admitted = false;
    bool LeaseOwned = false;
};

// Immutable view of the admitted roster. Generation is the source's revision;
// the coordinator also fingerprints every semantic field and therefore fails
// closed if a source accidentally mutates the view without advancing it.
struct MagmawRosterView
{
    Scope Lifecycle;
    uint64 Generation = 0;
    uint32 ExpectedSize = 0;
    MagmawRaidMode Mode = MagmawRaidMode::Unknown;
    bool Authoritative = false;
    std::vector<MagmawRosterMember> Members;
};

struct MagmawRaidAssignment
{
    ObjectGuid AssigneeGuid;
    uint64 Epoch = 0;

    friend bool operator==(MagmawRaidAssignment const& left,
        MagmawRaidAssignment const& right)
    {
        return left.AssigneeGuid == right.AssigneeGuid
            && left.Epoch == right.Epoch;
    }
};

class MagmawRaidPlan
{
public:
    static constexpr size_t AssignmentCount =
        size_t(MagmawRaidAssignmentSlot::Count);

    Scope Lifecycle;
    uint64 SourceRevision = 0;
    uint64 RosterGeneration = 0;
    uint64 Generation = 0;
    uint32 RosterExpectedSize = 0;
    MagmawRaidMode RosterMode = MagmawRaidMode::Unknown;
    std::string RosterFingerprint;
    bool Authoritative = false;
    ObjectGuid MangleOwnerGuid;
    bool MangleOwnerAuthoritative = false;

    static bool ValidSlot(MagmawRaidAssignmentSlot slot)
    {
        return size_t(slot) < AssignmentCount;
    }

    MagmawRaidAssignment const* FindAssignment(
        MagmawRaidAssignmentSlot slot) const
    {
        return ValidSlot(slot) ? &_assignments[size_t(slot)] : nullptr;
    }

    std::array<MagmawRaidAssignment, AssignmentCount> const&
    AllAssignments() const
    {
        return _assignments;
    }

    bool Matches(Scope const& scope, uint64 sourceRevision,
        uint64 rosterGeneration, std::string const& rosterFingerprint) const
    {
        return Lifecycle == scope && SourceRevision == sourceRevision
            && RosterGeneration == rosterGeneration
            && RosterFingerprint == rosterFingerprint;
    }

    bool ApplyAssignment(MagmawRaidAssignmentSlot slot, ObjectGuid desired,
        bool scopeChanged)
    {
        MagmawRaidAssignment* assignment = MutableAssignment(slot);
        if (!assignment || (!scopeChanged
            && assignment->AssigneeGuid == desired))
            return false;
        if (!assignment->AssigneeGuid.IsEmpty() || !desired.IsEmpty())
            assignment->Epoch = std::max<uint64>(1, assignment->Epoch + 1);
        assignment->AssigneeGuid = desired;
        return true;
    }

private:
    friend class MagmawCoordinator;

    MagmawRaidAssignment* MutableAssignment(MagmawRaidAssignmentSlot slot)
    {
        return ValidSlot(slot) ? &_assignments[size_t(slot)] : nullptr;
    }

    std::array<MagmawRaidAssignment, AssignmentCount> _assignments;
};
}

#endif
