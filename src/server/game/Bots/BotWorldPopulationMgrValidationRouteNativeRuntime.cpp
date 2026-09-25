#include "Bots/BotWorldPopulationMgrValidationRouteNativeRuntime.h"
#include "Bots/BotValidationRouteNativeLogic.h"
#include "Bots/BotWorldPopulationMgrValidationRouteBoardingAction.h"
#include "Bots/BotWorldPopulationMgrValidationRouteNativeFacts.h"

#include "DataStores/DBCStores.h"
#include "GameObject.h"
#include "GossipDef.h"
#include "MotionMaster.h"
#include "PathGenerator.h"
#include "Player.h"
#include "Transport.h"

#include <algorithm>
#include <cmath>
#include <utility>

namespace
{
using namespace BotValidationRouteNative;
using BotWorldPopulationMgrValidationRouteNative::Callbacks;
using BotWorldPopulationMgrValidationRouteNative::Input;
using BotWorldPopulationMgrValidationRouteNative::MemberInput;
namespace Facts = BotWorldPopulationMgrValidationRouteNative::Facts;

using OutcomeObserver = std::function<void(BotActionArbitration::Outcome const&)>;

void Submit(Input const& input, Callbacks const& callbacks, std::string const& mechanic,
    ObjectGuid actor, BotActionArbitration::Priority priority, float utility,
    BotNativeAction::Intent intent, std::string actionLabel,
    OutcomeObserver observe = {})
{
    BotNativeAction::Candidate native;
    native.Id.ScopeKey = input.Board->CurrentScope.Key();
    native.Id.Strategy = "native_route_interaction";
    native.Id.Mechanic = mechanic;
    native.Id.Actor = actor;
    native.Id.EventGeneration = input.Board->Revision;
    native.ActionPriority = priority;
    native.Utility = utility;
    native.ExpiresAtMs = input.NowMs + 500;
    native.Action = std::move(intent);

    BotActionArbitration::Candidate candidate;
    candidate.Key = native.Id.Key();
    candidate.Source = native.Id.Strategy;
    candidate.ActionPriority = native.ActionPriority;
    candidate.UtilityScore = native.Utility;
    candidate.RequiredResources = native.Resources();
    candidate.ExpiresAtMs = native.ExpiresAtMs;
    candidate.Attempt = [execute = callbacks.Execute, action = native.Action,
        situation = input.Situation, label = input.Action, state = input.State,
        actionLabel = std::move(actionLabel), observe = std::move(observe)]()
    {
        BotActionArbitration::Outcome outcome = execute(action,
            BotMovementArbitration::Owner::Route,
            BotMovementArbitration::Priority::Route);
        if (outcome.Result == BotActionArbitration::Disposition::Committed)
        {
            *situation = "native_route_interaction";
            *label = actionLabel;
            state->LastDecisionHandler = "native_route_interaction";
        }
        if (observe)
            observe(outcome);
        return outcome;
    };
    input.State->DecisionKernel.Submit(std::move(candidate));
}

// Keep the member where it is (aboard a platform, at a wait point, or blocked)
// by owning the movement lane without issuing any movement.
void SubmitHold(Input const& input, std::string const& reason)
{
    BotActionArbitration::Candidate candidate;
    candidate.Key = input.Board->CurrentScope.Key() + ":native_route_hold";
    candidate.Source = "native_route_interaction";
    candidate.ActionPriority = BotActionArbitration::Priority::Mechanic;
    candidate.UtilityScore = 1.0f;
    candidate.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::Movement);
    candidate.ExpiresAtMs = input.NowMs + 500;
    candidate.Attempt = [reason, situation = input.Situation, label = input.Action,
        state = input.State]()
    {
        *situation = "native_route_interaction";
        *label = "native_route_" + reason;
        state->LastDecisionHandler = "native_route_interaction";
        return BotActionArbitration::Outcome::Progressed(reason);
    };
    input.State->DecisionKernel.Submit(std::move(candidate));
}

