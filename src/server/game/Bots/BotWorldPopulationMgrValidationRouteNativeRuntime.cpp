#include "Bots/BotWorldPopulationMgrValidationRouteNativeRuntime.h"
#include "Bots/BotValidationRouteNativeLogic.h"
#include "Bots/BotWorldPopulationMgrValidationRouteNativeRecovery.h"
#include "Bots/BotWorldPopulationMgrNativePathTransportSurface.h"
#include "Bots/BotWorldPopulationMgrValidationRouteBoardingAction.h"
#include "Bots/BotWorldPopulationMgrValidationRouteNativeFacts.h"

#include "DataStores/DBCStores.h"
#include "GameObject.h"
#include "GossipDef.h"
#include "MotionMaster.h"
#include "Movement/Spline/MoveSpline.h"
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

// A cycling platform rests about two seconds at each level. A stage bound to
// that window (the walk to or onto the car, the step off, board, disembark
// and leave) and the cast-owning hold of a walk or step in flight win the
// Mechanic priority on utility over every ordinary Mechanic candidate that
// would take their lanes. Round 3 Chimaeron shard: the pre-pull consumable
// hold (Mechanic, utility 12, GCD/cast/target) beat the recovery ride's
// surface walk (Mechanic, utility 6) at every rest window, so only the three
// healers it skipped ever rode. Survival stays with the defensives and hazard
// exits (utility 200-500): only the fall and the landing, which cannot pause
// mid-air, take Survival, below every one of them.
constexpr float TransportWindowUtility = 20.0f;
constexpr BotActionArbitration::Priority TransportFallPriority =
    BotActionArbitration::Priority::Survival;
