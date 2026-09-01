#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"
#include "Bots/BotWorldPopulationMgrMovementProgressDiagnostics.h"
#include "Bots/BotWorldPopulationMgrNativeFloor.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneKernelBridge.h"
#include "GameTime.h"
#include "GitRevision.h"
#include "Map.h"
#include "Player.h"

#include <chrono>
#include <cmath>
#include <limits>
#include <sstream>
#include <utility>

namespace
{
namespace Checkpoint = BotEncounter::MagmawTransferLaneCheckpoint;

uint64 CheckpointNowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

std::string EscapeJson(std::string_view value)
{
    std::string result;
    result.reserve(value.size());
    for (char character : value)
    {
        if (character == '"' || character == '\\')
            result.push_back('\\');
        if (character == '\n')
            result += "\\n";
        else if (character != '\r')
            result.push_back(character);
    }
    return result;
}

bool Near(float left, float right, float tolerance)
{
    return std::fabs(left - right) <= tolerance;
}

bool ExactStart(Player const* bot, Checkpoint::Case const& selected)
{
    if (!bot || !bot->IsInWorld() || !bot->GetMap() || !bot->IsAlive()
        || bot->IsInCombat()
        || bot->GetMapId() != Checkpoint::MapId
        || std::hypot(bot->GetPositionX() - selected.StartX,
            bot->GetPositionY() - selected.StartY)
            > Checkpoint::StartTolerance2d
        || !Near(bot->GetPositionZ(), selected.StartZ,
            Checkpoint::StartToleranceZ))
        return false;
    float const floorZ = bot->GetMap()->GetHeight(bot->GetPhaseShift(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ() + 2.0f,
        true, 8.0f);
    return floorZ > INVALID_HEIGHT
        && Near(floorZ, bot->GetPositionZ(),
            BotWorldMovement::NativeFloorTolerance);
}

bool ExactImmediateOutcome(
    BotEncounter::MagmawTransferLaneNativeOutcome const& outcome,
    BotEncounter::MagmawTransferLaneTask const& task)
{
    BotWorldMovement::ExecutionObservation const& movement = outcome.Movement;
    return movement.Available && movement.ReceiptId
        && movement.Disposition
            == BotWorldMovement::ExecutionDisposition::Submitted
        && movement.PlannerAccepted && movement.NativeSubmitted
        && movement.RequestedX == task.Destination.X
        && movement.RequestedY == task.Destination.Y
        && movement.RequestedZ == task.Destination.Z;
}

bool ExactProgressIdentity(
    BotWorldMovement::NativeMovementProgressObservation const& progress,
    Checkpoint::State const& checkpoint)
{
    BotMovementArbitration::Scope const expected =
        BotEncounter::MagmawTransferLaneMovementScope(
            checkpoint.Task.Id.Episode.Lifecycle);
    return progress.Available
        && progress.ReceiptId == checkpoint.PlannerReceipt.ReceiptId
        && progress.BotGuid == checkpoint.Actor
        && progress.MapId == Checkpoint::MapId
        && progress.InstanceId == checkpoint.InstanceId
        && BotMovementArbitration::SameScope(progress.Scope, expected)
        && progress.SelectedX == checkpoint.Task.Destination.X
        && progress.SelectedY == checkpoint.Task.Destination.Y
        && progress.SelectedZ == checkpoint.Task.Destination.Z
        && progress.LaunchedSplineInitialized
        && progress.LaunchedSplineId == checkpoint.PlannerReceipt.SplineId;
}
}

std::string BotWorldPopulationMgr::ArmMagmawTransferLaneCheckpointForCohort(
    std::string const& cohortId, uint32 actorGuid,
    std::string const& caseId, std::string const& sealSha256,
    std::string const& sourceCommit)
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson(
            "botauto_magmaw_transfer_lane_checkpoint", cohortId);
    std::string const previous = _selectedCohortId;
    _selectedCohortId = cohortId;
    Checkpoint::State& checkpoint =
        Cohort().MagmawTransferLaneCheckpoint;
    BotControllerRouteHold::State& hold =
        Cohort().ChainwielderOwnerCheckpoint.ControllerRouteHold;
    Checkpoint::AdmissionInput const input{
        Cohort().Config.ValidationRouteEnable,
        Cohort().Config.MagmawTransferLaneCheckpointEnable,
        Cohort().Config.MagmawTransferLaneTaskAuthority,
        Cohort().Config.MagmawTransferLaneCheckpointFixtureId,
        Cohort().Config.MagmawTransferLaneCheckpointCaseId,
        Cohort().Config.MagmawTransferLaneCheckpointSealSha256,
        Cohort().Config.MagmawTransferLaneCheckpointSourceCommit,
        caseId, sealSha256, sourceCommit, GitRevision::GetHash() };
    BotControllerRouteHold::Identity const identity =
        CurrentControllerRouteHoldIdentity(actorGuid);
    if (!Checkpoint::AdmissionMatches(input)
        || hold.Scope.FixtureId != Checkpoint::FixtureId
        || !hold.AcknowledgeArm(identity, CheckpointNowMs()).Accepted
        || !checkpoint.Arm(caseId, actorGuid, Cohort().AttemptId))
    {
        checkpoint.Fail("magmaw_transfer_checkpoint_admission_failed");
        hold.Reject("magmaw_transfer_checkpoint_admission_failed");
    }
    std::string result = BuildMagmawTransferLaneCheckpointJson();
    _selectedCohortId = previous;
    return result;
}

