#!/usr/bin/env python3
"""Host-wide FIFO admission for heavyweight TrinityCore build work.

The coordinator stores only sanitized command hashes beneath the Git common
directory so every worktree shares one lease.  It deliberately owns the child
process group and continuously enforces the frozen host-resource policy.
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import hashlib
import json
import os
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, Sequence


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_POLICY = ROOT / "experiments/configs/cata_raid_build_resource_policy_v1.json"
STATE_VERSION = 1
TERMINAL_STATES = {"canceled", "finished", "recovered_stale"}
FANOUT_OPTIONS = {"-j", "--jobs", "--parallel"}
SHELL_WRAPPERS = {"bash", "dash", "env", "fish", "sh", "zsh"}


class CoordinatorError(RuntimeError):
    """Fail-closed coordinator error."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(json.dumps(value, indent=2, sort_keys=True).encode() + b"\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def load_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise CoordinatorError(f"cannot load required JSON {path}: {error}") from error
    if not isinstance(value, dict):
        raise CoordinatorError(f"required JSON object expected at {path}")
    return value


def git_output(worktree: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(worktree), *arguments],
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode:
        raise CoordinatorError(result.stderr.strip() or "git identity lookup failed")
    return result.stdout.strip()


def git_common_dir(worktree: Path) -> Path:
    raw = Path(git_output(worktree, "rev-parse", "--git-common-dir"))
    return raw.resolve() if raw.is_absolute() else (worktree / raw).resolve()


def coordinator_state_dir(worktree: Path) -> Path:
    override = os.environ.get("TRINITY_RAID_BUILD_STATE_DIR_OVERRIDE")
    test_mode = os.environ.get("TRINITY_RAID_BUILD_TESTING") == "1"
    if override:
        if not test_mode:
            raise CoordinatorError("state override is permitted only for synthetic coordinator tests")
        return Path(override).resolve()
    return git_common_dir(worktree) / "raid_program/build_queue_v1"


def process_start_ticks(pid: int) -> int | None:
    try:
        # The command name may contain spaces/parentheses, so split after its final ')'.
        tail = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").rsplit(")", 1)[1]
        fields = tail.split()
        return int(fields[19])  # field 22 overall; tail begins at field 3.
    except (OSError, ValueError, IndexError):
        return None


def same_process(pid: int | None, start_ticks: int | None) -> bool:
    return bool(pid and start_ticks and process_start_ticks(pid) == start_ticks)


def process_identity(pid: int) -> dict[str, int]:
    start = process_start_ticks(pid)
    if start is None:
        raise CoordinatorError(f"cannot resolve PID start time for {pid}")
    return {"pid": pid, "start_ticks": start}


@dataclass(frozen=True)
class Paths:
    state_dir: Path
    state: Path
    lock: Path
    receipts: Path
    logs: Path
    link_lock: Path

    @classmethod
    def for_worktree(cls, worktree: Path) -> "Paths":
        root = coordinator_state_dir(worktree)
        return cls(
            state_dir=root,
            state=root / "state.json",
            lock=root / "state.lock",
            receipts=root / "receipts",
            logs=root / "logs",
            link_lock=root / "link.lock",
        )


@contextlib.contextmanager
def locked_state(paths: Paths):
    paths.state_dir.mkdir(parents=True, exist_ok=True)
    paths.lock.touch(exist_ok=True)
    with paths.lock.open("r+") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        if paths.state.exists():
            state = load_json(paths.state)
        else:
            state = {
                "schema_version": STATE_VERSION,
                "next_queue_sequence": 1,
                "active": None,
                "queue": [],
                "tickets": {},
            }
        if state.get("schema_version") != STATE_VERSION:
            raise CoordinatorError("unsupported build queue state schema")
        state.setdefault("next_queue_sequence", 1)
        yield state
        atomic_json(paths.state, state)
        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def read_meminfo() -> dict[str, int]:
    result: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        name, raw = line.split(":", 1)
        result[name] = int(raw.strip().split()[0]) * 1024
    return result


def read_memory_psi() -> dict[str, float]:
    result = {"some_avg10": 0.0, "full_avg10": 0.0}
    try:
        for line in Path("/proc/pressure/memory").read_text(encoding="utf-8").splitlines():
            category, *fields = line.split()
            values = dict(field.split("=", 1) for field in fields)
            result[f"{category}_avg10"] = float(values["avg10"])
    except (OSError, KeyError, ValueError):
        result["unavailable"] = 1.0
    return result