// End the member's current walk where it stands: releasing the movement
// input, not a relocation. Used when a walk toward a platform would outrun
// the platform's rest window, or to settle on the platform before boarding.
void SubmitStop(Input const& input, std::string const& reason)
{
    BotActionArbitration::Candidate candidate;
    candidate.Key = input.Board->CurrentScope.Key() + ":native_route_stop";
    candidate.Source = "native_route_interaction";
    candidate.ActionPriority = BotActionArbitration::Priority::Mechanic;
    candidate.UtilityScore = 5.0f;
    candidate.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::Movement);
    candidate.ExpiresAtMs = input.NowMs + 500;
    candidate.Attempt = [reason, bot = input.Bot, situation = input.Situation,
        label = input.Action, state = input.State]()
    {
        bot->StopMoving();
        bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
        bot->GetMotionMaster()->MoveIdle();
        state->ActivePathValid = false;
        state->ActivePathPurposeValid = false;
        state->ActivePathSegmentValid = false;
        state->ActivePathTraversalMode.clear();
        state->ActivePathTargetGuid.Clear();
        state->MovementLease = {};
        state->IsMoving = false;
        *situation = "native_route_interaction";
        *label = "native_route_" + reason;
        state->LastDecisionHandler = "native_route_interaction";
        return BotActionArbitration::Outcome::Committed(reason);
    };
    input.State->DecisionKernel.Submit(std::move(candidate));
}

// Walk length to `target` along the native path (never shorter than the
// straight line); an incomplete path adds its last leg to the target.
float PathLengthTo(Player* bot, Point3 const& target)
{
    float const straight = bot->GetExactDist(target.X, target.Y, target.Z);
    PathGenerator path(bot);
    if (!path.CalculatePath(target.X, target.Y, target.Z)
        || (path.GetPathType() & PATHFIND_NOPATH) || path.GetPath().size() < 2)
        return straight;
    float length = 0.0f;
    auto const& points = path.GetPath();
    for (std::size_t i = 1; i < points.size(); ++i)
        length += (points[i] - points[i - 1]).length();
    G3D::Vector3 const end(target.X, target.Y, target.Z);
    length += (end - points.back()).length();
    return std::max(length, straight);
}

void RecordOnChange(Callbacks const& callbacks, std::string& last,
    std::string const& reason, WorldObject* target, float value, uint32 entry)
{
    if (last == reason)
        return;
    last = reason;
    if (callbacks.Record)
        callbacks.Record(reason, target, value, entry);
}

void FailOnce(NodeRuntime& runtime, Callbacks const& callbacks, std::string const& reason)
{
    if (runtime.FailureRecorded)
        return;
    runtime.FailureRecorded = true;
    if (callbacks.Fail)
        callbacks.Fail(reason);
}

bool Retried(BotActionArbitration::Outcome const& outcome)
{
    return outcome.Result == BotActionArbitration::Disposition::Retryable
        || outcome.Result == BotActionArbitration::Disposition::Unsafe;
}

std::vector<MemberView> MemberViews(Input const& input)
{
    std::vector<MemberView> views;
    for (MemberInput const& member : input.Members)
    {
        if (!member.Bot)
            continue;
        MemberView view;
        view.Guid = member.Bot->GetGUID().GetRawValue();
        view.Alive = member.OnRouteInstance && member.Bot->IsAlive();
        auto roster = input.Roster.find(view.Guid);
        if (roster != input.Roster.end())
        {
            view.RosterSlot = roster->second.Slot;
            view.Role = roster->second.Role;
        }
        views.push_back(std::move(view));
    }
    return views;
}

