"""World-thread stall detection and DPS measurement validity.

Two bases, reported as ``measurement_validity.stall_basis``:

``native_world_tick``
    The worldserver records each world update diff of at least 500 ms
    (``live_validation_world_ticks``).  When those rows cover every boss
    window, a stall is exactly such a diff overlapping the window.

``combat_log_inference``
    Otherwise stalls are inferred from combat-log event gaps.  A frozen
    world thread shows no event for the freeze, then every periodic effect
    and swing that was due lands in one millisecond (the catch-up burst).
    Inside a boss window a gap of at least ``STALL_MIN_GAP_SEC`` is a stall
    only if a harness console command caused it, it ends in a catch-up burst
    of ``CATCHUP_BURST_MIN_EVENTS`` or more, or it lasts at least
    ``UNATTRIBUTED_STALL_MIN_GAP_SEC``.  Other such gaps may be combat lulls
    or short freezes with little due work: they are ``possible_stalls``,
    never gating ``valid_for_dps`` but marking the measurement
    ``verification: unverified``.  With native coverage the same gaps are
    reported as ``lulls``.  Outside boss windows a catch-up gap is a
    stall when a console command caused it or it lasted at least
    ``UNATTRIBUTED_STALL_MIN_GAP_SEC``; shorter ones are ``hitches``.

``valid_for_dps`` tolerates a shared host: the boss-window stalled fraction
must stay at or below ``MAX_BOSS_WINDOW_STALL_FRACTION`` and no single
boss-window stall may reach ``MAX_SINGLE_BOSS_WINDOW_STALL_SEC``.  The raw
fraction and maximum are always reported so a stricter consumer can decide
for itself.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    from .live_validation_heartbeat import cleanup_steps_from_payloads, load_command_timings
    from .live_validation_world_ticks import load_world_tick_ledger, native_coverage, native_stall_intervals
except ImportError:  # pragma: no cover - script-style imports
    from live_validation_heartbeat import cleanup_steps_from_payloads, load_command_timings
    from live_validation_world_ticks import load_world_tick_ledger, native_coverage, native_stall_intervals

STALL_MIN_GAP_SEC = 0.5
UNATTRIBUTED_STALL_MIN_GAP_SEC = 1.0
CATCHUP_BURST_MIN_EVENTS = 10
MAX_BOSS_WINDOW_STALL_FRACTION = 0.02
MAX_SINGLE_BOSS_WINDOW_STALL_SEC = 2.0
# A command's recorded send/complete window is harness-side wall time; the
# first/last combat event around the freeze can sit a few ms outside it.
COMMAND_OVERLAP_SLACK_MS = 100
# A command-caused freeze starts when the world thread picks the command up,
# so the last event before it is at most one sparse event spacing before the
# send.  A command sent into an already running hitch merely waits for it.
FREEZE_START_TOLERANCE_MS = 300
# Legacy evidence only has the integer heartbeat report second.
HEARTBEAT_REPORT_ATTRIBUTION_SEC = 2.0


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _events(combat_log: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    rows = [
        row for row in combat_log.get("recent_events") or []
        if isinstance(row, Mapping) and _int(row.get("timestamp_ms")) > 0
    ]
    rows.sort(key=lambda row: (_int(row.get("timestamp_ms")), _int(row.get("event_sequence"))))
    return rows


def _catchup_weight(row: Mapping[str, Any]) -> int:
    """Count due work; zero-amount heals are out-of-combat AoE noise."""
    return 0 if str(row.get("kind") or "") == "heal" and _int(row.get("amount")) <= 0 else 1


def _overlap_ms(start: int, end: int, other_start: int, other_end: int) -> int:
    return max(0, min(end, other_end) - max(start, other_start))


def _overlapping_commands(
    start_ms: int, end_ms: int, timings: Sequence[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in timings:
        sent = _int(row.get("sent_at_ms"))
        completed = _int(row.get("completed_at_ms")) or sent
        if sent <= 0:
            continue
        if sent - COMMAND_OVERLAP_SLACK_MS <= end_ms and completed + COMMAND_OVERLAP_SLACK_MS >= start_ms:
            receipt = {
                key: row.get(key)
                for key in (
                    "phase",
                    "heartbeat_index",
                    "command",
                    "mode",
                    "sent_at_ms",
                    "completed_at_ms",
                    "duration_ms",
                    "response_bytes",
                )
                if key in row
            }
            receipt["freeze_started_after_send"] = start_ms >= sent - FREEZE_START_TOLERANCE_MS
            rows.append(receipt)
    return rows


def _report_time_heartbeat(end_ms: int, heartbeat_events: Sequence[Mapping[str, Any]]) -> int:
    best = 0
    best_delta = HEARTBEAT_REPORT_ATTRIBUTION_SEC + 1.0
    for row in heartbeat_events:
        generated = _int(row.get("generated_at_unix"))
        if generated <= 0:
            continue
        # The integer report second floors the time the last response was read.
        delta = abs((end_ms / 1000.0) - (generated + 0.5))
        if delta <= HEARTBEAT_REPORT_ATTRIBUTION_SEC and delta < best_delta:
            best = _int(row.get("heartbeat_index"))
            best_delta = delta
    return best


def boss_windows(
    combat_analysis: Mapping[str, Any] | None,
    validation_route_manifest: Mapping[str, Any] | None = None,
    validation_route: Mapping[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Return first-to-last party damage windows of boss route nodes."""
    boss_nodes: set[str] = set()
    manifest = validation_route_manifest if isinstance(validation_route_manifest, Mapping) else {}
    for route in manifest.get("routes") or []:
        if isinstance(route, Mapping) and str(route.get("kind") or "").lower() == "boss":
            boss_nodes.add(str(route.get("route_node_id") or ""))
    route = validation_route if isinstance(validation_route, Mapping) else {}
    if str(route.get("kind") or "").lower() == "boss":
        boss_nodes.add(str(route.get("route_node_id") or route.get("node_id") or ""))
    boss_nodes.discard("")
    analysis = combat_analysis if isinstance(combat_analysis, Mapping) else {}
    windows: list[dict[str, Any]] = []
    for encounter in analysis.get("encounters") or []:
        if not isinstance(encounter, Mapping):
            continue
        if str(encounter.get("route_node_id") or "") not in boss_nodes:
            continue
        first = _int(encounter.get("first_at_ms"))
        last = _int(encounter.get("last_at_ms"))
        if first <= 0 or last < first:
            continue
        windows.append({
            "route_node_id": str(encounter.get("route_node_id") or ""),
            "route_generation": _int(encounter.get("route_generation")),
            "first_at_ms": first,
            "last_at_ms": last,
            "duration_sec": round((last - first) / 1000.0, 3),
            "boundary_basis": encounter.get("encounter_window_boundary_basis"),
        })
    return windows


