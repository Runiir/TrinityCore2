#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawCoordinator.h"

#include <algorithm>
#include <map>

namespace BotEncounter
{
namespace
{
using Slot = MagmawRaidAssignmentSlot;

struct Member
{
    ObjectGuid Guid;
    std::string Role;
    std::string ClassSpec;
    bool Alive = false;
    bool Valid = false;
};

size_t Index(Slot slot)
{
    return size_t(slot);
}

std::vector<Member> ExactRoster(Blackboard const& board)
{
    std::map<uint64, Member> byGuid;
    std::set<uint64> duplicates;
    for (ActorSnapshot const& actor : board.Players)
    {
        uint64 const raw = actor.Guid.GetRawValue();
        if (!raw || !byGuid.emplace(raw, Member{ actor.Guid, actor.Role,
            actor.ClassSpec, actor.Alive, true }).second)
            duplicates.insert(raw);
    }

    std::vector<Member> members;
    for (auto& [raw, member] : byGuid)
    {
        bool const knownRole = member.Role == "tank"
            || member.Role == "healer" || member.Role == "dps";
        member.Valid = !duplicates.count(raw) && knownRole
            && !member.ClassSpec.empty();
        members.push_back(member);
    }
    return members;
}

bool Eligible(Member const& member, Slot slot)
{
    if (!member.Valid)
        return false;
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
        case Slot::MangleResponder:
            return member.Role == "healer";
        case Slot::BloodlustOwner:
            return member.Role == "dps"
                && member.ClassSpec == "elemental_shaman";
        case Slot::SemanticLaneOwner:
        case Slot::Count:
            return false;
    }
    return false;
}

Member const* Find(std::vector<Member> const& members, ObjectGuid guid)
{
    auto itr = std::find_if(members.begin(), members.end(),
        [guid](Member const& member) { return member.Guid == guid; });
    return itr == members.end() ? nullptr : &*itr;
}
}

