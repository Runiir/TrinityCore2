"""Watchdog signals that span heartbeats.

A heartbeat report is rebuilt from the newest response of each repeated
console command.  With ``.botauto trace ... delta`` that response holds only
the rows exported since the previous heartbeat, so a count taken from it
describes the last window, not the attempt.  One watchdog loop owns one
``HeartbeatSignals`` and carries these signals from heartbeat to heartbeat:

* ``RouteActionLedger``: the cumulative validation-route action count,
  deduplicated by (bot, sequence, timestamp) across delta windows, light
  tails and drains.  A long pre-pull hold drains the 128-row window of route
  actions; the ledger keeps the attempt's count.
* ``NearWipeTracker``: large alive-count drops, death bursts or new native
  wipes within one route node.  Repeated near-wipes on one node are a death
  loop even when no bot trace records ``repeated_death``.  A node change
  resets the count, and so do kills on a non-boss node (recovered trash
  deaths are progress); boss-window near-wipes always count.
* ``ContaminationWatchdog``: future-encounter contamination that persists for
  ``grace_heartbeats`` consecutive heartbeats becomes a typed terminal.
* ``PrepullWatchdog``: a failed native pre-pull consumables gate is labelled
  on the heartbeat that reports it and becomes terminal when it still holds
  an unengaged pull on the next heartbeat.
* ``drain_terminal_trace``: after a terminal failure, drain every bot's
  pending delta rows (bounded) so the failing bot's last decisions survive.
"""
from __future__ import annotations

import gzip
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence

try:
    from .live_validation_heartbeat import cleanup_step_receipt, command_tokens
except ImportError:  # pragma: no cover - script-directory imports
    from live_validation_heartbeat import cleanup_step_receipt, command_tokens

ROUTE_ACTION_PREFIXES = ("validation_route", "move_to_validation_route")
NEAR_WIPE_DROP_FRACTION = 0.5
NEAR_WIPE_RECOVERED_FRACTION = 0.75
NEAR_WIPE_HISTORY_LIMIT = 16
CONTAMINATION_GRACE_HEARTBEATS = 2
CONTAMINATION_COMPLETION_REASON = "future_encounter_contamination_watchdog"
CONTAMINATION_LABEL = "validation_route_future_encounter_contamination"
PREPULL_FAILURE_LABEL_PREFIX = "raid_prepull_consumables_failed:"
PREPULL_GRACE_HEARTBEATS = 2
TERMINAL_TRACE_DRAIN_FILE = "terminal_trace_drain.jsonl.gz"
TERMINAL_TRACE_DRAIN_BUDGET_SEC = 10.0
TERMINAL_TRACE_DRAIN_MAX_CALLS = 6

PayloadParser = Callable[[str], list[dict[str, Any]]]


def _int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def is_route_action(action: str) -> bool:
    return str(action or "").startswith(ROUTE_ACTION_PREFIXES)


def prepull_consumables_failure(status: Mapping[str, Any]) -> dict[str, Any]:
    """Return the current scope's native pre-pull consumables failure, or {}.

    ``raid_runtime.prepull_consumables.failed`` is a native Terminal outcome
    of the pre-pull candidate for its attempt/wipe/route scope: the bots do
    not pull in it.  A failure recorded for another route generation is stale.
    """
    status = _mapping(status)
    runtime = _mapping(status.get("raid_runtime"))
    prepull = _mapping(runtime.get("prepull_consumables"))
    if prepull.get("failed") is not True:
        return {}
    failure_generation = _int(prepull.get("route_generation")) or 0
    current_generation = _int(_mapping(status.get("validation_route")).get("generation")) or 0
    if failure_generation and current_generation and failure_generation != current_generation:
        return {}
    return {
        "failure_reason": str(prepull.get("failure_reason") or "unknown"),
        "attempt_id": _int(prepull.get("attempt_id")) or 0,
        "wipe_generation": _int(prepull.get("wipe_generation")) or 0,
        "route_generation": failure_generation,
    }


def prepull_failure_label(failure: Mapping[str, Any]) -> str:
    return PREPULL_FAILURE_LABEL_PREFIX + str(failure.get("failure_reason") or "unknown")


