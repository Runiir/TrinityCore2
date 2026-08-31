from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLANNER = (
    ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementPlanner.cpp"
)
PATH_VALIDATION = (
    ROOT / "src/server/game/Bots/BotWorldPopulationMgrNativePathValidation.h"
)


def test_floor_probe_defers_to_native_path_before_terminal_rejection() -> None:
    planner = PLANNER.read_text(encoding="utf-8")
    validation = PATH_VALIDATION.read_text(encoding="utf-8")
    request_probe = planner.index("float const floorZ =")
    native_path = planner.index("PathGenerator path(bot)")
    connected_proof = planner.index(
        "ClassifyNativePrimaryEndpointAdmission", native_path
    )
    local_fallback = planner.index(
        "if (!segmentSelected && progressivePathAdmission "
        "&& !strictNativeDescent"
    )
    final_floor_rejection = planner.index(
        "if (targetFloorRequiresNativeProof)", local_fallback
    )

    assert request_probe < native_path < connected_proof
    assert connected_proof < local_fallback < final_floor_rejection
    assert "targetZTransitionRequiresNativeProof" in planner
    assert "route_destination_invalid_z_transition" not in planner[:native_path]
    assert "nativeEndpointFloorValid" in planner
    assert "observation.EndpointFloorValid = endpointFloorValid" in validation
    assert "diagnoseCompleteNativePath" in planner
    assert "NativePathEndpointMatches" in validation
    assert "segmentX = verifiedMainEndpoint.x" in planner
    assert "FloorObservationConflict" in validation
    assert 'reject("route_destination_path_floor_gap", "path_floor")' in planner
    assert "PATHFIND_FARFROMPOLY)" in planner
    assert "MovePoint" not in planner
    assert "Resurrect" not in planner


def test_canary106_complete_native_proof_is_owner_independent() -> None:
    planner = PLANNER.read_text(encoding="utf-8")
    start = planner.index("auto diagnoseCompleteNativePath")
    end = planner.index("auto completeNativePathToPoint", start)
    invariant = planner[start:end]

    assert "DiagnoseCompleteNativePathProof" in invariant
    assert "nativeEndpointFloorValid" in invariant
    assert "diagnoseNativePathFloors" in invariant
    assert "intent.Owner" not in invariant
    assert "currentGoalDistance" not in invariant
    assert "43.6772" not in invariant

    # The recorded Canary106 values are represented by diagnostics, not by an
    # owner or distance exception in the admission rule.
    diagnostics_test = (
        ROOT / "tests/test_movement_planner_diagnostics.py"
    ).read_text(encoding="utf-8")
    assert "0.0633392f" in diagnostics_test
    for owner in ("Route", "CombatRange", "Hazard", "Mechanic"):
        assert owner not in invariant
