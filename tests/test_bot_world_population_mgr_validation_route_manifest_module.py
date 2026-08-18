from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteManifest.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


def test_validation_route_manifest_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrValidationRouteManifest.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    assert "BotWorldPopulationMgr::LoadValidationRouteManifest" in module
    assert "BotWorldPopulationMgr::LoadValidationRouteManifest" not in world


def test_validation_route_manifest_preserves_parser_and_identity_contracts() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "ReadSmallTextFile",
        "ExtractJsonObjectArrayItems",
        "ExtractJsonStrictUIntArrayField",
        "manifest_runtime_profile_identity_mismatch",
        "manifest_routes_missing",
        "manifest_routes_empty",
        "runtime_profile_id",
        "scenario_id",
        "roster_identity",
    ):
        assert marker in module


def test_validation_route_manifest_preserves_mechanic_and_native_contracts() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "AllowedMechanicContractFields",
        "MechanicContractResolved",
        "unsupported_or_incomplete_contract",
        "native_interaction_unknown_field",
        "native_completion_unknown_field",
        "native_interaction_contract_invalid",
        "native_completion_contract_invalid",
        "ApplyValidationRouteManifestNode(0, \"manifest_load\")",
    ):
        assert marker in module
