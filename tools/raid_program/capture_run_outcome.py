from __future__ import annotations

from typing import Any

try:
    from tools.raid_program.capture_no_bots_baseline import (
        process_sample as _baseline_process_sample,
    )
except ModuleNotFoundError:
    from capture_no_bots_baseline import process_sample as _baseline_process_sample


def _primary_gameplay_terminal(*terminals: dict[str, Any] | None) -> bool:
    """Return whether a controller/native terminal established gameplay failure.

    Evidence-integrity failures that occur while collecting the terminal bundle
    must not erase this primary outcome.  The integrity gates still reject the
    capture; this predicate only preserves the causal classification.
    """

    return any(
        isinstance(terminal, dict)
        and terminal.get("detected") is True
        and terminal.get("classification") == "gameplay_failure"
        for terminal in terminals
    )


def _terminal_evidence_incomplete(
    *,
    primary_gameplay_failure: bool,
    forced_evidence_report: dict[str, Any],
    telemetry_abort: dict[str, Any],
    telemetry_envelopes: dict[str, Any],
    demux_rejections: list[str],
) -> bool:
    """Expose incomplete terminal evidence without making it an acceptance.

    Only a known gameplay terminal gets this causal annotation.  Other
    incomplete captures remain infrastructure/incomplete evidence as before.
    """

    if not primary_gameplay_failure:
        return False
    return bool(
        forced_evidence_report.get("gate_passed") is not True
        or telemetry_abort.get("detected") is True
        or telemetry_envelopes.get("gate_passed") is not True
        or demux_rejections
    )


def _capture_classification(
    *,
    success: bool,
    forbidden_entries: list[Any],
    fixture_terminal_observed: bool = False,
    primary_gameplay_failure: bool,
    operational_infrastructure_abort: bool,
    evidence_incomplete: bool,
) -> str:
    """Classify a capture without letting evidence gaps erase causality.

    Evidence gates remain independent from this label through ``success``.
    An operational abort still takes precedence. A verified fixture terminal
    then keeps its non-gameplay classification, while a retained primary
    gameplay terminal takes precedence over incomplete terminal evidence.
    """

    if success:
        return "success"
    if forbidden_entries:
        return "diagnostic_only"
    if operational_infrastructure_abort:
        return "infrastructure_abort"
    if fixture_terminal_observed:
        return "fixture_terminal_observation"
    if primary_gameplay_failure:
        return "gameplay_failure"
    if evidence_incomplete:
        return "infrastructure_abort"
    return "incomplete_evidence"


def process_resource_sample(
    pid: int,
    *,
    sample_sequence: int,
    scenario_id: str,
    runtime_profile: str,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Retain a compact, identity-bound worldserver resource sample.

    The baseline sampler is the source of truth for `/proc` parsing and CPU
    tick/RSS units.  Only those process fields are retained here; host load,
    memory pressure, and other baseline diagnostics are intentionally not
    copied into the raid telemetry stream.  Runtime identity is attached to
    every row so a later report cannot accidentally join samples from another
    cohort or attempt.
    """
    baseline = _baseline_process_sample(pid)
    runtime = status.get("raid_runtime") if isinstance(status, dict) else None
    runtime = runtime if isinstance(runtime, dict) else {}
    identity: dict[str, Any] = {
        "scenario_id": scenario_id,
        "runtime_profile": runtime_profile,
    }
    if isinstance(status, dict) and status.get("cohort_id") is not None:
        identity["cohort_id"] = status["cohort_id"]
    for field in (
        "server_epoch", "attempt_id", "profile_generation", "profile_content_hash",
        "assignment_generation", "group_guid", "leader_guid", "instance_id",
        "lockout_save_id",
    ):
        value = runtime.get(field)
        if value is not None:
            identity[field] = value
    return {
        "sample_sequence": sample_sequence,
        "process_pid": pid,
        "monotonic_sec": baseline["monotonic_sec"],
        "process_cpu_ticks": baseline["process_cpu_ticks"],
        "process_rss_bytes": baseline["process_rss_bytes"],
        "run_identity": identity,
    }

def summarize_process_resource_samples(
    samples: list[dict[str, Any]], *, tick_rate: int | None = None,
    sampling_errors: list[str] | None = None,
    sampling_error_count: int | None = None,
) -> dict[str, Any]:
    """Summarize retained process samples without copying them into telemetry.

    CPU percentage intentionally matches ``capture_no_bots_baseline``:
    process CPU time divided by wall time, expressed as a percentage of one
    logical core.  A mixed-PID sample set fails closed for CPU delta rather
    than attributing a reused PID to the raid.
    """
    errors = sampling_errors or []
    error_count = len(errors) if sampling_error_count is None else sampling_error_count
    if not samples:
        return {
            "sample_count": 0,
            "process_pid": None,
            "pid_consistent": False,
            "elapsed_seconds": 0.0,
            "cpu_ticks_delta": None,
            "tick_rate": tick_rate,
            "mean_cpu_percent_one_core": None,
            "maximum_rss_bytes": None,
            "minimum_rss_bytes": None,
            "sampling_error_count": error_count,
        }
    pids = [int(row["process_pid"]) for row in samples]
    pid_consistent = len(set(pids)) == 1
    first_time = float(samples[0]["monotonic_sec"])
    last_time = float(samples[-1]["monotonic_sec"])
    elapsed = max(0.0, last_time - first_time)
    ticks_delta = None
    mean_cpu = None
    if pid_consistent and len(samples) > 1:
        ticks_delta = int(samples[-1]["process_cpu_ticks"]) - int(samples[0]["process_cpu_ticks"])
        if tick_rate and tick_rate > 0 and elapsed > 0:
            mean_cpu = round((ticks_delta / tick_rate) / elapsed * 100, 3)
    rss_values = [int(row["process_rss_bytes"]) for row in samples]
    return {
        "sample_count": len(samples),
        "process_pid": pids[0] if pid_consistent else None,
        "pid_consistent": pid_consistent,
        "first_monotonic_sec": round(first_time, 6),
        "last_monotonic_sec": round(last_time, 6),
        "elapsed_seconds": round(elapsed, 3),
        "cpu_ticks_delta": ticks_delta,
        "tick_rate": tick_rate,
        "mean_cpu_percent_one_core": mean_cpu,
        "maximum_rss_bytes": max(rss_values),
        "minimum_rss_bytes": min(rss_values),
        "sampling_error_count": error_count,
    }
