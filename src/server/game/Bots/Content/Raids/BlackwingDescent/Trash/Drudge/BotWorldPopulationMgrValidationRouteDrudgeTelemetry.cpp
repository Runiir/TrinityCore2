#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"

#include "Creature.h"
#include "GameTime.h"
#include "Player.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstring>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

bool SamePoint(float x, float y, float z, float otherX, float otherY,
    float otherZ)
{
    return std::hypot(x - otherX, y - otherY) <= 0.01f
        && std::fabs(z - otherZ) <= 0.01f;
}
}

namespace BotWorldPopulationMgrValidationRoute
{
using WorldBotState = BotWorldPopulationMgrBotState::WorldBotState;
using RecoveryMemberDiagnostic = BotRaidDrudgeSpacing::RecoveryMemberDiagnostic;
using RecoveryTick = BotRaidDrudgeSpacing::RecoveryTick;
using NativeTransition = BotRaidDrudgeSpacing::NativeTransition;

void DrudgeLaneContext::RecordRecoveryDiagnosticTick(
    uint64 observedAtMs, bool allRecoveryAnchorsReached,
    bool allRecoveryTankPathsProven, bool allCombatTankPathsProven,
    bool allCombatTankAnchorsReached, bool exactRosterReseparated)
{
    if (!Charge || !Charge->Landed || Charge->ReseparationRecorded
        || Sources.size() != 2)
        return;

    BotRaidDrudgeGeometry::Scope const scope{
        Manager.Cohort().AttemptId, Manager.Cohort().Raid.WipeGeneration,
        Manager.Party().ValidationRouteGeneration, Bot->GetMapId(),
        Bot->GetInstanceId(), Sources[0]->GetGUID().GetRawValue(),
        Sources[1]->GetGUID().GetRawValue() };
    RecoveryTick tick;
    tick.Scope = scope;
    tick.Sequence = Charge->Sequence;
    tick.ObservedAtMs = observedAtMs;
    tick.LandedRushPending = NativeChargePending;
    tick.RecoveryFormationActive = RecoveryFormationActive;
    tick.RecoveryBarrierOpen = Charge->RecoveryTankReturnBarrierOpened;
    tick.Source0Alive = Sources[0]->IsAlive();
    tick.Source1Alive = Sources[1]->IsAlive();
    tick.Source0X = Sources[0]->GetPositionX();
    tick.Source0Y = Sources[0]->GetPositionY();
    tick.Source0Z = Sources[0]->GetPositionZ();
    tick.Source1X = Sources[1]->GetPositionX();
    tick.Source1Y = Sources[1]->GetPositionY();
    tick.Source1Z = Sources[1]->GetPositionZ();
    tick.Source0Guid = Sources[0]->GetGUID().GetCounter();
    tick.Source1Guid = Sources[1]->GetGUID().GetCounter();
    tick.Source0VictimGuid = Sources[0]->GetVictim()
        ? Sources[0]->GetVictim()->GetGUID().GetCounter() : 0;
    tick.Source1VictimGuid = Sources[1]->GetVictim()
        ? Sources[1]->GetVictim()->GetGUID().GetCounter() : 0;
    tick.AllRecoveryAnchorsReached = allRecoveryAnchorsReached;
    tick.AllRecoveryTankPathsProven = allRecoveryTankPathsProven;
    tick.AllCombatTankPathsProven = allCombatTankPathsProven;
    tick.AllCombatTankAnchorsReached = allCombatTankAnchorsReached;
    tick.ExactRosterReseparated = exactRosterReseparated;
    tick.LandedRushRecoveryComplete = BotRaidDrudgeGeometry::LandedRushRecoveryComplete(
        tick.LandedRushPending, tick.AllRecoveryAnchorsReached,
        tick.AllCombatTankPathsProven, tick.AllCombatTankAnchorsReached,
        tick.ExactRosterReseparated);

    auto const& config = Manager.Cohort().Config;
    bool const sourcePairSeparated = Sources[0]->GetExactDist2d(Sources[1])
        >= LaneSeparation;
    bool const sourceLanesSafe = SourceOnFrozenLane(Sources[0], 0, nullptr)
        && SourceOnFrozenLane(Sources[1], 1, nullptr);
    Player const* source0Tank = LaneIndex == 0 ? LaneTank : OtherTank;
    Player const* source1Tank = LaneIndex == 1 ? LaneTank : OtherTank;
    bool const victimOwnershipSafe = (!Sources[0]->IsAlive()
            || Sources[0]->GetVictim() == source0Tank)
        && (!Sources[1]->IsAlive()
            || Sources[1]->GetVictim() == source1Tank);
    bool const commonRosterSafe = sourcePairSeparated && sourceLanesSafe
        && TanksOnFrozenLanes() && victimOwnershipSafe;

    for (WorldBotState const& cohortState : Manager.Party().Bots)
    {
        if (tick.Members.size() >= BotRaidDrudgeSpacing::MaximumRecoveryMembers)
            break;
        RecoveryMemberDiagnostic memberDiagnostic;
        memberDiagnostic.Guid = cohortState.Guid.GetCounter();
        Player* member = Manager.GetLoadedBot(cohortState);
        if (!member)
        {
            tick.Members.push_back(memberDiagnostic);
            continue;
        }
        memberDiagnostic.InWorld = member->IsInWorld();
        memberDiagnostic.Alive = member->IsAlive();
        memberDiagnostic.SameMap = member->GetMap() == Bot->GetMap();
        memberDiagnostic.X = member->GetPositionX();
        memberDiagnostic.Y = member->GetPositionY();
        memberDiagnostic.Z = member->GetPositionZ();
        auto roster = Manager.Cohort().Raid.RosterByGuid.find(
            member->GetGUID().GetCounter());
        if (roster == Manager.Cohort().Raid.RosterByGuid.end())
        {
            tick.Members.push_back(memberDiagnostic);
            continue;
        }
        memberDiagnostic.Guid = member->GetGUID().GetCounter();
        memberDiagnostic.RosterSlot = roster->second.SlotIndex + 1;
        memberDiagnostic.IsTank = roster->second.Role == "tank";
        memberDiagnostic.ActiveLease = roster->second.Active
            && roster->second.LeaseOwned;
        uint32 const slot = memberDiagnostic.RosterSlot;
        bool const laneA = std::find(config.ValidationRouteSplitLaneARosterSlots.begin(),
            config.ValidationRouteSplitLaneARosterSlots.end(), slot)
            != config.ValidationRouteSplitLaneARosterSlots.end();
        bool const laneB = std::find(config.ValidationRouteSplitLaneBRosterSlots.begin(),
            config.ValidationRouteSplitLaneBRosterSlots.end(), slot)
            != config.ValidationRouteSplitLaneBRosterSlots.end();
        float const projection = (memberDiagnostic.X - MidpointX) * AxisX
            + (memberDiagnostic.Y - MidpointY) * AxisY;
        memberDiagnostic.FrozenLaneSafe = laneA != laneB
            && (laneA ? -1.0f : 1.0f) * projection >= LaneSeparation * 0.25f;
        if (memberDiagnostic.IsTank)
        {
            uint32 const expectedSlot = laneA
                ? (config.ValidationRouteSplitLaneTankSlots.empty()
                    ? 0 : config.ValidationRouteSplitLaneTankSlots[0])
                : (config.ValidationRouteSplitLaneTankSlots.size() < 2
                    ? 0 : config.ValidationRouteSplitLaneTankSlots[1]);
            Player const* expectedTank = laneA ? LaneTank : OtherTank;
            memberDiagnostic.FrozenLaneSafe = memberDiagnostic.FrozenLaneSafe
                && slot == expectedSlot && member == expectedTank;
            memberDiagnostic.SourceDistance = expectedTank
                ? member->GetExactDist2d(laneA ? Sources[0] : Sources[1]) : 0.0f;
            memberDiagnostic.ExactRosterMemberReseparated = commonRosterSafe
                && memberDiagnostic.InWorld && memberDiagnostic.Alive
                && memberDiagnostic.SameMap && memberDiagnostic.ActiveLease
                && memberDiagnostic.FrozenLaneSafe
                && memberDiagnostic.SourceDistance
                    <= config.ValidationRouteSplitMinimumSeparationYards;
        }
        else
        {
            memberDiagnostic.GroupPositionSafe = GroupPositionSafe(member);
            memberDiagnostic.SourceDistance = std::min(
                member->GetExactDist2d(Sources[0]), member->GetExactDist2d(Sources[1]));
            memberDiagnostic.ExactRosterMemberReseparated = commonRosterSafe
                && memberDiagnostic.InWorld && memberDiagnostic.Alive
                && memberDiagnostic.SameMap && memberDiagnostic.ActiveLease
                && memberDiagnostic.GroupPositionSafe;
        }

        memberDiagnostic.AnchorValid = cohortState.ValidationRouteDrudgeAnchorValid;
        memberDiagnostic.AnchorPathProven = cohortState.ValidationRouteDrudgeAnchorPathProven;
        memberDiagnostic.RecoveryAnchorPathProven =
            cohortState.ValidationRouteDrudgeRecoveryAnchorPathProven;
        memberDiagnostic.RecoveryAnchorReached =
            cohortState.ValidationRouteDrudgeRecoveryAnchorReached;
        memberDiagnostic.AnchorCandidateIndex =
            cohortState.ValidationRouteDrudgeAnchorCandidateIndex;
        memberDiagnostic.AnchorX = cohortState.ValidationRouteDrudgeAnchorX;
        memberDiagnostic.AnchorY = cohortState.ValidationRouteDrudgeAnchorY;
        memberDiagnostic.AnchorZ = cohortState.ValidationRouteDrudgeAnchorZ;
        memberDiagnostic.RecoveryAnchorX = cohortState.ValidationRouteDrudgeRecoveryAnchorX;
        memberDiagnostic.RecoveryAnchorY = cohortState.ValidationRouteDrudgeRecoveryAnchorY;
        memberDiagnostic.RecoveryAnchorZ = cohortState.ValidationRouteDrudgeRecoveryAnchorZ;
        bool const activePathScopeMatches = cohortState.ActivePathAttemptId
                == Manager.Cohort().AttemptId
            && cohortState.ActivePathWipeGeneration
                == Manager.Cohort().Raid.WipeGeneration
            && cohortState.ActivePathRouteGeneration
                == Manager.Party().ValidationRouteGeneration
            && cohortState.ActivePathRouteNodeId
                == config.ValidationRouteNodeId;
        memberDiagnostic.ActivePathValid = cohortState.ActivePathValid;
        memberDiagnostic.ActivePathScopeMatches = activePathScopeMatches;
        memberDiagnostic.ActivePathDestinationX = cohortState.ActivePathToX;
        memberDiagnostic.ActivePathDestinationY = cohortState.ActivePathToY;
        memberDiagnostic.ActivePathDestinationZ = cohortState.ActivePathToZ;
        float const arrivalTolerance = memberDiagnostic.IsTank
            ? config.ValidationRouteSplitTankArrivalToleranceYards
            : config.ValidationRouteSplitArrivalToleranceYards;
        memberDiagnostic.ActivePathArrivalObserved = cohortState.ActivePathValid
            && activePathScopeMatches
            && member->GetExactDist(cohortState.ActivePathToX,
                cohortState.ActivePathToY, cohortState.ActivePathToZ)
                <= arrivalTolerance;
        if (memberDiagnostic.IsTank)
        {
            MemberAnchor const* combat = DeclaredCombatTankAnchorFor(slot);
            bool const combatAnchorMatches = combat
                && SamePoint(cohortState.ValidationRouteDrudgeAnchorX,
                    cohortState.ValidationRouteDrudgeAnchorY,
                    cohortState.ValidationRouteDrudgeAnchorZ,
                    combat->X, combat->Y, combat->Z);
            memberDiagnostic.CombatAnchorPathProven =
                cohortState.ValidationRouteDrudgeAnchorValid
                && cohortState.ValidationRouteDrudgeAnchorPathProven
                && combatAnchorMatches;
            memberDiagnostic.CombatAnchorArrivalObserved = combatAnchorMatches
                && member->GetExactDist(combat->X, combat->Y, combat->Z)
                    <= config.ValidationRouteSplitTankArrivalToleranceYards;
        }
        tick.Members.push_back(memberDiagnostic);
    }
    BotRaidDrudgeSpacing::ObserveRecoveryTick(
        Charge->RecoveryTicks, scope, std::move(tick));
}

void DrudgeLaneContext::RecordNativeTransition(Creature* source,
    char const* result, uint32 actionValue)
{
    if (!source || !result || Sources.size() != 2
        || (std::strcmp(result, "drudge_lane_native_ownership") != 0
            && std::strcmp(result, "drudge_lane_native_taunt") != 0
            && std::strcmp(result, "drudge_lane_native_taunt_approach") != 0
            && std::strcmp(result, "drudge_lane_wait_lane_ownership") != 0))
        return;
    auto observation = std::find_if(
        Manager.Party().ValidationRouteDrudgeChargeObservations.begin(),
        Manager.Party().ValidationRouteDrudgeChargeObservations.end(),
        [this](ChargeObservation const& candidate)
        {
            return candidate.Landed && !candidate.ReseparationRecorded
                && candidate.AttemptId == Manager.Cohort().AttemptId
                && candidate.WipeGeneration == Manager.Cohort().Raid.WipeGeneration
                && candidate.RouteGeneration == Manager.Party().ValidationRouteGeneration;
        });
    if (observation == Manager.Party().ValidationRouteDrudgeChargeObservations.end())
        return;
    BotRaidDrudgeGeometry::Scope const scope{
        Manager.Cohort().AttemptId, Manager.Cohort().Raid.WipeGeneration,
        Manager.Party().ValidationRouteGeneration, Bot->GetMapId(),
        Bot->GetInstanceId(), Sources[0]->GetGUID().GetRawValue(),
        Sources[1]->GetGUID().GetRawValue() };
    NativeTransition transition;
    transition.Scope = scope;
    transition.ObservedAtMs = NowMs();
    transition.BotGuid = Bot->GetGUID().GetCounter();
    transition.SourceGuid = source->GetGUID().GetCounter();
    transition.CurrentVictimGuid = source->GetVictim()
        ? source->GetVictim()->GetGUID().GetCounter() : 0;
    transition.ActionValue = actionValue;
    if (source == LaneSource)
        transition.AssignedTankGuid = LaneTank
            ? LaneTank->GetGUID().GetCounter() : 0;
    else if (source == OtherSource)
        transition.AssignedTankGuid = OtherTank
            ? OtherTank->GetGUID().GetCounter() : 0;
    for (uint32 index = 0; index < Manager.Cohort().Config.ValidationRouteSplitSourceGuids.size()
        && index < Sources.size(); ++index)
        if (source == Sources[index])
        {
            transition.SourceSpawnId =
                Manager.Cohort().Config.ValidationRouteSplitSourceGuids[index];
            break;
        }
    for (auto previous = observation->NativeTransitions.rbegin();
        previous != observation->NativeTransitions.rend(); ++previous)
        if (previous->Scope == scope && previous->SourceGuid == transition.SourceGuid)
        {
            transition.PreviousVictimGuid = previous->CurrentVictimGuid;
            break;
        }
    transition.VictimChanged = transition.PreviousVictimGuid != 0
        && transition.PreviousVictimGuid != transition.CurrentVictimGuid;
    transition.NativeVictimOwned = transition.AssignedTankGuid != 0
        && transition.AssignedTankGuid == transition.CurrentVictimGuid;
    transition.TauntAttempted = std::strcmp(result,
        "drudge_lane_native_taunt") == 0
        || std::strcmp(result, "drudge_lane_native_taunt_approach") == 0;
    transition.TauntSubmitted = std::strcmp(result,
        "drudge_lane_native_taunt") == 0;
    // The caller's cast helper proves submission/acceptance only.  A native
    // victim observation is retained separately; do not label the cast landed.
    transition.TauntOutcomeObserved = false;
    transition.Result = result;
    BotRaidDrudgeSpacing::ObserveNativeTransition(
        observation->NativeTransitions, scope, std::move(transition));
}
}
