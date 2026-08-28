from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FALLBACK = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelFallback.cpp"


def _route_kernel(source: str) -> str:
    start = source.index(
        "void BotWorldPopulationMgr::SubmitValidationKernelFallbackCandidates("
    )
    return source[start:]


def test_rejected_route_actions_stay_out_of_the_cast_lane() -> None:
    kernel = _route_kernel(FALLBACK.read_text(encoding="utf-8"))
    classifier_start = kernel.index("auto routeActionIsMovementOnly")
    classifier_end = kernel.index("auto runRoute", classifier_start)
    classifier = kernel[classifier_start:classifier_end]

    assert 'action.find("rejected") != std::string::npos' in classifier
    assert 'action == "drudge_entrance_native_path_no_progress"' in classifier
    assert 'action == "drudge_entrance_native_path_retained"' in classifier

    route_start = kernel.index('routeAction.Key = "world.validation_route_action"')
    movement_start = kernel.index(
        'routeMovement.Key = "world.validation_route_movement"', route_start
    )
    route_action = kernel[route_start:movement_start]
    assert "routeAttempt->ActionSubmitted" in route_action
    assert '"route_movement_only"' in route_action

    run_route = kernel[kernel.index("auto runRoute"):route_start]
    assert "routeActionIsMovementOnly(context.Action)" in run_route
    assert "routeAttempt->MovementSubmitted" in run_route


def test_retained_native_paths_keep_movement_ownership_without_a_new_path_stamp() -> None:
    kernel = _route_kernel(FALLBACK.read_text(encoding="utf-8"))
    retained_start = kernel.index("// MotionMaster paths are set-and-forget.")
    retained_end = kernel.index("routeAttempt->CombatAttempted", retained_start)
    retained = kernel[retained_start:retained_end]

    assert "context.State.ActivePathValid" in retained
    assert "context.State.IsMoving" in retained
    assert "routeActionIsMovementOnly(context.Action)" in retained
    assert "routeAttempt->MovementSubmitted = true" in retained


def test_unsubmitted_movement_yields_instead_of_claiming_a_postcondition() -> None:
    kernel = _route_kernel(FALLBACK.read_text(encoding="utf-8"))
    retry = kernel.index('"route_movement_not_submitted"')
    pending = kernel.index('"route_handled_pending_postcondition"')

    assert retry < pending


def test_exact_drudge_position_wait_commits_the_typed_movement_lane() -> None:
    kernel = _route_kernel(FALLBACK.read_text(encoding="utf-8"))
    assert "IsExactDrudgePositionHold(context.Action)" in kernel
    assert "routeAttempt->PositionHold" in kernel
    assert '"drudge_entrance_position_hold"' in kernel
    hold = kernel[kernel.index("routeAttempt->PositionHold") :]
    assert "typedDrudgeValidationRoute" in hold
    assert "context.AdaptiveDrudgeOwnsNode" in hold
    assert "!context.DrudgeCombatAuthorityAllowed" in hold
    route_action = kernel[
        kernel.index('routeAction.Attempt = '):
        kernel.index("context.State.DecisionKernel.Submit(std::move(routeAction))")
    ]
    assert "routeAttempt->PositionHold" in route_action
    assert "Resource::Movement" in kernel[
        kernel.index("BotActionArbitration::ResourceMask routeActionResources"):
        kernel.index("routeAction.RequiredResources")
    ]
