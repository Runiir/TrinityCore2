from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRUDGE = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge"
BOUNDARY = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeFutureBossBoundary.cpp"
LANE = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudgeLaneSelection.cpp"
HEADER = DRUDGE / "BotWorldPopulationMgrValidationRouteDrudge.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_future_boss_boundary_runs_before_drudge_anchor_or_combat_work() -> None:
    lane = LANE.read_text(encoding="utf-8")
    resolve = lane.index("result = ResolveSources();")
    boundary = lane.index("result = EnforceFutureBossBoundary();", resolve)
    anchors = lane.index("result = BuildAnchorPolicies();", boundary)

    assert resolve < boundary < anchors
    assert "PhaseResult EnforceFutureBossBoundary();" in HEADER.read_text(
        encoding="utf-8"
    )


def test_boundary_derives_the_future_boss_from_the_route_contract() -> None:
    text = BOUNDARY.read_text(encoding="utf-8")

    assert "ValidationRouteManifestIndex + 1" in text
    assert 'future.Kind != "boss"' in text
    assert "future.TargetSpawnId" in text
    assert "future.TargetEntry" in text
    assert "41570" not in text
    assert "exactDrudgeAlive" in text


def test_boundary_clears_target_victim_cast_and_only_route_owned_movement() -> None:
    text = BOUNDARY.read_text(encoding="utf-8")

    for marker in (
        "Bot->InterruptSpell",
        "Bot->AttackStop()",
        "State.TargetGuid.Clear()",
        "controlled->AttackStop()",
        "BotMovementArbitration::Owner::Route",
        "State.ActivePathTargetGuid",
        "State.ActivePathToX",
        "Bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE)",
        'Record(futureBoss, "drudge_future_boss_target_cleared")',
    ):
        assert marker in text
    assert text.strip().endswith("return PhaseResult::Continue;\n}\n}")


def test_boundary_is_a_separate_small_build_unit() -> None:
    text = BOUNDARY.read_text(encoding="utf-8")
    assert len(text.splitlines()) < 180
    assert BOUNDARY.name in CMAKE.read_text(encoding="utf-8")
