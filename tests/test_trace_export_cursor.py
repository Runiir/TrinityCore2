"""Trace serialization and lifecycle seams.

Retention/cursor behavior is exercised against the production C++ helpers in
test_trace_pending_retention.py; no copied Python ring model is used.
"""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_ROOT = ROOT / "src/server/game/Bots"
MANAGER = "\n".join(
    (BOT_ROOT / name).read_text(encoding="utf-8")
    for name in (
        "BotWorldPopulationMgrDecisionTrace.cpp",
        "BotWorldPopulationMgrDecisionTraceJson.h",
        "BotWorldPopulationMgrStatus.cpp",
        "BotWorldPopulationMgrValidationLifecycle.cpp",
        "BotWorldPopulationMgrValidationRouteRuntime.cpp",
        "BotWorldPopulationMgrRuntimeProfiles.cpp",
    )
)
HEADER = (BOT_ROOT / "BotWorldPopulationMgrRuntimeContracts.h").read_text(encoding="utf-8")
TRACE_MODULE = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrDecisionTrace.cpp").read_text(encoding="utf-8")
RUNTIME_MODULE = (BOT_ROOT / "BotWorldPopulationMgrValidationRouteRuntime.cpp").read_text(encoding="utf-8")
PROFILE_MODULE = (BOT_ROOT / "BotWorldPopulationMgrRuntimeProfiles.cpp").read_text(encoding="utf-8")


def test_delta_encoder_keeps_suppressed_repeatable_event_count_and_bound():
    assert "suppressed_repeatable_event_count" in MANAGER
    assert "SuppressedRepeatableDecisionCount" in TRACE_MODULE
    assert "coalesceRepeatable" in TRACE_MODULE
    assert "std::min<uint32>(limit, 128)" in MANAGER
    assert "TraceExportCursorByGuid.find" in MANAGER
    assert "BotWorldTrace::BuildExportCursorTransition" in MANAGER
    assert "BotWorldTrace::WriteExportCursorFields" in MANAGER
    assert "transition.EntryCount && transition.CursorAfter != transition.CursorBefore" in MANAGER


def test_trace_stream_reset_is_reserved_for_destructive_lifecycle_boundaries():
    helper = RUNTIME_MODULE[RUNTIME_MODULE.index("void BotWorldPopulationMgr::ResetTraceStreams") :]
    reset = RUNTIME_MODULE[
        RUNTIME_MODULE.index("void BotWorldPopulationMgr::ResetValidationRouteRuntimeState") :
        RUNTIME_MODULE.index("bool BotWorldPopulationMgr::ValidationRouteHasProgressSinceApply")
    ]
    apply_node = RUNTIME_MODULE[
        RUNTIME_MODULE.index("bool BotWorldPopulationMgr::ApplyValidationRouteManifestNode") :
        RUNTIME_MODULE.index("void BotWorldPopulationMgr::ResetValidationRouteBossAddEscapeState")
    ]
    profile_clear = PROFILE_MODULE[
        PROFILE_MODULE.index("std::string BotWorldPopulationMgr::ClearRuntimeProfile") :
        PROFILE_MODULE.index("std::string BotWorldPopulationMgr::ReloadRuntimeProfiles")
    ]
    advance = RUNTIME_MODULE[RUNTIME_MODULE.index(
        "bool BotWorldPopulationMgr::MaybeAdvanceValidationRouteManifest"
    ) :]
    assert "Party().TraceExportCursorByGuid.clear();" in helper
    assert "state.TraceSequence = 0;" in helper
    assert "state.DecisionTrace.clear();" in helper
    assert "ResetTraceStreams();" not in reset
    assert "flush_suppressed_repeatable_tail" not in reset
    assert "flush_suppressed_repeatable_tail" in apply_node
    assert apply_node.index("flush_suppressed_repeatable_tail") < apply_node.index(
        "Party().ValidationRouteGeneration = index + 1"
    )
    assert "ResetTraceStreams();" in profile_clear
    assert advance.index("validation_route_segment_advance") < advance.index(
        "ApplyValidationRouteManifestNode(nextIndex"
    )
    assert "mutable std::map<uint32, uint64> TraceExportCursorByGuid;" in HEADER
