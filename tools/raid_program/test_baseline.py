"""Known test failures: the suite's failures at a commit, and a check of a run against them.

    pixi run python -m tools.raid_program.test_baseline check [--jobs N] [--json] [--verbose] [-- PYTEST ARGS...]
    pixi run python -m tools.raid_program.test_baseline refresh [--jobs N] [--runs 2] [--keep-export]

``check`` runs pytest in this checkout (the whole suite in parallel file chunks when no pytest
arguments are given, otherwise one pytest process with exactly those arguments) and sorts every
failure against experiments/configs/known_test_failures_v1.json:

    new_failures    not in the baseline, or failing with a different normalized reason
    known_failures  in the baseline with the same normalized reason (its export reason, or the reason the
                    refresh saw when it reran the failure in the checkout)
    fixed           in the baseline and passed in this run (only tests that ran are listed)
    environment_only_passed
                    baseline failures marked environment_only that passed here, as they always do in a
                    checkout (they failed in the export only); informational
    flaky           excluded from the baseline because two baseline runs disagreed, failing now with one
                    of the reasons those runs saw; a flaky test failing for another reason is new

Exit codes: 0 clean; 1 new failures; 2 pytest produced no results; 3 pytest did not run cleanly
(listed under ``pytest_errors``; the rules are in test_baseline_chunks: a timeout, a signal, an
exit code other than 0 or 1, no results file, a missing session-finish or runner-completion marker,
an exception that escaped ``pytest.main`` such as a failing sessionfinish hookwrapper, trylast hook or
``pytest_unconfigure``, inconsistent statuses, or an INTERNALERROR or traceback on the chunk's
stderr); 3 wins over 1 because the results are then incomplete; 128 + N when stopped by signal N
(SIGTERM, SIGINT, SIGHUP), after stopping its pytest chunks, reaping their leftovers and removing its
scratch. A baseline from another commit is still used, with a warning that it may be stale; without
.git (a git archive export) HEAD is unknown and so is staleness.

Known limitation: a supervisor killed by SIGKILL takes its pytest chunks down (PR_SET_PDEATHSIG), but
test descendants in their own session (e.g. a detached fake worldserver) survive it; every check and
refresh reaps such orphans at its start through the markers they inherited (test_baseline_chunks).

``refresh`` regenerates the baseline for HEAD from a clean ``git archive HEAD`` export under
~/.cache/trinity-test-baseline/<sha12>-<run id>/tree; every invocation gets its own run id (a uuid),
so two refreshes of one commit never share an export, and each reaps only processes carrying its own
``RAID_TEST_BASELINE_RUN`` marker. The export gets the untracked local inputs the tests
read from this checkout: LOCAL_INPUT_DIRS (build, data with the DBC files, models, and .pixi so a
test's own ``pixi run`` reuses this environment) as read-only-by-convention symlinks, copies of
LOCAL_INPUT_FILES (the ignored trinity-*-test.conf files), and every DVC
output (dvc.lock stage outs and ``*.dvc`` outs, e.g. the dataset files and
dataset/world_knowledge/trainers.jsonl) present here but absent from the export, copied when at most
COPY_LIMIT_BYTES (runtime-asset readers refuse symlinked paths) and symlinked when larger. The suite
runs ``--runs`` times (default 2) with ``--jobs`` parallel pytest processes (default: CPUs - 4, so
four stay free); a test is a known failure only when it failed in every run with the same normalized
reason, and one whose outcome or reason differs between runs is recorded under ``flaky_excluded``
with the failure reasons it showed. A run that did not complete cleanly (exit code 3 rules above)
writes no baseline and exits 3. Known failures are rerun once in this checkout: those that pass here
are ``environment_only`` (they fail in the export because it lacks git metadata or another local
input). When the checkout is clean at the baseline commit (HEAD is that commit, no tracked
modifications and no untracked ``*.py``) both before and after the rerun, with the same file digest
(checkout_fingerprint: path, mtime and size of every tracked file and untracked ``*.py``, so an edit
made during the rerun, even one reverted, is seen), a known failure that fails here for another reason
also records it as ``checkout_reason``; otherwise that reason could come from an uncommitted
regression, so none is recorded and ``method.checkout_state`` says why. The export is deleted
afterwards unless ``--keep-export``.

A normalized reason is the first line of the failure's crash message (prefixed by the phase when it
is not the test call), with checkout, export and home paths, pytest temp paths, hex ids, addresses,
timestamps and second durations replaced by placeholders.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterable

from tools.raid_program.test_baseline_chunks import (  # noqa: F401 - re-exported for callers and tests
    CHUNK_TIMEOUT_SEC, EXIT_NAMES, OK_EXIT_CODES, PLUGIN_NAME, PYTEST_BASE, RUN_ENV, Terminated, chunk_problem,
    cleanup_on_exit, new_run_id, parse_results, reap_leftovers, reap_orphans, run_pytest, signals_blocked,
    terminate_on_signals,
)

ROOT = Path(__file__).resolve().parents[2]
SCHEMA = "known_test_failures_v1"
BASELINE = Path("experiments/configs/known_test_failures_v1.json")
SCRATCH = Path.home() / ".cache" / "trinity-test-baseline"
FREE_CPUS = 4
LOCAL_INPUT_DIRS = ("build", "data", "models", ".pixi")
LOCAL_INPUT_FILES = ("trinity-worldserver-test.conf", "trinity-authserver-test.conf")  # ignored local configs
CHUNKS_PER_JOB = 6
COPY_LIMIT_BYTES = 64 * 1024 * 1024  # DVC outputs up to this size are copied, larger ones symlinked
REASON_LIMIT = 240
EXIT_PYTEST_ERROR = 3


def default_jobs() -> int:
    return max(1, (os.cpu_count() or 1) - FREE_CPUS)


def _git(*args: str, cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=cwd or ROOT, check=True, capture_output=True,
                          text=True).stdout.strip()


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# --- reasons ------------------------------------------------------------------------------------------

_PATTERNS = (
    (re.compile(r"/tmp/pytest-of-[^/\s]+/pytest-\d+[^\s'\"),]*"), "<tmp>"),
    (re.compile(r"/tmp/[^\s'\"),]+"), "<tmp>"),
    (re.compile(r"0x[0-9a-fA-F]+"), "0x<addr>"),
    (re.compile(r"\b[0-9a-f]{12,}\b"), "<hex>"),
    (re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?Z?"), "<time>"),
    (re.compile(r"\b\d+\.\d+ ?s(?:ec)?\b"), "<secs>"),
    (re.compile(r"\bpid[ =:]+\d+"), "pid=<n>"),
    (re.compile(r"\s+"), " "),
)


def normalize_reason(message: str, when: str = "call", roots: Iterable[Path | str] = ()) -> str:
    """Stable identity of a failure: first message line, environment-specific parts replaced."""
    lines = [line for line in str(message or "").splitlines() if line.strip()]
    text = lines[0] if lines else "no message"
    for root in sorted({str(root) for root in (*roots, ROOT) if str(root)}, key=len, reverse=True):
        text = text.replace(root, "<root>")
    text = text.replace(str(Path.home()), "~")
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    text = text.strip()[:REASON_LIMIT]
    return text if when in ("call", "", None) else f"{when}: {text}"


# --- running pytest -----------------------------------------------------------------------------------

def suite_files(tree: Path) -> list[str]:
    """Test modules under tests/ (pytest's default python_files), relative to the tree."""
    found = {path.relative_to(tree).as_posix() for pattern in ("test_*.py", "*_test.py")
             for path in (tree / "tests").rglob(pattern) if "__pycache__" not in path.parts}
    return sorted(found)


def make_chunks(tree: Path, files: list[str], jobs: int) -> list[list[str]]:
    """Consecutive file groups of similar size (test functions + 1), heaviest first; deterministic."""
    weights = {name: (tree / name).read_text(errors="replace").count("def test_") + 1 for name in files}
    target = max(1.0, sum(weights.values()) / max(1, jobs * CHUNKS_PER_JOB))
    chunks, current, size = [], [], 0
    for name in files:
        current.append(name)
        size += weights[name]
        if size >= target:
            chunks.append(current)
            current, size = [], 0
    if current:
        chunks.append(current)
    return sorted(chunks, key=lambda chunk: -sum(weights[name] for name in chunk))


# --- baseline -----------------------------------------------------------------------------------------

def failure_reasons(results: dict[str, dict[str, Any]], roots: Iterable[Path]) -> dict[str, dict[str, str]]:
    roots = list(roots)
    return {nodeid: {"reason": normalize_reason(row.get("message") or "", row.get("when") or "call", roots),
                     "when": row.get("when") or "call"}
            for nodeid, row in results.items() if row.get("outcome") == "failed"}


def stable_failures(runs: list[dict[str, dict[str, Any]]], roots: Iterable[Path]
                    ) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, list[str]]]]:
    """(failures identical in every run, flaky: nodeid -> {"runs": per-run outcome or reason,
    "failure_reasons": the distinct normalized reasons of the runs where it failed})."""
    roots = list(roots)
    reasons = [failure_reasons(run, roots) for run in runs]
    stable, flaky = {}, {}
    for nodeid in sorted(set().union(*reasons)):
        seen = [row[nodeid]["reason"] if nodeid in row else (runs[index].get(nodeid) or {}).get("outcome", "not run")
                for index, row in enumerate(reasons)]
        if all(nodeid in row for row in reasons) and len(set(seen)) == 1:
            stable[nodeid] = reasons[0][nodeid]
        else:
            flaky[nodeid] = {"runs": seen,
                             "failure_reasons": sorted({row[nodeid]["reason"] for row in reasons if nodeid in row})}
    return stable, flaky


