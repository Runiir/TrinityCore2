from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from math import isfinite
from pathlib import Path
import time
from typing import Any, Callable

try:
    from tools.raid_program.capture_runtime_identity import (
        _roster_binding_identity,
        _runtime_identity,
    )
    from tools.raid_program.capture_value_types import _positive_int
except ModuleNotFoundError:
    from capture_runtime_identity import _roster_binding_identity, _runtime_identity
    from capture_value_types import _positive_int

try:
    from tools.raid_program import trace_transport_smoke
except ModuleNotFoundError:
    import trace_transport_smoke




# The native trace export emits 128-record pages and retains up to 4096
# unexported records per bot. A fixed ten-second poll can still overflow that
# bounded pending queue after a burst before the adaptive pressure detector
# receives warning. Default to the existing two-second pressure cadence;
# explicit slower diagnostics still adapt at the watermark. A native ``gap``
# remains retained and rejected by the evidence gates.
TRACE_EXPORT_BATCH_SIZE = 128
TRACE_PENDING_CAPACITY = 4096
# Compatibility alias for report and test consumers which used the old name.
TRACE_RING_CAPACITY = TRACE_EXPORT_BATCH_SIZE
TRACE_PRESSURE_WATERMARK = trace_transport_smoke.PRESSURE_WATERMARK
TRACE_PRESSURE_INTERVAL_SEC = trace_transport_smoke.PRESSURE_INTERVAL_SECONDS


def _json_row_from_log_line(raw: bytes) -> dict[str, Any] | None:
    """Decode one complete worldserver log line when it contains JSON evidence."""

    start = raw.find(b"{")
    end = raw.rfind(b"}")
    if start < 0 or end < start:
        return None
    try:
        row = json.loads(raw[start : end + 1])
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    return row if isinstance(row, dict) else None


class JsonLogCursor:
    """Incrementally parse complete evidence lines from an append-only log.

    The canonical monitor used to reread and decode the complete growing log on
    every five-second probe.  That made parsing O(n^2) over a long uncapped
    run, while adding no evidence.  This cursor reads each byte once during
    monitoring and retains an incomplete final line until the next probe.  The
    final immutable artifact is still parsed from the complete log below, so
    this optimization cannot remove or rewrite a transition row.
    """

    def __init__(self, path: Path):
        self.path = path
        self.offset = 0
        self._partial = b""
        self._partial_first_byte_at: float | None = None

    def read_new_rows(self) -> list[dict[str, Any]]:
        return [observation.row for observation in self.read_new_observations()]

    def read_new_observations(
        self, *, observed_at: float | None = None,
    ) -> list[JsonLogObservation]:
        """Return complete JSON rows with byte and parser timing receipts."""

        observed_at = time.monotonic() if observed_at is None else observed_at
        with self.path.open("rb") as handle:
            handle.seek(self.offset)
            chunk = handle.read()
            self.offset = handle.tell()
        if not chunk:
            return []

        previous_partial = self._partial
        previous_partial_first_byte_at = self._partial_first_byte_at
        data = self._partial + chunk
        lines = data.splitlines(keepends=True)
        if lines and not lines[-1].endswith((b"\n", b"\r")):
            self._partial = lines.pop()
            self._partial_first_byte_at = (
                previous_partial_first_byte_at
                if previous_partial and not lines else observed_at
            )
        else:
            self._partial = b""
            self._partial_first_byte_at = None
        observations: list[JsonLogObservation] = []
        for index, raw in enumerate(lines):
            parse_started = time.perf_counter()
            row = _json_row_from_log_line(raw)
            parse_duration = time.perf_counter() - parse_started
            if row is not None:
                first_byte_at = observed_at
                if index == 0 and previous_partial:
                    first_byte_at = previous_partial_first_byte_at or observed_at
                observations.append(JsonLogObservation(
                    row=row,
                    response_bytes=len(raw),
                    response_sha256=hashlib.sha256(raw).hexdigest(),
                    first_byte_observed_at_monotonic=first_byte_at,
                    response_complete_observed_at_monotonic=observed_at,
                    parse_duration_seconds=parse_duration,
                ))
        return observations


@dataclass(frozen=True)
class JsonLogObservation:
    row: dict[str, Any]
    response_bytes: int
    response_sha256: str
    first_byte_observed_at_monotonic: float
    response_complete_observed_at_monotonic: float
    parse_duration_seconds: float


