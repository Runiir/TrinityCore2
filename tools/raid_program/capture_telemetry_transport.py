from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import time
from typing import Any

try:
    from tools.raid_program import trace_transport_smoke
except ModuleNotFoundError:
    import trace_transport_smoke




# The native trace export is backed by a 128-entry per-bot ring.  A fixed
# ten-second poll is normally cheap, but a busy bot can approach that ring's
# capacity after a quiet interval.  Once a response reaches this conservative
# watermark, switch to a bounded faster cadence so later exports retain
# headroom.  This only changes collection frequency; a native ``gap`` is still
# retained and rejected by the evidence gates.
TRACE_RING_CAPACITY = 128
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
                if isinstance(entry, dict) and isinstance(entry.get("sequence"), int)
            ]
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
    # The native decision trace is a 128-entry ring.  Keep the normal delta
    # cadence at ten seconds to limit payload volume; observe_trace switches
    # to a bounded faster cadence when a response approaches ring pressure.
    trace_interval_sec: float = 10.0
    _next_status_at: float = 0.0
    _next_diagnose_at: float = 0.0
    _next_trace_at: float = 0.0
    _diagnose_forced: bool = True
    _trace_forced: bool = False
    _last_status_signature: str | None = None
    _trace_interval_override_sec: float | None = None
    _trace_pressure_entries: int = 0
    _trace_gap_observed: bool = False
    _trace_full_forced: bool = False

    def __post_init__(self) -> None:
        if self.status_interval_sec <= 0 or self.diagnose_interval_sec <= 0 or self.trace_interval_sec <= 0:
            raise ValueError("telemetry intervals must be positive")

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
            # A delta request cannot recover a cursor that has already fallen
            # behind the bounded native ring.  Use one bounded full snapshot
            # for the terminal bundle in that case.  The response validator
            # still rejects an explicit native gap, so this is not an evidence
            # waiver; it is the only capture-side recovery after pressure.
            self._trace_full_forced = (
                self._trace_gap_observed
                or self._trace_pressure_entries >= TRACE_PRESSURE_WATERMARK
            )

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

        self._trace_pressure_entries = max(
            self._trace_pressure_entries, pressure_entries,
        )
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
            commands.append(
                "botauto trace all 128"
                if self._trace_full_forced
                else "botauto trace all 128 delta"
            )
            trace_interval = self._trace_interval_override_sec or self.trace_interval_sec
            self._next_trace_at = now + trace_interval
            self._trace_forced = False
            self._trace_full_forced = False
        if now >= self._next_diagnose_at or self._diagnose_forced:
            commands.append("botauto diagnose all")
            self._next_diagnose_at = now + self.diagnose_interval_sec
            self._diagnose_forced = False
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
            "trace_gap_observed": self._trace_gap_observed,
            "trace_full_forced": self._trace_full_forced,
            "diagnose_forced": self._diagnose_forced,
            "trace_forced": self._trace_forced,
        }