@dataclass
class RouteActionLedger:
    """Cumulative validation-route actions across drained trace windows."""

    count: int = 0
    _seen: set[tuple[int, int, int]] = field(default_factory=set)

    def observe(self, entries: Iterable[Mapping[str, Any]]) -> int:
        for entry in entries:
            if not isinstance(entry, Mapping):
                continue
            action = str(entry.get("action") or entry.get("situation") or "")
            if not is_route_action(action):
                continue
            guid = _int(entry.get("bot_guid")) or 0
            sequence = _int(entry.get("sequence")) or 0
            if guid <= 0 or sequence <= 0:
                # Unsequenced rows cannot be deduplicated across windows; the
                # caller's window count still includes them.
                continue
            key = (guid, sequence, _int(entry.get("timestamp_ms")) or 0)
            if key in self._seen:
                continue
            self._seen.add(key)
            self.count += 1
        return self.count


@dataclass
class NearWipeTracker:
    """Count near-wipe episodes inside the current route node."""

    route_node_id: str = ""
    route_generation: int = 0
    route_kind: str = ""
    episodes: int = 0
    down: bool = False
    observed: bool = False
    wipe_generation: int = 0
    deaths: int | None = None
    kills_at_last_episode: int = 0
    last_alive: int | None = None
    expected: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)

    @staticmethod
    def thresholds(expected: int) -> tuple[int, int]:
        """(near-wipe: alive at most, recovered: alive at least)."""
        drop = int(math.floor(expected * NEAR_WIPE_DROP_FRACTION))
        recovered = max(drop + 1, int(math.ceil(expected * NEAR_WIPE_RECOVERED_FRACTION)))
        return drop, recovered

    def observe(self, status: Mapping[str, Any], *, kills: int | None = None) -> int:
        status = _mapping(status)
        if kills is None:
            kills = _int(status.get("kills")) or 0
        runtime = _mapping(status.get("raid_runtime"))
        route = _mapping(status.get("validation_route"))
        node_id = str(route.get("node_id") or "")
        generation = _int(route.get("generation")) or 0
        expected = _int(runtime.get("expected_size")) or 0
        alive = _int(runtime.get("alive_size"))
        if not node_id or generation <= 0 or expected <= 0 or alive is None:
            return self.episodes
        wipe_generation = _int(runtime.get("wipe_generation")) or 0
        deaths = _int(status.get("deaths"))
        drop_at, recovered_at = self.thresholds(expected)
        scope = (node_id, generation)
        if self.observed and scope != (self.route_node_id, self.route_generation):
            # The route advanced: the previous node's deaths are not a loop here.
            self.episodes = 0
            self.down = alive < recovered_at
            self.kills_at_last_episode = kills
            self.wipe_generation = wipe_generation
            self.deaths = deaths
        self.route_node_id, self.route_generation = scope
        self.route_kind = str(route.get("kind") or "").lower()
        if self.route_kind != "boss" and self.episodes and kills > self.kills_at_last_episode:
            # Kills since the last near-wipe on a trash/regroup node: the raid
            # recovered and progressed, which the user accepts.
            self.episodes = 0
        new_wipe = wipe_generation > self.wipe_generation
        death_burst = (
            deaths is not None
            and self.deaths is not None
            and deaths - self.deaths >= expected - drop_at
        )
        near_wipe = alive <= drop_at
        if not self.down and (near_wipe or new_wipe or death_burst):
            self.episodes += 1
            self.kills_at_last_episode = kills
            self.history.append({
                "route_node_id": node_id,
                "route_generation": generation,
                "route_kind": self.route_kind,
                "alive": alive,
                "expected": expected,
                "wipe_generation": wipe_generation,
                "trigger": "alive_drop" if near_wipe else "native_wipe" if new_wipe else "death_burst",
                "episode": self.episodes,
            })
            del self.history[:-NEAR_WIPE_HISTORY_LIMIT]
            self.down = near_wipe
        if self.down and alive >= recovered_at:
            self.down = False
        self.wipe_generation = max(self.wipe_generation, wipe_generation)
        if deaths is not None:
            self.deaths = deaths
        self.observed = True
        self.last_alive = alive
        self.expected = expected
        return self.episodes

    def receipt(self) -> dict[str, Any]:
        drop_at, recovered_at = self.thresholds(self.expected) if self.expected else (0, 0)
        return {
            "schema": "bot_near_wipe_death_loop_v1",
            "route_node_id": self.route_node_id,
            "route_generation": self.route_generation,
            "route_kind": self.route_kind,
            "episodes": self.episodes,
            "down": self.down,
            "alive": self.last_alive,
            "expected": self.expected,
            "near_wipe_alive_at_most": drop_at,
            "recovered_alive_at_least": recovered_at,
            "history": list(self.history),
        }


