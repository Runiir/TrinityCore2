#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawCoordinator.h"

#include <algorithm>
#include <map>
#include <set>

namespace BotEncounter
{
namespace
{
using Slot = MagmawRaidAssignmentSlot;

enum class Liveness : uint8
{
    Unobserved,
    Alive,
    Dead,
    Invalid
};

bool KnownRole(std::string const& role)
{
    return role == "tank" || role == "healer" || role == "dps";
}

bool ModeSize(MagmawRaidMode mode, uint32& size)
{
    switch (mode)
    {
        case MagmawRaidMode::Unknown:
            return false;
        case MagmawRaidMode::Normal10:
        case MagmawRaidMode::Heroic10:
            size = 10;
            return true;
        case MagmawRaidMode::Normal25:
        case MagmawRaidMode::Heroic25:
            size = 25;
            return true;
    }
    return false;
}

std::vector<MagmawRosterMember> CanonicalRoster(MagmawRosterView const& view,
    bool& valid)
{
    std::vector<MagmawRosterMember> members = view.Members;
    std::sort(members.begin(), members.end(),
        [](MagmawRosterMember const& left, MagmawRosterMember const& right)
        {
            return left.Guid.GetRawValue() < right.Guid.GetRawValue();
        });
    uint32 modeSize = 0;
    valid = view.Authoritative && view.Generation && ModeSize(view.Mode,
        modeSize) && view.ExpectedSize == modeSize
        && members.size() == modeSize;

    std::set<uint64> guids;
    std::set<std::string> slots;
    for (MagmawRosterMember const& member : members)
        valid = valid && !member.Guid.IsEmpty()
            && !member.RosterSlotId.empty() && KnownRole(member.Role)
            && !member.ClassSpec.empty()
            && member.Admitted && member.LeaseOwned
            && guids.insert(member.Guid.GetRawValue()).second
            && slots.insert(member.RosterSlotId).second;
    return members;
}

std::map<uint64, Liveness> ObserveLiveness(Blackboard const& board)
{
    std::map<uint64, Liveness> observations;
    for (ActorSnapshot const& actor : board.Players)
    {
        uint64 const guid = actor.Guid.GetRawValue();
        if (!guid)
            continue;
        Liveness const value = actor.Kind == ActorKind::Player
            ? actor.Alive ? Liveness::Alive : Liveness::Dead
            : Liveness::Invalid;
        if (!observations.emplace(guid, value).second)
            observations[guid] = Liveness::Invalid;
    }
    return observations;
}

Liveness Observed(std::map<uint64, Liveness> const& observations,
    ObjectGuid guid)
{
    auto itr = observations.find(guid.GetRawValue());
    return itr == observations.end() ? Liveness::Unobserved : itr->second;
}

bool Eligible(MagmawRosterMember const& member, Slot slot)
{
    switch (slot)
    {
        case Slot::FireMageBaiter:
            return member.Role == "dps" && member.ClassSpec == "fire_mage";
        case Slot::MarksmanshipHunterBaiter:
            return member.Role == "dps"
                && member.ClassSpec == "marksmanship_hunter";
        case Slot::HookOne:
        case Slot::HookTwo:
            return member.Role == "dps";
        case Slot::MainPullTank:
            return member.Role == "tank";
        case Slot::BloodlustOwner:
            return member.Role == "dps"
                && member.ClassSpec == "elemental_shaman";
        case Slot::SemanticLaneOwner:
        case Slot::Count:
            return false;
    }
    return false;
}

MagmawRosterMember const* Find(std::vector<MagmawRosterMember> const& members,
    ObjectGuid guid)
{
    auto itr = std::find_if(members.begin(), members.end(),
        [guid](MagmawRosterMember const& member)
        {
            return member.Guid == guid;
        });
    return itr == members.end() ? nullptr : &*itr;
}
}

std::shared_ptr<MagmawCoordinator const> MagmawCoordinator::Reconcile(
    std::shared_ptr<MagmawCoordinator const> const& current,
    MagmawFacts const& facts, Blackboard const& board,
    MagmawRosterView const& roster)
{
    bool rosterValid = false;
    std::vector<MagmawRosterMember> const members = CanonicalRoster(roster,
        rosterValid);
    bool const sourceMatches = facts.Lifecycle == board.CurrentScope
        && facts.ObservationRevision == board.Revision
        && roster.Lifecycle == facts.Lifecycle;
    // The current publisher has no exact Magmaw identity or encounter epoch.
    // Assignments remain empty until both facts and the admitted roster agree.
    bool const authoritative = sourceMatches && facts.LifecycleAuthoritative
        && facts.ProjectionAuthoritative
        && facts.OwnsNode == MagmawTruth::True && rosterValid;
    if (current && current->Matches(facts.Lifecycle,
        facts.ObservationRevision, roster.Generation)
        && current->_plan.Authoritative == authoritative)
        return current;

    std::unique_ptr<MagmawCoordinator> next(new MagmawCoordinator());
    if (current)
        next->_plan = current->_plan;
    MagmawRaidPlan const before = next->_plan;
    bool const scopeChanged = !current || !(before.Lifecycle == facts.Lifecycle);
    bool const rosterChanged = !current || before.RosterGeneration != roster.Generation;
    next->_plan.Lifecycle = facts.Lifecycle;
    next->_plan.SourceRevision = facts.ObservationRevision;
    next->_plan.RosterGeneration = roster.Generation;
    next->_plan.RosterExpectedSize = roster.ExpectedSize;
    next->_plan.RosterMode = roster.Mode;
    next->_plan.Authoritative = authoritative;

    std::map<uint64, Liveness> const observations = ObserveLiveness(board);
    auto candidates = [&](Slot slot, bool newAssignment)
    {
        std::vector<ObjectGuid> result;
        if (authoritative)
            for (MagmawRosterMember const& member : members)
            {
                Liveness const live = Observed(observations, member.Guid);
                if (Eligible(member, slot) && (newAssignment
                    ? live == Liveness::Alive
                    : live != Liveness::Dead && live != Liveness::Invalid))
                        result.push_back(member.Guid);
            }
        return result;
    };
    auto reconcileSlot = [&](Slot slot,
        std::vector<ObjectGuid> const& choices,
        std::vector<ObjectGuid> const& retainable,
        std::set<uint64> const& excluded = {})
    {
        MagmawRaidAssignment* assignment = next->_plan.MutableAssignment(slot);
        if (!assignment)
            return;
        auto usable = [&](ObjectGuid guid)
        {
            return !guid.IsEmpty()
                && std::find(choices.begin(), choices.end(), guid)
                    != choices.end()
                && !excluded.count(guid.GetRawValue());
        };
        ObjectGuid desired;
        bool const retain = std::find(retainable.begin(), retainable.end(),
            assignment->AssigneeGuid) != retainable.end()
            && !excluded.count(assignment->AssigneeGuid.GetRawValue());
        if (!scopeChanged && retain)
            desired = assignment->AssigneeGuid;
        else
            for (ObjectGuid choice : choices)
                if (usable(choice))
                {
                    desired = choice;
                    break;
                }
        if (scopeChanged || assignment->AssigneeGuid != desired)
        {
            if (!assignment->AssigneeGuid.IsEmpty() || !desired.IsEmpty())
                assignment->Epoch = std::max<uint64>(1,
                    assignment->Epoch + 1);
            assignment->AssigneeGuid = desired;
        }
    };

    if (authoritative || scopeChanged)
    {
        auto reconcileStandard = [&](Slot slot)
        {
            reconcileSlot(slot, candidates(slot, true),
                candidates(slot, false));
        };
        reconcileStandard(Slot::FireMageBaiter);
        reconcileStandard(Slot::MarksmanshipHunterBaiter);
        std::set<uint64> hookOneExcluded;
        if (MagmawRaidAssignment const* hookTwo = before.FindAssignment(
            Slot::HookTwo); hookTwo && !hookTwo->AssigneeGuid.IsEmpty())
            hookOneExcluded.insert(hookTwo->AssigneeGuid.GetRawValue());
        reconcileSlot(Slot::HookOne, candidates(Slot::HookOne, true),
            candidates(Slot::HookOne, false), hookOneExcluded);
        std::set<uint64> hookTwoExcluded;
        if (MagmawRaidAssignment const* hookOne = next->_plan.FindAssignment(
            Slot::HookOne); hookOne && !hookOne->AssigneeGuid.IsEmpty())
            hookTwoExcluded.insert(hookOne->AssigneeGuid.GetRawValue());
        reconcileSlot(Slot::HookTwo, candidates(Slot::HookTwo, true),
            candidates(Slot::HookTwo, false), hookTwoExcluded);
        reconcileStandard(Slot::MainPullTank);

        std::vector<ObjectGuid> laneRetainable;
        std::vector<ObjectGuid> laneChoices;
        for (Slot slot : { Slot::FireMageBaiter,
            Slot::MarksmanshipHunterBaiter })
            if (MagmawRaidAssignment const* bait =
                next->_plan.FindAssignment(slot);
                bait && !bait->AssigneeGuid.IsEmpty())
            {
                laneRetainable.push_back(bait->AssigneeGuid);
                if (Observed(observations, bait->AssigneeGuid)
                    == Liveness::Alive)
                    laneChoices.push_back(bait->AssigneeGuid);
            }
        reconcileSlot(Slot::SemanticLaneOwner, laneChoices, laneRetainable);
        std::vector<ObjectGuid> bloodlustRoster = candidates(
            Slot::BloodlustOwner, false);
        std::vector<ObjectGuid> bloodlust = candidates(
            Slot::BloodlustOwner, true);
        size_t const bloodlustOwners = std::count_if(members.begin(),
            members.end(), [](MagmawRosterMember const& member)
            { return Eligible(member, Slot::BloodlustOwner); });
        if (!authoritative || bloodlustOwners != 1)
        {
            bloodlust.clear();
            bloodlustRoster.clear();
        }
        reconcileSlot(Slot::BloodlustOwner, bloodlust, bloodlustRoster);
    }
    next->_plan.MangleOwnerAuthoritative = authoritative
        && facts.MangleOwnerAuthoritative;
    next->_plan.MangleOwnerGuid = next->_plan.MangleOwnerAuthoritative
        ? facts.MangleOwnerGuid : ObjectGuid();
    if (next->_plan.MangleOwnerAuthoritative)
    {
        MagmawRosterMember const* owner = Find(members,
            next->_plan.MangleOwnerGuid);
        if (!owner || Observed(observations, owner->Guid) != Liveness::Alive)
        {
            next->_plan.MangleOwnerAuthoritative = false;
            next->_plan.MangleOwnerGuid.Clear();
        }
    }

    bool changed = scopeChanged || rosterChanged
        || before.RosterExpectedSize != next->_plan.RosterExpectedSize
        || before.RosterMode != next->_plan.RosterMode
        || before.Authoritative != next->_plan.Authoritative
        || before.MangleOwnerAuthoritative
            != next->_plan.MangleOwnerAuthoritative
        || before.MangleOwnerGuid != next->_plan.MangleOwnerGuid;
    auto const& oldAssignments = before.AllAssignments();
    auto const& newAssignments = next->_plan.AllAssignments();
    for (size_t index = 0; index < MagmawRaidPlan::AssignmentCount; ++index)
        changed = changed
            || oldAssignments[index].AssigneeGuid
                != newAssignments[index].AssigneeGuid
            || oldAssignments[index].Epoch != newAssignments[index].Epoch;
    next->_plan.Generation = before.Generation + (changed ? 1 : 0);
    return std::shared_ptr<MagmawCoordinator const>(next.release());
}
}
