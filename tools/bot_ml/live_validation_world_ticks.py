"""Native world-update tick ledger for live validation.

The worldserver records every world update whose diff (time since the
previous world tick) is at least 500 ms and publishes the rows cumulatively
in ``.botauto status`` as ``world_update`` (``BotWorldTickRecorder.h``).
Rows carry a sequence, and the server keeps the newest 256, so the harness
merges every status it reads (each heartbeat and once at cleanup) and can
tell when rows were lost.  A native row is direct evidence of a frozen world
thread over ``[start_ms, at_ms]`` on the combat-log clock.  ``start_ms`` is
the previous update's game time; rows from recorders that predate it fall
back to ``at_ms - diff_ms`` (``diff_ms`` is on the steady world-loop clock).

Sequences restart with the worldserver process, so rows are keyed by
``(first_update_at_ms, sequence)``: every recorder start is its own epoch.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

WORLD_TICK_LEDGER_FILE = "world_update_ticks.json"

PayloadParser = Callable[[str], list[dict[str, Any]]]

_EPOCH_SUMMARY_KEYS = (
    "now_ms", "threshold_ms", "capacity", "update_count", "max_diff_ms",
    "max_diff_at_ms", "stall_count", "dropped_count",
)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class _Epoch:
    def __init__(self, first_update_at_ms: int) -> None:
        self.first_update_at_ms = first_update_at_ms
        self.reads = 0
        self.rows: dict[int, dict[str, int]] = {}
        self.latest: dict[str, Any] = {}

    def observe(self, world_update: Mapping[str, Any]) -> None:
        self.reads += 1
        if _int(world_update.get("now_ms")) >= _int(self.latest.get("now_ms")):
            self.latest = {key: value for key, value in world_update.items() if key != "stalls"}
        for row in world_update.get("stalls") or []:
            if not isinstance(row, Mapping):
                continue
            sequence = _int(row.get("sequence"))
            if sequence <= 0:
                continue
            merged = {
                "first_update_at_ms": self.first_update_at_ms,
                "sequence": sequence,
                "at_ms": _int(row.get("at_ms")),
                "diff_ms": _int(row.get("diff_ms")),
            }
            if _int(row.get("start_ms")) > 0:
                merged["start_ms"] = _int(row.get("start_ms"))
            self.rows[sequence] = merged

    def snapshot(self) -> dict[str, Any]:
        stall_count = _int(self.latest.get("stall_count"))
        summary = {key: _int(self.latest.get(key)) for key in _EPOCH_SUMMARY_KEYS}
        return {
            "first_update_at_ms": self.first_update_at_ms,
            "reads": self.reads,
            **summary,
            "missing_sequences": sorted(set(range(1, stall_count + 1)) - set(self.rows)),
            "stalls": [self.rows[key] for key in sorted(self.rows)],
        }


class WorldTickLedger:
    """Merge cumulative ``world_update`` snapshots by epoch and sequence."""

    def __init__(self) -> None:
        self.reads = 0
        self.epochs: dict[int, _Epoch] = {}

    def observe(self, world_update: Mapping[str, Any] | None) -> bool:
        if not isinstance(world_update, Mapping) or "stall_count" not in world_update:
            return False
        first_update = _int(world_update.get("first_update_at_ms"))
        epoch = self.epochs.get(first_update)
        if epoch is None:
            epoch = self.epochs[first_update] = _Epoch(first_update)
        epoch.observe(world_update)
        self.reads += 1
        return True

    def observe_output(self, output: str, parse: PayloadParser) -> bool:
        if '"world_update"' not in (output or ""):
            return False
        observed = False
        for payload in parse(output):
            if payload.get("action") == "botauto_status":
                observed = self.observe(payload.get("world_update")) or observed
        return observed

    def snapshot(self) -> dict[str, Any]:
        epochs = [self.epochs[key].snapshot() for key in sorted(self.epochs)]
        latest = max(epochs, key=lambda row: row["now_ms"], default={})
        return {
            "schema": "bot_world_update_tick_ledger_v2",
            "reads": self.reads,
            "epoch_count": len(epochs),
            # Top-level counters describe the most recently read epoch.
            **{key: _int(latest.get(key)) for key in ("first_update_at_ms", *_EPOCH_SUMMARY_KEYS)},
            "missing_sequences": list(latest.get("missing_sequences") or []),
            "epochs": epochs,
            "stalls": [row for epoch in epochs for row in epoch["stalls"]],
        }

    def write(self, output_dir: Path) -> None:
        if not self.reads:
            return
        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
            (Path(output_dir) / WORLD_TICK_LEDGER_FILE).write_text(
                json.dumps(self.snapshot(), sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
        except OSError:
            pass


def load_world_tick_ledger(
    output_dir: Path, status: Mapping[str, Any] | None = None
) -> dict[str, Any] | None:
    """Return the merged ledger, or one final status snapshot as fallback."""
    try:
        payload = json.loads((Path(output_dir) / WORLD_TICK_LEDGER_FILE).read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except (OSError, json.JSONDecodeError):
        pass
    ledger = WorldTickLedger()
    if isinstance(status, Mapping) and ledger.observe(status.get("world_update")):
        return ledger.snapshot()
    return None


def ledger_epochs(ledger: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    """Return per-recorder epochs; a v1 ledger is one epoch."""
    if not isinstance(ledger, Mapping):
        return []
    epochs = ledger.get("epochs")
    if isinstance(epochs, list):
        return [epoch for epoch in epochs if isinstance(epoch, Mapping)]
    return [ledger]


def _epoch_gap_reason(epoch: Mapping[str, Any], first: int) -> str:
    """Return why lost rows of this epoch could hide a stall after ``first``."""
    missing = [_int(value) for value in epoch.get("missing_sequences") or []]
    if not missing:
        return ""
    newest_missing = max(missing)
    rows = sorted(
        (row for row in epoch.get("stalls") or [] if isinstance(row, Mapping)),
        key=lambda item: _int(item.get("sequence")),
    )
    anchor = next((row for row in rows if _int(row.get("sequence")) > newest_missing), None)
    if anchor is None or _interval(anchor)[0] >= first:
        return "world_update_rows_lost_near_boss_window"
    return ""


def native_coverage(
    ledger: Mapping[str, Any] | None, windows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Decide whether native rows fully describe every boss window.

    Each window must lie inside one recorder epoch: the recorder was already
    ticking when the window started, a status was read after it ended, and no
    lost row of that epoch could fall inside it.  A lost row is only harmless
    when a retained row older than the window follows it.
    """
    epochs = ledger_epochs(ledger)
    if not epochs or _int((ledger or {}).get("reads")) <= 0:
        return {"available": False, "complete_for_boss_windows": False, "reason": "no_world_update_reads"}
    reason = ""
    for window in windows:
        first = _int(window.get("first_at_ms"))
        last = _int(window.get("last_at_ms"))
        started = [
            epoch for epoch in epochs
            if 0 < _int(epoch.get("first_update_at_ms")) <= first
        ]
        if not started:
            reason = "world_update_recorder_started_after_boss_window"
            break
        # The newest recorder that started before the window owns it; a
        # restart inside the window leaves it without complete coverage.
        epoch = max(started, key=lambda row: _int(row.get("first_update_at_ms")))
        if any(first < _int(row.get("first_update_at_ms")) <= last for row in epochs):
            reason = "worldserver_restarted_during_boss_window"
        elif _int(epoch.get("now_ms")) < last:
            reason = "no_world_update_read_after_boss_window"
        else:
            reason = _epoch_gap_reason(epoch, first)
        if reason:
            break
    if not windows:
        reason = reason or "no_boss_window"
    latest = max(epochs, key=lambda row: _int(row.get("now_ms")))
    return {
        "available": True,
        "complete_for_boss_windows": not reason,
        "reason": reason,
        "reads": _int((ledger or {}).get("reads")),
        "epoch_count": len(epochs),
        "now_ms": _int(latest.get("now_ms")),
        "first_update_at_ms": _int(latest.get("first_update_at_ms")),
        "threshold_ms": _int(latest.get("threshold_ms")),
        "update_count": _int(latest.get("update_count")),
        "stall_count": sum(_int(epoch.get("stall_count")) for epoch in epochs),
        "dropped_count": sum(_int(epoch.get("dropped_count")) for epoch in epochs),
        "missing_sequences": [
            {"first_update_at_ms": _int(epoch.get("first_update_at_ms")), "sequence": _int(value)}
            for epoch in epochs for value in epoch.get("missing_sequences") or []
        ],
        "max_diff_ms": max(_int(epoch.get("max_diff_ms")) for epoch in epochs),
        "max_diff_at_ms": _int(max(epochs, key=lambda row: _int(row.get("max_diff_ms"))).get("max_diff_at_ms")),
    }