def resource_snapshot(worktree: Path) -> dict[str, float | int]:
    meminfo = read_meminfo()
    disk = shutil.disk_usage(worktree)
    load1, load5, load15 = os.getloadavg()
    psi = read_memory_psi()
    return {
        "captured_at_utc": utc_now(),
        "memory_total_bytes": meminfo["MemTotal"],
        "memory_available_bytes": meminfo["MemAvailable"],
        "swap_used_bytes": meminfo.get("SwapTotal", 0) - meminfo.get("SwapFree", 0),
        "memory_psi_some_avg10": psi["some_avg10"],
        "memory_psi_full_avg10": psi["full_avg10"],
        "load_average_1m": load1,
        "load_average_5m": load5,
        "load_average_15m": load15,
        "filesystem_available_bytes": disk.free,
    }


def reserve_bytes(policy: dict, snapshot: dict) -> int:
    thresholds = policy["admission_thresholds"]
    fixed = float(thresholds["minimum_memory_available_gib"]) * 1024**3
    fractional = float(thresholds["minimum_memory_available_fraction"]) * int(
        snapshot["memory_total_bytes"]
    )
    return int(max(fixed, fractional))


def pressure_reasons(policy: dict, snapshot: dict, initial_swap_used: int | None = None) -> list[str]:
    thresholds = policy["admission_thresholds"]
    reasons: list[str] = []
    if int(snapshot["memory_available_bytes"]) < reserve_bytes(policy, snapshot):
        reasons.append("memory_reserve")
    if float(snapshot["memory_psi_some_avg10"]) > float(thresholds["maximum_memory_psi_some_avg10"]):
        reasons.append("memory_psi_some")
    if float(snapshot["memory_psi_full_avg10"]) > float(thresholds["maximum_memory_psi_full_avg10"]):
        reasons.append("memory_psi_full")
    if float(snapshot["load_average_1m"]) > float(thresholds["maximum_load_average_1m"]):
        reasons.append("load_average")
    minimum_disk = float(thresholds["minimum_filesystem_available_gib"]) * 1024**3
    if int(snapshot["filesystem_available_bytes"]) < minimum_disk:
        reasons.append("filesystem_reserve")
    if initial_swap_used is not None:
        allowed_growth = int(thresholds["maximum_swap_growth_mib_per_job"]) * 1024**2
        if int(snapshot["swap_used_bytes"]) - initial_swap_used > allowed_growth:
            reasons.append("swap_growth")
    return reasons


def find_live_validation_processes(policy: dict, ignore_pids: Iterable[int] = ()) -> list[dict[str, object]]:
    ignored = set(ignore_pids)
    patterns = policy["live_validation_exclusion"]["process_patterns"]
    found: list[dict[str, object]] = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit() or int(entry.name) in ignored:
            continue
        try:
            arguments = [
                value.decode(errors="replace")
                for value in (entry / "cmdline").read_bytes().split(b"\0")
                if value
            ]
        except OSError:
            continue
        if not arguments:
            continue
        basenames = [Path(value).name for value in arguments]
        matched_pattern: str | None = None
        for pattern in patterns:
            tokens = pattern.split()
            if len(tokens) == 1:
                # Match executable/script argv elements, never arbitrary prose or
                # build-target arguments that happen to mention a protected name.
                executable_positions = basenames[:1]
                if basenames and basenames[0].startswith("python"):
                    executable_positions = basenames[:2]
                if tokens[0] in executable_positions:
                    matched_pattern = pattern
                    break
            else:
                for index in range(len(arguments) - len(tokens) + 1):
                    window = arguments[index : index + len(tokens)]
                    normalized = [Path(window[0]).name, *window[1:]]
                    if normalized == tokens:
                        matched_pattern = pattern
                        break
                if matched_pattern:
                    break
        if matched_pattern:
            found.append({"pid": int(entry.name), "matched_pattern": matched_pattern})
    return sorted(found, key=lambda row: int(row["pid"]))


def command_hash(command: Sequence[str]) -> str:
    return sha256_bytes(canonical_json(list(command)))


def worktree_state(worktree: Path) -> dict[str, object]:
    status = subprocess.run(
        ["git", "-C", str(worktree), "status", "--porcelain=v1", "-z", "--untracked-files=all"],
        check=False,
        capture_output=True,
    )
    if status.returncode:
        raise CoordinatorError(status.stderr.decode(errors="replace").strip() or "git status failed")
    porcelain = status.stdout
    return {
        "commit": git_output(worktree, "rev-parse", "HEAD"),
        "tree": git_output(worktree, "rev-parse", "HEAD^{tree}"),
        "clean": not porcelain,
        "dirty": bool(porcelain),
        "porcelain_sha256": sha256_bytes(porcelain),
    }


