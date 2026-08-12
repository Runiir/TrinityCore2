from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
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


def report_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def zero_bot_status_observed(log_bytes: bytes) -> bool:
    statuses = re.findall(rb"\{[^\r\n]*\"action\":\"botauto_status\"[^\r\n]*\}", log_bytes)
    return any(
        re.search(rb'\"bots\"\s*:\s*0(?:\D|$)', status)
        and re.search(rb'\"lease_count\"\s*:\s*0(?:\D|$)', status)
        for status in statuses
    )


def tracked_identity() -> dict[str, Any]:
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    listed = subprocess.check_output(
        ["git", "ls-files", "--modified", "--others", "--exclude-standard", "-z"], cwd=ROOT
    ).split(b"\0")
    files: list[dict[str, Any]] = []
    for raw in sorted(row for row in listed if row):
        relative = raw.decode("utf-8", errors="surrogateescape")
        path = ROOT / relative
        files.append(
            {
                "path": relative,
                "sha256": sha256_file(path) if path.is_file() else None,
            }
        )
    encoded = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    return {"head": head, "dirty_file_count": len(files), "dirty_content_sha256": hashlib.sha256(encoded).hexdigest()}


def meminfo() -> dict[str, int]:
    values: dict[str, int] = {}
    for line in Path("/proc/meminfo").read_text(encoding="utf-8").splitlines():
        key, value = line.split(":", 1)
        values[key] = int(value.strip().split()[0]) * 1024
    return values


def memory_psi() -> dict[str, float]:
    result = {"some_avg10": 0.0, "full_avg10": 0.0}
    for line in Path("/proc/pressure/memory").read_text(encoding="utf-8").splitlines():
        fields = line.split()
        if fields and fields[0] in {"some", "full"}:
            result[f"{fields[0]}_avg10"] = float(dict(field.split("=", 1) for field in fields[1:])["avg10"])
    return result


def process_sample(pid: int) -> dict[str, Any]:
    stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8").split()
    status: dict[str, str] = {}
    for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            status[key] = value.strip()
    memory = meminfo()
    psi = memory_psi()
    return {
        "monotonic_sec": time.monotonic(),
        "process_cpu_ticks": int(stat[13]) + int(stat[14]),
        "process_rss_bytes": int(status["VmRSS"].split()[0]) * 1024,
        "host_load_1m": os.getloadavg()[0],
        "memory_available_bytes": memory["MemAvailable"],
        "swap_free_bytes": memory["SwapFree"],
        "memory_psi_some_avg10": psi["some_avg10"],
        "memory_psi_full_avg10": psi["full_avg10"],
    }