std::string BotWorldPopulationMgr::GetMagmawTransferLaneCheckpointJsonForCohort(
    std::string const& cohortId) const
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson(
            "botauto_magmaw_transfer_lane_checkpoint", cohortId);
    std::string const previous = _selectedCohortId;
    const_cast<BotWorldPopulationMgr*>(this)->_selectedCohortId = cohortId;
    std::string result = BuildMagmawTransferLaneCheckpointJson();
    const_cast<BotWorldPopulationMgr*>(this)->_selectedCohortId = previous;
    return result;
}

void BotWorldPopulationMgr::SubmitMagmawTransferLaneCheckpointAfterKernelBegin(
    BotUpdateContext& context)
{
    Checkpoint::State& checkpoint =
        Cohort().MagmawTransferLaneCheckpoint;
    if (checkpoint.CurrentStage == Checkpoint::Stage::Disabled
        || checkpoint.Terminal()
        || !context.Bot || context.State.Guid.GetCounter() != checkpoint.Actor)
        return;

    Checkpoint::Case const* selected = Checkpoint::FindCase(checkpoint.CaseId);
    if (!selected || checkpoint.AttemptId != Cohort().AttemptId
        || Cohort().Config.MagmawTransferLaneTaskAuthority
        || Cohort().Raid.WipeGeneration
            > std::numeric_limits<uint32>::max()
        || context.Bot->GetMapId() != Checkpoint::MapId
        || ++checkpoint.AwaitTicks > Checkpoint::MaximumAwaitTicks)
    {
        FailMagmawTransferLaneCheckpoint(checkpoint,
            "magmaw_transfer_checkpoint_scope_or_timeout");
        return;
    }

    if (checkpoint.CurrentStage == Checkpoint::Stage::Armed)
    {
        QueueMagmawTransferLaneCheckpoint(context, checkpoint, *selected);
        return;
    }

    if (checkpoint.CurrentStage == Checkpoint::Stage::Queued)
        if (!ObserveMagmawTransferLaneCheckpointSubmission(
                context, checkpoint))
            return;
    ObserveMagmawTransferLaneCheckpointProgress(checkpoint);
}