void RunInteraction(Input const& input, Callbacks const& callbacks,
    NodeContract& node, OwnerElection const& election)
{
    InteractionContract const& contract = node.Interaction;
    NodeRuntime& runtime = node.Runtime;
    Player* bot = input.Bot;
    uint64 const self = bot->GetGUID().GetRawValue();
    if (!election.Owner)
        RecordOnChange(callbacks, runtime.LastDiagnostic, election.Reason, nullptr, 0.0f, 0);
    if (election.Owner != self)
    {
        // Everyone but the owner holds (or gathers) at the node anchor.
        if (contract.Gather && bot->IsAlive()
            && bot->GetExactDist(input.AnchorX, input.AnchorY, input.AnchorZ)
                > contract.GatherRadiusYards)
            Submit(input, callbacks, "gather", bot->GetGUID(),
                BotActionArbitration::Priority::RouteMovement, 1.0f,
                BotNativeAction::Move{ input.AnchorX, input.AnchorY,
                    input.AnchorZ, "native_interaction_gather" },
                "native_route_interaction_gather");
        return;
    }

    InteractionObservation observation;
    WorldObject* target = nullptr;
    float targetX = 0.0f, targetY = 0.0f, targetZ = 0.0f;
    if (contract.Action == InteractionAction::AreaTrigger)
    {
        AreaTriggerEntry const* trigger = sAreaTriggerStore.LookupEntry(contract.AreaTriggerId);
        observation.TargetResolved = trigger && trigger->ContinentID == bot->GetMapId();
        if (observation.TargetResolved)
        {
            targetX = trigger->Pos.X;
            targetY = trigger->Pos.Y;
            targetZ = trigger->Pos.Z;
            observation.InRange = bot->IsInAreaTriggerRadius(trigger);
        }
    }
    else
    {
        Facts::ResolvedTarget const resolved = Facts::ResolveInteractionTarget(bot, contract);
        target = resolved.Object;
        observation.TargetAmbiguous = resolved.Ambiguous;
        observation.TargetResolved = target != nullptr;
        if (target)
        {
            targetX = target->GetPositionX();
            targetY = target->GetPositionY();
            targetZ = target->GetPositionZ();
            // Gameobjects always use the native reach rule; a declared range
            // can only tighten the creature interaction distance.
            if (GameObject const* object = target->ToGameObject())
                observation.InRange = object->IsAtInteractDistance(bot);
            else
                observation.InRange = bot->IsWithinDistInMap(target, contract.RangeYards > 0.0f
                    ? std::min(contract.RangeYards, INTERACTION_DISTANCE) : INTERACTION_DISTANCE);
            observation.CurrentGossipMenu =
                bot->PlayerTalkClass->GetGossipMenu().GetMenuId();
            observation.GossipBoundToTarget =
                bot->PlayerTalkClass->GetInteractionData().SourceGuid == target->GetGUID();
        }
    }

    AttemptGate const gate = EvaluateAttemptGate(contract, runtime.Attempt,
        runtime.StartedAtMs, input.NowMs);
    InteractionDecision const decision = DecideInteraction(contract, observation, gate);
    RecordOnChange(callbacks, runtime.LastDiagnostic, decision.Reason, target,
        float(runtime.Attempt.Attempts), contract.Entry);

    ObjectGuid const targetGuid = target ? target->GetGUID() : ObjectGuid::Empty;
    BotNativeAction::Intent intent;
    switch (decision.Step)
    {
        case InteractionStep::Hold:
            return;
        case InteractionStep::Fail:
            FailOnce(runtime, callbacks, decision.Reason);
            return;
        case InteractionStep::Approach:
            intent = BotNativeAction::Move{ targetX, targetY, targetZ,
                "native_interaction_approach" };
            break;
        case InteractionStep::Use:
            intent = BotNativeAction::GameObjectUse{ targetGuid };
            break;
        case InteractionStep::GossipOpen:
            intent = BotNativeAction::GossipOpen{ targetGuid };
            break;
        case InteractionStep::GossipSelect:
            intent = BotNativeAction::GossipSelect{ targetGuid,
                observation.CurrentGossipMenu, contract.Option };
            break;
        case InteractionStep::SpellClick:
            intent = BotNativeAction::SpellClick{ targetGuid };
            break;
        case InteractionStep::VehicleEnter:
            intent = BotNativeAction::VehicleEnter{ targetGuid, int8(contract.Seat) };
            break;
        case InteractionStep::AreaTrigger:
            intent = BotNativeAction::AreaTrigger{ contract.AreaTriggerId };
            break;
    }
    OutcomeObserver observe;
    if (decision.CountsAsAttempt)
        // Accepted and rejected submissions both count toward exhaustion.
        observe = [runtimePtr = &runtime, scope = input.Scope, now = input.NowMs](
            BotActionArbitration::Outcome const& outcome)
        {
            if (runtimePtr->Scope != scope)
                return;
            if (outcome.Result == BotActionArbitration::Disposition::Committed
                || Retried(outcome))
                RecordAttempt(runtimePtr->Attempt, now);
        };
    Submit(input, callbacks, contract.ActionName, targetGuid,
        BotActionArbitration::Priority::Mechanic, 6.0f, std::move(intent),
        "native_route_interaction_submitted", std::move(observe));
}