def collect_log_observations(
    cursor: JsonLogCursor,
    *,
    duration_seconds: float,
    poll_interval_seconds: float = 0.01,
) -> list[JsonLogObservation]:
    """Observe append timing without changing the controller's poll window."""

    deadline = time.monotonic() + duration_seconds
    observations: list[JsonLogObservation] = []
    while True:
        observations.extend(cursor.read_new_observations())
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_interval_seconds, remaining))
    return observations


class TelemetryTransportLedger:
    """Bind trace commands to bounded-observation and parser receipts."""

    def __init__(self) -> None:
        self._next_sequence = 1
        self._receipts: list[dict[str, Any]] = []
        self.observation_poll_interval_seconds = 0.01

    @staticmethod
    def _trace_identity(row: dict[str, Any]) -> dict[str, Any]:
        runtime = row.get("raid_runtime")
        runtime = runtime if isinstance(runtime, dict) else {}
        identity = {
            "cohort_id": row.get("cohort_id"),
            "server_epoch": row.get("server_epoch"),
            "attempt_id": row.get("attempt_id"),
            "instance_id": runtime.get("instance_id"),
            "runtime_profile": row.get("active_profile"),
            "active_profile": row.get("active_profile"),
            "assignment_generation": runtime.get("assignment_generation"),
            "profile_generation": row.get("profile_generation"),
            "profile_content_hash": row.get("profile_content_hash"),
        }
        actors = []
        for bot_row in row.get("bots", []):
            if not isinstance(bot_row, dict):
                continue
            entries = bot_row.get("entries")
            entries = entries if isinstance(entries, list) else []
            sequences = [
                entry.get("sequence") for entry in entries
                if isinstance(entry, dict)
                and isinstance(entry.get("sequence"), int)
                and not isinstance(entry.get("sequence"), bool)
            ]
            sequences_contiguous = (
                len(sequences) == len(entries)
                and (
                    not sequences
                    or sequences
                    == list(range(sequences[0], sequences[-1] + 1))
                )
            )
            discontinuity = bot_row.get("discontinuity")
            discontinuity = discontinuity if isinstance(discontinuity, dict) else {}
            actors.append({
                "bot_guid": bot_row.get("bot_guid"),
                "cursor_before": bot_row.get("cursor_before"),
                "cursor_after": bot_row.get("cursor_after"),
                "gap": bot_row.get("gap"),
                "entry_count": len(entries),
                "first_sequence": sequences[0] if sequences else None,
                "last_sequence": sequences[-1] if sequences else None,
                "sequences_contiguous": sequences_contiguous,
                **({
                    "pending_metadata_present": True,
                    "pending_entry_count_present": (
                        "pending_entry_count" in bot_row
                    ),
                    "newest_retained_sequence_present": (
                        "newest_retained_sequence" in bot_row
                    ),
                    **{
                        field: bot_row.get(field)
                        for field in (
                            "pending_entry_count", "newest_retained_sequence",
                        )
                    },
                } if any(
                    field in bot_row for field in (
                        "pending_entry_count", "newest_retained_sequence",
                    )
                ) else {}),
                **({
                    field: discontinuity.get(field)
                    for field in (
                        "missing_sequence_start", "missing_sequence_end",
                        "oldest_retained_sequence", "newest_retained_sequence",
                    )
                } if any(
                    field in discontinuity for field in (
                        "missing_sequence_start", "missing_sequence_end",
                        "oldest_retained_sequence", "newest_retained_sequence",
                    )
                ) else {}),
            })
        identity["actors"] = actors
        return identity

    def command_sent(
        self,
        commands: list[str],
        *,
        sent_at_monotonic: float,
        scheduler_state: dict[str, Any],
    ) -> None:
        trace_command = next(
            (command for command in commands if command.startswith("botauto trace ")),
            None,
        )
        if trace_command is None:
            return
        if self._receipts:
            previous = self._receipts[-1]
            if previous.get("next_command_sent_at_monotonic") is None:
                previous["next_command_sent_at_monotonic"] = sent_at_monotonic
                previous["next_command_delay_seconds"] = round(
                    sent_at_monotonic
                    - float(previous["command_sent_at_monotonic"]),
                    6,
                )
                completed_at = previous.get(
                    "response_complete_observed_at_monotonic"
                )
                if isinstance(completed_at, (int, float)):
                    previous["response_complete_to_next_send_seconds"] = round(
                        sent_at_monotonic - float(completed_at), 6,
                    )
        self._receipts.append({
            "command_sequence": self._next_sequence,
            "command": trace_command,
            "command_sent_at_monotonic": sent_at_monotonic,
            "response_first_byte_observed_at_monotonic": None,
            "response_complete_observed_at_monotonic": None,
            "observation_poll_interval_seconds": (
                self.observation_poll_interval_seconds
            ),
            "association_state": "awaiting_response",
            "next_command_sent_at_monotonic": None,
            "send_to_first_byte_observed_seconds": None,
            "observed_response_delivery_seconds": None,
            "response_complete_to_next_send_seconds": None,
            "response_bytes": None,
            "response_sha256": None,
            "parse_duration_seconds": None,
            "scheduler_state_at_send": dict(scheduler_state),
            "scheduler_state_after_response": None,
            "identity": None,
        })
        self._next_sequence += 1

    def observe(self, observation: JsonLogObservation) -> int | None:
        if observation.row.get("action") != "botauto_trace":
            return None
        pending = [
            (index, receipt) for index, receipt in enumerate(self._receipts)
            if receipt["response_complete_observed_at_monotonic"] is None
        ]
        if len(pending) != 1:
            for _, receipt in pending:
                receipt["association_state"] = "ambiguous_multiple_pending"
            return None
        index, receipt = pending[0]
        receipt.update({
            "response_first_byte_observed_at_monotonic": (
                observation.first_byte_observed_at_monotonic
            ),
            "response_complete_observed_at_monotonic": (
                observation.response_complete_observed_at_monotonic
            ),
            "send_to_first_byte_observed_seconds": round(
                observation.first_byte_observed_at_monotonic
                - float(receipt["command_sent_at_monotonic"]), 6,
            ),
            "observed_response_delivery_seconds": round(
                observation.response_complete_observed_at_monotonic
                - observation.first_byte_observed_at_monotonic, 6,
            ),
            "response_bytes": observation.response_bytes,
            "response_sha256": observation.response_sha256,
            "parse_duration_seconds": round(
                observation.parse_duration_seconds, 9,
            ),
            "identity": self._trace_identity(observation.row),
            "association_state": "bound_in_serial_command_order",
        })
        next_sent_at = receipt.get("next_command_sent_at_monotonic")
        if isinstance(next_sent_at, (int, float)):
            receipt["response_complete_to_next_send_seconds"] = round(
                float(next_sent_at)
                - observation.response_complete_observed_at_monotonic,
                6,
            )
        return index

    def finalize_responses(
        self, receipt_indexes: list[int], scheduler_state: dict[str, Any],
    ) -> None:
        for index in receipt_indexes:
            self._receipts[index]["scheduler_state_after_response"] = dict(
                scheduler_state
            )

    def receipts(self) -> list[dict[str, Any]]:
        return [dict(receipt) for receipt in self._receipts]


