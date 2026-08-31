#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"
#include "Bots/BotWorldPopulationMgrMovementProgressDiagnostics.h"
#include "Bots/BotWorldPopulationMgrNativeFloor.h"
#include "GameTime.h"
#include "GitRevision.h"
#include "Map.h"
#include "Player.h"

#include <chrono>
#include <cmath>
#include <sstream>
#include <string>

namespace
{
using BotNativePathCheckpoint::Case;
using BotNativePathCheckpoint::ExpectedPrimaryDisposition;
using BotNativePathCheckpoint::Stage;
using BotNativePathCheckpoint::State;

constexpr float EndpointTolerance = 0.25f;

uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

bool Near(float left, float right, float tolerance = EndpointTolerance)
{
    return std::fabs(left - right) <= tolerance;
}

BotWorldMovement::Intent StageIntent(Case const& selected)
{
    BotWorldMovement::Intent intent;
    intent.X = selected.StartX;
    intent.Y = selected.StartY;
    intent.Z = selected.StartZ;
    intent.TerminalOnFailure = true;
    intent.Owner = BotMovementArbitration::Owner::Formation;
    intent.Priority = BotMovementArbitration::Priority::Formation;
    intent.RequireCompletePath = true;
    intent.AllowRecentFailureRetry = true;
    intent.IntentReason = "native_path_checkpoint_stage:";
    intent.IntentReason += selected.Id;
    return intent;
}

BotWorldMovement::Intent HazardIntent(Case const& selected)
{
    BotWorldMovement::Intent intent;
    intent.X = selected.RequestX;
    intent.Y = selected.RequestY;
    intent.Z = selected.RequestZ;
    intent.TerminalOnFailure = true;
    intent.Owner = BotMovementArbitration::Owner::Hazard;
    intent.Priority = BotMovementArbitration::Priority::Hazard;
    intent.BoundedHazardProgress = true;
    intent.RequireCompletePath = selected.RequireCompletePath;
    intent.AllowRecentFailureRetry = true;
    intent.IntentReason = "native_path_checkpoint_hazard:";
    intent.IntentReason += selected.Id;
    return intent;
}

BotWorldMovement::PrimaryDisposition ExpectedDisposition(
    Case const& selected)
{
    switch (selected.ExpectedDisposition)
    {
        case ExpectedPrimaryDisposition::CompleteTerminal:
            return BotWorldMovement::PrimaryDisposition::CompleteTerminal;
        case ExpectedPrimaryDisposition::IncompleteFallbackEligible:
            return BotWorldMovement::PrimaryDisposition::
                IncompleteFallbackEligible;
        case ExpectedPrimaryDisposition::Forbidden:
            return BotWorldMovement::PrimaryDisposition::Forbidden;
    }
    return BotWorldMovement::PrimaryDisposition::Forbidden;
}

bool ExactPlannerIdentity(BotWorldMovement::MovementPlannerObservation const& row,
    Player const* bot, Case const& selected,
    BotWorldMovement::Intent const& intent)
{
    return row.Available && bot
        && row.BotGuid == bot->GetGUID().GetCounter()
        && row.RequestedMapId == BotNativePathCheckpoint::MapId
        && row.MovementOwner == intent.Owner
        && row.IntentReason == intent.IntentReason
        && Near(row.RequestedX, selected.RequestX)
        && Near(row.RequestedY, selected.RequestY)
        && Near(row.RequestedZ, selected.RequestZ)
        && row.RequireCompletePath == selected.RequireCompletePath
        && row.PrimaryPathDisposition == ExpectedDisposition(selected);
}

bool StageTerminalIsExact(
    BotWorldMovement::NativeMovementProgressObservation const& progress,
    Player const* bot, Case const& selected)
{
    if (!bot || !progress.Available || !progress.Terminal
        || progress.TerminalOutcome != "selected_endpoint_reached"
        || !Near(progress.SelectedX, selected.StartX)
        || !Near(progress.SelectedY, selected.StartY)
        || !Near(progress.SelectedZ, selected.StartZ)
        || !Near(bot->GetPositionX(), selected.StartX)
        || !Near(bot->GetPositionY(), selected.StartY)
        || std::fabs(bot->GetPositionZ() - selected.StartZ)
            > BotWorldMovement::NativeFloorTolerance)
        return false;
    float const floorZ = bot->GetMap()->GetHeight(bot->GetPhaseShift(),
        bot->GetPositionX(), bot->GetPositionY(),
        bot->GetPositionZ() + 2.0f, true, 8.0f);
    return floorZ > INVALID_HEIGHT
        && std::fabs(floorZ - bot->GetPositionZ())
            <= BotWorldMovement::NativeFloorTolerance;
}
}

