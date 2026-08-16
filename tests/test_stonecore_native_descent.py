import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp").read_text(
    encoding="utf-8"
)
HEADER = (ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h").read_text(
    encoding="utf-8"
)
INTENTS = (ROOT / "src/server/game/Bots/BotNativeActionIntent.h").read_text(
    encoding="utf-8"
)


def _stonecore_scenarios() -> list[dict]:
    config = json.loads(
        (ROOT / "experiments/configs/validation_scenarios_cata_001.json").read_text(
            encoding="utf-8"
        )
    )
    return [
        scenario
        for scenario in config["scenarios"]
        if scenario["id"] in {"stonecore_5n", "stonecore_5h"}
    ]


def test_stonecore_declares_exactly_two_typed_native_walkable_descents() -> None:
    scenarios = _stonecore_scenarios()
    assert {scenario["id"] for scenario in scenarios} == {
        "stonecore_5n",
        "stonecore_5h",
    }
    for scenario in scenarios:
        descents = [node for node in scenario["route"] if node["kind"] == "descent"]
        assert [node["label"] for node in descents] == [
            "lower stonecore approach regroup",
            "post-Ozruk flayer approach regroup",
        ]
        assert all(
            node["descent_action"] == "native_walkable_descent"
            for node in descents
        )
        assert all(
            node["completion_policy"]
            == "native_grounded_landing_and_onward_path"
            for node in descents
        )


def test_descent_is_a_typed_movement_intent_not_a_synthetic_motion() -> None:
    assert "struct NativeDescent" in INTENTS
    assert "std::is_same_v<T, NativeDescent>" in INTENTS
    assert "BotNativeAction::NativeDescent" in RUNTIME
    assert "ExecuteNativeDescentIntent" in HEADER

    descent = RUNTIME[
        RUNTIME.index(
            "BotWorldPopulationMgr::ExecuteNativeDescentIntent"
        ) : RUNTIME.index(
            "BotWorldPopulationMgr::ExecuteNativeActionIntent",
            RUNTIME.index("BotWorldPopulationMgr::ExecuteNativeDescentIntent"),
        )
    ]
    for forbidden in (
        "MoveJump(",
        "MoveFall(",
        "TeleportTo(",
        "NearTeleportTo(",
        "UpdatePosition(",
        "SetHealth(",
        "ModifyHealth(",
    ):
        assert forbidden not in descent
    assert "MoveBotToPoint" in descent
    assert "PathGenerator onwardPath(bot)" in descent
    assert "PATHFIND_INCOMPLETE" in descent
    assert "SubmitMeleeAutoAttackIntent" in descent
    assert "BotMeleeAutoAttack::Kind::Suppress" in descent


def test_descent_tracks_player_observations_and_requires_cohort_barrier() -> None:
    required_state = (
        "ValidationRouteDescentDepartureObserved",
        "ValidationRouteDescentFallingObserved",
        "ValidationRouteDescentLandingObserved",
        "ValidationRouteDescentHealthMarginSatisfied",
        "ValidationRouteDescentLandingPathProven",
        "ValidationRouteDescentMonotonicProgressObserved",
    )
    for field in required_state:
        assert field in HEADER

    descent = RUNTIME[
        RUNTIME.index(
            "BotWorldPopulationMgr::ExecuteNativeDescentIntent"
        ) : RUNTIME.index(
            "BotWorldPopulationMgr::ExecuteNativeActionIntent",
            RUNTIME.index("BotWorldPopulationMgr::ExecuteNativeDescentIntent"),
        )
    ]
    assert "bot->IsFalling()" in descent
    assert "MinimumLandingHealthPct" in descent
    assert "native_descent_grounded_stability_pending" in descent
    assert "native_descent_landing_next_goal_path_unavailable" in descent
    assert "native_descent_departure_not_observed" in descent

    advance = RUNTIME[
        RUNTIME.index("bool BotWorldPopulationMgr::MaybeAdvanceValidationRouteManifest") :
        RUNTIME.index("bool BotWorldPopulationMgr::TryReattachValidationBot")
    ]
    assert '== "native_walkable_descent"' in advance
    for field in (
        "ValidationRouteDescentDepartureObserved",
        "ValidationRouteDescentLandingObserved",
        "ValidationRouteDescentHealthMarginSatisfied",
        "ValidationRouteDescentLandingPathProven",
        "ValidationRouteDescentMonotonicProgressObserved",
    ):
        assert field in advance
    assert "loadedBot->IsFalling()" in advance
    assert '"native_descent_landed_path_proven"' in advance


