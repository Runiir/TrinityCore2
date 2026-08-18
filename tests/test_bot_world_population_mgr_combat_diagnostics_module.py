from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatDiagnostics.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "BuildCombatAttemptSummary",
    "BuildRouteProgressSummary",
    "BuildCombatAttemptJson",
    "BuildRouteProgressJson",
    "RecordCombatAttempt",
    "RecordRouteProgress",
    "BuildBlockedDiagnosticText",
    "TryRecoverStuckBot",
    "ObserveBotCandidateFailure",
    "MarkBotBlocked",
    "MarkBotUnstuck",
    "TryResolveBotBlocker",
)


def test_combat_diagnostics_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrCombatDiagnostics.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_combat_diagnostics_preserves_native_gate_observations() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for gate in (
        "casting",
        "global_cooldown",
        "cooldown_ready",
        "known_spell",
        "has_power",
        "line_of_sight",
        "in_range",
        "target_alive",
        "target_attackable",
    ):
        assert gate in module
    assert "HasPowerForSpell" in module
    assert "BotActionArbitration::Priority::Survival" in module


def test_combat_diagnostics_keeps_blocker_resolution_contract() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for reason in (
        "movement_progress",
        "route_target_combat_progress",
        "cast_succeeded",
        "profile_action_valid",
        "hunter_pet_ready",
        "persistent_preexisting_affliction_pet_observed",
    ):
        assert reason in module
    assert "ProfileActionStableSamples" in module