@dataclass
class ContaminationWatchdog:
    """Future-encounter contamination for ``grace_heartbeats`` in a row is terminal."""

    grace_heartbeats: int = CONTAMINATION_GRACE_HEARTBEATS
    consecutive: int = 0
    first_heartbeat_index: int = 0

    def observe(self, report: Mapping[str, Any], heartbeat_index: int) -> dict[str, Any] | None:
        evidence = _mapping(_mapping(report).get("evidence"))
        rows = [
            {key: row.get(key) for key in ("route_node_id", "route_generation") if key in row}
            for row in evidence.get("contamination_evidence") or []
            if isinstance(row, Mapping)
        ]
        if not rows:
            # The native observer cleared it: the grace restarts.
            self.consecutive = 0
            self.first_heartbeat_index = 0
            return None
        if self.consecutive == 0:
            self.first_heartbeat_index = int(heartbeat_index)
        self.consecutive += 1
        if self.consecutive < max(1, int(self.grace_heartbeats)):
            return None
        return {
            "kind": "future_encounter_contamination",
            "completion_reason": CONTAMINATION_COMPLETION_REASON,
            "failure_reason": CONTAMINATION_LABEL,
            "consecutive_heartbeats": self.consecutive,
            "grace_heartbeats": int(self.grace_heartbeats),
            "first_observed_heartbeat_index": self.first_heartbeat_index,
            "contamination_evidence": rows[:8],
        }


@dataclass
class PrepullWatchdog:
    """A failed pre-pull gate that holds the pull for ``grace_heartbeats`` is terminal.

    The label is on the first heartbeat; the terminal waits one more because
    some bosses engage natively despite the gate (the round-2 Magmaw smoke
    cleared with ``failed=true``).  An engaged encounter or a native clear
    resets the count.
    """

    grace_heartbeats: int = PREPULL_GRACE_HEARTBEATS
    consecutive: int = 0
    first_heartbeat_index: int = 0

    def observe(self, report: Mapping[str, Any], heartbeat_index: int) -> dict[str, Any] | None:
        report = _mapping(report)
        evidence = _mapping(report.get("evidence"))
        failure = _mapping(evidence.get("prepull_consumables_failure"))
        runtime = _mapping(_mapping(report.get("status")).get("raid_runtime"))
        engaged = (
            runtime.get("encounter_in_progress") is True
            or str(runtime.get("wipe_state") or "") == "engaged"
        )
        native_clear = bool(evidence.get("manifest_completion_evidence")) and bool(
            evidence.get("real_boss_kill_evidence"))
        if not failure or engaged or native_clear:
            self.consecutive = 0
            self.first_heartbeat_index = 0
            return None
        if self.consecutive == 0:
            self.first_heartbeat_index = int(heartbeat_index)
        self.consecutive += 1
        if self.consecutive < max(1, int(self.grace_heartbeats)):
            return None
        return {
            "kind": "raid_prepull_consumables_failed",
            "completion_reason": "machine_failure_predicate",
            "failure_reason": prepull_failure_label(failure),
            "native_failure_reason": str(failure.get("failure_reason") or ""),
            "attempt_id": int(failure.get("attempt_id") or 0),
            "wipe_generation": int(failure.get("wipe_generation") or 0),
            "route_generation": int(failure.get("route_generation") or 0),
            "consecutive_heartbeats": self.consecutive,
            "grace_heartbeats": int(self.grace_heartbeats),
            "first_observed_heartbeat_index": self.first_heartbeat_index,
        }


@dataclass
class HeartbeatSignals:
    """Per-watchdog-loop state threaded through every heartbeat report."""

    route_actions: RouteActionLedger = field(default_factory=RouteActionLedger)
    near_wipes: NearWipeTracker = field(default_factory=NearWipeTracker)
    contamination: ContaminationWatchdog = field(default_factory=ContaminationWatchdog)
    prepull: PrepullWatchdog = field(default_factory=PrepullWatchdog)

    def terminal(self, report: Mapping[str, Any], heartbeat_index: int) -> dict[str, Any] | None:
        """The first stateful terminal of this heartbeat, if any."""
        contamination = self.contamination.observe(report, heartbeat_index)
        prepull = self.prepull.observe(report, heartbeat_index)
        return contamination or prepull