constexpr float TransportFallUtility = 6.0f;

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
// by owning the movement lane without issuing any movement. A walk, step or
// fall in flight also owns the cast lanes (ApproachHoldOwnsCasting), ahead of
// any heal or rotation at the same priority.
void SubmitHold(Input const& input, std::string const& reason, bool ownsCasting = false)
{
    BotActionArbitration::Candidate candidate;
    candidate.Key = input.Board->CurrentScope.Key() + ":native_route_hold";
    candidate.Source = "native_route_interaction";
    bool const falling = ownsCasting && reason == "transport_drop_falling";
    candidate.ActionPriority = falling ? TransportFallPriority
        : BotActionArbitration::Priority::Mechanic;
    candidate.UtilityScore = falling ? TransportFallUtility
        : ownsCasting ? TransportWindowUtility : 1.0f;
    candidate.RequiredResources = ownsCasting
        ? BotActionArbitration::Uses(BotActionArbitration::Resource::Movement,
            BotActionArbitration::Resource::GlobalCooldown, BotActionArbitration::Resource::Cast)
        : BotActionArbitration::Uses(BotActionArbitration::Resource::Movement);
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

// A native route motion replaced (or ended) the member's ordinary planned
// path: drop that path's retained evidence and its movement lease.
void ReleaseOrdinaryPath(BotWorldPopulationMgrValidationRouteNative::WorldBotState& state,
    bool moving)
{
    state.ActivePathValid = false;
    state.ActivePathPurposeValid = false;
    state.ActivePathSegmentValid = false;
    state.ActivePathTraversalMode.clear();
    state.ActivePathTargetGuid.Clear();
    state.MovementLease = {};
    state.IsMoving = moving;
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
        ReleaseOrdinaryPath(*state, false);
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

// The owner's walk toward a creature or gameobject: a point on the complete
// native path, short of the target and within its reach (see
// SelectInteractionApproachPoint). Without a complete path the target's own
// position is kept and the movement planner reports why.
Point3 InteractionApproachPoint(Player* bot, Point3 const& target, float reachYards)
{
    std::vector<Point3> points;
    PathGenerator path(bot);
    if (path.CalculatePath(target.X, target.Y, target.Z, false)
        && path.GetPathType() == PATHFIND_NORMAL)
        for (G3D::Vector3 const& point : path.GetPath())
            points.push_back({ point.x, point.y, point.z, true });
    return SelectInteractionApproachPoint(target, points, reachYards);
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

// One member's step of an interaction contract: the node's own, or a
// recovery wake's (each with its own runtime state).
void RunInteraction(Input const& input, Callbacks const& callbacks,
    InteractionContract const& contract, NodeRuntime& runtime,
    OwnerElection const& election)
{
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
        {
            // Area triggers keep their own centre; creatures and gameobjects
            // are reached from the walkable floor short of them, within the
            // same reach the in-range observation uses (never beyond 5 yd).
            Point3 destination{ targetX, targetY, targetZ, true };
            if (target)
            {
                float reach = INTERACTION_DISTANCE;
                if (GameObject const* object = target->ToGameObject())
                    reach = std::min(object->GetInteractionDistance(), INTERACTION_DISTANCE);
                else if (contract.RangeYards > 0.0f)
                    reach = std::min(contract.RangeYards, INTERACTION_DISTANCE);
                destination = InteractionApproachPoint(bot, destination, reach);
                // A gameobject is used from where its native check admits the
                // player: keep its own position when the stand point is not.
                if (GameObject const* object = target->ToGameObject())
                    if (!object->IsAtInteractDistance(
                            Position(destination.X, destination.Y, destination.Z),
                            object->GetInteractionDistance()))
                        destination = Point3{ targetX, targetY, targetZ, true };
            }
            intent = BotNativeAction::Move{ destination.X, destination.Y, destination.Z,
                "native_interaction_approach" };
            break;
        }
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

// How far the member stands from its approach start: from the start point,
// or for a ledge drop from the line toward the step-off point (a step cut
// short on the lip steps off again from there).
float ApproachStartDistance(Player const* bot, ApproachContract const& approach)
{
    if (approach.Mode == ApproachMode::LedgeDrop)
        return DistanceToApproachLine(approach.StartPoint, approach.StepOffPoint,
            bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ());
    return bot->GetExactDist(approach.StartPoint.X, approach.StartPoint.Y,
        approach.StartPoint.Z);
}

// Every loaded cohort member as the node-level approach rules see it: the
// ledge-drop barrier, the completion override's handover and the typed
// timeout all read the same views.
std::vector<ApproachMemberView> ApproachMemberViews(Input const& input,
    NodeRuntime const& runtime, GameObject const* transport, TransportContract const& contract)
{
    ApproachContract const& approach = contract.Approach;
    float const startTolerance =
        std::min(contract.ArrivalToleranceYards, ApproachStartToleranceYards);
    std::vector<ApproachMemberView> views;
    for (MemberInput const& member : input.Members)
    {
        Player* bot = member.Bot;
        if (!bot)
            continue;
        ApproachMemberView view;
        view.Guid = bot->GetGUID().GetRawValue();
        view.Alive = bot->IsAlive();
        view.OnRouteInstance = member.OnRouteInstance && bot->IsInWorld();
        view.Aboard = Facts::OnTransport(bot, transport);
        auto const state = runtime.TransportMembers.find(view.Guid);
        if (state != runtime.TransportMembers.end())
            view.Phase = state->second.Approach;
        view.Falling = BotValidationRouteBoardingAction::NativeFallInProgress(bot);
        // At the start and on a verified floor there (a probe miss holds the
        // cohort while that member re-snaps).
        view.AtStart = approach.StartPoint.Valid && AtApproachStart(
            ApproachStartDistance(bot, approach), startTolerance,
            BotValidationRouteBoardingAction::StaticFloorUnderfoot(bot,
                contract.FloorToleranceYards));
        view.FallMarginOk = true;
        if (approach.Mode == ApproachMode::LedgeDrop && bot->GetMaxHealth())
            view.FallMarginOk = float(bot->GetHealth()) / float(bot->GetMaxHealth())
                    - BotTransportSurfaceMovement::PredictFallDamagePct(bot,
                        bot->GetPositionZ() - approach.LandingZ)
                >= approach.MinHealthAfterFallPct;
        views.push_back(view);
    }
    return views;
}

// One member's step of a transport contract: the node's own, or a recovery
// ride's (each with its own runtime state).
void RunTransport(Input const& input, Callbacks const& callbacks,
    TransportContract const& contract, NodeRuntime& runtime,
    Facts::TransportTarget const& transport)
{
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
    // Unit::IsFalling() stays true after a finalized MoveFall spline until
    // the next spline replaces it; only a running fall or the falling flags
    // count here.
    observation.Falling = BotValidationRouteBoardingAction::NativeFallInProgress(bot);
    observation.FallSplineActive = BotValidationRouteBoardingAction::NativeFallSplineActive(bot);
    observation.LandingPending = BotValidationRouteBoardingAction::NativeFallLandingPending(bot);
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
    ApproachContract const& approach = contract.Approach;
    if (observation.ReadyToBoard && contract.BoardPoint.Valid
        && approach.Mode == ApproachMode::None)
    {
        // Off the platform the walk follows the native path; on it, the
        // remaining distance is a straight step across its own surface.
        bool const onPlatform = observation.TransportFloorUnderfoot
            && !observation.StaticFloorUnderfoot;
        float const walk = onPlatform ? observation.DistanceToBoard
            : PathLengthTo(bot, contract.BoardPoint);
        observation.TravelToBoardMs = uint64(walk / runSpeed * 1000.0f);
    }
    if (!observation.StaticFloorUnderfoot && !observation.TransportFloorUnderfoot)
        observation.FloorNear = BotTransportSurfaceMovement::FloorNear(bot, ResnapFloorBandYards);
    observation.HealthPct = bot->GetMaxHealth()
        ? float(bot->GetHealth()) / float(bot->GetMaxHealth()) : 0.0f;
    if (approach.Mode == ApproachMode::SurfaceWalk)
    {
        observation.DistanceToApproachStart = distance(approach.StartPoint);
        // One straight walk across the platform's surface to the board point.
        observation.ApproachTravelMs = WalkTimeMs(observation.DistanceToBoard, runSpeed);
        observation.OffApproachCorridor = !OnApproachCorridor(approach.StartPoint,
            contract.BoardPoint, bot->GetPositionX(), bot->GetPositionY(), ApproachCorridorYards);
    }
    else if (approach.Mode == ApproachMode::LedgeDrop)
    {
        observation.DistanceToApproachStart = ApproachStartDistance(bot, approach);
        float const height = bot->GetPositionZ() - approach.LandingZ;
        observation.ApproachTravelMs = WalkTimeMs(bot->GetExactDist2d(approach.StepOffPoint.X,
            approach.StepOffPoint.Y), runSpeed) + NativeFallTimeMs(height);
        observation.PredictedFallDamagePct =
            BotTransportSurfaceMovement::PredictFallDamagePct(bot, height);
        observation.OffApproachCorridor = !OnApproachCorridor(approach.StartPoint,
            approach.StepOffPoint, bot->GetPositionX(), bot->GetPositionY(), ApproachCorridorYards,
            MaxStepOffYards + ApproachStartToleranceYards);
        observation.CohortAtApproachStart = !CohortBarrierHolder(
            ApproachMemberViews(input, runtime, transport.Object, contract));
    }
    // A movement generator waiting to resume with no spline would walk an
    // unchecked line once its stun or root ends.
    observation.MotionSuspended = bot->movespline->Finalized()
        && bot->HasUnitState(UNIT_STATE_ROAMING_MOVE);
    // The executor's own refusals for a member it does not control.
    observation.MemberNotFree = bot->HasUnitState(UNIT_STATE_NOT_MOVE)
        || bot->GetMotionMaster()->GetMotionSlot(MOTION_SLOT_CONTROLLED);

    // Without the platform's collision model neither boarding nor the
    // stranded-member check can be proven: stop instead of guessing.
    TransportDecision decision = transport.Object && !modelAvailable
        ? TransportDecision{ TransportStep::Fail, "transport_model_unavailable" }
        : DecideTransportStep(contract, observation, member);
    RecordOnChange(callbacks, member.LastReason,
        std::string("native_route_transport_") + TransportStepName(decision.Step)
            + ":" + decision.Reason,
        transport.Object, transport.Fact.PositionZ, contract.Entry);
    // Like a player watching the platform or feeling the landing, an armed or
    // in-flight approach observes again within ApproachFollowUpMs.
    if (ApproachWantsFollowUp(contract, decision, member))
        input.State->DecisionTimer = std::min<uint32>(input.State->DecisionTimer,
            ApproachFollowUpMs);

    ObjectGuid const transportGuid = transport.Object
        ? transport.Object->GetGUID() : ObjectGuid::Empty;
    // A refused submission counts at most once per SubmissionRejectionWindowMs
    // (CountRejectedSubmission); every counted one is recorded by reason.
    auto countRejection = [record = callbacks.Record, entry = contract.Entry,
        nowMs = input.NowMs](TransportMemberState& state, std::string const& reason)
    {
        if (CountRejectedSubmission(state, nowMs, reason) && record)
            record("native_route_transport_rejection_counted:" + reason, nullptr,
                float(state.FailedSubmissions), entry);
    };
    auto countSubmission = [runtimePtr = &runtime, scope = input.Scope, guid,
        fail = callbacks.Fail, countRejection](bool boarding)
    {
        return [runtimePtr, scope, guid, fail, countRejection, boarding](
            BotActionArbitration::Outcome const& outcome)
        {
            if (runtimePtr->Scope != scope)
                return;
            TransportMemberState& state = runtimePtr->TransportMembers[guid];
            if (outcome.Result == BotActionArbitration::Disposition::Committed)
                ++(boarding ? state.BoardSubmissions : state.LeaveSubmissions);
            else if (Retried(outcome))
                countRejection(state, outcome.Reason);
            if (outcome.Result == BotActionArbitration::Disposition::Unsafe
                && !runtimePtr->FailureRecorded)
            {
                runtimePtr->FailureRecorded = true;
                if (fail)
                    fail(outcome.Reason);
            }
        };
    };
    // Final approach submissions: an accepted one advances the member's
    // approach phase (and replaces its ordinary path); rejected ones count
    // toward MaxSubmissions like boarding; every new outcome is recorded.
    auto approachSubmission = [runtimePtr = &runtime, scope = input.Scope, guid,
        fail = callbacks.Fail, record = callbacks.Record, state = input.State,
        entry = contract.Entry, countRejection](TransportStep step)
    {
        return [runtimePtr, scope, guid, fail, record, state, entry, countRejection, step](
            BotActionArbitration::Outcome const& outcome)
        {
            if (runtimePtr->Scope != scope)
                return;
            TransportMemberState& member = runtimePtr->TransportMembers[guid];
            if (outcome.Result == BotActionArbitration::Disposition::Committed)
            {
                bool const completed = outcome.LifecyclePhase
                    == BotActionArbitration::Phase::Completed;
                // A landing without floor falls on (Progressed), uncounted.
                bool const fellAgain = step == TransportStep::DropLand
                    && outcome.LifecyclePhase == BotActionArbitration::Phase::Progressed;
                member.Approach = ApproachPhaseAfter(step, completed, fellAgain);
                ReleaseOrdinaryPath(*state,
                    fellAgain || (!completed && step != TransportStep::DropLand));
            }
            else if (Retried(outcome))
                countRejection(member, outcome.Reason);
            if (member.LastApproachOutcome != outcome.Reason)
            {
                member.LastApproachOutcome = outcome.Reason;
                if (record)
                    record("native_route_transport_approach_outcome:" + outcome.Reason,
                        nullptr, float(member.FailedSubmissions), entry);
            }
            if (outcome.Result == BotActionArbitration::Disposition::Unsafe
                && !runtimePtr->FailureRecorded)
            {
                runtimePtr->FailureRecorded = true;
                if (fail)
                    fail(outcome.Reason);
            }
        };
    };
    // Walks end at the board point on the platform's own surface, or at the
    // disembark point over static ground; drops step off at the step-off point.
    auto surfaceMove = [&contract, &approach, transportGuid](
        BotNativeAction::TransportSurfaceMove::Stage stage, bool disembark = false)
    {
        BotNativeAction::TransportSurfaceMove move;
        move.Transport = transportGuid;
        move.Kind = stage;
        Point3 const& target = disembark ? contract.DisembarkPoint
            : stage == BotNativeAction::TransportSurfaceMove::Stage::Walk
                ? contract.BoardPoint : approach.StepOffPoint;
        move.X = target.X;
        move.Y = target.Y;
        move.Z = target.Z;
        move.EndOnTransport = !disembark;
        move.FloorToleranceYards = contract.FloorToleranceYards;
        move.LandingZ = approach.LandingZ;
        move.LandingToleranceYards = approach.LandingToleranceYards;
        move.LandOnTransport = approach.LandOnTransport;
        move.MinHealthAfterFallPct = approach.MinHealthAfterFallPct;
        return move;
    };
    using SurfaceStage = BotNativeAction::TransportSurfaceMove::Stage;
    switch (decision.Step)
    {
        case TransportStep::Fail:
            // Exhaustion names the member and the executor's last refusal.
            FailOnce(runtime, callbacks, decision.Reason == "transport_submissions_exhausted"
                ? decision.Reason + ":" + member.LastRejection + ":" + std::to_string(guid)
                : decision.Reason);
            break;
        case TransportStep::Stop:
            SubmitStop(input, decision.Reason);
            break;
        case TransportStep::Hold:
        case TransportStep::HoldAboard:
        case TransportStep::Done:
        case TransportStep::Blocked:
            SubmitHold(input, decision.Reason, ApproachHoldOwnsCasting(decision));
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
                BotActionArbitration::Priority::Mechanic, TransportWindowUtility,
                BotNativeAction::Move{ contract.BoardPoint.X, contract.BoardPoint.Y,
                    contract.BoardPoint.Z, "native_transport_board_path" },
                "native_route_transport_board_path");
            break;
        case TransportStep::Board:
            Submit(input, callbacks, "transport_board", transportGuid,
                BotActionArbitration::Priority::Mechanic, TransportWindowUtility,
                BotNativeAction::TransportBoard{ transportGuid, contract.FloorToleranceYards },
                "native_route_transport_board", countSubmission(true));
            break;
        case TransportStep::MoveToDisembark:
            Submit(input, callbacks, "transport_disembark_path", transportGuid,
                BotActionArbitration::Priority::Mechanic, TransportWindowUtility,
                BotNativeAction::Move{ contract.DisembarkPoint.X,
                    contract.DisembarkPoint.Y, contract.DisembarkPoint.Z,
                    "native_transport_disembark_path" },
                "native_route_transport_disembark_path");
            break;
        case TransportStep::Leave:
            Submit(input, callbacks, "transport_leave", transportGuid,
                BotActionArbitration::Priority::Mechanic, TransportWindowUtility,
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
        case TransportStep::MoveToApproachStart:
            Submit(input, callbacks, "transport_approach_start", transportGuid,
                BotActionArbitration::Priority::Mechanic, 4.0f,
                BotNativeAction::Move{ approach.StartPoint.X, approach.StartPoint.Y,
                    approach.StartPoint.Z, "native_transport_approach_start" },
                "native_route_transport_approach_start");
            break;
        case TransportStep::SurfaceWalk:
            Submit(input, callbacks, "transport_surface_walk", transportGuid,
                BotActionArbitration::Priority::Mechanic, TransportWindowUtility,
                surfaceMove(SurfaceStage::Walk), "native_route_transport_surface_walk",
                approachSubmission(decision.Step));
            break;
        case TransportStep::DropStepOff:
            Submit(input, callbacks, "transport_drop_step_off", transportGuid,
                BotActionArbitration::Priority::Mechanic, TransportWindowUtility,
                surfaceMove(SurfaceStage::StepOff), "native_route_transport_drop_step_off",
                approachSubmission(decision.Step));
            break;
        case TransportStep::DropFall:
            Submit(input, callbacks, "transport_drop_fall", transportGuid,
                TransportFallPriority, TransportFallUtility,
                surfaceMove(SurfaceStage::Fall), "native_route_transport_drop_fall",
                approachSubmission(decision.Step));
            break;
        case TransportStep::DropLand:
            Submit(input, callbacks, "transport_drop_land", transportGuid,
                TransportFallPriority, TransportFallUtility,
                surfaceMove(SurfaceStage::Land), "native_route_transport_drop_land",
                approachSubmission(decision.Step));
            break;
        case TransportStep::DisembarkWalk:
            Submit(input, callbacks, "transport_disembark_walk", transportGuid,
                BotActionArbitration::Priority::Mechanic, TransportWindowUtility,
                surfaceMove(SurfaceStage::Walk, true), "native_route_transport_disembark_walk",
                approachSubmission(decision.Step));
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
void RefreshVerdict(Input const& input, Callbacks const& callbacks, NodeContract& node,
    OwnerElection const& election, Player* evaluator)
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
    // The completion override is a fail-fast guard, never an early
    // completion: once an observed boss state holds (the encounter engaged)
    // with a member aboard, a member neither aboard nor in flight fails the
    // node after a grace instead of waiting out its timeout.
    if (!satisfied && evaluator && node.Transport.Declared
        && node.Transport.CompletionOverride.Declared)
    {
        Verdict const early = Facts::EvaluateCompletion(node.Transport.CompletionOverride,
            evaluator, input.Members, election.Owner, runtime.Completion);
        Facts::TransportTarget const transport = Facts::ResolveTransport(evaluator,
            node.Transport.Entry, node.Transport.SpawnId);
        if (!transport.Object)
        {
            // No platform to be aboard: report it as it is, never as members.
            runtime.OverrideSatisfiedAtMs = 0;
            if (early.Satisfied)
                reason = transport.Fact.Ambiguous ? "transport_ambiguous" : "transport_missing";
        }
        else
        {
            OverrideGuardDecision const guard = DecideOverrideGuard(
                ApproachMemberViews(input, runtime, transport.Object, node.Transport),
                early.Satisfied, runtime.OverrideSatisfiedAtMs, input.NowMs);
            if (guard.Step == OverrideGuardStep::Wait)
                reason = guard.Reason;
            else if (guard.Step == OverrideGuardStep::Fail)
                FailOnce(runtime, callbacks,
                    guard.Reason + ":" + std::to_string(guard.Member));
        }
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

    NodeContract& node = *input.Node;
    // A recovery ride or wake owns the node while it runs; a node without
    // contracts of its own is otherwise left to the ordinary route adapters.
    if (!node.Recovery.empty() || !node.RecoveryInteractions.empty())
    {
        RecoveryOps ops;
        ops.Ride = [](Input const& riders, Callbacks const& ridden, TransportContract const& ride,
            NodeRuntime& rideRuntime, Facts::TransportTarget const& platform)
        {
            RunTransport(riders, ridden, ride, rideRuntime, platform);
        };
        ops.Hold = [&input](std::string const& reason) { SubmitHold(input, reason); };
        ops.Elect = [&input](InteractionContract const& wake)
        { return ElectOwner(wake, MemberViews(input)); };
        ops.Interact = [&input](Callbacks const& woken, InteractionContract const& wake,
            NodeRuntime& wakeRuntime, OwnerElection const& election)
        {
            RunInteraction(input, woken, wake, wakeRuntime, election);
        };
        if (RunRecovery(input, callbacks, node, ops))
        {
            result.OwnsNode = true;
            return result;
        }
    }
    if (!node.Interaction.Declared && !node.Completion.Declared && !node.Transport.Declared)
        return result;
    result.OwnsNode = true;
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

    RefreshVerdict(input, callbacks, node, election, evaluator);
    if (runtime.FailureRecorded)
        return result;
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
            RunTransport(input, callbacks, node.Transport, runtime,
                Facts::ResolveTransport(input.Bot, node.Transport.Entry, node.Transport.SpawnId));
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
        // Name the member a ledge drop's cohort barrier is still waiting for
        // (only against a resolved platform: without one nobody is aboard).
        std::uint64_t holder = 0;
        if (node.Transport.Approach.Mode == ApproachMode::LedgeDrop)
            if (GameObject const* platform = Facts::ResolveTransport(input.Bot,
                    node.Transport.Entry, node.Transport.SpawnId).Object)
                holder = CohortBarrierHolder(ApproachMemberViews(input, runtime, platform,
                    node.Transport));
        FailOnce(runtime, callbacks, holder
            ? "native_transport_timeout:waiting_for_cohort:" + std::to_string(holder)
            : std::string("native_transport_timeout"));
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
        RunTransport(input, callbacks, node.Transport, runtime,
            Facts::ResolveTransport(input.Bot, node.Transport.Entry, node.Transport.SpawnId));
    if (node.Interaction.Declared && !runtime.FailureRecorded)
        RunInteraction(input, callbacks, node.Interaction, runtime, election);
    return result;
}
}
