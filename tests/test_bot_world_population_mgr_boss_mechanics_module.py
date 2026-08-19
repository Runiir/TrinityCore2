from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrBossMechanics.cpp"
SUPPORT = ROOT / "src/server/game/Bots/BotWorldPopulationMgrBossMechanicsSupport.cpp"
SUPPORT_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrBossMechanicsSupport.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_boss_mechanics_dispatch_is_bounded_and_registered():
    assert len(MODULE.read_text().splitlines()) <= 1000
    assert len(SUPPORT.read_text().splitlines()) <= 1000
    assert len(SUPPORT_HEADER.read_text().splitlines()) <= 1000
    cmake = CMAKE.read_text()
    assert "BotWorldPopulationMgrBossMechanics.cpp" in cmake
    assert "BotWorldPopulationMgrBossMechanicsSupport.cpp" in cmake
    assert '#include "Bots/BotWorldPopulationMgrBossMechanicsSupport.h"' in MODULE.read_text()


def test_boss_mechanics_method_is_not_left_in_monolith():
    source = SOURCE.read_text()
    module = MODULE.read_text()
    signature = (
        "BotWorldPopulationMgr::BossMechanicActionResult "
        "BotWorldPopulationMgr::TryBossMechanics"
    )
    assert signature not in source
    assert signature in module


def test_boss_mechanics_support_keeps_native_predicates_together():
    support = SUPPORT.read_text()
    for marker in (
        "NowMs",
        "IsNativeCombatObserved",
        "UnitHealthPct",
        "SpellHasHostileMultiTargetSemantics",
    ):
        assert marker in support
