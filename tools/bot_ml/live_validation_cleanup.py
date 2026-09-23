"""Bounded end-of-run cleanup for the live validation watchdogs.

Cleanup exports the combat log, optionally drains retained trace rows,
stops the cohort (``--stop`` or transport cleanup) and, in process mode,
shuts the worldserver down.  Every step is attempted even after an earlier
failure.  Each step gets at most ``CLEANUP_STEP_MAX_SEC`` and all steps share
``CLEANUP_TOTAL_BUDGET_SEC``; ``STOP_RESERVE_SEC`` of that budget is held back
so ``.botauto stop`` always gets a turn.  Shutdown always gets
``SHUTDOWN_GRACE_SEC`` from the moment it is sent.

Cleanup never changes the watchdog verdict: when the heartbeat loop ended on
its own (native clear or a watchdog terminal), a slow, failed or skipped
cleanup step, time spent past the emergency cap, or a shutdown that needed a
kill is recorded in the ``harness_cleanup_summary`` receipt
(``report["harness_cleanup"]``, ``report["cleanup_overrun_sec"]``), never as
``timed_out``.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Callable

CLEANUP_STEP_MAX_SEC = 180
CLEANUP_TOTAL_BUDGET_SEC = 600
STOP_RESERVE_SEC = 60
SHUTDOWN_GRACE_SEC = 10


def is_stop_command(command_text: str) -> bool:
    return str(command_text or "").split()[:2] == [".botauto", "stop"]


@dataclass
class CleanupBudget:
    """Per-step and total time budget for one cleanup phase."""

    deadline: float | None = None
    total_sec: float = CLEANUP_TOTAL_BUDGET_SEC
    step_max_sec: float = CLEANUP_STEP_MAX_SEC
    stop_reserve_sec: float = STOP_RESERVE_SEC
    stop_pending: bool = False
    clock: Callable[[], float] = time.monotonic
    started: float = 0.0
    failed_steps: list[dict[str, Any]] = field(default_factory=list)
    skipped_steps: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.started = self.clock()

    def elapsed(self) -> float:
        return max(0.0, self.clock() - self.started)

    def remaining(self) -> float:
        return float(self.total_sec) - self.elapsed()

    def step_timeout(self, command_text: str) -> int:
        """Return this step's timeout in whole seconds; 0 means skip it."""
        remaining = self.remaining()
        if is_stop_command(command_text):
            # The reserve keeps the stop reachable; its own cap still holds.
            return int(min(self.step_max_sec, max(self.stop_reserve_sec, remaining)))
        if self.stop_pending:
            remaining -= self.stop_reserve_sec
        if remaining < 1.0:
            return 0
        return int(min(self.step_max_sec, remaining))

    def record(self, command_text: str, *, completed: bool, returncode: int, timed_out: bool) -> None:
        if not completed:
            self.failed_steps.append({
                "command": command_text,
                "returncode": int(returncode),
                "timed_out": bool(timed_out),
            })

    def skip(self, command_text: str) -> None:
        self.skipped_steps.append(command_text)

    def summary_receipt(
        self,
        *,
        watchdog_timed_out: bool,
        shutdown_sent: bool = False,
        shutdown_killed: bool = False,
        worldserver_exit_code: int | None = None,
    ) -> str:
        finished = self.clock()
        overrun = 0.0
        if self.deadline is not None:
            overrun = max(0.0, finished - self.deadline) - max(0.0, self.started - self.deadline)
        row = {
            "action": "harness_cleanup_summary",
            "schema": "bot_harness_cleanup_v1",
            "complete": not self.failed_steps and not self.skipped_steps and not shutdown_killed,
            "cleanup_elapsed_sec": round(finished - self.started, 3),
            "cleanup_budget_sec": float(self.total_sec),
            "cleanup_step_max_sec": float(self.step_max_sec),
            "cleanup_stop_reserve_sec": float(self.stop_reserve_sec),
            "cleanup_budget_exhausted": bool(self.skipped_steps) or self.elapsed() > self.total_sec,
            "cleanup_overrun_sec": round(max(0.0, overrun), 3),
            "watchdog_timed_out": bool(watchdog_timed_out),
            "failed_steps": list(self.failed_steps),
            "skipped_steps": list(self.skipped_steps),
            "shutdown_grace_sec": SHUTDOWN_GRACE_SEC,
            "shutdown_sent": bool(shutdown_sent),
            "shutdown_killed": bool(shutdown_killed),
            "worldserver_exit_code": worldserver_exit_code,
        }
        return json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n"
