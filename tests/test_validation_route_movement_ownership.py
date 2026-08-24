from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"


def test_route_anchors_keep_route_ownership_during_combat():
    manager = (BOT_DIR / "BotWorldPopulationMgr.cpp").read_text(
        encoding="utf-8"
    )
    patrol = (
        BOT_DIR / "BotWorldPopulationMgrValidationPatrolPull.cpp"
    ).read_text(encoding="utf-8")

    route_owner = "BotMovementArbitration::Owner::Route"
    route_priority = "BotMovementArbitration::Priority::Route"

    route_anchor = manager[
        manager.index("auto moveToRouteAnchor = [&]() -> bool") :
        manager.index("auto routeFocusTankOwned", manager.index(
            "auto moveToRouteAnchor = [&]() -> bool"
        ))
    ]
    assert route_owner in route_anchor
    assert route_priority in route_anchor

    terminal_regroup = manager[
        manager.index("move_to_terminal_route_endpoint") - 900 :
        manager.index("move_to_terminal_route_endpoint") + 200
    ]
    assert route_owner in terminal_regroup
    assert route_priority in terminal_regroup

    patrol_anchor = patrol[
        patrol.index("validation_route_patrol_anchor_move") - 800 :
        patrol.index("validation_route_patrol_anchor_move") + 100
    ]
    assert route_owner in patrol_anchor
    assert route_priority in patrol_anchor
