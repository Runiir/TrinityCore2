"""Addressed calibration scheduling under one caller-owned worldserver."""
from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import time
from typing import Any, Callable

from tools.bot_ml.run_live_bot_validation import (
    CohortCommandExecutor, apply_calibration_only_acceptance,
    attach_phase8_role_calibration, combined_calibration_status,
    live_validation_report, parse_json_objects,
)


def write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


@dataclass
class Attempt:
    spec: str
    cohort: str
    output: Path
    executor: CohortCommandExecutor
    started: float
    identity: tuple = ()
    latest: dict = field(default_factory=dict)
    last_damage: int = 0
    last_damage_at: float = 0
    terminal: str | None = None
    stopped: bool = False


def actor_row(calibration: dict) -> dict:
    rows = ((calibration.get("previous_window") or {}).get("bots")
            if calibration.get("window_complete") else calibration.get("bots")) or []
    return next((row for row in rows if row.get("guid") == calibration.get("target_guid")), {})


def identity(calibration: dict) -> tuple:
    return tuple(calibration.get(key) for key in (
        "server_epoch", "cohort_id", "attempt_id", "target_guid",
        "calibration_phase_id", "profile_generation", "profile_content_hash",
    ))


def measurement_outcome(report: dict, *, terminal: str) -> dict:
    """Keep measured activity independent of reference and diagnostic admission."""
    full = report.get("combat_calibration") or {}
    capture = report.get("calibration_acceptance") or {}
    checks = (report.get("role_calibration_evaluation") or {}).get("checks") or {}
    exact = (full.get("scored_seconds") == 300 and
             full.get("scored_ended_at_ms", 0) - full.get("scored_started_at_ms", 0) == 300000)
    isolation = all(checks.get(key) is True for key in
                    ("isolated_single_target_fixture", "single_target_damage_isolated"))
    completed = bool(exact and terminal == "complete" and capture.get("transport_passed") and isolation)
    compatibility = ((report.get("role_calibration_record") or {})
                     .get("reference_condition_compatibility") or {})
    comparable = checks.get("reference_conditions_compatible") is True
    row = actor_row(full)
    healing = row.get("effective_healing")
    if healing is None:
        healing = (row.get("healer_metrics") or {}).get("effective_healing")
    return {
        "measurement_completed": completed,
        "measurement_status": "complete" if completed else "incomplete_or_invalid",
        "diagnostics_complete": capture.get("diagnostics_passed") is True,
        "reference_comparable": comparable,
        "comparison_status": "ready_for_review" if completed and comparable else
                             "blocked_by_reference_setup" if completed else "measurement_unavailable",
        "comparison_rejections": list(compatibility.get("reasons") or
                                      ([] if comparable else ["reference_conditions_compatible"])),
        "dps": float(row["damage"]) / 300 if completed and row.get("damage") is not None else None,
        "hps": float(healing) / 300 if completed and healing is not None else None,
        "performance_accepted": False,
        "training_eligible": False,
    }


def observe(attempt: Attempt, calibration: dict, epoch: int) -> None:
    if calibration.get("cohort_id") != attempt.cohort or calibration.get("server_epoch") != epoch:
        raise RuntimeError("calibration responder identity mismatch")
    if calibration.get("target_spec") != attempt.spec:
        raise RuntimeError("calibration spec mismatch")
    observed = identity(calibration)
    if attempt.identity and observed != attempt.identity:
        raise RuntimeError("calibration identity changed during attempt")
    if not all(observed):
        raise RuntimeError("incomplete calibration identity")
    isolation = calibration.get("calibration_isolation") or {}
    observed_at = int(isolation.get("observed_at_ms") or 0)
    previous_observed_at = int((attempt.latest.get("calibration_isolation") or {}).get("observed_at_ms") or 0)
    if calibration.get("scored_started_at_ms") and (
            isolation.get("phase_lease_held") is not True
            or isolation.get("phase_match") is not True
            or isolation.get("observed_bot_phase_id") != observed[4]
            or isolation.get("observed_target_phase_id") != observed[4]
            or isolation.get("own_target_visibility_observed") is not True
            or observed_at < int(calibration["scored_started_at_ms"])
            or observed_at < previous_observed_at):
        raise RuntimeError("scoring calibration lacks observed native phase isolation")
    attempt.identity = observed
    attempt.latest = calibration


