#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawCoordinator.h"

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawCoordinatorAssignments.h"

#include <algorithm>
#include <array>
#include <initializer_list>
#include <set>
#include <sstream>
#include <tuple>

namespace BotEncounter
{
namespace
{
struct RosterAdmission
{
    std::vector<MagmawRosterMember> Members;
    std::string Fingerprint;
    bool Authoritative = false;
};

bool AllTrue(std::initializer_list<bool> values)
{
    return std::all_of(values.begin(), values.end(),
        [](bool value) { return value; });
}

bool AnyTrue(std::initializer_list<bool> values)
{
    return std::any_of(values.begin(), values.end(),
        [](bool value) { return value; });
}

bool KnownRole(std::string const& role)
{
    std::array<std::string, 3> const roles = { "tank", "healer", "dps" };
    return std::find(roles.begin(), roles.end(), role) != roles.end();
}

uint32 ExpectedModeSize(MagmawRaidMode mode)
{
    using ModeSize = std::pair<MagmawRaidMode, uint32>;
    std::array<ModeSize, 4> const sizes = {{
        { MagmawRaidMode::Normal10, 10 },
        { MagmawRaidMode::Heroic10, 10 },
        { MagmawRaidMode::Normal25, 25 },
        { MagmawRaidMode::Heroic25, 25 }
    }};
    auto itr = std::find_if(sizes.begin(), sizes.end(),
        [mode](ModeSize const& value) { return value.first == mode; });
    return itr == sizes.end() ? 0 : itr->second;
}

bool ValidRosterMember(MagmawRosterMember const& member)
{
    return AllTrue({ !member.Guid.IsEmpty(), !member.RosterSlotId.empty(),
        KnownRole(member.Role), !member.ClassSpec.empty(), member.Admitted,
        member.LeaseOwned });
}

void AppendToken(std::ostringstream& stream, std::string const& value)
{
    stream << value.size() << ':' << value << ';';
}

void AppendScope(std::ostringstream& stream, Scope const& scope)
{
    stream << scope.ServerEpoch << ';';
    AppendToken(stream, scope.CohortId);
    stream << scope.AttemptId << ';' << scope.WipeGeneration << ';'
        << scope.RouteGeneration << ';';
    AppendToken(stream, scope.NodeId);
    stream << scope.MapId << ';' << scope.InstanceId << ';';
    AppendToken(stream, scope.EncounterId);
    stream << scope.EncounterEpoch << ';';
}

std::string RosterFingerprint(MagmawRosterView const& view,
    std::vector<MagmawRosterMember> const& members)
{
    std::ostringstream stream;
    AppendScope(stream, view.Lifecycle);
    stream << unsigned(view.Mode) << ';' << view.ExpectedSize << ';'
        << view.Authoritative << ';' << members.size() << ';';
    for (MagmawRosterMember const& member : members)
    {
        stream << member.Guid.GetRawValue() << ';';
        AppendToken(stream, member.RosterSlotId);
        AppendToken(stream, member.Role);
        AppendToken(stream, member.ClassSpec);
        stream << member.Admitted << ';' << member.LeaseOwned << ';';
    }
    return stream.str();
}

RosterAdmission AdmitCanonicalRoster(MagmawRosterView const& view)
{
    RosterAdmission result;
    result.Members = view.Members;
    std::sort(result.Members.begin(), result.Members.end(),
        [](MagmawRosterMember const& left,
            MagmawRosterMember const& right)
        {
            return std::tie(left.Guid, left.RosterSlotId, left.Role,
                left.ClassSpec, left.Admitted, left.LeaseOwned)
                < std::tie(right.Guid, right.RosterSlotId, right.Role,
                    right.ClassSpec, right.Admitted, right.LeaseOwned);
        });
    result.Fingerprint = RosterFingerprint(view, result.Members);
    uint32 const modeSize = ExpectedModeSize(view.Mode);
    result.Authoritative = AllTrue({ view.Authoritative,
        view.Generation != 0, modeSize != 0, view.ExpectedSize == modeSize,
        result.Members.size() == modeSize });
    std::set<uint64> guids;
    std::set<std::string> slots;
    for (MagmawRosterMember const& member : result.Members)
        result.Authoritative = AllTrue({ result.Authoritative,
            ValidRosterMember(member),
            guids.insert(member.Guid.GetRawValue()).second,
            slots.insert(member.RosterSlotId).second });
    return result;
}

bool SourcesAuthoritative(MagmawFacts const& facts, Blackboard const& board,
    MagmawRosterView const& roster, RosterAdmission const& admission)
{
    // Production facts intentionally fail closed until an exact encounter
    // identity and encounter epoch make LifecycleAuthoritative true.
    return AllTrue({ facts.Lifecycle == board.CurrentScope,
        facts.ObservationRevision == board.Revision,
        roster.Lifecycle == facts.Lifecycle,
        facts.LifecycleAuthoritative, facts.ProjectionAuthoritative,
        facts.OwnsNode == MagmawTruth::True, admission.Authoritative });
}

MagmawRosterMember const* FindMember(
    std::vector<MagmawRosterMember> const& members, ObjectGuid guid)
{
    auto itr = std::find_if(members.begin(), members.end(),
        [guid](MagmawRosterMember const& member)
        {
            return member.Guid == guid;
        });
    return itr == members.end() ? nullptr : &*itr;
}

void ObserveMangleOwner(MagmawRaidPlan& plan, MagmawFacts const& facts,
    std::vector<MagmawRosterMember> const& members,
    MagmawRosterObservations const& observations)
{
    plan.MangleOwnerAuthoritative = plan.Authoritative
        && facts.MangleOwnerAuthoritative;
    plan.MangleOwnerGuid = plan.MangleOwnerAuthoritative
        ? facts.MangleOwnerGuid : ObjectGuid();
    MagmawRosterMember const* owner = FindMember(members,
        plan.MangleOwnerGuid);
    if (plan.MangleOwnerAuthoritative && (!owner
        || ObserveMagmawRosterMember(observations, owner->Guid)
            != MagmawRosterLiveness::Alive))
    {
        plan.MangleOwnerAuthoritative = false;
        plan.MangleOwnerGuid.Clear();
    }
}

bool AssignmentsChanged(MagmawRaidPlan const& before,
    MagmawRaidPlan const& after)
{
    auto const& oldAssignments = before.AllAssignments();
    auto const& newAssignments = after.AllAssignments();
    return !std::equal(oldAssignments.begin(), oldAssignments.end(),
        newAssignments.begin());
}

void FinalizePlan(MagmawRaidPlan& plan, MagmawRaidPlan const& before,
    bool scopeChanged)
{
    bool const changed = AnyTrue({ scopeChanged,
        before.RosterGeneration != plan.RosterGeneration,
        before.RosterExpectedSize != plan.RosterExpectedSize,
        before.RosterMode != plan.RosterMode,
        before.RosterFingerprint != plan.RosterFingerprint,
        before.Authoritative != plan.Authoritative,
        before.MangleOwnerAuthoritative != plan.MangleOwnerAuthoritative,
        before.MangleOwnerGuid != plan.MangleOwnerGuid,
        AssignmentsChanged(before, plan) });
    plan.Generation = before.Generation + (changed ? 1 : 0);
}
}

std::shared_ptr<MagmawCoordinator const> MagmawCoordinator::Reconcile(
    std::shared_ptr<MagmawCoordinator const> const& current,
    MagmawFacts const& facts, Blackboard const& board,
    MagmawRosterView const& roster)
{
    RosterAdmission const admission = AdmitCanonicalRoster(roster);
    bool const authoritative = SourcesAuthoritative(facts, board, roster,
        admission);
    if (current && current->_plan.Matches(facts.Lifecycle,
        facts.ObservationRevision, roster.Generation,
        admission.Fingerprint)
        && current->_plan.Authoritative == authoritative)
        return current;

    std::unique_ptr<MagmawCoordinator> next(new MagmawCoordinator());
    if (current)
        next->_plan = current->_plan;
    MagmawRaidPlan const before = next->_plan;
    bool const scopeChanged = !current
        || !(before.Lifecycle == facts.Lifecycle);
    next->_plan.Lifecycle = facts.Lifecycle;
    next->_plan.SourceRevision = facts.ObservationRevision;
    next->_plan.RosterGeneration = roster.Generation;
    next->_plan.RosterExpectedSize = roster.ExpectedSize;
    next->_plan.RosterMode = roster.Mode;
    next->_plan.RosterFingerprint = admission.Fingerprint;
    next->_plan.Authoritative = authoritative;

    MagmawRosterObservations const observations =
        BuildMagmawRosterObservations(board);
    bool mainTankConfigured = false;
    ObjectGuid configuredMainTank;
    for (AssignmentLease const& lease : board.Assignments)
        if (lease.Kind == AssignmentKind::Tank && lease.Slot == "main_tank")
        {
            mainTankConfigured = true;
            configuredMainTank = lease.AssigneeGuid;
            break;
        }
    ReconcileMagmawAssignments(next->_plan, before, admission.Members,
        observations, authoritative, scopeChanged, mainTankConfigured,
        configuredMainTank);
    ObserveMangleOwner(next->_plan, facts, admission.Members, observations);
    FinalizePlan(next->_plan, before, scopeChanged);
    return std::shared_ptr<MagmawCoordinator const>(next.release());
}
}
