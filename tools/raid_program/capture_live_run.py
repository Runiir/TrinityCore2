from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import time
from typing import Any

from tools.raid_program.capture_checkpoint_controller import (
    chainwielder_checkpoint_monitor_commands,
    observe_chainwielder_checkpoint_arm_gate,
)
from tools.raid_program.capture_drudge_contract import accepted_drudge_contract
from tools.raid_program.capture_forced_evidence import (
    validate_forced_combat_log_bundle,
    validate_forced_evidence_bundle,
)
from tools.raid_program.capture_fixture_terminal import (
    bind_fixture_terminal_evidence,
    controller_fixture_terminal_observation,
)
from tools.raid_program.capture_progress import (
    observe_monotonic_semantic_progress,
    ready_for_native_readycheck,
    semantic_progress_signature,
)
from tools.raid_program.capture_run_outcome import process_resource_sample
from tools.raid_program.capture_runtime_acceptance import (
    accepted_foundation_status,
    accepted_native_recovery,
    native_readycheck_request_identity,
    terminal_preflight_failure_reason,
    terminal_runtime_failure_reason,
)
from tools.raid_program.capture_runtime_io import (
    bounded_native_shutdown,
    wait_for_prompt,
)
from tools.raid_program.capture_setup import CaptureSetup
from tools.raid_program.capture_telemetry_transport import (
    JsonLogCursor,
    TelemetryScheduler,
    TelemetryTransportLedger,
    collect_log_observations,
    observe_telemetry_freshness,
)
from tools.raid_program.capture_terminal_batch import (
    classify_terminal_failure_batch,
)
from tools.raid_program.capture_watchdog import observe_capture_watchdog
from tools.raid_program import trace_transport_smoke


@dataclass(frozen=True)
class CaptureRunResult:
    started_utc: str
    recovery_required: bool
    stable: list[dict[str, Any]]
    last_rejections: list[str]
    startup_error: str | None
    process_return_code: int | None
    telemetry_scheduler: TelemetryScheduler | None
    telemetry_transport_ledger: TelemetryTransportLedger
    telemetry_command_counts: dict[str, int]
    trace_transport_pressure_gate: dict[str, Any]
    operator_interrupt: bool
    shutdown_error: str | None
    stop_commands_sent: bool
    checkpoint_arm_command_sent: bool
    checkpoint_arm_gate: dict[str, Any]
    resource_samples: list[dict[str, Any]]
    resource_sampling_errors: list[str]
    resource_sampling_error_count: int
    resource_tick_rate: int | None
    forced_evidence_report: dict[str, Any]
    fixture_terminal: dict[str, Any]
    terminal_failure: dict[str, Any]
    semantic_stall: dict[str, Any]
    controller_watchdog: dict[str, Any]
    trace_transport_gate: dict[str, Any] | None
    telemetry_abort: dict[str, Any]
    log_bytes: bytes