def json_actions(log_bytes: bytes, action: str) -> list[dict[str, Any]]:
    return [row for row in json_rows(log_bytes) if row.get("action") == action]


def json_rows(log_bytes: bytes) -> list[dict[str, Any]]:
    """Parse only complete JSON objects, retaining their log order."""

    rows: list[dict[str, Any]] = []
    for raw in log_bytes.splitlines():
        row = _json_row_from_log_line(raw)
        if row is not None:
            rows.append(row)
    return rows


def action_payloads(rows: list[dict[str, Any]], action: str) -> list[dict[str, Any]]:
    """Project already-parsed normalized evidence without reparsing its log."""

    payloads: list[dict[str, Any]] = []
    for row in rows:
        payload = row.get("payload")
        if isinstance(payload, dict) and payload.get("action") == action:
            payloads.append(payload)
    return payloads




def observe_telemetry_freshness(
    state: dict[str, dict[str, float | int]], counts: dict[str, int], now: float,
    timeout_seconds: float,
) -> list[str]:
    """Update per-channel heartbeats and return channels whose output is stale.

    The canonical raid runtime is intentionally uncapped, but its control and
    evidence channels are not. A live worldserver that stops producing any one
    of status, diagnosis, or trace evidence is an infrastructure failure, not a
    healthy long boss attempt.
    """
    stale: list[str] = []
    for channel in ("status", "diagnosis", "trace"):
        channel_state = state.setdefault(channel, {
            "count": 0,
            "last_observed_monotonic": now,
        })
        count = int(counts.get(channel, 0))
        if count > int(channel_state["count"]):
            channel_state["count"] = count
            channel_state["last_observed_monotonic"] = now
        if now - float(channel_state["last_observed_monotonic"]) > timeout_seconds:
            stale.append(channel)
    return stale


