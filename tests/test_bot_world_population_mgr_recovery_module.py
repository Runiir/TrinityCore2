from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRecovery.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "BuildDeathRecoveryPolicy",
    "RecoverDeadBot",
    "TryNativeCorpseRun",
    "AreNativeRaidRecoveryControlledUnitsReady",
    "TryRestoreNativeRaidRecoveryPet",
    "TryRespondNativeRaidReadyCheck",
)


def test_recovery_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrRecovery.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_recovery_module_preserves_native_corpse_run_phases() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for phase in (
        "release_pending",
        "released_ghost_observed",
        "entrance_unavailable",
        "moving_to_entrance",
        "entrance_submitted",
        "moving_to_corpse",
        "reclaim_delay_pending",
        "reclaim_submitted",
        "completed",
        "terminal",
    ):
        assert f'"{phase}"' in module
    for action in (
        "BotNativeAction::ReleaseSpirit",
        "BotNativeAction::AreaTrigger",
        "BotNativeAction::ReclaimCorpse",
    ):
        assert action in module


def test_recovery_module_keeps_ready_check_and_pet_gates() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for gate in (
        "AreNativeRaidRecoveryControlledUnitsReady",
        "NativeReadyCheckPending",
        "RosterCompositionValid",
        "NativeHostileInactivityObserved",
        "TryCastFriendlySpell",
        "native_recovery_hunter_pet_revive_submitted",
        "HandleRaidReadyCheckOpcode",
    ):
        assert gate in module
