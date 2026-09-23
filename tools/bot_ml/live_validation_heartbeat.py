"""Heartbeat command planning, timing receipts and trace retention.

Every console command runs inside ``World::Update`` and its response is
printed on the world thread.  The Magmaw 10N evidence (base1/sq1/sq2/sq3)
showed that a full heartbeat (status 0.1 MB, ``diagnose all`` 1.0 MB,
``trace all 128 delta`` 12.65 MB, summary 1 KB) froze the world for
3.6-12.3 s per in-combat heartbeat.  While the cohort is fighting, or a boss
route node is waiting for its pull, the planner keeps the full status,
diagnosis and summary snapshots but replaces the 1280-row trace delta with
the newest ``LIGHT_TRACE_LIMIT`` rows per bot (a non-delta tail that leaves
the server-side export cursor untouched, so no delta row is lost).
"""
from __future__ import annotations

import gzip
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

LIGHT_TRACE_LIMIT = 8
HEARTBEAT_COMMAND_TIMINGS_FILE = "heartbeat_command_timings.jsonl"
TRACE_HISTORY_FILE = "trace_history.jsonl.gz"
TRACE_HISTORY_MAX_DRAIN_CALLS = 24
READY_RECOVERY_STATES = frozenset({"", "none", "recovered_ready_check"})
PRE_PULL_WIPE_STATES = frozenset({"", "ready", "engaged"})

PayloadParser = Callable[[str], list[dict[str, Any]]]


def now_ms() -> int:
    return int(time.time() * 1000)


def command_tokens(command_text: str) -> list[str]:
    return str(command_text or "").split()


def is_status_command(command_text: str) -> bool:
    return command_tokens(command_text)[:2] == [".botauto", "status"]


def is_trace_command(command_text: str) -> bool:
    return command_tokens(command_text)[:2] == [".botauto", "trace"]


def light_trace_command(command_text: str, limit: int = LIGHT_TRACE_LIMIT) -> str:
    """Return the non-delta newest-row tail for one configured trace command."""
    tokens = command_tokens(command_text)
    if tokens[:2] != [".botauto", "trace"]:
        return command_text
    if tokens and tokens[-1] == "delta":
        tokens = tokens[:-1]
    for index in range(len(tokens) - 1, 1, -1):
        if tokens[index].isdigit():
            tokens[index] = str(max(1, min(int(tokens[index]), int(limit))))
            return " ".join(tokens)
    return command_text


def latest_status_payload(output: str, parse: PayloadParser) -> dict[str, Any] | None:
    for row in reversed(parse(output)):
        if isinstance(row, dict) and row.get("action") == "botauto_status":
            return row
    return None


def combat_activity(status: Mapping[str, Any] | None) -> dict[str, Any]:
    """Classify whether a heartbeat would land inside live combat.

    ``native_hostile_activity_active`` covers trash and boss combat inside the
    native instance, ``encounter_in_progress`` and ``wipe_state == engaged``
    cover a boss encounter.  A boss route node that is ready but not yet
    complete is also light: its pull can start at any tick.
    """
    reasons: list[str] = []
    if not isinstance(status, Mapping):
        return {"active": False, "reasons": reasons}
    runtime = status.get("raid_runtime")
    runtime = runtime if isinstance(runtime, Mapping) else {}
    route = status.get("validation_route")
    route = route if isinstance(route, Mapping) else {}
    if runtime.get("native_hostile_activity_active") is True:
        reasons.append("native_hostile_activity_active")
    if runtime.get("encounter_in_progress") is True:
        reasons.append("encounter_in_progress")
    wipe_state = str(runtime.get("wipe_state") or "")
    if wipe_state == "engaged":
        reasons.append("wipe_state_engaged")
    recovery_state = str(runtime.get("recovery_state") or "")
    if (
        str(route.get("kind") or "").lower() == "boss"
        and route.get("manifest_complete") is not True
        and wipe_state in PRE_PULL_WIPE_STATES
        and recovery_state in READY_RECOVERY_STATES
    ):
        reasons.append("boss_route_node_open")
    return {"active": bool(reasons), "reasons": reasons}