void RunTransport(Input const& input, Callbacks const& callbacks, NodeContract& node,
    Facts::TransportTarget const& transport)
{
    TransportContract const& contract = node.Transport;
    NodeRuntime& runtime = node.Runtime;
    Player* bot = input.Bot;
    // Dead members belong to the native death/recovery flow, not the ride.
    if (!bot->IsAlive())
        return;
    uint64 const guid = bot->GetGUID().GetRawValue();
    TransportMemberState& member = runtime.TransportMembers[guid];

    bool modelAvailable = true;
    TransportMemberObservation observation;
    observation.Alive = bot->IsAlive();
    observation.TransportPresent = transport.Fact.Present;
    observation.TransportAmbiguous = transport.Fact.Ambiguous;
    observation.ReadyToBoard = TransportReadyToBoard(contract, transport.Fact);
    observation.AtExit = TransportAtExit(contract, transport.Fact);
    observation.OnThisTransport = Facts::OnTransport(bot, transport.Object);
    observation.OnOtherTransportOrVehicle = (bot->GetTransport() && !observation.OnThisTransport)
        || bot->GetVehicle();
    observation.Moving = bot->isMoving() || bot->HasUnitState(UNIT_STATE_MOVING);
    observation.Falling = bot->IsFalling();
    observation.NowMs = input.NowMs;
    observation.StaticFloorUnderfoot = BotValidationRouteBoardingAction::StaticFloorUnderfoot(
        bot, contract.FloorToleranceYards);
    if (transport.Object)
        observation.TransportFloorUnderfoot =
            BotValidationRouteBoardingAction::TransportFloorUnderfoot(bot, transport.Object,
                contract.FloorToleranceYards, modelAvailable);
    if (observation.ReadyToBoard && transport.Object)
        observation.RestRemainingMs = contract.BoardStopFrame >= 0 ? UnboundedRestMs
            : BotValidationRouteBoardingAction::RestRemainingAtLevelMs(transport.Object,
                contract.BoardTransportZ, contract.LevelToleranceYards);
    auto distance = [bot](Point3 const& point)
    {
        return point.Valid ? bot->GetExactDist(point.X, point.Y, point.Z) : 0.0f;
    };
    observation.DistanceToWait = distance(contract.WaitPoint);
    observation.DistanceToBoard = distance(contract.BoardPoint);
    observation.DistanceToDisembark = distance(contract.DisembarkPoint);
    observation.DistanceToExit = distance(contract.ExitPoint);
    float const runSpeed = std::max(bot->GetSpeed(MOVE_RUN), 0.1f);
    if (observation.ReadyToBoard && contract.BoardPoint.Valid)
    {
        // Off the platform the walk follows the native path; on it, the
        // remaining distance is a straight step across its own surface.
        bool const onPlatform = observation.TransportFloorUnderfoot
            && !observation.StaticFloorUnderfoot;
        float const walk = onPlatform ? observation.DistanceToBoard
            : PathLengthTo(bot, contract.BoardPoint);
        observation.TravelToBoardMs = uint64(walk / runSpeed * 1000.0f);
    }

    // Without the platform's collision model neither boarding nor the
    // stranded-member check can be proven: stop instead of guessing.
    TransportDecision decision = transport.Object && !modelAvailable
        ? TransportDecision{ TransportStep::Fail, "transport_model_unavailable" }
        : DecideTransportStep(contract, observation, member);
    RecordOnChange(callbacks, member.LastReason,
        std::string("native_route_transport_") + TransportStepName(decision.Step)
            + ":" + decision.Reason,
        transport.Object, transport.Fact.PositionZ, contract.Entry);

    ObjectGuid const transportGuid = transport.Object
        ? transport.Object->GetGUID() : ObjectGuid::Empty;
    auto countSubmission = [runtimePtr = &runtime, scope = input.Scope, guid,
        fail = callbacks.Fail](bool boarding)
    {
        return [runtimePtr, scope, guid, fail, boarding](
            BotActionArbitration::Outcome const& outcome)
        {
            if (runtimePtr->Scope != scope)
                return;
            TransportMemberState& state = runtimePtr->TransportMembers[guid];
            if (outcome.Result == BotActionArbitration::Disposition::Committed)
                ++(boarding ? state.BoardSubmissions : state.LeaveSubmissions);
            else if (Retried(outcome))
                ++state.FailedSubmissions;
            if (outcome.Result == BotActionArbitration::Disposition::Unsafe
                && !runtimePtr->FailureRecorded)
            {
                runtimePtr->FailureRecorded = true;
                if (fail)
                    fail(outcome.Reason);
            }
        };
    };
    switch (decision.Step)
    {
        case TransportStep::Fail:
            FailOnce(runtime, callbacks, decision.Reason);
            break;
        case TransportStep::Stop:
            SubmitStop(input, decision.Reason);
            break;
        case TransportStep::Hold:
        case TransportStep::HoldAboard:
        case TransportStep::Done:
        case TransportStep::Blocked:
            SubmitHold(input, decision.Reason);
            break;
        case TransportStep::MoveToWait:
            Submit(input, callbacks, "transport_wait", transportGuid,
                BotActionArbitration::Priority::Mechanic, 4.0f,
                BotNativeAction::Move{ contract.WaitPoint.X, contract.WaitPoint.Y,
                    contract.WaitPoint.Z, "native_transport_wait" },
                "native_route_transport_wait");
            break;
        case TransportStep::MoveToBoard:
            Submit(input, callbacks, "transport_board_path", transportGuid,
                BotActionArbitration::Priority::Mechanic, 4.0f,
                BotNativeAction::Move{ contract.BoardPoint.X, contract.BoardPoint.Y,
                    contract.BoardPoint.Z, "native_transport_board_path" },
                "native_route_transport_board_path");
            break;
        case TransportStep::Board:
            Submit(input, callbacks, "transport_board", transportGuid,
                BotActionArbitration::Priority::Mechanic, 6.0f,
                BotNativeAction::TransportBoard{ transportGuid, contract.FloorToleranceYards },
                "native_route_transport_board", countSubmission(true));
            break;
        case TransportStep::MoveToDisembark:
            Submit(input, callbacks, "transport_disembark_path", transportGuid,
                BotActionArbitration::Priority::Mechanic, 4.0f,
                BotNativeAction::Move{ contract.DisembarkPoint.X,
                    contract.DisembarkPoint.Y, contract.DisembarkPoint.Z,
                    "native_transport_disembark_path" },
                "native_route_transport_disembark_path");
            break;
        case TransportStep::Leave:
            Submit(input, callbacks, "transport_leave", transportGuid,
                BotActionArbitration::Priority::Mechanic, 6.0f,
                BotNativeAction::TransportLeave{ transportGuid, contract.FloorToleranceYards },
                "native_route_transport_leave", countSubmission(false));
            break;
        case TransportStep::MoveToExit:
            Submit(input, callbacks, "transport_exit_path", transportGuid,
                BotActionArbitration::Priority::Mechanic, 4.0f,
                BotNativeAction::Move{ contract.ExitPoint.X, contract.ExitPoint.Y,
                    contract.ExitPoint.Z, "native_transport_exit_path" },
                "native_route_transport_exit_path");
            break;
    }
}

