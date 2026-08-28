from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOVEMENT_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovement.h"
MOVEMENT_ADAPTER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovement.cpp"
PLANNER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementPlanner.cpp"
EXECUTOR = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementExecutor.cpp"
RECOVERY = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRecovery.cpp"
NATIVE_ACTION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrNativeAction.cpp"
PREPARATION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotPreparation.cpp"
DEATH_UPDATE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateDeath.cpp"


def _recovery_witness(last_progress_ms: int, native_progress_ms: int,
                      matching: bool) -> int:
    """Model the bounded native-position witness from the update timestamp."""
    return native_progress_ms if matching and native_progress_ms > last_progress_ms else last_progress_ms


def _dead_position_witness(last_progress_ms: int, now_ms: int,
                           moved_yards: float, matching: bool) -> int:
    return now_ms if matching and moved_yards >= 0.2 else last_progress_ms


def _stalled_native_path(now_ms: int, last_progress_ms: int,
                         repath_count: int, matching: bool) -> tuple[str, int]:
    if now_ms - last_progress_ms >= 30_000 and matching and repath_count == 0:
        return "repath", 1
    if now_ms - last_progress_ms >= 30_000:
        return "terminal", repath_count
    return "wait", repath_count


def _native_runback_submission(*, matching: bool, stalled: bool,
                               repath_count: int) -> tuple[str, int]:
    if matching and not stalled:
        return "preserve", repath_count
    if matching and repath_count == 0:
        return "repath", 1
    if matching:
        return "terminal", repath_count
    return "submit", repath_count


def _matching_native_recovery_path(*, now_ms: int, expires_at_ms: int,
                                   owner: str = "Recovery", active: bool = True,
                                   traversal: str = "native_long_path",
                                   dynamic_target_guid: int = 0,
                                   attempt: int = 7, wipe: int = 3,
                                   route: int = 11, node: str = "drudges") -> bool:
    # Lease expiry is intentionally an observation detail, not part of the
    # receipt-bound native-generator identity.
    _ = (now_ms, expires_at_ms)
    return (active and traversal == "native_long_path"
            and dynamic_target_guid == 0 and owner == "Recovery"
            and attempt == 7 and wipe == 3 and route == 11
            and node == "drudges")


def _blocks_cross_map_movement(owner: str, pending: bool) -> bool:
    return pending and owner != "Recovery"


def _admits_native_recovery_cross_map(*, owner: str,
                                      validation_enabled: bool,
                                      cohort_locked: bool,
                                      episode_scoped: bool,
                                      corpse_authority: bool,
                                      bot_map: int,
                                      cohort_map: int) -> bool:
    return (owner == "Recovery" and validation_enabled and cohort_locked
            and episode_scoped
            and corpse_authority and bot_map != cohort_map)


def test_native_long_path_is_recovery_entrance_only() -> None:
    header = MOVEMENT_HEADER.read_text(encoding="utf-8")
    adapter = MOVEMENT_ADAPTER.read_text(encoding="utf-8")
    planner = PLANNER.read_text(encoding="utf-8")

    assert "constexpr bool AllowsNativeLongPath" in header
    assert "owner == BotMovementArbitration::Owner::Recovery" in header
    assert "bool const nativeRecoveryCrossMap = movementOwner" in adapter
    assert "bool const nativeRecoveryEpisodeScoped" in adapter
    assert "state.NativeRecoveryEpisodeAttemptId == Cohort().AttemptId" in adapter
    assert "state.NativeRecoveryEpisodeRouteGeneration" in adapter
    assert "state.NativeRecoveryEpisodeWipeGeneration" in adapter
    assert "state.NativeRecoveryEpisodeDeathOrdinal == state.RecentDeathCount" in adapter
    assert "HasNativeRaidCorpseAuthority(state, bot)" in adapter
    assert "nativeRecoveryEntranceRequired" in adapter
    assert (
        "intent.AllowNativeLongPath = BotWorldMovement::AllowsNativeLongPath(\n"
        "        movementOwner, nativeRecoveryEntranceRequired);"
    ) in adapter
    assert "intent.Owner == BotMovementArbitration::Owner::Recovery" in planner
    assert "plan.NativeLongPath = true" in planner
    assert 'plan.TraversalMode = "native_long_path"' in planner

    # The mechanical scope is the complete admission truth table: recovery
    # may use the native long path only while the recovery episode requires
    # the entrance; every other owner remains fail-closed.
    cases = (
        ("Recovery", False, False),
        ("Recovery", True, True),
        ("Route", False, False),
        ("Route", True, False),
        ("CombatRange", True, False),
        ("Formation", True, False),
        ("Support", True, False),
    )
    for owner, required, expected in cases:
        actual = owner == "Recovery" and required
        assert actual is expected