def _attribution(
    start_ms: int,
    end_ms: int,
    command_timings: Sequence[Mapping[str, Any]],
    heartbeat_events: Sequence[Mapping[str, Any]],
) -> tuple[str, int, list[dict[str, Any]]]:
    commands = _overlapping_commands(start_ms, end_ms, command_timings)
    causal = [row for row in commands if row.get("freeze_started_after_send")]
    heartbeat_index = next(
        (_int(row.get("heartbeat_index")) for row in causal if row.get("phase") == "heartbeat"),
        0,
    )
    attribution = "console_command" if causal else "unattributed"
    if not commands and heartbeat_events:
        heartbeat_index = _report_time_heartbeat(end_ms, heartbeat_events)
        if heartbeat_index:
            attribution = "heartbeat_report_time"
    return attribution, heartbeat_index, commands


def _window_overlap_ms(start_ms: int, end_ms: int, windows: Sequence[Mapping[str, Any]]) -> int:
    return sum(
        _overlap_ms(start_ms, end_ms, _int(window.get("first_at_ms")), _int(window.get("last_at_ms")))
        for window in windows
    )


def detect_world_stalls(
    combat_log: Mapping[str, Any] | None,
    *,
    command_timings: Sequence[Mapping[str, Any]] = (),
    heartbeat_events: Sequence[Mapping[str, Any]] = (),
    windows: Sequence[Mapping[str, Any]] = (),
    min_gap_sec: float = STALL_MIN_GAP_SEC,
    unattributed_min_gap_sec: float = UNATTRIBUTED_STALL_MIN_GAP_SEC,
    catchup_burst_min_events: int = CATCHUP_BURST_MIN_EVENTS,
) -> dict[str, Any]:
    """Infer world-thread freezes from combat-log event gaps."""
    log = combat_log if isinstance(combat_log, Mapping) else {}
    events = _events(log)
    same_ms: Counter[int] = Counter()
    for row in events:
        same_ms[_int(row.get("timestamp_ms"))] += _catchup_weight(row)
    stalls: list[dict[str, Any]] = []
    hitches: list[dict[str, Any]] = []
    unexplained: list[dict[str, Any]] = []
    for index in range(1, len(events)):
        start_ms = _int(events[index - 1].get("timestamp_ms"))
        end_ms = _int(events[index].get("timestamp_ms"))
        gap_sec = (end_ms - start_ms) / 1000.0
        if gap_sec < min_gap_sec:
            continue
        overlap = _window_overlap_ms(start_ms, end_ms, windows)
        catchup = same_ms[end_ms]
        in_boss_window = overlap > 0
        is_catchup = catchup >= catchup_burst_min_events
        if not is_catchup and not in_boss_window:
            # Outside a boss window a gap without a catch-up burst is an
            # ordinary lull, travel or no combat at all: nothing was due.
            continue
        attribution, heartbeat_index, commands = _attribution(
            start_ms, end_ms, command_timings, heartbeat_events
        )
        end_event = events[index]
        row = {
            "start_ms": start_ms,
            "end_ms": end_ms,
            "duration_sec": round(gap_sec, 3),
            "route_node_id": str(end_event.get("route_node_id") or ""),
            "route_generation": _int(end_event.get("route_generation")),
            "catchup_events": catchup,
            "detection": "catchup_burst" if is_catchup else "boss_window_event_gap",
            "attribution": attribution,
            "heartbeat_index": heartbeat_index or None,
            "overlapping_commands": commands,
            "boss_window_overlap_sec": round(overlap / 1000.0, 3),
        }
        caused_or_long = attribution != "unattributed" or gap_sec >= unattributed_min_gap_sec
        if caused_or_long or (in_boss_window and is_catchup):
            stalls.append(row)
        elif in_boss_window:
            # Without native ticks a short unexplained gap may be a lull or a
            # freeze that happened to have little due work behind it.
            row["detection"] = "possible_stall"
            unexplained.append(row)
        else:
            hitches.append(row)
    return {
        "schema": "bot_world_stall_scan_v3",
        "source": "combat_log_recent_events",
        "thresholds": {
            "stall_min_gap_sec": min_gap_sec,
            "unattributed_stall_min_gap_sec": unattributed_min_gap_sec,
            "catchup_burst_min_events": catchup_burst_min_events,
            "command_overlap_slack_ms": COMMAND_OVERLAP_SLACK_MS,
            "boss_window_stall_rule": "console_command_or_catchup_burst_or_unattributed_min_gap",
        },
        "event_window": {
            "event_count": len(events),
            "first_ms": _int(events[0].get("timestamp_ms")) if events else 0,
            "last_ms": _int(events[-1].get("timestamp_ms")) if events else 0,
            "recent_events_dropped": _int(log.get("recent_events_dropped")),
        },
        "command_timing_rows": len(command_timings),
        "stalls": stalls,
        "hitches": hitches,
        "boss_window_unexplained_gaps": unexplained,
    }


