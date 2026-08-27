#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"

#include "Creature.h"
#include "Map.h"
#include "PathGenerator.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <functional>
#include <limits>
#include <set>
#include <string>
#include <utility>
#include <vector>

using BotWorldPopulationMgrNativeHelpers::Distance2d;
using BotWorldPopulationMgrNativeHelpers::UnitHealthPct;

namespace BotWorldPopulationMgrValidationRoute
{
DrudgeLaneContext::DrudgeLaneContext(DrudgeLaneRequest const& request)
    : Manager(*request.Manager), State(*request.State), Bot(request.Bot),
      Power(*request.Power), Stage(request.Stage), Activity(request.Activity),
      Situation(*request.Situation), Action(*request.Action), Target(*request.Target),
      RouteArrivalRadius(request.RouteArrivalRadius), Callbacks(request.Callbacks)
{
}

}

bool BotWorldPopulationMgr::TryValidationRouteDrudgeChargeLanes(
    WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power,
    BotProgressionStage stage, BotProgressionActivity activity,
    std::string& situation, std::string& action, Unit*& target,
    std::function<bool(Player*, Unit*, bool, bool)> const& tryRouteGroupHeal,
    std::function<bool(Creature const*)> const& isValidationCohortCombatLinked,
    std::function<void(Creature const*, bool)> const& enrollValidationRoutePackMember,
    std::function<bool()> const& recordDefeatedValidationRoutePackMembers,
    std::function<float()> const& canonicalRouteDistance,
    float routeArrivalRadius)
{
    BotWorldPopulationMgrValidationRoute::DrudgeLaneRequest request;
    request.Manager = this;
    request.State = &state;
    request.Bot = bot;
    request.Power = &power;
    request.Stage = stage;
    request.Activity = activity;
    request.Situation = &situation;
    request.Action = &action;
    request.Target = &target;
    request.RouteArrivalRadius = routeArrivalRadius;
    request.Callbacks.TryGroupHeal = tryRouteGroupHeal;
    request.Callbacks.IsCombatLinked = isValidationCohortCombatLinked;
    request.Callbacks.EnrollPackMember = enrollValidationRoutePackMember;
    request.Callbacks.RecordDefeatedPackMembers =
        recordDefeatedValidationRoutePackMembers;
    request.Callbacks.CanonicalRouteDistance = canonicalRouteDistance;
    return BotWorldPopulationMgrValidationRoute::TryValidationRouteDrudgeChargeLanes(request);
}

