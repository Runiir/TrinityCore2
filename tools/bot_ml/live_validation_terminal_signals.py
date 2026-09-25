"""Watchdog signals that span heartbeats.

A heartbeat report is rebuilt from the newest response of each repeated
console command.  With ``.botauto trace ... delta`` that response holds only
the rows exported since the previous heartbeat, so a count taken from it
describes the last window, not the attempt.  One watchdog loop owns one
``HeartbeatSignals`` and carries these signals from heartbeat to heartbeat:

* ``RouteActionLedger``: the cumulative validation-route action count,
  deduplicated by (bot, sequence, timestamp) across delta windows, light
  tails and drains.  It is reported as ``validation_route_actions_cumulative``
  and never replaces the window count in the label predicates.
* ``NearWipeTracker``: large alive-count drops, death bursts or new native
  wipes within one route node.  Repeated near-wipes on one node are a death
  loop even when no bot trace records ``repeated_death``.  A node change
  resets the count, and so do kills on a non-boss node (recovered trash
  deaths are progress); boss-window near-wipes count, except on the heartbeat
  that carries the boss kill or the manifest completion.
* ``ContaminationWatchdog``: ``validation_route.contamination_evidence`` only
  grows during an attempt (the runtime clears it only on a config load), so
  its presence is not persistence.  Contamination is terminal only when a
  contaminating creature is again the raid's native hostile activity after
  the raid has had a near-wipe or wipe since the contamination was recorded:
  the raid lost to it and it is fighting again.  A patrol the runtime guards
  and transfers, or that dies, never qualifies.
* ``drain_terminal_trace``: after a terminal failure, drain the oldest
  pending delta rows (bounded) and capture every bot's newest rows with one
  non-delta tail, so the failing bot's last decisions survive.

A failed native pre-pull consumables gate is only a label here
(``raid_prepull_consumables_failed:<reason>``): bosses can engage natively
despite it (round-2 Magmaw batch: failed from heartbeat 8, engaged at 18,
killed at 22), so the semantic no-progress and plateau clocks end a pre-pull
that is really stuck.
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
TERMINAL_TRACE_DRAIN_FILE = "terminal_trace_drain.jsonl.gz"
# The budget is checked before each delta call; one call may still take up to
# the cleanup step cap (live_validation_cleanup.CLEANUP_STEP_MAX_SEC, 180 s),
# and the final tail is one more call.  Worst case: about
# TERMINAL_TRACE_DRAIN_BUDGET_SEC + 2 * CLEANUP_STEP_MAX_SEC, always inside the
# shared cleanup budget, which reserves time for ``.botauto stop``.
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


def is_prepull_failure_label(label: Any) -> bool:
    return str(label).startswith(PREPULL_FAILURE_LABEL_PREFIX)


def _route_scope_settled(status: Mapping[str, Any], node_id: str, generation: int) -> bool:
    """The route's current node already has its boss death or the manifest completed."""
    route = _mapping(status.get("validation_route"))
    if route.get("manifest_complete") is True:
        return True
    for row in route.get("boss_death_evidence") or []:
        row = _mapping(row)
        if (
            str(row.get("route_node_id") or "") == node_id
            and (_int(row.get("route_generation")) or 0) == generation
        ):
            return True
    return False


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
    total_episodes: int = 0
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
        if not self.observed:
            # Baselines come from the first observation: a wipe generation or
            # death count carried in from before the watchdog is not a burst.
            self.wipe_generation = wipe_generation
            self.deaths = deaths
        elif scope != (self.route_node_id, self.route_generation):
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
        # The kill pull can lose half the raid and still clear: the heartbeat
        # that carries the boss death or the manifest completion is progress.
        settled = _route_scope_settled(status, node_id, generation)
        if not self.down and not settled and (near_wipe or new_wipe or death_burst):
            self.episodes += 1
            self.total_episodes += 1
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
            "total_episodes": self.total_episodes,
            "down": self.down,
            "alive": self.last_alive,
            "expected": self.expected,
            "near_wipe_alive_at_most": drop_at,
            "recovered_alive_at_least": recovered_at,
            "history": list(self.history),
        }


