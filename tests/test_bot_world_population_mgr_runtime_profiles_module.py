from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrRuntimeProfiles.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "RuntimeProfilesJson",
    "EnsureRuntimeProfilesLoaded",
    "LoadRuntimeProfiles",
    "GetRuntimeProfilesJson",
    "SelectRuntimeProfile",
    "ClearRuntimeProfile",
    "ReloadRuntimeProfiles",
    "SelectConfiguredRuntimeProfile",
)


def test_runtime_profiles_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrRuntimeProfiles.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_runtime_profiles_module_keeps_manifest_contract() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for field in (
        "target_population",
        "pool_tag_filter",
        "spawn_mode",
        "validation_route",
        "manifest_path",
        "scenario_id",
        "mechanic_profile",
    ):
        assert field in module
    for failure in (
        "profile_manifest_unreadable",
        "profile_manifest_profiles_missing",
        "profile_missing_name",
        "profile_duplicate_name",
        "profile_bad_raid_size",
    ):
        assert failure in module


def test_runtime_profiles_module_preserves_operator_actions() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for action in (
        "botauto_profiles",
        "botauto_profile",
        "botauto_profile_clear",
        "botauto_profile_reload",
        "runtime_profile_clear",
        "RuntimeProfileSelectionPending",
    ):
        assert action in module