def test_descent_reachability_accepts_only_a_complete_native_path() -> None:
    descent = RUNTIME[
        RUNTIME.index(
            "BotWorldPopulationMgr::ExecuteNativeDescentIntent"
        ) : RUNTIME.index(
            "BotWorldPopulationMgr::ExecuteNativeActionIntent",
            RUNTIME.index("BotWorldPopulationMgr::ExecuteNativeDescentIntent"),
        )
    ]
    movement = RUNTIME[
        RUNTIME.index("bool BotWorldPopulationMgr::MoveBotToPoint") :
        RUNTIME.index("BotWorldPopulationMgr::ValidationDescentPhaseName")
    ]
    assert "PathGenerator descentPreflight(bot)" in descent
    assert "descentPathType & PATHFIND_NORMAL" in descent
    assert "descentPathType & PATHFIND_INCOMPLETE" in descent
    assert "native_descent_drop_policy_rejected" in descent
    assert "MaximumNativeWalkStepDown" in descent
    assert "native_walkable_step" in movement
    assert "GetActualEndPosition" in movement
    assert "route_destination_shortcut_path" in movement


def test_descent_rejects_incomplete_primary_path_without_partial_fallback() -> None:
    movement = RUNTIME[
        RUNTIME.index("bool BotWorldPopulationMgr::MoveBotToPoint") :
        RUNTIME.index("BotWorldPopulationMgr::ValidationDescentPhaseName")
    ]
    assert (
        'Cohort().Config.ValidationRouteDescentAction\n'
        '            == "native_walkable_descent"'
    ) in movement
    assert "else if (!strictNativeDescent && progressiveStaticRoute" in movement
    assert "if (!segmentSelected && progressiveStaticRoute && !strictNativeDescent)" in movement
    assert 'descentRejectReason = "native_descent_complete_path_required"' in movement

    descent = RUNTIME[
        RUNTIME.index(
            "BotWorldPopulationMgr::ExecuteNativeDescentIntent"
        ) : RUNTIME.index(
            "BotWorldPopulationMgr::ExecuteNativeActionIntent",
            RUNTIME.index("BotWorldPopulationMgr::ExecuteNativeDescentIntent"),
        )
    ]
    preflight = descent[
        descent.index("PathGenerator descentPreflight(bot)") :
        descent.index("bool const moved = MoveBotToPoint", descent.index("PathGenerator descentPreflight(bot)"))
    ]
    assert "!(descentPathType & PATHFIND_INCOMPLETE)" in preflight
    assert "if (!completeNativePath)" in preflight
    assert 'return reject("native_descent_complete_path_required")' in preflight


def test_descent_rejects_incomplete_step_and_onward_paths() -> None:
    movement = RUNTIME[
        RUNTIME.index("bool BotWorldPopulationMgr::MoveBotToPoint") :
        RUNTIME.index("BotWorldPopulationMgr::ValidationDescentPhaseName")
    ]
    fallback = movement[
        movement.index(
            "if (!segmentSelected && progressiveStaticRoute && !strictNativeDescent)"
        ) : movement.index("char const* descentRejectReason")
    ]
    assert "stepType & (PATHFIND_NORMAL | PATHFIND_INCOMPLETE)" in fallback
    # The entire incomplete/local-step fallback is unreachable for the typed
    # descent because its enclosing predicate requires !strictNativeDescent.
    assert fallback.startswith(
        "if (!segmentSelected && progressiveStaticRoute && !strictNativeDescent)"
    )

    descent = RUNTIME[
        RUNTIME.index(
            "BotWorldPopulationMgr::ExecuteNativeDescentIntent"
        ) : RUNTIME.index(
            "BotWorldPopulationMgr::ExecuteNativeActionIntent",
            RUNTIME.index("BotWorldPopulationMgr::ExecuteNativeDescentIntent"),
        )
    ]
    onward = descent[
        descent.index("PathGenerator onwardPath(bot)") :
        descent.index(
            "state.ValidationRouteDescentLandingPathProven = true"
        )
    ]
    assert "!(onwardType & PATHFIND_INCOMPLETE)" in onward
    assert 'return reject("native_descent_landing_next_goal_path_unavailable")' in onward