def native_world_stalls(
    ledger: Mapping[str, Any] | None,
    *,
    combat_log: Mapping[str, Any] | None = None,
    command_timings: Sequence[Mapping[str, Any]] = (),
    windows: Sequence[Mapping[str, Any]] = (),
) -> list[dict[str, Any]]:
    """Return stall rows from native world update diffs of at least 500 ms."""
    events = _events(combat_log if isinstance(combat_log, Mapping) else {})
    same_ms: Counter[int] = Counter()
    for event in events:
        same_ms[_int(event.get("timestamp_ms"))] += _catchup_weight(event)
    rows: list[dict[str, Any]] = []
    for interval in native_stall_intervals(ledger):
        start_ms, end_ms = interval["start_ms"], interval["end_ms"]
        overlap = _window_overlap_ms(start_ms, end_ms, windows)
        window = next(
            (row for row in windows
             if _overlap_ms(start_ms, end_ms, _int(row.get("first_at_ms")), _int(row.get("last_at_ms"))) > 0),
            None,
        )
        attribution, heartbeat_index, commands = _attribution(start_ms, end_ms, command_timings, ())
        rows.append({
            "start_ms": start_ms,
            "end_ms": end_ms,
            # Both ends are game time; diff_ms is the steady-clock diff.
            "duration_sec": round((end_ms - start_ms) / 1000.0, 3),
            "diff_ms": interval["diff_ms"],
            "start_basis": interval["start_basis"],
            "first_update_at_ms": interval["first_update_at_ms"],
            "sequence": interval["sequence"],
            "route_node_id": str((window or {}).get("route_node_id") or ""),
            "route_generation": _int((window or {}).get("route_generation")),
            "catchup_events": same_ms.get(end_ms, 0),
            "detection": "native_world_tick",
            "attribution": attribution,
            "heartbeat_index": heartbeat_index or None,
            "overlapping_commands": commands,
            "boss_window_overlap_sec": round(overlap / 1000.0, 3),
        })
    return rows


