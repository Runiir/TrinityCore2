from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[2]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def json_actions(log_bytes: bytes, action: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for raw in log_bytes.splitlines():
        start = raw.find(b"{")
        end = raw.rfind(b"}")
        if start < 0 or end < start:
            continue
        try:
            row = json.loads(raw[start : end + 1])
        except (UnicodeDecodeError, json.JSONDecodeError):
            continue
        if isinstance(row, dict) and row.get("action") == action:
            rows.append(row)
    return rows


def accepted_foundation_status(status: dict[str, Any]) -> tuple[bool, list[str]]:
    runtime = status.get("raid_runtime") or {}
    roster = runtime.get("roster") or []
    roster_by_slot = sorted(roster, key=lambda row: row.get("slot", -1))
    reasons: list[str] = []
    checks = {
        "status_ok": status.get("ok") is True,
        "ten_bots": status.get("bots") == 10,
        "ten_leases": status.get("lease_count") == 10,
        "runtime_active": runtime.get("active") is True,
        "expected_size_10": runtime.get("expected_size") == 10,
        "active_size_10": runtime.get("active_size") == 10,
        "alive_size_10": runtime.get("alive_size") == 10,
        "roster_complete": runtime.get("roster_complete") is True,
        "difficulty_10n": runtime.get("expected_difficulty") == 0 and runtime.get("group_difficulty") == 0,
        "live_map_difficulty_10n": runtime.get("map_difficulty") == 0,
        "difficulty_matches": runtime.get("difficulty_matches") is True,
        "map_bwd": runtime.get("map_id") == 669,
        "instance_owned": int(runtime.get("instance_id") or 0) > 0,
        "lockout_save_owned": int(runtime.get("lockout_save_id") or 0) > 0,
        "group_owned": int(runtime.get("group_guid") or 0) > 0,
        "leader_owned": int(runtime.get("leader_guid") or 0) > 0,
        "server_epoch_owned": int(runtime.get("server_epoch") or 0) > 0,
        "attempt_owned": int(runtime.get("attempt_id") or 0) > 0,
        "boss_state_readback": len(runtime.get("boss_states") or []) == 6,
        "ready_check_satisfied": runtime.get("ready_check_satisfied") is True,
        "unique_leases": runtime.get("unique_leases") is True,
        "exact_roster": len(roster) == 10,
        "deterministic_slots": [row.get("slot") for row in roster_by_slot] == list(range(10)),
        "deterministic_subgroups": [row.get("subgroup") for row in roster_by_slot] == [0] * 5 + [1] * 5,
        "all_roster_active": all(row.get("active") is True for row in roster),
        "all_roster_leases_owned": all(row.get("lease_owned") is True for row in roster),
        "unique_roster_guids": len({row.get("guid") for row in roster}) == 10,
    }
    reasons.extend(name for name, passed in checks.items() if not passed)
    return not reasons, reasons


def accepted_native_recovery(statuses: list[dict[str, Any]]) -> tuple[bool, list[str]]:
    runtimes = [status.get("raid_runtime") or {} for status in statuses]
    checks = {
        "ready_check_observed": any(runtime.get("ready_check_satisfied") is True for runtime in runtimes),
        "native_wipe_observed": any(int(runtime.get("wipe_generation") or 0) > 0 for runtime in runtimes),
        "boss_reset_observed": any(int(runtime.get("boss_reset_generation") or 0) > 0 for runtime in runtimes),
        "native_recovery_observed": any(
            int(runtime.get("recovery_generation") or 0) > 0
            and runtime.get("recovery_state") == "recovered_ready_check"
            and runtime.get("ready_check_satisfied") is True
            for runtime in runtimes
        ),
    }
    reasons = [name for name, passed in checks.items() if not passed]
    return not reasons, reasons


def wait_for_prompt(process: subprocess.Popen[bytes], log_path: Path, timeout_sec: int) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"worldserver exited before readiness with code {process.returncode}")
        if log_path.exists() and b"TC>" in log_path.read_bytes()[-65536:]:
            return
        time.sleep(0.25)
    raise RuntimeError("worldserver readiness prompt timed out")


