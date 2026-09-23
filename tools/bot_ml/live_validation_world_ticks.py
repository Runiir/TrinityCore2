"""Native world-update tick ledger for live validation.

The worldserver records every world update whose diff (time since the
previous world tick) is at least 500 ms and publishes the rows cumulatively
in ``.botauto status`` as ``world_update`` (``BotWorldTickRecorder.h``).
Rows carry a sequence, and the server keeps the newest 256, so the harness
merges every status it reads (each heartbeat and once at cleanup) and can
tell when rows were lost.  A native row is direct evidence of a frozen world
thread over ``[at_ms - diff_ms, at_ms]`` on the combat-log clock.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

WORLD_TICK_LEDGER_FILE = "world_update_ticks.json"

PayloadParser = Callable[[str], list[dict[str, Any]]]


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


class WorldTickLedger:
    """Merge cumulative ``world_update`` snapshots by stall sequence."""

    def __init__(self) -> None:
        self.reads = 0
        self.rows: dict[int, dict[str, int]] = {}
        self.latest: dict[str, Any] = {}

    def observe(self, world_update: Mapping[str, Any] | None) -> bool:
        if not isinstance(world_update, Mapping) or "stall_count" not in world_update:
            return False
        self.reads += 1
        if _int(world_update.get("now_ms")) >= _int(self.latest.get("now_ms")):
            self.latest = {key: value for key, value in world_update.items() if key != "stalls"}
        for row in world_update.get("stalls") or []:
            if not isinstance(row, Mapping):
                continue
            sequence = _int(row.get("sequence"))
            if sequence > 0:
                self.rows[sequence] = {
                    "sequence": sequence,
                    "at_ms": _int(row.get("at_ms")),
                    "diff_ms": _int(row.get("diff_ms")),
                }
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
        stall_count = _int(self.latest.get("stall_count"))
        missing = sorted(set(range(1, stall_count + 1)) - set(self.rows))
        return {
            "schema": "bot_world_update_tick_ledger_v1",
            "reads": self.reads,
            "now_ms": _int(self.latest.get("now_ms")),
            "threshold_ms": _int(self.latest.get("threshold_ms")),
            "capacity": _int(self.latest.get("capacity")),
            "update_count": _int(self.latest.get("update_count")),
            "first_update_at_ms": _int(self.latest.get("first_update_at_ms")),
            "max_diff_ms": _int(self.latest.get("max_diff_ms")),
            "max_diff_at_ms": _int(self.latest.get("max_diff_at_ms")),
            "stall_count": stall_count,
            "dropped_count": _int(self.latest.get("dropped_count")),
            "missing_sequences": missing,
            "stalls": [self.rows[key] for key in sorted(self.rows)],
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


def native_coverage(
    ledger: Mapping[str, Any] | None, windows: Sequence[Mapping[str, Any]]
) -> dict[str, Any]:
    """Decide whether native rows fully describe every boss window.

    Coverage needs a read after each window ended, a recorder that was
    already ticking when each window started, and no lost row that could
    fall inside a window.  A lost row (ring overflow between reads) is only
    harmless when a retained row older than the window follows it.
    """
    if not isinstance(ledger, Mapping) or _int(ledger.get("reads")) <= 0:
        return {"available": False, "complete_for_boss_windows": False, "reason": "no_world_update_reads"}
    rows = [row for row in ledger.get("stalls") or [] if isinstance(row, Mapping)]
    missing = [_int(value) for value in ledger.get("missing_sequences") or []]
    now_ms = _int(ledger.get("now_ms"))
    first_update = _int(ledger.get("first_update_at_ms"))
    reason = ""
    for window in windows:
        first = _int(window.get("first_at_ms"))
        last = _int(window.get("last_at_ms"))
        if now_ms < last:
            reason = "no_world_update_read_after_boss_window"
        elif first_update <= 0 or first_update > first:
            reason = "world_update_recorder_started_after_boss_window"
        elif missing:
            newest_missing = max(missing)
            anchor = next(
                (row for row in sorted(rows, key=lambda item: _int(item.get("sequence")))
                 if _int(row.get("sequence")) > newest_missing),
                None,
            )
            if anchor is None or _int(anchor.get("at_ms")) - _int(anchor.get("diff_ms")) >= first:
                reason = "world_update_rows_lost_near_boss_window"
        if reason:
            break
    if not windows:
        reason = reason or "no_boss_window"
    return {
        "available": True,
        "complete_for_boss_windows": not reason,
        "reason": reason,
        "reads": _int(ledger.get("reads")),
        "now_ms": now_ms,
        "first_update_at_ms": first_update,
        "threshold_ms": _int(ledger.get("threshold_ms")),
        "update_count": _int(ledger.get("update_count")),
        "stall_count": _int(ledger.get("stall_count")),
        "dropped_count": _int(ledger.get("dropped_count")),
        "missing_sequences": missing,
        "max_diff_ms": _int(ledger.get("max_diff_ms")),
        "max_diff_at_ms": _int(ledger.get("max_diff_at_ms")),
    }


def native_stall_intervals(ledger: Mapping[str, Any] | None) -> list[dict[str, int]]:
    """Return ``[start_ms, end_ms]`` intervals of native world stalls."""
    if not isinstance(ledger, Mapping):
        return []
    rows: list[dict[str, int]] = []
    for row in ledger.get("stalls") or []:
        if not isinstance(row, Mapping):
            continue
        end_ms = _int(row.get("at_ms"))
        diff_ms = _int(row.get("diff_ms"))
        if end_ms <= 0 or diff_ms <= 0:
            continue
        rows.append({
            "sequence": _int(row.get("sequence")),
            "start_ms": end_ms - diff_ms,
            "end_ms": end_ms,
            "diff_ms": diff_ms,
        })
    return sorted(rows, key=lambda row: (row["end_ms"], row["sequence"]))