def test_cross_map_recovery_requires_exact_native_corpse_authority() -> None:
    adapter = MOVEMENT_ADAPTER.read_text(encoding="utf-8")
    assert "state.ValidationCohortLocked" in adapter
    assert "bot->GetMapId() != state.ValidationCohortMapId" in adapter
    assert "state.NativeRecoveryEntranceRequired && nativeRecoveryEpisodeScoped" in adapter
    assert "|| nativeRecoveryCrossMap" in adapter

    common = dict(
        owner="Recovery", validation_enabled=True, cohort_locked=True,
        episode_scoped=True,
        corpse_authority=True, bot_map=0, cohort_map=669,
    )
    assert _admits_native_recovery_cross_map(**common)
    assert not _admits_native_recovery_cross_map(**{**common, "owner": "Route"})
    assert not _admits_native_recovery_cross_map(
        **{**common, "validation_enabled": False}
    )
    assert not _admits_native_recovery_cross_map(
        **{**common, "cohort_locked": False}
    )
    assert not _admits_native_recovery_cross_map(
        **{**common, "episode_scoped": False}
    )
    assert not _admits_native_recovery_cross_map(
        **{**common, "corpse_authority": False}
    )
    assert not _admits_native_recovery_cross_map(
        **{**common, "bot_map": 669}
    )


def test_cross_map_recovery_blocks_stale_non_recovery_movement() -> None:
    header = MOVEMENT_HEADER.read_text(encoding="utf-8")
    adapter = MOVEMENT_ADAPTER.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")

    assert "constexpr bool BlocksNonRecoveryCrossMapMovement" in header
    assert "intent.NativeRecoveryCrossMapPending =" in adapter
    assert "state.ValidationCohortMapId" in adapter
    assert "BlocksNonRecoveryCrossMapMovement" in executor
    assert 'native_recovery_worldport_pending' in executor

    # A route/combat callback can be evaluated while the corpse-run entrance
    # is still on the source map, but it must not reach PlanMovementPath. The
    # recovery owner remains admitted, and every same-map movement owner is
    # unchanged.
    owners = ("Route", "Formation", "CombatRange", "Support", "Recovery")
    assert [_blocks_cross_map_movement(owner, True) for owner in owners] == [
        True, True, True, True, False
    ]
    assert not any(_blocks_cross_map_movement(owner, False) for owner in owners)

    gate = executor.index("BlocksNonRecoveryCrossMapMovement")
    observation = executor.index("ObserveActiveMovement")
    planner = executor.index("PlanMovementPath")
    assert gate < observation < planner


def test_native_long_path_keeps_motionmaster_in_executor_and_preserves_active_path() -> None:
    planner = PLANNER.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")

    assert "MovePoint" not in planner
    assert "ObserveActiveMovement" in executor
    assert "active.NativePointPathActive" in executor
    assert "active.MatchingDestination" in executor
    assert "plan.NativeLongPath" in executor
    assert "MovePoint(0, intent.X, intent.Y, intent.Z,\n            true)" in executor
    assert executor.index("ObserveActiveMovement") < executor.index(
        "PlanMovementPath"
    )
    assert executor.index("active.MatchingDestination") < executor.index(
        "plan.NativeLongPath"
    )

    # The bypass is ordered before target-floor and progressive Euclidean
    # admission, while the executor remains the only movement owner.
    planner_native = planner.index("bool const nativeLongPathRecovery")
    assert planner_native < planner.index("float const floorZ")
    assert planner_native < planner.index("float const currentGoalDistance")
    movement_sources = (
        MOVEMENT_ADAPTER,
        PLANNER,
        EXECUTOR,
    )
    for source in movement_sources:
        text = source.read_text(encoding="utf-8")
        if source == EXECUTOR:
            assert "MovePoint" in text
        else:
            assert "MovePoint" not in text


def test_recovery_brain_stays_typed_and_forbids_cheat_operations() -> None:
    recovery = RECOVERY.read_text(encoding="utf-8")
    native_action = NATIVE_ACTION.read_text(encoding="utf-8")
    adapter = MOVEMENT_ADAPTER.read_text(encoding="utf-8")

    assert "BotNativeAction::Move" in recovery
    assert "BotNativeAction::AreaTrigger" in recovery
    assert "GetMotionMaster()->MovePoint" not in recovery
    for forbidden in ("TeleportTo(", "NearTeleportTo(", "ResurrectPlayer"):
        assert forbidden not in recovery
        assert forbidden not in adapter
    assert "forceDestination" not in recovery
    assert "BotNativeAction::Move" in native_action
    assert "MoveBotToPoint(state, bot, action.X, action.Y, action.Z" in native_action


