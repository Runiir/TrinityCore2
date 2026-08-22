from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOVEMENT_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovement.h"
MOVEMENT_ADAPTER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovement.cpp"
PLANNER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementPlanner.cpp"
EXECUTOR = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementExecutor.cpp"
RECOVERY = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRecovery.cpp"
NATIVE_ACTION = ROOT / "src/server/game/Bots/BotWorldPopulationMgrNativeAction.cpp"


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