def validate_command(command: Sequence[str], compiler_jobs: int) -> None:
    if not command:
        raise CoordinatorError("a command is required after '--'")
    executable = Path(command[0]).name
    if executable in SHELL_WRAPPERS:
        raise CoordinatorError(
            "shell/environment wrappers are forbidden because embedded build fan-out cannot be audited"
        )
    index = 0
    while index < len(command):
        token = command[index]
        numeric: int | None = None
        if token in FANOUT_OPTIONS:
            if index + 1 >= len(command) or not command[index + 1].isdigit():
                raise CoordinatorError(f"unbounded or invalid build fan-out option: {token}")
            numeric = int(command[index + 1])
            index += 1
        elif re.fullmatch(r"-j\d+", token):
            numeric = int(token[2:])
        elif token.startswith("--parallel=") or token.startswith("--jobs="):
            raw = token.split("=", 1)[1]
            if not raw.isdigit():
                raise CoordinatorError(f"invalid build fan-out option: {token}")
            numeric = int(raw)
        if numeric is not None and (numeric < 1 or numeric > compiler_jobs):
            raise CoordinatorError(
                f"requested build fan-out {numeric} exceeds coordinator ceiling {compiler_jobs}"
            )
        index += 1


def new_ticket(worktree: Path, resource_class: str, command: Sequence[str] | None = None) -> dict:
    resolved = worktree.resolve()
    source_state = worktree_state(resolved)
    return {
        "ticket_id": f"raid-build-{uuid.uuid4().hex}",
        "state": "queued",
        "resource_class": resource_class,
        "requested_at_utc": utc_now(),
        "requester": process_identity(os.getpid()),
        "worktree": str(resolved),
        "commit": source_state["commit"],
        "worktree_dirty": source_state["dirty"],
        "worktree_porcelain_sha256": source_state["porcelain_sha256"],
        "source_identity": {"request": source_state},
        "command_sha256": command_hash(command) if command else None,
        "admission": None,
        "completion": None,
    }


def enqueue(paths: Paths, ticket: dict) -> None:
    with locked_state(paths) as state:
        identifier = ticket["ticket_id"]
        if identifier in state["tickets"]:
            raise CoordinatorError(f"duplicate ticket {identifier}")
        ticket["queue_sequence"] = int(state["next_queue_sequence"])
        state["next_queue_sequence"] = ticket["queue_sequence"] + 1
        state["tickets"][identifier] = ticket
        state["queue"].append(identifier)


def safe_kill_process_group(ticket: dict, sig: int) -> bool:
    child = ticket.get("child") or {}
    pid = child.get("pid")
    start = child.get("start_ticks")
    pgid = child.get("pgid")
    if not (same_process(pid, start) and pgid == pid):
        return False
    try:
        os.killpg(int(pgid), sig)
        return True
    except ProcessLookupError:
        return False


def stop_recorded_process_group(ticket: dict, grace_seconds: float) -> bool:
    """Stop only the recorded PID/start-time-safe child process group."""
    child = ticket.get("child") or {}
    pid = child.get("pid")
    start = child.get("start_ticks")
    if not same_process(pid, start):
        return False
    sent = safe_kill_process_group(ticket, signal.SIGTERM)
    if not sent:
        return False
    deadline = time.monotonic() + grace_seconds
    while time.monotonic() < deadline and same_process(pid, start):
        time.sleep(0.05)
    if same_process(pid, start):
        safe_kill_process_group(ticket, signal.SIGKILL)
    return True


def recover_stale_locked(state: dict, paths: Paths) -> list[dict]:
    active_id = state.get("active")
    if not active_id:
        return []
    ticket = state["tickets"].get(active_id)
    if not ticket:
        state["active"] = None
        return [{"classification": "orphan_state_recovered", "ticket_id": active_id}]
    owner = ticket.get("lease_owner") or {}
    if same_process(owner.get("pid"), owner.get("start_ticks")):
        return []
    terminated = stop_recorded_process_group(ticket, 1.0)
    event = {
        "schema_version": 1,
        "ticket_id": active_id,
        "classification": "stale_lease_recovered",
        "recovered_at_utc": utc_now(),
        "child_process_group_terminated": terminated,
        "pid_reuse_safe_validation": True,
    }
    ticket["state"] = "recovered_stale"
    ticket["completion"] = event
    state["active"] = None
    state["queue"] = [value for value in state["queue"] if value != active_id]
    atomic_json(paths.receipts / f"{active_id}.stale-recovery.json", event)
    return [event]


def try_admit(paths: Paths, policy: dict, ticket_id: str, worktree: Path) -> tuple[bool, dict, list[str]]:
    snapshot = resource_snapshot(worktree)
    source_snapshot = worktree_state(worktree)
    reasons = pressure_reasons(policy, snapshot)
    live = find_live_validation_processes(policy, ignore_pids={os.getpid(), os.getppid()})
    if live:
        reasons.append("canonical_live_validation_active")
    with locked_state(paths) as state:
        recover_stale_locked(state, paths)
        ticket = state["tickets"].get(ticket_id)
        if not ticket:
            raise CoordinatorError(f"unknown ticket {ticket_id}")
        if ticket["state"] == "cancel_requested" or ticket["state"] == "canceled":
            return False, snapshot, ["canceled"]
        if state["active"] is not None or not state["queue"] or state["queue"][0] != ticket_id:
            ticket["state"] = "queued"
            return False, snapshot, ["fifo_wait"]
        if reasons:
            ticket["state"] = "waiting_resource"
            ticket["last_preflight"] = {"at_utc": utc_now(), "reasons": reasons}
            return False, snapshot, reasons
        owner = process_identity(os.getpid())
        ticket["state"] = "active"
        ticket["lease_owner"] = owner
        ticket.setdefault("source_identity", {})["admission"] = source_snapshot
        ticket["admission"] = {"admitted_at_utc": utc_now(), "preflight": snapshot}
        ticket["heartbeat_at_utc"] = utc_now()
        state["active"] = ticket_id
        return True, snapshot, []


