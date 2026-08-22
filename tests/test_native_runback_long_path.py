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
    assert "NativeRecoveryEntranceRequired" in adapter
    assert "NativeRecoveryEntranceAvailable" in adapter
    assert "NativeRunbackAreaTriggerId != 0" in adapter
    assert "AllowsNativeLongPath(" in adapter
    assert "intent.Owner == BotMovementArbitration::Owner::Recovery" in planner
    assert "plan.NativeLongPath = true" in planner


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


def test_recovery_brain_stays_typed_and_forbids_cheat_operations() -> None:
    recovery = RECOVERY.read_text(encoding="utf-8")
    native_action = NATIVE_ACTION.read_text(encoding="utf-8")

    assert "BotNativeAction::Move" in recovery
    assert "BotNativeAction::AreaTrigger" in recovery
    assert "GetMotionMaster()->MovePoint" not in recovery
    for forbidden in ("TeleportTo(", "NearTeleportTo(", "ResurrectPlayer"):
        assert forbidden not in recovery
    assert "BotNativeAction::Move" in native_action
    assert "MoveBotToPoint(state, bot, action.X, action.Y, action.Z" in native_action