def mysql_probe(container: str) -> dict[str, Any]:
    started = time.monotonic()
    completed = subprocess.run(
        [
            "docker",
            "exec",
            container,
            "sh",
            "-lc",
            'mariadb -uroot -p"$MARIADB_ROOT_PASSWORD" --batch --skip-column-names -e "SELECT 1"',
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        timeout=10,
        check=False,
    )
    return {
        "latency_ms": round((time.monotonic() - started) * 1000, 3),
        "ok": completed.returncode == 0 and completed.stdout.strip() == "1",
    }


def wait_for_prompt(process: subprocess.Popen[bytes], log_path: Path, timeout_sec: int) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"worldserver exited before readiness with code {process.returncode}")
        if log_path.exists() and b"TC>" in log_path.read_bytes()[-65536:]:
            return
        time.sleep(0.25)
    raise RuntimeError("worldserver readiness prompt timed out")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--observe-sec", type=int, default=30)
    parser.add_argument("--startup-timeout-sec", type=int, default=120)
    parser.add_argument("--mysql-container", default="trinity-cata-db")
    args = parser.parse_args()

    binary = args.binary.resolve()
    config = args.config.resolve()
    output = args.output.resolve()
    if args.observe_sec < 10:
        raise SystemExit("--observe-sec must be at least 10")
    if not binary.is_file() or not config.is_file():
        raise SystemExit("binary and config must exist")
    if output.exists():
        raise SystemExit("output already exists; baseline artifacts are immutable")
    if subprocess.run(["pgrep", "-x", "worldserver"], stdout=subprocess.DEVNULL, check=False).returncode == 0:
        raise SystemExit("a worldserver process already exists")

    before = tracked_identity()
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    samples: list[dict[str, Any]] = []
    mysql_samples: list[dict[str, Any]] = []
    with tempfile.NamedTemporaryFile(prefix="raid-no-bots-worldserver-", suffix=".log", delete=False) as log:
        log_path = Path(log.name)
        process = subprocess.Popen(
            [str(binary), "--config", str(config)],
            cwd=ROOT,
            stdin=subprocess.PIPE,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        try:
            wait_for_prompt(process, log_path, args.startup_timeout_sec)
            assert process.stdin is not None
            process.stdin.write(b"botauto status\nserver info\n")
            process.stdin.flush()
            deadline = time.monotonic() + args.observe_sec
            next_db = 0.0
            while time.monotonic() < deadline:
                samples.append(process_sample(process.pid))
                if time.monotonic() >= next_db:
                    mysql_samples.append(mysql_probe(args.mysql_container))
                    next_db = time.monotonic() + 5.0
                time.sleep(1.0)
            process.stdin.write(b"botauto status\nserver exit\n")
            process.stdin.flush()
            process.wait(timeout=30)
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

    after = tracked_identity()
    tick_rate = os.sysconf(os.sysconf_names["SC_CLK_TCK"])
    elapsed = samples[-1]["monotonic_sec"] - samples[0]["monotonic_sec"] if len(samples) > 1 else 0.0
    cpu_ticks = samples[-1]["process_cpu_ticks"] - samples[0]["process_cpu_ticks"] if len(samples) > 1 else 0
    active_bots_zero = zero_bot_status_observed(log_bytes)
    success = process.returncode == 0 and before == after and active_bots_zero and all(row["ok"] for row in mysql_samples)
    report = {
        "schema_version": 1,
        "baseline_id": "cata_raid_phase0_no_bots_worldserver_v1",
        "classification": "success" if success else "infrastructure_abort",
        "started_at_utc": started_utc,
        "observe_sec": args.observe_sec,
        "identity": before,
        "identity_stable_during_run": before == after,
        "binary": {"path": report_path(binary), "sha256": sha256_file(binary)},
        "config": {"path": report_path(config), "sha256": sha256_file(config)},
        "worldserver": {
            "exit_code": process.returncode,
            "active_bots_zero_observed": active_bots_zero,
            "log_sha256": hashlib.sha256(log_bytes).hexdigest(),
            "log_bytes": len(log_bytes),
            "sample_count": len(samples),
            "mean_cpu_percent_one_core": round((cpu_ticks / tick_rate) / elapsed * 100, 3) if elapsed else None,
            "maximum_rss_bytes": max(row["process_rss_bytes"] for row in samples),
        },
        "host": {
            "logical_cpus": os.cpu_count(),
            "maximum_load_1m": max(row["host_load_1m"] for row in samples),
            "minimum_memory_available_bytes": min(row["memory_available_bytes"] for row in samples),
            "minimum_swap_free_bytes": min(row["swap_free_bytes"] for row in samples),
            "maximum_memory_psi_some_avg10": max(row["memory_psi_some_avg10"] for row in samples),
            "maximum_memory_psi_full_avg10": max(row["memory_psi_full_avg10"] for row in samples),
        },
        "mysql": {
            "container": args.mysql_container,
            "probe_count": len(mysql_samples),
            "all_probes_ok": all(row["ok"] for row in mysql_samples),
            "maximum_latency_ms": max(row["latency_ms"] for row in mysql_samples),
        },
        "samples_retained": False,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())