@dataclass
class ContaminationWatchdog:
    """Contamination the raid lost to and is fighting again is terminal.

    The native evidence list is sticky, so the watchdog keys on behaviour: a
    contaminating creature (by GUID, or by entry when the row has no GUID) is
    the raid's native hostile activity on this heartbeat, and the near-wipe
    tracker has counted an episode since the contamination was first seen.
    A native clear is never terminal here (the loop also checks it first).
    """

    first_heartbeat_index: int = 0
    episodes_at_first: int | None = None
    _episodes_before: int = 0

    def observe(
        self,
        report: Mapping[str, Any],
        heartbeat_index: int,
        near_wipes: NearWipeTracker | None = None,
    ) -> dict[str, Any] | None:
        report = _mapping(report)
        evidence = _mapping(report.get("evidence"))
        episodes = near_wipes.total_episodes if near_wipes is not None else 0
        # ``near_wipes`` already observed this heartbeat's status; the value
        # it had before this heartbeat is the baseline at first contamination.
        episodes_before, self._episodes_before = self._episodes_before, episodes
        status = _mapping(report.get("status"))
        # The report's evidence keeps only scopes; the native status rows carry
        # the contaminating creature's GUID and entry.
        rows = [
            _mapping(row)
            for row in _mapping(status.get("validation_route")).get("contamination_evidence") or []
            if isinstance(row, Mapping)
        ] or [_mapping(row) for row in evidence.get("contamination_evidence") or [] if isinstance(row, Mapping)]
        if not rows:
            return None
        if self.episodes_at_first is None:
            self.episodes_at_first = episodes_before
            self.first_heartbeat_index = int(heartbeat_index)
        if bool(evidence.get("manifest_completion_evidence")) and bool(evidence.get("real_boss_kill_evidence")):
            return None
        runtime = _mapping(status.get("raid_runtime"))
        if runtime.get("native_hostile_activity_active") is not True:
            return None
        active_guid = str(runtime.get("native_hostile_activity_guid") or "")
        active_entry = _int(runtime.get("native_hostile_activity_entry")) or 0
        engaged = next((
            row for row in rows
            if (str(row.get("target_id") or "") and str(row.get("target_id")) == active_guid)
            or (not row.get("target_id") and active_entry and (_int(row.get("target_entry")) or 0) == active_entry)
        ), None)
        episodes_since = episodes - int(self.episodes_at_first)
        if engaged is None or episodes_since <= 0:
            return None
        return {
            "kind": "future_encounter_contamination",
            "completion_reason": CONTAMINATION_COMPLETION_REASON,
            "failure_reason": CONTAMINATION_LABEL,
            "rule": "contaminating_creature_reengaged_after_near_wipe",
            "first_observed_heartbeat_index": self.first_heartbeat_index,
            "near_wipe_episodes_since_contamination": episodes_since,
            "engaged_target_entry": _int(engaged.get("target_entry")) or 0,
            "engaged_target_id": str(engaged.get("target_id") or ""),
            "contamination_evidence": [
                {key: row.get(key) for key in ("route_node_id", "route_generation", "target_entry") if key in row}
                for row in rows[:8]
            ],
        }


@dataclass
class HeartbeatSignals:
    """Per-watchdog-loop state threaded through every heartbeat report."""

    route_actions: RouteActionLedger = field(default_factory=RouteActionLedger)
    near_wipes: NearWipeTracker = field(default_factory=NearWipeTracker)
    contamination: ContaminationWatchdog = field(default_factory=ContaminationWatchdog)

    def terminal(self, report: Mapping[str, Any], heartbeat_index: int) -> dict[str, Any] | None:
        """The stateful terminal of this heartbeat, if any (after the clear check)."""
        return self.contamination.observe(report, heartbeat_index, self.near_wipes)


def terminal_drain_command(heartbeat_commands: Sequence[str]) -> str:
    for command in heartbeat_commands:
        tokens = command_tokens(command)
        if tokens[:2] == [".botauto", "trace"] and tokens[-1:] == ["delta"]:
            return command
    return ""


def terminal_tail_command(delta_command: str) -> str:
    """The non-delta form: the newest N rows per bot, cursor untouched."""
    tokens = command_tokens(delta_command)
    return " ".join(tokens[:-1]) if tokens[-1:] == ["delta"] else delta_command