// Every living cohort member, wherever it is, must have ridden (or boarded).
bool TransportNodeDone(Input const& input, NodeContract& node,
    Facts::TransportTarget const& transport, std::string& reason)
{
    if (!transport.Object)
    {
        reason = transport.Fact.Ambiguous ? "transport_ambiguous" : "transport_missing";
        return false;
    }
    uint32 living = 0;
    for (MemberInput const& input_member : input.Members)
    {
        Player* member = input_member.Bot;
        if (!member || !member->IsAlive())
            continue;
        ++living;
        // A member mid-teleport (loaded, not in the world) is off the route.
        if (!member->IsInWorld() || !input_member.OnRouteInstance
            || member->GetMap() != transport.Object->GetMap())
        {
            reason = "transport_member_off_route_map";
            return false;
        }
        TransportMemberState& state =
            node.Runtime.TransportMembers[member->GetGUID().GetRawValue()];
        bool const aboard = Facts::OnTransport(member, transport.Object);
        if (aboard)
            state.Boarded = true;
        Point3 const& exit = node.Transport.ExitPoint;
        float const exitDistance = exit.Valid
            ? member->GetExactDist(exit.X, exit.Y, exit.Z) : 0.0f;
        if (!MemberTransportDone(node.Transport, aboard, state.Boarded, exitDistance))
        {
            reason = "transport_members_pending";
            return false;
        }
    }
    reason = living ? "transport_route_complete" : "transport_no_living_members";
    return living > 0;
}