void BotWorldPopulationMgr::QueueMagmawTransferLaneCheckpoint(
    BotUpdateContext& context, Checkpoint::State& checkpoint,
    Checkpoint::Case const& selected)
{
    if (!ExactStart(context.Bot, selected))
    {
        FailMagmawTransferLaneCheckpoint(checkpoint,
            "magmaw_transfer_checkpoint_start_invalid");
        return;
    }
    checkpoint.InstanceId = context.Bot->GetInstanceId();
    if (!checkpoint.InstanceId)
    {
        FailMagmawTransferLaneCheckpoint(checkpoint,
            "magmaw_transfer_checkpoint_instance_missing");
        return;
    }
    checkpoint.StartX = context.Bot->GetPositionX();
    checkpoint.StartY = context.Bot->GetPositionY();
    checkpoint.StartZ = context.Bot->GetPositionZ();
    BotEncounter::Scope lifecycle{ Cohort().Id, Cohort().AttemptId,
        static_cast<uint32>(Cohort().Raid.WipeGeneration),
        Party().ValidationRouteGeneration,
        Cohort().Config.ValidationRouteNodeId, Checkpoint::MapId,
        checkpoint.InstanceId, "magmaw_transfer_lane_checkpoint" };
    float const initialDistance = std::hypot(
        context.Bot->GetPositionX() - selected.DestinationX,
        context.Bot->GetPositionY() - selected.DestinationY);
    checkpoint.Task = Checkpoint::BuildTask(selected, lifecycle,
        context.Bot->GetGUID(), context.DecisionNowMs, initialDistance);
    BotNativeAction::Candidate legacy =
        Checkpoint::BuildLegacyCandidate(checkpoint.Task);
    std::vector<BotEncounter::MagmawTransferLaneTask> tasks{ checkpoint.Task };
    BotEncounter::MagmawTransferLaneAuthoritySelection selection =
        BotEncounter::SelectMagmawTransferLaneAuthority(false, tasks,
            context.Bot->GetGUID(), legacy,
            Checkpoint::LegacyTransitionGeneration);
    if (!Checkpoint::ExactAuthorityOffSelection(selection, legacy,
            checkpoint.Task))
    {
        FailMagmawTransferLaneCheckpoint(checkpoint,
            "magmaw_transfer_checkpoint_selector_diverged");
        return;
    }
    checkpoint.Binding = selection.Binding;
    checkpoint.ScopeKey = checkpoint.Binding->ScopeKey;
    checkpoint.CandidateKey = checkpoint.Binding->CandidateKey;
    bool const submitted = BotEncounter::SubmitMagmawTransferLaneKernelCandidate(
        context.State.DecisionKernel, *selection.Movement,
        *checkpoint.Binding, context.DecisionNowMs,
        [this, &context](BotNativeAction::Intent const& nativeIntent,
            BotWorldMovement::ExecutionObservation& movement)
        {
            Checkpoint::State& active =
                Cohort().MagmawTransferLaneCheckpoint;
            ++active.CandidateAttemptCount;
            context.State.LastMovementExecution = movement;
            BotActionArbitration::Outcome outcome = ExecuteNativeActionIntent(
                context.State, context.Bot, nativeIntent,
                BotMovementArbitration::Owner::Hazard,
                BotMovementArbitration::Priority::Hazard);
            movement = context.State.LastMovementExecution;
            if (movement.NativeSubmitted)
                ++active.NativeSubmissionCount;
            return outcome;
        },
        [this](BotEncounter::MagmawTransferLaneNativeOutcome const& row)
        {
            Cohort().MagmawTransferLaneCheckpoint.NativeOutcome = row;
        }, "validation_route_adapter");
    BotControllerRouteHold::State const& hold =
        Cohort().ChainwielderOwnerCheckpoint.ControllerRouteHold;
    bool const admissionMarked =
        BotControllerRouteHold::MarkCheckpointObservationCandidate(
            context.State.DecisionKernel, checkpoint.CandidateKey, hold,
            context.State.Guid.GetCounter());
    if (!submitted || !admissionMarked || ++checkpoint.QueueCount != 1)
    {
        FailMagmawTransferLaneCheckpoint(checkpoint,
            "magmaw_transfer_checkpoint_kernel_submit_failed");
        return;
    }
    checkpoint.CurrentStage = Checkpoint::Stage::Queued;
    checkpoint.QueuedAtMs = context.DecisionNowMs;
    checkpoint.Outcome = "magmaw_transfer_checkpoint_queued";
}

