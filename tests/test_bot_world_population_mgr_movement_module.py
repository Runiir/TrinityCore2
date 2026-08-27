from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovement.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"
LEASE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementLease.cpp"
PLANNER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementPlanner.cpp"
EVIDENCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementEvidence.cpp"
EXECUTOR = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementExecutor.cpp"
NATIVE_EXECUTOR = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementNativeExecutor.cpp"
HELPER_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovement.h"


MOVEMENT_SOURCES = (MODULE, LEASE, PLANNER, EVIDENCE, EXECUTOR,
                    NATIVE_EXECUTOR)


def test_movement_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    cmake = CMAKE.read_text(encoding="utf-8")
    for source in MOVEMENT_SOURCES:
        assert source.name in cmake
        assert len(source.read_text(encoding="utf-8").splitlines()) <= 1000
    assert HELPER_HEADER.exists()
    assert len(HELPER_HEADER.read_text(encoding="utf-8").splitlines()) <= 1000
    assert "BotWorldPopulationMgr::MoveBotToPoint" in module
    assert "BotWorldPopulationMgr::ExecuteNativeDescentIntent" in NATIVE_EXECUTOR.read_text(
        encoding="utf-8"
    )
    assert "BotWorldPopulationMgr::ExecuteNativeDescentIntent" not in world
    assert "BotWorldPopulationMgr::MoveBotToPoint" not in world


def test_movement_module_preserves_native_path_admission() -> None:
    module = "\n".join(source.read_text(encoding="utf-8") for source in MOVEMENT_SOURCES)
    for reason in (
        "movement_lease_invalid_scope",
        "route_destination_invalid_floor",
        "route_destination_partial_path",
        "route_destination_shortcut_path",
        "route_destination_off_mesh",
        "route_destination_recently_failed",
        "native_descent_complete_path_required",
        "native_descent_drop_policy_rejected",
    ):
        assert reason in module
    assert "PathGenerator" in module
    assert "BotExperienceLearningPolicy::ScorePath" in module


def test_movement_module_keeps_descent_evidence_states() -> None:
    module = NATIVE_EXECUTOR.read_text(encoding="utf-8")
    for phase in (
        "Unobserved",
        "Approaching",
        "Departed",
        "Falling",
        "Landed",
        "Ready",
        "Blocked",
    ):
        assert f"ValidationDescentPhase::{phase}" in module
    for event in (
        "native_descent_falling_observed",
        "native_descent_grounded_observed",
        "native_descent_ready",
        "native_descent_walk_segment_submitted",
    ):
        assert event in module


def test_movement_boundary_is_intent_driven_and_nonblocking() -> None:
    adapter = MODULE.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")
    planner = PLANNER.read_text(encoding="utf-8")
    assert "BotWorldMovement::Intent intent" in adapter
    assert "ExecuteMovementIntent(state, bot, intent)" in adapter
    assert "MovePoint" in executor and "MoveChase" in executor
    assert "WaitForReach" not in executor
    assert "SetNextCheckDelay" not in executor
    assert "MovementActions" not in "\n".join(
        source.read_text(encoding="utf-8") for source in MOVEMENT_SOURCES
    )
    # Planning admits paths; native MotionMaster submission belongs only to
    # the executor, keeping policy/brain cadence outside the service.
    assert "MovePoint" not in planner
    assert "MoveChase" not in planner
    assert "TryValidationRouteObjective" not in executor
    retained = executor.index("active.ScopeMatches && active.MatchingDestination")
    committed = executor.index("CommitMovementEvidence")
    assert retained < committed
    assert 'state.LastRecoveryResult = "native_movement_retained";' in executor[
        retained:committed
    ]


def test_route_and_recovery_progressive_admission_is_bounded() -> None:
    header = HELPER_HEADER.read_text(encoding="utf-8")
    adapter = MODULE.read_text(encoding="utf-8")

    assert "constexpr bool AllowsProgressiveSegments" in header
    assert "BotWorldMovement::AllowsProgressiveSegments(" in adapter
    assert "movementOwner\n        == BotMovementArbitration::Owner::Route\n        && intent.AllowProgressiveSegments" in adapter

    # This is the complete deterministic truth table for the C++ boundary.
    cases = (
        ("Route", False, True),
        ("Route", True, True),
        ("Recovery", False, False),
        ("Recovery", True, True),
        ("CombatRange", True, False),
        ("Formation", True, False),
        ("Support", True, False),
    )
    for owner, native_recovery_entrance, expected in cases:
        actual = owner == "Route" or (
            owner == "Recovery" and native_recovery_entrance
        )
        assert actual is expected


def test_path_rejection_and_commit_preserve_evidence_invariants() -> None:
    evidence = EVIDENCE.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")
    for field in (
        "ActivePathValid",
        "ActivePathSegmentValid",
        "ActivePathTraversalMode",
        "ActivePathTargetGuid",
        "LastPathRejectReason",
        "LastPathChangeMs",
    ):
        assert field in evidence
    assert "RejectMovementPath" in executor
    assert "CommitMovementEvidence" in executor
    assert "BotMovementArbitration::Apply" in evidence
