"""Source contracts for the transport-surface approach runtime and executor.

The decision logic is exercised by tests/test_bot_transport_surface_approach.py;
these checks pin the server wiring: which native calls each stage may make,
their order, the explicit captures of deferred observers, and the absence of
any relocation, height write, flag write or invented damage.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"

OWNED = (
    "BotValidationRouteNativeApproach.h",
    "BotValidationRouteNativeTransportLogic.h",
    "BotValidationRouteNativeLogic.h",
    "BotValidationRouteNativeContract.h",
    "BotValidationRouteNativeTypes.h",
    "BotWorldPopulationMgrNativePathTransportSurface.h",
    "BotWorldPopulationMgrNativePathTransportSurface.cpp",
    "BotWorldPopulationMgrValidationRouteBoardingAction.h",
    "BotWorldPopulationMgrValidationRouteBoardingAction.cpp",
    "BotWorldPopulationMgrValidationRouteNativeRuntime.cpp",
)


def _source(name: str) -> str:
    return (BOTS / name).read_text(encoding="utf-8")


def _code(text: str) -> str:
    text = re.sub(r"//.*", "", text)
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _function(text: str, signature: str) -> str:
    start = text.index(signature)
    depth = 0
    for index in range(text.index("{", start), len(text)):
        depth += {"{": 1, "}": -1}.get(text[index], 0)
        if depth == 0:
            return text[start:index + 1]
    raise AssertionError(signature)


def test_modules_stay_below_the_size_limit_and_pure_headers_stay_pure() -> None:
    for name in OWNED:
        assert len(_source(name).splitlines()) < 1000, name
    for pure in ("BotValidationRouteNativeApproach.h", "BotValidationRouteNativeTransportLogic.h"):
        includes = re.findall(r'#include [<"]([^>"]+)[>"]', _source(pure))
        assert all(name.startswith("Bots/BotValidationRouteNative") or "/" not in name
                   and not name.endswith(".h") for name in includes), (pure, includes)
    # RouteState.h (about 180 TUs) still sees only the data-only types.
    route_state = _source("BotWorldPopulationMgrRouteState.h")
    for heavy in ("BotValidationRouteNativeApproach.h", "BotValidationRouteNativeTransportLogic.h",
                  "BotWorldPopulationMgrNativePathTransportSurface.h"):
        assert heavy not in route_state


def test_executor_launches_only_native_movement_after_its_proofs() -> None:
    executor = _code(_source("BotWorldPopulationMgrNativePathTransportSurface.cpp"))
    walk = _function(executor, "Outcome ExecuteWalk(")
    # Proof first: floor samples on the straight segment, the body's sweep,
    # the platform staying put; then one checked straight line.
    assert walk.index("ValidateSurfaceWalk(") < walk.index("TransportStationaryMs(transport)") \
        < walk.index("LaunchCheckedLine(bot, to);")
    assert "PointSplineLaunched(bot, to)" in walk
    # A new walk may replace a running one (checked from where the member is
    # now), never one queued under a controlled effect, a fall or a root.
    assert "native_surface_walk_moving" not in walk
    assert "GetMotionSlot(MOTION_SLOT_CONTROLLED)" in walk
    assert '"native_surface_walk_controlled_motion"' in walk
    assert "bot->GetTransport() != nullptr);" in walk
    # Review blocker: the checked line runs in a generator that ends when its
    # spline is stopped or replaced (GenericMovementGenerator), never in the
    # resumable PointMovementGenerator (MotionMaster::MovePoint).
    line = _function(executor, "void LaunchCheckedLine(")
    assert "init.MoveTo(destination.x, destination.y, destination.z, false);" in line
    assert "LaunchMoveSpline(std::move(init), 0, MOTION_SLOT_ACTIVE,\n        POINT_MOTION_TYPE);" in line
    assert "MovePoint(" not in executor
    probe = _function(executor, "SegmentProbe ProbeSegment(")
    assert "GetStaticHeight(" in _function(executor, "bool StaticFloorAt(")
    assert "transport->m_model->intersectRay(" in _function(executor, "bool TransportFloorAt(")
    assert "probe.CollisionFree = BodySweepClear(bot, from, to);" in probe
    sweep = _function(executor, "bool BodySweepClear(")
    assert "Route::BodySweepLifts(bot->GetCollisionHeight())" in sweep
    assert "for (float const side : Route::BodySweepSideFractions)" in sweep
    assert "LINEOFSIGHT_ALL_CHECKS, VMAP::ModelIgnoreFlags::Nothing" in sweep

    step = _function(executor, "Outcome ExecuteStepOff(")
    # The lip, landing, liquid and health are proven before the standing
    # report (Player::m_lastFallZ) and only then does the level step start.
    assert step.index("ValidateLedgeDrop(") < step.index("ReportStandingPosition(bot)") \
        < step.index("LaunchCheckedLine(bot, chosen);")
    assert '"native_ledge_drop_position_report_not_applied"' in step
    assert "StepOffCandidateAdvances(verdict.Reason)" in step
    # A passenger may drop only from this transport (a pillar top) and the
    # platform keeps still for the step, the native fall and the boarding.
    assert '"native_ledge_drop_on_other_transport"' in step
    assert step.index("ValidateLedgeDrop(") < step.index("TransportStationaryMs(transport)") \
        < step.index("ReportStandingPosition(bot)")
    assert "Route::NativeFallTimeMs(fromZ - action.LandingZ)" in step
    # First footprint-clear point along the declared heading, level at the
    # member's own feet (no height is chosen for it).
    assert "G3D::Vector3 const candidate(fromX + headingX * step, fromY + headingY * step, fromZ);" in step
    assert "step <= Route::MaxStepOffYards + 1e-3f" in step
    drop = _function(executor, "Route::LedgeDropProbe ProbeLedgeDrop(")
    # Exactly MoveFall's landing query: WorldObject::GetMapHeight with
    # MAX_FALL_DISTANCE from the step-off point.
    assert "bot->GetMapHeight(stepOff.x, stepOff.y, stepOff.z, true,\n        MAX_FALL_DISTANCE)" in drop
    assert "IsInWater(phase, stepOff.x, stepOff.y, landing + 0.1f)" in drop
    assert "PredictFallDamagePct(bot,\n            from.z - landing)" in drop
    # A sloped lip is flagged under every unsupported sample; a static
    # landing is static ground within tolerance of the landing height.
    assert "probe.Step[i].ShallowFloorBelow = below > INVALID_HEIGHT" in drop
    assert "probe.LandingOnStatic = staticFloor > INVALID_HEIGHT\n            && std::fabs(staticFloor - landing) <= tolerance;" in drop

    fall = _function(executor, "Outcome ExecuteFall(")
    # Nothing may resume a line through the air after the fall, and the fall
    # origin is reported right before MoveFall (also without a step-off).
    assert fall.index("Clear(MOTION_SLOT_ACTIVE)") < fall.index("ReportStandingPosition(bot)") \
        < fall.index("LaunchNativeFall(bot, false)")
    assert '"native_ledge_drop_fall_waiting_for_motion"' in fall
    launch = _function(executor, "Outcome LaunchNativeFall(")
    assert "bot->GetMotionMaster()->MoveFall();" in launch
    assert "MOTION_SLOT_CONTROLLED) == EFFECT_MOTION_TYPE" in launch
    # A root holds the member where it is: not a counted rejection.
    assert 'Outcome::NotApplicable("native_ledge_drop_fall_held_by_root")' in launch
    assert 'Outcome::Progressed("native_ledge_drop_fell_again")' in launch
    land = _function(executor, "Outcome ExecuteLand(")
    assert land.index("NativeFallLandingPending(bot)") < land.index("ReportFallLanding(")
    # No floor under the feet: fall on (uncounted); report only onto a floor.
    assert land.index("return LaunchNativeFall(bot, true);") < land.index("ReportFallLanding(")
    assert "native_ledge_drop_land_no_floor" not in land
    # After the report a zero-length turn replaces the finished fall spline,
    # so Unit::IsFalling() reads the landed member as grounded.
    assert land.index("ReportFallLanding(") < land.index("SettleAfterLanding(bot);")
    settle = _function(executor, "void SettleAfterLanding(")
    assert "init.MoveTo(bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), false);" in settle
    assert "init.SetFacing(bot->GetOrientation());" in settle
    assert "DisableTransportPathTransformations" not in settle
    # Finalized at once (a finished stop spline), so MOVEMENTFLAG_FORWARD
    # clears before the next observation.
    assert settle.index("init.Launch();") < settle.index("bot->StopMoving();")
    # Gravity never waits for the transport: Fall resolves no transport.
    execute = _function(executor, "BotActionArbitration::Outcome Execute(")
    assert execute.index("Stage::Fall)\n        return ExecuteFall(bot);") < execute.index("ResolveTransport(")
    # Walks and step-offs only on a platform that moves vertically.
    assert '"native_surface_move_transport_not_vertical"' in execute

    # Native fall damage rules as Player::HandleFall applies them.
    predict = _function(executor, "float PredictFallDamagePct(")
    for marker in ("SPELL_AURA_HOVER", "SPELL_AURA_FEATHER_FALL", "SPELL_AURA_FLY",
                   "IsImmunedToDamage(SPELL_SCHOOL_MASK_NORMAL)", "SPELL_AURA_SAFE_FALL",
                   "RATE_DAMAGE_FALL"):
        assert marker in predict, marker

    for forbidden in (
        "TeleportTo(", "NearTeleportTo(", "Relocate(", "UpdatePosition(", "SetFall(",
        "SetFallInformation(", "AddPassenger(", "SetTransport(", "SetDisableGravity(",
        "SetCanFly(", "SetHover(", "EnvironmentalDamage(", "HandleFall(", "SetHealth(",
        "ModifyHealth(", "DealDamage(", "MoveJump", "MoveKnockback", "UpdateGroundPositionZ",
        "UpdateAllowedPositionZ", "RemoveUnitMovementFlag(", "AddUnitMovementFlag(",
        "HandleMovementOpcode(", "SetFacingTo(", "SetFallInformation", "m_lastFallZ",
        "IsInCombat(",
    ):
        assert forbidden not in executor, forbidden
    # Exactly two splines are built here: the checked line and the landing turn.
    assert executor.count("Movement::MoveSplineInit init(bot);") == 2


def test_boarding_reports_are_client_packets_at_the_current_position() -> None:
    boarding = _code(_source("BotWorldPopulationMgrValidationRouteBoardingAction.cpp"))
    standing = _function(boarding, "bool ReportStandingPosition(")
    assert "HandleMovementOpcode(MSG_MOVE_HEARTBEAT, report)" in standing
    assert "report.jump.fallTime = 0;" in standing
    landing = _function(boarding, "bool ReportFallLanding(")
    assert "HandleMovementOpcode(MSG_MOVE_FALL_LAND, report)" in landing
    for report in (standing, landing):
        assert "MovementInfo report = CurrentStandingReport(bot);" in report
        assert "EnsureActiveMover(bot)" in report
    # A passenger's report keeps its own transport block: no board, no leave.
    keep = _function(boarding, "static MovementInfo CurrentStandingReport(")
    assert "MovementInfo info = CurrentPositionReport(bot);" in keep
    assert "info.transport = bot->m_movementInfo.transport;" in keep
    # A finalized fall spline keeps isFalling(); it is not a fall.
    assert "BotValidationRouteNativeFall::SplineActive(*bot->movespline)" in boarding
    fall = _source("BotValidationRouteNativeFallSpline.h")
    assert "return spline.Initialized() && !spline.Finalized() && spline.isFalling();" in fall
    board = _function(boarding, "BotActionArbitration::Outcome BoardTransport(")
    assert "NativeFallInProgress(bot)" in board and "IsFalling()" not in board
    assert "->GetMotionMaster(" not in boarding
    # The handler returns silently in several cases: a report counts only
    # when the mover's movement info now carries it.
    applied = _function(boarding, "static bool ReportApplied(")
    for marker in ("now.time == report.time", "!now.HasMovementFlag(MOVEMENTFLAG_MASK_MOVING)",
                   "now.transport.guid == report.transport.guid",
                   "now.pos.GetExactDist(&report.pos) < 0.01f"):
        assert marker in applied, marker
    for report in (standing, landing):
        assert "return ReportApplied(bot, report);" in report
    # Stationarity from height keys only when the animation never moves
    # sideways or turns.
    vertical = _function(boarding, "bool TransportAnimatesOnlyVertically(")
    assert "animation->Path" in vertical and "animation->Rotations" in vertical
    stationary = _function(boarding, "std::uint64_t TransportStationaryMs(")
    assert "if (!TransportAnimatesOnlyVertically(transport))\n        return 0;" in stationary


def test_runtime_submits_typed_approach_intents_with_bounded_observers() -> None:
    runtime = _code(_source("BotWorldPopulationMgrValidationRouteNativeRuntime.cpp"))
    transport = _function(runtime, "void RunTransport(")
    for stage, label in (
        ("Walk", "native_route_transport_surface_walk"),
        ("StepOff", "native_route_transport_drop_step_off"),
        ("Fall", "native_route_transport_drop_fall"),
        ("Land", "native_route_transport_drop_land"),
    ):
        assert f'surfaceMove(SurfaceStage::{stage}), "{label}",\n                approachSubmission(decision.Step));' in transport
    # The passenger's disembark walk ends over static ground, not on the car.
    assert 'surfaceMove(SurfaceStage::Walk, true), "native_route_transport_disembark_walk",\n                approachSubmission(decision.Step));' in transport
    assert "Point3 const& target = disembark ? contract.DisembarkPoint" in transport
    assert "move.EndOnTransport = !disembark;" in transport
    assert '"native_transport_approach_start" }' in transport
    # Observations the decision needs; the approach replaces the path-length
    # estimate (no PathGenerator for the off-navmesh board point).
    for marker in (
        "observation.FallSplineActive = BotValidationRouteBoardingAction::NativeFallSplineActive(bot);",
        "observation.LandingPending = BotValidationRouteBoardingAction::NativeFallLandingPending(bot);",
        "observation.FloorNear = BotTransportSurfaceMovement::FloorNear(bot, ResnapFloorBandYards);",
        "BotTransportSurfaceMovement::PredictFallDamagePct(bot, height);",
        "&& approach.Mode == ApproachMode::None)",
    ):
        assert marker in transport, marker
    # Follow-up cadence only for approaches (pure predicate decides).
    assert "if (ApproachWantsFollowUp(contract, decision, member))\n        input.State->DecisionTimer = std::min<uint32>(input.State->DecisionTimer,\n            ApproachFollowUpMs);" in transport
    # The deferred observer captures explicitly (no blanket capture), counts
    # rejections toward MaxSubmissions and fails the node once on Unsafe.
    observer = transport[transport.index("auto approachSubmission"):transport.index("auto surfaceMove")]
    assert "[&]" not in observer and "[=]" not in observer
    assert "return [runtimePtr, scope, guid, fail, record, state, entry, countRejection, step](" in observer
    assert "member.Approach = ApproachPhaseAfter(step, completed, fellAgain);" in observer
    assert "&& outcome.LifecyclePhase == BotActionArbitration::Phase::Progressed;" in observer
    assert "countRejection(member, outcome.Reason);" in observer
    assert "runtimePtr->FailureRecorded = true;" in observer
    assert "ReleaseOrdinaryPath(*state,\n                    fellAgain || (!completed && step != TransportStep::DropLand));" in observer
    for forbidden in ("TeleportTo(", "NearTeleportTo(", "Relocate(", "UpdatePosition(",
                      "MoveFall(", "MovePoint(", "SetFall(", "HandleMovementOpcode("):
        assert forbidden not in runtime, forbidden
    # Supervision of a walk or step in flight and the drop's cohort barrier.
    for marker in (
        "observation.MotionSuspended = bot->movespline->Finalized()\n        && bot->HasUnitState(UNIT_STATE_ROAMING_MOVE);",
        "observation.OffApproachCorridor = !OnApproachCorridor(approach.StartPoint,\n            contract.BoardPoint,",
        "observation.CohortAtApproachStart = !CohortBarrierHolder(\n            ApproachMemberViews(input, runtime, transport.Object, contract));",
    ):
        assert marker in transport, marker


def test_completion_override_is_a_fail_fast_guard_never_an_early_completion() -> None:
    runtime = _code(_source("BotWorldPopulationMgrValidationRouteNativeRuntime.cpp"))
    verdict = _function(runtime, "void RefreshVerdict(")
    assert "node.Transport.CompletionOverride.Declared)" in verdict
    assert "Facts::EvaluateCompletion(node.Transport.CompletionOverride," in verdict
    assert verdict.index("TransportNodeDone(") < verdict.index("node.Transport.CompletionOverride.Declared")
    guard = verdict[verdict.index("node.Transport.CompletionOverride.Declared"):]
    # The pure guard (replayed in the approach tests) decides; it never sets
    # the node satisfied, and a member left behind past the grace fails the
    # node typed, with its GUID.
    assert "satisfied = true" not in guard
    assert "OverrideGuardDecision const guard = DecideOverrideGuard(" in guard
    assert "early.Satisfied, runtime.OverrideSatisfiedAtMs, input.NowMs);" in guard
    assert "FailOnce(runtime, callbacks,\n                    guard.Reason + \":\" + std::to_string(guard.Member));" in guard
    # No platform resolved: report the transport, never the members.
    assert "if (!transport.Object)" in guard
    assert 'reason = transport.Fact.Ambiguous ? "transport_ambiguous" : "transport_missing";' in guard
    assert "runtime.OverrideSatisfiedAtMs = 0;" in guard
    views = _function(runtime, "std::vector<ApproachMemberView> ApproachMemberViews(")
    for marker in ("view.Aboard = Facts::OnTransport(bot, transport);",
                   "view.Falling = BotValidationRouteBoardingAction::NativeFallInProgress(bot);",
                   "view.OnRouteInstance = member.OnRouteInstance && bot->IsInWorld();",
                   "BotTransportSurfaceMovement::PredictFallDamagePct(bot,",
                   # (c) the barrier's start test includes the edge-floor proof.
                   "view.AtStart = approach.StartPoint.Valid && AtApproachStart(",
                   "BotValidationRouteBoardingAction::StaticFloorUnderfoot(bot,\n                contract.FloorToleranceYards));"):
        assert marker in views, marker
    run = _function(runtime, "Result Run(")
    assert "RefreshVerdict(input, callbacks, node, election, evaluator);\n    if (runtime.FailureRecorded)\n        return result;" in run
    # A timed-out ledge drop names the member its cohort barrier waits for,
    # judged only against a resolved platform.
    assert '"native_transport_timeout:waiting_for_cohort:" + std::to_string(holder)' in run
    assert "if (GameObject const* platform = Facts::ResolveTransport(input.Bot," in run


def test_nothing_in_the_approach_path_refuses_or_aborts_in_combat() -> None:
    """DoZoneInCombat puts every player in the map in combat when Onyxia's
    start-fight pulse hits: the descent, drop, boarding and handover run in
    combat, so none of them may test combat state."""
    runtime = _code(_source("BotWorldPopulationMgrValidationRouteNativeRuntime.cpp"))
    for name in ("void RunTransport(", "std::vector<ApproachMemberView> ApproachMemberViews(",
                 "bool TransportNodeDone(", "void RefreshVerdict("):
        assert "Combat" not in _function(runtime, name), name
    for source in ("BotWorldPopulationMgrNativePathTransportSurface.cpp",
                   "BotValidationRouteNativeTransportLogic.h", "BotValidationRouteNativeApproach.h"):
        assert "Combat" not in _code(_source(source)), source
    boarding = _code(_source("BotWorldPopulationMgrValidationRouteBoardingAction.cpp"))
    for name in ("BotActionArbitration::Outcome BoardTransport(",
                 "BotActionArbitration::Outcome LeaveTransport("):
        assert "Combat" not in _function(boarding, name), name


def test_intent_and_dispatch_wiring_patch_applied() -> None:
    """Gate for patch requests P1 (BotNativeActionIntent.h) and P2
    (BotWorldPopulationMgrNativeAction.cpp); fails until the coordinator
    applies them, and the new executor does not compile without P1."""
    intents = _source("BotNativeActionIntent.h")
    native = _source("BotWorldPopulationMgrNativeAction.cpp")
    assert "struct TransportSurfaceMove\n{\n    enum class Stage : uint8 { Walk, StepOff, Fall, Land };" in intents
    assert "TransportBoard, TransportLeave, TransportSurfaceMove>;" in intents
    # Every stage claims the cast lanes (round 3): Walk and StepOff abandon a
    # movement-preventing cast, and no cast-time spell may stop a fall.
    resources = intents[intents.index("if constexpr (std::is_same_v<T, TransportSurfaceMove>)"):]
    resources = resources[:resources.index("if constexpr (std::is_same_v<T, CombatResApproach>)")]
    assert "return Uses(Resource::Movement, Resource::GlobalCooldown, Resource::Cast);" in resources
    assert '#include "Bots/BotWorldPopulationMgrNativePathTransportSurface.h"' in native
    assert "std::is_same_v<T, BotNativeAction::TransportSurfaceMove>)\n        {\n            return BotTransportSurfaceMovement::Execute(bot, action);" in native
    cmake = (ROOT / "src/server/game/CMakeLists.txt").read_text(encoding="utf-8")
    assert "Bots/BotWorldPopulationMgrNativePathTransportSurface.cpp" in cmake


def test_round3_in_flight_approach_owns_casting_and_names_its_refusals() -> None:
    # Round 2 live evidence (blackwing_descent_10n_nefarian_c0): the holy
    # paladin's own heal (TryCastFriendlySpell stops movement before a
    # cast-time spell) cut its step off the lip 0.42 yd short; the member
    # re-walked to the start, and five refused step-offs within about a
    # second exhausted the node with no reason in the failure.
    runtime = _code(_source("BotWorldPopulationMgrValidationRouteNativeRuntime.cpp"))
    transport = runtime[runtime.index("void RunTransport("):runtime.index("bool TransportNodeDone(")]
    # A walk, step or fall in flight also owns the cast lanes, ahead of heals.
    hold = runtime[runtime.index("void SubmitHold("):runtime.index("void ReleaseOrdinaryPath(")]
    assert "candidate.UtilityScore = ownsCasting ? 6.0f : 1.0f;" in hold
    assert "BotActionArbitration::Resource::GlobalCooldown, BotActionArbitration::Resource::Cast)" in hold
    assert "SubmitHold(input, decision.Reason, ApproachHoldOwnsCasting(decision));" in transport
    intent = _code(_source("BotNativeActionIntent.h"))
    surface = intent[intent.index("if constexpr (std::is_same_v<T, TransportSurfaceMove>)"):]
    surface = surface[:surface.index("if constexpr (std::is_same_v<T, CombatResApproach>)")]
    assert "return Uses(Resource::Movement, Resource::GlobalCooldown, Resource::Cast);" in surface
    assert "Stage::Fall" not in surface and "Stage::Land" not in surface
    # Refusals count at most once per window, each counted one is recorded,
    # and exhaustion names the last refusal and the member.
    assert "if (CountRejectedSubmission(state, nowMs, reason) && record)" in transport
    assert '"native_route_transport_rejection_counted:" + reason' in transport
    assert "countRejection(state, outcome.Reason);" in transport
    assert "countRejection(member, outcome.Reason);" in transport
    assert "++state.FailedSubmissions;" not in transport and "++member.FailedSubmissions;" not in transport
    assert '? decision.Reason + ":" + member.LastRejection + ":" + std::to_string(guid)' in transport
    # The executor's refusals for a member it does not control are observed.
    assert "observation.MemberNotFree = bot->HasUnitState(UNIT_STATE_NOT_MOVE)\n        || bot->GetMotionMaster()->GetMotionSlot(MOTION_SLOT_CONTROLLED);" in transport
    # A step cut short on the lip is at the approach start: the observation
    # and the cohort barrier measure from the same declared line.
    assert "return DistanceToApproachLine(approach.StartPoint, approach.StepOffPoint," in runtime
    assert "observation.DistanceToApproachStart = ApproachStartDistance(bot, approach);" in transport
    views = runtime[runtime.index("std::vector<ApproachMemberView> ApproachMemberViews("):runtime.index("void RunTransport(")]
    assert "ApproachStartDistance(bot, approach), startTolerance," in views
    # A fall stopped mid-air is still a landing owed: the landing step falls
    # on from there (fall origin unchanged) or reports it.
    boarding = _code(_source("BotWorldPopulationMgrValidationRouteBoardingAction.cpp"))
    pending = boarding[boarding.index("bool NativeFallLandingPending("):]
    pending = pending[:pending.index("}") + 1]
    # A stop mid-air clears the spline (not Initialized): still owed.
    assert "BotValidationRouteNativeFall::LandingPending(" in pending
    assert "return fallingFlags && (!spline.Initialized() || spline.Finalized());" in _source(
        "BotValidationRouteNativeFallSpline.h")
    assert "isFalling()" not in pending
