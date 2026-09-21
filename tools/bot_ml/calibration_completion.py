"""Timing and completion state for native isolated calibration windows."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Any, Mapping


CALIBRATION_SCORING_SECONDS = 300.0
CALIBRATION_SCORING_MILLISECONDS = 300_000


def _number(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if math.isfinite(parsed) else 0.0


def _integer(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def native_calibration_window_complete(calibration: Mapping[str, Any]) -> bool:
    """Require the native terminal marker and a full scored window.

    A status payload can report a terminal-looking phase before the native
    clock has accumulated all 300 scored seconds.  The launcher must keep
    polling in that case; acceptance remains responsible for the detailed
    evidence checks after capture.
    """
    if calibration.get("window_complete") is not True:
        return False
    if str(calibration.get("phase") or "").lower() != "complete":
        return False
    if _number(calibration.get("scored_seconds")) != CALIBRATION_SCORING_SECONDS:
        return False
    started = _integer(calibration.get("scored_started_at_ms"))
    ended = _integer(calibration.get("scored_ended_at_ms"))
    if started > 0 and ended > 0:
        return ended - started == CALIBRATION_SCORING_MILLISECONDS
    return True


@dataclass
class CalibrationCompletionClock:
    """Track warmup and scoring separately for a bounded native watchdog."""

    warmup_timeout_sec: float
    heartbeat_sec: float
    started_monotonic: float
    scoring_started_monotonic: float | None = None
    scoring_started_at_ms: int = 0
    phase: str = ""
    scored_seconds: float = 0.0
    complete: bool = False

    def observe(
        self,
        calibration: Mapping[str, Any],
        now: float,
    ) -> str | None:
        self.phase = str(calibration.get("phase") or "").lower()
        self.scored_seconds = _number(calibration.get("scored_seconds"))
        native_started = _integer(calibration.get("scored_started_at_ms"))
        scoring_phase = (
            native_started > 0
            or self.scored_seconds > 0.0
            or self.phase in {"scoring", "complete"}
        )
        if scoring_phase and self.scoring_started_monotonic is None:
            self.scoring_started_monotonic = now
            self.scoring_started_at_ms = native_started
        self.complete = native_calibration_window_complete(calibration)
        if self.complete:
            return "complete"
        if self.scoring_started_monotonic is None:
            if now - self.started_monotonic >= max(1.0, self.warmup_timeout_sec):
                return "calibration_pre_scoring_timeout"
            return None
        # The native terminal marker is authoritative.  This deadline is an
        # infrastructure bound with one polling interval of grace; reaching
        # it never counts as a successful calibration window.
        scoring_deadline = (
            self.scoring_started_monotonic
            + CALIBRATION_SCORING_SECONDS
            + max(1.0, self.heartbeat_sec)
        )
        if now >= scoring_deadline:
            return "calibration_scoring_timeout"
        return None

    def receipt(self, now: float) -> dict[str, Any]:
        scoring_elapsed = (
            max(0.0, now - self.scoring_started_monotonic)
            if self.scoring_started_monotonic is not None
            else 0.0
        )
        return {
            "schema": "bot_calibration_completion_clock_v1",
            "mode": "native_completion",
            "phase": self.phase,
            "native_scoring_started": self.scoring_started_monotonic is not None,
            "native_scoring_started_at_ms": self.scoring_started_at_ms,
            "warmup_elapsed_seconds": round(
                max(
                    0.0,
                    (self.scoring_started_monotonic or now) - self.started_monotonic,
                ),
                3,
            ),
            "scoring_elapsed_seconds": round(scoring_elapsed, 3),
            "scored_seconds": self.scored_seconds,
            "required_scoring_seconds": CALIBRATION_SCORING_SECONDS,
            "window_complete": self.complete,
        }


def native_calibration_requested(
    *, calibration_only: bool, observe_sec_was_explicit: bool
) -> bool:
    """Select native completion only when no observation timer was supplied."""
    return bool(calibration_only and not observe_sec_was_explicit)
