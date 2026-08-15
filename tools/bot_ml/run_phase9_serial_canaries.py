"""Run the Phase 9 Stonecore canaries through one serial session operator."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ROOT = REPO_ROOT / "artifacts/all_spec_program/phase9_serial_canaries_20260728"


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(f"{path.suffix}.tmp")
    temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def route_start_restored(session: dict[str, Any]) -> bool:
    route_start = (session.get("preparation") or {}).get("route_bot_start") or {}
    return bool(
        route_start.get("applied") is True
        and int(route_start.get("statements") or 0) > 0
        and int(route_start.get("map_id") or 0) == 725
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-plan", type=Path, default=DEFAULT_ROOT / "run_plan.json")
    parser.add_argument("--start-index", type=int, default=1)
    parser.add_argument("--stop-index", type=int, default=8)
    parser.add_argument("--state-output", type=Path, default=DEFAULT_ROOT / "operator_state.json")
    parser.add_argument("--log-dir", type=Path, default=DEFAULT_ROOT / "operator_logs")
    args = parser.parse_args()

    plan = read_json(args.run_plan.resolve())
    attempts = plan.get("attempts") or plan.get("runs") or []
    if plan.get("restore_route_bot_start_each_attempt") is not True:
        raise SystemExit("Phase 9 serial plan must restore the route start before every attempt")
    if any("--skip-route-bot-start-mutation" in (attempt.get("command") or []) for attempt in attempts):
        raise SystemExit("Phase 9 serial plan disables required per-attempt route-start restoration")
    selected = [
        attempt
        for attempt in attempts
        if args.start_index <= int(attempt["serial_index"]) <= args.stop_index
    ]
    if not selected:
        raise SystemExit("no Phase 9 attempts selected")

    identity_path = Path(
        next(
            attempt["command"][attempt["command"].index("--evidence-identity-manifest") + 1]
            for attempt in selected
        )
    )
    identity = read_json(identity_path)
    expected_runtime = identity["runtime_identity"]
    state: dict[str, Any] = {
        "schema": "phase9_serial_canary_operator_state_v1",
        "run_plan": str(args.run_plan.resolve().relative_to(REPO_ROOT)),
        "start_index": args.start_index,
        "stop_index": args.stop_index,
        "identity_manifest_sha256": identity["manifest_sha256"],
        "expected_server_process_id": expected_runtime["server_process_id"],
        "expected_server_epoch": expected_runtime["server_epoch"],
        "expected_profile_generation": expected_runtime["profile_generation"],
        "expected_profile_content_hash": expected_runtime["profile_content_hash"].lower(),
        "attempts": [],
        "status": "running",
    }
    write_json(args.state_output.resolve(), state)
    args.log_dir.resolve().mkdir(parents=True, exist_ok=True)

    for attempt in selected:
        serial_index = int(attempt["serial_index"])
        output_dir = (REPO_ROOT / attempt["output_dir"]).resolve()
        if output_dir.exists():
            raise SystemExit(f"refusing to overwrite existing attempt directory: {output_dir}")

        log_path = args.log_dir.resolve() / f"canary_{serial_index:02d}.log"
        current = {
            "serial_index": serial_index,
            "attempt_id": attempt["attempt_id"],
            "composition_id": attempt["composition_id"],
            "output_dir": str(output_dir.relative_to(REPO_ROOT)),
            "log": str(log_path.relative_to(REPO_ROOT)),
            "status": "running",
        }
        state["attempts"].append(current)
        write_json(args.state_output.resolve(), state)
        print(json.dumps({"event": "start", **current}, sort_keys=True), flush=True)

        command = list(attempt["command"])
        if command and command[0] == "pixi":
            command[0] = str(Path.home() / ".pixi/bin/pixi")
        with log_path.open("wb") as log:
            result = subprocess.run(
                command,
                cwd=REPO_ROOT,
                env=os.environ.copy(),
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )

        summary_path = output_dir / "batch/retained/summary.json"
        receipt_path = output_dir / "batch/retained/publication_receipt.json"
        report_path = output_dir / "report.json"
        summary = read_json(summary_path) if summary_path.exists() else {}
        receipt = read_json(receipt_path) if receipt_path.exists() else {}
        report = read_json(report_path) if report_path.exists() else {}
        session = report.get("session") or {}
        cleanup = session.get("cleanup") or {}

        current.update(
            {
                "status": "closed",
                "returncode": result.returncode,
                "acceptable_final_evidence": summary.get("acceptable_final_evidence"),
                "completion_reason": summary.get("completion_reason"),
                "failure_reason": summary.get("failure_reason"),
                "remote_verified": receipt.get("remote_verified"),
                "receipt_sha256": receipt.get("receipt_sha256"),
                "raw_retained_locally": (output_dir / "batch/raw").exists(),
                "compact_retained_locally": (output_dir / "batch/compact").exists(),
                "batch_cache_retained_locally": (output_dir / "batch/.batch-dvc-cache").exists(),
                "server_process_id": session.get("server_process_id"),
                "server_epoch": session.get("server_epoch"),
                "profile_generation": session.get("profile_generation"),
                "profile_content_hash": str(session.get("profile_content_hash") or "").lower(),
                "exact_party_verified": session.get("exact_party_verified"),
                "route_start_restored": route_start_restored(session),
                "cleanup": cleanup,
            }
        )
        identity_matches = (
            current["server_process_id"] == state["expected_server_process_id"]
            and current["server_epoch"] == state["expected_server_epoch"]
            and current["profile_generation"] == state["expected_profile_generation"]
            and current["profile_content_hash"] == state["expected_profile_content_hash"]
        )
        cleanup_complete = (
            cleanup.get("active") is False
            and cleanup.get("active_bots") == 0
            and cleanup.get("lease_count") == 0
            and cleanup.get("party_bot_count") == 0
        )
        current["identity_matches"] = identity_matches
        current["cleanup_complete"] = cleanup_complete
        current["targeted_eviction_complete"] = bool(
            current["remote_verified"]
            and not current["raw_retained_locally"]
            and not current["compact_retained_locally"]
            and not current["batch_cache_retained_locally"]
        )
        current["passed"] = bool(
            result.returncode == 0
            and current["acceptable_final_evidence"]
            and current["remote_verified"]
            and current["targeted_eviction_complete"]
            and current["exact_party_verified"]
            and current["route_start_restored"]
            and identity_matches
            and cleanup_complete
        )
        print(json.dumps({"event": "closed", **current}, sort_keys=True), flush=True)
        if not current["passed"]:
            state["status"] = "failed"
            state["failed_serial_index"] = serial_index
            write_json(args.state_output.resolve(), state)
            return 1
        # The immutable command/output stream is already present in the
        # remotely verified batch.  The outer operator log is redundant bulk
        # and is removed only after the acceptance and cleanup gates pass.
        log_path.unlink(missing_ok=True)
        current["operator_log_evicted_after_publication"] = True
        write_json(args.state_output.resolve(), state)

    state["status"] = "passed"
    write_json(args.state_output.resolve(), state)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