def _interval(row: Mapping[str, Any]) -> tuple[int, int, str]:
    """Return ``(start_ms, end_ms, basis)`` on the combat-log clock."""
    end_ms = _int(row.get("at_ms"))
    start_ms = _int(row.get("start_ms"))
    if 0 < start_ms <= end_ms:
        return start_ms, end_ms, "previous_update_game_time"
    return end_ms - _int(row.get("diff_ms")), end_ms, "at_ms_minus_diff_ms"


def native_stall_intervals(ledger: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Return ``[start_ms, end_ms]`` intervals of native world stalls."""
    rows: list[dict[str, Any]] = []
    for epoch in ledger_epochs(ledger):
        epoch_start = _int(epoch.get("first_update_at_ms"))
        for row in epoch.get("stalls") or []:
            if not isinstance(row, Mapping):
                continue
            start_ms, end_ms, basis = _interval(row)
            if end_ms <= 0 or end_ms <= start_ms:
                continue
            rows.append({
                "first_update_at_ms": _int(row.get("first_update_at_ms")) or epoch_start,
                "sequence": _int(row.get("sequence")),
                "start_ms": start_ms,
                "end_ms": end_ms,
                "diff_ms": _int(row.get("diff_ms")),
                "start_basis": basis,
            })
    return sorted(rows, key=lambda row: (row["end_ms"], row["first_update_at_ms"], row["sequence"]))
