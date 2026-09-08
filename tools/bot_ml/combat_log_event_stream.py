"""Lossless transport and reconciliation for sequenced combat-log events.

The native combat-log command emits aggregate snapshots as a bounded chunked
export.  Delta exports use the same transport, but their decoded document is
``botauto_combatlog_delta`` and contains only sequenced events.  This module
keeps the two concerns separate: the terminal full document remains the source
of aggregate truth, while this accumulator retains event rows and reports any
transport discontinuity or conflict.
"""

from __future__ import annotations

from copy import deepcopy
import base64
from dataclasses import dataclass, field
import json
import time
from typing import Any, Callable, Iterable


MAX_DELTA_LIMIT = 4096
DELTA_ACTION = "botauto_combatlog_delta"
FULL_ACTION = "botauto_combatlog"
CHUNK_ACTION = "botauto_combatlog_chunk"
COMPLETE_ACTION = "botauto_combatlog_complete"


def _integer(value: Any, *, minimum: int = 0) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        return None
    return value


def _runtime_value(payload: dict[str, Any], field: str) -> Any:
    value = payload.get(field)
    if value is not None:
        return value
    runtime = payload.get("raid_runtime")
    if isinstance(runtime, dict):
        return runtime.get(field)
    return None


def combat_log_identity(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the native event-stream identity, excluding rotating run labels."""

    return {
        "cohort_id": _runtime_value(payload, "cohort_id"),
        "server_epoch": _runtime_value(payload, "server_epoch"),
        "attempt_id": _runtime_value(payload, "attempt_id"),
        "combat_log_epoch": _runtime_value(payload, "combat_log_epoch"),
    }


def _identity_key(identity: dict[str, Any]) -> tuple[Any, ...]:
    return tuple(identity.get(field) for field in (
        "cohort_id", "server_epoch", "attempt_id", "combat_log_epoch",
    ))


def _identity_complete(identity: dict[str, Any]) -> bool:
    return (
        isinstance(identity.get("cohort_id"), str)
        and bool(identity["cohort_id"])
        and _integer(identity.get("server_epoch"), minimum=1) is not None
        and _integer(identity.get("attempt_id"), minimum=1) is not None
        and _integer(identity.get("combat_log_epoch"), minimum=0) is not None
    )


def _profile_context(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "profile_generation": _runtime_value(payload, "profile_generation"),
        "profile_content_hash": _runtime_value(payload, "profile_content_hash"),
    }


def _context_complete(context: dict[str, Any]) -> bool:
    return (
        _integer(context.get("profile_generation"), minimum=1) is not None
        and isinstance(context.get("profile_content_hash"), str)
        and bool(context["profile_content_hash"])
    )


def combat_log_profile_context(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the profile context that accompanies a combat-log export."""

    return _profile_context(payload)


def is_full_combat_log_payload(payload: dict[str, Any]) -> bool:
    """Recognize current and legacy decoded full snapshots."""

    action = payload.get("action")
    schema = payload.get("combat_log_schema_version")
    schema_valid = (
        isinstance(schema, int)
        and not isinstance(schema, bool)
        and schema > 0
    ) or (action == FULL_ACTION and schema is None)
    return bool(
        payload.get("ok") is not False
        and schema_valid
        and action not in {DELTA_ACTION, CHUNK_ACTION, COMPLETE_ACTION}
        and ("event_count" in payload or "abilities" in payload)
    )


def _canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _event_sequence(event: dict[str, Any]) -> int | None:
    return _integer(event.get("event_sequence"), minimum=1)


def _event_rows(payload: dict[str, Any]) -> list[dict[str, Any]] | None:
    rows = payload.get("recent_events")
    if not isinstance(rows, list):
        return None
    return [row for row in rows if isinstance(row, dict)] if len(rows) == sum(
        isinstance(row, dict) for row in rows
    ) else None


def _compact_range(start: int, end: int) -> dict[str, int]:
    return {"start": int(start), "end": int(end)}


def _append_range(ranges: list[tuple[int, int]], start: int, end: int) -> None:
    if start > end:
        return
    pending = (int(start), int(end))
    merged: list[tuple[int, int]] = []
    for current in sorted([*ranges, pending]):
        if not merged or current[0] > merged[-1][1] + 1:
            merged.append(current)
        else:
            merged[-1] = (merged[-1][0], max(merged[-1][1], current[1]))
    ranges[:] = merged


def _record_discontinuity(
    discontinuities: list[dict[str, Any]], value: dict[str, Any],
) -> None:
    """Keep one record per missing range, preferring native detail."""

    start = _integer(value.get("missing_sequence_start"), minimum=1)
    end = _integer(value.get("missing_sequence_end"), minimum=1)
    if start is None or end is None or start > end:
        return
    for index, prior in enumerate(discontinuities):
        if (
            prior.get("missing_sequence_start") == start
            and prior.get("missing_sequence_end") == end
        ):
            if len(value) > len(prior):
                discontinuities[index] = deepcopy(value)
            return
    discontinuities.append(deepcopy(value))


@dataclass
class _Namespace:
    identity: dict[str, Any]
    context: dict[str, Any]
    cursor: int = 0
    event_count_at_export: int = 0
    events: dict[int, dict[str, Any]] = field(default_factory=dict)
    gaps: list[tuple[int, int]] = field(default_factory=list)
    discontinuities: list[dict[str, Any]] = field(default_factory=list)
    conflicts: list[int] = field(default_factory=list)
    duplicate_count: int = 0
    response_count: int = 0
    accepted_response_count: int = 0
    labels: list[dict[str, Any]] = field(default_factory=list)

    def receipt(self) -> dict[str, Any]:
        sequences = sorted(self.events)
        gap_ranges = [_compact_range(start, end) for start, end in self.gaps]
        conflict_sequences = sorted(set(self.conflicts))
        return {
            "identity": deepcopy(self.identity),
            "profile_context": deepcopy(self.context),
            "cursor": self.cursor,
            "event_count_at_export": self.event_count_at_export,
            "event_count": len(sequences),
            "first_sequence": sequences[0] if sequences else None,
            "last_sequence": sequences[-1] if sequences else None,
            "response_count": self.response_count,
            "accepted_response_count": self.accepted_response_count,
            "duplicate_count": self.duplicate_count,
            "conflict_sequences": conflict_sequences,
            "conflict_count": len(conflict_sequences),
            "gap_ranges": gap_ranges,
            "gaps": [
                {
                    "missing_sequence_start": row["start"],
                    "missing_sequence_end": row["end"],
                }
                for row in gap_ranges
            ],
            "gap_count": len(gap_ranges),
            "discontinuities": deepcopy(self.discontinuities),
            "labels": deepcopy(self.labels[-8:]),
        }


@dataclass(frozen=True)
class CombatLogDeltaResult:
    """Outcome of one completed chunked response."""

    response_complete: bool
    is_delta: bool
    accepted: bool
    needs_retry: bool
    cursor_before: int | None = None
    cursor_after: int | None = None
    event_count_at_export: int | None = None
    reason: str | None = None


class CombatLogEventStream:
    """Decode complete delta transfers and reconcile their event sequences.

    ``observe_rows`` represents one controller poll.  Chunks may arrive over
    several polls; the cursor only changes when a completion marker has yielded
    a valid decoded delta document.  A new native combat-log epoch receives a
    separate namespace, so a reset can never merge with the prior stream.
    """

    def __init__(self, *, expected_cohort_id: str | None = None) -> None:
        self.expected_cohort_id = expected_cohort_id
        self._expected_stable_identity: dict[str, Any] | None = None
        self._expected_context: dict[str, Any] | None = None
        self.poll_count = 0
        self._namespaces: dict[tuple[Any, ...], _Namespace] = {}
        self._active_key: tuple[Any, ...] | None = None
        self._pending_chunks: dict[int, dict[str, Any]] = {}
        self._pending_export_id: int | None = None
        self._latest_export_id: int = 0
        self._pending_chunk_count: int | None = None
        self._pending_cohort_id: str | None = None
        self._pending_kind: str | None = None
        self._pending_invalid = False
        self._pending_request = False
        self._full_exports: list[dict[str, Any]] = []
        self._saw_delta = False
        self._transport_rejections: list[str] = []
        self._response_results: list[CombatLogDeltaResult] = []
        self._accepted_events: list[dict[str, Any]] = []

    @property
    def cursor(self) -> int:
        namespace = self._active_namespace()
        return namespace.cursor if namespace is not None else 0

    @property
    def identity(self) -> dict[str, Any] | None:
        namespace = self._active_namespace()
        return deepcopy(namespace.identity) if namespace is not None else None

    @property
    def pending(self) -> bool:
        return self._pending_request

    @property
    def needs_retry(self) -> bool:
        return bool(self._response_results and self._response_results[-1].needs_retry)

    @property
    def decoded_exports(self) -> list[dict[str, Any]]:
        return [deepcopy(row) for row in self._full_exports]

    @property
    def saw_delta(self) -> bool:
        return self._saw_delta

    def bind_cohort(self, cohort_id: str | None) -> None:
        if isinstance(cohort_id, str) and cohort_id:
            self.expected_cohort_id = cohort_id

    def bind_identity(self, payload: dict[str, Any]) -> None:
        """Pin stable identity/context from an accepted status envelope."""

        identity = combat_log_identity(payload)
        self.expected_cohort_id = identity.get("cohort_id") or self.expected_cohort_id
        self._expected_stable_identity = {
            field: identity.get(field)
            for field in ("cohort_id", "server_epoch", "attempt_id")
        }
        self._expected_context = _profile_context(payload)

    def observe_rows(self, rows: Iterable[dict[str, Any]]) -> list[CombatLogDeltaResult]:
        self.poll_count += 1
        results: list[CombatLogDeltaResult] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            result = self.observe(row)
            if result is not None:
                results.append(result)
        return results

    def observe(self, row: dict[str, Any]) -> CombatLogDeltaResult | None:
        action = row.get("action")
        if is_full_combat_log_payload(row):
            self._full_exports.append(deepcopy(row))
            return None
        if action == DELTA_ACTION:
            self._saw_delta = True
            self._transport_rejections.append("unframed_delta_rejected")
            result = CombatLogDeltaResult(False, True, False, False, reason="unframed_delta_rejected")
            self._response_results.append(result)
            return result
        if action == CHUNK_ACTION:
            self._observe_chunk(row)
            return None
        if action != COMPLETE_ACTION:
            return None
        result = self._complete_attempt(row)
        if result.is_delta:
            self._response_results.append(result)
        return result

    def _active_namespace(self) -> _Namespace | None:
        return self._namespaces.get(self._active_key) if self._active_key is not None else None

    def _observe_chunk(self, row: dict[str, Any]) -> None:
        export_id = _integer(row.get("export_id"), minimum=1)
        if export_id is not None:
            if export_id < self._latest_export_id:
                return
            if export_id != self._pending_export_id:
                if self._pending_chunks:
                    self._transport_rejections.append("chunk_attempt_abandoned")
                self._reset_pending()
                self._pending_export_id = export_id
                self._latest_export_id = export_id
        if row.get("ok") is False:
            self._transport_rejections.append("chunk_response_not_ok")
            self._pending_invalid = True
            self._pending_request = True
            return
        schema = row.get("combat_log_chunk_schema_version")
        if schema is not None and schema != 1:
            self._transport_rejections.append("chunk_schema_version_invalid")
            self._pending_invalid = True
            self._pending_request = True
            return
        cohort_id = row.get("cohort_id")
        if cohort_id is not None and (
            not isinstance(cohort_id, str)
            or not cohort_id
            or (
                self.expected_cohort_id is not None
                and cohort_id != self.expected_cohort_id
            )
        ):
            self._transport_rejections.append("chunk_cohort_mismatch")
            self._pending_invalid = True
            self._pending_request = True
            return
        if (
            self._pending_cohort_id is not None
            and cohort_id is not None
            and cohort_id != self._pending_cohort_id
        ):
            self._transport_rejections.append("chunk_cohort_changed")
            self._pending_invalid = True
            self._pending_request = True
            return
        sequence = _integer(row.get("sequence"), minimum=0)
        count = _integer(row.get("chunk_count"), minimum=1)
        if sequence is None or count is None or sequence >= count:
            self._transport_rejections.append("chunk_sequence_invalid")
            self._pending_invalid = True
            self._pending_request = True
            return
        if row.get("encoding") != "base64" or not isinstance(row.get("data"), str):
            self._transport_rejections.append("chunk_encoding_invalid")
            self._pending_invalid = True
            self._pending_request = True
            return
        if self._pending_chunk_count is None:
            self._pending_chunk_count = count
            self._pending_cohort_id = cohort_id
            self._pending_kind = str(row.get("export_kind") or "") or None
        elif count != self._pending_chunk_count:
            # The canonical controller never overlaps requests.  A new
            # sequence-zero frame with a different count therefore marks the
            # abandoned transfer boundary before starting the next export.
            # Without that boundary, a bounded final delta could poison the
            # terminal full snapshot's otherwise valid framing.
            if sequence == 0:
                self._transport_rejections.append("chunk_attempt_restarted")
                self._reset_pending()
                self._pending_chunk_count = count
                self._pending_cohort_id = cohort_id
                self._pending_kind = str(row.get("export_kind") or "") or None
            else:
                self._transport_rejections.append("chunk_count_changed")
                self._pending_invalid = True
                self._pending_request = True
                return
        if self._pending_kind != (str(row.get("export_kind") or "") or None):
            self._transport_rejections.append("chunk_export_kind_changed")
            self._pending_invalid = True
        prior = self._pending_chunks.get(sequence)
        if prior is not None and prior.get("data") != row.get("data"):
            self._transport_rejections.append("chunk_conflict")
            self._pending_invalid = True
            self._pending_request = True
            return
        self._pending_chunks[sequence] = row
        self._pending_request = True

    def _complete_attempt(self, completion: dict[str, Any]) -> CombatLogDeltaResult:
        export_id = _integer(completion.get("export_id"), minimum=1)
        if export_id is not None and export_id != self._pending_export_id:
            return CombatLogDeltaResult(False, False, False, False, reason="foreign_completion")
        if completion.get("ok") is False:
            self._transport_rejections.append("complete_response_not_ok")
            self._pending_invalid = True
        completion_schema = completion.get("combat_log_chunk_schema_version")
        if completion_schema is not None and completion_schema != 1:
            self._transport_rejections.append("complete_schema_version_invalid")
            self._pending_invalid = True
        completion_cohort = completion.get("cohort_id")
        if completion_cohort is not None and (
            not isinstance(completion_cohort, str)
            or not completion_cohort
            or (
                self.expected_cohort_id is not None
                and completion_cohort != self.expected_cohort_id
            )
        ):
            self._transport_rejections.append("complete_cohort_mismatch")
            self._pending_invalid = True
        if (
            self._pending_cohort_id is not None
            and completion_cohort is not None
            and completion_cohort != self._pending_cohort_id
        ):
            self._transport_rejections.append("complete_cohort_changed")
            self._pending_invalid = True
        if self._pending_kind != (str(completion.get("export_kind") or "") or None):
            self._transport_rejections.append("complete_export_kind_changed")
            self._pending_invalid = True
        expected = _integer(completion.get("chunk_count"), minimum=1)
        if expected is None:
            expected = self._pending_chunk_count
        received = len(self._pending_chunks)
        if (
            self._pending_invalid
            or expected is None
            or received != expected
            or set(self._pending_chunks) != set(range(expected))
        ):
            self._transport_rejections.append("chunks_incomplete")
            result = CombatLogDeltaResult(
                response_complete=True,
                is_delta=self._pending_kind != "full",
                accepted=False,
                needs_retry=True,
                reason="chunks_incomplete",
            )
            self._reset_pending()
            return result
        raw_parts: list[bytes] = []
        try:
            for sequence in range(expected):
                raw_parts.append(base64.b64decode(
                    self._pending_chunks[sequence]["data"], validate=True,
                ))
            raw = b"".join(raw_parts)
            total_bytes = _integer(completion.get("total_bytes"), minimum=0)
            if total_bytes is not None and len(raw) != total_bytes:
                raise ValueError("total_bytes_mismatch")
            payload = json.loads(raw)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            result = CombatLogDeltaResult(
                response_complete=True,
                is_delta=self._pending_kind != "full",
                accepted=False,
                needs_retry=True,
                reason="chunk_payload_invalid",
            )
            self._reset_pending()
            return result
        kind = self._pending_kind
        self._reset_pending()
        if kind is not None and (
            not isinstance(payload, dict)
            or (kind == "delta" and payload.get("action") != DELTA_ACTION)
            or (kind == "full" and not is_full_combat_log_payload(payload))
            or kind not in {"delta", "full"}
        ):
            self._transport_rejections.append("chunk_payload_kind_conflict")
            return CombatLogDeltaResult(True, kind == "delta", False, True, reason="chunk_payload_kind_conflict")
        if isinstance(payload, dict) and payload.get("action") == DELTA_ACTION:
            self._saw_delta = True
            return self._accept_delta(payload)
        if isinstance(payload, dict) and is_full_combat_log_payload(payload):
            self._full_exports.append(deepcopy(payload))
            return CombatLogDeltaResult(
                response_complete=True,
                is_delta=False,
                accepted=True,
                needs_retry=False,
                reason="full_export_complete",
            )
        self._transport_rejections.append("chunk_payload_action_invalid")
        return CombatLogDeltaResult(
            response_complete=True,
            is_delta=False,
            accepted=False,
            needs_retry=False,
            reason="chunk_payload_action_invalid",
        )

    def _reset_pending(self) -> None:
        self._pending_chunks.clear()
        self._pending_export_id = None
        self._pending_chunk_count = None
        self._pending_cohort_id = None
        self._pending_kind = None
        self._pending_invalid = False
        self._pending_request = False

    def _namespace_for(self, payload: dict[str, Any]) -> _Namespace | None:
        identity = combat_log_identity(payload)
        if self.expected_cohort_id is not None and identity.get("cohort_id") != self.expected_cohort_id:
            self._transport_rejections.append("delta_cohort_mismatch")
            return None
        if not _identity_complete(identity):
            self._transport_rejections.append("delta_identity_incomplete")
            return None
        stable_identity = self._expected_stable_identity
        if stable_identity is None and self._active_key is not None:
            active = self._active_namespace()
            stable_identity = {
                field: active.identity.get(field) if active else None
                for field in ("cohort_id", "server_epoch", "attempt_id")
            }
        if stable_identity is not None:
            if any(
                stable_identity.get(field) is None
                or identity.get(field) != stable_identity.get(field)
                for field in ("cohort_id", "server_epoch", "attempt_id")
            ):
                self._transport_rejections.append("delta_stable_identity_conflict")
                return None
        expected_context = self._expected_context
        context = _profile_context(payload)
        if expected_context is None and self._active_key is not None:
            active = self._active_namespace()
            expected_context = deepcopy(active.context) if active else None
        if expected_context is not None:
            if not _context_complete(expected_context) or context != expected_context:
                self._transport_rejections.append("delta_profile_context_conflict")
                return None
        elif not _context_complete(context):
            self._transport_rejections.append("delta_profile_context_missing")
            return None
        key = _identity_key(identity)
        namespace = self._namespaces.get(key)
        if namespace is None:
            namespace = _Namespace(identity=identity, context=context)
            self._namespaces[key] = namespace
        self._active_key = key
        if namespace.context != context:
            namespace.conflicts.append(-1)
            self._transport_rejections.append("delta_profile_context_conflict")
            return None
        return namespace

    def _accept_delta(self, payload: dict[str, Any]) -> CombatLogDeltaResult:
        previous_key = self._active_key
        namespace = self._namespace_for(payload)
        cursor_before = _integer(payload.get("cursor_before"), minimum=0)
        cursor_after = _integer(payload.get("cursor_after"), minimum=0)
        event_count = _integer(payload.get("event_count_at_export"), minimum=0)
        if namespace is None:
            return CombatLogDeltaResult(
                response_complete=True, is_delta=True, accepted=False,
                needs_retry=False, cursor_before=cursor_before,
                cursor_after=cursor_after, event_count_at_export=event_count,
                reason="identity_rejected",
            )
        namespace.response_count += 1
        rows = _event_rows(payload)
        if (
            payload.get("ok") is not True
            or payload.get("combat_log_schema_version") != 3
            or cursor_before is None
            or cursor_after is None
            or event_count is None
            or rows is None
        ):
            if payload.get("ok") is not True:
                self._transport_rejections.append("delta_response_not_ok")
            if payload.get("combat_log_schema_version") != 3:
                self._transport_rejections.append("delta_schema_version_invalid")
            self._transport_rejections.append("delta_cursor_or_events_invalid")
            return CombatLogDeltaResult(
                response_complete=True, is_delta=True, accepted=False,
                needs_retry=True, cursor_before=cursor_before,
                cursor_after=cursor_after, event_count_at_export=event_count,
                reason="delta_fields_invalid",
            )
        if (
            previous_key is not None and previous_key != self._active_key
            and namespace.accepted_response_count == 0 and cursor_before != 0
        ):
            return CombatLogDeltaResult(
                True, True, False, True, cursor_before, 0, event_count,
                "combat_log_epoch_reset_discovered",
            )
        if cursor_after < cursor_before or cursor_after > event_count:
            self._transport_rejections.append("delta_cursor_bounds_invalid")
            return CombatLogDeltaResult(
                response_complete=True, is_delta=True, accepted=False,
                needs_retry=True, cursor_before=cursor_before,
                cursor_after=cursor_after, event_count_at_export=event_count,
                reason="delta_cursor_bounds_invalid",
            )
        parsed_events: list[tuple[int, dict[str, Any], str]] = []
        for event in rows:
            sequence = _event_sequence(event)
            if sequence is None:
                self._transport_rejections.append("delta_event_sequence_invalid")
                return CombatLogDeltaResult(
                    response_complete=True, is_delta=True, accepted=False,
                    needs_retry=True, cursor_before=cursor_before,
                    cursor_after=cursor_after, event_count_at_export=event_count,
                    reason="delta_event_sequence_invalid",
                )
            parsed_events.append((sequence, event, _canonical(event)))
        sequence_values = [sequence for sequence, _, _ in parsed_events]
        if (
            any(sequence > cursor_after for sequence in sequence_values)
            or (sequence_values and max(sequence_values) != cursor_after)
            or (not sequence_values and cursor_after != cursor_before)
            or len(sequence_values) > MAX_DELTA_LIMIT
        ):
            self._transport_rejections.append("delta_event_cursor_mismatch")
            return CombatLogDeltaResult(True, True, False, True, reason="delta_event_cursor_mismatch")
        copies: dict[int, str] = {}
        internal_conflicts = []
        for sequence, _, encoded in parsed_events:
            if sequence in copies and copies[sequence] != encoded:
                internal_conflicts.append(sequence)
            copies[sequence] = encoded
        conflicts = internal_conflicts + [
            sequence for sequence, _, encoded in parsed_events
            if sequence in namespace.events and _canonical(namespace.events[sequence]) != encoded
        ]
        if conflicts:
            namespace.conflicts.extend(conflicts)
            self._transport_rejections.append("delta_event_conflict")
            return CombatLogDeltaResult(
                response_complete=True, is_delta=True, accepted=False,
                needs_retry=False, cursor_before=cursor_before,
                cursor_after=cursor_after, event_count_at_export=event_count,
                reason="delta_event_conflict",
            )

        suffix = sorted({sequence for sequence in sequence_values if sequence > cursor_before})
        if suffix and any(current != prior + 1 for prior, current in zip(suffix, suffix[1:])):
            self._transport_rejections.append("delta_noncontiguous_suffix")
            return CombatLogDeltaResult(True, True, False, True, reason="delta_noncontiguous_suffix")
        known_before = namespace.cursor
        sequence_values = sorted({sequence for sequence, _, _ in parsed_events})
        expected_first = max(known_before, cursor_before) + 1
        new_values = [sequence for sequence in sequence_values if sequence > known_before]
        if new_values:
            if new_values[0] > expected_first:
                _append_range(namespace.gaps, expected_first, new_values[0] - 1)
                _record_discontinuity(namespace.discontinuities, {
                    "missing_sequence_start": expected_first,
                    "missing_sequence_end": new_values[0] - 1,
                })
            for prior, current in zip(new_values, new_values[1:]):
                if current > prior + 1:
                    _append_range(namespace.gaps, prior + 1, current - 1)
                    _record_discontinuity(namespace.discontinuities, {
                        "missing_sequence_start": prior + 1,
                        "missing_sequence_end": current - 1,
                    })
        discontinuity = payload.get("discontinuity")
        if payload.get("gap") is True and isinstance(discontinuity, dict):
            missing_start = _integer(discontinuity.get("missing_sequence_start"), minimum=1)
            missing_end = _integer(discontinuity.get("missing_sequence_end"), minimum=1)
            if (
                missing_start is not None and missing_end is not None
                and missing_start <= missing_end
            ):
                _append_range(namespace.gaps, missing_start, missing_end)
                _record_discontinuity(namespace.discontinuities, discontinuity)
            else:
                self._transport_rejections.append("delta_discontinuity_invalid")
                return CombatLogDeltaResult(
                    response_complete=True, is_delta=True, accepted=False,
                    needs_retry=True, cursor_before=cursor_before,
                    cursor_after=cursor_after,
                    event_count_at_export=event_count,
                    reason="delta_discontinuity_invalid",
                )
        elif payload.get("gap") is True:
            self._transport_rejections.append("delta_discontinuity_missing")
            return CombatLogDeltaResult(
                response_complete=True, is_delta=True, accepted=False,
                needs_retry=True, cursor_before=cursor_before,
                cursor_after=cursor_after, event_count_at_export=event_count,
                reason="delta_discontinuity_missing",
            )
        if cursor_before > known_before:
            _append_range(namespace.gaps, known_before + 1, cursor_before)
            _record_discontinuity(namespace.discontinuities, {
                "missing_sequence_start": known_before + 1,
                "missing_sequence_end": cursor_before,
            })
        last_emitted = max(sequence_values, default=known_before)
        if cursor_after > last_emitted and cursor_after > known_before:
            _append_range(namespace.gaps, last_emitted + 1, cursor_after)
            _record_discontinuity(namespace.discontinuities, {
                "missing_sequence_start": last_emitted + 1,
                "missing_sequence_end": cursor_after,
            })
        for sequence, event, _ in parsed_events:
            if sequence in namespace.events:
                namespace.duplicate_count += 1
            else:
                namespace.events[sequence] = deepcopy(event)
                self._accepted_events.append({"identity": deepcopy(namespace.identity),
                    "profile_context": deepcopy(namespace.context), "event": deepcopy(event)})
        namespace.cursor = max(namespace.cursor, cursor_after)
        namespace.event_count_at_export = max(namespace.event_count_at_export, event_count)
        namespace.response_count += 0
        namespace.accepted_response_count += 1
        label = {
            "experiment_id": payload.get("experiment_id"),
            "run_id": payload.get("run_id"),
        }
        if label not in namespace.labels:
            namespace.labels.append(label)
        return CombatLogDeltaResult(
            response_complete=True, is_delta=True, accepted=True,
            needs_retry=cursor_after < event_count,
            cursor_before=cursor_before, cursor_after=cursor_after,
            event_count_at_export=event_count, reason="delta_accepted",
        )

    def take_accepted_events(self) -> list[dict[str, Any]]:
        """Drain new rows from completed, gap-free identity-bound deltas only."""
        rows, self._accepted_events = self._accepted_events, []
        receipt = self.receipt()
        if receipt.get("transport_rejections") or receipt.get("gap_ranges") or receipt.get("conflict_sequences"):
            return []
        return [row for row in rows if row["identity"] == self.identity]

    def events(self, identity: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        namespace = (
            self._namespaces.get(_identity_key(identity))
            if identity is not None else self._active_namespace()
        )
        if namespace is None:
            return []
        return [deepcopy(namespace.events[sequence]) for sequence in sorted(namespace.events)]

    def namespace_receipt(self, identity: dict[str, Any] | None = None) -> dict[str, Any] | None:
        namespace = (
            self._namespaces.get(_identity_key(identity))
            if identity is not None else self._active_namespace()
        )
        return namespace.receipt() if namespace is not None else None

    def receipt(self, identity: dict[str, Any] | None = None) -> dict[str, Any]:
        namespace = (
            self._namespaces.get(_identity_key(identity))
            if identity is not None else self._active_namespace()
        )
        selected = namespace.receipt() if namespace is not None else None
        receipt = {
            "schema": "combat_log_event_stream_v1",
            "identity": selected.get("identity") if selected else None,
            "profile_context": selected.get("profile_context") if selected else None,
            "namespace_count": len(self._namespaces),
            "poll_count": self.poll_count,
            "pending": self.pending,
            "transport_rejections": list(dict.fromkeys(self._transport_rejections)),
            "response_count": len(self._response_results),
            "accepted_response_count": sum(
                result.accepted and result.is_delta for result in self._response_results
            ),
            "retry_count": sum(result.needs_retry for result in self._response_results),
            "namespace": selected,
            "complete": bool(
                selected
                and selected["accepted_response_count"] > 0
                and selected["event_count"] == selected["event_count_at_export"]
                and (selected["event_count"] == 0 or (
                    selected["first_sequence"] == 1
                    and selected["last_sequence"] == selected["event_count_at_export"]
                ))
                and selected["cursor"] >= selected["event_count_at_export"]
                and not self.pending
                and not selected["conflict_sequences"]
                and not selected["gap_ranges"]
                and not self._transport_rejections
            ),
        }
        if selected is not None:
            receipt.update({
                "cursor": selected["cursor"],
                "cursor_after": selected["cursor"],
                "event_count": selected["event_count"],
                "event_count_at_export": selected["event_count_at_export"],
                "duplicate_count": selected["duplicate_count"],
                "conflict_sequences": selected["conflict_sequences"],
                "conflict_count": selected["conflict_count"],
                "gap_ranges": selected["gap_ranges"],
                "gaps": selected["gaps"],
                "gap_count": selected["gap_count"],
                "discontinuities": selected["discontinuities"],
            })
        return receipt

    def abort_pending(self, reason: str = "delta_transfer_abandoned") -> None:
        """Discard an unfinished transfer before a later command begins."""

        self._transport_rejections.append(str(reason))
        self._reset_pending()


class CombatLogDeltaController:
    """Bind and schedule one in-flight native delta request for capture."""

    def __init__(
        self,
        *,
        send_commands: Callable[[list[str]], None],
        read_rows: Callable[[], list[dict[str, Any]]],
        command_counts: dict[str, int],
        trace_interval_seconds: float = 2.0,
        clock: Callable[[], float] | None = None,
        sleeper: Callable[[float], None] | None = None,
    ) -> None:
        self.stream = CombatLogEventStream()
        self._send_commands = send_commands
        self._read_rows = read_rows
        self._command_counts = command_counts
        self._interval = min(2.0, max(0.25, float(trace_interval_seconds)))
        self._clock = clock or time.monotonic
        self._sleep = sleeper or time.sleep
        self.cohort_id: str | None = None
        self.accepted_status: dict[str, Any] | None = None
        self._in_flight = False
        self._due = False
        self._next_at = 0.0

    def bind_active_status(
        self, status: dict[str, Any], *, profile_name: str, scenario_id: str,
        route_manifest_sha256: str | None,
    ) -> None:
        """Bind collection at native admission, independently of route success."""
        if self.cohort_id is not None:
            return
        from tools.raid_program.capture_runtime_identity import (
            _runtime_identity, _roster_binding_identity, _roster_binding_lifecycle_rejections,
        )
        runtime = status.get("raid_runtime")
        if not isinstance(runtime, dict):
            return
        admission = runtime.get("admission_receipt")
        roster = runtime.get("roster")
        if not isinstance(admission, dict) or not isinstance(roster, list):
            return
        identity = combat_log_identity(status)
        context = _profile_context(status)
        stable_fields = ("server_epoch", "attempt_id", "profile_generation", "profile_content_hash")
        expected_admission = {
            field: runtime.get(field) for field in (*stable_fields, "group_guid", "instance_id", "leader_guid")
        }
        expected_admission.update(scenario_id=scenario_id, runtime_profile=profile_name,
                                  route_manifest_sha256=route_manifest_sha256)
        if not (
            status.get("ok") is True and status.get("action") == "botauto_status"
            and status.get("active_profile") == profile_name
            and isinstance(identity["cohort_id"], str) and bool(identity["cohort_id"])
            and _context_complete(context)
            and all(_integer(runtime.get(field), minimum=1) is not None
                    for field in ("server_epoch", "attempt_id", "group_guid", "instance_id", "leader_guid"))
            and all(status.get(field) == runtime.get(field) for field in stable_fields)
            and runtime.get("active") is True and runtime.get("admission_phase") == "active"
            and runtime.get("server_provisioning_complete") is True
            and runtime.get("bot_actions_enabled") is True
            and _runtime_identity(runtime) is not None
            and _roster_binding_identity(roster) is not None
            and not _roster_binding_lifecycle_rejections(roster)
            and runtime.get("roster_complete") is True and runtime.get("unique_leases") is True
            and status.get("bots") == status.get("lease_count") == runtime.get("expected_size") == 10
            and _integer(admission.get("committed_at_ms"), minimum=1) is not None
            and admission.get("bot_actions_enabled_at_commit") is True
            and isinstance(admission.get("members"), list)
            and len(admission["members"]) == len(roster)
            and {row.get("guid") for row in admission["members"] if isinstance(row, dict)}
                == {row.get("guid") for row in roster}
            and isinstance(route_manifest_sha256, str) and bool(route_manifest_sha256)
            and all(admission.get(field) == value for field, value in expected_admission.items())
        ):
            return
        self.bind_status(status)
        self.accepted_status = deepcopy(status)

    def bind_status(self, status: dict[str, Any]) -> None:
        if self.cohort_id is not None:
            return
        identity = combat_log_identity(status)
        cohort_id = identity.get("cohort_id")
        if isinstance(cohort_id, str) and cohort_id:
            self.cohort_id = cohort_id
            self.stream.bind_identity(status)
            self._due = True

    def observe_rows(self, rows: list[dict[str, Any]]) -> None:
        if self.cohort_id is None:
            return
        for result in self.stream.observe_rows(rows):
            if not result.response_complete or not result.is_delta:
                continue
            self._in_flight = False
            if result.is_delta and result.needs_retry:
                self._due = True

    def append_command(
        self, commands: list[str], *, now: float | None = None, force: bool = False,
    ) -> bool:
        if not self.cohort_id or self._in_flight:
            return False
        now = self._clock() if now is None else now
        if not force and not self._due and now < self._next_at:
            return False
        commands.append(
            f"botauto combatlog {self.cohort_id} delta {self.stream.cursor} {MAX_DELTA_LIMIT}"
        )
        self._in_flight = True
        self._due = False
        self._next_at = now + self._interval
        self._command_counts["combat_log_delta"] = (
            self._command_counts.get("combat_log_delta", 0) + 1
        )
        return True

    def drain_final(self, deadline: float) -> dict[str, Any]:
        if not self.cohort_id:
            return {
                "requested": False,
                "rejections": ["combat_log_delta_cohort_unbound"],
            }
        sent = False
        abandoned = False
        while self._clock() < deadline:
            if not self._in_flight and (not sent or self._due):
                commands: list[str] = []
                if not self.append_command(commands, force=True):
                    break
                sent = True
                self._send_commands(commands)
            self._sleep(min(0.25, max(0.0, deadline - self._clock())))
            self.observe_rows(self._read_rows())
            if sent and not self._in_flight and not self._due:
                break
        receipt = self.stream.receipt()
        if self._in_flight:
            self.stream.abort_pending()
            self._in_flight = False
            self._due = False
            abandoned = True
            receipt = self.stream.receipt()
        receipt["requested"] = sent
        receipt["completed_before_deadline"] = bool(
            sent and not self._in_flight and not abandoned
        )
        return receipt


def merge_event_rows(
    full_events: Iterable[dict[str, Any]],
    delta_events: Iterable[dict[str, Any]],
    *,
    conflicts: list[int] | None = None,
) -> list[dict[str, Any]]:
    """Union sequenced events with the native ring tail, preserving exact rows."""

    full = [deepcopy(row) for row in full_events if isinstance(row, dict)]
    sequenced: dict[int, dict[str, Any]] = {}
    unsequenced: list[dict[str, Any]] = []
    for row in full:
        sequence = _event_sequence(row)
        if sequence is None:
            unsequenced.append(row)
            continue
        prior = sequenced.get(sequence)
        if prior is None:
            sequenced[sequence] = row
        elif _canonical(prior) != _canonical(row) and conflicts is not None:
            conflicts.append(sequence)
    for row in delta_events:
        if not isinstance(row, dict):
            continue
        sequence = _event_sequence(row)
        if sequence is None:
            unsequenced.append(deepcopy(row))
            continue
        prior = sequenced.get(sequence)
        if prior is None:
            sequenced[sequence] = deepcopy(row)
        elif _canonical(prior) != _canonical(row) and conflicts is not None:
            conflicts.append(sequence)
    return [sequenced[sequence] for sequence in sorted(sequenced)] + unsequenced


def stream_from_rows(
    rows: Iterable[dict[str, Any]], *, expected_cohort_id: str | None = None,
) -> CombatLogEventStream:
    stream = CombatLogEventStream(expected_cohort_id=expected_cohort_id)
    stream.observe_rows(rows)
    return stream
