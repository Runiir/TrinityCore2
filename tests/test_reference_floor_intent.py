from __future__ import annotations

from math import isfinite
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MOVEMENT = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovement.cpp"
MOVEMENT_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovement.h"
PLANNER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementPlanner.cpp"
DRUDGE_ACTIONS = ROOT / (
    "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
    "BotWorldPopulationMgrValidationRouteDrudgeActions.cpp"
)
DRUDGE_TAUNT = ROOT / (
    "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
    "BotWorldPopulationMgrValidationRouteDrudgeTaunt.cpp"
)
DRUDGE_ENTRANCE_MOVEMENT = ROOT / (
    "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
    "BotWorldPopulationMgrValidationRouteDrudgeEntranceMovement.cpp"
)
MANAGER_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"


def _reference_floor_accepts(
    actor_z: float, sample_zs: tuple[float, ...], reference_z: float
) -> bool:
    """Model NativePathFloorsValid's explicit four-yard envelope."""
    if not all(isfinite(value) for value in (actor_z, reference_z, *sample_zs)):
        return False
    return abs(actor_z - reference_z) <= 4.0 and all(
        abs(sample_z - reference_z) <= 4.0 for sample_z in sample_zs
    )


def test_reference_floor_is_scoped_and_absent_by_default() -> None:
    header = MOVEMENT_HEADER.read_text(encoding="utf-8")
    movement = MOVEMENT.read_text(encoding="utf-8")
    planner = PLANNER.read_text(encoding="utf-8")
    drudge = DRUDGE_ACTIONS.read_text(encoding="utf-8")

    assert "std::optional<float> ReferenceFloorZ" in header
    assert "std::nullopt" in movement
    assert "intent.ReferenceFloorZ = referenceFloorZ;" in movement
    assert "if (intent.ReferenceFloorZ)" in planner
    assert "NativePathFloorsValid(bot, candidatePath)" in planner
    assert "NativePathFloorsValid(bot, candidatePath,\n                *intent.ReferenceFloorZ, true)" in planner
    assert drudge.count("MoveBotToPointWithReferenceFloor") == 1
    assert "MoveBotToPointWithReferenceFloor" not in "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "src/server/game/Bots").glob(
            "BotWorldPopulationMgrMovement*.cpp"
        )
        if path != MOVEMENT
    )


def test_reference_floor_adapter_declaration_matches_definition() -> None:
    header = MANAGER_HEADER.read_text(encoding="utf-8")
    movement = MOVEMENT.read_text(encoding="utf-8")

    signature = "std::optional<float> referenceFloorZ"
    assert signature in header
    assert signature in movement
    assert header.count("MoveBotToPointWithReferenceFloor(") == 1
    assert movement.count("MoveBotToPointWithReferenceFloor(") == 2


def test_drudge_reference_floor_calls_follow_native_path_proofs() -> None:
    drudge = DRUDGE_ACTIONS.read_text(encoding="utf-8")
    taunt = DRUDGE_TAUNT.read_text(encoding="utf-8")
    entrance = DRUDGE_ENTRANCE_MOVEMENT.read_text(encoding="utf-8")
    call = drudge.index("Manager.MoveBotToPointWithReferenceFloor")

    # The taunt approach does not require source-union validation, so it must
    # retain the generic strict movement contract.
    assert "MoveBotToPoint(State, Bot, recoveryX, recoveryY" in taunt
    # SelectPathableDrudgeAnchor performs complete-path, floor, endpoint,
    # source-union, lane, and spacing admission before this submission. A
    # pending tank charge adds the explicit tank-path proof below it.
    selector = drudge.index("SelectPathableDrudgeAnchor(AssignedTank)")
    assert selector < call
    assert drudge.index("StrictTankRecoveryPath(State.ValidationRouteDrudgeAnchorX", selector) < call

    # Entrance positioning has its own complete-path admission immediately
    # before the scoped reference-floor submission.
    entrance_call = entrance.index("Manager.MoveBotToPointWithReferenceFloor")
    assert entrance.index("StrictNativePath(anchor->X", 0, entrance_call) < entrance_call


def test_reference_floor_keeps_generic_strictness_and_four_yard_rejection() -> None:
    # Without an explicit contract, the planner's strict overload remains the
    # only generic path admission. The model covers the scoped fallback's
    # actor and every sampled-point envelope.
    planner = PLANNER.read_text(encoding="utf-8")
    optional_call = planner.index(
        "NativePathFloorsValid(bot, candidatePath,\n                *intent.ReferenceFloorZ, true)"
    )
    strict_call = planner.index(
        "NativePathFloorsValid(bot, candidatePath);", optional_call
    )
    assert optional_call < strict_call

    assert _reference_floor_accepts(214.0, (214.2, 217.9), 214.0)
    assert not _reference_floor_accepts(218.01, (214.2,), 214.0)
    assert not _reference_floor_accepts(214.0, (218.01,), 214.0)