def flaky_reasons(entry: Any) -> set[str]:
    """The failure reasons a flaky_excluded entry allows (older baselines stored only the per-run list)."""
    if isinstance(entry, dict):
        return set(entry.get("failure_reasons") or [])
    return {value for value in entry or [] if value not in ("passed", "skipped", "not run")}


def _dvc_outputs(tree: Path) -> list[str]:
    import yaml
    outs = []
    lock = tree / "dvc.lock"
    if lock.exists():
        for stage in (yaml.safe_load(lock.read_text()) or {}).get("stages", {}).values():
            outs += [str(row["path"]) for row in stage.get("outs") or [] if row.get("path")]
    for pointer in tree.rglob("*.dvc"):
        if ".dvc" in pointer.relative_to(tree).parts[:1]:
            continue
        try:
            document = yaml.safe_load(pointer.read_text()) or {}
        except (OSError, yaml.YAMLError):
            continue
        base = pointer.parent.relative_to(tree)
        outs += [(base / str(row["path"])).as_posix() for row in document.get("outs") or [] if row.get("path")]
    return sorted(set(outs))


def _size(path: Path, limit: int) -> int:
    """Bytes under ``path`` without following symlinks, stopping once past ``limit``."""
    if not path.is_dir() or path.is_symlink():
        return path.lstat().st_size
    total = 0
    for folder, _, names in os.walk(path):
        for name in names:
            total += os.lstat(os.path.join(folder, name)).st_size
            if total > limit:
                return total
    return total


