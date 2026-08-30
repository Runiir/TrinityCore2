from __future__ import annotations

from pathlib import Path
import subprocess
import time
from typing import Any

try:
    from tools.raid_program.capture_environment_validation import sha256_file
except ModuleNotFoundError:
    from capture_environment_validation import sha256_file


def wait_for_prompt(process: subprocess.Popen[bytes], log_path: Path, timeout_sec: int) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"worldserver exited before readiness with code {process.returncode}")
        if log_path.exists() and b"TC>" in log_path.read_bytes()[-65536:]:
            return
        time.sleep(0.25)
    raise RuntimeError("worldserver readiness prompt timed out")


def _artifact_record(path: Path, kind: str) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"immutable artifact missing: {path}")
    return {
        "kind": kind,
        "path": str(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "immutable": True,
    }


def bounded_native_shutdown(
    process: subprocess.Popen[bytes], wait_seconds: float,
) -> dict[str, Any]:
    """Request native cleanup and wait for the child within a hard budget.

    The caller still owns process-group escalation after this function
    returns.  Keeping the native request separate makes the operator-abort
    path testable without starting a worldserver and ensures repeated Ctrl-C
    cannot turn cleanup into an uncaught traceback.
    """
    result: dict[str, Any] = {
        "commands_sent": False,
        "operator_interrupted": False,
        "error": None,
        "exited": process.poll() is not None,
        "wait_seconds": wait_seconds,
    }
    if result["exited"]:
        return result
    if process.stdin is None:
        result["error"] = "native_shutdown_stdin_unavailable"
        return result
    try:
        process.stdin.write(b"botauto stop\nbotauto status\nserver exit\n")
        process.stdin.flush()
        result["commands_sent"] = True
    except (BrokenPipeError, OSError) as error:
        result["error"] = f"native_shutdown_write:{type(error).__name__}:{error}"
        return result
    deadline = time.monotonic() + wait_seconds
    while process.poll() is None and time.monotonic() < deadline:
        try:
            process.wait(timeout=min(0.25, max(0.01, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            continue
        except KeyboardInterrupt:
            result["operator_interrupted"] = True
            continue
    result["exited"] = process.poll() is not None
    if not result["exited"]:
        result["error"] = f"native_shutdown_timeout:{wait_seconds:g}s"
    return result