def test_descent_cannot_complete_while_falling() -> None:
    descent = RUNTIME[
        RUNTIME.index(
            "BotWorldPopulationMgr::ExecuteNativeDescentIntent"
        ) : RUNTIME.index(
            "BotWorldPopulationMgr::ExecuteNativeActionIntent",
            RUNTIME.index("BotWorldPopulationMgr::ExecuteNativeDescentIntent"),
        )
    ]
    falling = descent.index("if (bot->IsFalling())")
    landing = descent.index("if (insideLanding && grounded)")
    ready = descent.index("native_descent_ready")
    assert falling < landing < ready
    assert "native_descent_falling_observed" in descent[falling:landing]


def test_descent_requires_all_five_members_at_barrier() -> None:
    advance = RUNTIME[
        RUNTIME.index("bool BotWorldPopulationMgr::MaybeAdvanceValidationRouteManifest") :
        RUNTIME.index("bool BotWorldPopulationMgr::TryReattachValidationBot")
    ]
    typed_start = advance.index("bool const typedNativeDescent")
    typed = advance[typed_start:]
    assert "for (WorldBotState const& state : Party().Bots)" in typed
    assert "++loadedParticipants" in typed
    assert "Cohort().Config.TargetPopulation" in typed
    assert "loadedParticipants < Cohort().Config.TargetPopulation" in typed
    assert "allLoadedArrived = false" in typed


def test_descent_requires_exact_onward_path_before_ready() -> None:
    descent = RUNTIME[
        RUNTIME.index(
            "BotWorldPopulationMgr::ExecuteNativeDescentIntent"
        ) : RUNTIME.index(
            "BotWorldPopulationMgr::ExecuteNativeActionIntent",
            RUNTIME.index("BotWorldPopulationMgr::ExecuteNativeDescentIntent"),
        )
    ]
    onward = descent.index("PathGenerator onwardPath(bot)")
    path_proven = descent.index(
        "state.ValidationRouteDescentLandingPathProven = true"
    )
    ready = descent.index("state.ValidationRouteDescentPhase = Phase::Ready")
    assert onward < path_proven < ready
    for rejected_type in (
        "PATHFIND_NOPATH",
        "PATHFIND_NOT_USING_PATH",
        "PATHFIND_INCOMPLETE",
        "PATHFIND_SHORTCUT",
        "PATHFIND_FARFROMPOLY",
    ):
        assert rejected_type in descent[onward:path_proven]


def test_descent_no_progress_is_a_bounded_terminal_attempt_failure() -> None:
    descent = RUNTIME[
        RUNTIME.index(
            "BotWorldPopulationMgr::ExecuteNativeDescentIntent"
        ) : RUNTIME.index(
            "BotWorldPopulationMgr::ExecuteNativeActionIntent",
            RUNTIME.index("BotWorldPopulationMgr::ExecuteNativeDescentIntent"),
        )
    ]
    assert "NoProgressTerminalMs = 30000" in descent
    assert "ValidationRouteDescentLastProgressMs" in descent
    assert '"native_descent_no_progress_terminal"' in descent
    assert "FailValidationAttemptOnce(state, bot, failureReason" in descent
    assert "BotActionArbitration::Outcome::Terminal" in descent
    assert '"native_descent_pre_step_health_margin_low"' in descent
    assert "MinimumPreDescentHealthPct = 0.50f" in descent


