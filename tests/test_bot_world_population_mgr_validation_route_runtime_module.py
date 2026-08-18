from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrValidationRouteRuntime.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "ApplyValidationRouteManifestNode",
    "ResetValidationRouteBossAddEscapeState",
    "ResetValidationRouteBossAddDensityState",
    "ResetTraceStreams",
    "ResetValidationRouteRuntimeState",
    "ValidationRouteHasProgressSinceApply",
    "MaybeAdvanceValidationRouteManifest",
)


def test_validation_route_runtime_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrValidationRouteRuntime.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_validation_route_runtime_preserves_generation_and_reset_contracts() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "ValidationRouteGeneration",
        "ValidationRouteManifestIndex",
        "ValidationRouteManifestAdvancePending",
        "ValidationRouteProgressBaselineKills",
        "FlushDecisionFingerprintMemory",
        "PendingTraceSuppressedRepeatableEventCount",
        "LastPersistedDiagnosticDecisionKey",
        "ValidationRouteDrudgeChargeObservations",
    ):
        assert marker in module


def test_validation_route_runtime_preserves_terminal_evidence_and_transitions() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "ValidationRouteTerminalEvidence",
        "validation_route_manifest_complete",
        "validation_route_segment_advance",
        "native_descent_landed_path_proven",
        "all_routes_complete",
        "ApplyValidationRouteManifestNode(nextIndex",
        "ValidationRouteManifestComplete",
    ):
        assert marker in module