def measurement_validity(
    scan: Mapping[str, Any],
    windows: Sequence[Mapping[str, Any]],
    *,
    combat_log_available: bool,
    max_stall_fraction: float = MAX_BOSS_WINDOW_STALL_FRACTION,
    max_single_stall_sec: float = MAX_SINGLE_BOSS_WINDOW_STALL_SEC,
) -> dict[str, Any]:
    """Summarise stall impact on the boss encounter window(s)."""
    stalls = [row for row in scan.get("stalls") or [] if isinstance(row, Mapping)]
    hitches = [row for row in scan.get("hitches") or [] if isinstance(row, Mapping)]
    event_window = scan.get("event_window") if isinstance(scan.get("event_window"), Mapping) else {}
    window_rows: list[dict[str, Any]] = []
    for window in windows:
        first = _int(window.get("first_at_ms"))
        last = _int(window.get("last_at_ms"))
        inside = [
            row for row in stalls
            if _overlap_ms(_int(row.get("start_ms")), _int(row.get("end_ms")), first, last) > 0
        ]
        stalled_ms = sum(
            _overlap_ms(_int(row.get("start_ms")), _int(row.get("end_ms")), first, last)
            for row in inside
        )
        window_rows.append({
            **dict(window),
            "stall_count": len(inside),
            "catchup_burst_stall_count": sum(1 for row in inside if row.get("detection") == "catchup_burst"),
            "event_gap_stall_count": sum(1 for row in inside if row.get("detection") == "boss_window_event_gap"),
            "native_world_tick_stall_count": sum(1 for row in inside if row.get("detection") == "native_world_tick"),
            "stalled_sec": round(stalled_ms / 1000.0, 3),
            "unstalled_duration_sec": round(max(0, last - first - stalled_ms) / 1000.0, 3),
            "stall_fraction": round(stalled_ms / max(1, last - first), 6),
            "max_stall_sec": max((float(row.get("duration_sec") or 0.0) for row in inside), default=0.0),
        })
    total_window_ms = sum(
        max(0, _int(row.get("last_at_ms")) - _int(row.get("first_at_ms"))) for row in window_rows
    )
    boss_stalled_sec = round(sum(float(row["stalled_sec"]) for row in window_rows), 3)
    stall_fraction = round(boss_stalled_sec * 1000.0 / max(1, total_window_ms), 6)
    max_boss_stall = max((float(row["max_stall_sec"]) for row in window_rows), default=0.0)
    reasons: list[str] = []
    if not combat_log_available:
        reasons.append("combat_log_unavailable")
    if not window_rows:
        reasons.append("no_boss_window")
    first_event = _int(event_window.get("first_ms"))
    if window_rows and (
        first_event <= 0
        or any(first_event > _int(row.get("first_at_ms")) for row in window_rows)
    ):
        reasons.append("combat_log_event_window_misses_boss_window")
    if window_rows and stall_fraction > max_stall_fraction:
        reasons.append("boss_window_stall_fraction_exceeded")
    if window_rows and max_boss_stall >= max_single_stall_sec:
        reasons.append("boss_window_stall_too_long")
    return {
        "schema": "bot_measurement_validity_v3",
        "valid_for_dps": not reasons,
        "reasons": reasons,
        "stall_fraction": stall_fraction,
        "max_boss_window_stall_sec": max_boss_stall,
        "boss_window_stalled_sec": boss_stalled_sec,
        "boss_window_duration_sec": round(total_window_ms / 1000.0, 3),
        "boss_window_stall_count": sum(int(row["stall_count"]) for row in window_rows),
        "max_stall_sec": max((float(row.get("duration_sec") or 0.0) for row in stalls), default=0.0),
        "stall_count": len(stalls),
        "stalled_sec": round(sum(float(row.get("duration_sec") or 0.0) for row in stalls), 3),
        "boss_windows": window_rows,
        "hitch_count": len(hitches),
        "max_hitch_sec": max((float(row.get("duration_sec") or 0.0) for row in hitches), default=0.0),
        "thresholds": {
            **dict(scan.get("thresholds") or {}),
            "max_boss_window_stall_fraction": max_stall_fraction,
            "max_single_boss_window_stall_sec": max_single_stall_sec,
        },
        "event_window": dict(event_window),
        "command_timing_rows": _int(scan.get("command_timing_rows")),
    }


