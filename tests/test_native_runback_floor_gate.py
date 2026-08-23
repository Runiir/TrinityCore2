from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLANNER = (
    ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementPlanner.cpp"
)


def _target_floor_gate(*, target_floor_valid: bool,
                       progressive_static_route: bool,
                       strict_native_descent: bool) -> bool:
    """Model only the planner's target-floor admission predicate."""
    return target_floor_valid or (
        progressive_static_route and not strict_native_descent
    )


def _coarse_z_gate(*, z_mismatch: bool,
                   progressive_static_route: bool,
                   strict_native_descent: bool) -> bool:
    """Model the planner's early height rejection predicate."""
    return not z_mismatch or (
        progressive_static_route and not strict_native_descent
    )


def test_coarse_z_mismatch_defers_only_for_non_strict_progressive_routes() -> None:
    cases = (
        (True, True, False, True),
        (True, True, True, False),
        (True, False, False, False),
        (False, False, False, True),
    )
    for mismatch, progressive, strict, expected in cases:
        assert _coarse_z_gate(
            z_mismatch=mismatch,
            progressive_static_route=progressive,
            strict_native_descent=strict,
        ) is expected


def test_invalid_runback_target_floor_admits_only_progressive_local_recovery() -> None:
    # Recorded counterexample: the native entrance target had no floor sample,
    # while recovery had already admitted progressive segments.
    cases = (
        (False, True, False, True),
        (False, False, False, False),
        (False, True, True, False),
        (True, False, False, True),
        (True, True, False, True),
        (True, True, True, True),
    )
    for target_floor_valid, progressive, strict, expected in cases:
        assert _target_floor_gate(
            target_floor_valid=target_floor_valid,
            progressive_static_route=progressive,
            strict_native_descent=strict,
        ) is expected


def test_floor_gate_defers_to_the_existing_validated_local_step() -> None:
    planner = PLANNER.read_text(encoding="utf-8")
    gate = planner.index(
        "if (!targetFloorValid && (!progressiveStaticRoute || strictNativeDescent))"
    )
    local_fallback = planner.index(
        "if (!segmentSelected && progressiveStaticRoute && !strictNativeDescent)"
    )
    final_floor_rejection = planner.index(
        "if (!targetFloorValid)", local_fallback
    )

    assert gate < local_fallback < final_floor_rejection
    assert (
        "if (targetFloorValid && std::fabs(floorZ - intent.Z) > 4.0f\n"
        "        && (!progressiveStaticRoute || strictNativeDescent))"
    ) in planner
    assert "nativeEndpointFloorValid" in planner
    assert "&& nativeEndpointFloorValid(path)" in planner
    assert "if (!nativeEndpointFloorValid(stepPath))" in planner
    assert "PATHFIND_FARFROMPOLY)" in planner
    assert "MovePoint" not in planner
    assert "Resurrect" not in planner
