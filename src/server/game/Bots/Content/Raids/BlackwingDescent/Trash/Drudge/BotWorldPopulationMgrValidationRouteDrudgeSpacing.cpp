#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeRecoveryCandidates.h"

#include "Creature.h"
#include "PathGenerator.h"
#include "Player.h"

#include <array>

using BotWorldPopulationMgrNativeHelpers::Distance2d;

bool BotWorldPopulationMgr::TryValidationRouteDrudgeMinimumDistance(
    WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power,
    BotProgressionStage stage, BotProgressionActivity activity,
    std::string& situation, std::string& action, Unit*& target,
    std::function<bool(Creature const*)> const& isValidationCohortCombatLinked,
    bool specializedDrudgeRecovery)
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
    request.Callbacks.IsCombatLinked = isValidationCohortCombatLinked;
    BotWorldPopulationMgrValidationRoute::DrudgeLaneContext context(request);
    return context.TryMinimumDistance(specializedDrudgeRecovery);
}

namespace BotWorldPopulationMgrValidationRoute
{
bool DrudgeLaneContext::IsEntrancePullEstablished() const
{
    auto const& roster = Manager.Cohort().Raid.RosterByGuid;
    auto const& owners =
        Manager.Party().ValidationRouteDrudgeOwnershipRosterGuids;
    uint32 exactTanks = 0;
    for (auto const& [guid, member] : roster)
        if (member.Active && member.LeaseOwned && member.Role == "tank")
        {
            ++exactTanks;
            if (!owners.count(guid))
                return false;
        }
    return exactTanks == 2 && owners.size() == exactTanks;
}

bool DrudgeLaneContext::IsRecoveryFormationActive() const
{
    if (Manager.Cohort().Config.ValidationRouteMechanicProfile
        != "trash_two_tank_charge_lanes")
        return false;
    return IsEntrancePullEstablished() || IsLandedRushPending();
}

bool DrudgeLaneContext::SourceUnionSafeAt(
    uint32 sourceIndex, float x, float y) const
{
    float const minimum = Manager.Cohort().Config.ValidationRouteMinimumDistanceYards;
    if (sourceIndex >= Sources.size() || !Sources[sourceIndex] || minimum <= 0.0f)
        return false;
    Creature const* source = Sources[sourceIndex];
    Position const& home = source->GetHomePosition();
    return Distance2d(x, y, source->GetPositionX(), source->GetPositionY())
            >= minimum
        && Distance2d(x, y, home.GetPositionX(), home.GetPositionY()) >= minimum;
}

bool DrudgeLaneContext::SourceUnionSafe(float x, float y) const
{
    return Sources.size() == 2 && SourceUnionSafeAt(0, x, y)
        && SourceUnionSafeAt(1, x, y);
}

bool DrudgeLaneContext::SourceUnionPathSafe(PathGenerator const& path) const
{
    if (!Bot || path.GetPath().empty()
        || !SourceUnionSafe(path.GetActualEndPosition().x,
            path.GetActualEndPosition().y))
        return false;
    float const minimum = Manager.Cohort().Config.ValidationRouteMinimumDistanceYards;
    if (minimum <= 0.0f)
        return false;
    using BotRaidDrudgeRecoveryCandidates::Point2d;
    std::array<Point2d, 4> const unionAnchors{
        Point2d{ Sources[0]->GetPositionX(), Sources[0]->GetPositionY() },
        Point2d{ Sources[1]->GetPositionX(), Sources[1]->GetPositionY() },
        Point2d{ Sources[0]->GetHomePosition().GetPositionX(),
            Sources[0]->GetHomePosition().GetPositionY() },
        Point2d{ Sources[1]->GetHomePosition().GetPositionX(),
            Sources[1]->GetHomePosition().GetPositionY() } };
    Point2d const start{ Bot->GetPositionX(), Bot->GetPositionY() };
    std::array<float, 4> startDistances{};
    for (std::size_t index = 0; index < unionAnchors.size(); ++index)
        startDistances[index] = std::sqrt(
            BotRaidDrudgeRecoveryCandidates::DistanceSquared(
                start, unionAnchors[index]));
    std::size_t firstPoint = 0;
    G3D::Vector3 const& first = path.GetPath().front();
    if (std::hypot(first.x - Bot->GetPositionX(), first.y - Bot->GetPositionY())
        <= 0.25f)
        firstPoint = 1;
    for (std::size_t index = firstPoint; index < path.GetPath().size(); ++index)
    {
        G3D::Vector3 const& point = path.GetPath()[index];
        Point2d const pathPoint{ point.x, point.y };
        for (std::size_t anchorIndex = 0;
            anchorIndex < unionAnchors.size(); ++anchorIndex)
            if (!BotRaidDrudgeRecoveryCandidates::PathPointPreservesSourceDistance(
                    pathPoint, unionAnchors[anchorIndex],
                    startDistances[anchorIndex], minimum))
                return false;
    }
    return true;
}

BotRaidDrudgeSpacing::CandidateResult DrudgeLaneContext::EvaluateAndRecordCandidateSpacing(
    uint32 candidateIndex, float x, float y, bool tank,
    bool dynamicCandidate, float dynamicLaneProjection, uint64 nowMs)
{
    BotRaidDrudgeSpacing::CandidateResult result;
    BotRaidDrudgeRecoveryCandidates::Constraints const constraints{
        { Sources[0]->GetPositionX(), Sources[0]->GetPositionY() },
        { Sources[1]->GetPositionX(), Sources[1]->GetPositionY() },
        { MidpointX, MidpointY }, { AxisX, AxisY },
        Manager.Cohort().Config.ValidationRouteMinimumDistanceYards,
        LaneSign, LaneSeparation * 0.25f };
    BotRaidDrudgeRecoveryCandidates::Point2d const candidate{x, y};
    float const projection = (x - MidpointX) * AxisX
        + (y - MidpointY) * AxisY;
    result.LaneSafe = BotRaidDrudgeRecoveryCandidates::LaneSafe(
        candidate, constraints)
        && LaneSign * projection >= dynamicLaneProjection;
    if (dynamicCandidate)
    {
        result.Spacing = EvaluateRecoveryCandidateSpacing(x, y, tank);
        result.Source0Safe = tank || SourceUnionSafeAt(0, x, y);
        result.Source1Safe = tank || SourceUnionSafeAt(1, x, y);
        result.GroupPositionSafe = BotRaidDrudgeGeometry::DynamicGroupPositionSafe(
            result.Source0Safe, result.Source1Safe, result.LaneSafe,
            result.Spacing.Safe);
    }
    if (dynamicCandidate && Charge)
    {
        BotRaidDrudgeSpacing::PredicateEvidence const evidence{
            Bot->GetGUID().GetCounter(), candidateIndex, x, y,
            result.Spacing.PeerGuid, result.Spacing.PeerDistance,
            result.Spacing.PeerCoordinateSource, result.Source0Safe,
            result.Source1Safe, result.LaneSafe, result.Spacing.Safe,
            result.GroupPositionSafe };
        BotRaidDrudgeGeometry::Scope const scope{
            Manager.Cohort().AttemptId,
            Manager.Cohort().Raid.WipeGeneration,
            Manager.Party().ValidationRouteGeneration,
            Bot->GetMapId(), Bot->GetInstanceId(),
            Sources[0]->GetGUID().GetRawValue(),
            Sources[1]->GetGUID().GetRawValue() };
        BotRaidDrudgeSpacing::RecordFirstFailure(
            Charge->FirstSpacingFailure, scope, evidence, nowMs);
    }
    return result;
}
}