def link_local_inputs(tree: Path, source: Path | None = None) -> list[dict[str, str]]:
    """Bring the untracked inputs the tests read from ``source`` into the export.

    LOCAL_INPUT_DIRS are symlinked and LOCAL_INPUT_FILES (the ignored test configs) copied. A DVC
    output is copied when it holds at most COPY_LIMIT_BYTES (runtime-asset readers refuse symlinked
    paths, as the checkout never has them) and symlinked otherwise. Returns ``{"path", "mode"}`` per input, in order.
    """
    source = source or ROOT
    brought: list[dict[str, str]] = []
    for name in LOCAL_INPUT_DIRS:
        if (source / name).exists() and not (tree / name).exists():
            (tree / name).symlink_to(source / name)
            brought.append({"path": name, "mode": "symlink"})
    for name in LOCAL_INPUT_FILES:
        if (source / name).is_file() and not os.path.lexists(tree / name):
            shutil.copy2(source / name, tree / name)
            brought.append({"path": name, "mode": "copy"})
    top = [row["path"] for row in brought]
    for relative in _dvc_outputs(tree):
        target, origin = tree / relative, source / relative
        if not origin.exists() or os.path.lexists(target) or any(relative.startswith(f"{name}/") for name in top):
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if _size(origin, COPY_LIMIT_BYTES) <= COPY_LIMIT_BYTES:
            if origin.is_dir() and not origin.is_symlink():
                shutil.copytree(origin, target, symlinks=True)
            else:
                shutil.copy2(origin, target, follow_symlinks=False)
            brought.append({"path": relative, "mode": "copy"})
        else:
            target.symlink_to(origin)
            brought.append({"path": relative, "mode": "symlink"})
    return brought


