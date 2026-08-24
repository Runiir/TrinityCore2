"""Regression tests for lossless bounded bot trace polling.

The production ring lives in C++, so these tests keep a small executable
model of its cursor contract and pair it with source assertions for the
serialization/reset seams.  The model intentionally treats a missing prefix
as an evidence failure rather than silently accepting the retained suffix.
"""

from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_ROOT = ROOT / "src/server/game/Bots"
MANAGER = "\n".join(
    (BOT_ROOT / name).read_text(encoding="utf-8")
    for name in (
        "BotWorldPopulationMgrDecisionTrace.cpp",
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


@dataclass
class TraceRow:
    sequence: int
    decision_sequence: int
    suppressed_repeatable_event_count: int = 0
    suppressed_repeatable_decision_count: int = 0
    key: str = ""
    timestamp_ms: int = 0


class TraceRing:
    def __init__(self):
        self.rows = []
        self.trace_sequence = 0
        self.cursor = None

    def record(self, decision_sequence, suppressed=0, *, key="", timestamp_ms=0, coalesce=False):
        if coalesce and self.rows:
            previous = self.rows[-1]
            if previous.key == key and timestamp_ms >= previous.timestamp_ms \
                    and timestamp_ms - previous.timestamp_ms < 5000:
                previous.suppressed_repeatable_decision_count += 1
                return
        self.trace_sequence += 1
        self.rows.append(TraceRow(
            self.trace_sequence, decision_sequence, suppressed,
            key=key, timestamp_ms=timestamp_ms,
        ))
        self.rows = self.rows[-128:]

    def delta(self, limit=20):
        cursor = 0 if self.cursor is None else self.cursor
        cursor_initialized = self.cursor is not None
        new = [row for row in self.rows if row.sequence > cursor]
        expected = cursor + 1
        gap = bool(new) and (
            (not cursor_initialized and new[0].sequence != 1)
            or (cursor_initialized and new[0].sequence != expected)
        )
        if not gap:
            for previous, current in zip(new, new[1:]):
                if current.sequence != previous.sequence + 1:
                    gap = True
                    break
        if gap:
            return {"entries": [], "gap": True, "cursor_before": cursor, "cursor_after": cursor}
        emitted = new[: min(limit, 128)]
        if emitted:
            self.cursor = emitted[-1].sequence
        return {
            "entries": emitted,
            "gap": False,
            "cursor_before": cursor,
            "cursor_after": cursor if not emitted else emitted[-1].sequence,
        }


def test_trace_rows_have_a_distinct_monotonic_stream_from_decisions():
    ring = TraceRing()
    ring.record(7)
    ring.record(7)
    ring.record(8)
    assert [row.sequence for row in ring.rows] == [1, 2, 3]
    assert [row.decision_sequence for row in ring.rows] == [7, 7, 8]
    assert "entry.Sequence = ++state.TraceSequence;" in MANAGER
    assert "entry.DecisionSequence = state.Sequence;" in MANAGER


def test_initial_ring_overwrite_fails_closed_without_advancing_cursor():
    ring = TraceRing()
    for decision in range(129):
        ring.record(decision)
    result = ring.delta(128)
    assert result["gap"] is True
    assert result["entries"] == []
    assert result["cursor_before"] == result["cursor_after"] == 0


def test_partial_batch_advances_only_through_last_emitted_row():
    ring = TraceRing()
    for decision in range(5):
        ring.record(decision)
    first = ring.delta(2)
    assert [row.sequence for row in first["entries"]] == [1, 2]
    assert first["cursor_after"] == 2
    second = ring.delta(128)
    assert [row.sequence for row in second["entries"]] == [3, 4, 5]
    assert second["cursor_after"] == 5


def test_later_gap_fails_closed_and_preserves_the_prior_cursor():
    ring = TraceRing()
    for decision in range(4):
        ring.record(decision)
    assert [row.sequence for row in ring.delta(1)["entries"]] == [1]
    ring.rows = [row for row in ring.rows if row.sequence != 2]
    result = ring.delta(128)
    assert result["gap"] is True
    assert result["entries"] == []
    assert result["cursor_before"] == result["cursor_after"] == 1


def test_delta_encoder_keeps_suppressed_repeatable_event_count_and_bound():
    assert "suppressed_repeatable_event_count" in MANAGER
    assert "SuppressedRepeatableDecisionCount" in TRACE_MODULE
    assert "coalesceRepeatable" in TRACE_MODULE
    assert "std::min<uint32>(limit, 128)" in MANAGER
    assert "TraceExportCursorByGuid.find" in MANAGER
    assert "if (!gap && cursorAfter != cursor)" in MANAGER


def test_repeatable_decisions_coalesce_without_losing_the_exact_count():
    ring = TraceRing()
    for decision in range(1000):
        ring.record(
            decision, key="validation_route_patrol_anchor_path_rejected",
            timestamp_ms=decision * 100, coalesce=True,
        )

    result = ring.delta(128)
    assert result["gap"] is False
    assert len(result["entries"]) < 128
    assert sum(row.suppressed_repeatable_decision_count for row in result["entries"]) == 980


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