def terminal_drain_command(heartbeat_commands: Sequence[str]) -> str:
    for command in heartbeat_commands:
        tokens = command_tokens(command)
        if tokens[:2] == [".botauto", "trace"] and tokens[-1:] == ["delta"]:
            return command
    return ""


def drain_terminal_trace(
    run: Callable[[str], tuple[str, bool]],
    heartbeat_commands: Sequence[str],
    output_dir: Path,
    parse: PayloadParser,
    *,
    observe: Callable[[str, str], Any] | None = None,
    budget_sec: float = TERMINAL_TRACE_DRAIN_BUDGET_SEC,
    max_calls: int = TERMINAL_TRACE_DRAIN_MAX_CALLS,
    clock: Callable[[], float] = time.monotonic,
) -> str:
    """Drain every bot's pending delta rows after a terminal failure.

    Repeats the configured ``.botauto trace <cohort> <selector> <n> delta``
    until every bot reports ``pending_entry_count == 0``, ``max_calls`` calls
    were sent, or ``budget_sec`` elapsed.  Rows go to
    ``terminal_trace_drain.jsonl.gz`` (never the bounded console buffer); the
    returned cleanup receipt carries each bot's last drained decision.
    """
    command = terminal_drain_command(heartbeat_commands)
    if not command:
        return ""
    started = clock()
    calls = 0
    drained_rows = 0
    pending: dict[int, int] = {}
    last_entries: dict[int, dict[str, Any]] = {}
    seen: set[tuple[int, int, int]] = set()
    stop_reason = "budget_exhausted"
    path = Path(output_dir) / TERMINAL_TRACE_DRAIN_FILE
    while calls < max(1, int(max_calls)):
        if calls and clock() - started >= budget_sec:
            break
        calls += 1
        output, ok = run(command)
        if observe is not None:
            observe(command, output or "")
        if not ok:
            stop_reason = "transport_unavailable"
            break
        payloads = [row for row in parse(output or "") if row.get("action") == "botauto_trace"]
        if not payloads:
            stop_reason = "no_trace_payload"
            break
        pending = {}
        lines: list[str] = []
        for payload in payloads:
            for bot in payload.get("bots") or []:
                if not isinstance(bot, Mapping):
                    continue
                guid = _int(bot.get("bot_guid")) or 0
                pending[guid] = max(0, _int(bot.get("pending_entry_count")) or 0)
                for entry in bot.get("entries") or []:
                    if not isinstance(entry, Mapping):
                        continue
                    key = (guid, _int(entry.get("sequence")) or 0, _int(entry.get("timestamp_ms")) or 0)
                    if key in seen:
                        continue
                    seen.add(key)
                    lines.append(json.dumps(
                        {"drain_call": calls, "bot_guid": guid, "bot_name": bot.get("bot_name"), "entry": entry},
                        sort_keys=True, separators=(",", ":"),
                    ))
                    previous = last_entries.get(guid)
                    if previous is None or key[1] >= int(previous.get("sequence") or 0):
                        last_entries[guid] = {
                            "bot_guid": guid,
                            "bot_name": bot.get("bot_name"),
                            "sequence": key[1],
                            "action": entry.get("action") or entry.get("situation"),
                            "result": entry.get("result"),
                            "route_node_id": entry.get("route_node_id"),
                        }
        if lines:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(path, "at", encoding="utf-8") as handle:
                    handle.write("\n".join(lines) + "\n")
                drained_rows += len(lines)
            except OSError:
                stop_reason = "write_failed"
                break
        if all(value <= 0 for value in pending.values()):
            stop_reason = "pending_zero"
            break
    complete = stop_reason == "pending_zero"
    return cleanup_step_receipt(
        command, returncode=0, timed_out=stop_reason == "budget_exhausted", completed=complete,
        extra={
            "purpose": "terminal_trace_drain",
            "stop_reason": stop_reason,
            "drain_calls": calls,
            "drained_rows": drained_rows,
            "elapsed_ms": int(max(0.0, clock() - started) * 1000),
            "pending_after": sum(pending.values()),
            "bots_pending": sorted(guid for guid, value in pending.items() if value > 0),
            "path": TERMINAL_TRACE_DRAIN_FILE if drained_rows else "",
            "last_decisions": [last_entries[guid] for guid in sorted(last_entries)],
        },
    )