def stall_suspected(
    previous_report: Mapping[str, Any] | None,
    no_progress_window_sec: int,
) -> list[str]:
    """Return reasons to keep full diagnostics even while in combat."""
    if not isinstance(previous_report, Mapping):
        return []
    reasons: list[str] = []
    liveness = previous_report.get("semantic_liveness")
    if isinstance(liveness, Mapping):
        try:
            elapsed = float(liveness.get("elapsed_no_progress_sec") or 0.0)
        except (TypeError, ValueError):
            elapsed = 0.0
        if elapsed >= max(1.0, float(no_progress_window_sec) / 2.0):
            reasons.append("semantic_no_progress_half_window")
    counters = previous_report.get("progress_counters")
    if isinstance(counters, Mapping):
        try:
            if int(counters.get("validation_route_no_progress_diagnoses") or 0) > 0:
                reasons.append("native_route_no_progress_diagnosis")
        except (TypeError, ValueError):
            pass
    return reasons


@dataclass
class HeartbeatPlanner:
    """Choose the per-heartbeat command variant after the status response."""

    heartbeat_commands: Sequence[str]
    no_progress_window_sec: int
    parse: PayloadParser
    light_trace_limit: int = LIGHT_TRACE_LIMIT
    enabled: bool = True
    mode: str = "full"
    reasons: list[str] = field(default_factory=list)
    _suspicion: list[str] = field(default_factory=list)

    def begin(self, previous_report: Mapping[str, Any] | None) -> None:
        self.mode = "full"
        self.reasons = []
        self._suspicion = stall_suspected(previous_report, self.no_progress_window_sec)

    def observe(self, configured_command: str, output: str) -> None:
        if not self.enabled or not is_status_command(configured_command):
            return
        activity = combat_activity(latest_status_payload(output, self.parse))
        if activity["active"] and not self._suspicion:
            self.mode = "light"
            self.reasons = list(activity["reasons"])
        else:
            self.mode = "full"
            self.reasons = list(self._suspicion) if activity["active"] else []

    def effective_command(self, configured_command: str) -> str:
        if self.mode == "light" and is_trace_command(configured_command):
            return light_trace_command(configured_command, self.light_trace_limit)
        return configured_command

    def receipt(self) -> dict[str, Any]:
        return {
            "schema": "bot_heartbeat_plan_v1",
            "mode": self.mode,
            "reasons": list(self.reasons),
            "light_trace_limit": self.light_trace_limit,
            "commands": [self.effective_command(value) for value in self.heartbeat_commands],
        }


@dataclass
class CommandTimingRecorder:
    """Append one compact wall-clock receipt per console command."""

    output_dir: Path

    @property
    def path(self) -> Path:
        return Path(self.output_dir) / HEARTBEAT_COMMAND_TIMINGS_FILE

    def record(
        self,
        *,
        phase: str,
        heartbeat_index: int,
        command: str,
        configured_command: str = "",
        mode: str = "",
        sent_at_ms: int,
        completed_at_ms: int,
        response_bytes: int,
        returncode: int | None = None,
        timed_out: bool | None = None,
    ) -> dict[str, Any]:
        row = {
            "phase": phase,
            "heartbeat_index": int(heartbeat_index),
            "command": command,
            "configured_command": configured_command or command,
            "mode": mode,
            "sent_at_ms": int(sent_at_ms),
            "completed_at_ms": int(completed_at_ms),
            "duration_ms": max(0, int(completed_at_ms) - int(sent_at_ms)),
            "response_bytes": int(response_bytes),
        }
        if returncode is not None:
            row["returncode"] = int(returncode)
        if timed_out is not None:
            row["timed_out"] = bool(timed_out)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n")
        except OSError:
            pass
        return row


def load_command_timings(output_dir: Path) -> list[dict[str, Any]]:
    path = Path(output_dir) / HEARTBEAT_COMMAND_TIMINGS_FILE
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return rows
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def cleanup_step_receipt(
    command: str,
    *,
    returncode: int,
    timed_out: bool,
    completed: bool,
    extra: Mapping[str, Any] | None = None,
) -> str:
    row: dict[str, Any] = {
        "action": "harness_cleanup_step",
        "command": command,
        "returncode": int(returncode),
        "timed_out": bool(timed_out),
        "completed": bool(completed),
    }
    if extra:
        row.update(dict(extra))
    return json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"


def cleanup_steps_from_payloads(payloads: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in payloads
        if isinstance(row, Mapping) and row.get("action") == "harness_cleanup_step"
    ]