def execute_capture_run(setup: CaptureSetup) -> CaptureRunResult:
    args = setup.args
    binary = setup.binary
    config = setup.config
    worktree = setup.worktree
    profile_name = setup.profile_name
    scenario_id = setup.scenario_id
    server_log_output = setup.server_log_output
    recurrence_admission = setup.recurrence_admission
    checkpoint_arm_command = setup.checkpoint_arm_command
    runtime_assets = setup.runtime_assets
    controller_route_hold_scheduler = setup.controller_route_hold_scheduler
    drudge_observed = setup.drudge_observed
    drudge_required = setup.drudge_required
    drudge_frozen_anchors = setup.drudge_frozen_anchors
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    recovery_required = (
        profile_name == "blackwing_descent_10n"
        and not args.trace_transport_smoke
    )
    stable: list[dict[str, Any]] = []
    last_rejections: list[str] = ["no_status_observed"]
    startup_error: str | None = None
    process: subprocess.Popen[bytes] | None = None
    telemetry_scheduler: TelemetryScheduler | None = None
    telemetry_transport_ledger = TelemetryTransportLedger()
    telemetry_command_counts = {
        "status": 0, "diagnose": 0, "trace": 0, "trace_pressure": 0,
        "combat_log": 0,
    }
    trace_transport_pressure_gate = trace_transport_smoke.pressure_receipt_report([])
    operator_interrupt = False
    shutdown_error: str | None = None
    stop_commands_sent = False
    checkpoint_arm_command_sent = False
    checkpoint_arm_gate: dict[str, Any] = {
        "schema": "chainwielder_checkpoint_pre_route_arm_gate_v1",
        "required": checkpoint_arm_command is not None,
        "required_stable_statuses": 2,
        "consecutive_stable_statuses": 0,
        "last_identity_sha256": None,
        "last_readiness": None,
        "pre_route_probe_batches": 0,
        "pre_route_probe_command_count": 0,
        "gate_open": False,
        "command_sent": False,
        "emission_count": 0,
        "emission": None,
    }
    resource_samples: list[dict[str, Any]] = []
    resource_sampling_errors: list[str] = []
    resource_sampling_error_count = 0
    resource_sample_sequence = 0
    try:
        resource_tick_rate = int(os.sysconf(os.sysconf_names["SC_CLK_TCK"]))
    except (AttributeError, KeyError, OSError, ValueError):
        resource_tick_rate = None
    forced_evidence_report: dict[str, Any] = {
        "requested": False,
        "gate_passed": False,
        "missing_channels": ["diagnosis", "trace"],
        "rejections": ["forced_bundle_not_requested"],
    }
    fixture_terminal: dict[str, Any] = {"detected": False}
    terminal_failure: dict[str, Any] = {"detected": False}
    semantic_stall: dict[str, Any] = {"detected": False}
    controller_watchdog: dict[str, Any] = {
        "detected": False,
        "classification": None,
        "failure_reason": None,
        "max_repeated_decisions": args.max_repeated_decision_count,
        "max_death_loops": args.max_death_loop_count,
        "repeated_decision_count": 0,
        "death_loop_count": 0,
        "rejections": ["controller_watchdog_not_started"],
    }
    trace_transport_gate: dict[str, Any] | None = None
    telemetry_abort: dict[str, Any] = {"detected": False}
    flush_forced_evidence_callback: Any = None

    def request_final_evidence(reason: str) -> dict[str, Any]:
        nonlocal operator_interrupt
        if forced_evidence_report.get("requested") is True:
            return forced_evidence_report
        if flush_forced_evidence_callback is None or process is None or process.poll() is not None:
            return {
                "requested": False,
                "gate_passed": False,
                "missing_channels": ["diagnosis", "trace"],
                "rejections": ["forced_bundle_process_unavailable"],
                "reason": reason,
            }
        try:
            report = flush_forced_evidence_callback()
            report["reason"] = reason
            return report
        except KeyboardInterrupt:
            operator_interrupt = True
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            return {
                "requested": True,
                "gate_passed": False,
                "missing_channels": ["diagnosis", "trace"],
                "rejections": ["forced_bundle_operator_interrupted"],
                "reason": reason,
            }
        except BaseException as error:
            return {
                "requested": True,
                "gate_passed": False,
                "missing_channels": ["diagnosis", "trace"],
                "rejections": [f"forced_bundle_error:{type(error).__name__}:{error}"],
                "reason": reason,
            }
    server_log_output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=".raid-phase1-worldserver-", suffix=".log.tmp", dir=server_log_output.parent, delete=False
    ) as log:
        log_path = Path(log.name)
        process = subprocess.Popen(
            [str(binary), "--config", str(config)], cwd=worktree, stdin=subprocess.PIPE,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )

        try:
            wait_for_prompt(process, log_path, args.startup_timeout_sec)
            assert process.stdin is not None
            log_cursor = JsonLogCursor(log_path)
            controller_hold_bootstrap_statuses: list[dict[str, Any]] = []
            # Bind the run to the explicitly selected frozen runtime profile.
            # The test worldserver configuration deliberately has AutoStart
            # disabled, so an explicit native operator command is required;
            # omitting it would only poll an inactive default cohort forever.
            if controller_route_hold_scheduler is not None:
                bootstrap_commands = controller_route_hold_scheduler.start()
                process.stdin.write(
                    ("\n".join(bootstrap_commands) + "\n").encode()
                )
                process.stdin.flush()
                bootstrap_deadline = time.monotonic() + args.telemetry_timeout_sec
                while (
                    controller_route_hold_scheduler.phase
                    != "awaiting_terminal"
                    and not controller_route_hold_scheduler.failed
                    and time.monotonic() < bootstrap_deadline
                ):
                    if process.poll() is not None:
                        controller_route_hold_scheduler._fail(
                            "controller_route_hold_worldserver_exited_during_bootstrap"
                        )
                        break
                    observations = collect_log_observations(
                        log_cursor, duration_seconds=0.25,
                    )
                    for observation in observations:
                        row = observation.row
                        if row.get("action") == "botauto_status":
                            controller_hold_bootstrap_statuses.append(row)
                        next_commands = controller_route_hold_scheduler.observe(row)
                        if next_commands:
                            process.stdin.write(
                                ("\n".join(next_commands) + "\n").encode()
                            )
                            process.stdin.flush()
                        if controller_route_hold_scheduler.failed:
                            break
                if controller_route_hold_scheduler.phase != "awaiting_terminal":
                    controller_route_hold_scheduler.finish()
                    raise RuntimeError(
                        "controller route hold bootstrap rejected: "
                        + str(controller_route_hold_scheduler.failure_reason)
                    )
                checkpoint_arm_command_sent = (
                    controller_route_hold_scheduler.command_counts["arm"] == 1
                )
            elif profile_name == "blackwing_descent_10n":
                process.stdin.write(b"botauto start blackwing_descent_10n\n")
                process.stdin.flush()
            else:
                process.stdin.write((f"botauto start {profile_name}\n").encode())
                process.stdin.flush()
            if controller_route_hold_scheduler is None:
                time.sleep(1.0)
            if args.trace_transport_smoke:
                # Produce one bounded native decision-history backlog before
                # the unchanged production scheduler begins polling, then use
                # the attempt-latched telemetry-only writer exactly once. The
                # first normal delta must expose the real ring discontinuity.
                time.sleep(trace_transport_smoke.PRESSURE_WARMUP_SECONDS)
                process.stdin.write(
                    (trace_transport_smoke.PRESSURE_COMMAND + "\n").encode()
                )
                process.stdin.flush()
                telemetry_command_counts["trace_pressure"] += 1
                pressure_observations = collect_log_observations(
                    log_cursor, duration_seconds=1.0,
                )
                trace_transport_pressure_gate = (
                    trace_transport_smoke.pressure_receipt_report(
                        [observation.row for observation in pressure_observations]
                    )
                )
                if trace_transport_pressure_gate["gate_passed"] is not True:
                    raise RuntimeError(
                        "trace transport pressure rejected: "
                        + ",".join(trace_transport_pressure_gate["rejections"])
                    )
            # Canonical raid validation is terminal-gate driven. Raid and boss
            # duration alone must never end an otherwise healthy run. A
            # positive limit remains available only for explicitly bounded
            # diagnostics and tests; zero is deliberately uncapped.
            deadline = time.monotonic() + args.observe_sec if args.observe_sec else None
            telemetry_scheduler = TelemetryScheduler(
                status_interval_sec=args.status_interval_sec,
                diagnose_interval_sec=args.diagnose_interval_sec,
                trace_interval_sec=args.trace_interval_sec,
            )
            monitor_statuses: list[dict[str, Any]] = list(
                controller_hold_bootstrap_statuses
            )
            for bootstrap_status in monitor_statuses:
                telemetry_scheduler.observe_status(bootstrap_status)
            diagnosis_count = 0
            trace_count = 0
            latest_diagnosis: dict[str, Any] | None = None
            recovery_accepted = not recovery_required
            drudge_accepted = not drudge_required
            readycheck_requested_for: tuple[Any, ...] | None = None
            semantic_progress_state: dict[str, Any] = {}
            last_semantic_progress_at = time.monotonic()
            unchanged_semantic_samples = 0
            semantic_stall: dict[str, Any] = {"detected": False}
            controller_watchdog_state: dict[str, Any] = {}
            controller_watchdog: dict[str, Any] = {
                "detected": False,
                "classification": None,
                "failure_reason": None,
                "max_repeated_decisions": args.max_repeated_decision_count,
                "max_death_loops": args.max_death_loop_count,
                "repeated_decision_count": 0,
                "death_loop_count": 0,
                "rejections": [],
            }
            monitor_started_at = time.monotonic()
            telemetry_freshness: dict[str, dict[str, float | int]] = {}
            telemetry_abort: dict[str, Any] = {"detected": False}
            trace_transport_gate = trace_transport_smoke.evaluate([])

            next_resource_sample_at = monitor_started_at

            def record_process_resource_sample(*, force: bool = False) -> None:
                nonlocal next_resource_sample_at, resource_sample_sequence
                nonlocal resource_sampling_error_count
                now = time.monotonic()
                if not force and now < next_resource_sample_at:
                    return
                if process.poll() is not None:
                    return
                try:
                    resource_samples.append(process_resource_sample(
                        process.pid,
                        sample_sequence=resource_sample_sequence,
                        scenario_id=scenario_id,
                        runtime_profile=profile_name,
                        status=monitor_statuses[-1] if monitor_statuses else None,
                    ))
                    resource_sample_sequence += 1
                except (OSError, IndexError, KeyError, TypeError, ValueError) as error:
                    resource_sampling_error_count += 1
                    # Preserve a bounded diagnostic prefix; a persistent
                    # /proc race must not make a long-run report grow without
                    # limit. The summary retains the exact total count.
                    if len(resource_sampling_errors) < 8:
                        resource_sampling_errors.append(f"{type(error).__name__}:{error}")
                finally:
                    next_resource_sample_at = now + args.resource_sample_interval_sec

            # Start the resource series as soon as the worldserver is ready;
            # later rows gain cohort/attempt identity once status is observed.
            record_process_resource_sample(force=True)

            def flush_forced_evidence() -> dict[str, Any]:
                """Retain and independently validate a final evidence bundle.

                Console commands are asynchronous.  Wait for the exact
                identity-bound responses to this request, bounded by the
                telemetry freshness budget, rather than treating a fixed
                sleep as proof that the commands ran.
                """
                nonlocal diagnosis_count, trace_count, latest_diagnosis
                telemetry_scheduler.force_diagnosis(include_trace=True)
                request_started = time.monotonic()
                commands = telemetry_scheduler.commands_due(request_started)
                trace_command = (
                    "botauto trace all 128"
                    if "botauto trace all 128" in commands
                    else "botauto trace all 128 delta"
                )
                required_commands = {
                    "botauto diagnose all", trace_command,
                }
                if not required_commands.issubset(commands):
                    return {
                        "requested": False,
                        "gate_passed": False,
                        "missing_channels": [
                            channel for channel in ("diagnosis", "trace")
                            if {
                                "diagnosis": "botauto diagnose all",
                                "trace": trace_command,
                            }[channel] not in commands
                        ],
                        "rejections": ["forced_request_commands_not_scheduled"],
                        "commands": commands,
                    }
                for command in commands:
                    if command == "botauto status":
                        telemetry_command_counts["status"] += 1
                    elif command == "botauto diagnose all":
                        telemetry_command_counts["diagnose"] += 1
                    elif command in {
                        "botauto trace all 128",
                        "botauto trace all 128 delta",
                    }:
                        telemetry_command_counts["trace"] += 1
                process.stdin.write(("\n".join(commands) + "\n").encode())
                process.stdin.flush()
                observations: list[tuple[dict[str, Any], float]] = []
                expected_status = monitor_statuses[-1] if monitor_statuses else None
                deadline = request_started + args.telemetry_timeout_sec
                report: dict[str, Any] = {
                    "requested": True,
                    "gate_passed": False,
                    "missing_channels": ["diagnosis", "trace"],
                    "rejections": ["forced_responses_not_observed"],
                    "commands": commands,
                }
                while time.monotonic() < deadline:
                    time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
                    record_process_resource_sample()
                    observed_at = time.monotonic()
                    for row in log_cursor.read_new_rows():
                        action = row.get("action")
                        if action == "botauto_diagnose":
                            diagnosis_count += 1
                            latest_diagnosis = row
                            observations.append((row, observed_at))
                        elif action == "botauto_trace":
                            trace_count += 1
                            observations.append((row, observed_at))
                    report = validate_forced_evidence_bundle(
                        observations,
                        expected_status,
                        requested_at_monotonic=request_started,
                        freshness_timeout_seconds=args.telemetry_timeout_sec,
                    )
                    report["requested"] = True
                    report["commands"] = commands
                    if report["gate_passed"]:
                        break
                combat_log_started = time.monotonic()
                process.stdin.write(b"botauto combatlog\n")
                process.stdin.flush()
                telemetry_command_counts["combat_log"] += 1
                combat_log_rows: list[dict[str, Any]] = []
                combat_log_deadline = combat_log_started + min(
                    15.0, float(args.telemetry_timeout_sec)
                )
                combat_log_report = validate_forced_combat_log_bundle(
                    combat_log_rows,
                    expected_status.get("cohort_id")
                    if isinstance(expected_status, dict) else None,
                )
                while time.monotonic() < combat_log_deadline:
                    time.sleep(min(
                        0.25,
                        max(0.0, combat_log_deadline - time.monotonic()),
                    ))
                    observed_at = time.monotonic()
                    for row in log_cursor.read_new_rows():
                        action = row.get("action")
                        if action in {
                            "botauto_combatlog_chunk",
                            "botauto_combatlog_complete",
                        }:
                            combat_log_rows.append(row)
                        elif action == "botauto_diagnose":
                            diagnosis_count += 1
                            latest_diagnosis = row
                            observations.append((row, observed_at))
                        elif action == "botauto_trace":
                            trace_count += 1
                            observations.append((row, observed_at))
                    combat_log_report = validate_forced_combat_log_bundle(
                        combat_log_rows,
                        expected_status.get("cohort_id")
                        if isinstance(expected_status, dict) else None,
                    )
                    if combat_log_report["gate_passed"]:
                        break
                report["combat_log"] = combat_log_report
                if combat_log_report["gate_passed"] is not True:
                    report["gate_passed"] = False
                    report.setdefault("missing_channels", []).append(
                        "combat_log"
                    )
                    report.setdefault("rejections", []).extend(
                        f"combat_log:{reason}"
                        for reason in combat_log_report["rejections"]
                    )
                report["response_wait_seconds"] = round(time.monotonic() - request_started, 3)
                return report

            flush_forced_evidence_callback = flush_forced_evidence

            while (deadline is None or time.monotonic() < deadline) and not (
                trace_transport_gate.get("terminal") is True
                if args.trace_transport_smoke
                else (
                    len(stable) >= args.required_stable_statuses
                    and recovery_accepted and drudge_accepted
                    and (
                        controller_route_hold_scheduler is None
                        or controller_route_hold_scheduler.complete
                    )
                )
            ):
                if process.poll() is not None:
                    break
                record_process_resource_sample()
                due_commands = telemetry_scheduler.commands_due(time.monotonic())
                if due_commands:
                    if controller_route_hold_scheduler is None:
                        due_commands = chainwielder_checkpoint_monitor_commands(
                            due_commands,
                            checkpoint_arm_command=checkpoint_arm_command,
                            checkpoint_arm_gate=checkpoint_arm_gate,
                        )
                    # A diagnosis is a point-in-time snapshot, not durable
                    # state. Only the diagnosis observed in this poll may
                    # drive the watchdog. Retain latest_diagnosis separately
                    # for the final report and semantic summaries.
                    fresh_diagnosis: dict[str, Any] | None = None
                    # Diagnosis carries the exact current decision per bot;
                    # trace is an incremental export so a long raid does not
                    # replay each bot's cumulative 128-entry history every
                    # five seconds. The server cursor retains every edge
                    # unless its bounded in-memory history was overrun.
                    for command in due_commands:
                        if command == "botauto status":
                            telemetry_command_counts["status"] += 1
                        elif command == "botauto diagnose all":
                            telemetry_command_counts["diagnose"] += 1
                        elif command in {
                            "botauto trace all 128",
                            "botauto trace all 128 delta",
                        }:
                            telemetry_command_counts["trace"] += 1
                    process.stdin.write(("\n".join(due_commands) + "\n").encode())
                    process.stdin.flush()
                    command_sent_at = time.monotonic()
                    telemetry_transport_ledger.command_sent(
                        due_commands,
                        sent_at_monotonic=command_sent_at,
                        scheduler_state=telemetry_scheduler.state(),
                    )
                    observations = collect_log_observations(
                        log_cursor, duration_seconds=1.0,
                    )
                    new_statuses: list[dict[str, Any]] = []
                    new_trace_rows: list[dict[str, Any]] = []
                    trace_receipt_indexes: list[int] = []
                    for observation in observations:
                        row = observation.row
                        if controller_route_hold_scheduler is not None:
                            hold_commands = controller_route_hold_scheduler.observe(
                                row
                            )
                            if hold_commands:
                                process.stdin.write(
                                    ("\n".join(hold_commands) + "\n").encode()
                                )
                                process.stdin.flush()
                            checkpoint_arm_command_sent = (
                                controller_route_hold_scheduler.command_counts[
                                    "arm"
                                ] == 1
                            )
                            if controller_route_hold_scheduler.failed:
                                raise RuntimeError(
                                    "controller route hold protocol rejected: "
                                    + str(
                                        controller_route_hold_scheduler
                                        .failure_reason
                                    )
                                )
                        action = row.get("action")
                        if action == "botauto_status":
                            new_statuses.append(row)
                        elif action == "botauto_diagnose":
                            diagnosis_count += 1
                            latest_diagnosis = row
                            fresh_diagnosis = row
                        elif action == "botauto_trace":
                            trace_count += 1
                            new_trace_rows.append(row)
                            receipt_index = telemetry_transport_ledger.observe(
                                observation
                            )
                            if receipt_index is not None:
                                trace_receipt_indexes.append(receipt_index)
                    telemetry_scheduler.observe_trace(
                        new_trace_rows, observed_at=time.monotonic(),
                    )
                    telemetry_transport_ledger.finalize_responses(
                        trace_receipt_indexes, telemetry_scheduler.state(),
                    )
                    if args.trace_transport_smoke:
                        trace_transport_gate = trace_transport_smoke.evaluate(
                            telemetry_transport_ledger.receipts()
                        )
                    monitor_statuses.extend(new_statuses)
                    for status in new_statuses:
                        telemetry_scheduler.observe_status(status)
                    if not args.trace_transport_smoke:
                        batch_failure = classify_terminal_failure_batch(
                            new_statuses,
                            profile_name=profile_name,
                            elapsed_seconds=time.monotonic() - monitor_started_at,
                            request_final_evidence=request_final_evidence,
                            preflight_classifier=terminal_preflight_failure_reason,
                            runtime_classifier=terminal_runtime_failure_reason,
                        )
                        if batch_failure is not None:
                            terminal_failure, telemetry_abort = batch_failure
                            break
                    fixture_terminal = controller_fixture_terminal_observation(
                        controller_route_hold_scheduler,
                        elapsed_seconds=time.monotonic() - monitor_started_at,
                    )
                    if fixture_terminal.get("detected") is True:
                        forced_evidence_report = request_final_evidence(
                            "controller_route_hold_fixture_terminal"
                        )
                        fixture_terminal, telemetry_abort = (
                            bind_fixture_terminal_evidence(
                                fixture_terminal,
                                forced_evidence_report,
                                elapsed_seconds=(
                                    time.monotonic() - monitor_started_at
                                ),
                            )
                        )
                        break
                    for status in new_statuses:
                        if args.trace_transport_smoke:
                            continue
                        if (
                            checkpoint_arm_command is not None
                            and controller_route_hold_scheduler is None
                        ):
                            observe_chainwielder_checkpoint_arm_gate(
                                checkpoint_arm_gate,
                                status,
                                process=process,
                                recurrence_admission=recurrence_admission,
                                checkpoint_arm_command=checkpoint_arm_command,
                                actor_guid=args.chainwielder_checkpoint_actor_guid,
                                profile_name=profile_name,
                                scenario_id=scenario_id,
                                expected_route_manifest_sha256=runtime_assets.get(
                                    "route_sha256"
                                ),
                            )
                            checkpoint_arm_command_sent = (
                                checkpoint_arm_gate["command_sent"] is True
                            )
                        accepted, rejections = accepted_foundation_status(
                            status,
                            profile_name=profile_name,
                            route_partition=runtime_assets.get("route_partition"),
                        )
                        last_rejections = rejections
                        if accepted:
                            stable.append(status)
                        else:
                            stable.clear()
                    if monitor_statuses and not args.trace_transport_smoke:
                        controller_watchdog = observe_capture_watchdog(
                            controller_watchdog_state,
                            monitor_statuses[-1],
                            fresh_diagnosis,
                            new_trace_rows,
                            profile_name=profile_name,
                            max_repeated_decisions=args.max_repeated_decision_count,
                            max_death_loops=args.max_death_loop_count,
                        )
                        if controller_watchdog.get("detected") is True:
                            forced_evidence_report = request_final_evidence(
                                "controller_watchdog_failure"
                            )
                            terminal_failure = {
                                "detected": True,
                                "classification": "gameplay_failure",
                                "failure_reason": controller_watchdog.get(
                                    "failure_reason"
                                ),
                                "terminal_status": monitor_statuses[-1],
                                "watchdog": controller_watchdog,
                                "route": monitor_statuses[-1].get("validation_route"),
                                "raid_runtime": monitor_statuses[-1].get("raid_runtime"),
                                "elapsed_seconds": round(
                                    time.monotonic() - monitor_started_at, 3
                                ),
                                "final_forced_evidence": forced_evidence_report.get(
                                    "gate_passed"
                                ) is True,
                                "final_forced_evidence_report": forced_evidence_report,
                            }
                            if forced_evidence_report.get("gate_passed") is not True:
                                telemetry_abort = {
                                    "detected": True,
                                    "classification": "infrastructure_abort",
                                    "reason": "terminal_failure_forced_evidence_incomplete",
                                    "missing_channels": forced_evidence_report.get(
                                        "missing_channels", []
                                    ),
                                    "rejections": forced_evidence_report.get(
                                        "rejections", []
                                    ),
                                    "elapsed_seconds": round(
                                        time.monotonic() - monitor_started_at, 3
                                    ),
                                }
                            break
                    telemetry_now = time.monotonic()
                    stale_channels = observe_telemetry_freshness(
                        telemetry_freshness,
                        {
                            "status": len(monitor_statuses),
                            "diagnosis": diagnosis_count,
                            "trace": trace_count,
                        },
                        telemetry_now,
                        args.telemetry_timeout_sec,
                    )
                    if stale_channels:
                        forced_evidence_report = request_final_evidence(
                            "telemetry_channel_stale"
                        )
                        telemetry_abort = {
                            "detected": True,
                            "classification": "infrastructure_abort",
                            "reason": "telemetry_channel_stale",
                            "stale_channels": stale_channels,
                            "timeout_seconds": args.telemetry_timeout_sec,
                            "elapsed_seconds": round(telemetry_now - monitor_started_at, 3),
                            "channel_state": telemetry_freshness,
                        }
                        break
                    if monitor_statuses and not args.trace_transport_smoke:
                        signature = semantic_progress_signature(
                            monitor_statuses[-1], latest_diagnosis,
                        )
                        if observe_monotonic_semantic_progress(
                            semantic_progress_state,
                            monitor_statuses[-1], latest_diagnosis,
                        ):
                            last_semantic_progress_at = time.monotonic()
                            unchanged_semantic_samples = 1
                        else:
                            unchanged_semantic_samples += 1
                        stalled_for = time.monotonic() - last_semantic_progress_at
                        if (unchanged_semantic_samples >= args.semantic_stall_min_samples
                                and stalled_for >= args.semantic_stall_sec):
                            forced_evidence_report = flush_forced_evidence()
                            semantic_stall = {
                                "detected": True,
                                "classification": "gameplay_failure",
                                "failure_reason": "semantic_stall",
                                "terminal_status": monitor_statuses[-1],
                                "stalled_for_seconds": round(stalled_for, 3),
                                "unchanged_samples": unchanged_semantic_samples,
                                "semantic_signature": signature,
                                "monotonic_progress_state": semantic_progress_state,
                                "route": monitor_statuses[-1].get("validation_route"),
                                "raid_runtime": monitor_statuses[-1].get("raid_runtime"),
                                "diagnosis_rows": diagnosis_count,
                                "trace_rows": trace_count,
                                "final_forced_evidence": forced_evidence_report.get("gate_passed") is True,
                                "final_forced_evidence_report": forced_evidence_report,
                            }
                            if forced_evidence_report.get("gate_passed") is not True:
                                telemetry_abort = {
                                    "detected": True,
                                    "classification": "infrastructure_abort",
                                    "reason": "final_forced_evidence_incomplete",
                                    "missing_channels": forced_evidence_report.get("missing_channels", []),
                                    "rejections": forced_evidence_report.get("rejections", []),
                                    "elapsed_seconds": round(time.monotonic() - monitor_started_at, 3),
                                }
                            break
                    if recovery_required:
                        recovery_accepted, _ = accepted_native_recovery(
                            monitor_statuses,
                            profile_name=profile_name,
                        )
                    if drudge_observed:
                        drudge_accepted, _ = accepted_drudge_contract(
                            monitor_statuses, frozen_anchors=drudge_frozen_anchors,
                        )
                    if monitor_statuses and not args.trace_transport_smoke:
                        runtime = monitor_statuses[-1].get("raid_runtime") or {}
                        status = monitor_statuses[-1]
                        request_identity = native_readycheck_request_identity(status)
                        ready_for_native_check = ready_for_native_readycheck(status)
                        if ready_for_native_check and readycheck_requested_for != request_identity:
                            # This invokes only the native Group ready-check packet path.
                            # It cannot alter encounter, death, movement, or resurrection state.
                            process.stdin.write(b"botauto readycheck\n")
                            process.stdin.flush()
                            readycheck_requested_for = request_identity
                time.sleep(0.25)

            if (
                controller_route_hold_scheduler is not None
                and not controller_route_hold_scheduler.complete
            ):
                controller_route_hold_scheduler.finish()
                raise RuntimeError(
                    "controller route hold protocol incomplete: "
                    + str(controller_route_hold_scheduler.failure_reason)
                )

            # Capture one last live process sample before native shutdown so
            # the final CPU/RSS interval includes the terminal polling work.
            record_process_resource_sample(force=True)
            if (
                not args.trace_transport_smoke
                and forced_evidence_report.get("requested") is not True
            ):
                forced_evidence_report = request_final_evidence(
                    "terminal_gate_or_process_exit"
                )
            shutdown = bounded_native_shutdown(process, 60.0)
            stop_commands_sent = bool(shutdown["commands_sent"])
            shutdown_error = shutdown["error"]
            if shutdown["operator_interrupted"]:
                operator_interrupt = True
                startup_error = "KeyboardInterrupt:operator_interrupt"
                signal.signal(signal.SIGINT, signal.SIG_IGN)
        except KeyboardInterrupt:
            # Do not let an operator abort become a Python traceback.  Keep
            # the already captured bytes, issue the native cleanup sequence,
            # and let the immutable report classify this as an infrastructure
            # abort with an explicit operator reason.
            operator_interrupt = True
            startup_error = "KeyboardInterrupt:operator_interrupt"
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            forced_evidence_report = request_final_evidence("operator_interrupt")
            shutdown = bounded_native_shutdown(process, 20.0)
            stop_commands_sent = bool(shutdown["commands_sent"])
            shutdown_error = shutdown["error"]
        except Exception as error:  # captured as infrastructure evidence below
            startup_error = f"{type(error).__name__}:{error}"
            forced_evidence_report = request_final_evidence("capture_exception")
            shutdown = bounded_native_shutdown(process, 20.0)
            stop_commands_sent = bool(shutdown["commands_sent"])
            shutdown_error = shutdown["error"]
        finally:
            # Once capture teardown begins, a further SIGINT must not tear
            # through raw-log normalization or immutable report publication.
            # Record the request without raising, finish bounded cleanup, and
            # classify the run as an operator infrastructure abort below.
            def defer_post_capture_interrupt(_signum: int, _frame: Any) -> None:
                nonlocal operator_interrupt, startup_error
                operator_interrupt = True
                startup_error = "KeyboardInterrupt:operator_interrupt"

            signal.signal(signal.SIGINT, defer_post_capture_interrupt)
            if process is not None and process.poll() is None:
                try:
                    os.killpg(process.pid, 15)
                    process.wait(timeout=10)
                except (subprocess.TimeoutExpired, KeyboardInterrupt):
                    try:
                        os.killpg(process.pid, 9)
                        process.wait(timeout=10)
                    except (OSError, subprocess.TimeoutExpired, KeyboardInterrupt):
                        pass
                except OSError:
                    pass
        # Move the captured file into its caller-selected immutable location;
        # do not delete the raw worldserver log after capture.
        os.replace(log_path, server_log_output)
        log_bytes = server_log_output.read_bytes()

    process_return_code = process.returncode if process is not None else None
    return CaptureRunResult(
        started_utc=started_utc,
        recovery_required=recovery_required,
        stable=stable,
        last_rejections=last_rejections,
        startup_error=startup_error,
        process_return_code=process_return_code,
        telemetry_scheduler=telemetry_scheduler,
        telemetry_transport_ledger=telemetry_transport_ledger,
        telemetry_command_counts=telemetry_command_counts,
        trace_transport_pressure_gate=trace_transport_pressure_gate,
        operator_interrupt=operator_interrupt,
        shutdown_error=shutdown_error,
        stop_commands_sent=stop_commands_sent,
        checkpoint_arm_command_sent=checkpoint_arm_command_sent,
        checkpoint_arm_gate=checkpoint_arm_gate,
        resource_samples=resource_samples,
        resource_sampling_errors=resource_sampling_errors,
        resource_sampling_error_count=resource_sampling_error_count,
        resource_tick_rate=resource_tick_rate,
        forced_evidence_report=forced_evidence_report,
        fixture_terminal=fixture_terminal,
        terminal_failure=terminal_failure,
        semantic_stall=semantic_stall,
        controller_watchdog=controller_watchdog,
        trace_transport_gate=trace_transport_gate,
        telemetry_abort=telemetry_abort,
        log_bytes=log_bytes,
    )