def validate_pair(attempts: list[Attempt]) -> None:
    for index in (3, 4):  # Native actor leases and private phases must be disjoint.
        values = [a.identity[index] for a in attempts if a.identity]
        if len(values) != len(set(values)):
            raise RuntimeError("concurrent calibration actor or phase collision")
    targets = [(a.latest.get("fixture_target") or {}).get("runtime_guid") for a in attempts]
    known = [target for target in targets if target]
    if len(known) != len(set(known)):
        raise RuntimeError("concurrent calibration target collision")


def run_batch(*, execute: Callable, specs: list[str], output: Path, epoch: int,
              run_id: str, seed: int = 1, concurrency: int = 2,
              heartbeat: float = 5, timeout: float = 600,
              clock: Callable = time.monotonic, sleep: Callable = time.sleep,
              policy_path: Path) -> dict:
    if concurrency not in (1, 2) or not specs or len(specs) != len(set(specs)):
        raise ValueError("one or two concurrent unique specs required")
    if heartbeat <= 0 or timeout <= 300:
        raise ValueError("positive heartbeat and timeout above scoring duration required")
    active: list[Attempt] = []
    attempts: list[Attempt] = []
    pending = list(specs)
    witnesses: list[dict] = []
    results: list[dict] = []

    def recorded(spec: str, path: Path):
        def transport(command: str, seconds: int):
            started = clock()
            raw, code, expired = execute(command, seconds)
            with path.open("a") as stream:
                stream.write(json.dumps({"spec": spec, "command": command,
                    "observed_monotonic": clock(), "duration_seconds": clock() - started,
                    "returncode": code, "timed_out": expired, "output": raw}) + "\n")
            return raw, code, expired
        return transport

    def command(a: Attempt, text: str) -> str:
        raw, code, expired = a.executor.run(text, 60)
        if code or expired:
            raise RuntimeError("calibration command transport failed")
        return raw

    def calibration(a: Attempt, operation: str) -> tuple[dict, str]:
        raw = command(a, f".botauto calibrate {a.cohort} {operation}")
        row, transport = combined_calibration_status(parse_json_objects(raw))
        if not row or not (transport.get("direct") or transport.get("reassembled")):
            raise RuntimeError("calibration export incomplete")
        return row, raw

    def stop(a: Attempt) -> None:
        if a.stopped:
            return
        def bound(row: dict) -> bool:
            return (row.get("server_epoch") == epoch and row.get("cohort_id") == a.cohort
                    and (not a.identity or row.get("attempt_id") == a.identity[2]))
        for text, action in ((f".botauto calibrate {a.cohort} stop", "botauto_calibrate_stop"),
                             (f".botauto stop {a.cohort}", "botauto_stop")):
            raw = command(a, text)
            rows = [r for r in parse_json_objects(raw) if r.get("action") == action]
            if len(rows) != 1 or rows[0].get("ok") is not True or not bound(rows[0]):
                raise RuntimeError("addressed calibration cleanup failed")
        raw = command(a, f".botauto status {a.cohort}")
        status = next((r for r in parse_json_objects(raw) if r.get("action") == "botauto_status"), {})
        if not bound(status) or status.get("active") is not False or status.get("lease_count") != 0:
            raise RuntimeError("cohort remains active or leased after stop")
        write(a.output / "cleanup.json", status)
        a.stopped = True

    try:
        while pending or active:
            # Give the first scorer a head start. This lets a later peer prove
            # continuing native progress after the first addressed cleanup.
            can_start = not active or any(float(a.latest.get("scored_seconds") or 0) >= 20 for a in active)
            if pending and len(active) < concurrency and can_start:
                spec = pending.pop(0)
                folder = output / spec
                folder.mkdir(exist_ok=False)
                cohort = f"{run_id}-{len(attempts) + 1}"
                executor = CohortCommandExecutor(recorded(spec, folder / "commands.jsonl"), cohort, exclusive=False)
                a = Attempt(spec, cohort, folder, executor, clock(), last_damage_at=clock())
                attempts.append(a)
                active.append(a)
                for call in (executor.create, executor.start):
                    raw, code, expired = call()
                    if code or expired or not any(r.get("ok") is True for r in parse_json_objects(raw)):
                        raise RuntimeError("cohort admission failed")
                raw, code, expired = executor.calibration("start", mode="single_target_300", target_spec=spec, seed=seed)
                if code or expired:
                    raise RuntimeError("calibration startup transport failed")
                write(folder / "request.json", {"cohort_id": cohort, "spec": spec, "seed": seed,
                                               "mode": "single_target_300", "server_epoch": epoch})
            for a in list(active):
                progress, _ = calibration(a, "progress")
                if progress.get("ok") is not True or progress.get("failure_reason"):
                    a.latest = progress
                    a.terminal = "setup_failure"
                else:
                    observe(a, progress, epoch)
                    validate_pair(active)
                    damage = int(actor_row(progress).get("damage") or 0)
                    if damage != a.last_damage:
                        a.last_damage, a.last_damage_at = damage, clock()
                    if progress.get("window_complete") and progress.get("phase") == "complete":
                        a.terminal = "complete"
                    elif progress.get("scored_started_at_ms") and clock() - a.last_damage_at > 60:
                        a.terminal = "semantic_stall"
                    elif clock() - a.started > timeout:
                        a.terminal = "infrastructure_timeout"
                    for witness in witnesses:
                        if witness["cohort_id"] == a.cohort and not witness["proved"]:
                            witness["proved"] = (float(progress.get("scored_seconds") or 0) > witness["scored_seconds"]
                                                 and damage > witness["damage"])
                with (a.output / "progress.jsonl").open("a") as stream:
                    stream.write(json.dumps(progress, separators=(",", ":")) + "\n")
                if not a.terminal:
                    continue
                full, raw = calibration(a, "status")
                if full.get("detail_level") == "progress":
                    raise RuntimeError("final calibration export omitted details")
                if a.identity:
                    observe(a, full, epoch)
                report = live_validation_report(raw)
                report["requested_calibration"] = {"mode": "single_target_300", "target_spec": a.spec, "seed": seed}
                report["batch_terminal_reason"] = a.terminal
                apply_calibration_only_acceptance(report)
                capture_ok = report["calibration_acceptance"]["passed"]
                exact = (full.get("scored_seconds") == 300 and
                         full.get("scored_ended_at_ms", 0) - full.get("scored_started_at_ms", 0) == 300000)
                attach_phase8_role_calibration(report, policy_path=policy_path)
                checks = (report.get("role_calibration_evaluation") or {}).get("checks") or {}
                structural = ("reference_conditions_compatible", "isolated_single_target_fixture",
                              "single_target_damage_isolated")
                report["capture_rejections"] = [name for name in structural if checks.get(name) is not True]
                report["exact_window_capture_accepted"] = bool(capture_ok and exact and a.terminal == "complete"
                                                              and not report["capture_rejections"])
                report["performance_accepted"] = False
                report["training_eligible"] = False
                outcome = measurement_outcome(report, terminal=a.terminal)
                report["measurement_outcome"] = outcome
                write(a.output / "report.json", report)
                row = actor_row(full)
                result = {"spec": a.spec, "cohort_id": a.cohort, "identity": list(a.identity),
                          "terminal_reason": a.terminal, "capture_accepted": report["exact_window_capture_accepted"],
                          "scored_seconds": full.get("scored_seconds"), "damage": row.get("damage"),
                          **outcome}
                stop(a)
                active.remove(a)
                for peer in active:
                    # Freeze the witness baseline after cleanup. An older
                    # heartbeat cannot prove progress occurred after the stop.
                    after_stop, _ = calibration(peer, "progress")
                    observe(peer, after_stop, epoch)
                    validate_pair(active)
                    with (peer.output / "progress.jsonl").open("a") as stream:
                        stream.write(json.dumps(after_stop, separators=(",", ":")) + "\n")
                    if after_stop.get("scored_started_at_ms") and not after_stop.get("window_complete"):
                        witnesses.append({"stopped_cohort": a.cohort, "cohort_id": peer.cohort,
                                          "baseline_observed_after_cleanup": True,
                                          "scored_seconds": float(after_stop.get("scored_seconds") or 0),
                                          "damage": int(actor_row(after_stop).get("damage") or 0), "proved": False})
                results.append(result)
                write(output / "results.json", {"actors": results, "cleanup_witnesses": witnesses})
            if active:
                sleep(heartbeat)
    finally:
        for a in attempts:
            if not a.stopped:
                try:
                    stop(a)
                except Exception as exc:
                    write(a.output / "cleanup-error.json", {"error": str(exc)})
    captures = (len(results) == len(specs) and {r["spec"] for r in results} == set(specs)
                and all(r["capture_accepted"] for r in results))
    cleanup_proved = any(w["proved"] for w in witnesses)
    return {"actors": results, "cleanup_witnesses": witnesses,
            "all_measurements_completed": len(results) == len(specs) and all(
                r["measurement_completed"] for r in results),
            "all_references_comparable": len(results) == len(specs) and all(
                r["reference_comparable"] for r in results),
            "all_captures_accepted": captures,
            "concurrent_cleanup_proved": cleanup_proved,
            "batch_accepted": captures and (concurrency == 1 or len(specs) == 1 or cleanup_proved),
            "performance_accepted": False, "training_eligible": False}