bool BotWorldPopulationMgr::ObserveMagmawTransferLaneCheckpointSubmission(
    BotUpdateContext& context, Checkpoint::State& checkpoint)
{
    if (!checkpoint.CandidateAttemptCount)
    {
        if (context.DecisionNowMs > checkpoint.QueuedAtMs)
            FailMagmawTransferLaneCheckpoint(checkpoint,
                "magmaw_transfer_checkpoint_task_not_selected");
        return false;
    }
    if (checkpoint.CandidateAttemptCount != 1
        || checkpoint.NativeSubmissionCount != 1
        || !checkpoint.NativeOutcome || !checkpoint.Binding
        || !ExactImmediateOutcome(*checkpoint.NativeOutcome, checkpoint.Task))
    {
        FailMagmawTransferLaneCheckpoint(checkpoint,
            "magmaw_transfer_checkpoint_native_submit_failed");
        return false;
    }
    uint64 const receiptId = checkpoint.NativeOutcome->Movement.ReceiptId;
    BotWorldMovement::MovementPlannerObservation const planner =
        BotWorldMovement::MovementPlannerDiagnostics().ForReceipt(receiptId);
    if (!Checkpoint::CaptureExactPlannerReceipt(checkpoint.PlannerReceipt,
            planner, *checkpoint.Binding, checkpoint.Task)
        || checkpoint.PlannerReceipt.ReceiptId != receiptId)
    {
        FailMagmawTransferLaneCheckpoint(checkpoint,
            "magmaw_transfer_checkpoint_planner_receipt_failed");
        return false;
    }
    BotWorldMovement::MovementProgressDiagnostics().RequestRetention(
        receiptId, checkpoint.Actor);
    checkpoint.CurrentStage = Checkpoint::Stage::NativeSubmitted;
    checkpoint.Outcome = "magmaw_transfer_checkpoint_native_submitted";
    return true;
}

void BotWorldPopulationMgr::ObserveMagmawTransferLaneCheckpointProgress(
    Checkpoint::State& checkpoint)
{
    BotWorldMovement::NativeMovementProgressObservation const progress =
        BotWorldMovement::MovementProgressDiagnostics().ForReceipt(
            checkpoint.PlannerReceipt.ReceiptId);
    Checkpoint::ProgressPublicationDecision const publication =
        Checkpoint::ObserveProgressPublication(checkpoint, progress.Available);
    if (publication == Checkpoint::ProgressPublicationDecision::Await)
        return;
    if (publication == Checkpoint::ProgressPublicationDecision::TimedOut)
    {
        FailMagmawTransferLaneCheckpoint(checkpoint,
            "magmaw_transfer_checkpoint_progress_publication_timeout");
        return;
    }
    if (!ExactProgressIdentity(progress, checkpoint))
    {
        FailMagmawTransferLaneCheckpoint(checkpoint,
            "magmaw_transfer_checkpoint_progress_receipt_failed");
        return;
    }
    for (BotWorldMovement::NativeMovementProgressSample const& sample
        : progress.Samples)
    {
        if (sample.ObservedAtMs <= checkpoint.LastSampleObservedAtMs)
            continue;
        if (!Checkpoint::ConsumeProgressSample(checkpoint, sample))
            break;
    }
    if (checkpoint.Terminal())
        PublishMagmawTransferLaneCheckpointTerminal(checkpoint);
    else if (progress.Terminal)
        FailMagmawTransferLaneCheckpoint(checkpoint,
            "magmaw_transfer_checkpoint_terminal_without_arrival");
}

void BotWorldPopulationMgr::FailMagmawTransferLaneCheckpoint(
    Checkpoint::State& checkpoint, std::string reason)
{
    checkpoint.Fail(std::move(reason));
    PublishMagmawTransferLaneCheckpointTerminal(checkpoint);
}

void BotWorldPopulationMgr::PublishMagmawTransferLaneCheckpointTerminal(
    Checkpoint::State& checkpoint)
{
    if (!checkpoint.Terminal() || checkpoint.TerminalPublished)
        return;
    checkpoint.TerminalPublished = true;
    // The booleans acknowledge terminal fixture state and preserved identity
    // only. Dedicated JSON never certifies gameplay success or boss fidelity.
    Cohort().ChainwielderOwnerCheckpoint.ControllerRouteHold
        .ObserveCheckpointTerminal(
            CurrentControllerRouteHoldIdentity(checkpoint.Actor),
            Checkpoint::StageName(checkpoint.CurrentStage), true, true,
            CheckpointNowMs());
}