def git_identity(cwd: Path) -> dict[str, Any]:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=cwd, text=True).strip()
    porcelain = subprocess.check_output(["git", "status", "--porcelain=v1", "-z"], cwd=cwd)
    return {"head": head, "clean": not porcelain, "porcelain_sha256": hashlib.sha256(porcelain).hexdigest()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--worktree", type=Path, default=ROOT)
    parser.add_argument("--observe-sec", type=int, default=900)
    parser.add_argument("--startup-timeout-sec", type=int, default=180)
    parser.add_argument("--required-stable-statuses", type=int, default=3)
    args = parser.parse_args()

    binary = args.binary.resolve()
    config = args.config.resolve()
    output = args.output.resolve()
    worktree = args.worktree.resolve()
    if output.exists():
        raise SystemExit("output already exists; phase1 artifacts are immutable")
    if not binary.is_file() or not config.is_file():
        raise SystemExit("binary and config must exist")
    if args.observe_sec < 30 or args.required_stable_statuses < 2:
        raise SystemExit("observation must be at least 30 seconds and require at least two stable statuses")
    if subprocess.run(["pgrep", "-x", "worldserver"], stdout=subprocess.DEVNULL, check=False).returncode == 0:
        raise SystemExit("a worldserver process already exists")

    identity_before = git_identity(worktree)
    if not identity_before["clean"]:
        raise SystemExit("canonical phase1 capture requires a clean worktree")

    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    stable: list[dict[str, Any]] = []
    last_rejections: list[str] = ["no_status_observed"]
    startup_error: str | None = None
    with tempfile.NamedTemporaryFile(prefix="raid-phase1-worldserver-", suffix=".log", delete=False) as log:
        log_path = Path(log.name)
        process = subprocess.Popen(
            [str(binary), "--config", str(config)], cwd=worktree, stdin=subprocess.PIPE,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )
        try:
            wait_for_prompt(process, log_path, args.startup_timeout_sec)
            assert process.stdin is not None
            deadline = time.monotonic() + args.observe_sec
            next_probe = 0.0
            seen_statuses = 0
            recovery_accepted = False
            while time.monotonic() < deadline and not (
                len(stable) >= args.required_stable_statuses and recovery_accepted
            ):
                if process.poll() is not None:
                    break
                if time.monotonic() >= next_probe:
                    process.stdin.write(b"botauto status\nbotauto diagnose all\nbotauto trace all 20\n")
                    process.stdin.flush()
                    next_probe = time.monotonic() + 5.0
                    time.sleep(1.0)
                    statuses = json_actions(log_path.read_bytes(), "botauto_status")
                    for status in statuses[seen_statuses:]:
                        accepted, rejections = accepted_foundation_status(status)
                        last_rejections = rejections
                        if accepted:
                            stable.append(status)
                        else:
                            stable.clear()
                    seen_statuses = len(statuses)
                    recovery_accepted, _ = accepted_native_recovery(statuses)
                time.sleep(0.25)

            process.stdin.write(b"botauto stop\nbotauto status\nserver exit\n")
            process.stdin.flush()
            process.wait(timeout=60)
        except Exception as error:  # captured as infrastructure evidence below
            startup_error = f"{type(error).__name__}:{error}"
        finally:
            if process.poll() is None:
                os.killpg(process.pid, 15)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, 9)
                    process.wait(timeout=10)
        log_bytes = log_path.read_bytes()
        log_path.unlink(missing_ok=True)

    statuses = json_actions(log_bytes, "botauto_status")
    diagnoses = json_actions(log_bytes, "botauto_diagnose")
    traces = json_actions(log_bytes, "botauto_trace")
    stop_rows = json_actions(log_bytes, "botauto_stop")
    recovery_accepted, recovery_rejections = accepted_native_recovery(statuses)
    cleanup_status = statuses[-1] if statuses else {}
    cleanup_ok = cleanup_status.get("bots") == 0 and cleanup_status.get("lease_count") == 0
    identity_after = git_identity(worktree)
    identity_stable = identity_before == identity_after
    success = (
        startup_error is None
        and process.returncode == 0
        and len(stable) >= args.required_stable_statuses
        and recovery_accepted
        and cleanup_ok
        and bool(stop_rows and stop_rows[-1].get("ok") is True)
        and identity_stable
    )
    report = {
        "schema_version": 1,
        "capture_id": "cata_raid_phase1_bwd_10n_foundation_v1",
        "classification": "success" if success else ("infrastructure_abort" if startup_error else "foundation_gate_failed"),
        "started_at_utc": started_utc,
        "identity": identity_before,
        "identity_stable_during_run": identity_stable,
        "binary_sha256": sha256_file(binary),
        "config_sha256": sha256_file(config),
        "worldserver_exit_code": process.returncode,
        "startup_error": startup_error,
        "required_stable_statuses": args.required_stable_statuses,
        "accepted_stable_statuses": len(stable),
        "last_foundation_rejections": last_rejections,
        "native_recovery_accepted": recovery_accepted,
        "native_recovery_rejections": recovery_rejections,
        "accepted_raid_runtime": stable[-1].get("raid_runtime") if stable else None,
        "diagnose_observed": bool(diagnoses),
        "trace_observed": bool(traces),
        "stop_observed": bool(stop_rows),
        "cleanup_zero_bots_and_leases": cleanup_ok,
        "log_sha256": hashlib.sha256(log_bytes).hexdigest(),
        "log_bytes": len(log_bytes),
        "raw_log_retained": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