def export_head(scratch: Path, commit: str) -> Path:
    tree = scratch / "tree"
    if tree.exists():
        shutil.rmtree(tree)
    tree.mkdir(parents=True)
    archive = subprocess.Popen(["git", "archive", commit], cwd=ROOT, stdout=subprocess.PIPE)
    subprocess.run(["tar", "-x", "-C", str(tree)], stdin=archive.stdout, check=True)
    archive.stdout.close()
    if archive.wait() != 0:
        raise SystemExit(f"git archive {commit} failed")
    return tree


def _groups_by_file(nodeids: Iterable[str], per_group: int = 60) -> list[list[str]]:
    by_file: dict[str, list[str]] = {}
    for nodeid in sorted(nodeids):
        by_file.setdefault(nodeid.split("::", 1)[0], []).append(nodeid)
    groups, current = [], []
    for ids in by_file.values():
        current += ids
        if len(current) >= per_group:
            groups.append(current)
            current = []
    return groups + ([current] if current else [])


def _counts(results: dict[str, dict[str, Any]]) -> dict[str, int]:
    counts = {"tests": len(results), "passed": 0, "failed": 0, "skipped": 0}
    for row in results.values():
        counts[row.get("outcome") if row.get("outcome") in counts else "failed"] += 1
    return counts


def checkout_fingerprint(commit: str) -> dict[str, Any]:
    """This checkout's state around the known-failure rerun.

    ``clean``: HEAD is ``commit``, no tracked modification and no untracked ``*.py``. ``files_sha256``
    digests the path, mtime and size of every tracked file and untracked ``*.py``, so an edit made and
    reverted between two samples still changes it.
    """
    head = _git("rev-parse", "HEAD")
    tracked = [line for line in _git("status", "--porcelain", "--untracked-files=no").splitlines() if line.strip()]
    untracked = sorted(line[3:] for line in _git("status", "--porcelain", "--untracked-files=all").splitlines()
                       if line.startswith("?? ") and line.rstrip('"').endswith(".py"))
    digest = hashlib.sha256()
    for name in sorted({name for name in _git("ls-files", "-z").split("\0") if name} | set(untracked)):
        try:
            stat = os.lstat(ROOT / name)
            digest.update(f"{name}\0{stat.st_mtime_ns}\0{stat.st_size}\n".encode())
        except OSError:
            digest.update(f"{name}\0missing\n".encode())
    return {"clean": head == commit and not tracked and not untracked, "head": head,
            "tracked_changes": len(tracked), "untracked_python_files": len(untracked),
            "files_sha256": digest.hexdigest()}


def _report_errors(errors: list[dict[str, Any]], what: str) -> None:
    print(f"{what}: {len(errors)} pytest chunk(s) did not run cleanly:", file=sys.stderr)
    for row in errors:
        print(f"  {row['label']} chunk {row['chunk']} {' '.join(row['args'])}: {row['problem']} (log {row['log']})",
              file=sys.stderr)