namespace BotWorldPopulationMgrValidationRoute
{

bool DrudgeLaneContext::ComputeExactCombatTankPathsProven() const
{
    auto const& config = Manager.Cohort().Config;
    if (!LaneTank || !OtherTank || Bot->GetInstanceId() == 0
        || config.ValidationRouteSplitLaneTankSlots.size() != 2)
        return false;
    std::array<std::pair<float, float>, 2> navigationPoints{};
    std::array<bool, 2> pointSeen{ false, false };
    for (Player const* tank : { LaneTank, OtherTank })
    {
        auto tankState = std::find_if(Manager.Party().Bots.begin(),
            Manager.Party().Bots.end(), [tank](WorldBotState const& candidate)
            {
                return candidate.Guid == tank->GetGUID();
            });
        auto tankRoster = Manager.Cohort().Raid.RosterByGuid.find(
            tank->GetGUID().GetCounter());
        if (tankState == Manager.Party().Bots.end()
            || tankRoster == Manager.Cohort().Raid.RosterByGuid.end())
            return false;
        uint32 const slot = tankRoster->second.SlotIndex + 1;
        bool const combatCandidate = RecoveryTankReturnBarrierOpen()
            && IsRecoveryFormationActive()
            && RecoveryAnchorReachedFor(slot)
            && tankState->ValidationRouteDrudgeAnchorCandidateIndex == 0;
        MemberAnchor const* anchor = combatCandidate
            ? DeclaredCombatTankAnchorFor(slot)
            : DeclaredNavigationTankAnchorFor(slot);
        if (!anchor || !tankState->ValidationRouteDrudgeAnchorValid
            || !tankState->ValidationRouteDrudgeAnchorPathProven
            || tankState->ValidationRouteDrudgeAnchorAttemptId != Manager.Cohort().AttemptId
            || tankState->ValidationRouteDrudgeAnchorWipeGeneration
                != Manager.Cohort().Raid.WipeGeneration
            || tankState->ValidationRouteDrudgeAnchorRouteGeneration
                != Manager.Party().ValidationRouteGeneration
            || tankState->ValidationRouteDrudgeAnchorMapId != Bot->GetMapId()
            || tankState->ValidationRouteDrudgeAnchorInstanceId != Bot->GetInstanceId()
            || tankState->ValidationRouteDrudgeAnchorSource0Identity
                != Sources[0]->GetGUID().GetRawValue()
            || tankState->ValidationRouteDrudgeAnchorSource1Identity
                != Sources[1]->GetGUID().GetRawValue()
            || tankState->ValidationRouteDrudgeAnchorCandidateIndex > 1
            || Distance2d(tankState->ValidationRouteDrudgeAnchorX,
                tankState->ValidationRouteDrudgeAnchorY, anchor->X, anchor->Y) > 0.01f
            || std::fabs(tankState->ValidationRouteDrudgeAnchorZ - anchor->Z) > 0.01f)
            return false;
        uint32 const sourceIndex = slot == config.ValidationRouteSplitLaneTankSlots[0] ? 0 : 1;
        Position const& home = sourceIndex == 0
            ? Sources[0]->GetHomePosition() : Sources[1]->GetHomePosition();
        if (Distance2d(anchor->X, anchor->Y,
                home.GetPositionX(), home.GetPositionY())
            > config.ValidationRouteSplitMinimumSeparationYards)
            return false;
        navigationPoints[sourceIndex] = { anchor->X, anchor->Y };
        pointSeen[sourceIndex] = true;
    }
    if (!pointSeen[0] || !pointSeen[1])
        return false;
    float const tankTolerance = config.ValidationRouteSplitTankArrivalToleranceYards;
    if (Distance2d(navigationPoints[0].first, navigationPoints[0].second,
            navigationPoints[1].first, navigationPoints[1].second)
        < config.ValidationRouteSplitMinimumSeparationYards + 2.0f * tankTolerance)
        return false;
    std::array<std::pair<float, float>, 2> predictedSources{};
    for (uint32 sourceIndex = 0; sourceIndex < 2; ++sourceIndex)
    {
        Position const& home = sourceIndex == 0
            ? Sources[0]->GetHomePosition() : Sources[1]->GetHomePosition();
        float const dx = navigationPoints[sourceIndex].first - home.GetPositionX();
        float const dy = navigationPoints[sourceIndex].second - home.GetPositionY();
        float const distance = std::hypot(dx, dy);
        if (distance <= 0.001f)
            return false;
        float const travel = std::max(0.0f,
            distance - config.ValidationRouteSplitNativeMeleeStopYards);
        predictedSources[sourceIndex] = { home.GetPositionX() + dx * travel / distance,
            home.GetPositionY() + dy * travel / distance };
        float const projection = (predictedSources[sourceIndex].first - MidpointX) * AxisX
            + (predictedSources[sourceIndex].second - MidpointY) * AxisY;
        if ((sourceIndex == 0 ? -1.0f : 1.0f) * projection
            < HomeLaneProjectionMinimum + tankTolerance)
            return false;
    }
    if (Distance2d(predictedSources[0].first, predictedSources[0].second,
            predictedSources[1].first, predictedSources[1].second)
        < LaneSeparation + 2.0f * tankTolerance)
        return false;
    for (MemberAnchor const& anchor : config.ValidationRouteSplitMemberAnchors)
    {
        if (std::find(config.ValidationRouteSplitLaneTankSlots.begin(),
                config.ValidationRouteSplitLaneTankSlots.end(), anchor.RosterSlot)
            != config.ValidationRouteSplitLaneTankSlots.end())
            continue;
        if (Distance2d(anchor.X, anchor.Y, predictedSources[0].first,
                predictedSources[0].second)
                < config.ValidationRouteMinimumDistanceYards + tankTolerance
            || Distance2d(anchor.X, anchor.Y, predictedSources[1].first,
                predictedSources[1].second)
                < config.ValidationRouteMinimumDistanceYards + tankTolerance)
            return false;
    }
    return true;
}

bool DrudgeLaneContext::ComputeExactRecoveryTankPathsProven() const
{
    auto const& config = Manager.Cohort().Config;
    if (!LaneTank || !OtherTank || Bot->GetInstanceId() == 0
        || config.ValidationRouteSplitLaneTankSlots.size() != 2)
        return false;
    std::array<std::pair<float, float>, 2> recoveryPoints{};
    std::array<bool, 2> pointSeen{ false, false };
    for (Player const* tank : { LaneTank, OtherTank })
    {
        auto tankState = std::find_if(Manager.Party().Bots.begin(),
            Manager.Party().Bots.end(), [tank](WorldBotState const& candidate)
            {
                return candidate.Guid == tank->GetGUID();
            });
        auto tankRoster = Manager.Cohort().Raid.RosterByGuid.find(
            tank->GetGUID().GetCounter());
        if (tankState == Manager.Party().Bots.end()
            || tankRoster == Manager.Cohort().Raid.RosterByGuid.end())
            return false;
        uint32 const slot = tankRoster->second.SlotIndex + 1;
        MemberAnchor const* anchor = DeclaredRecoveryTankAnchorFor(slot);
        if (!anchor || !tankState->ValidationRouteDrudgeAnchorValid
            || !tankState->ValidationRouteDrudgeAnchorPathProven
            || !tankState->ValidationRouteDrudgeRecoveryAnchorPathProven
            || tankState->ValidationRouteDrudgeAnchorAttemptId != Manager.Cohort().AttemptId
            || tankState->ValidationRouteDrudgeAnchorWipeGeneration
                != Manager.Cohort().Raid.WipeGeneration
            || tankState->ValidationRouteDrudgeAnchorRouteGeneration
                != Manager.Party().ValidationRouteGeneration
            || tankState->ValidationRouteDrudgeAnchorMapId != Bot->GetMapId()
            || tankState->ValidationRouteDrudgeAnchorInstanceId != Bot->GetInstanceId()
            || tankState->ValidationRouteDrudgeAnchorSource0Identity
                != Sources[0]->GetGUID().GetRawValue()
            || tankState->ValidationRouteDrudgeAnchorSource1Identity
                != Sources[1]->GetGUID().GetRawValue()
            || Distance2d(tankState->ValidationRouteDrudgeAnchorX,
                tankState->ValidationRouteDrudgeAnchorY,
                tankState->ValidationRouteDrudgeRecoveryAnchorX,
                tankState->ValidationRouteDrudgeRecoveryAnchorY) > 0.01f
            || std::fabs(tankState->ValidationRouteDrudgeAnchorZ
                - tankState->ValidationRouteDrudgeRecoveryAnchorZ) > 0.01f)
            return false;
        uint32 const sourceIndex = slot == config.ValidationRouteSplitLaneTankSlots[0] ? 0 : 1;
        float const projection =
            (tankState->ValidationRouteDrudgeRecoveryAnchorX - MidpointX) * AxisX
            + (tankState->ValidationRouteDrudgeRecoveryAnchorY - MidpointY) * AxisY;
        float const inset = config.ValidationRouteSplitNativeMeleeStopYards
            + config.ValidationRouteSplitTankArrivalToleranceYards;
        if ((sourceIndex == 0 ? -1.0f : 1.0f) * projection
            < HomeLaneProjectionMinimum + inset)
            return false;
        recoveryPoints[sourceIndex] = {
            tankState->ValidationRouteDrudgeRecoveryAnchorX,
            tankState->ValidationRouteDrudgeRecoveryAnchorY };
        pointSeen[sourceIndex] = true;
    }
    if (!pointSeen[0] || !pointSeen[1])
        return false;
    float const tankTolerance = config.ValidationRouteSplitTankArrivalToleranceYards;
    float const meleeStop = config.ValidationRouteSplitNativeMeleeStopYards;
    if (Distance2d(recoveryPoints[0].first, recoveryPoints[0].second,
            recoveryPoints[1].first, recoveryPoints[1].second)
        < LaneSeparation + 2.0f * (meleeStop + tankTolerance))
        return false;
    float const memberClearance = config.ValidationRouteMinimumDistanceYards + meleeStop + config.ValidationRouteSplitArrivalToleranceYards + tankTolerance;
    for (MemberAnchor const& anchor : config.ValidationRouteSplitRecoveryMemberAnchors)
    {
        if (std::find(config.ValidationRouteSplitLaneTankSlots.begin(),
                config.ValidationRouteSplitLaneTankSlots.end(), anchor.RosterSlot)
            != config.ValidationRouteSplitLaneTankSlots.end())
            continue;
        if (Distance2d(anchor.X, anchor.Y, recoveryPoints[0].first,
                recoveryPoints[0].second) < memberClearance
            || Distance2d(anchor.X, anchor.Y, recoveryPoints[1].first,
                recoveryPoints[1].second) < memberClearance)
            return false;
    }
    return true;
}

bool DrudgeLaneContext::ComputeExactRecoveryTankAnchorsReached() const
{
    auto const& config = Manager.Cohort().Config;
    if (!LaneTank || !OtherTank || Bot->GetInstanceId() == 0
        || config.ValidationRouteSplitLaneTankSlots.size() != 2)
        return false;
    for (Player const* tank : { LaneTank, OtherTank })
    {
        auto tankState = std::find_if(Manager.Party().Bots.begin(),
            Manager.Party().Bots.end(), [tank](WorldBotState const& candidate)
            {
                return candidate.Guid == tank->GetGUID();
            });
        auto tankRoster = Manager.Cohort().Raid.RosterByGuid.find(
            tank->GetGUID().GetCounter());
        if (tankState == Manager.Party().Bots.end()
            || tankRoster == Manager.Cohort().Raid.RosterByGuid.end())
            return false;
        MemberAnchor const* anchor = DeclaredRecoveryTankAnchorFor(
            tankRoster->second.SlotIndex + 1);
        if (!anchor || !tankState->ValidationRouteDrudgeRecoveryAnchorPathProven
            || !tankState->ValidationRouteDrudgeRecoveryAnchorReached
            || tankState->ValidationRouteDrudgeAnchorAttemptId
                != Manager.Cohort().AttemptId
            || tankState->ValidationRouteDrudgeAnchorWipeGeneration
                != Manager.Cohort().Raid.WipeGeneration
            || tankState->ValidationRouteDrudgeAnchorRouteGeneration
                != Manager.Party().ValidationRouteGeneration
            || tankState->ValidationRouteDrudgeAnchorMapId != Bot->GetMapId()
            || tankState->ValidationRouteDrudgeAnchorInstanceId != Bot->GetInstanceId()
            || tankState->ValidationRouteDrudgeAnchorSource0Identity
                != Sources[0]->GetGUID().GetRawValue()
            || tankState->ValidationRouteDrudgeAnchorSource1Identity
                != Sources[1]->GetGUID().GetRawValue()
            || !tankState->ValidationRouteDrudgeAnchorValid
            || !tankState->ValidationRouteDrudgeAnchorPathProven
            || Distance2d(tankState->ValidationRouteDrudgeRecoveryAnchorX,
                tankState->ValidationRouteDrudgeRecoveryAnchorY,
                tankState->ValidationRouteDrudgeAnchorX,
                tankState->ValidationRouteDrudgeAnchorY) > 0.01f
            || std::fabs(tankState->ValidationRouteDrudgeRecoveryAnchorZ
                - tankState->ValidationRouteDrudgeAnchorZ) > 0.01f)
            return false;
    }
    return true;
}

bool DrudgeLaneContext::ComputeExactCombatTankAnchorsReached() const
{
    auto const& config = Manager.Cohort().Config;
    if (!LaneTank || !OtherTank || Bot->GetInstanceId() == 0
        || config.ValidationRouteSplitLaneTankSlots.size() != 2)
        return false;
    for (Player const* tank : { LaneTank, OtherTank })
    {
        auto tankState = std::find_if(Manager.Party().Bots.begin(),
            Manager.Party().Bots.end(), [tank](WorldBotState const& candidate)
            {
                return candidate.Guid == tank->GetGUID();
            });
        auto tankRoster = Manager.Cohort().Raid.RosterByGuid.find(
            tank->GetGUID().GetCounter());
        if (tankState == Manager.Party().Bots.end()
            || tankRoster == Manager.Cohort().Raid.RosterByGuid.end())
            return false;
        uint32 const slot = tankRoster->second.SlotIndex + 1;
        bool const combatCandidate = RecoveryTankReturnBarrierOpen()
            && IsRecoveryFormationActive()
            && RecoveryAnchorReachedFor(slot)
            && tankState->ValidationRouteDrudgeAnchorCandidateIndex == 0;
        MemberAnchor const* anchor = combatCandidate
            ? DeclaredCombatTankAnchorFor(slot)
            : DeclaredNavigationTankAnchorFor(slot);
        if (!anchor || !tankState->ValidationRouteDrudgeAnchorValid
            || !tankState->ValidationRouteDrudgeAnchorPathProven
            || tankState->ValidationRouteDrudgeAnchorAttemptId
                != Manager.Cohort().AttemptId
            || tankState->ValidationRouteDrudgeAnchorWipeGeneration
                != Manager.Cohort().Raid.WipeGeneration
            || tankState->ValidationRouteDrudgeAnchorRouteGeneration
                != Manager.Party().ValidationRouteGeneration
            || tankState->ValidationRouteDrudgeAnchorMapId != Bot->GetMapId()
            || tankState->ValidationRouteDrudgeAnchorInstanceId != Bot->GetInstanceId()
            || tankState->ValidationRouteDrudgeAnchorSource0Identity
                != Sources[0]->GetGUID().GetRawValue()
            || tankState->ValidationRouteDrudgeAnchorSource1Identity
                != Sources[1]->GetGUID().GetRawValue()
            || tankState->ValidationRouteDrudgeAnchorCandidateIndex > 1
            || Distance2d(tankState->ValidationRouteDrudgeAnchorX,
                tankState->ValidationRouteDrudgeAnchorY, anchor->X, anchor->Y)
                > 0.01f
            || std::fabs(tankState->ValidationRouteDrudgeAnchorZ - anchor->Z) > 0.01f
            || tank->GetExactDist(anchor->X, anchor->Y, anchor->Z)
                > config.ValidationRouteSplitTankArrivalToleranceYards)
            return false;
    }
    return true;
}

bool DrudgeLaneContext::ComputeExactLiveRecoveryTankPathsPreflighted() const
{
    auto const& config = Manager.Cohort().Config;
    if (!LaneTank || !OtherTank || Bot->GetInstanceId() == 0)
        return false;
    for (Player const* tank : { LaneTank, OtherTank })
    {
        auto tankState = std::find_if(Manager.Party().Bots.begin(),
            Manager.Party().Bots.end(), [tank](WorldBotState const& candidate)
            {
                return candidate.Guid == tank->GetGUID();
            });
        auto roster = Manager.Cohort().Raid.RosterByGuid.find(
            tank->GetGUID().GetCounter());
        if (tankState == Manager.Party().Bots.end()
            || roster == Manager.Cohort().Raid.RosterByGuid.end())
            return false;
        MemberAnchor const* anchor = DeclaredRecoveryTankAnchorFor(
            roster->second.SlotIndex + 1);
        if (!anchor || !tankState->ValidationRouteDrudgeRecoveryAnchorPathProven
            || tankState->ValidationRouteDrudgeAnchorAttemptId != Manager.Cohort().AttemptId
            || tankState->ValidationRouteDrudgeAnchorWipeGeneration
                != Manager.Cohort().Raid.WipeGeneration
            || tankState->ValidationRouteDrudgeAnchorRouteGeneration
                != Manager.Party().ValidationRouteGeneration
            || tankState->ValidationRouteDrudgeAnchorMapId != Bot->GetMapId()
            || tankState->ValidationRouteDrudgeAnchorInstanceId != Bot->GetInstanceId()
            || tankState->ValidationRouteDrudgeAnchorSource0Identity
                != Sources[0]->GetGUID().GetRawValue()
            || tankState->ValidationRouteDrudgeAnchorSource1Identity
                != Sources[1]->GetGUID().GetRawValue()
            || Distance2d(tankState->ValidationRouteDrudgeRecoveryAnchorX,
                tankState->ValidationRouteDrudgeRecoveryAnchorY, anchor->X, anchor->Y) > 0.01f
            || std::fabs(tankState->ValidationRouteDrudgeRecoveryAnchorZ - anchor->Z) > 0.01f)
            return false;
    }
    return true;
}

void DrudgeLaneContext::RecordReseparationEvidence(ChargeObservation& observation)
    {
        auto const& config = Manager.Cohort().Config;
        observation.ReseparatedRosterGuids.clear();
        for (WorldBotState const& cohortState : Manager.Party().Bots)
            if (!cohortState.Guid.IsEmpty())
                observation.ReseparatedRosterGuids.insert(cohortState.Guid.GetCounter());
        Manager.Party().ValidationRouteDrudgeReseparatedRosterGuids =
            observation.ReseparatedRosterGuids;
        observation.ReseparationRecorded = true;
        observation.EntrancePullEstablished = IsEntrancePullEstablished();
        float const groupOffset = config.ValidationRouteMinimumDistanceYards
            + config.ValidationRouteSplitNavigationMarginYards;
        observation.Home0X = Sources[0]->GetHomePosition().GetPositionX();
        observation.Home0Y = Sources[0]->GetHomePosition().GetPositionY();
        observation.Home1X = Sources[1]->GetHomePosition().GetPositionX();
        observation.Home1Y = Sources[1]->GetHomePosition().GetPositionY();
        observation.MidpointX = MidpointX;
        observation.MidpointY = MidpointY;
        observation.AxisX = AxisX;
        observation.AxisY = AxisY;
        observation.LaneSeparation = LaneSeparation;
        observation.MinimumDistance = config.ValidationRouteMinimumDistanceYards;
        observation.NavigationMargin = config.ValidationRouteSplitNavigationMarginYards;
        float const tankAnchorX = MidpointX - AxisX * LaneSeparation * 0.5f;
        float const tankAnchorY = MidpointY - AxisY * LaneSeparation * 0.5f;
        observation.GroupAnchorBaseX = tankAnchorX - AxisX * groupOffset;
        observation.GroupAnchorBaseY = tankAnchorY - AxisY * groupOffset;
        observation.Source0X = Sources[0]->GetPositionX();
        observation.Source0Y = Sources[0]->GetPositionY();
        observation.Source0LaneSideValid =
            SourceOnFrozenLane(Sources[0], 0, &observation.Source0Projection);
        observation.Source0HealthPct = UnitHealthPct(Sources[0]);
        observation.Source1X = Sources[1]->GetPositionX();
        observation.Source1Y = Sources[1]->GetPositionY();
        observation.Source1LaneSideValid =
            SourceOnFrozenLane(Sources[1], 1, &observation.Source1Projection);
        observation.Source1HealthPct = UnitHealthPct(Sources[1]);
        observation.Source0VictimGuid = Sources[0]->GetVictim()
            ? Sources[0]->GetVictim()->GetGUID().GetCounter() : 0;
        observation.Source1VictimGuid = Sources[1]->GetVictim()
            ? Sources[1]->GetVictim()->GetGUID().GetCounter() : 0;
        observation.Source0Alive = Sources[0]->IsAlive();
        observation.Source1Alive = Sources[1]->IsAlive();
        auto saveTank = [](Player* tank, Creature* source, uint32 slot,
            float& x, float& y, uint32& guid, uint32& savedSlot,
            float& projection, float& distance, float axisX, float axisY,
            float midpointX, float midpointY)
        {
            if (!tank)
                return;
            x = tank->GetPositionX();
            y = tank->GetPositionY();
            guid = tank->GetGUID().GetCounter();
            savedSlot = slot;
            projection = (x - midpointX) * axisX + (y - midpointY) * axisY;
            distance = tank->GetExactDist2d(source);
        };
        saveTank(LaneIndex == 0 ? LaneTank : OtherTank, Sources[0],
            config.ValidationRouteSplitLaneTankSlots[0], observation.Tank0X,
            observation.Tank0Y, observation.Tank0Guid, observation.Tank0Slot,
            observation.Tank0Projection, observation.Tank0SourceDistance,
            AxisX, AxisY, MidpointX, MidpointY);
        saveTank(LaneIndex == 0 ? OtherTank : LaneTank, Sources[1],
            config.ValidationRouteSplitLaneTankSlots[1], observation.Tank1X,
            observation.Tank1Y, observation.Tank1Guid, observation.Tank1Slot,
            observation.Tank1Projection, observation.Tank1SourceDistance,
            AxisX, AxisY, MidpointX, MidpointY);
        observation.SourceSeparation = Sources[0]->GetExactDist2d(Sources[1]);
        observation.MinimumSourceSeparation =
            config.ValidationRouteSplitMinimumSeparationYards;
        saveTank(LaneTank, LaneSource, LaneTankSlot, observation.LaneTankX,
            observation.LaneTankY, observation.LaneTankGuid, observation.LaneTankSlot,
            observation.LaneTankProjection, observation.LaneTankSourceDistance,
            AxisX, AxisY, MidpointX, MidpointY);
        saveTank(OtherTank, OtherSource, OtherTankSlot, observation.OtherTankX,
            observation.OtherTankY, observation.OtherTankGuid, observation.OtherTankSlot,
            observation.OtherTankProjection, observation.OtherTankSourceDistance,
            AxisX, AxisY, MidpointX, MidpointY);
        observation.MinimumMemberSpacing = std::max(3.0f,
            config.ValidationRouteSplitNavigationMarginYards
                + config.ValidationRouteSplitArrivalToleranceYards * 0.5f);
        observation.ArrivalTolerance = config.ValidationRouteSplitArrivalToleranceYards;
        observation.TankArrivalTolerance =
            config.ValidationRouteSplitTankArrivalToleranceYards;
        observation.MemberGeometry.clear();
        for (WorldBotState const& cohortState : Manager.Party().Bots)
        {
            Player* member = Manager.GetLoadedBot(cohortState);
            if (!member)
                continue;
            auto roster = Manager.Cohort().Raid.RosterByGuid.find(
                member->GetGUID().GetCounter());
            if (roster == Manager.Cohort().Raid.RosterByGuid.end())
                continue;
            BotWorldPopulationMgrRouteState::ValidationRouteDrudgeMemberGeometry geometry;
            geometry.Guid = member->GetGUID().GetCounter();
            geometry.RosterSlot = roster->second.SlotIndex + 1;
            geometry.X = member->GetPositionX();
            geometry.Y = member->GetPositionY();
            geometry.Projection = (geometry.X - MidpointX) * AxisX
                + (geometry.Y - MidpointY) * AxisY;
            bool const memberLaneA = std::find(
                config.ValidationRouteSplitLaneARosterSlots.begin(),
                config.ValidationRouteSplitLaneARosterSlots.end(), geometry.RosterSlot)
                != config.ValidationRouteSplitLaneARosterSlots.end();
            geometry.LaneSideValid = (memberLaneA ? -1.0f : 1.0f)
                * geometry.Projection >= BotRaidDrudgeGeometry::ArrivalAdjustedLaneProjectionMinimum(
                    HomeLaneProjectionMinimum, config.ValidationRouteSplitArrivalToleranceYards,
                    IsRecoveryFormationActive(), roster->second.Role == "tank",
                    IsEntrancePullActive());
            auto candidates = AnchorCandidatesFor(geometry.RosterSlot);
            if (!candidates.empty())
            {
                geometry.GroupAnchorBaseX = candidates[0].first;
                geometry.GroupAnchorBaseY = candidates[0].second;
            }
            auto memberState = std::find_if(Manager.Party().Bots.begin(),
                Manager.Party().Bots.end(), [member](WorldBotState const& candidate)
                {
                    return candidate.Guid == member->GetGUID();
                });
            if (memberState != Manager.Party().Bots.end()
                && memberState->ValidationRouteDrudgeAnchorValid
                && memberState->ValidationRouteDrudgeAnchorAttemptId
                    == Manager.Cohort().AttemptId
                && memberState->ValidationRouteDrudgeAnchorWipeGeneration
                    == Manager.Cohort().Raid.WipeGeneration
                && memberState->ValidationRouteDrudgeAnchorRouteGeneration
                    == Manager.Party().ValidationRouteGeneration
                && memberState->ValidationRouteDrudgeAnchorCandidateIndex < candidates.size()
                && Distance2d(memberState->ValidationRouteDrudgeAnchorX,
                    memberState->ValidationRouteDrudgeAnchorY,
                    candidates[memberState->ValidationRouteDrudgeAnchorCandidateIndex].first,
                    candidates[memberState->ValidationRouteDrudgeAnchorCandidateIndex].second)
                    <= 0.01f)
            {
                geometry.AnchorCandidateIndex =
                    memberState->ValidationRouteDrudgeAnchorCandidateIndex;
                geometry.AnchorX = memberState->ValidationRouteDrudgeAnchorX;
                geometry.AnchorY = memberState->ValidationRouteDrudgeAnchorY;
                geometry.AnchorDistance = Distance2d(geometry.X, geometry.Y,
                    geometry.AnchorX, geometry.AnchorY);
                geometry.AnchorSelected = geometry.AnchorDistance <= observation.ArrivalTolerance;
                geometry.AnchorPathValid = geometry.AnchorSelected;
            }
            float nearestSameLane = std::numeric_limits<float>::max();
            for (WorldBotState const& otherState : Manager.Party().Bots)
            {
                Player* other = Manager.GetLoadedBot(otherState);
                if (!other || other == member)
                    continue;
                auto otherRoster = Manager.Cohort().Raid.RosterByGuid.find(
                    other->GetGUID().GetCounter());
                if (otherRoster == Manager.Cohort().Raid.RosterByGuid.end()
                    || otherRoster->second.Role == "tank")
                    continue;
                bool const otherLaneA = std::find(
                    config.ValidationRouteSplitLaneARosterSlots.begin(),
                    config.ValidationRouteSplitLaneARosterSlots.end(),
                    otherRoster->second.SlotIndex + 1)
                    != config.ValidationRouteSplitLaneARosterSlots.end();
                if (otherLaneA == memberLaneA)
                    nearestSameLane = std::min(nearestSameLane,
                        member->GetExactDist2d(other));
            }
            geometry.NearestSameLaneDistance = nearestSameLane
                == std::numeric_limits<float>::max() ? 0.0f : nearestSameLane;
            geometry.SameLaneSpacingValid = nearestSameLane
                == std::numeric_limits<float>::max()
                || nearestSameLane >= observation.MinimumMemberSpacing;
            observation.MemberGeometry.push_back(geometry);
        }
        for (WorldBotState& cohortState : Manager.Party().Bots)
            cohortState.LastValidationRouteDrudgeChargeGenerationHandled = observation.Sequence;
    }

bool TryValidationRouteDrudgeChargeLanes(DrudgeLaneRequest const& request)
{
    if (!request.Manager || !request.State || !request.Bot || !request.Power
        || !request.Situation || !request.Action || !request.Target)
        return false;
    DrudgeLaneContext context(request);
    return context.Run();
}

bool DrudgeLaneContext::Run()
{
    PhaseResult result = BuildContract();
    if (result == PhaseResult::Abort)
        return false;
    if (result == PhaseResult::Handled)
        return true;

    result = ResolveSources();
    if (result == PhaseResult::Abort)
        return false;
    if (result == PhaseResult::Handled)
        return true;

    // Once both tanks own their entrance Drudges, use ordinary native class
    // actions with only lane targeting and paired-health synchronization.
    if (IsEntrancePullEstablished())
        return RunEntranceCombat() == PhaseResult::Handled;

    result = BuildAnchorPolicies();
    if (result == PhaseResult::Abort)
        return false;
    if (result == PhaseResult::Handled)
        return true;

    result = RunEntrancePullActions();
    if (result == PhaseResult::Abort)
        return false;
    if (result == PhaseResult::Handled)
        return true;

    result = RunFormationActions();
    if (result == PhaseResult::Abort)
        return false;
    if (result == PhaseResult::Handled)
        return true;
    result = RunThreatAndEvidenceActions();
    return result != PhaseResult::Abort;
}

DrudgeLaneContext::PhaseResult DrudgeLaneContext::BuildContract()
{
    if (Manager.Cohort().Config.ValidationRouteMechanicProfile
        != "trash_two_tank_charge_lanes")
        return PhaseResult::Abort;

    ExactRosterSlots = { 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 };
    std::vector<uint32> laneSlots =
        Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots;
    laneSlots.insert(laneSlots.end(),
        Manager.Cohort().Config.ValidationRouteSplitLaneBRosterSlots.begin(),
        Manager.Cohort().Config.ValidationRouteSplitLaneBRosterSlots.end());
    std::sort(laneSlots.begin(), laneSlots.end());

    auto rosterSlotHasExactRole = [this](uint32 oneBasedSlot,
        char const* role) -> bool
    {
        for (auto const& [guid, roster] : Manager.Cohort().Raid.RosterByGuid)
        {
            (void)guid;
            if (roster.SlotIndex + 1 == oneBasedSlot)
                return roster.Active && roster.LeaseOwned && roster.Role == role;
        }
        return false;
    };
    std::vector<uint32> anchorSlots;
    for (MemberAnchor const& anchor :
        Manager.Cohort().Config.ValidationRouteSplitMemberAnchors)
        anchorSlots.push_back(anchor.RosterSlot);
    std::sort(anchorSlots.begin(), anchorSlots.end());
    std::vector<uint32> recoveryMemberAnchorSlots;
    for (MemberAnchor const& anchor : Manager.Cohort().Config.ValidationRouteSplitRecoveryMemberAnchors)
        recoveryMemberAnchorSlots.push_back(anchor.RosterSlot);
    std::sort(recoveryMemberAnchorSlots.begin(), recoveryMemberAnchorSlots.end());
    std::vector<uint32> combatTankAnchorSlots;
    for (MemberAnchor const& anchor :
        Manager.Cohort().Config.ValidationRouteSplitTankCombatAnchors)
        combatTankAnchorSlots.push_back(anchor.RosterSlot);
    std::sort(combatTankAnchorSlots.begin(), combatTankAnchorSlots.end());
    std::vector<uint32> navigationTankAnchorSlots;
    for (MemberAnchor const& anchor :
        Manager.Cohort().Config.ValidationRouteSplitTankNavigationAnchors)
        navigationTankAnchorSlots.push_back(anchor.RosterSlot);
    std::sort(navigationTankAnchorSlots.begin(), navigationTankAnchorSlots.end());
    std::vector<uint32> recoveryTankAnchorSlots;
    for (MemberAnchor const& anchor :
        Manager.Cohort().Config.ValidationRouteSplitTankRecoveryAnchors)
        recoveryTankAnchorSlots.push_back(anchor.RosterSlot);
    std::sort(recoveryTankAnchorSlots.begin(), recoveryTankAnchorSlots.end());
    HealerSlots = Manager.Cohort().Config.ValidationRouteSplitHealerRosterSlots;
    std::sort(HealerSlots.begin(), HealerSlots.end());
    bool const healerSlotsResolved = HealerSlots.size() == 3
        && std::adjacent_find(HealerSlots.begin(), HealerSlots.end())
            == HealerSlots.end()
        && std::all_of(HealerSlots.begin(), HealerSlots.end(),
            [&rosterSlotHasExactRole](uint32 oneBasedSlot)
            {
                return rosterSlotHasExactRole(oneBasedSlot, "healer");
            });
    bool const seedSlotsResolved =
        Manager.Cohort().Config.ValidationRouteSplitSeedRosterSlots.size() == 2
        && Manager.Cohort().Config.ValidationRouteSplitSeedRosterSlots[0]
            != Manager.Cohort().Config.ValidationRouteSplitSeedRosterSlots[1]
        && std::find(Manager.Cohort().Config.ValidationRouteSplitLaneBRosterSlots.begin(),
            Manager.Cohort().Config.ValidationRouteSplitLaneBRosterSlots.end(),
            Manager.Cohort().Config.ValidationRouteSplitSeedRosterSlots[0])
            != Manager.Cohort().Config.ValidationRouteSplitLaneBRosterSlots.end()
        && std::find(Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
            Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(),
            Manager.Cohort().Config.ValidationRouteSplitSeedRosterSlots[1])
            != Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end()
        && std::find(Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots.begin(),
            Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots.end(),
            Manager.Cohort().Config.ValidationRouteSplitSeedRosterSlots[0])
            == Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots.end()
        && std::find(Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots.begin(),
            Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots.end(),
            Manager.Cohort().Config.ValidationRouteSplitSeedRosterSlots[1])
            == Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots.end()
        && rosterSlotHasExactRole(
            Manager.Cohort().Config.ValidationRouteSplitSeedRosterSlots[0], "dps")
        && rosterSlotHasExactRole(
            Manager.Cohort().Config.ValidationRouteSplitSeedRosterSlots[1], "dps");

    ContractResolved = Manager.Cohort().Config.ValidationRouteSplitSourceGuids.size() == 2
        && Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.size() == 5
        && Manager.Cohort().Config.ValidationRouteSplitLaneBRosterSlots.size() == 5
        && Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots.size() == 2
        && laneSlots == ExactRosterSlots && anchorSlots == ExactRosterSlots
        && recoveryMemberAnchorSlots == ExactRosterSlots
        && combatTankAnchorSlots == std::vector<uint32>({ 1, 2 })
        && navigationTankAnchorSlots == std::vector<uint32>({ 1, 2 })
        && recoveryTankAnchorSlots == std::vector<uint32>({ 1, 2 })
        && Manager.Cohort().Config.ValidationRouteBossRecovery
            == ValidationRouteBossRecoveryPolicy::NativeFullWipeOnly
        && Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots[0]
            == Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots[0]
        && Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots[1]
            == Manager.Cohort().Config.ValidationRouteSplitLaneBRosterSlots[0]
        && Manager.Cohort().Config.ValidationRouteSplitMinimumSeparationYards > 0.0f
        && Manager.Cohort().Config.ValidationRouteSplitNavigationMarginYards >= 0.0f
        && Manager.Cohort().Config.ValidationRouteSplitArrivalToleranceYards > 0.0f
        && Manager.Cohort().Config.ValidationRouteSplitTankArrivalToleranceYards > 0.0f
        && Manager.Cohort().Config.ValidationRouteSplitTankArrivalToleranceYards
            <= Manager.Cohort().Config.ValidationRouteSplitArrivalToleranceYards
        && Manager.Cohort().Config.ValidationRouteSplitNativeMeleeStopYards > 0.0f
        && healerSlotsResolved && seedSlotsResolved
        && Manager.Cohort().Config.ValidationRouteSplitSeedMaxRangeYards > 0.0f
        && Manager.Cohort().Config.ValidationRouteSplitTankThreatHeadroomMultiplier >= 1.3f
        && Manager.Cohort().Config.ValidationRouteMinimumDistanceYards > 0.0f
        && Manager.Cohort().Config.ValidationRouteThunderclapSpellId
        && Manager.Cohort().Config.ValidationRouteChargeSpellId
        && Manager.Cohort().Config.ValidationRouteChargeRangeYards > 0.0f
        && Manager.Cohort().Config.ValidationRouteChargeNativeIntervalMs
        && Manager.Cohort().Config.ValidationRouteVengefulRageSpellId;

    if (!ContractResolved || !Bot->GetMap() || !Manager.Cohort().Raid.RosterComplete
        || Manager.Cohort().Raid.RosterByGuid.size() != ExactRosterSlots.size())
    {
        HoldOffense();
        Record(nullptr, "drudge_lane_contract_unresolved");
        Target = nullptr;
        State.TargetGuid.Clear();
        return PhaseResult::Handled;
    }

    auto roster = Manager.Cohort().Raid.RosterByGuid.find(Bot->GetGUID().GetCounter());
    if (roster == Manager.Cohort().Raid.RosterByGuid.end() || !roster->second.Active
        || !roster->second.LeaseOwned || roster->second.SlotIndex >= ExactRosterSlots.size())
    {
        HoldOffense();
        Record(nullptr, "drudge_lane_roster_identity_missing");
        Target = nullptr;
        State.TargetGuid.Clear();
        return PhaseResult::Handled;
    }
    OneBasedSlot = roster->second.SlotIndex + 1;
    Role = roster->second.Role;
    std::vector<std::string> const exactSlotIds = {
        "raid_tank_1", "raid_tank_2", "raid_healer_1", "raid_healer_2",
        "raid_healer_3", "raid_dps_1", "raid_dps_2", "raid_dps_3",
        "raid_dps_4", "raid_dps_5"
    };
    if (roster->second.RosterSlotId != exactSlotIds[roster->second.SlotIndex])
    {
        HoldOffense();
        Record(nullptr, "drudge_lane_roster_slot_identity_mismatch");
        Target = nullptr;
        State.TargetGuid.Clear();
        return PhaseResult::Handled;
    }
    LaneA = std::find(Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
        Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(), OneBasedSlot)
        != Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
    LaneB = std::find(Manager.Cohort().Config.ValidationRouteSplitLaneBRosterSlots.begin(),
        Manager.Cohort().Config.ValidationRouteSplitLaneBRosterSlots.end(), OneBasedSlot)
        != Manager.Cohort().Config.ValidationRouteSplitLaneBRosterSlots.end();
    if (LaneA == LaneB)
    {
        HoldOffense();
        Record(nullptr, "drudge_lane_slot_not_exactly_once");
        Target = nullptr;
        State.TargetGuid.Clear();
        return PhaseResult::Handled;
    }
    LaneIndex = LaneA ? 0 : 1;
    AssignedTank = OneBasedSlot
        == Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots[LaneIndex];
    if (AssignedTank != (Role == "tank"))
    {
        HoldOffense();
        Record(nullptr, "drudge_lane_tank_role_mismatch");
        Target = nullptr;
        State.TargetGuid.Clear();
        return PhaseResult::Handled;
    }

    DeclaredAnchorFor = [this](uint32 slot) -> MemberAnchor const*
    {
        auto anchor = std::find_if(
            Manager.Cohort().Config.ValidationRouteSplitMemberAnchors.begin(),
            Manager.Cohort().Config.ValidationRouteSplitMemberAnchors.end(),
            [slot](MemberAnchor const& candidate)
            {
                return candidate.RosterSlot == slot;
            });
        return anchor == Manager.Cohort().Config.ValidationRouteSplitMemberAnchors.end()
            ? nullptr : &*anchor;
    };
    DeclaredNavigationTankAnchorFor = [this](uint32 slot) -> MemberAnchor const*
    {
        auto anchor = std::find_if(
            Manager.Cohort().Config.ValidationRouteSplitTankNavigationAnchors.begin(),
            Manager.Cohort().Config.ValidationRouteSplitTankNavigationAnchors.end(),
            [slot](MemberAnchor const& candidate)
            {
                return candidate.RosterSlot == slot;
            });
        return anchor == Manager.Cohort().Config.ValidationRouteSplitTankNavigationAnchors.end()
            ? nullptr : &*anchor;
    };
    DeclaredCombatTankAnchorFor = [this](uint32 slot) -> MemberAnchor const*
    {
        auto anchor = std::find_if(
            Manager.Cohort().Config.ValidationRouteSplitTankCombatAnchors.begin(),
            Manager.Cohort().Config.ValidationRouteSplitTankCombatAnchors.end(),
            [slot](MemberAnchor const& candidate)
            {
                return candidate.RosterSlot == slot;
            });
        return anchor == Manager.Cohort().Config.ValidationRouteSplitTankCombatAnchors.end()
            ? nullptr : &*anchor;
    };
    DeclaredRecoveryTankAnchorFor = [this](uint32 slot) -> MemberAnchor const*
    {
        auto anchor = std::find_if(
            Manager.Cohort().Config.ValidationRouteSplitTankRecoveryAnchors.begin(),
            Manager.Cohort().Config.ValidationRouteSplitTankRecoveryAnchors.end(),
            [slot](MemberAnchor const& candidate)
            {
                return candidate.RosterSlot == slot;
            });
        return anchor == Manager.Cohort().Config.ValidationRouteSplitTankRecoveryAnchors.end()
            ? nullptr : &*anchor;
    };
    DeclaredAnchorAvailable = [this](uint32 slot)
    {
        return DeclaredAnchorFor(slot) != nullptr;
    };
    DeclaredNavigationTankAnchorAvailable = [this](uint32 slot)
    {
        return DeclaredNavigationTankAnchorFor(slot) != nullptr;
    };
    DeclaredRecoveryTankAnchorAvailable = [this](uint32 slot)
    {
        return DeclaredRecoveryTankAnchorFor(slot) != nullptr;
    };
    MemberAnchor const* prepullAnchor = DeclaredAnchorFor(OneBasedSlot);
    if (!prepullAnchor || (AssignedTank
        && (!DeclaredNavigationTankAnchorFor(OneBasedSlot)
            || !DeclaredRecoveryTankAnchorFor(OneBasedSlot))))
    {
        HoldOffense();
        Record(nullptr, "drudge_lane_declared_anchor_missing");
        Target = nullptr;
        State.TargetGuid.Clear();
        return PhaseResult::Handled;
    }
    return PhaseResult::Continue;
}

DrudgeLaneContext::PhaseResult DrudgeLaneContext::ResolveSources()
{
    Sources.clear();
    for (uint32 spawnId : Manager.Cohort().Config.ValidationRouteSplitSourceGuids)
    {
        Creature* source = Bot->GetMap()->GetCreatureBySpawnId(spawnId);
        if (!source || source->GetEntry()
                != Manager.Cohort().Config.ValidationRouteMinimumDistanceSourceEntry
            || source->GetMap() != Bot->GetMap())
        {
            if (!Manager.Party().ValidationRoutePackObservedEngagement
                && Callbacks.CanonicalRouteDistance
                && Callbacks.CanonicalRouteDistance() > RouteArrivalRadius)
                return PhaseResult::Abort;
            HoldOffense();
            Record(source, "drudge_lane_exact_source_missing", 0.0f, spawnId);
            Target = nullptr;
            State.TargetGuid.Clear();
            return PhaseResult::Handled;
        }
        Sources.push_back(source);
    }
    if (Sources.size() != 2 || Sources[0] == Sources[1])
    {
        HoldOffense();
        Record(Sources.empty() ? nullptr : Sources[0], "drudge_lane_duplicate_source");
        Target = nullptr;
        State.TargetGuid.Clear();
        return PhaseResult::Handled;
    }

    for (Creature* source : Sources)
    {
        bool const nativeCombatObserved = source->IsAlive()
            && (source->IsInCombat() || source->GetVictim()
                || source->GetHealth() < source->GetMaxHealth()
                || (Callbacks.IsCombatLinked
                    && Callbacks.IsCombatLinked(source)));
        if (Callbacks.EnrollPackMember)
            Callbacks.EnrollPackMember(source, nativeCombatObserved);
    }
    if (!Sources[0]->IsAlive() && !Sources[1]->IsAlive())
    {
        if (Callbacks.RecordDefeatedPackMembers)
            Callbacks.RecordDefeatedPackMembers();
        return PhaseResult::Abort;
    }

    SourceCombatStarted = Sources[0]->IsInCombat() || Sources[1]->IsInCombat()
        || Sources[0]->GetVictim() || Sources[1]->GetVictim();
    Position const& homeA = Sources[0]->GetHomePosition();
    Position const& homeB = Sources[1]->GetHomePosition();
    AxisX = homeB.GetPositionX() - homeA.GetPositionX();
    AxisY = homeB.GetPositionY() - homeA.GetPositionY();
    float const axisLength = std::hypot(AxisX, AxisY);
    if (axisLength <= 0.001f)
    {
        HoldOffense();
        Record(nullptr, "drudge_lane_source_axis_unresolved");
        Target = nullptr;
        State.TargetGuid.Clear();
        return PhaseResult::Handled;
    }
    AxisX /= axisLength;
    AxisY /= axisLength;
    MidpointX = (homeA.GetPositionX() + homeB.GetPositionX()) * 0.5f;
    MidpointY = (homeA.GetPositionY() + homeB.GetPositionY()) * 0.5f;
    MidpointZ = (homeA.GetPositionZ() + homeB.GetPositionZ()) * 0.5f;
    LaneSeparation = Manager.Cohort().Config.ValidationRouteSplitMinimumSeparationYards
        + Manager.Cohort().Config.ValidationRouteSplitNavigationMarginYards;
    HomeLaneProjectionMinimum = axisLength * 0.25f;
    LaneSign = LaneIndex == 0 ? -1.0f : 1.0f;
    LaneSource = Sources[LaneIndex];
    OtherSource = Sources[1 - LaneIndex];
    LaneTankSlot = Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots[LaneIndex];
    OtherTankSlot = Manager.Cohort().Config.ValidationRouteSplitLaneTankSlots[1 - LaneIndex];
    for (WorldBotState const& cohortState : Manager.Party().Bots)
    {
        Player* member = Manager.GetLoadedBot(cohortState);
        if (!member || !member->IsInWorld() || member->GetMap() != Bot->GetMap())
            continue;
        auto memberRoster = Manager.Cohort().Raid.RosterByGuid.find(
            member->GetGUID().GetCounter());
        if (memberRoster == Manager.Cohort().Raid.RosterByGuid.end()
            || !memberRoster->second.Active || !memberRoster->second.LeaseOwned)
            continue;
        uint32 memberSlot = memberRoster->second.SlotIndex + 1;
        if (memberSlot == LaneTankSlot && memberRoster->second.Role == "tank")
            LaneTank = member;
        else if (memberSlot == OtherTankSlot && memberRoster->second.Role == "tank")
            OtherTank = member;
    }
    return PhaseResult::Continue;
}
}