def peak_observations(samples: Sequence[dict]) -> dict:
    return {
        "sample_count": len(samples),
        "minimum_memory_available_bytes": min(int(row["memory_available_bytes"]) for row in samples),
        "maximum_swap_used_bytes": max(int(row["swap_used_bytes"]) for row in samples),
        "maximum_memory_psi_some_avg10": max(float(row["memory_psi_some_avg10"]) for row in samples),
        "maximum_memory_psi_full_avg10": max(float(row["memory_psi_full_avg10"]) for row in samples),
        "maximum_load_average_1m": max(float(row["load_average_1m"]) for row in samples),
        "minimum_filesystem_available_bytes": min(int(row["filesystem_available_bytes"]) for row in samples),
    }


def mark_heartbeat(paths: Paths, ticket_id: str, child: dict | None = None) -> str:
    with locked_state(paths) as state:
        ticket = state["tickets"][ticket_id]
        if child is not None:
            ticket["child"] = child
        ticket["heartbeat_at_utc"] = utc_now()
        return ticket["state"]


def terminate_group(process: subprocess.Popen, grace_seconds: float) -> None:
    if process.poll() is not None:
        return
    with contextlib.suppress(ProcessLookupError):
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=grace_seconds)
    except subprocess.TimeoutExpired:
        with contextlib.suppress(ProcessLookupError):
            os.killpg(process.pid, signal.SIGKILL)
        process.wait(timeout=grace_seconds)


