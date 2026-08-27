#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativePathValidation.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeNativeAnchor.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeNativePathDecision.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeRecoveryCandidates.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"

#include "Creature.h"
#include "PathGenerator.h"
#include "Player.h"

#include <array>
#include <cmath>
#include <limits>

namespace BotWorldPopulationMgrValidationRoute
{
namespace
{
using BotRaidDrudgeRecoveryCandidates::Point2d;

bool PreservesUnionDistanceFloors(Player const* bot,
    std::array<Point2d, 4> const& anchors, PathGenerator const& path,
    float minimumDistance)
{
    if (!bot || path.GetPath().empty() || minimumDistance <= 0.0f)
        return false;
    Point2d const start{ bot->GetPositionX(), bot->GetPositionY() };
    std::array<float, 4> startDistances{};
    for (std::size_t index = 0; index < anchors.size(); ++index)
        startDistances[index] = std::sqrt(
            BotRaidDrudgeRecoveryCandidates::DistanceSquared(
                start, anchors[index]));

    auto pointSafe = [&](G3D::Vector3 const& point)
    {
        Point2d const pathPoint{ point.x, point.y };
        for (std::size_t index = 0; index < anchors.size(); ++index)
            if (!BotRaidDrudgeRecoveryCandidates::PathPointPreservesSourceDistance(
                    pathPoint, anchors[index], startDistances[index],
                    minimumDistance))
                return false;
        return true;
    };

    std::size_t firstPoint = 0;
    G3D::Vector3 const& first = path.GetPath().front();
    if (std::hypot(first.x - start.X, first.y - start.Y) <= 0.25f)
        firstPoint = 1;
    for (std::size_t index = firstPoint; index < path.GetPath().size(); ++index)
        if (!pointSafe(path.GetPath()[index]))
            return false;
    return pointSafe(path.GetActualEndPosition());
}
}

bool DrudgeLaneContext::SelectProgressiveDrudgeEscape(uint64 nowMs)
{
    if (!Bot || AssignedTank || Sources.size() != 2 || !Sources[0]
        || !Sources[1] || !IsDynamicGroupRecoveryActive()
        || !IsLandedRushPending()
        || SourceUnionSafe(Bot->GetPositionX(), Bot->GetPositionY()))
        return false;

    auto const& config = Manager.Cohort().Config;
    float const minimumDistance = config.ValidationRouteMinimumDistanceYards;
    float const maximumMiss = config.ValidationRouteSplitNavigationMarginYards;
    if (minimumDistance <= 0.0f
        || maximumMiss <= BotRaidDrudgeNativePath::ExactEndpointTolerance2dYards)
        return false;

    MemberAnchor const* declared = DeclaredAnchorFor(OneBasedSlot);
    std::vector<std::pair<float, float>> const candidates =
        AnchorCandidatesFor(OneBasedSlot);
    if (!declared || candidates.size() <= 1)
        return false;

    Point2d const start{ Bot->GetPositionX(), Bot->GetPositionY() };
    Point2d const source0{ Sources[0]->GetPositionX(),
        Sources[0]->GetPositionY() };
    Point2d const source1{ Sources[1]->GetPositionX(),
        Sources[1]->GetPositionY() };
    std::array<Point2d, 4> const unionAnchors{
        source0, source1,
        Point2d{ Sources[0]->GetHomePosition().GetPositionX(),
            Sources[0]->GetHomePosition().GetPositionY() },
        Point2d{ Sources[1]->GetHomePosition().GetPositionX(),
            Sources[1]->GetHomePosition().GetPositionY() } };

    bool found = false;
    float bestMinimumDistance = -std::numeric_limits<float>::infinity();
    Point2d bestEndpoint;
    float bestZ = 0.0f;
    uint32 bestIndex = 0;
    BotRaidDrudgeSpacing::CandidateResult bestSpacing;
    for (std::size_t index = 1; index < candidates.size(); ++index)
    {
        Point2d const requested{ candidates[index].first,
            candidates[index].second };
        BotRaidDrudgeSpacing::CandidateResult const requestedSpacing =
            EvaluateAndRecordCandidateSpacing(uint32(index), requested.X,
                requested.Y, false, true, HomeLaneProjectionMinimum, nowMs);
        if (!requestedSpacing.Source0Safe || !requestedSpacing.Source1Safe
            || !requestedSpacing.LaneSafe || !requestedSpacing.Spacing.Safe
            || !NonTankEntranceEnvelopeSafe(OneBasedSlot, requested.X, requested.Y))
            continue;

        float requestedZ = declared->Z;
        if (!BotRaidDrudgeNativeAnchor::ResolveDynamicCandidateZ(
                Bot->GetMap(), Bot->GetPhaseShift(), requested.X,
                requested.Y, declared->Z, &requestedZ))
            continue;
        PathGenerator path(Bot);
        bool const pathOk = path.CalculatePath(
            requested.X, requested.Y, requestedZ, false);
        if (!BotWorldMovement::NativePathIsComplete(pathOk, path)
            || !BotWorldMovement::NativePathFloorsValid(
                Bot, path, requestedZ, true))
            continue;

        G3D::Vector3 const& nativeEnd = path.GetActualEndPosition();
        Point2d const endpoint{ nativeEnd.x, nativeEnd.y };
        if (!BotRaidDrudgeRecoveryCandidates::BoundedEndpointMiss(
                requested, endpoint, maximumMiss)
            || std::fabs(nativeEnd.z - requestedZ)
                > BotRaidDrudgeNativePath::ExactEndpointToleranceZYards
            || Bot->GetExactDist(nativeEnd.x, nativeEnd.y, nativeEnd.z) < 1.0f
            || !PreservesUnionDistanceFloors(
                Bot, unionAnchors, path, minimumDistance)
            || !BotRaidDrudgeRecoveryCandidates::EscapeEndpointProgresses(
                start, endpoint, source0, source1, minimumDistance))
            continue;

        uint32 const escapeIndex =
            BotRaidDrudgeRecoveryCandidates::EscapeCandidateIndex(uint32(index));
        BotRaidDrudgeSpacing::CandidateResult const endpointSpacing =
            EvaluateAndRecordCandidateSpacing(escapeIndex, endpoint.X,
                endpoint.Y, false, true, HomeLaneProjectionMinimum, nowMs);
        if (!endpointSpacing.LaneSafe || !endpointSpacing.Spacing.Safe
            || !NonTankEntranceEnvelopeSafe(
                OneBasedSlot, endpoint.X, endpoint.Y))
            continue;

        float const candidateMinimum =
            BotRaidDrudgeRecoveryCandidates::MinimumLiveSourceDistance(
                endpoint, source0, source1);
        if (!BotRaidDrudgeRecoveryCandidates::PreferEscapeEndpoint(
                found, bestMinimumDistance, candidateMinimum))
            continue;
        found = true;
        bestMinimumDistance = candidateMinimum;
        bestEndpoint = endpoint;
        bestZ = nativeEnd.z;
        bestIndex = escapeIndex;
        bestSpacing = endpointSpacing;
    }
    if (!found)
        return false;

    State.ValidationRouteDrudgeAnchorX = bestEndpoint.X;
    State.ValidationRouteDrudgeAnchorY = bestEndpoint.Y;
    State.ValidationRouteDrudgeAnchorZ = bestZ;
    State.ValidationRouteDrudgeAnchorCandidateIndex = bestIndex;
    State.ValidationRouteDrudgeAnchorValid = true;
    State.ValidationRouteDrudgeAnchorPathProven = true;
    State.ValidationRouteDrudgeAnchorAttemptId = Manager.Cohort().AttemptId;
    State.ValidationRouteDrudgeAnchorWipeGeneration =
        Manager.Cohort().Raid.WipeGeneration;
    State.ValidationRouteDrudgeAnchorRouteGeneration =
        Manager.Party().ValidationRouteGeneration;
    State.ValidationRouteDrudgeAnchorMapId = Bot->GetMapId();
    State.ValidationRouteDrudgeAnchorInstanceId = Bot->GetInstanceId();
    State.ValidationRouteDrudgeAnchorSource0Identity =
        Sources[0]->GetGUID().GetRawValue();
    State.ValidationRouteDrudgeAnchorSource1Identity =
        Sources[1]->GetGUID().GetRawValue();
    State.ValidationRouteDrudgeAnchorSearchCooldownUntilMs = 0;
    State.LastPathRejectReason.clear();
    State.LastRecoveryResult.clear();
    if (Charge)
    {
        BotRaidDrudgeGeometry::Scope const scope{
            Manager.Cohort().AttemptId,
            Manager.Cohort().Raid.WipeGeneration,
            Manager.Party().ValidationRouteGeneration,
            Bot->GetMapId(), Bot->GetInstanceId(),
            Sources[0]->GetGUID().GetRawValue(),
            Sources[1]->GetGUID().GetRawValue() };
        BotRaidDrudgeSpacing::ObserveReseparationCandidate(
            Charge->ReseparationReceipts, scope,
            Bot->GetGUID().GetCounter(), bestIndex,
            bestEndpoint.X, bestEndpoint.Y, bestZ,
            bestSpacing.Source0Safe, bestSpacing.Source1Safe,
            bestSpacing.LaneSafe, bestSpacing.Spacing.Safe,
            bestSpacing.GroupPositionSafe, true,
            "selected_progressive_path_proven", "none", nowMs);
    }
    return true;
}
}
