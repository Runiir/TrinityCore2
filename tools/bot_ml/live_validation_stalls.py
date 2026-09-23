"""World-thread stall detection and DPS measurement validity.

A frozen world thread produces a combat-log signature: no event for the
freeze, then every periodic effect and swing that was due lands in the same
millisecond (the catch-up burst).  The Magmaw 10N evidence runs showed
heartbeat freezes of 3.6-12.3 s ending in 56-260 same-millisecond events,
plus unrelated 0.4-0.8 s world-update hitches ending in 13-53 events, while
ordinary combat lulls end with 1-8 events.

``world_stalls`` lists catch-up gaps of at least ``STALL_MIN_GAP_SEC`` that
began after a harness console command was sent and before it completed (the
heartbeat freeze class), and any catch-up gap of at least
``UNATTRIBUTED_STALL_MIN_GAP_SEC`` whatever its cause.  Shorter unattributed
catch-up gaps (including a command that was merely sent into a running
hitch) are summarised as hitches and do not invalidate a measurement.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

try:
    from .live_validation_heartbeat import cleanup_steps_from_payloads, load_command_timings
except ImportError:  # pragma: no cover - script-style imports
    from live_validation_heartbeat import cleanup_steps_from_payloads, load_command_timings

STALL_MIN_GAP_SEC = 0.5
UNATTRIBUTED_STALL_MIN_GAP_SEC = 1.0
CATCHUP_BURST_MIN_EVENTS = 10
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
    """Scan combat-log event gaps for world-thread freezes."""
    log = combat_log if isinstance(combat_log, Mapping) else {}
    events = _events(log)
    same_ms: Counter[int] = Counter()
    for row in events:
        same_ms[_int(row.get("timestamp_ms"))] += _catchup_weight(row)
    stalls: list[dict[str, Any]] = []
    hitches: list[dict[str, Any]] = []
    for index in range(1, len(events)):
        start_ms = _int(events[index - 1].get("timestamp_ms"))
        end_ms = _int(events[index].get("timestamp_ms"))
        gap_sec = (end_ms - start_ms) / 1000.0
        if gap_sec < min_gap_sec:
            continue
        catchup = same_ms[end_ms]
        if catchup < catchup_burst_min_events:
            # Ordinary combat lull or no combat at all: nothing was due.
            continue
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
        end_event = events[index]
        row = {
            "start_ms": start_ms,
            "end_ms": end_ms,
            "duration_sec": round(gap_sec, 3),
            "route_node_id": str(end_event.get("route_node_id") or ""),
            "route_generation": _int(end_event.get("route_generation")),
            "catchup_events": catchup,
            "attribution": attribution,
            "heartbeat_index": heartbeat_index or None,
            "overlapping_commands": commands,
        }
        overlap = sum(
            _overlap_ms(start_ms, end_ms, _int(window.get("first_at_ms")), _int(window.get("last_at_ms")))
            for window in windows
        )
        row["boss_window_overlap_sec"] = round(overlap / 1000.0, 3)
        if attribution != "unattributed" or gap_sec >= unattributed_min_gap_sec:
            stalls.append(row)
        else:
            hitches.append(row)
    return {
        "schema": "bot_world_stall_scan_v1",
        "source": "combat_log_recent_events",
        "thresholds": {
            "stall_min_gap_sec": min_gap_sec,
            "unattributed_stall_min_gap_sec": unattributed_min_gap_sec,
            "catchup_burst_min_events": catchup_burst_min_events,
            "command_overlap_slack_ms": COMMAND_OVERLAP_SLACK_MS,
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
    }


def measurement_validity(
    scan: Mapping[str, Any],
    windows: Sequence[Mapping[str, Any]],
    *,
    combat_log_available: bool,
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
        hitch_ms = sum(
            _overlap_ms(_int(row.get("start_ms")), _int(row.get("end_ms")), first, last)
            for row in hitches
        )
        window_rows.append({
            **dict(window),
            "stall_count": len(inside),
            "stalled_sec": round(stalled_ms / 1000.0, 3),
            "unstalled_duration_sec": round(max(0, last - first - stalled_ms) / 1000.0, 3),
            "stall_fraction": round(stalled_ms / max(1, last - first), 6),
            "max_stall_sec": max((float(row.get("duration_sec") or 0.0) for row in inside), default=0.0),
            "hitch_sec": round(hitch_ms / 1000.0, 3),
        })
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
    boss_stalls = [row for row in window_rows if int(row["stall_count"]) > 0]
    if boss_stalls:
        reasons.append("world_stall_overlaps_boss_window")
    boss_stalled_sec = round(sum(float(row["stalled_sec"]) for row in window_rows), 3)
    return {
        "schema": "bot_measurement_validity_v1",
        "valid_for_dps": not reasons,
        "reasons": reasons,
        "boss_window_stalled_sec": boss_stalled_sec,
        "boss_window_stall_count": sum(int(row["stall_count"]) for row in window_rows),
        "max_boss_window_stall_sec": max((float(row["max_stall_sec"]) for row in window_rows), default=0.0),
        "max_stall_sec": max((float(row.get("duration_sec") or 0.0) for row in stalls), default=0.0),
        "stall_count": len(stalls),
        "stalled_sec": round(sum(float(row.get("duration_sec") or 0.0) for row in stalls), 3),
        "boss_windows": window_rows,
        "hitch_count": len(hitches),
        "max_hitch_sec": max((float(row.get("duration_sec") or 0.0) for row in hitches), default=0.0),
        "boss_window_hitch_sec": round(sum(float(row["hitch_sec"]) for row in window_rows), 3),
        "thresholds": dict(scan.get("thresholds") or {}),
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
    validity = measurement_validity(scan, windows, combat_log_available=available)
    validity["hitches"] = scan["hitches"]
    return list(scan["stalls"]), validity


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
    """Attach ``world_stalls``, ``measurement_validity`` and cleanup receipts.

    ``report["measurement_validity"]["valid_for_dps"]`` is true only when no
    stall overlaps a boss encounter window.
    """
    timings = load_command_timings(Path(output_dir))
    combat_log = report.get("combat_log")
    combat_analysis = report.get("combat_analysis")
    found, validity = world_stall_report(
        combat_log if isinstance(combat_log, Mapping) else None,
        combat_analysis if isinstance(combat_analysis, Mapping) else None,
        validation_route_manifest=validation_route_manifest,
        validation_route=validation_route,
        command_timings=timings,
        heartbeat_events=_heartbeat_events(Path(output_dir)),
    )
    report["world_stalls"] = found
    report["measurement_validity"] = validity
    report["heartbeat_command_timings"] = timings[-2000:]
    steps = cleanup_steps_from_payloads(payloads)
    if steps:
        report["harness_cleanup_steps"] = steps
