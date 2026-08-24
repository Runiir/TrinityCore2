#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

#include "Bots/BotWorldPopulationMgr.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"
#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeRecoveryCandidates.h"

#include "Creature.h"
#include "Player.h"

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
bool DrudgeLaneContext::IsRecoveryFormationActive() const
{
    if (Manager.Cohort().Config.ValidationRouteMechanicProfile
        != "trash_two_tank_charge_lanes")
        return false;
    for (ChargeObservation const& observation :
        Manager.Party().ValidationRouteDrudgeChargeObservations)
        if (observation.Landed
            && observation.AttemptId == Manager.Cohort().AttemptId
            && observation.WipeGeneration == Manager.Cohort().Raid.WipeGeneration
            && observation.RouteGeneration
                == Manager.Party().ValidationRouteGeneration)
            return true;
    return false;
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
        result.Source0Safe = Distance2d(x, y, Sources[0]->GetPositionX(),
            Sources[0]->GetPositionY())
            >= Manager.Cohort().Config.ValidationRouteMinimumDistanceYards;
        result.Source1Safe = Distance2d(x, y, Sources[1]->GetPositionX(),
            Sources[1]->GetPositionY())
            >= Manager.Cohort().Config.ValidationRouteMinimumDistanceYards;
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
