"""Compare retained capture receipts without rereading duplicate native logs."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def capture_cost(report: dict[str, Any]) -> dict[str, Any]:
    resources = report.get("resource_sampling", {}).get("summary", {})
    schedule = report.get("telemetry_schedule", {})
    receipts = schedule.get("trace_transport_receipts", [])
    receipts = receipts if isinstance(receipts, list) else []
    duration = resources.get("elapsed_seconds")
    duration = duration if isinstance(duration, (int, float)) and duration > 0 else None
    log_bytes = report.get("log_bytes")
    parse_times = [r["parse_duration_seconds"] for r in receipts
                   if isinstance(r.get("parse_duration_seconds"), (int, float))]
    response_sizes = [r["response_bytes"] for r in receipts
                      if isinstance(r.get("response_bytes"), int)]
    trace_bytes = sum(response_sizes) if response_sizes else None
    return {
        "capture_id": report.get("capture_id"),
        "sampled_elapsed_seconds": duration,
        "native_log_bytes": log_bytes,
        "native_log_bytes_per_second": log_bytes / duration
        if isinstance(log_bytes, int) and duration else None,
        "trace_response_bytes": trace_bytes,
        "trace_parse_seconds": sum(parse_times) if parse_times else None,
        "trace_parse_seconds_per_sampled_second": sum(parse_times) / duration
        if parse_times and duration else None,
        "trace_receipt_count": len(receipts),
        "commands": schedule.get("commands_sent", {}),
        "diagnose_interval_seconds": schedule.get("diagnose_interval_seconds"),
        "mean_worldserver_cpu_percent_one_core": resources.get("mean_cpu_percent_one_core"),
        "maximum_worldserver_rss_bytes": resources.get("maximum_rss_bytes"),
        "sampling_errors": resources.get("sampling_error_count"),
    }


def compare(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    before, after = capture_cost(baseline), capture_cost(candidate)
    metrics = ("native_log_bytes", "native_log_bytes_per_second",
               "trace_parse_seconds_per_sampled_second",
               "mean_worldserver_cpu_percent_one_core", "maximum_worldserver_rss_bytes")
    changes = {}
    for metric in metrics:
        a, b = before[metric], after[metric]
        changes[metric] = ((b / a - 1) * 100
                           if isinstance(a, (int, float)) and a > 0
                           and isinstance(b, (int, float)) else None)
    return {
        "schema": "bot_capture_cost_comparison_v1",
        "baseline": before, "candidate": after, "change_percent": changes,
        "measurement_scope": "Observed full-capture receipts, including startup and trash. "
        "Fight duration, workload and gameplay may differ. CPU changes are not an isolated "
        "estimate of instrumentation cost. Trace parser cost excludes other JSON channels. "
        "Normalized raw JSONL and native logs contain overlapping evidence; compare native "
        "bytes once rather than summing copies. Missing measurements remain null.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("baseline", type=Path)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare(json.loads(args.baseline.read_text()), json.loads(args.candidate.read_text()))
    args.output.write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