def refresh(args: argparse.Namespace) -> int:
    commit = _git("rev-parse", "HEAD")
    run_id = new_run_id()
    scratch = Path(args.scratch).expanduser() / f"{commit[:12]}-{run_id}"
    jobs = args.jobs or default_jobs()
    print(f"refresh: exporting {commit[:12]} to {scratch / 'tree'}", file=sys.stderr, flush=True)
    runs, meta, errors, checkout = [], [], [], {}
    with cleanup_on_exit(run_id, scratch, args.keep_export, "refresh"):
        tree = export_head(scratch, commit)
        inputs = link_local_inputs(tree)
        chunks = make_chunks(tree, suite_files(tree), jobs)
        roots = [tree, ROOT]
        for number in range(1, args.runs + 1):
            print(f"refresh: run {number}/{args.runs}, {len(chunks)} chunks, {jobs} jobs", file=sys.stderr, flush=True)
            outcome = run_pytest(tree, chunks, jobs, scratch / f"run{number}", timeout=args.chunk_timeout,
                                 label=f"run{number}", run_id=run_id)
            runs.append(outcome["results"])
            errors += outcome["errors"]
            meta.append({key: outcome[key] for key in ("seconds", "timed_out_chunks")} | _counts(outcome["results"]))
        stable, flaky = stable_failures(runs, roots)
        before = checkout_fingerprint(commit)
        if stable and not errors:
            print(f"refresh: rerunning {len(stable)} known failures in {ROOT} (checkout "
                  f"{'clean' if before['clean'] else 'dirty'})", file=sys.stderr, flush=True)
            outcome = run_pytest(ROOT, _groups_by_file(stable), jobs, scratch / "checkout",
                                 timeout=args.chunk_timeout, label="checkout", run_id=run_id)
            checkout = outcome["results"]
            errors += outcome["errors"]
        after = checkout_fingerprint(commit)
    if errors:
        _report_errors(errors, "refresh")
        print("refresh: no baseline written; fix the pytest errors and refresh again", file=sys.stderr)
        return EXIT_PYTEST_ERROR
    # A rerun reason is trusted only from a checkout clean at the commit before and after the rerun and
    # untouched in between (same HEAD and file digest): otherwise it may be an uncommitted regression.
    trusted = before["clean"] and after["clean"] and before == after
    failures = {}
    here = failure_reasons(checkout, [ROOT]) if trusted else {}
    for nodeid, row in stable.items():
        passed_here = (checkout.get(nodeid) or {}).get("outcome") == "passed" or (
            row["when"] == "collect" and any(key.startswith(nodeid + "::") and value.get("outcome") == "passed"
                                             for key, value in checkout.items()))
        failures[nodeid] = {**row, "environment_only": bool(passed_here)}
        if nodeid in here and here[nodeid]["reason"] != row["reason"]:
            failures[nodeid]["checkout_reason"] = here[nodeid]["reason"]
    if trusted:
        reason_rule = ("recorded: a known failure that failed in the rerun in the checkout (clean at the commit "
                       "before and after, untouched in between) with another normalized reason, e.g. past the "
                       "export's missing git metadata, keeps it as checkout_reason; check accepts either reason")
    else:
        reason_rule = ("not recorded: the checkout was not clean at the baseline commit before and after the rerun, "
                       "or changed during it, so a different rerun reason could be an uncommitted regression")
    import pytest as _pytest
    baseline = {
        "schema": SCHEMA,
        "commit": commit,
        "generated_at": utc_now(),
        "command": "pixi run python -m tools.raid_program.test_baseline refresh",
        "method": {
            "export": "git archive HEAD, extracted under ~/.cache/trinity-test-baseline/<sha12>-<run id>/tree",
            "local_inputs": inputs,
            "local_inputs_rule": "from the checkout: LOCAL_INPUT_DIRS as symlinks, LOCAL_INPUT_FILES as copies, and "
                                 "every DVC output (dvc.lock stage outs, *.dvc outs) present there and absent from "
                                 f"the export, copied up to {COPY_LIMIT_BYTES // (1024 * 1024)} MiB and symlinked "
                                 "above",
            "runs": args.runs, "jobs": jobs, "chunks": len(chunks), "chunk_timeout_sec": args.chunk_timeout,
            "pytest_options": list(PYTEST_BASE),
            "known_failure_rule": "failed in every run with the same normalized reason; every run's pytest chunks "
                                  "completed cleanly",
            "flaky_rule": "failed in some run but not identically in all: excluded from failures, with the "
                          "failure reasons seen; check calls another reason new",
            "environment_only_rule": "a known failure that passed when rerun once in the main checkout; a dirty "
                                     "checkout can only move a pass from fixed to environment_only_passed",
            "checkout_state": {"before_rerun": before, "after_rerun": after, "unchanged": before == after,
                               "checkout_reasons_trusted": trusted},
            "checkout_reason_rule": reason_rule,
        },
        "python": sys.version.split()[0],
        "pytest": _pytest.__version__,
        "runs": meta,
        "counts": {**_counts(runs[-1]), "known_failures": len(failures),
                   "environment_only": sum(row["environment_only"] for row in failures.values()),
                   "checkout_reasons": sum("checkout_reason" in row for row in failures.values()),
                   "flaky_excluded": len(flaky)},
        "normalization": "first line of the crash message, phase-prefixed unless the test call; checkout, export "
                         "and home paths, pytest temp paths, hex ids, addresses, timestamps and second durations "
                         "replaced by placeholders (tools/raid_program/test_baseline.normalize_reason)",
        "failures": failures,
        "flaky_excluded": flaky,
    }
    path = ROOT / (args.baseline or BASELINE)
    path.write_text(json.dumps(baseline, indent=1, sort_keys=True) + "\n")
    counts = baseline["counts"]
    print(f"wrote {path.relative_to(ROOT)} for {commit[:12]}: {counts['tests']} tests, {counts['known_failures']} "
          f"known failures ({counts['environment_only']} environment-only, {counts['checkout_reasons']} with a "
          f"checkout reason), {counts['flaky_excluded']} flaky excluded")
    return 0


