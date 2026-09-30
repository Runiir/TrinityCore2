"""pytest plugin of tools.raid_program.test_baseline: one JSON line per test outcome.

test_baseline copies this file to a scratch directory as ``raid_test_baseline_plugin.py`` and loads it
with ``-p raid_test_baseline_plugin`` (never from the tree under test, so an export of an older commit
needs no copy of it). Lines go to ``$RAID_TEST_BASELINE_OUTPUT`` as they happen, so a chunk killed by
its timeout keeps every finished result and names the test that was still running:

    {"event": "start", "nodeid": ...}
    {"event": "result", "nodeid": ..., "outcome": "passed|failed|skipped", "when": ..., "message": ...}
    {"event": "finish", "exitstatus": int}

A collection error is a failed result whose nodeid is the module path and ``when`` is ``collect``.
The finish line is written last (``trylast``): when another plugin's or conftest's sessionfinish
raises first it is missing, and test_baseline treats the chunk as not having run cleanly.
"""
from __future__ import annotations

import json
import os

import pytest

_OUTCOMES: dict[str, str] = {}


def _write(row: dict) -> None:
    path = os.environ.get("RAID_TEST_BASELINE_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True, default=str) + "\n")


def _message(report) -> str:
    longrepr = report.longrepr
    crash = getattr(longrepr, "reprcrash", None)
    if crash is not None and getattr(crash, "message", None):
        return str(crash.message)
    if isinstance(longrepr, tuple) and len(longrepr) == 3:  # skip reports: (path, lineno, reason)
        return str(longrepr[2])
    lines = [line for line in str(longrepr or "").splitlines() if line.strip()]
    errors = [line[1:].strip() for line in lines if line.startswith("E ")]
    return errors[0] if errors else (lines[-1].strip() if lines else "")


def pytest_runtest_logstart(nodeid, location):
    _write({"event": "start", "nodeid": nodeid})


def pytest_runtest_logreport(report):
    previous = _OUTCOMES.get(report.nodeid)
    if report.failed:
        outcome = "failed"
    elif report.skipped and report.when in ("setup", "call"):
        outcome = "skipped"
    else:
        outcome = "passed"
    if previous == "failed" or (previous == "skipped" and outcome == "passed"):
        return  # the first failure (or skip) of a test decides it; teardown passes never undo it
    if outcome == "passed" and report.when != "teardown":
        _OUTCOMES.setdefault(report.nodeid, "passed")
        return  # a setup or call pass is final only after teardown
    _OUTCOMES[report.nodeid] = outcome
    _write({"event": "result", "nodeid": report.nodeid, "outcome": outcome, "when": report.when,
            "message": _message(report) if outcome != "passed" else ""})


def pytest_collectreport(report):
    if report.failed:
        _write({"event": "result", "nodeid": report.nodeid or "<collection>", "outcome": "failed",
                "when": "collect", "message": _message(report)})


@pytest.hookimpl(trylast=True)
def pytest_sessionfinish(session, exitstatus):
    _write({"event": "finish", "exitstatus": int(exitstatus)})