std::string BotWorldPopulationMgr::ArmNativePathCheckpointForCohort(
    std::string const& cohortId, uint32 actorGuid,
    std::string const& caseId, std::string const& sealSha256,
    std::string const& sourceCommit)
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson("botauto_native_path_checkpoint", cohortId);
    std::string const previous = _selectedCohortId;
    _selectedCohortId = cohortId;
    State& checkpoint = Cohort().NativePathCheckpoint;
    BotControllerRouteHold::State& hold =
        Cohort().ChainwielderOwnerCheckpoint.ControllerRouteHold;
    std::string const nativeRevisionHash = GitRevision::GetHash();
    bool const configured = Cohort().Config.ValidationRouteEnable
        && Cohort().Config.NativePathCheckpointEnable
        && Cohort().Config.NativePathCheckpointFixtureId
            == BotNativePathCheckpoint::FixtureId
        && Cohort().Config.NativePathCheckpointCaseId == caseId
        && Cohort().Config.NativePathCheckpointSealSha256 == sealSha256
        && Cohort().Config.NativePathCheckpointSourceCommit == sourceCommit
        && BotControllerRouteHold::IsLowerHex(sealSha256, 64)
        && BotControllerRouteHold::IsLowerHex(sourceCommit, 40)
        && sourceCommit.substr(0, nativeRevisionHash.size())
            == nativeRevisionHash;
    BotControllerRouteHold::Identity const identity =
        CurrentControllerRouteHoldIdentity(actorGuid);
    if (!configured || hold.Scope.FixtureId
            != BotNativePathCheckpoint::FixtureId
        || !hold.AcknowledgeArm(identity, NowMs()).Accepted
        || !checkpoint.Arm(caseId, actorGuid, Cohort().AttemptId))
    {
        checkpoint.Fail("native_path_checkpoint_admission_failed");
        hold.Reject("native_path_checkpoint_admission_failed");
    }
    std::string result = BuildNativePathCheckpointJson();
    _selectedCohortId = previous;
    return result;
}

std::string BotWorldPopulationMgr::GetNativePathCheckpointJsonForCohort(
    std::string const& cohortId) const
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson("botauto_native_path_checkpoint", cohortId);
    std::string const previous = _selectedCohortId;
    const_cast<BotWorldPopulationMgr*>(this)->_selectedCohortId = cohortId;
    std::string result = BuildNativePathCheckpointJson();
    const_cast<BotWorldPopulationMgr*>(this)->_selectedCohortId = previous;
    return result;
}