std::shared_ptr<MagmawCoordinator const> MagmawCoordinator::Reconcile(
    std::shared_ptr<MagmawCoordinator const> const& current,
    MagmawFacts const& facts, Blackboard const& board,
    std::vector<MagmawAssignmentRetirementInput> const& retirements)
{
    bool const sourceMatches = facts.Lifecycle == board.CurrentScope
        && facts.ObservationRevision == board.Revision;
    // This is intentionally fail-closed. The current publisher has no exact
    // Magmaw encounter identity or epoch, so production shadow plans remain
    // non-authoritative until those two lifecycle facts are published.
    bool const authoritative = sourceMatches
        && facts.LifecycleAuthoritative && facts.ProjectionAuthoritative
        && facts.OwnsNode == MagmawTruth::True;
    if (current && current->Matches(facts.Lifecycle,
        facts.ObservationRevision) && facts.Lifecycle == board.CurrentScope
        && facts.ObservationRevision == board.Revision
        && current->_plan.Authoritative == authoritative
        && retirements.empty())
        return current;

    std::unique_ptr<MagmawCoordinator> next(new MagmawCoordinator());
    if (current)
    {
        next->_plan = current->_plan;
        next->_retired = current->_retired;
    }

    bool const scopeChanged = !current
        || !(current->_plan.Lifecycle == facts.Lifecycle);
    if (scopeChanged)
        for (auto& retired : next->_retired)
            retired.clear();

    MagmawRaidPlan const before = next->_plan;
    next->_plan.Lifecycle = facts.Lifecycle;
    next->_plan.SourceRevision = facts.ObservationRevision;
    next->_plan.Authoritative = authoritative;

    for (MagmawAssignmentRetirementInput const& input : retirements)
    {
        if (scopeChanged || !input.Active())
            continue;
        MagmawRaidAssignment const& assignment =
            before.Assignment(input.Slot);
        if (assignment.AssigneeGuid == input.AssigneeGuid
            && assignment.Epoch == input.AssignmentEpoch)
            next->_retired[Index(input.Slot)].insert(
                input.AssigneeGuid.GetRawValue());
    }

    std::vector<Member> const members = next->_plan.Authoritative
        ? ExactRoster(board) : std::vector<Member>();
    auto reconcileSlot = [&](Slot slot,
        std::vector<ObjectGuid> const& candidates,
        std::set<uint64> const& excluded = {})
    {
        MagmawRaidAssignment& assignment = next->_plan.Assignments[Index(slot)];
        auto eligible = [&](ObjectGuid guid)
        {
            Member const* member = Find(members, guid);
            return member && member->Alive
                && std::find(candidates.begin(), candidates.end(), guid)
                    != candidates.end()
                && !next->_retired[Index(slot)].count(guid.GetRawValue())
                && !excluded.count(guid.GetRawValue());
        };
        if (next->_plan.Authoritative && !assignment.AssigneeGuid.IsEmpty()
            && !eligible(assignment.AssigneeGuid))
            next->_retired[Index(slot)].insert(
                assignment.AssigneeGuid.GetRawValue());

        ObjectGuid desired;
        if (!scopeChanged && eligible(assignment.AssigneeGuid))
            desired = assignment.AssigneeGuid;
        else
            for (ObjectGuid candidate : candidates)
                if (eligible(candidate))
                {
                    desired = candidate;
                    break;
                }

        if (scopeChanged || assignment.AssigneeGuid != desired)
        {
            if (!assignment.AssigneeGuid.IsEmpty() || !desired.IsEmpty())
                assignment.Epoch = std::max<uint64>(1,
                    assignment.Epoch + 1);
            assignment.AssigneeGuid = desired;
        }
    };
    auto candidates = [&](Slot slot)
    {
        std::vector<ObjectGuid> result;
        for (Member const& member : members)
            if (Eligible(member, slot))
                result.push_back(member.Guid);
        return result;
    };

    reconcileSlot(Slot::FireMageBaiter,
        candidates(Slot::FireMageBaiter));
    reconcileSlot(Slot::MarksmanshipHunterBaiter,
        candidates(Slot::MarksmanshipHunterBaiter));

    std::set<uint64> hookOneExcluded;
    MagmawRaidAssignment const& oldHookTwo = before.Assignment(Slot::HookTwo);
    if (!oldHookTwo.AssigneeGuid.IsEmpty())
        hookOneExcluded.insert(oldHookTwo.AssigneeGuid.GetRawValue());
    reconcileSlot(Slot::HookOne, candidates(Slot::HookOne), hookOneExcluded);
    std::set<uint64> hookTwoExcluded;
    ObjectGuid const hookOne = next->_plan.Assignment(Slot::HookOne).AssigneeGuid;
    if (!hookOne.IsEmpty())
        hookTwoExcluded.insert(hookOne.GetRawValue());
    reconcileSlot(Slot::HookTwo, candidates(Slot::HookTwo), hookTwoExcluded);

    reconcileSlot(Slot::MainPullTank, candidates(Slot::MainPullTank));
    reconcileSlot(Slot::MangleResponder,
        candidates(Slot::MangleResponder));
    std::vector<ObjectGuid> laneCandidates = {
        next->_plan.Assignment(Slot::FireMageBaiter).AssigneeGuid,
        next->_plan.Assignment(Slot::MarksmanshipHunterBaiter).AssigneeGuid };
    laneCandidates.erase(std::remove_if(laneCandidates.begin(),
        laneCandidates.end(), [](ObjectGuid guid) { return guid.IsEmpty(); }),
        laneCandidates.end());
    reconcileSlot(Slot::SemanticLaneOwner, laneCandidates);
    reconcileSlot(Slot::BloodlustOwner, candidates(Slot::BloodlustOwner));

    next->_plan.MangleOwnerAuthoritative = sourceMatches
        && facts.MangleOwnerAuthoritative;
    next->_plan.MangleOwnerGuid = next->_plan.MangleOwnerAuthoritative
        ? facts.MangleOwnerGuid : ObjectGuid();

    bool changed = scopeChanged
        || before.Authoritative != next->_plan.Authoritative
        || before.MangleOwnerAuthoritative
            != next->_plan.MangleOwnerAuthoritative
        || before.MangleOwnerGuid != next->_plan.MangleOwnerGuid;
    for (size_t index = 0; index < MagmawRaidPlan::AssignmentCount; ++index)
        changed = changed
            || before.Assignments[index].AssigneeGuid
                != next->_plan.Assignments[index].AssigneeGuid
            || before.Assignments[index].Epoch
                != next->_plan.Assignments[index].Epoch;
    next->_plan.Generation = before.Generation + (changed ? 1 : 0);
    return std::shared_ptr<MagmawCoordinator const>(next.release());
}
}