def execute_process(
    command: Sequence[str],
    worktree: Path,
    environment: dict[str, str],
    log_path: Path,
    policy: dict,
    paths: Paths,
    ticket_id: str,
    snapshot_provider: Callable[[Path], dict] = resource_snapshot,
) -> tuple[int, str, list[dict], list[str]]:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    process = subprocess.Popen(
        list(command),
        cwd=worktree,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    child = process_identity(process.pid) | {"pgid": process.pid}
    mark_heartbeat(paths, ticket_id, child)
    selector = selectors.DefaultSelector()
    assert process.stdout is not None
    os.set_blocking(process.stdout.fileno(), False)
    selector.register(process.stdout, selectors.EVENT_READ)
    thresholds = policy["admission_thresholds"]
    interval = float(thresholds["sample_interval_seconds"])
    sustained_limit = int(thresholds["sustained_unsafe_sample_count"])
    grace = float(policy["coordination"]["termination_grace_seconds"])
    samples: list[dict] = []
    unsafe_streak = 0
    terminal_reasons: list[str] = []
    classification = "command_failed"
    initial_swap: int | None = None
    next_sample = 0.0
    try:
        with log_path.open("wb") as log:
            while True:
                for key, _ in selector.select(timeout=min(interval, 0.25)):
                    try:
                        chunk = os.read(key.fileobj.fileno(), 65536)
                    except BlockingIOError:
                        chunk = b""
                    if chunk:
                        log.write(chunk)
                        log.flush()
                        sys.stdout.buffer.write(chunk)
                        sys.stdout.buffer.flush()
                now = time.monotonic()
                if now >= next_sample:
                    snapshot = snapshot_provider(worktree)
                    samples.append(snapshot)
                    if initial_swap is None:
                        initial_swap = int(snapshot["swap_used_bytes"])
                    reasons = pressure_reasons(policy, snapshot, initial_swap)
                    unsafe_streak = unsafe_streak + 1 if reasons else 0
                    state_value = mark_heartbeat(paths, ticket_id)
                    if state_value == "cancel_requested":
                        terminal_reasons = ["cancel_requested"]
                        classification = "canceled"
                        terminate_group(process, grace)
                    elif unsafe_streak >= sustained_limit:
                        terminal_reasons = reasons
                        classification = "build_resource_abort"
                        terminate_group(process, grace)
                    next_sample = now + interval
                if process.poll() is not None:
                    while True:
                        try:
                            chunk = os.read(process.stdout.fileno(), 65536)
                        except BlockingIOError:
                            break
                        if not chunk:
                            break
                        log.write(chunk)
                        sys.stdout.buffer.write(chunk)
                    break
    except BaseException:
        terminate_group(process, grace)
        raise
    finally:
        selector.close()
    returncode = int(process.returncode or 0)
    if not terminal_reasons:
        classification = "success" if returncode == 0 else "command_failed"
    return returncode, classification, samples, terminal_reasons


def coordinated_environment(policy: dict, paths: Paths, ticket_id: str) -> dict[str, str]:
    compiler_jobs = int(policy["parallelism"]["maximum_compiler_jobs"])
    linker_jobs = int(policy["parallelism"]["maximum_linker_jobs"])
    environment = dict(os.environ)
    environment.update(
        {
            "CMAKE_BUILD_PARALLEL_LEVEL": str(compiler_jobs),
            "CTEST_PARALLEL_LEVEL": str(compiler_jobs),
            "MAKEFLAGS": f"-j{compiler_jobs}",
            "NINJAFLAGS": f"-j{compiler_jobs}",
            "TRINITY_RAID_BUILD_COORDINATED": "1",
            "TRINITY_RAID_BUILD_TICKET": ticket_id,
            "TRINITY_RAID_BUILD_COMPILER_JOBS": str(compiler_jobs),
            "TRINITY_RAID_BUILD_LINKER_JOBS": str(linker_jobs),
            "TRINITY_RAID_BUILD_LINK_LOCK": str(paths.link_lock),
        }
    )
    return environment


def finalize_ticket(paths: Paths, ticket_id: str, receipt: dict) -> None:
    with locked_state(paths) as state:
        ticket = state["tickets"][ticket_id]
        ticket["state"] = "finished" if receipt["classification"] != "canceled" else "canceled"
        ticket["completion"] = {
            "classification": receipt["classification"],
            "ended_at_utc": receipt["ended_at_utc"],
            "receipt_sha256": receipt["receipt_sha256"],
        }
        state["queue"] = [value for value in state["queue"] if value != ticket_id]
        if state.get("active") == ticket_id:
            state["active"] = None


def run_ticket(
    worktree: Path,
    policy: dict,
    resource_class: str,
    command: Sequence[str],
    ticket_id: str | None,
    receipt_output: Path | None,
    admission_timeout: float | None,
) -> tuple[int, dict]:
    paths = Paths.for_worktree(worktree)
    compiler_jobs = int(policy["parallelism"]["maximum_compiler_jobs"])
    validate_command(command, compiler_jobs)
    if resource_class == "synthetic" and os.environ.get("TRINITY_RAID_BUILD_TESTING") != "1":
        raise CoordinatorError("synthetic resource class is test-only")
    if resource_class not in policy["resource_classes"]:
        raise CoordinatorError(f"unknown resource class {resource_class}")
    if ticket_id is None:
        ticket = new_ticket(worktree, resource_class, command)
        ticket_id = ticket["ticket_id"]
        enqueue(paths, ticket)
    else:
        with locked_state(paths) as state:
            ticket = state["tickets"].get(ticket_id)
            if not ticket:
                raise CoordinatorError(f"unknown ticket {ticket_id}")
            if ticket["state"] not in {"queued", "waiting_resource"}:
                raise CoordinatorError(f"ticket {ticket_id} is not runnable from {ticket['state']}")
            if Path(ticket["worktree"]).resolve() != worktree.resolve():
                raise CoordinatorError("ticket worktree does not match current worktree")
            ticket["command_sha256"] = command_hash(command)
    started_wait = time.monotonic()
    wait_timeout = admission_timeout or float(policy["coordination"]["default_admission_timeout_seconds"])
    poll = float(policy["coordination"]["admission_poll_seconds"])
    preflight: dict = {}
    while True:
        admitted, preflight, reasons = try_admit(paths, policy, ticket_id, worktree)
        if admitted:
            break
        if reasons == ["canceled"]:
            raise CoordinatorError(f"ticket {ticket_id} was canceled before admission")
        if time.monotonic() - started_wait > wait_timeout:
            cancel_ticket(paths, ticket_id)
            raise CoordinatorError(f"admission timeout for {ticket_id}: {','.join(reasons)}")
        time.sleep(poll)
    admitted_monotonic = time.monotonic()
    with locked_state(paths) as state:
        admitted_at_utc = state["tickets"][ticket_id]["admission"]["admitted_at_utc"]
        ticket = dict(state["tickets"][ticket_id])
    log_path = paths.logs / f"{ticket_id}.log"
    environment = coordinated_environment(policy, paths, ticket_id)
    returncode = 1
    classification = "coordinator_error"
    samples: list[dict] = [preflight]
    terminal_reasons: list[str] = []
    error_message: str | None = None
    request_source = (ticket.get("source_identity") or {}).get("request")
    admission_source = (ticket.get("source_identity") or {}).get("admission")
    source_identity_admissible = bool(
        request_source and admission_source
        and request_source == admission_source
        and (
            resource_class == "synthetic"
            or (
                request_source.get("clean") is True
                and admission_source.get("clean") is True
            )
        )
    )
    worldserver_path = (worktree / "build/src/server/worldserver/worldserver").resolve()
    worldserver_before: dict[str, object] | None = None
    if resource_class in {"worldserver_build", "integration_build"} and worldserver_path.is_file():
        before_stat = worldserver_path.stat()
        worldserver_before = {
            "size_bytes": before_stat.st_size,
            "mtime_ns": before_stat.st_mtime_ns,
            "sha256": sha256_file(worldserver_path),
        }
    log_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        if not source_identity_admissible:
            returncode = 76
            classification = "build_provenance_abort"
            error_message = "source_identity_changed_or_dirty_before_admission"
            log_path.write_text(error_message + "\n", encoding="utf-8")
        else:
            returncode, classification, process_samples, terminal_reasons = execute_process(
                command, worktree, environment, log_path, policy, paths, ticket_id
            )
            samples.extend(process_samples)
    except BaseException as error:
        classification = "coordinator_error"
        error_message = f"{type(error).__name__}: {error}"
        with locked_state(paths) as state:
            safe_kill_process_group(state["tickets"][ticket_id], signal.SIGTERM)
        if isinstance(error, KeyboardInterrupt):
            classification = "canceled"
    ended = utc_now()
    completion_source = worktree_state(worktree)
    source_identity = {
        "request": request_source,
        "admission": admission_source,
        "completion": completion_source,
    }
    source_identity_stable = bool(
        request_source and admission_source
        and request_source == admission_source == completion_source
        and (
            resource_class == "synthetic"
            or all(snapshot.get("clean") is True for snapshot in source_identity.values())
        )
    )
    provenance_reasons: list[str] = []
    if not source_identity_admissible:
        provenance_reasons.append("source_identity_changed_or_dirty_before_admission")
    if not source_identity_stable:
        provenance_reasons.append("source_identity_changed_or_dirty_before_completion")
    if classification == "success" and not source_identity_stable:
        classification = "build_provenance_abort"
        returncode = 76
    log_hash = sha256_bytes(log_path.read_bytes()) if log_path.exists() else None
    output_artifacts: list[dict[str, object]] = []
    if classification == "success" and resource_class in {"worldserver_build", "integration_build"}:
        worldserver = worldserver_path
        if worldserver.is_file() and worldserver.read_bytes()[:4] == b"\x7fELF":
            after_stat = worldserver.stat()
            after_hash = sha256_file(worldserver)
            produced_by_ticket = worldserver_before is None or (
                after_stat.st_mtime_ns > int(worldserver_before["mtime_ns"])
                and (
                    after_hash != worldserver_before["sha256"]
                    or after_stat.st_size != int(worldserver_before["size_bytes"])
                )
            )
            if produced_by_ticket:
                output_artifacts.append(
                    {
                        "kind": "worldserver_elf",
                        "path": str(worldserver),
                        "size_bytes": after_stat.st_size,
                        "mtime_ns": after_stat.st_mtime_ns,
                        "sha256": after_hash,
                        "produced_by_ticket": True,
                        "preexisting_artifact": worldserver_before,
                    }
                )
    receipt_without_hash = {
        "schema_version": 2,
        "policy_id": policy["policy_id"],
        "ticket_id": ticket_id,
        "resource_class": resource_class,
        "worktree": str(worktree.resolve()),
        "commit": request_source.get("commit") if isinstance(request_source, dict) else None,
        "worktree_dirty_at_request": ticket["worktree_dirty"],
        "worktree_porcelain_sha256_at_request": ticket["worktree_porcelain_sha256"],
        "source_identity": source_identity,
        "source_identity_stable": source_identity_stable,
        "provenance_reasons": provenance_reasons,
        "command_sha256": command_hash(command),
        "command_arguments_retained": False,
        "queue_sequence": ticket["queue_sequence"],
        "queue_wait_seconds": round(admitted_monotonic - started_wait, 6),
        "admitted_at_utc": admitted_at_utc,
        "ended_at_utc": ended,
        "compiler_job_ceiling": compiler_jobs,
        "linker_job_ceiling": int(policy["parallelism"]["maximum_linker_jobs"]),
        "preflight": preflight,
        "peak_observations": peak_observations(samples),
        "classification": classification,
        "exit_code": returncode,
        "signal": -returncode if returncode < 0 else None,
        "pressure_reasons": terminal_reasons,
        "log_sha256": log_hash,
        "output_artifacts": output_artifacts,
        "artifact_provenance_required": resource_class in {"worldserver_build", "integration_build"},
        "error": error_message,
        "test_mode": os.environ.get("TRINITY_RAID_BUILD_TESTING") == "1",
        "policy_sha256": sha256_bytes(canonical_json(policy)),
    }
    receipt = dict(receipt_without_hash)
    receipt["receipt_sha256"] = sha256_bytes(canonical_json(receipt_without_hash))
    canonical_receipt = paths.receipts / f"{ticket_id}.json"
    atomic_json(canonical_receipt, receipt)
    if receipt_output:
        atomic_json(receipt_output.resolve(), receipt)
    finalize_ticket(paths, ticket_id, receipt)
    mapped_returncode = 75 if classification == "build_resource_abort" else returncode
    if classification == "canceled":
        mapped_returncode = 130
    if classification == "coordinator_error":
        mapped_returncode = 70
    if classification == "build_provenance_abort":
        mapped_returncode = 76
    return mapped_returncode, receipt


def verify_receipt(path: Path, policy: dict, allow_test_mode: bool = False) -> dict:
    receipt = load_json(path)
    required = {
        "receipt_sha256",
        "policy_id",
        "policy_sha256",
        "ticket_id",
        "queue_sequence",
        "worktree",
        "commit",
        "worktree_porcelain_sha256_at_request",
        "source_identity",
        "source_identity_stable",
        "provenance_reasons",
        "command_sha256",
        "classification",
        "compiler_job_ceiling",
        "linker_job_ceiling",
        "peak_observations",
        "log_sha256",
    }
    missing = sorted(required - receipt.keys())
    if missing:
        raise CoordinatorError(f"receipt is missing required fields: {','.join(missing)}")
    claimed = receipt["receipt_sha256"]
    unhashed = dict(receipt)
    del unhashed["receipt_sha256"]
    if sha256_bytes(canonical_json(unhashed)) != claimed:
        raise CoordinatorError("receipt canonical hash mismatch")
    if receipt["policy_id"] != policy["policy_id"]:
        raise CoordinatorError("receipt policy ID mismatch")
    if receipt["policy_sha256"] != sha256_bytes(canonical_json(policy)):
        raise CoordinatorError("receipt policy content hash mismatch")
    if receipt.get("command_arguments_retained") is not False:
        raise CoordinatorError("receipt retained command arguments")
    if receipt.get("schema_version") != 2:
        raise CoordinatorError("legacy receipt cannot satisfy the production source-provenance gate")
    source_identity = receipt.get("source_identity")
    if not isinstance(source_identity, dict):
        raise CoordinatorError("receipt is missing source identity snapshots")
    snapshots = [source_identity.get(stage) for stage in ("request", "admission", "completion")]
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            raise CoordinatorError("receipt source identity snapshot is missing")
        if (not (receipt.get("test_mode") and allow_test_mode)
            and (snapshot.get("clean") is not True or snapshot.get("dirty") is not False)):
            raise CoordinatorError("receipt source identity snapshot is dirty")
        if not isinstance(snapshot.get("commit"), str) or not re.fullmatch(r"[0-9a-f]{40,64}", snapshot["commit"]):
            raise CoordinatorError("receipt source commit is invalid")
        if not isinstance(snapshot.get("tree"), str) or not re.fullmatch(r"[0-9a-f]{40,64}", snapshot["tree"]):
            raise CoordinatorError("receipt source tree is invalid")
        if not isinstance(snapshot.get("porcelain_sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", snapshot["porcelain_sha256"]):
            raise CoordinatorError("receipt source porcelain hash is invalid")
    if not (snapshots[0] == snapshots[1] == snapshots[2]):
        raise CoordinatorError("receipt source identity changed during the coordinated command")
    reconstructed_stable = snapshots[0] == snapshots[1] == snapshots[2] and bool(
        receipt.get("test_mode") and allow_test_mode
        or all(snapshot.get("clean") is True for snapshot in snapshots)
    )
    if receipt.get("source_identity_stable") is not reconstructed_stable:
        raise CoordinatorError("receipt source stability claim does not match reconstructed snapshots")
    provenance_reasons = receipt.get("provenance_reasons")
    if not isinstance(provenance_reasons, list) or any(not isinstance(value, str) for value in provenance_reasons):
        raise CoordinatorError("receipt provenance reasons are invalid")
    if receipt.get("classification") == "success" and (
        not reconstructed_stable or provenance_reasons
    ):
        raise CoordinatorError("successful receipt has invalid source provenance")
    if receipt.get("commit") != snapshots[0]["commit"]:
        raise CoordinatorError("receipt commit does not match source identity")
    if int(receipt["compiler_job_ceiling"]) > int(policy["parallelism"]["maximum_compiler_jobs"]):
        raise CoordinatorError("receipt compiler ceiling exceeds policy")
    if int(receipt["linker_job_ceiling"]) > int(policy["parallelism"]["maximum_linker_jobs"]):
        raise CoordinatorError("receipt linker ceiling exceeds policy")
    if receipt.get("test_mode") and not allow_test_mode:
        raise CoordinatorError("synthetic/test receipt cannot satisfy a production build gate")
    require_worldserver_hash = bool(
        policy.get("mechanical_controls", {}).get("receipt_worldserver_sha256_required")
    )
    if (
        require_worldserver_hash
        and receipt.get("classification") == "success"
        and receipt.get("resource_class") in {"worldserver_build", "integration_build"}
    ):
        artifacts = receipt.get("output_artifacts")
        worldserver = next(
            (
                row for row in artifacts
                if isinstance(row, dict) and row.get("kind") == "worldserver_elf"
            ),
            None,
        ) if isinstance(artifacts, list) else None
        if (
            not worldserver
            or not isinstance(worldserver.get("path"), str)
            or not isinstance(worldserver.get("size_bytes"), int)
            or worldserver["size_bytes"] <= 0
            or not isinstance(worldserver.get("sha256"), str)
            or not re.fullmatch(r"[0-9a-f]{64}", worldserver["sha256"])
            or worldserver.get("produced_by_ticket") is not True
        ):
            raise CoordinatorError("receipt is missing the required worldserver artifact identity")
    return {
        "valid": True,
        "receipt_sha256": claimed,
        "ticket_id": receipt["ticket_id"],
        "classification": receipt["classification"],
        "test_mode": bool(receipt.get("test_mode")),
    }


def cancel_ticket(paths: Paths, ticket_id: str) -> dict:
    with locked_state(paths) as state:
        ticket = state["tickets"].get(ticket_id)
        if not ticket:
            raise CoordinatorError(f"unknown ticket {ticket_id}")
        if ticket["state"] in TERMINAL_STATES:
            return ticket
        if state.get("active") == ticket_id:
            ticket["state"] = "cancel_requested"
            ticket["cancel_requested_at_utc"] = utc_now()
        else:
            ticket["state"] = "canceled"
            ticket["completion"] = {"classification": "canceled", "ended_at_utc": utc_now()}
            state["queue"] = [value for value in state["queue"] if value != ticket_id]
        return dict(ticket)


def status(paths: Paths, recover: bool = True) -> dict:
    with locked_state(paths) as state:
        events = recover_stale_locked(state, paths) if recover else []
        return {
            "schema_version": STATE_VERSION,
            "active": state["active"],
            "queue": list(state["queue"]),
            "tickets": dict(state["tickets"]),
            "recovery_events": events,
        }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--worktree", type=Path, default=Path.cwd())
    result.add_argument("--policy", type=Path, default=DEFAULT_POLICY)
    commands = result.add_subparsers(dest="action", required=True)
    enqueue_parser = commands.add_parser("enqueue")
    enqueue_parser.add_argument("--resource-class", default="worldserver_build")
    run_parser = commands.add_parser("run")
    run_parser.add_argument("--resource-class", default="worldserver_build")
    run_parser.add_argument("--ticket")
    run_parser.add_argument("--receipt", type=Path)
    run_parser.add_argument("--admission-timeout-sec", type=float)
    run_parser.add_argument("command", nargs=argparse.REMAINDER)
    status_parser = commands.add_parser("status")
    status_parser.add_argument("--no-recover", action="store_true")
    cancel_parser = commands.add_parser("cancel")
    cancel_parser.add_argument("ticket")
    commands.add_parser("recover")
    verify_parser = commands.add_parser("verify")
    verify_parser.add_argument("receipt", type=Path)
    verify_parser.add_argument("--allow-test-mode", action="store_true")
    return result


def main(arguments: Sequence[str] | None = None) -> int:
    args = parser().parse_args(arguments)
    try:
        worktree = args.worktree.resolve()
        policy = load_json(args.policy.resolve())
        paths = Paths.for_worktree(worktree)
        if args.action == "enqueue":
            ticket = new_ticket(worktree, args.resource_class)
            enqueue(paths, ticket)
            print(json.dumps({"ticket_id": ticket["ticket_id"], "state": "queued"}, sort_keys=True))
            return 0
        if args.action == "run":
            command = list(args.command)
            if command and command[0] == "--":
                command = command[1:]
            returncode, receipt = run_ticket(
                worktree,
                policy,
                args.resource_class,
                command,
                args.ticket,
                args.receipt,
                args.admission_timeout_sec,
            )
            print(json.dumps(receipt, indent=2, sort_keys=True))
            return returncode
        if args.action == "status":
            print(json.dumps(status(paths, recover=not args.no_recover), indent=2, sort_keys=True))
            return 0
        if args.action == "cancel":
            print(json.dumps(cancel_ticket(paths, args.ticket), indent=2, sort_keys=True))
            return 0
        if args.action == "recover":
            report = status(paths, recover=True)
            print(json.dumps(report["recovery_events"], indent=2, sort_keys=True))
            return 0
        if args.action == "verify":
            print(
                json.dumps(
                    verify_receipt(args.receipt.resolve(), policy, args.allow_test_mode),
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0
    except CoordinatorError as error:
        print(f"queued_build: {error}", file=sys.stderr)
        return 64
    raise AssertionError(args.action)


if __name__ == "__main__":
    raise SystemExit(main())