# --- check --------------------------------------------------------------------------------------------

def load_baseline(path: Path) -> dict[str, Any]:
    baseline = json.loads(path.read_text())
    if baseline.get("schema") != SCHEMA:
        raise SystemExit(f"{path} is not a {SCHEMA} baseline")
    return baseline


def classify(results: dict[str, dict[str, Any]], baseline: dict[str, Any], roots: Iterable[Path] = ()
             ) -> dict[str, list[dict[str, Any]]]:
    """new_failures / known_failures / fixed / flaky / environment_only_passed for one run's results."""
    known = baseline.get("failures") or {}
    flaky = baseline.get("flaky_excluded") or {}
    buckets: dict[str, list[dict[str, Any]]] = {"new_failures": [], "known_failures": [], "fixed": [], "flaky": [],
                                                "environment_only_passed": []}
    for nodeid, row in sorted(failure_reasons(results, roots).items()):
        base = known.get(nodeid)
        entry = {"nodeid": nodeid, "reason": row["reason"]}
        if base and row["reason"] in (base.get("reason"), base.get("checkout_reason")):
            buckets["known_failures"].append(entry)
        elif not base and nodeid in flaky and row["reason"] in flaky_reasons(flaky[nodeid]):
            buckets["flaky"].append(entry | {"baseline_runs": flaky[nodeid]})
        elif base:
            buckets["new_failures"].append(entry | {"baseline_reason": base.get("reason")})
        elif nodeid in flaky:  # flaky, but not for this reason
            buckets["new_failures"].append(entry | {"flaky_reasons": sorted(flaky_reasons(flaky[nodeid]))})
        else:
            buckets["new_failures"].append(entry)
    for nodeid, base in sorted(known.items()):
        ran = results.get(nodeid)
        passed = (ran or {}).get("outcome") == "passed" or (
            base.get("when") == "collect" and nodeid not in results
            and any(key.startswith(nodeid + "::") and value.get("outcome") == "passed" for key, value in results.items()))
        if passed:
            bucket = "environment_only_passed" if base.get("environment_only") else "fixed"
            buckets[bucket].append({"nodeid": nodeid, "baseline_reason": base.get("reason")})
    return buckets


def _print_bucket(name: str, rows: list[dict[str, Any]], limit: int | None) -> None:
    print(f"{name} ({len(rows)}):")
    for row in rows[:limit] if limit is not None else rows:
        extra = f" [baseline: {row['baseline_reason']}]" if row.get("reason") and row.get("baseline_reason") else ""
        print(f"  {row['nodeid']}: {row.get('reason') or row.get('baseline_reason')}{extra}")
    if limit is not None and len(rows) > limit:
        print(f"  ... {len(rows) - limit} more (--verbose lists all)")