@dataclass
class TraceRouteRetention:
    """Keep every trace row of selected route nodes in one gzip JSONL file.

    The watchdog output buffer keeps only the newest response of each repeated
    command.  Diagnostics that need a trash node's decisions (for example the
    Magmaw Drudge exit) opt in with ``--retain-trace-route-node``.  Rows are
    deduplicated by ``(bot_guid, sequence)`` across delta exports, light tails
    and the bounded cleanup drain.
    """

    output_dir: Path
    route_nodes: Sequence[str]
    parse: PayloadParser
    retained_rows: int = 0
    _seen: set[tuple[int, int]] = field(default_factory=set)

    @property
    def enabled(self) -> bool:
        return bool(self.route_nodes)

    @property
    def path(self) -> Path:
        return Path(self.output_dir) / TRACE_HISTORY_FILE

    def observe(self, *, heartbeat_index: int, phase: str, command: str, output: str) -> dict[str, Any]:
        """Retain matching rows; return pending/match counters for draining."""
        summary = {"matching_rows": 0, "pending_entry_count": 0, "entry_count": 0}
        if not self.enabled or '"botauto_trace"' not in output:
            return summary
        wanted = set(self.route_nodes)
        lines: list[str] = []
        for payload in self.parse(output):
            if payload.get("action") != "botauto_trace":
                continue
            for bot in payload.get("bots") or []:
                if not isinstance(bot, Mapping):
                    continue
                try:
                    summary["pending_entry_count"] += int(bot.get("pending_entry_count") or 0)
                except (TypeError, ValueError):
                    pass
                bot_guid = int(bot.get("bot_guid") or 0)
                for entry in bot.get("entries") or []:
                    if not isinstance(entry, Mapping):
                        continue
                    summary["entry_count"] += 1
                    if str(entry.get("route_node_id") or "") not in wanted:
                        continue
                    summary["matching_rows"] += 1
                    key = (bot_guid, int(entry.get("sequence") or 0))
                    if key in self._seen:
                        continue
                    self._seen.add(key)
                    lines.append(json.dumps(
                        {
                            "heartbeat_index": int(heartbeat_index),
                            "phase": phase,
                            "command": command,
                            "bot_guid": bot_guid,
                            "bot_name": bot.get("bot_name"),
                            "entry": entry,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ))
        if lines:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(self.path, "at", encoding="utf-8") as handle:
                    handle.write("\n".join(lines) + "\n")
                self.retained_rows += len(lines)
            except OSError:
                pass
        return summary

    def should_continue_drain(self, summary: Mapping[str, Any], calls: int) -> bool:
        if calls >= TRACE_HISTORY_MAX_DRAIN_CALLS:
            return False
        if int(summary.get("pending_entry_count") or 0) <= 0:
            return False
        if int(summary.get("entry_count") or 0) <= 0:
            return False
        # Delta rows arrive in sequence order.  Once retained rows were seen
        # and the backlog has moved past every selected node, stop.
        return not (self._seen and int(summary.get("matching_rows") or 0) <= 0)


def drain_trace_backlog(
    run: Callable[[str], tuple[str, bool]],
    retention: TraceRouteRetention,
    heartbeat_commands: Sequence[str],
    heartbeat_index: int,
) -> str:
    """Drain the delta backlog for retained route nodes; return one receipt.

    Called during cleanup (after the combat-log export) because light
    in-combat heartbeats leave the delta cursor untouched.  ``run`` sends one
    command and returns ``(output, ok)``; its output is never added to the
    bounded console buffer.
    """
    drain_command = drain_delta_command(heartbeat_commands)
    if not retention.enabled or not drain_command:
        return ""
    calls = 0
    while True:
        calls += 1
        output, ok = run(drain_command)
        if not ok:
            break
        summary = retention.observe(
            heartbeat_index=heartbeat_index,
            phase="trace_retention_drain",
            command=drain_command,
            output=output,
        )
        if not retention.should_continue_drain(summary, calls):
            break
    return cleanup_step_receipt(
        drain_command, returncode=0, timed_out=False, completed=True,
        extra={
            "purpose": "trace_retention_drain",
            "drain_calls": calls,
            "retained_trace_rows": retention.retained_rows,
        },
    )


def drain_delta_command(heartbeat_commands: Sequence[str]) -> str:
    for command in heartbeat_commands:
        tokens = command_tokens(command)
        if tokens[:2] == [".botauto", "trace"] and tokens[-1:] == ["delta"]:
            return command
    return ""
