#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawCoordinatorAssignments.h"

#include <algorithm>
#include <array>
#include <set>

namespace BotEncounter
{
namespace
{
using Slot = MagmawRaidAssignmentSlot;

struct AssignmentRule
{
    Slot Value;
    char const* Role;
    char const* ClassSpec;
};

struct CandidatePool
{
    std::vector<ObjectGuid> Assignable;
    std::vector<ObjectGuid> Retainable;
    size_t IdentityCount = 0;
};

std::array<AssignmentRule, 6> const Rules = {{
    { Slot::FireMageBaiter, "dps", "fire_mage" },
    { Slot::MarksmanshipHunterBaiter, "dps", "marksmanship_hunter" },
    { Slot::HookOne, "dps", "" },
    { Slot::HookTwo, "dps", "" },
    { Slot::MainPullTank, "tank", "" },
    { Slot::BloodlustOwner, "dps", "elemental_shaman" }
}};

AssignmentRule const* FindRule(Slot slot)
{
    auto itr = std::find_if(Rules.begin(), Rules.end(),
        [slot](AssignmentRule const& rule) { return rule.Value == slot; });
    return itr == Rules.end() ? nullptr : &*itr;
}

bool MatchesRule(MagmawRosterMember const& member,
    AssignmentRule const& rule)
{
    return member.Role == rule.Role
        && (!*rule.ClassSpec || member.ClassSpec == rule.ClassSpec);
}

CandidatePool BuildCandidates(std::vector<MagmawRosterMember> const& members,
    MagmawRosterObservations const& observations, Slot slot,
    bool authoritative, bool mainTankConfigured = false,
    ObjectGuid configuredMainTank = {})
{
    CandidatePool pool;
    AssignmentRule const* rule = FindRule(slot);
    if (!authoritative || !rule)
        return pool;
    for (MagmawRosterMember const& member : members)
    {
        if (!MatchesRule(member, *rule))
            continue;
        if (slot == Slot::MainPullTank && mainTankConfigured
            && member.Guid != configuredMainTank)
            continue;
        ++pool.IdentityCount;
        MagmawRosterLiveness const liveness = ObserveMagmawRosterMember(
            observations, member.Guid);
        if (liveness == MagmawRosterLiveness::Alive)
            pool.Assignable.push_back(member.Guid);
        if (liveness != MagmawRosterLiveness::Dead
            && liveness != MagmawRosterLiveness::Invalid)
            pool.Retainable.push_back(member.Guid);
    }
    return pool;
}

bool Contains(std::vector<ObjectGuid> const& values, ObjectGuid value)
{
    return std::find(values.begin(), values.end(), value) != values.end();
}

ObjectGuid FirstAvailable(std::vector<ObjectGuid> const& choices,
    std::set<uint64> const& excluded)
{
    auto itr = std::find_if(choices.begin(), choices.end(),
        [&excluded](ObjectGuid guid)
        {
            return !guid.IsEmpty()
                && !excluded.count(guid.GetRawValue());
        });
    return itr == choices.end() ? ObjectGuid() : *itr;
}

void ReconcileSlot(MagmawRaidPlan& plan, MagmawRaidPlan const& before,
    Slot slot, CandidatePool const& pool, bool scopeChanged,
    std::set<uint64> const& excluded = {})
{
    MagmawRaidAssignment const* assignment = before.FindAssignment(slot);
    if (!assignment)
        return;
    bool const retain = !scopeChanged
        && Contains(pool.Retainable, assignment->AssigneeGuid)
        && !excluded.count(assignment->AssigneeGuid.GetRawValue());
    ObjectGuid const desired = retain ? assignment->AssigneeGuid
        : FirstAvailable(pool.Assignable, excluded);
    plan.ApplyAssignment(slot, desired, scopeChanged);
}

void ReconcileStandardSlots(MagmawRaidPlan& plan,
    MagmawRaidPlan const& before,
    std::vector<MagmawRosterMember> const& members,
    MagmawRosterObservations const& observations, bool authoritative,
    bool scopeChanged, bool mainTankConfigured,
    ObjectGuid configuredMainTank)
{
    for (Slot slot : { Slot::FireMageBaiter,
        Slot::MarksmanshipHunterBaiter, Slot::MainPullTank })
        ReconcileSlot(plan, before, slot,
            BuildCandidates(members, observations, slot, authoritative,
                mainTankConfigured, configuredMainTank),
            scopeChanged);
}

void ReconcileHooks(MagmawRaidPlan& plan, MagmawRaidPlan const& before,
    std::vector<MagmawRosterMember> const& members,
    MagmawRosterObservations const& observations, bool authoritative,
    bool scopeChanged)
{
    CandidatePool const hookOne = BuildCandidates(members, observations,
        Slot::HookOne, authoritative);
    CandidatePool const hookTwo = BuildCandidates(members, observations,
        Slot::HookTwo, authoritative);
    std::set<uint64> excluded;
    if (MagmawRaidAssignment const* oldHookTwo = before.FindAssignment(
        Slot::HookTwo); oldHookTwo && !oldHookTwo->AssigneeGuid.IsEmpty())
        excluded.insert(oldHookTwo->AssigneeGuid.GetRawValue());
    ReconcileSlot(plan, before, Slot::HookOne, hookOne, scopeChanged,
        excluded);
    excluded.clear();
    if (MagmawRaidAssignment const* newHookOne = plan.FindAssignment(
        Slot::HookOne); newHookOne && !newHookOne->AssigneeGuid.IsEmpty())
        excluded.insert(newHookOne->AssigneeGuid.GetRawValue());
    ReconcileSlot(plan, before, Slot::HookTwo, hookTwo, scopeChanged,
        excluded);
}

void ReconcileLane(MagmawRaidPlan& plan, MagmawRaidPlan const& before,
    MagmawRosterObservations const& observations, bool authoritative,
    bool scopeChanged)
{
    CandidatePool lane;
    if (authoritative)
        for (Slot slot : { Slot::FireMageBaiter,
            Slot::MarksmanshipHunterBaiter })
            if (MagmawRaidAssignment const* bait = plan.FindAssignment(slot);
                bait && !bait->AssigneeGuid.IsEmpty())
            {
                lane.Retainable.push_back(bait->AssigneeGuid);
                if (ObserveMagmawRosterMember(observations,
                    bait->AssigneeGuid) == MagmawRosterLiveness::Alive)
                    lane.Assignable.push_back(bait->AssigneeGuid);
            }
    ReconcileSlot(plan, before, Slot::SemanticLaneOwner, lane, scopeChanged);
}

void ReconcileBloodlust(MagmawRaidPlan& plan, MagmawRaidPlan const& before,
    std::vector<MagmawRosterMember> const& members,
    MagmawRosterObservations const& observations, bool authoritative,
    bool scopeChanged)
{
    CandidatePool pool = BuildCandidates(members, observations,
        Slot::BloodlustOwner, authoritative);
    if (pool.IdentityCount != 1)
        pool = CandidatePool();
    ReconcileSlot(plan, before, Slot::BloodlustOwner, pool, scopeChanged);
}
}

MagmawRosterObservations BuildMagmawRosterObservations(
    Blackboard const& board)
{
    MagmawRosterObservations observations;
    for (ActorSnapshot const& actor : board.Players)
    {
        uint64 const guid = actor.Guid.GetRawValue();
        if (!guid)
            continue;
        MagmawRosterLiveness const value = actor.Kind == ActorKind::Player
            ? actor.Alive ? MagmawRosterLiveness::Alive
                : MagmawRosterLiveness::Dead
            : MagmawRosterLiveness::Invalid;
        if (!observations.emplace(guid, value).second)
            observations[guid] = MagmawRosterLiveness::Invalid;
    }
    return observations;
}

MagmawRosterLiveness ObserveMagmawRosterMember(
    MagmawRosterObservations const& observations, ObjectGuid guid)
{
    auto itr = observations.find(guid.GetRawValue());
    return itr == observations.end() ? MagmawRosterLiveness::Unobserved
        : itr->second;
}

void ReconcileMagmawAssignments(MagmawRaidPlan& plan,
    MagmawRaidPlan const& before,
    std::vector<MagmawRosterMember> const& members,
    MagmawRosterObservations const& observations, bool authoritative,
    bool scopeChanged, bool mainTankConfigured,
    ObjectGuid configuredMainTank)
{
    if (!authoritative && !scopeChanged)
        return;
    ReconcileStandardSlots(plan, before, members, observations,
        authoritative, scopeChanged, mainTankConfigured,
        configuredMainTank);
    ReconcileHooks(plan, before, members, observations, authoritative,
        scopeChanged);
    ReconcileLane(plan, before, observations, authoritative, scopeChanged);
    ReconcileBloodlust(plan, before, members, observations, authoritative,
        scopeChanged);
}
}