def check(args: argparse.Namespace) -> int:
    path = ROOT / (args.baseline or BASELINE)
    baseline = load_baseline(path)
    try:  # a checkout without .git (e.g. a git archive export) can still check; staleness is then unknown
        head = _git("rev-parse", "HEAD")
    except (OSError, subprocess.CalledProcessError):
        head = None
    run_id = new_run_id()
    scratch = Path(args.scratch).expanduser() / f"check-{run_id}"
    pytest_args = [arg for arg in args.pytest_args if arg != "--"]
    with cleanup_on_exit(run_id, scratch, False, "check"):
        if pytest_args:
            outcome = run_pytest(ROOT, [pytest_args], 1, scratch, timeout=args.chunk_timeout, label="check",
                                 run_id=run_id)
        else:
            jobs = args.jobs or default_jobs()
            outcome = run_pytest(ROOT, make_chunks(ROOT, suite_files(ROOT), jobs), jobs, scratch,
                                 timeout=args.chunk_timeout, label="check", run_id=run_id)
    results = outcome["results"]
    buckets = classify(results, baseline, [ROOT])
    stale = None if head is None else baseline.get("commit") != head
    summary = {"baseline": path.relative_to(ROOT).as_posix(), "baseline_commit": baseline.get("commit"), "head": head,
               "stale_baseline": stale, "counts": _counts(results) | {key: len(rows) for key, rows in buckets.items()},
               "timed_out_chunks": outcome["timed_out_chunks"],
               "pytest_errors": [{key: row[key] for key in ("label", "chunk", "problem", "exit_code", "markers",
                                                            "args")} for row in outcome["errors"]],
               **buckets}
    if args.json:
        print(json.dumps(summary, indent=1, sort_keys=True))
    else:
        counts = summary["counts"]
        print(f"baseline {summary['baseline']} at {str(baseline.get('commit'))[:12]}; HEAD {str(head)[:12]}"
              + (" (baseline is from another commit: refresh it once HEAD is committed)" if stale else ""))
        print(f"ran {counts['tests']} tests: {counts['passed']} passed, {counts['failed']} failed, "
              f"{counts['skipped']} skipped")
        limit = None if args.verbose else 20
        _print_bucket("new_failures", buckets["new_failures"], None)
        _print_bucket("known_failures", buckets["known_failures"], limit)
        _print_bucket("fixed", buckets["fixed"], limit)
        _print_bucket("flaky", buckets["flaky"], limit)
        _print_bucket("environment_only_passed", buckets["environment_only_passed"], 0 if limit is not None else None)
        print(f"pytest_errors ({len(summary['pytest_errors'])}):")
        for row in summary["pytest_errors"]:
            print(f"  chunk {row['chunk']} {' '.join(row['args'])}: {row['problem']}")
    if outcome["errors"]:
        print("pytest did not run cleanly; the results are incomplete (exit 3)", file=sys.stderr)
        return EXIT_PYTEST_ERROR
    if not results:
        print("pytest produced no results; see its output above", file=sys.stderr)
        return 2
    return 1 if buckets["new_failures"] else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("check", "refresh"):
        command = sub.add_parser(name)
        command.add_argument("--jobs", type=int, default=0, help=f"parallel pytest processes (default CPUs - {FREE_CPUS})")
        command.add_argument("--baseline", help=f"baseline path relative to the checkout (default {BASELINE})")
        command.add_argument("--scratch", default=str(SCRATCH), help="scratch directory (default %(default)s)")
        command.add_argument("--chunk-timeout", type=float, default=CHUNK_TIMEOUT_SEC)
    sub.choices["check"].add_argument("--json", action="store_true")
    sub.choices["check"].add_argument("--verbose", action="store_true")
    sub.choices["check"].add_argument("pytest_args", nargs=argparse.REMAINDER, help="passed to pytest after --")
    sub.choices["refresh"].add_argument("--runs", type=int, default=2)
    sub.choices["refresh"].add_argument("--keep-export", action="store_true")
    args = parser.parse_args(argv)
    orphans = reap_orphans()  # descendants of an earlier supervisor that was killed by SIGKILL
    if orphans:
        print(f"{args.command}: stopped leftovers of an earlier killed run: {orphans}", file=sys.stderr)
    with terminate_on_signals():
        try:
            return check(args) if args.command == "check" else refresh(args)
        except Terminated as stop:
            print(f"{args.command}: stopped by {signal.Signals(stop.signum).name}; its pytest chunks were stopped, "
                  "leftovers reaped and scratch removed", file=sys.stderr)
            return 128 + stop.signum


if __name__ == "__main__":
    sys.exit(main())