void BotWorldPopulationMgr::ObserveNativePathCheckpointBeforeUpdate(
    WorldBotState& state, Player* bot)
{
    State& checkpoint = Cohort().NativePathCheckpoint;
    if (!bot || checkpoint.Terminal()
        || checkpoint.CurrentStage == Stage::Disabled
        || checkpoint.ActorGuid != state.Guid.GetCounter()
        || checkpoint.AttemptId != Cohort().AttemptId)
        return;
    Case const* selected = BotNativePathCheckpoint::FindCase(
        checkpoint.CaseId);
    auto terminalize = [&](bool success, char const* outcome)
    {
        checkpoint.CurrentStage = success ? Stage::Completed : Stage::Failed;
        checkpoint.Outcome = outcome;
        BotControllerRouteHold::State& hold =
            Cohort().ChainwielderOwnerCheckpoint.ControllerRouteHold;
        hold.ObserveCheckpointTerminal(
            CurrentControllerRouteHoldIdentity(checkpoint.ActorGuid),
            BotNativePathCheckpoint::StageName(checkpoint.CurrentStage),
            true, true, NowMs());
    };
    if (!selected || bot->GetMapId() != BotNativePathCheckpoint::MapId
        || ++checkpoint.AwaitTicks > BotNativePathCheckpoint::MaximumAwaitTicks)
    {
        terminalize(false, "native_path_checkpoint_scope_or_timeout");
        return;
    }

    if (checkpoint.CurrentStage == Stage::Armed)
    {
        BotWorldMovement::Intent const intent = StageIntent(*selected);
        ++checkpoint.StageSubmitCount;
        if (checkpoint.StageSubmitCount != 1
            || !ExecuteMovementIntent(state, bot, intent))
        {
            terminalize(false, "native_path_checkpoint_stage_submit_failed");
            return;
        }
        BotWorldMovement::MovementPlannerObservation const row =
            BotWorldMovement::MovementPlannerDiagnostics().Latest(
                checkpoint.ActorGuid);
        checkpoint.StageReceiptId = row.LaunchReceipt.Id;
        if (!checkpoint.StageReceiptId || row.IntentReason != intent.IntentReason)
        {
            terminalize(false, "native_path_checkpoint_stage_receipt_missing");
            return;
        }
        checkpoint.CurrentStage = Stage::Staging;
        checkpoint.Outcome = "native_path_checkpoint_staging";
        return;
    }

    if (checkpoint.CurrentStage == Stage::Staging)
    {
        BotWorldMovement::NativeMovementProgressObservation const progress =
            BotWorldMovement::MovementProgressDiagnostics().ForReceipt(
                checkpoint.StageReceiptId);
        if (!progress.Terminal)
            return;
        if (!StageTerminalIsExact(progress, bot, *selected))
        {
            terminalize(false, "native_path_checkpoint_stage_identity_failed");
            return;
        }

        BotWorldMovement::Intent const intent = HazardIntent(*selected);
        ++checkpoint.HazardSubmitCount;
        bool const launched = ExecuteMovementIntent(state, bot, intent);
        BotWorldMovement::MovementPlannerObservation const row =
            BotWorldMovement::MovementPlannerDiagnostics().Latest(
                checkpoint.ActorGuid);
        checkpoint.HazardReceiptId = row.LaunchReceipt.Id;
        if (checkpoint.HazardSubmitCount != 1 || !checkpoint.HazardReceiptId
            || !ExactPlannerIdentity(row, bot, *selected, intent))
        {
            terminalize(false, "native_path_checkpoint_hazard_identity_failed");
            return;
        }
        bool const expectsLaunch = selected->ExpectedDisposition
            == ExpectedPrimaryDisposition::IncompleteFallbackEligible;
        bool const proofShape = expectsLaunch
            ? row.LocalFallbackAttempted && row.NativeProof.Accepted
                && row.NativeProof.Complete
                && row.FinalTraversalMode != "unavailable"
                && row.LaunchReceipt.MotionMasterSubmissionObserved
            : !row.LocalFallbackAttempted
                && !row.LaunchReceipt.MotionMasterSubmissionObserved;
        if (launched != expectsLaunch || !proofShape)
        {
            terminalize(false, "native_path_checkpoint_outcome_mismatch");
            return;
        }
        if (!expectsLaunch)
        {
            terminalize(true, "native_path_checkpoint_no_launch_verified");
            return;
        }
        checkpoint.CurrentStage = Stage::HazardSubmitted;
        checkpoint.Outcome = "native_path_checkpoint_hazard_submitted";
        return;
    }

    BotWorldMovement::NativeMovementProgressObservation const progress =
        BotWorldMovement::MovementProgressDiagnostics().ForReceipt(
            checkpoint.HazardReceiptId);
    if (!progress.Terminal)
        return;
    bool const complete = progress.TerminalOutcome
            == "selected_endpoint_reached"
        && !progress.Samples.empty();
    terminalize(complete, complete
        ? "native_path_checkpoint_launch_progress_verified"
        : "native_path_checkpoint_launch_progress_failed");
}

std::string BotWorldPopulationMgr::BuildNativePathCheckpointJson() const
{
    State const& checkpoint = Cohort().NativePathCheckpoint;
    Case const* selected = BotNativePathCheckpoint::FindCase(checkpoint.CaseId);
    BotWorldMovement::MovementPlannerObservation const planner =
        BotWorldMovement::MovementPlannerDiagnostics().Latest(
            checkpoint.ActorGuid);
    std::ostringstream json;
    json << "{\"ok\":"
         << (checkpoint.CurrentStage != Stage::Failed ? "true" : "false")
         << ",\"action\":\"botauto_native_path_checkpoint\""
         << ",\"authority\":\"" << BotNativePathCheckpoint::Authority << "\""
         << ",\"fixture_id\":\"" << BotNativePathCheckpoint::FixtureId << "\""
         << ",\"case_id\":\"" << checkpoint.CaseId << "\""
         << ",\"stage\":\""
         << BotNativePathCheckpoint::StageName(checkpoint.CurrentStage) << "\""
         << ",\"terminal\":" << (checkpoint.Terminal() ? "true" : "false")
         << ",\"actor_guid\":" << checkpoint.ActorGuid
         << ",\"source_actor_guid\":"
         << (selected ? selected->SourceActorGuid : 0)
         << ",\"source_receipt_id\":"
         << (selected ? selected->SourceReceiptId : 0)
         << ",\"stage_receipt_id\":" << checkpoint.StageReceiptId
         << ",\"hazard_receipt_id\":" << checkpoint.HazardReceiptId
         << ",\"stage_submit_count\":" << checkpoint.StageSubmitCount
         << ",\"hazard_submit_count\":" << checkpoint.HazardSubmitCount
         << ",\"outcome\":\"" << checkpoint.Outcome << "\""
         << ",\"controller_route_hold\":" << BuildControllerRouteHoldJson()
         << ",\"movement_planner\":"
         << BotWorldMovement::MovementPlannerObservationJson(planner)
         << "}";
    return json.str();
}