def test_descent_terminal_latches_one_cohort_failure_and_event() -> None:
    failure = RUNTIME[
        RUNTIME.index("bool BotWorldPopulationMgr::FailValidationAttemptOnce") :
        RUNTIME.index(
            "void BotWorldPopulationMgr::MaybeStartAutoRecordingWindow",
            RUNTIME.index("bool BotWorldPopulationMgr::FailValidationAttemptOnce"),
        )
    ]
    assert "ValidationAttemptFailureReason = reason" in failure
    assert "ValidationAttemptFailureAttemptId = Cohort().AttemptId" in failure
    assert "ValidationAttemptFailureRouteGeneration = routeGeneration" in failure
    assert "routeGeneration != Party().ValidationRouteGeneration" in failure
    assert (
        "Cohort().ValidationAdmission = ValidationAdmissionPhase::Terminal"
        in failure
    )
    assert "Cohort().Raid.BotActionsEnabled = false" in failure
    assert "Cohort().Raid.AdmissionActionGateEnabled = false" in failure
    assert "BotRaidAreaAuthority::SetAllOffenseSuppressed" in failure
    assert "BotMovementArbitration::Clear(member.MovementLease)" in failure
    assert "member.ValidationRouteTerminalState = true" in failure
    assert failure.count(
        'RecordEvent(reporterState, reporter, "validation_route_terminal"'
    ) == 1
    # The first current-attempt latch returns before the event site on every
    # subsequent bot/tick, so one blocked member cannot fan out terminal rows.
    assert failure.index("ValidationAttemptFailureAttemptId == Cohort().AttemptId") < (
        failure.index(
            'RecordEvent(reporterState, reporter, "validation_route_terminal"'
        )
    )

    ensure = RUNTIME[
        RUNTIME.index("void BotWorldPopulationMgr::EnsurePopulation()") :
        RUNTIME.index(
            "void BotWorldPopulationMgr::EnsureCalibrationCohortGroup",
            RUNTIME.index("void BotWorldPopulationMgr::EnsurePopulation()"),
        )
    ]
    terminal_guard = ensure.index(
        "Cohort().ValidationAdmission == ValidationAdmissionPhase::Terminal"
    )
    active_revalidation = ensure.index(
        "Cohort().ValidationAdmission == ValidationAdmissionPhase::Active"
    )
    assert terminal_guard < active_revalidation
    assert "return;" in ensure[terminal_guard:active_revalidation]

    assert (
        'Cohort().ValidationAdmission == ValidationAdmissionPhase::Terminal '
        '? "terminal" : "provisioning"'
        in RUNTIME
    )


def test_descent_proximity_cannot_complete_before_typed_reconciliation() -> None:
    arrival = RUNTIME[
        RUNTIME.index(
            'if (arrivalRoute && !arrivalCombatActive)'
        ) : RUNTIME.index(
            'if (Cohort().Config.ValidationRouteKind != "boss"',
            RUNTIME.index('if (arrivalRoute && !arrivalCombatActive)'),
        )
    ]
    typed = arrival.index(
        'Cohort().Config.ValidationRouteDescentAction.empty()'
    )
    proximity = arrival.index("canonicalRouteDistance <= routeArrivalRadius")
    assert typed < proximity
    assert "native_descent_semantics_unavailable" in arrival
    assert "FailValidationAttemptOnce(state, bot" in arrival
    assert "validation_route_descent_blocked" in arrival
    assert "validation_route_descent_complete" in arrival


def test_unsupported_descent_action_terminalizes_the_cohort_once() -> None:
    arrival = RUNTIME[
        RUNTIME.index(
            'if (Cohort().Config.ValidationRouteKind == "descent"'
        ) : RUNTIME.index(
            "size_t const nextIndex",
            RUNTIME.index(
                'if (Cohort().Config.ValidationRouteKind == "descent"'
            ),
        )
    ]
    assert (
        'Cohort().Config.ValidationRouteDescentAction\n'
        '                != "native_walkable_descent"'
        in arrival
    )
    assert '"native_descent_semantics_unavailable"' in arrival
    assert "FailValidationAttemptOnce(state, bot" in arrival
    assert "Party().ValidationRouteGeneration" in arrival
    assert 'RecordEvent(state, bot, "validation_route_descent_blocked"' not in arrival
    for forbidden in ("MoveJump(", "MoveFall(", "TeleportTo(", "UpdatePosition("):
        assert forbidden not in arrival