std::string BotWorldPopulationMgr::BuildMagmawTransferLaneCheckpointJson() const
{
    Checkpoint::State const& checkpoint =
        Cohort().MagmawTransferLaneCheckpoint;
    std::ostringstream json;
    json << "{\"ok\":"
         << (checkpoint.CurrentStage != Checkpoint::Stage::Failed
                ? "true" : "false")
         << ",\"action\":\"botauto_magmaw_transfer_lane_checkpoint\""
         << ",\"terminal_kind\":\"fixture_checkpoint\""
         << ",\"certifies_gameplay_success\":false"
         << ",\"certifies_boss_fidelity\":false"
         << ",\"fixture_gate_passed\":"
         << (checkpoint.CurrentStage == Checkpoint::Stage::Completed
                ? "true" : "false")
         << ",\"authority\":\"" << Checkpoint::Authority << "\""
         << ",\"fixture_id\":\"" << Checkpoint::FixtureId << "\""
         << ",\"case_id\":\"" << EscapeJson(checkpoint.CaseId) << "\""
         << ",\"stage\":\""
         << Checkpoint::StageName(checkpoint.CurrentStage) << "\""
         << ",\"terminal\":"
         << (checkpoint.Terminal() ? "true" : "false")
         << ",\"actor_guid\":" << checkpoint.Actor
         << ",\"task_authority_enabled\":"
         << (Cohort().Config.MagmawTransferLaneTaskAuthority
                ? "true" : "false")
         << ",\"scope_key\":\"" << EscapeJson(checkpoint.ScopeKey) << "\""
         << ",\"episode_generation\":" << Checkpoint::EpisodeGeneration
         << ",\"task_generation\":" << Checkpoint::TaskGeneration
         << ",\"legacy_generation\":"
         << Checkpoint::LegacyTransitionGeneration
         << ",\"candidate_key\":\""
         << EscapeJson(checkpoint.CandidateKey) << "\""
         << ",\"queue_count\":" << checkpoint.QueueCount
         << ",\"candidate_attempt_count\":"
         << checkpoint.CandidateAttemptCount
         << ",\"native_submission_count\":"
         << checkpoint.NativeSubmissionCount
         << ",\"planner_receipt_id\":"
         << checkpoint.PlannerReceipt.ReceiptId
         << ",\"planner_candidate_key\":\""
         << EscapeJson(checkpoint.PlannerReceipt.CandidateKey) << "\""
         << ",\"motion_master_slot\":"
         << checkpoint.PlannerReceipt.MotionMasterSlot
         << ",\"motion_master_generator_type\":"
         << checkpoint.PlannerReceipt.MotionMasterGeneratorType
         << ",\"spline_id\":" << checkpoint.PlannerReceipt.SplineId
         << ",\"requested_destination\":{\"x\":"
         << checkpoint.Task.Destination.X << ",\"y\":"
         << checkpoint.Task.Destination.Y << ",\"z\":"
         << checkpoint.Task.Destination.Z << "}"
         << ",\"actor_start\":{\"x\":" << checkpoint.StartX
         << ",\"y\":" << checkpoint.StartY << ",\"z\":"
         << checkpoint.StartZ << "}"
         << ",\"actor_last_same_floor\":{\"x\":"
         << checkpoint.LastActorX << ",\"y\":"
         << checkpoint.LastActorY << ",\"z\":"
         << checkpoint.LastActorZ << ",\"floor_z\":"
         << checkpoint.LastFloorZ << "}"
         << ",\"progress_samples\":"
         << checkpoint.ConsumedProgressSamples
         << ",\"decreasing_progress_samples\":"
         << checkpoint.DecreasingProgressSamples
         << ",\"wrong_floor_samples\":" << checkpoint.WrongFloorSamples
         << ",\"task_state\":\""
         << BotEncounter::ToString(checkpoint.Task.State) << "\""
         << ",\"outcome\":\"" << EscapeJson(checkpoint.Outcome) << "\""
         << ",\"controller_route_hold\":"
         << BuildControllerRouteHoldJson() << "}";
    return json.str();
}
