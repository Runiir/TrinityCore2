from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrBossDispatch.cpp"
HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_boss_dispatch_module_is_bounded_and_registered():
    text = MODULE.read_text()
    assert len(text.splitlines()) <= 1000
    assert "BotWorldPopulationMgrBossDispatch.cpp" in CMAKE.read_text()
    assert '#include "Bots/BotWorldPopulationMgr.h"' in text
    for method in ("ReconcileRaidAreaAutocasts", "PrepareBossMechanicAction"):
        assert f"BotWorldPopulationMgr::{method}" in text
        assert method in HEADER.read_text()


def test_boss_dispatch_preparation_is_not_left_in_monolith():
    text = SOURCE.read_text()
    assert "PrepareBossMechanicAction(state, bot, boundRouteTarget, result)" in text
    assert "auto reconcileRaidAreaAutocasts" not in text


def test_boss_dispatch_keeps_native_target_and_area_authority_contract():
    text = MODULE.read_text()
    for marker in (
        "FindBossTarget",
        "bound_route_target_without_boss_contract",
        "BotRaidAreaAuthority::Set",
        "SpellHasHostileMultiTargetSemantics",
        "RemoveDynObject",
        "raid_target_not_declared_hold",
    ):
        assert marker in text
