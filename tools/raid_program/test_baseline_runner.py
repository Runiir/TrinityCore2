"""Process runner of tools.raid_program.test_baseline: ``pytest.main`` plus a completion marker.

test_baseline copies this file next to its plugin as ``raid_test_baseline_runner.py`` and starts every
pytest chunk as ``python -m raid_test_baseline_runner <pytest args>`` (``python -m pytest`` is
``pytest.main`` too, so collection and imports are unchanged). The runner

* dies with its supervisor: PR_SET_PDEATHSIG=SIGKILL, so a supervisor killed even by SIGKILL does not
  leave the chunk running (the chunk runs in its own session, out of reach of the supervisor's group);
* runs ``pytest.main`` and treats every exception that escapes it as a failure: a sessionfinish
  hookwrapper raising after ``yield``, a failing trylast sessionfinish or ``pytest_unconfigure`` hook, a
  hook calling ``sys.exit``, an interrupt. It prints the traceback, appends an ``escaped`` line to
  ``$RAID_TEST_BASELINE_OUTPUT`` and exits EXIT_ESCAPED;
* then shuts down the normal way (``sys.exit``: non-daemon threads are joined, then the atexit handlers
  run, including pytest's release of its numbered temp-dir lock, without which pytest never prunes
  that directory). The marker writer is the first atexit handler registered, so it runs last; an exit
  handler or thread that failed during shutdown (seen through sys.unraisablehook and
  threading.excepthook) is reported as ``exit_error`` instead of the marker;
* otherwise appends ``{"event": "complete", "exitstatus": code}`` as its very last act and leaves with
  ``os._exit(code)``.

A chunk without the ``complete`` line did not finish cleanly, whatever its exit code.
"""
from __future__ import annotations

import atexit
import json
import os
import sys
import threading
import traceback

EXIT_ESCAPED = 70  # EX_SOFTWARE: an exception escaped pytest.main
PR_SET_PDEATHSIG = 1


def _write(row: dict) -> None:
    path = os.environ.get("RAID_TEST_BASELINE_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _die_with_supervisor() -> None:
    """SIGKILL this process when the supervisor that started it dies (Linux)."""
    try:
        import ctypes
        import signal
        ctypes.CDLL(None, use_errno=True).prctl(PR_SET_PDEATHSIG, int(signal.SIGKILL), 0, 0, 0)
    except (OSError, AttributeError):
        return
    expected = os.environ.get("RAID_TEST_BASELINE_SUPERVISOR")
    if expected and os.getppid() != int(expected):  # the supervisor died before prctl took effect
        os._exit(EXIT_ESCAPED)


_STATE: dict = {"code": None, "errors": []}


def _record(error: str) -> None:
    _STATE["errors"].append(error[:300])


def _fail(event: str, error: str) -> None:
    _write({"event": event, "error": error[:300]})
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    finally:
        os._exit(EXIT_ESCAPED)


def _final() -> None:
    """Registered first, so atexit runs it last: after the normal join of non-daemon threads and every
    other exit handler. Writes the marker as the process's very last act."""
    if _STATE["code"] is None:  # pytest.main never returned; the escape path already reported it
        return
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except BaseException as error:  # noqa: BLE001
        _record(f"flush: {type(error).__name__}: {error}")
    if _STATE["errors"]:
        _fail("exit_error", "; ".join(_STATE["errors"]))
    _write({"event": "complete", "exitstatus": _STATE["code"]})
    os._exit(_STATE["code"])


def main(argv: list[str]) -> None:
    _die_with_supervisor()
    atexit.register(_final)
    try:
        import pytest
        code = int(pytest.main(argv))
    except BaseException as error:  # noqa: BLE001 - anything escaping pytest is a chunk failure
        traceback.print_exc()
        _fail("escaped", f"{type(error).__name__}: {error}")
    _STATE["code"] = code
    unraisable, thread_hook = sys.unraisablehook, threading.excepthook

    def record_unraisable(info) -> None:  # atexit reports failing handlers here
        _record(f"{type(info.exc_value).__name__}: {info.exc_value}")
        unraisable(info)

    def record_thread(args) -> None:  # a thread dying with an exception after the session
        _record(f"thread {getattr(args.thread, 'name', '?')}: {args.exc_type.__name__}: {args.exc_value}")
        thread_hook(args)

    sys.unraisablehook, threading.excepthook = record_unraisable, record_thread
    sys.exit(code)  # normal shutdown: join non-daemon threads, run atexit handlers, _final last


if __name__ == "__main__":
    main(sys.argv[1:])
