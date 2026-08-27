from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrBossMechanics.cpp"
HEALER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrBossHealer.cpp"
SUPPORT = ROOT / "src/server/game/Bots/BotWorldPopulationMgrBossMechanicsSupport.cpp"
SUPPORT_HEADER = ROOT / "src/server/game/Bots/BotWorldPopulationMgrBossMechanicsSupport.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_boss_mechanics_dispatch_is_bounded_and_registered():
    assert len(MODULE.read_text().splitlines()) <= 1000
    assert len(HEALER.read_text().splitlines()) <= 1000
    assert len(SUPPORT.read_text().splitlines()) <= 1000
    assert len(SUPPORT_HEADER.read_text().splitlines()) <= 1000
    cmake = CMAKE.read_text()
    assert "BotWorldPopulationMgrBossMechanics.cpp" in cmake
    assert "BotWorldPopulationMgrBossHealer.cpp" in cmake
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


def test_boss_healer_call_stays_between_adds_and_profile_fallback():
    source = MODULE.read_text()
    adds = source.index('result.Action = "switch_to_adds"')
    healer = source.index("TryBossHealer(state, bot, role")
    fallback = source.index("ResolvedCombatAction profileAction", healer)

    assert adds < healer < fallback
    assert "TryBossHealer" in HEALER.read_text()


def test_boss_healer_rejection_reasons_are_traceable():
    healer = HEALER.read_text()
    for reason in (
        "unassigned_healer",
        "no_eligible_target",
        "no_profile_heal",
        "range_or_los_rejected",
        "cast_failed",
    ):
        assert reason in healer
    assert '"boss_heal_rejected"' in healer
    assert '"raid_healer_rejection"' in healer
    assert "failureReason" in healer


def test_boss_mechanics_support_keeps_native_predicates_together():
    support = SUPPORT.read_text()
    for marker in (
        "NowMs",
        "IsNativeCombatObserved",
        "UnitHealthPct",
        "SpellHasHostileMultiTargetSemantics",
    ):
        assert marker in support
