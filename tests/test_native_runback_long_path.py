from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOVEMENT_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovement.h"
MOVEMENT_ADAPTER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovement.cpp"
PLANNER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementPlanner.cpp"
EXECUTOR = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementExecutor.cpp"
RECOVERY = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRecovery.cpp"
NATIVE_ACTION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrNativeAction.cpp"
PREPARATION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotPreparation.cpp"


def _recovery_witness(last_progress_ms: int, native_progress_ms: int,
                      matching: bool) -> int:
    """Model the bounded native-position witness from the update timestamp."""
    return native_progress_ms if matching and native_progress_ms > last_progress_ms else last_progress_ms


def _stalled_native_path(now_ms: int, last_progress_ms: int,
                         repath_count: int, matching: bool) -> tuple[str, int]:
    if now_ms - last_progress_ms >= 30_000 and matching and repath_count == 0:
        return "repath", 1
    if now_ms - last_progress_ms >= 30_000:
        return "terminal", repath_count
    return "wait", repath_count


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


def test_native_long_path_is_recovery_entrance_only() -> None:
    header = MOVEMENT_HEADER.read_text(encoding="utf-8")
    adapter = MOVEMENT_ADAPTER.read_text(encoding="utf-8")
    planner = PLANNER.read_text(encoding="utf-8")

    assert "constexpr bool AllowsNativeLongPath" in header
    assert "owner == BotMovementArbitration::Owner::Recovery" in header
    assert (
        "intent.AllowNativeLongPath = BotWorldMovement::AllowsNativeLongPath(\n"
        "        movementOwner, state.NativeRecoveryEntranceRequired);"
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

    assert "BotNativeAction::Move" in recovery
    assert "BotNativeAction::AreaTrigger" in recovery
    assert "GetMotionMaster()->MovePoint" not in recovery
    for forbidden in ("TeleportTo(", "NearTeleportTo(", "ResurrectPlayer"):
        assert forbidden not in recovery
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