@dataclass
class _DrainCapture:
    """Rows and per-bot receipts across the drain and tail calls."""

    path: Path
    seen: set[tuple[int, int, int]] = field(default_factory=set)
    rows: int = 0
    bots: dict[int, dict[str, Any]] = field(default_factory=dict)
    write_failed: bool = False

    def add(self, payloads: list[dict[str, Any]], *, call: int, source: str) -> dict[int, int]:
        pending: dict[int, int] = {}
        lines: list[str] = []
        for payload in payloads:
            for bot in payload.get("bots") or []:
                if not isinstance(bot, Mapping):
                    continue
                guid = _int(bot.get("bot_guid")) or 0
                receipt = self.bots.setdefault(guid, {
                    "bot_guid": guid, "bot_name": bot.get("bot_name"),
                    "newest_retained_sequence": 0, "last_captured_sequence": 0,
                })
                newest = _int(bot.get("newest_retained_sequence"))
                if newest is not None:
                    receipt["newest_retained_sequence"] = max(receipt["newest_retained_sequence"], newest)
                if source == "delta":
                    pending[guid] = max(0, _int(bot.get("pending_entry_count")) or 0)
                    receipt["delta_pending_after"] = pending[guid]
                for entry in bot.get("entries") or []:
                    if not isinstance(entry, Mapping):
                        continue
                    key = (guid, _int(entry.get("sequence")) or 0, _int(entry.get("timestamp_ms")) or 0)
                    if key in self.seen:
                        continue
                    self.seen.add(key)
                    lines.append(json.dumps(
                        {"drain_call": call, "source": source, "bot_guid": guid,
                         "bot_name": bot.get("bot_name"), "entry": entry},
                        sort_keys=True, separators=(",", ":"),
                    ))
                    if key[1] >= int(receipt["last_captured_sequence"] or 0):
                        receipt.update({
                            "last_captured_sequence": key[1],
                            "action": entry.get("action") or entry.get("situation"),
                            "result": entry.get("result"),
                            "route_node_id": entry.get("route_node_id"),
                        })
        if lines and not self.write_failed:
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(self.path, "at", encoding="utf-8") as handle:
                    handle.write("\n".join(lines) + "\n")
                self.rows += len(lines)
            except OSError:
                self.write_failed = True
        return pending


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
    """Capture every bot's pending and newest decisions after a terminal failure.

    A delta export returns the OLDEST pending rows; round-2 backlogs reached
    1665-2390 rows per bot, so a bounded delta drain rarely reaches the end.
    This therefore (1) repeats the configured ``.botauto trace <cohort>
    <selector> <n> delta`` until every bot reports ``pending_entry_count ==
    0``, ``max_calls`` calls were sent or ``budget_sec`` elapsed, then (2)
    always sends the non-delta ``.botauto trace <cohort> <selector> <n>``,
    which returns each bot's newest ``n`` rows: the failing bot's last
    decisions.  Rows go to ``terminal_trace_drain.jsonl.gz`` (never the
    bounded console buffer).  The receipt states per bot whether the newest
    retained sequence was captured and how much delta backlog remains.

    The budget is checked between calls, and one call can take up to the
    cleanup step cap (``CLEANUP_STEP_MAX_SEC``, 180 s), so the worst case is
    about ``budget_sec`` plus two step caps, inside the shared cleanup budget.
    """
    command = terminal_drain_command(heartbeat_commands)
    if not command:
        return ""
    tail = terminal_tail_command(command)
    started = clock()
    capture = _DrainCapture(Path(output_dir) / TERMINAL_TRACE_DRAIN_FILE)
    calls = 0
    pending: dict[int, int] = {}
    delta_stop = "budget_exhausted"
    while calls < max(1, int(max_calls)):
        if calls and clock() - started >= budget_sec:
            break
        calls += 1
        output, ok = run(command)
        if observe is not None:
            observe(command, output or "")
        if not ok:
            delta_stop = "transport_unavailable"
            break
        payloads = [row for row in parse(output or "") if row.get("action") == "botauto_trace"]
        if not payloads:
            delta_stop = "no_trace_payload"
            break
        pending = capture.add(payloads, call=calls, source="delta")
        if all(value <= 0 for value in pending.values()):
            delta_stop = "pending_zero"
            break
    else:
        delta_stop = "max_calls"
    tail_captured = False
    if delta_stop != "transport_unavailable":
        output, ok = run(tail)
        if observe is not None:
            observe(tail, output or "")
        payloads = [row for row in parse(output or "") if row.get("action") == "botauto_trace"] if ok else []
        if payloads:
            capture.add(payloads, call=calls + 1, source="tail")
            tail_captured = True
    bots = [capture.bots[guid] for guid in sorted(capture.bots)]
    for receipt in bots:
        newest = int(receipt.get("newest_retained_sequence") or 0)
        receipt["newest_captured"] = bool(newest) and int(receipt.get("last_captured_sequence") or 0) >= newest
    newest_captured = bool(bots) and all(receipt["newest_captured"] for receipt in bots)
    backlog_drained = delta_stop == "pending_zero"
    return cleanup_step_receipt(
        command, returncode=0, timed_out=delta_stop in {"budget_exhausted", "max_calls"},
        completed=newest_captured and not capture.write_failed,
        extra={
            "purpose": "terminal_trace_drain",
            "delta_stop_reason": delta_stop,
            "delta_backlog_drained": backlog_drained,
            "delta_calls": calls,
            "tail_command": tail,
            "tail_captured": tail_captured,
            "newest_captured": newest_captured,
            "captured_rows": capture.rows,
            "write_failed": capture.write_failed,
            "elapsed_ms": int(max(0.0, clock() - started) * 1000),
            "delta_pending_after": sum(pending.values()),
            "bots_with_delta_backlog": sorted(guid for guid, value in pending.items() if value > 0),
            "path": TERMINAL_TRACE_DRAIN_FILE if capture.rows else "",
            "bots": bots,
        },
    )