def world_stall_report(
    combat_log: Mapping[str, Any] | None,
    combat_analysis: Mapping[str, Any] | None,
    *,
    validation_route_manifest: Mapping[str, Any] | None = None,
    validation_route: Mapping[str, Any] | None = None,
    command_timings: Sequence[Mapping[str, Any]] = (),
    heartbeat_events: Iterable[Mapping[str, Any]] = (),
    world_ticks: Mapping[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return ``(world_stalls, measurement_validity)`` for one run."""
    windows = boss_windows(combat_analysis, validation_route_manifest, validation_route)
    available = isinstance(combat_log, Mapping) and bool(combat_log.get("recent_events"))
    scan = detect_world_stalls(
        combat_log,
        command_timings=command_timings,
        # Integer report seconds are only a fallback for runs recorded
        # before per-command timing receipts existed.
        heartbeat_events=[] if command_timings else list(heartbeat_events),
        windows=windows,
    )
    coverage = native_coverage(world_ticks, windows)
    inferred = measurement_validity(scan, windows, combat_log_available=available)
    if coverage.get("complete_for_boss_windows"):
        native_scan = dict(scan)
        native_scan["stalls"] = native_world_stalls(
            world_ticks, combat_log=combat_log, command_timings=command_timings, windows=windows,
        )
        native_scan["hitches"] = []
        native_scan["thresholds"] = {
            **dict(scan.get("thresholds") or {}),
            "native_world_tick_min_diff_ms": _int(coverage.get("threshold_ms")),
        }
        validity = measurement_validity(native_scan, windows, combat_log_available=available)
        validity["stall_basis"] = "native_world_tick"
        validity["combat_log_inference"] = {
            key: inferred[key]
            for key in (
                "valid_for_dps", "reasons", "stall_fraction", "max_boss_window_stall_sec",
                "boss_window_stalled_sec", "boss_window_stall_count",
            )
        }
        stalls = list(native_scan["stalls"])
    else:
        validity = inferred
        validity["stall_basis"] = "combat_log_inference"
        stalls = list(scan["stalls"])
    coverage["stalls"] = native_stall_intervals(world_ticks)
    validity["native_world_tick"] = coverage
    validity["hitches"] = list(scan["hitches"])
    gaps = [dict(row) for row in scan.get("boss_window_unexplained_gaps") or []]
    if validity["stall_basis"] == "native_world_tick":
        # Native ticks decide the stalls; the combat-log gaps stay lulls.
        lulls = [{**row, "detection": "combat_lull"} for row in gaps]
        possible: list[dict[str, Any]] = []
    else:
        lulls = []
        possible = gaps
    validity["lulls"] = lulls
    validity["lull_count"] = len(lulls)
    validity["max_lull_sec"] = max((float(row.get("duration_sec") or 0.0) for row in lulls), default=0.0)
    validity["boss_window_lull_sec"] = round(sum(float(row.get("boss_window_overlap_sec") or 0.0) for row in lulls), 3)
    validity["possible_stalls"] = possible
    validity["possible_stall_count"] = len(possible)
    validity["max_possible_stall_sec"] = max((float(row.get("duration_sec") or 0.0) for row in possible), default=0.0)
    validity["boss_window_possible_stall_sec"] = round(
        sum(float(row.get("boss_window_overlap_sec") or 0.0) for row in possible), 3
    )
    # valid_for_dps comes from real stalls only; unexplained short gaps make
    # the measurement unverified until native ticks can rule them out.
    unverified = ["boss_window_possible_stall"] if possible else []
    validity["verification"] = "unverified" if unverified else "verified"
    validity["unverified_reasons"] = unverified
    return stalls, validity


def _heartbeat_events(output_dir: Path) -> list[dict[str, Any]]:
    try:
        lines = (Path(output_dir) / "heartbeat_events.jsonl").read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    rows: list[dict[str, Any]] = []
    for line in lines:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def attach_measurement_validity(
    report: dict[str, Any],
    output_dir: Path,
    payloads: Sequence[Mapping[str, Any]],
    *,
    validation_route_manifest: Mapping[str, Any] | None = None,
    validation_route: Mapping[str, Any] | None = None,
) -> None:
    """Attach stall, validity, console-pipe and cleanup receipts to a report.

    ``report["measurement_validity"]["valid_for_dps"]`` applies the boss
    window stall tolerance described in this module's docstring.
    """
    timings = load_command_timings(Path(output_dir))
    combat_log = report.get("combat_log")
    combat_analysis = report.get("combat_analysis")
    status = report.get("status")
    found, validity = world_stall_report(
        combat_log if isinstance(combat_log, Mapping) else None,
        combat_analysis if isinstance(combat_analysis, Mapping) else None,
        validation_route_manifest=validation_route_manifest,
        validation_route=validation_route,
        command_timings=timings,
        heartbeat_events=_heartbeat_events(Path(output_dir)),
        world_ticks=load_world_tick_ledger(
            Path(output_dir), status if isinstance(status, Mapping) else None
        ),
    )
    report["world_stalls"] = found
    report["measurement_validity"] = validity
    report["heartbeat_command_timings"] = timings[-2000:]
    steps = cleanup_steps_from_payloads(payloads)
    if steps:
        report["harness_cleanup_steps"] = steps
    summary = next(
        (
            dict(row) for row in reversed(list(payloads))
            if isinstance(row, Mapping) and row.get("action") == "harness_cleanup_summary"
        ),
        None,
    )
    if summary is not None:
        summary.pop("action", None)
        report["harness_cleanup"] = summary
        report["cleanup_overrun_sec"] = float(summary.get("cleanup_overrun_sec") or 0.0)
    pipe = next(
        (
            dict(row) for row in payloads
            if isinstance(row, Mapping) and row.get("action") == "harness_console_pipe"
        ),
        None,
    )
    if pipe is not None:
        pipe.pop("action", None)
        report["console_pipe_buffer"] = pipe