// Completion is evaluated once per cohort observation tick.
void RefreshVerdict(Input const& input, NodeContract& node, OwnerElection const& election,
    Player* evaluator)
{
    NodeRuntime& runtime = node.Runtime;
    if (runtime.VerdictValid && runtime.VerdictTick == input.Tick)
        return;
    bool satisfied = node.Completion.Declared || node.Transport.Declared;
    std::string reason = satisfied ? "" : "native_contract_without_completion";
    if (node.Completion.Declared)
    {
        Verdict const verdict = Facts::EvaluateCompletion(node.Completion, evaluator,
            input.Members, election.Owner, runtime.Completion);
        satisfied = satisfied && verdict.Satisfied;
        reason = verdict.Reason;
    }
    if (node.Transport.Declared && satisfied)
    {
        Facts::TransportTarget const transport = Facts::ResolveTransport(evaluator,
            node.Transport.Entry, node.Transport.SpawnId);
        satisfied = evaluator && TransportNodeDone(input, node, transport, reason);
    }
    runtime.VerdictValid = true;
    runtime.VerdictTick = input.Tick;
    runtime.VerdictSatisfied = satisfied;
    runtime.VerdictReason = reason;
}

bool TimedOut(std::uint32_t timeoutMs, NodeRuntime const& runtime, std::uint64_t nowMs)
{
    return timeoutMs && nowMs >= runtime.StartedAtMs + timeoutMs;
}
}

namespace BotWorldPopulationMgrValidationRouteNative
{
Result Run(Input const& input, Callbacks const& callbacks)
{
    Result result;
    if (!input.Bot || !input.State || !input.Board || !input.Node
        || !input.Situation || !input.Action || !input.Node->Declared())
        return result;
    result.OwnsNode = true;

    NodeContract& node = *input.Node;
    NodeRuntime& runtime = node.Runtime;
    runtime.Enter(input.Scope, input.NowMs);
    if (runtime.FailureRecorded)
        return result;

    auto const acting = std::find_if(input.Members.begin(), input.Members.end(),
        [&input](MemberInput const& member) { return member.Bot == input.Bot; });
    bool const actingOnRoute = acting != input.Members.end() && acting->OnRouteInstance;
    Player* const evaluator = Facts::SelectEvaluator(input.Members);
    OwnerElection const election = node.Interaction.Declared
        ? ElectOwner(node.Interaction, MemberViews(input)) : OwnerElection();

    RefreshVerdict(input, node, election, evaluator);
    if (runtime.VerdictSatisfied)
    {
        result.Satisfied = true;
        if (!input.CompletionAlreadyRecorded && !runtime.CompletionRecorded)
        {
            runtime.CompletionRecorded = true;
            if (callbacks.Complete)
                callbacks.Complete(node.Completion.Declared ? node.Completion.KindName
                    : runtime.VerdictReason, nullptr);
        }
        // Boarded members stay aboard until the next node takes over.
        if (node.Transport.Declared && actingOnRoute)
            RunTransport(input, callbacks,
                node, Facts::ResolveTransport(input.Bot, node.Transport.Entry, node.Transport.SpawnId));
        return result;
    }

    // Every declared contract is bounded in time.
    if (TimedOut(node.Interaction.TimeoutMs, runtime, input.NowMs))
    {
        FailOnce(runtime, callbacks, "native_interaction_timeout");
        return result;
    }
    if (TimedOut(node.Transport.TimeoutMs, runtime, input.NowMs))
    {
        FailOnce(runtime, callbacks, "native_transport_timeout");
        return result;
    }
    if (TimedOut(node.Completion.TimeoutMs, runtime, input.NowMs))
    {
        FailOnce(runtime, callbacks, "native_completion_timeout");
        return result;
    }
    if (!actingOnRoute)
        return result;

    if (node.Transport.Declared)
        RunTransport(input, callbacks, node,
            Facts::ResolveTransport(input.Bot, node.Transport.Entry, node.Transport.SpawnId));
    if (node.Interaction.Declared && !runtime.FailureRecorded)
        RunInteraction(input, callbacks, node, election);
    return result;
}
}
