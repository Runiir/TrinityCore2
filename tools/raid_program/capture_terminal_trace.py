"""Identity-bound terminal trace collection and pending-page drain."""
from __future__ import annotations

import time
from typing import Any, Callable

from tools.raid_program.capture_telemetry_transport import (
    TelemetryScheduler,
    TelemetryTransportLedger,
    drain_pending_trace_batches,
)


def collect_terminal_trace(
    *,
    process: Any,
    log_cursor: Any,
    combat_log_delta_controller: Any,
    scheduler: TelemetryScheduler,
    transport_ledger: TelemetryTransportLedger,
    command_counts: dict[str, int],
    expected_status: dict[str, Any] | None,
    telemetry_timeout_seconds: float,
    record_resource_sample: Callable[[], None],
    validate_bundle: Callable[..., dict[str, Any]],
    drain_pending: Callable[..., dict[str, Any]] = drain_pending_trace_batches,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> tuple[dict[str, Any], list[dict[str, Any]], int]:
    """Request final diagnosis plus delta trace, then drain retained pages."""

    scheduler.force_diagnosis(include_trace=True)
    requested_at = monotonic()
    commands = scheduler.commands_due(requested_at)
    required = {"botauto diagnose all", "botauto trace all 128 delta"}
    if not required.issubset(commands):
        return ({
            "requested": False,
            "gate_passed": False,
            "missing_channels": [
                channel for channel, command in (
                    ("diagnosis", "botauto diagnose all"),
                    ("trace", "botauto trace all 128 delta"),
                ) if command not in commands
            ],
            "rejections": ["forced_request_commands_not_scheduled"],
            "commands": commands,
        }, [], 0)

    for command in commands:
        if command == "botauto status":
            command_counts["status"] += 1
        elif command == "botauto diagnose all":
            command_counts["diagnose"] += 1
        elif command == "botauto trace all 128 delta":
            command_counts["trace"] += 1
    process.stdin.write(("\n".join(commands) + "\n").encode())
    process.stdin.flush()
    transport_ledger.command_sent(
        commands, sent_at_monotonic=requested_at,
        scheduler_state=scheduler.state(),
    )

    observed_bundle: list[tuple[dict[str, Any], float]] = []
    diagnoses: list[dict[str, Any]] = []
    trace_count = 0
    initial_trace: tuple[dict[str, Any], float] | None = None
    deadline = requested_at + telemetry_timeout_seconds
    report: dict[str, Any] = {
        "requested": True,
        "gate_passed": False,
        "missing_channels": ["diagnosis", "trace"],
        "rejections": ["forced_responses_not_observed"],
        "commands": commands,
    }
    while monotonic() < deadline:
        sleep(min(0.25, max(0.0, deadline - monotonic())))
        record_resource_sample()
        new_observations = log_cursor.read_new_observations()
        combat_log_delta_controller.observe_rows([
            observation.row for observation in new_observations
        ])
        receipt_indexes: list[int] = []
        trace_rows: list[dict[str, Any]] = []
        for observation in new_observations:
            row = observation.row
            observed_at = observation.response_complete_observed_at_monotonic
            if row.get("action") == "botauto_diagnose":
                diagnoses.append(row)
                observed_bundle.append((row, observed_at))
            elif row.get("action") == "botauto_trace":
                trace_count += 1
                trace_rows.append(row)
                observed_bundle.append((row, observed_at))
                initial_trace = (row, observed_at)
                receipt_index = transport_ledger.observe(observation)
                if receipt_index is not None:
                    receipt_indexes.append(receipt_index)
        scheduler.observe_trace(trace_rows, observed_at=monotonic())
        transport_ledger.finalize_responses(receipt_indexes, scheduler.state())
        report = validate_bundle(
            observed_bundle, expected_status,
            requested_at_monotonic=requested_at,
            freshness_timeout_seconds=telemetry_timeout_seconds,
        )
        report["requested"] = True
        report["commands"] = commands
        if report["gate_passed"]:
            break

    def send_delta() -> None:
        command = "botauto trace all 128 delta"
        sent_at = monotonic()
        process.stdin.write((command + "\n").encode())
        process.stdin.flush()
        command_counts["trace"] += 1
        transport_ledger.command_sent(
            [command], sent_at_monotonic=sent_at,
            scheduler_state=scheduler.state(),
        )

    def read_trace_response(
        response_deadline: float,
    ) -> tuple[dict[str, Any], float] | None:
        nonlocal trace_count
        while monotonic() < response_deadline:
            sleep(min(0.05, max(0.0, response_deadline - monotonic())))
            record_resource_sample()
            new_observations = log_cursor.read_new_observations()
            combat_log_delta_controller.observe_rows([
                observation.row for observation in new_observations
            ])
            for observation in new_observations:
                row = observation.row
                if row.get("action") == "botauto_diagnose":
                    diagnoses.append(row)
                elif row.get("action") == "botauto_trace":
                    trace_count += 1
                    observed_at = observation.response_complete_observed_at_monotonic
                    receipt_index = transport_ledger.observe(observation)
                    scheduler.observe_trace([row], observed_at=observed_at)
                    if receipt_index is not None:
                        transport_ledger.finalize_responses(
                            [receipt_index], scheduler.state(),
                        )
                    return row, observed_at
        return None

    drain_report = drain_pending(
        initial_trace, expected_status,
        deadline_monotonic=monotonic() + min(15.0, telemetry_timeout_seconds),
        send_delta=send_delta,
        read_trace_response=read_trace_response,
        monotonic=monotonic,
    )
    report["trace_drain"] = drain_report
    if drain_report["gate_passed"] is not True:
        report["gate_passed"] = False
        if "trace" not in report.setdefault("missing_channels", []):
            report["missing_channels"].append("trace")
        report.setdefault("rejections", []).extend(
            f"trace:{reason}" for reason in drain_report["rejections"]
        )
    report["response_wait_seconds"] = round(monotonic() - requested_at, 3)
    return report, diagnoses, trace_count
