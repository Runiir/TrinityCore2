#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudgeRecovery.h"

#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"
#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"

#include "PathGenerator.h"
#include "Player.h"

#include <algorithm>
#include <cmath>
#include <vector>

using BotWorldPopulationMgrNativeHelpers::Distance2d;

namespace BotWorldPopulationMgrValidationRoute
{
bool DrudgeLaneContext::IsRecoveryCandidateSpacingSafe(
    float x, float y, bool tank) const
{
    if (tank)
        return true;
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
        }
        if (Distance2d(x, y, otherX, otherY)
            < std::max(3.0f,
                Manager.Cohort().Config.ValidationRouteSplitNavigationMarginYards
                    + Manager.Cohort().Config.ValidationRouteSplitArrivalToleranceYards
                        * 0.5f))
            return false;
    }
    return true;
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
}
