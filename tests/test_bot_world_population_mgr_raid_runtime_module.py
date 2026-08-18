from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRaidRuntime.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_raid_runtime_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrRaidRuntime.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    assert "BotWorldPopulationMgr::BuildRaidRuntimeJson" in module
    assert "BotWorldPopulationMgr::BuildRaidRuntimeJson" not in world


def test_raid_runtime_preserves_admission_and_gear_identity_contracts() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "admission_receipt",
        "all_current_gear_matches_admission",
        "ResolveExpectedBotGearIdentity",
        "ObserveEquippedGearIdentity",
        "EquippedGearManifestsEqual",
        "identity_catalog_source_sha256",
        "initial_baseline_normalized",
        "initial_alive_state_verified",
    ):
        assert marker in module


def test_raid_runtime_preserves_compact_route_and_recovery_evidence() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "compactTelemetry",
        "native_recovery_hold_active",
        "native_hostile_activity_active",
        "strategy_transition",
        "route_progress",
        "boss_states",
        "drudge_charge",
        "native_threat_candidates",
    ):
        assert marker in module