def material_status_signature(status: dict[str, Any]) -> str:
    """Return a stable signature for status changes that need a full diagnose.

    Status includes several heartbeat/evidence counters which change on every
    poll and must not turn the reduced steady-state cadence back into a full
    diagnose cadence. The fields below are the state edges that change the
    interpretation of a decision trace: route/encounter/boss lifecycle,
    roster/recovery state, and explicit errors. The complete status remains
    retained in the immutable evidence stream; this projection only controls
    when an additional command is requested.
    """
    runtime = status.get("raid_runtime") if isinstance(status.get("raid_runtime"), dict) else {}
    route = status.get("validation_route") if isinstance(status.get("validation_route"), dict) else {}
    error_fields = {
        "status_error": status.get("error"),
        "status_failure": status.get("failure"),
        "status_failure_reason": status.get("failure_reason"),
        "runtime_error": runtime.get("error"),
        "runtime_failure": runtime.get("failure"),
        "runtime_error_state": runtime.get("error_state"),
    }
    payload = {
        "ok": status.get("ok"),
        "active": runtime.get("active"),
        "route": {key: route.get(key) for key in (
            "manifest_index", "generation", "node_id", "kind", "manifest_complete",
            "terminal_evidence", "boss_death_evidence",
        )},
        "raid": {key: runtime.get(key) for key in (
            "map_id", "instance_id", "lockout_save_id", "strategy_id",
            "assignment_generation", "boss_states", "encounter_phase",
            "encounter_in_progress", "alive_size", "expected_size", "wipe_state",
            "recovery_state", "wipe_generation", "boss_reset_generation",
            "recovery_generation", "ready_check_satisfied", "roster_complete",
        )},
        # These fields are deliberately not heartbeat counters.  A hostile
        # that remains alive after a native wipe changes whether re-entry is
        # safe, while the reset generation and reason explain which native
        # edge produced that state.  Keep all known reason spellings so a
        # compact/full producer transition cannot hide a material edge.
        "native_hostile": {key: runtime.get(key) for key in (
            "native_hostile_activity_active",
            "native_hostile_activity_seen_at_wipe",
            "native_hostile_inactivity_observed",
            "native_hostile_reset_generation",
            "native_hostile_reset_generation_at_wipe",
            "native_hostile_activity_entry",
            "native_hostile_activity_guid",
            "native_hostile_activity_reason",
            "native_hostile_inactivity_reason",
            "native_hostile_reset_reason",
            "native_hostile_state_reason",
        )},
        # Recovery booleans alone cannot express a newly completed per-GUID
        # transition.  Include the ordered native sequence tuple for every
        # member; sorting makes status map iteration order immaterial.
        "native_recovery_members": sorted(
            [
                {
                    key: member.get(key)
                    for key in (
                        "guid", "wipe_generation", "death_sequence",
                        "corpse_sequence", "release_sequence", "runback_sequence",
                        "reentry_sequence", "resurrection_sequence",
                    )
                }
                for member in (runtime.get("native_recovery", {}).get("members", [])
                               if isinstance(runtime.get("native_recovery"), dict)
                               else [])
                if isinstance(member, dict)
            ],
            key=lambda member: int(member.get("guid") or 0),
        ),
        "errors": error_fields,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(canonical).hexdigest()


def drain_pending_trace_batches(
    initial_trace: tuple[dict[str, Any], float] | None,
    expected_status: dict[str, Any] | None,
    *,
    deadline_monotonic: float,
    send_delta: Callable[[], None],
    read_trace_response: Callable[[float], tuple[dict[str, Any], float] | None],
    monotonic: Callable[[], float] = time.monotonic,
    max_batches: int = 64,
) -> dict[str, Any]:
    """Drain every retained terminal trace page without changing cursor mode.

    New producers state how many rows remain after each page. Older producers
    are drained until they return fewer than the 128-row export limit. Every
    page remains identity-bound and an explicit gap is terminal. The native
    4096-row pending limit bounds server memory; this deadline bounds capture
    work if actors continue producing rows during shutdown.
    """

    rejections: list[str] = []
    batches: list[dict[str, Any]] = []
    expected_runtime = (
        expected_status.get("raid_runtime")
        if isinstance(expected_status, dict)
        and isinstance(expected_status.get("raid_runtime"), dict)
        else None
    )
    expected_identity = (
        _runtime_identity(expected_runtime, include_strategy=False)
        if expected_runtime is not None else None
    )
    expected_roster = (
        _roster_binding_identity(expected_runtime.get("roster"))
        if expected_runtime is not None
        and isinstance(expected_runtime.get("roster"), list)
        else None
    )
    expected_cohort = (
        expected_status.get("cohort_id")
        if isinstance(expected_status, dict) else None
    )
    expected_guids = {
        int(member[3]) for member in expected_roster or ()
        if _positive_int(member[3])
    }
    cursors: dict[int, int] = {}

    def reject(reason: str) -> None:
        if reason not in rejections:
            rejections.append(reason)

    if expected_identity is None or expected_roster is None or not expected_guids:
        reject("trace_drain_expected_identity_missing")
    if not isinstance(expected_cohort, str) or not expected_cohort:
        reject("trace_drain_expected_cohort_missing")

    def accept_page(row: dict[str, Any], observed_at: float) -> bool:
        if (
            not isinstance(observed_at, (int, float))
            or isinstance(observed_at, bool)
            or not isfinite(float(observed_at))
            or observed_at > deadline_monotonic
        ):
            reject("trace_drain_response_after_deadline")
        if row.get("action") != "botauto_trace" or row.get("ok") is not True:
            reject("trace_drain_response_envelope_invalid")
            return False
        runtime = row.get("raid_runtime")
        roster = runtime.get("roster") if isinstance(runtime, dict) else None
        if (
            not isinstance(runtime, dict)
            or _runtime_identity(runtime, include_strategy=False) != expected_identity
            or _roster_binding_identity(roster) != expected_roster
            or row.get("cohort_id") != expected_cohort
        ):
            reject("trace_drain_runtime_identity_mismatch")
        bot_rows = row.get("bots")
        if not isinstance(bot_rows, list):
            reject("trace_drain_bot_rows_missing")
            return False

        actor_rows: dict[int, dict[str, Any]] = {}
        entry_count = 0
        pending_counts: list[int] = []
        metadata_rows = 0
        for bot_row in bot_rows:
            if not isinstance(bot_row, dict):
                reject("trace_drain_bot_row_invalid")
                continue
            identity = bot_row.get("identity")
            guid = (
                identity.get("bot_guid")
                if isinstance(identity, dict) else bot_row.get("bot_guid")
            )
            if not _positive_int(guid):
                reject("trace_drain_bot_guid_invalid")
                continue
            guid = int(guid)
            if guid in actor_rows:
                reject("trace_drain_duplicate_bot_guid")
                continue
            actor_rows[guid] = bot_row
            if bot_row.get("gap") is True:
                reject("trace_drain_gap_observed")
            elif bot_row.get("gap") is not False:
                reject("trace_drain_gap_invalid")

            entries = bot_row.get("entries")
            if not isinstance(entries, list):
                reject("trace_drain_entries_invalid")
                entries = []
            entry_count = max(entry_count, len(entries))
            cursor_before = bot_row.get("cursor_before")
            cursor_after = bot_row.get("cursor_after")
            if not isinstance(cursor_before, int) or isinstance(cursor_before, bool) \
                    or not isinstance(cursor_after, int) or isinstance(cursor_after, bool):
                reject("trace_drain_cursor_invalid")
            else:
                if guid in cursors and cursor_before != cursors[guid]:
                    reject("trace_drain_cursor_discontinuity")
                sequences = [
                    entry.get("sequence") for entry in entries
                    if isinstance(entry, dict)
                    and isinstance(entry.get("sequence"), int)
                    and not isinstance(entry.get("sequence"), bool)
                ]
                if len(sequences) != len(entries) or any(
                    right != left + 1
                    for left, right in zip(sequences, sequences[1:])
                ):
                    reject("trace_drain_entry_sequence_invalid")
                elif entries and (
                    sequences[0] != cursor_before + 1
                    or sequences[-1] != cursor_after
                ):
                    reject("trace_drain_cursor_entry_mismatch")
                elif not entries and cursor_after != cursor_before:
                    reject("trace_drain_empty_cursor_advance")
                cursors[guid] = cursor_after
                for entry in entries:
                    actor = entry.get("actor") if isinstance(entry, dict) else None
                    if (
                        expected_runtime is None
                        or not isinstance(entry, dict)
                        or entry.get("server_epoch") != expected_runtime.get("server_epoch")
                        or entry.get("attempt_id") != expected_runtime.get("attempt_id")
                        or entry.get("cohort_id") != expected_cohort
                        or not isinstance(actor, dict)
                        or actor.get("guid") != guid
                        or actor.get("map_id") != expected_runtime.get("map_id")
                        or actor.get("instance_id") != expected_runtime.get("instance_id")
                    ):
                        reject("trace_drain_entry_identity_mismatch")
                        break

            has_pending = "pending_entry_count" in bot_row
            has_newest = "newest_retained_sequence" in bot_row
            if has_pending != has_newest:
                reject("trace_drain_pending_metadata_partial")
            elif has_pending:
                metadata_rows += 1
                pending = bot_row.get("pending_entry_count")
                newest = bot_row.get("newest_retained_sequence")
                if (
                    not isinstance(pending, int) or isinstance(pending, bool)
                    or pending < 0 or pending > TRACE_PENDING_CAPACITY
                    or not isinstance(newest, int) or isinstance(newest, bool)
                    or newest < 0
                ):
                    reject("trace_drain_pending_metadata_invalid")
                else:
                    pending_counts.append(pending)
                    if (
                        isinstance(cursor_after, int)
                        and newest - cursor_after != pending
                    ):
                        reject("trace_drain_newest_sequence_invalid")

        if set(actor_rows) != expected_guids:
            reject("trace_drain_roster_incomplete_or_unbound")
        if metadata_rows not in (0, len(bot_rows)):
            reject("trace_drain_pending_metadata_incomplete")
        legacy = metadata_rows == 0
        pending = max(pending_counts, default=None)
        needs_more = pending > 0 if pending is not None else entry_count >= TRACE_EXPORT_BATCH_SIZE
        batches.append({
            "observed_at_monotonic": observed_at,
            "actor_count": len(actor_rows),
            "entry_count_high_watermark": entry_count,
            "pending_entry_count_high_watermark": pending,
            "legacy_pending_inference": legacy,
            "needs_more": needs_more,
        })
        return needs_more

    if initial_trace is None:
        reject("trace_drain_initial_response_missing")
    else:
        needs_more = accept_page(*initial_trace)
        while needs_more and not rejections:
            if len(batches) >= max_batches:
                reject("trace_drain_batch_limit_exceeded")
                break
            if monotonic() >= deadline_monotonic:
                reject("trace_drain_deadline_exceeded")
                break
            send_delta()
            response = read_trace_response(deadline_monotonic)
            if response is None:
                reject("trace_drain_deadline_exceeded")
                break
            needs_more = accept_page(*response)

    pending_final = (
        batches[-1]["pending_entry_count_high_watermark"] if batches else None
    )
    return {
        "schema": "terminal_pending_trace_drain_v1",
        "requested": initial_trace is not None,
        "gate_passed": bool(batches) and not rejections and not batches[-1]["needs_more"],
        "batch_count": len(batches),
        "additional_delta_command_count": max(0, len(batches) - 1),
        "pending_entry_count_final": pending_final,
        "retention_capacity": TRACE_PENDING_CAPACITY,
        "export_batch_size": TRACE_EXPORT_BATCH_SIZE,
        "batches": batches,
        "rejections": rejections,
    }


@dataclass
class TelemetryScheduler:
    """Schedule independent evidence channels without losing transition edges.

    Status is the control heartbeat and remains frequent. Diagnose is the
    expensive semantic snapshot and trace is the append-only delta export. A
    material status edge promotes the next loop to an immediate diagnose;
    callers can also force both heavy channels before terminating on a stall.
    ``commands_due`` advances each channel independently, so a delayed
    diagnosis never delays status; ``observe_trace`` tightens polling when
    retained deltas approach the native ring limit.
    """

    status_interval_sec: float = 5.0
    # Full diagnosis and trace are materially larger than the status
    # heartbeat.  Keep their steady-state cadence deliberately sparse for an
    # uncapped raid; material status edges and the final forced bundle still
    # request them immediately, so this is a volume reduction rather than an
    # evidence reduction.
    diagnose_interval_sec: float = 30.0
    # Drain the 128-entry native ring before a first combat burst can overwrite
    # it. Delta exports retain the same events at this shorter cadence.
    trace_interval_sec: float = 2.0
    _next_status_at: float = 0.0
    _next_diagnose_at: float = 0.0
    _next_trace_at: float = 0.0
    _diagnose_forced: bool = True
    _trace_forced: bool = False
    _last_status_signature: str | None = None
    _trace_interval_override_sec: float | None = None
    _trace_pressure_entries: int = 0
    _trace_pending_entries: int = 0
    _trace_gap_observed: bool = False
    diagnosis_failure_cooldown_sec: float = 15.0
    _trace_context_diagnosis_pending: bool = False
    _next_trace_context_diagnosis_at: float = 0.0
    _last_trace_context_by_guid: dict[int, tuple[Any, Any]] | None = None
    _last_trace_sequence_by_guid: dict[int, int] | None = None
    _trace_context_trigger_count: int = 0

    def __post_init__(self) -> None:
        if (
            self.status_interval_sec <= 0 or self.diagnose_interval_sec <= 0
            or self.trace_interval_sec <= 0
            or self.diagnosis_failure_cooldown_sec <= 0
        ):
            raise ValueError("telemetry intervals must be positive")
        self._last_trace_context_by_guid = {}
        self._last_trace_sequence_by_guid = {}

    def observe_status(self, status: dict[str, Any]) -> bool:
        """Record a status and request immediate diagnosis on a material edge."""
        signature = material_status_signature(status)
        changed = self._last_status_signature is not None and signature != self._last_status_signature
        # The initial scheduler tick already includes one full diagnosis. A
        # later material edge must promote the next tick immediately.
        if changed:
            self._diagnose_forced = True
        self._last_status_signature = signature
        return changed

    def force_diagnosis(self, *, include_trace: bool = True) -> None:
        """Force a final semantic bundle before a stall/error termination."""
        self._diagnose_forced = True
        if include_trace:
            self._trace_forced = True

    def observe_trace(
        self,
        trace_rows: list[dict[str, Any]],
        *,
        observed_at: float | None = None,
    ) -> None:
        """Use retained delta size to bound the next trace-ring poll.

        The response is advisory input to scheduling only.  In particular,
        ``gap=true`` is remembered for diagnostics but never clears a cursor,
        marks a channel valid, or otherwise relaxes the demux gate.  Malformed
        rows cannot reduce the polling interval or create evidence.
        """

        pressure_entries = 0
        pending_entries = 0
        context_triggered = False
        last_context = self._last_trace_context_by_guid or {}
        last_sequences = self._last_trace_sequence_by_guid or {}
        for row in trace_rows:
            if not isinstance(row, dict):
                continue
            bots = row.get("bots")
            if not isinstance(bots, list):
                continue
            for bot_row in bots:
                if not isinstance(bot_row, dict):
                    continue
                if bot_row.get("gap") is True:
                    self._trace_gap_observed = True
                entries = bot_row.get("entries")
                if isinstance(entries, list):
                    pressure_entries = max(pressure_entries, len(entries))
                pending = bot_row.get("pending_entry_count")
                if isinstance(pending, int) and not isinstance(pending, bool):
                    pending_entries = max(pending_entries, pending)
                identity = bot_row.get("identity")
                guid = (
                    identity.get("bot_guid")
                    if isinstance(identity, dict) else bot_row.get("bot_guid")
                )
                if not _positive_int(guid) or not isinstance(entries, list):
                    continue
                guid = int(guid)
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    sequence = entry.get("sequence")
                    if (
                        not isinstance(sequence, int) or isinstance(sequence, bool)
                        or sequence <= last_sequences.get(guid, 0)
                    ):
                        continue
                    last_sequences[guid] = sequence
                    context = (entry.get("situation"), entry.get("mechanic_family"))
                    previous_context = last_context.get(guid)
                    if previous_context is not None and context != previous_context:
                        context_triggered = True
                    last_context[guid] = context
                    target_return = entry.get("target_return")
                    target_observation = (
                        target_return.get("observation")
                        if isinstance(target_return, dict) else None
                    )
                    captured_at = (
                        target_return.get("captured_at_ms")
                        if isinstance(target_return, dict) else None
                    )
                    target_observed_at = (
                        target_return.get("observed_at_ms")
                        if isinstance(target_return, dict) else None
                    )
                    target_age = (
                        target_return.get("age_ms")
                        if isinstance(target_return, dict) else None
                    )
                    if (
                        isinstance(target_return, dict)
                        and target_return.get("current_at_record") is True
                        and target_return.get("stale") is False
                        and isinstance(captured_at, int)
                        and not isinstance(captured_at, bool)
                        and isinstance(target_observed_at, int)
                        and not isinstance(target_observed_at, bool)
                        and 0 < target_observed_at <= captured_at
                        and isinstance(target_age, int)
                        and not isinstance(target_age, bool)
                        and target_age == captured_at - target_observed_at
                        and isinstance(target_observation, dict)
                        and target_observation.get("evaluated") is True
                        and target_observation.get("bind_result") in {
                            "native_missing", "native_dead", "native_invalid",
                            "invalid_payload",
                        }
                    ):
                        context_triggered = True
                    repeat_high_watermark = max(
                        int(entry.get(field) or 0)
                        for field in (
                            "fingerprint_failure_count", "fingerprint_repeat_count",
                            "consecutive_same_decision_count",
                            "suppressed_repeatable_decision_count",
                        )
                        if isinstance(entry.get(field), int)
                        and not isinstance(entry.get(field), bool)
                    ) if any(
                        isinstance(entry.get(field), int)
                        and not isinstance(entry.get(field), bool)
                        for field in (
                            "fingerprint_failure_count", "fingerprint_repeat_count",
                            "consecutive_same_decision_count",
                            "suppressed_repeatable_decision_count",
                        )
                    ) else 0
                    failure_value = " ".join(str(entry.get(field) or "").lower()
                        for field in ("result", "reason_code"))
                    if repeat_high_watermark >= 5 and any(
                        marker in failure_value
                        for marker in ("fail", "reject", "missing", "invalid", "blocked")
                    ):
                        context_triggered = True
                    death_value = " ".join(str(entry.get(field) or "").lower()
                        for field in ("action", "situation", "result", "reason_code"))
                    if any(marker in death_value for marker in (
                        "death", "repeated_death", "death_loop",
                    )):
                        context_triggered = True

        self._trace_pressure_entries = max(
            self._trace_pressure_entries, pressure_entries,
        )
        self._trace_pending_entries = pending_entries
        self._last_trace_context_by_guid = last_context
        self._last_trace_sequence_by_guid = last_sequences
        if pending_entries > 0:
            self._trace_forced = True
        if context_triggered:
            self._trace_context_diagnosis_pending = True
            self._trace_context_trigger_count += 1
        if pressure_entries < TRACE_PRESSURE_WATERMARK:
            return

        # Keep the configured cadence as the upper bound.  A caller can pass
        # a shorter interval for a diagnostic partition and it must not be
        # made slower by this adaptive path.
        hot_interval = min(self.trace_interval_sec, TRACE_PRESSURE_INTERVAL_SEC)
        self._trace_interval_override_sec = hot_interval
        if observed_at is not None:
            self._next_trace_at = min(self._next_trace_at, observed_at + hot_interval)

    def commands_due(self, now: float) -> list[str]:
        """Return due console commands and advance only their own deadlines."""
        commands: list[str] = []
        if now >= self._next_status_at:
            commands.append("botauto status")
            self._next_status_at = now + self.status_interval_sec
        if now >= self._next_trace_at or self._trace_forced:
            commands.append("botauto trace all 128 delta")
            trace_interval = self._trace_interval_override_sec or self.trace_interval_sec
            self._next_trace_at = now + trace_interval
            self._trace_forced = False
        trace_context_due = (
            self._trace_context_diagnosis_pending
            and now >= self._next_trace_context_diagnosis_at
        )
        if now >= self._next_diagnose_at or self._diagnose_forced or trace_context_due:
            commands.append("botauto diagnose all")
            self._next_diagnose_at = now + self.diagnose_interval_sec
            self._diagnose_forced = False
            if self._trace_context_diagnosis_pending:
                self._trace_context_diagnosis_pending = False
                self._next_trace_context_diagnosis_at = (
                    now + self.diagnosis_failure_cooldown_sec
                )
        return commands

    def state(self) -> dict[str, Any]:
        """Expose scheduler state for watchdog evidence and deterministic tests."""
        return {
            "status_interval_seconds": self.status_interval_sec,
            "diagnose_interval_seconds": self.diagnose_interval_sec,
            "trace_interval_seconds": self.trace_interval_sec,
            "next_status_at": self._next_status_at,
            "next_diagnose_at": self._next_diagnose_at,
            "next_trace_at": self._next_trace_at,
            "effective_trace_interval_seconds": (
                self._trace_interval_override_sec or self.trace_interval_sec
            ),
            "trace_pressure_entries": self._trace_pressure_entries,
            "trace_pending_entries": self._trace_pending_entries,
            "trace_gap_observed": self._trace_gap_observed,
            "trace_context_diagnosis_pending": self._trace_context_diagnosis_pending,
            "trace_context_trigger_count": self._trace_context_trigger_count,
            "next_trace_context_diagnosis_at": self._next_trace_context_diagnosis_at,
            "diagnosis_failure_cooldown_seconds": self.diagnosis_failure_cooldown_sec,
            "diagnose_forced": self._diagnose_forced,
            "trace_forced": self._trace_forced,
        }
