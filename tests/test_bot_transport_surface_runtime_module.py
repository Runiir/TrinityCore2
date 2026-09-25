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
    # Proof first: floor samples on the straight segment, line of sight at
    # three heights, the platform staying put; then one straight point spline.
    assert walk.index("ValidateSurfaceWalk(") < walk.index("TransportStationaryMs(transport)") \
        < walk.index("MovePoint(0, to.x, to.y, to.z, false)")
    assert "PointSplineLaunched(bot, to)" in walk
    probe = _function(executor, "SegmentProbe ProbeSegment(")
    assert "GetStaticHeight(" in _function(executor, "bool StaticFloorAt(")
    assert "transport->m_model->intersectRay(" in _function(executor, "bool TransportFloorAt(")
    assert "LINEOFSIGHT_ALL_CHECKS, VMAP::ModelIgnoreFlags::Nothing" in probe
    assert "0.3f * height), 0.6f * height, 0.9f * height" in probe

    step = _function(executor, "Outcome ExecuteStepOff(")
    # The lip, landing, liquid and health are proven before the standing
    # report (Player::m_lastFallZ) and only then does the level step start.
    assert step.index("ValidateLedgeDrop(") < step.index("ReportStandingPosition(bot)") \
        < step.index("MovePoint(0, chosen.x, chosen.y, chosen.z, false)")
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

    fall = _function(executor, "Outcome ExecuteFall(")
    assert "bot->GetMotionMaster()->MoveFall();" in fall
    assert "MOTION_SLOT_CONTROLLED) == EFFECT_MOTION_TYPE" in fall
    land = _function(executor, "Outcome ExecuteLand(")
    assert land.index("NativeFallLandingPending(bot)") < land.index("ReportFallLanding(")
    assert "native_ledge_drop_land_no_floor" in land
    # Gravity never waits for the transport: Fall resolves no transport.
    execute = _function(executor, "BotActionArbitration::Outcome Execute(")
    assert execute.index("Stage::Fall)\n        return ExecuteFall(bot);") < execute.index("ResolveTransport(")

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
        "MoveSplineInit", "HandleMovementOpcode(",
    ):
        assert forbidden not in executor, forbidden


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
    assert "!bot->movespline->Finalized()\n        && bot->movespline->isFalling()" in boarding
    board = _function(boarding, "BotActionArbitration::Outcome BoardTransport(")
    assert "NativeFallInProgress(bot)" in board and "IsFalling()" not in board
    assert "->GetMotionMaster(" not in boarding


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
    assert "return [runtimePtr, scope, guid, fail, record, state, entry, step](" in observer
    assert "member.Approach = ApproachPhaseAfter(step, completed);" in observer
    assert "++member.FailedSubmissions;" in observer
    assert "runtimePtr->FailureRecorded = true;" in observer
    assert "ReleaseOrdinaryPath(*state, " in observer
    for forbidden in ("TeleportTo(", "NearTeleportTo(", "Relocate(", "UpdatePosition(",
                      "MoveFall(", "MovePoint(", "SetFall(", "HandleMovementOpcode("):
        assert forbidden not in runtime, forbidden


def test_intent_and_dispatch_wiring_patch_applied() -> None:
    """Gate for patch requests P1 (BotNativeActionIntent.h) and P2
    (BotWorldPopulationMgrNativeAction.cpp); fails until the coordinator
    applies them, and the new executor does not compile without P1."""
    intents = _source("BotNativeActionIntent.h")
    native = _source("BotWorldPopulationMgrNativeAction.cpp")
    assert "struct TransportSurfaceMove\n{\n    enum class Stage : uint8 { Walk, StepOff, Fall, Land };" in intents
    assert "TransportBoard, TransportLeave, TransportSurfaceMove>;" in intents
    assert "|| std::is_same_v<T, TransportSurfaceMove>)\n            return Uses(Resource::Movement);" in intents
    assert '#include "Bots/BotWorldPopulationMgrNativePathTransportSurface.h"' in native
    assert "std::is_same_v<T, BotNativeAction::TransportSurfaceMove>)\n        {\n            return BotTransportSurfaceMovement::Execute(bot, action);" in native
    cmake = (ROOT / "src/server/game/CMakeLists.txt").read_text(encoding="utf-8")
    assert "Bots/BotWorldPopulationMgrNativePathTransportSurface.cpp" in cmake
