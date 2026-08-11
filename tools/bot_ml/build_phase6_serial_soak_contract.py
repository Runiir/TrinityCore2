"""Build the Phase 6 long-lived serial validation orchestration contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from .batch_evidence_lifecycle import publish_batch
from .common import write_json
from .live_validation_session import canonical_sha256, sha256_file
from .run_live_bot_validation import compact_published_report


REPO_ROOT = Path(__file__).resolve().parents[2]
RUNNER = REPO_ROOT / "tools/bot_ml/run_live_bot_validation.py"


def _static_contract() -> dict[str, Any]:
    source = RUNNER.read_text(encoding="utf-8")
    session_runner = source[
        source.index("def run_reusable_validation_session("):
        source.index("\ndef main() -> int:")
    ]
    checks = {
        "server_owner_explicit": "class ReusableValidationServerOwner" in source,
        "serial_scheduler_explicit": "class SerialValidationScheduler" in source,
        "cohort_executor_explicit": "class CohortCommandExecutor" in source,
        "attempt_watchdog_explicit": "class CohortAttemptWatchdog" in source,
        "immutable_capture_writer_explicit": "class ImmutableCaptureWriter" in source,
        "acceptance_recomputer_explicit": "class AcceptanceRecomputer" in source,
        "serialized_dvc_publisher_explicit": "class SerializedDvcPublisher" in source,
        "watchdog_uses_cohort_executor": (
            "run_transport_completion_watchdog(\n                executor.run" in session_runner
        ),
        "addressed_status_polling": (
            "status_command=executor.status_command" in session_runner
        ),
        "transport_process_identity_verified": (
            'payload.get("server_process_id")' in source
            and 'self.lifecycle["server_process_identity_verified"]' in source
        ),
        "global_lifecycle_count_recorded": (
            'lifecycle["global_lifecycle_command_count"]' in session_runner
        ),
        "cleanup_checks_leases_and_party": all(
            marker in session_runner
            for marker in (
                'int(inactive_payload.get("lease_count") or 0) == 0',
                'int(cohort_row.get("party_bot_count") or 0) == 0',
            )
        ),
        "provisioning_scoped_to_epoch": "owner.provision_once(" in session_runner,
        "atomic_db_reload_owned_by_server": "owner.reload_rotation_profiles()" in session_runner,
        "capture_recomputes_before_publication": (
            source.index("AcceptanceRecomputer().recompute(")
            < source.index("ImmutableCaptureWriter(REPO_ROOT).capture(")
            < source.index("SerializedDvcPublisher(")
        ),
        "targeted_eviction_default": "evict_after_verify=not args.retain_published_batch" in source,
        "published_payloads_compacted": "compact_published_report(report)" in source,
    }
    return {"checks": checks, "passed": all(checks.values())}


def _recover_closed_attempt(attempt_root: Path) -> bool:
    receipt_path = attempt_root / "batch/retained/publication_receipt.json"
    session_path = attempt_root / "session.json"
    report_path = attempt_root / "report.json"
    if receipt_path.is_file() and report_path.is_file():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        if session_path.is_file():
            report["session"] = json.loads(session_path.read_text(encoding="utf-8"))
        if report.get("published_raw_payloads_retained_locally") is not False:
            report["batch_publication"] = json.loads(
                receipt_path.read_text(encoding="utf-8")
            )
        write_json(report_path, compact_published_report(report))
        for name in (
            "combat_analysis.json",
            "combat_log.json",
            "heartbeat_events.jsonl",
            "latest.json",
            "worldserver_output.log",
        ):
            (attempt_root / name).unlink(missing_ok=True)
        return True
    batch_root = attempt_root / "batch"
    if not session_path.is_file() or not report_path.is_file():
        return False
    session = json.loads(session_path.read_text(encoding="utf-8"))
    cleanup = session.get("cleanup") or {}
    clean = (
        bool(session.get("inactive_after_attempt"))
        and int(cleanup.get("active_bots") or 0) == 0
        and int(cleanup.get("lease_count") or 0) == 0
        and int(cleanup.get("party_bot_count") or 0) == 0
        and (batch_root / "raw").is_dir()
        and (batch_root / "compact").is_dir()
    )
    if not clean:
        return False
    receipt = publish_batch(REPO_ROOT, batch_root, evict_after_verify=True)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["session"] = session
    report["batch_capture"] = json.loads(
        (batch_root / "retained/final_manifest.json").read_text(encoding="utf-8")
    )
    report["batch_publication"] = receipt
    write_json(report_path, compact_published_report(report))
    for name in (
        "combat_analysis.json",
        "combat_log.json",
        "heartbeat_events.jsonl",
        "latest.json",
        "worldserver_output.log",
    ):
        (attempt_root / name).unlink(missing_ok=True)
    return True


def _run_attempt(
    attempt_root: Path,
    *,
    cohort_id: str,
    attempt_index: int,
    profile: str,
    scenario_id: str,
    environment: str,
    timeout_sec: int,
    no_progress_window_sec: int,
    heartbeat_sec: int,
) -> None:
    command = [
        sys.executable,
        "-m",
        "tools.bot_ml.run_live_bot_validation",
        "--transport",
        "session",
        "--output-dir",
        str(attempt_root),
        "--session-profile",
        profile,
        "--cohort-id",
        cohort_id,
        "--session-attempt-index",
        str(attempt_index),
        "--session-environment",
        environment,
        "--validation-scenario-id",
        scenario_id,
        "--timeout-sec",
        str(timeout_sec),
        "--observe-sec",
        str(heartbeat_sec),
        "--heartbeat-sec",
        str(heartbeat_sec),
        "--no-progress-window-sec",
        str(no_progress_window_sec),
        "--max-repeated-decision-count",
        "100000",
        "--max-death-loop-count",
        "100000",
        "--publish-batch",
    ]
    completed = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=os.environ.copy(),
        capture_output=True,
        text=True,
        check=False,
        timeout=timeout_sec + 360,
    )
    if completed.returncode not in {0, 1}:
        detail = (completed.stderr or completed.stdout)[-4000:]
        raise RuntimeError(
            f"serial soak attempt {attempt_index} failed with "
            f"return code {completed.returncode}: {detail}"
        )


def _attempt_summary(attempt_root: Path) -> dict[str, Any]:
    session_path = attempt_root / "session.json"
    report_path = attempt_root / "report.json"
    receipt_path = attempt_root / "batch/retained/publication_receipt.json"
    for path in (session_path, report_path, receipt_path):
        if not path.is_file():
            raise RuntimeError(f"missing closed-attempt artifact: {path}")
    session = json.loads(session_path.read_text(encoding="utf-8"))
    report = json.loads(report_path.read_text(encoding="utf-8"))
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    commands = [str(command) for command in session.get("commands") or []]
    cohort_id = str(session.get("cohort_id") or "")
    cleanup = session.get("cleanup") or {}
    raw_dir = attempt_root / "batch/raw"
    compact_dir = attempt_root / "batch/compact"
    pointers = receipt.get("pointers") or []
    checks = {
        "scheduler_closed": [
            event.get("action") for event in session.get("scheduler_events") or []
        ] == ["admit", "close"],
        "same_attempt_identity": (
            int(session.get("attempt_index") or 0)
            == int((report.get("session") or {}).get("attempt_index") or 0)
        ),
        "cohort_in_every_runtime_command": bool(cohort_id) and all(
            not command.startswith(".botauto ")
            or (
                len(command.split()) >= 3
                and command.split()[2] == cohort_id
            )
            for command in commands
        ),
        "no_global_lifecycle_command": (
            int(session.get("global_lifecycle_command_count") or 0) == 0
            and not any(
                command in {".botauto start", ".botauto stop", ".botauto status"}
                for command in commands
            )
        ),
        "transport_process_identity_verified": (
            bool(session.get("server_process_identity_verified"))
            and int(session.get("server_process_id") or 0)
            == int(session.get("server_pid") or 0)
        ),
        "inactive_after_attempt": bool(session.get("inactive_after_attempt")),
        "zero_active_bots": int(cleanup.get("active_bots") or 0) == 0,
        "zero_leases": int(cleanup.get("lease_count") or 0) == 0,
        "empty_party": int(cleanup.get("party_bot_count") or 0) == 0,
        "remote_verified": bool(receipt.get("remote_verified")),
        "separate_raw_compact_pointers": (
            len(pointers) == 2
            and {Path(str(row.get("path") or "")).name for row in pointers}
            == {"raw.dvc", "compact.dvc"}
        ),
        "targeted_eviction_complete": not raw_dir.exists() and not compact_dir.exists(),
        "compact_local_report": report.get("published_raw_payloads_retained_locally") is False,
    }
    return {
        "attempt_index": int(session.get("attempt_index") or 0),
        "runtime_attempt_id": int(session.get("runtime_attempt_id") or 0),
        "server_action": str(session.get("server_action") or ""),
        "server_pid": int(session.get("server_pid") or 0),
        "server_epoch": int(session.get("server_epoch") or 0),
        "profile_generation": int(session.get("profile_generation") or 0),
        "profile_content_hash": str(session.get("profile_content_hash") or ""),
        "admitted_at_unix": int(session.get("admitted_at_unix") or 0),
        "closed_at_unix": int(session.get("closed_at_unix") or 0),
        "receipt_sha256": str(receipt.get("receipt_sha256") or ""),
        "checks": checks,
        "passed": all(checks.values()),
    }


def _live_contract(attempt_root: Path, minimum_soak_sec: int) -> dict[str, Any]:
    attempts = [
        _attempt_summary(path)
        for path in sorted(attempt_root.glob("attempt_*"))
        if path.is_dir()
    ]
    epochs = {row["server_epoch"] for row in attempts}
    pids = {row["server_pid"] for row in attempts}
    generations = {row["profile_generation"] for row in attempts}
    profile_hashes = {row["profile_content_hash"] for row in attempts}
    runtime_attempt_ids = [row["runtime_attempt_id"] for row in attempts]
    admitted = [row["admitted_at_unix"] for row in attempts if row["admitted_at_unix"]]
    closed = [row["closed_at_unix"] for row in attempts if row["closed_at_unix"]]
    soak_sec = max(closed) - min(admitted) if admitted and closed else 0
    checks = {
        "attempts_present": bool(attempts),
        "all_attempts_passed": bool(attempts) and all(row["passed"] for row in attempts),
        "one_server_epoch": len(epochs) == 1 and 0 not in epochs,
        "one_worldserver_process": len(pids) == 1 and 0 not in pids,
        "one_profile_generation": len(generations) == 1 and 0 not in generations,
        "one_profile_content_hash": len(profile_hashes) == 1 and "" not in profile_hashes,
        "fresh_runtime_attempts_monotonic": runtime_attempt_ids == list(
            range(runtime_attempt_ids[0], runtime_attempt_ids[0] + len(runtime_attempt_ids))
        ) if runtime_attempt_ids else False,
        "later_attempts_attach_without_restart": all(
            row["server_action"] == "already_healthy" for row in attempts[1:]
        ),
        "minimum_multi_hour_soak_met": soak_sec >= minimum_soak_sec,
    }
    return {
        "attempt_count": len(attempts),
        "soak_seconds": soak_sec,
        "minimum_soak_seconds": minimum_soak_sec,
        "server_epochs": sorted(epochs),
        "server_pids": sorted(pids),
        "runtime_attempt_ids": runtime_attempt_ids,
        "checks": checks,
        "attempts": attempts,
        "passed": all(checks.values()),
    }


def build_contract(args: argparse.Namespace) -> dict[str, Any]:
    attempt_root = args.attempt_root.resolve()
    attempt_root.mkdir(parents=True, exist_ok=True)
    if args.run_soak:
        if not os.environ.get("TRINITY_SOAP_USER") or not os.environ.get("TRINITY_SOAP_PASSWORD"):
            raise RuntimeError("TRINITY_SOAP_USER and TRINITY_SOAP_PASSWORD are required")
        for attempt_index in range(1, args.attempt_count + 1):
            output = attempt_root / f"attempt_{attempt_index:03d}"
            if _recover_closed_attempt(output):
                continue
            if output.exists() and any(output.iterdir()):
                raise RuntimeError(f"incomplete attempt directory blocks resume: {output}")
            _run_attempt(
                output,
                cohort_id=args.cohort_id,
                attempt_index=attempt_index,
                profile=args.profile,
                scenario_id=args.scenario_id,
                environment=args.session_environment,
                timeout_sec=args.attempt_timeout_sec,
                no_progress_window_sec=args.no_progress_window_sec,
                heartbeat_sec=args.heartbeat_sec,
            )
    static = _static_contract()
    live = _live_contract(attempt_root, args.minimum_soak_sec)
    identity = {
        "runner_sha256": sha256_file(RUNNER),
        "attempt_receipts_sha256": canonical_sha256(
            [row["receipt_sha256"] for row in live["attempts"]]
        ),
        "server_epoch_sha256": canonical_sha256(live["server_epochs"]),
    }
    contract = {
        "schema": "all_spec_phase6_serial_soak_contract_v1",
        "static": static,
        "live": live,
        "identity": identity,
        "gate_passed": static["passed"] and live["passed"],
    }
    contract["contract_sha256"] = canonical_sha256(contract)
    return contract


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--attempt-root",
        type=Path,
        default=Path("artifacts/all_spec_program/phase6_serial_soak_20260719_epoch2"),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("dataset/all_spec_phase6_serial_soak_contract"),
    )
    parser.add_argument("--run-soak", action="store_true")
    parser.add_argument("--attempt-count", type=int, default=8)
    parser.add_argument("--attempt-timeout-sec", type=int, default=960)
    parser.add_argument("--no-progress-window-sec", type=int, default=900)
    parser.add_argument("--heartbeat-sec", type=int, default=30)
    parser.add_argument("--minimum-soak-sec", type=int, default=7200)
    parser.add_argument("--cohort-id", default="phase6-serial-soak")
    parser.add_argument("--profile", default="stonecore_5n")
    parser.add_argument("--scenario-id", default="stonecore_5n")
    parser.add_argument("--session-environment", default="phase6-serial-soak")
    args = parser.parse_args()
    if args.attempt_count < 1:
        raise SystemExit("--attempt-count must be positive")
    if args.no_progress_window_sec >= args.attempt_timeout_sec:
        raise SystemExit("--no-progress-window-sec must be below --attempt-timeout-sec")
    contract = build_contract(args)
    attempt_root = args.attempt_root.resolve()
    soak_manifest = {
        "schema": "all_spec_phase6_serial_soak_input_manifest_v1",
        "gate_passed": contract["gate_passed"],
        "contract_sha256": contract["contract_sha256"],
        "attempt_count": contract["live"]["attempt_count"],
        "attempt_receipts_sha256": contract["identity"]["attempt_receipts_sha256"],
        "attempts": [
            {
                "attempt_index": row["attempt_index"],
                "receipt_sha256": row["receipt_sha256"],
                "session_file_sha256": sha256_file(
                    attempt_root / f"attempt_{row['attempt_index']:03d}" / "session.json"
                ),
                "report_file_sha256": sha256_file(
                    attempt_root / f"attempt_{row['attempt_index']:03d}" / "report.json"
                ),
            }
            for row in contract["live"]["attempts"]
        ],
    }
    write_json(attempt_root / "soak_manifest.json", soak_manifest)
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    write_json(output_dir / "contract.json", contract)
    manifest = {
        "schema": "all_spec_phase6_serial_soak_contract_manifest_v1",
        "contract_sha256": contract["contract_sha256"],
        "contract_file_sha256": hashlib.sha256(
            (output_dir / "contract.json").read_bytes()
        ).hexdigest(),
        "gate_passed": contract["gate_passed"],
    }
    write_json(output_dir / "manifest.json", manifest)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0 if contract["gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
