#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeRecovery.h"

#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"

#include "Creature.h"
#include "PathGenerator.h"
#include "Player.h"

#include <algorithm>
#include <cmath>
#include <vector>

using BotWorldPopulationMgrNativeHelpers::Distance2d;

namespace BotWorldPopulationMgrValidationRoute
{
bool DrudgeLaneContext::IsLandedRushPending() const
{
    if (Manager.Cohort().Config.ValidationRouteMechanicProfile
        != "trash_two_tank_charge_lanes")
        return false;
    auto observation = std::find_if(
        Manager.Party().ValidationRouteDrudgeChargeObservations.begin(),
        Manager.Party().ValidationRouteDrudgeChargeObservations.end(),
        [this](ChargeObservation const& candidate)
        {
            return !candidate.ReseparationRecorded
                && candidate.AttemptId == Manager.Cohort().AttemptId
                && candidate.WipeGeneration == Manager.Cohort().Raid.WipeGeneration
                && candidate.RouteGeneration
                    == Manager.Party().ValidationRouteGeneration;
        });
    return observation != Manager.Party().ValidationRouteDrudgeChargeObservations.end()
        && observation->Landed;
}

bool DrudgeLaneContext::IsDynamicGroupRecoveryActive() const
{
    auto const& party = Manager.Party();
    bool const exactPrepullStaged = party.ValidationRouteDrudgePrepullStaged
        && party.ValidationRouteDrudgePrepullAttemptId == Manager.Cohort().AttemptId
        && party.ValidationRouteDrudgePrepullWipeGeneration
            == Manager.Cohort().Raid.WipeGeneration
        && party.ValidationRouteDrudgePrepullRouteGeneration
            == party.ValidationRouteGeneration;
    return BotRaidDrudgeGeometry::DynamicGroupRecoveryActive(
        Manager.Cohort().Config.ValidationRouteMechanicProfile
            == "trash_two_tank_charge_lanes",
        exactPrepullStaged, IsLandedRushPending());
}

bool DrudgeLaneContext::RecoveryTankReturnBarrierOpen() const
{
    bool const allRecoveryAnchorsReached = ExactRecoveryTankAnchorsReached
        && ExactRecoveryTankAnchorsReached();
    if (!Charge)
        return BotRaidDrudgeGeometry::RecoveryTankReturnBarrierOpen(
            IsLandedRushPending(), allRecoveryAnchorsReached);
    return BotRaidDrudgeGeometry::AdvanceRecoveryTankReturnBarrier(
        Charge->RecoveryTankReturnBarrierOpened, IsLandedRushPending(),
        allRecoveryAnchorsReached);
}

bool DrudgeLaneContext::RecoveryTankAnchorPending(uint32 slot) const
{
    return IsLandedRushPending() && !RecoveryAnchorReachedFor(slot);
}

BotRaidDrudgeSpacing::PeerResult DrudgeLaneContext::EvaluateRecoveryCandidateSpacing(
    float x, float y, bool tank) const
{
    BotRaidDrudgeSpacing::PeerResult result;
    if (tank)
        return result;
    for (WorldBotState const& cohortState : Manager.Party().Bots)
    {
        Player* other = Manager.GetLoadedBot(cohortState);
        if (!other || other == Bot || !other->IsInWorld()
            || !other->IsAlive() || other->GetMap() != Bot->GetMap())
            continue;
        auto otherRoster = Manager.Cohort().Raid.RosterByGuid.find(
            other->GetGUID().GetCounter());
        if (otherRoster == Manager.Cohort().Raid.RosterByGuid.end()
            || otherRoster->second.Role == "tank")
            continue;
        bool const otherLaneA = std::find(
            Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.begin(),
            Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end(),
            otherRoster->second.SlotIndex + 1)
            != Manager.Cohort().Config.ValidationRouteSplitLaneARosterSlots.end();
        if (otherLaneA != LaneA)
            continue;
        float otherX = other->GetPositionX();
        float otherY = other->GetPositionY();
        char const* coordinateSource = "live";
        if (cohortState.ValidationRouteDrudgeAnchorValid
            && cohortState.ValidationRouteDrudgeAnchorAttemptId
                == Manager.Cohort().AttemptId
            && cohortState.ValidationRouteDrudgeAnchorWipeGeneration
                == Manager.Cohort().Raid.WipeGeneration
            && cohortState.ValidationRouteDrudgeAnchorRouteGeneration
                == Manager.Party().ValidationRouteGeneration)
        {
            otherX = cohortState.ValidationRouteDrudgeAnchorX;
            otherY = cohortState.ValidationRouteDrudgeAnchorY;
            coordinateSource = "cached";
        }
        float const distance = Distance2d(x, y, otherX, otherY);
        if (distance < std::max(3.0f,
                Manager.Cohort().Config.ValidationRouteSplitNavigationMarginYards
                    + Manager.Cohort().Config.ValidationRouteSplitArrivalToleranceYards
                        * 0.5f))
        {
            result.Safe = false;
            result.PeerGuid = other->GetGUID().GetCounter();
            result.PeerDistance = distance;
            result.PeerCoordinateSource = coordinateSource;
            return result;
        }
    }
    return result;
}

bool DrudgeLaneContext::IsRecoveryCandidateSpacingSafe(
    float x, float y, bool tank) const
{
    return EvaluateRecoveryCandidateSpacing(x, y, tank).Safe;
}

bool DrudgeLaneContext::ComputeStrictTankRecoveryPath(
    float x, float y, float z) const
{
    if (!AssignedTank || !OtherTank || !Bot->GetMap()
        || !StrictNativePath(x, y, z, true, nullptr))
        return false;
    PathGenerator path(Bot);
    if (!path.CalculatePath(x, y, z, false))
        return false;
    std::vector<BotRaidDrudgeGeometry::Point2d> points;
    points.push_back({ Bot->GetPositionX(), Bot->GetPositionY() });
    for (G3D::Vector3 const& point : path.GetPath())
        points.push_back({ point.x, point.y });
    points.push_back({ path.GetActualEndPosition().x,
        path.GetActualEndPosition().y });
    float const otherProjection =
        (OtherTank->GetPositionX() - MidpointX) * AxisX
        + (OtherTank->GetPositionY() - MidpointY) * AxisY;
    return BotRaidDrudgeGeometry::RecoveryPathPreservesTankSeparation(
        points, MidpointX, MidpointY,
        AxisX, AxisY, LaneSign,
        -LaneSign * otherProjection,
        Manager.Cohort().Config.ValidationRouteSplitMinimumSeparationYards);
}

bool DrudgeLaneContext::ComputeRecoveryAnchorReached(uint32 slot) const
{
    MemberAnchor const* recovery = DeclaredRecoveryTankAnchorFor(slot);
    if (!recovery)
        return false;
    for (auto const& [guid, roster] : Manager.Cohort().Raid.RosterByGuid)
        if (roster.Active && roster.LeaseOwned && roster.Role == "tank"
            && roster.SlotIndex + 1 == slot)
            for (WorldBotState const& memberState : Manager.Party().Bots)
                if (memberState.Guid.GetCounter() == guid)
                    return memberState.ValidationRouteDrudgeRecoveryAnchorPathProven
                        && memberState.ValidationRouteDrudgeRecoveryAnchorReached
                        && memberState.ValidationRouteDrudgeAnchorAttemptId
                            == Manager.Cohort().AttemptId
                        && memberState.ValidationRouteDrudgeAnchorWipeGeneration
                            == Manager.Cohort().Raid.WipeGeneration
                        && memberState.ValidationRouteDrudgeAnchorRouteGeneration
                            == Manager.Party().ValidationRouteGeneration
                        && memberState.ValidationRouteDrudgeAnchorMapId == Bot->GetMapId()
                        && memberState.ValidationRouteDrudgeAnchorInstanceId
                            == Bot->GetInstanceId()
                        && memberState.ValidationRouteDrudgeAnchorSource0Identity
                            == Sources[0]->GetGUID().GetRawValue()
                        && memberState.ValidationRouteDrudgeAnchorSource1Identity
                            == Sources[1]->GetGUID().GetRawValue()
                        && ((Distance2d(
                                memberState.ValidationRouteDrudgeRecoveryAnchorX,
                                memberState.ValidationRouteDrudgeRecoveryAnchorY,
                                recovery->X, recovery->Y) <= 0.01f
                            && std::fabs(memberState.ValidationRouteDrudgeRecoveryAnchorZ
                                - recovery->Z) <= 0.01f)
                            || (std::isfinite(
                                    memberState.ValidationRouteDrudgeRecoveryAnchorX)
                                && std::isfinite(
                                    memberState.ValidationRouteDrudgeRecoveryAnchorY)
                                && std::isfinite(
                                    memberState.ValidationRouteDrudgeRecoveryAnchorZ)));
    return false;
}
}