def test_non_monotonic_native_position_refreshes_episode_witness() -> None:
    recovery = RECOVERY.read_text(encoding="utf-8")
    preparation = PREPARATION.read_text(encoding="utf-8")
    assert "state.LastMovementProgressMs" in recovery
    assert "state.NativeRecoveryEpisodeLastProgressMs = nowMs;" in recovery
    assert "state.LastMovementProgressMs\n                <= state.NativeRecoveryEpisodeLastProgressMs" in recovery
    assert preparation.index("context.State.LastMovementProgressMs = NowMs();") < preparation.index(
        "context.State.LastX = context.Bot->GetPositionX();"
    )
    assert preparation.index("HandleBotDeath(context.State, context.Bot, context.Diff)") < preparation.index(
        "context.State.LastX = context.Bot->GetPositionX();"
    )

    # A winding native path can increase trigger distance while the position
    # itself advances. The episode witness must follow actual movement.
    trigger_distances = (10.0, 11.5, 9.0)
    assert trigger_distances[1] > trigger_distances[0]
    assert _recovery_witness(1_000, 2_000, True) == 2_000
    assert _recovery_witness(1_000, 2_000, False) == 1_000


def test_dead_ghost_samples_stalled_and_progressing_native_positions() -> None:
    recovery = RECOVERY.read_text(encoding="utf-8")
    death_update = DEATH_UPDATE.read_text(encoding="utf-8")
    assert "ObserveNativeRecoveryDeadPosition(state, bot, NowMs());" in death_update
    assert death_update.index(
        "ObserveNativeRecoveryDeadPosition(state, bot, NowMs());"
    ) < death_update.index("state.DeadTimer += diff;")
    assert "state.LastMovementProgressMs = nowMs;" in death_update
    assert "state.ActivePathTraversalMode == \"native_long_path\"" in death_update
    assert "BotMovementArbitration::Owner::Recovery" in death_update
    assert "state.IsMoving" not in death_update[
        death_update.index("bool ObserveNativeRecoveryDeadPosition"):
        death_update.index("void BotWorldPopulationMgr::HandleBotDeath")
    ]
    assert "The dead update path samples the native ghost position" in recovery

    # A stationary accepted generator keeps the original witness and reaches
    # the existing 30-second repath decision; actual native position change
    # refreshes it and preserves the path.
    assert _dead_position_witness(1_000, 31_000, 0.0, True) == 1_000
    assert _dead_position_witness(1_000, 31_000, 0.25, True) == 31_000
    assert _dead_position_witness(1_000, 31_000, 5.0, False) == 1_000


def test_stalled_native_generator_gets_one_repath_then_terminal_bound() -> None:
    recovery = RECOVERY.read_text(encoding="utf-8")
    assert "state.NativeRecoveryMovementRetryCount == 0" in recovery
    assert "++state.NativeRecoveryMovementRetryCount;" in recovery
    assert "BotNativeAction::Move{ entranceEntry->Pos.X" in recovery
    assert 'terminal("native_runback_no_progress")' in recovery

    decision, retries = _stalled_native_path(30_000, 0, 0, True)
    assert (decision, retries) == ("repath", 1)
    decision, retries = _stalled_native_path(60_000, 30_000, retries, True)
    assert (decision, retries) == ("terminal", 1)


def test_active_native_runback_path_is_not_resubmitted_before_stall() -> None:
    recovery = RECOVERY.read_text(encoding="utf-8")
    preserve = recovery.index("if (matchingRecoveryPath && !recoveryPathStalled)")
    in_progress = recovery.index('result = "native_instance_runback_in_progress";', preserve)
    submit = recovery.index("BotActionArbitration::Outcome const moveOutcome", preserve)
    assert preserve < in_progress < submit

    assert _native_runback_submission(
        matching=True, stalled=False, repath_count=0
    ) == ("preserve", 0)
    assert _native_runback_submission(
        matching=True, stalled=True, repath_count=0
    ) == ("repath", 1)
    assert _native_runback_submission(
        matching=True, stalled=True, repath_count=1
    ) == ("terminal", 1)
    assert _native_runback_submission(
        matching=False, stalled=False, repath_count=0
    ) == ("submit", 0)


def test_repath_keeps_native_executor_and_no_cheat_boundaries() -> None:
    recovery = RECOVERY.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")
    assert "matchingNativeRecoveryPath" in recovery
    assert 'state.ActivePathTraversalMode == "native_long_path"' in recovery
    assert "BotMovementArbitration::Owner::Recovery" in recovery
    assert "GetMotionMaster()->MovePoint" not in recovery
    for forbidden in ("TeleportTo(", "NearTeleportTo(", "ResurrectPlayer"):
        assert forbidden not in recovery
    assert "MovePoint(0, intent.X, intent.Y, intent.Z," in executor


def test_native_repath_match_ignores_lease_expiry_but_preserves_scope() -> None:
    recovery = RECOVERY.read_text(encoding="utf-8")
    matcher = recovery[recovery.index("auto matchingNativeRecoveryPath"):
                       recovery.index("auto observeNativeRecoveryMovement")]
    assert "ExpiresAtMs" not in matcher

    for now_ms, expires_at_ms in ((1499, 1500), (1500, 1500), (1501, 1500)):
        assert _matching_native_recovery_path(
            now_ms=now_ms, expires_at_ms=expires_at_ms
        )
    assert not _matching_native_recovery_path(
        now_ms=1500, expires_at_ms=1500, owner="Route"
    )
    assert not _matching_native_recovery_path(
        now_ms=1500, expires_at_ms=1500, route=12
    )
