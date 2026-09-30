"""Hand-off hardening (2026-09-29): the known-test-failure baseline (tools/raid_program/test_baseline.py).

A run's failures are new (not in the baseline, or a different normalized reason), known, fixed or
flaky; only new failures fail the check, and a pytest run that did not complete cleanly fails it with
its own exit code. The baseline is generated from a clean git archive export, per invocation, and
never lists a test whose two runs disagreed."""
from __future__ import annotations

import contextlib
import json
import os
import re
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

from tools.raid_program import test_baseline as tb

ROOT = Path(__file__).resolve().parents[1]


def test_normalize_reason_drops_environment_noise():
    message = (f"AssertionError: {ROOT}/x and /tmp/pytest-of-me/pytest-12/test_a0/run.json at 0x7f3a2b1c "
               "sha 0855911a0f468c4429730ff122 on 2026-09-29T10:11:12Z after 3.25s pid=4321\nsecond line")
    assert tb.normalize_reason(message, "call", [Path("/elsewhere")]) == (
        "AssertionError: <root>/x and <tmp> at 0x<addr> sha <hex> on <time> after <secs> pid=<n>")
    assert tb.normalize_reason("boom", "setup") == "setup: boom"
    assert tb.normalize_reason("", "call") == "no message"
    export = Path.home() / ".cache/trinity-test-baseline/abc/tree"
    assert tb.normalize_reason(f"missing {export}/dataset/x", "call", [export]) == "missing <root>/dataset/x"


def _run(**outcomes):
    return {nodeid: ({"outcome": "failed", "when": "call", "message": value} if value not in ("passed", "skipped")
                     else {"outcome": value, "when": "teardown", "message": ""}) for nodeid, value in outcomes.items()}


def test_only_failures_identical_in_every_run_are_known():
    first = _run(a="passed", b="E: same", c="E: first", d="E: once", e="skipped")
    second = _run(a="passed", b="E: same", c="E: second", d="passed", e="skipped")
    stable, flaky = tb.stable_failures([first, second], [])
    assert stable == {"b": {"reason": "E: same", "when": "call"}}
    assert flaky == {"c": {"runs": ["E: first", "E: second"], "failure_reasons": ["E: first", "E: second"]},
                     "d": {"runs": ["E: once", "passed"], "failure_reasons": ["E: once"]}}


def test_classify_sorts_new_known_fixed_and_flaky():
    baseline = {"failures": {"known": {"reason": "E: x", "when": "call"},
                             "changed": {"reason": "E: old", "when": "call"},
                             "moved": {"reason": "E: export", "when": "call", "checkout_reason": "E: checkout"},
                             "healed": {"reason": "E: y", "when": "call", "environment_only": True},
                             "not_run": {"reason": "E: z", "when": "call"},
                             "tests/test_mod.py": {"reason": "collect: ImportError", "when": "collect"}},
                "flaky_excluded": {"wobbly": {"runs": ["E: w", "passed"], "failure_reasons": ["E: w"]}}}
    results = _run(known="E: x", changed="E: new", healed="passed", fresh="E: n", wobbly="E: w", moved="E: checkout")
    results["tests/test_mod.py::test_one"] = {"outcome": "passed", "when": "teardown", "message": ""}
    buckets = tb.classify(results, baseline)
    assert [row["nodeid"] for row in buckets["known_failures"]] == ["known", "moved"]
    assert buckets["new_failures"] == [{"nodeid": "changed", "reason": "E: new", "baseline_reason": "E: old"},
                                       {"nodeid": "fresh", "reason": "E: n"}]
    assert [row["nodeid"] for row in buckets["fixed"]] == ["tests/test_mod.py"]
    assert [row["nodeid"] for row in buckets["environment_only_passed"]] == ["healed"]
    assert [row["nodeid"] for row in buckets["flaky"]] == ["wobbly"]


def test_parse_results_marks_the_test_a_chunk_died_in(tmp_path):
    path = tmp_path / "out.jsonl"
    rows = [{"event": "start", "nodeid": "a"}, {"event": "result", "nodeid": "a", "outcome": "passed", "when": "teardown",
                                               "message": ""}, {"event": "start", "nodeid": "b"}]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows) + "not json\n")
    results, markers = tb.parse_results(path, timed_out=True)
    assert markers == {"finish": None, "complete": None, "escaped": None, "exit_error": None}
    assert results["a"]["outcome"] == "passed"
    assert results["b"] == {"outcome": "failed", "when": "timeout", "message": "chunk timeout"}
    assert tb.parse_results(path)[0]["b"]["when"] == "crashed"


SUITE = {
    "tests/test_alpha.py": '''
import pytest

@pytest.fixture
def broken_teardown():
    yield
    raise RuntimeError("teardown broke")

@pytest.fixture
def broken_setup():
    raise RuntimeError("setup broke")

def test_pass():
    assert True

def test_fail():
    assert 1 == 2

def test_skip():
    pytest.skip("not here")

@pytest.mark.xfail(reason="known", strict=True)
def test_xfail():
    assert False

def test_setup_error(broken_setup):
    pass

def test_teardown_error(broken_teardown):
    pass
''',
    "tests/test_beta.py": "import missing_module_for_baseline_test\n\ndef test_never():\n    pass\n",
}


def write_suite(folder: Path) -> Path:
    for relative, text in SUITE.items():
        (folder / relative).parent.mkdir(parents=True, exist_ok=True)
        (folder / relative).write_text(text)
    return folder


def test_the_plugin_reports_every_outcome(tmp_path):
    suite = write_suite(tmp_path / "suite")
    files = tb.suite_files(suite)
    assert files == ["tests/test_alpha.py", "tests/test_beta.py"]
    outcome = tb.run_pytest(suite, tb.make_chunks(suite, files, 2), 2, tmp_path / "scratch")
    results = outcome["results"]
    got = {nodeid.split("::")[-1]: (row["outcome"], row["when"]) for nodeid, row in results.items()}
    assert got == {"test_pass": ("passed", "teardown"), "test_fail": ("failed", "call"),
                   "test_skip": ("skipped", "call"), "test_xfail": ("skipped", "call"),
                   "test_setup_error": ("failed", "setup"), "test_teardown_error": ("failed", "teardown"),
                   "tests/test_beta.py": ("failed", "collect")}
    reasons = {nodeid.split("::")[-1]: row["reason"] for nodeid, row in tb.failure_reasons(results, [suite]).items()}
    assert reasons["test_fail"] == "assert 1 == 2"
    assert reasons["test_setup_error"] == "setup: RuntimeError: setup broke"
    assert reasons["test_teardown_error"] == "teardown: RuntimeError: teardown broke"
    assert reasons["tests/test_beta.py"].startswith("collect: ModuleNotFoundError")
    assert outcome["timed_out_chunks"] == []


def test_a_hanging_chunk_is_stopped_and_its_test_named(tmp_path):
    suite = tmp_path / "suite"
    (suite / "tests").mkdir(parents=True)
    (suite / "tests/test_hang.py").write_text("import time\n\ndef test_done():\n    pass\n\n"
                                              "def test_hang():\n    time.sleep(120)\n")
    started = time.monotonic()
    outcome = tb.run_pytest(suite, [["tests/test_hang.py"]], 1, tmp_path / "scratch", timeout=5)
    assert time.monotonic() - started < 60
    assert outcome["timed_out_chunks"] == [0]
    assert outcome["results"]["tests/test_hang.py::test_hang"]["when"] == "timeout"
    assert outcome["results"]["tests/test_hang.py::test_done"]["outcome"] == "passed"


def sleeper(run_id: str | None = None, output: Path | None = None) -> subprocess.Popen:
    env = {key: value for key, value in os.environ.items() if key not in (tb.RUN_ENV, "RAID_TEST_BASELINE_OUTPUT")}
    if run_id:
        env[tb.RUN_ENV] = run_id
    if output:
        env["RAID_TEST_BASELINE_OUTPUT"] = str(output)
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], env=env, start_new_session=True)


def stop(*processes: subprocess.Popen) -> None:
    for process in processes:
        if process.poll() is None:
            process.kill()
            process.wait()


def test_leftover_processes_of_a_run_are_reaped(tmp_path):
    mine, prefix = tb.new_run_id(), tb.new_run_id()
    child = sleeper(mine)
    others = [sleeper(), sleeper(prefix[:8]), sleeper(mine + "0"), sleeper(output=tmp_path / "chunk.jsonl")]
    try:
        time.sleep(0.3)
        reaped = tb.reap_leftovers(mine)
        assert [entry.split()[0] for entry in reaped] == [str(child.pid)]
        assert child.wait(timeout=10) != 0 and all(process.poll() is None for process in others)
    finally:
        stop(child, *others)


@pytest.mark.parametrize("limit, knowledge_mode", [(64 * 1024 * 1024, "copy"), (2, "symlink")])
def test_local_inputs_are_brought_only_where_the_export_lacks_them(tmp_path, monkeypatch, limit, knowledge_mode):
    monkeypatch.setattr(tb, "COPY_LIMIT_BYTES", limit)
    source, tree = tmp_path / "checkout", tmp_path / "tree"
    for path in ("build/bin", "data/dbc/enUS", "dataset/world_knowledge", "dataset/tracked", "dataset/pointer_out"):
        (source / path).mkdir(parents=True)
    (source / "dataset/world_knowledge/trainers.jsonl").write_text("{}\n")
    (source / "trinity-worldserver-test.conf").write_text("LoginDatabaseInfo = x\n")
    (tree / "dataset/tracked").mkdir(parents=True)
    (tree / "dvc.lock").write_text("schema: '2.0'\nstages:\n  knowledge:\n    outs:\n    - path: dataset/world_knowledge\n"
                                   "    - path: dataset/tracked\n    - path: dataset/absent\n")
    (tree / "dataset/pointer_out.dvc").write_text("outs:\n- md5: x\n  path: pointer_out\n")
    brought = tb.link_local_inputs(tree, source)
    assert brought == [{"path": "build", "mode": "symlink"}, {"path": "data", "mode": "symlink"},
                       {"path": "trinity-worldserver-test.conf", "mode": "copy"},
                       {"path": "dataset/pointer_out", "mode": "copy"},
                       {"path": "dataset/world_knowledge", "mode": knowledge_mode}]
    assert (tree / "dataset/world_knowledge/trainers.jsonl").read_text() == "{}\n"
    assert (tree / "dataset/world_knowledge").is_symlink() is (knowledge_mode == "symlink")
    assert (tree / "build").is_symlink() and not (tree / "dataset/tracked").is_symlink()
    assert not (tree / "trinity-worldserver-test.conf").is_symlink()


def test_chunks_cover_every_file_once_and_are_deterministic(tmp_path):
    suite = tmp_path / "suite"
    (suite / "tests").mkdir(parents=True)
    for index in range(30):
        (suite / f"tests/test_{index:02d}.py").write_text("def test_a():\n    pass\n" * (index % 5 + 1))
    files = tb.suite_files(suite)
    chunks = tb.make_chunks(suite, files, 3)
    assert sorted(name for chunk in chunks for name in chunk) == files
    assert chunks == tb.make_chunks(suite, files, 3) and 1 < len(chunks) <= 3 * tb.CHUNKS_PER_JOB + 1


def test_check_exits_nonzero_only_on_new_failures(tmp_path, monkeypatch, capsys):
    suite = write_suite(tmp_path / "suite")
    baseline = {"schema": tb.SCHEMA, "commit": "c" * 40, "failures": {
        "tests/test_alpha.py::test_fail": {"reason": "assert 1 == 2", "when": "call"},
        "tests/test_alpha.py::test_setup_error": {"reason": "setup: RuntimeError: setup broke", "when": "setup"},
        "tests/test_alpha.py::test_teardown_error": {"reason": "teardown: RuntimeError: teardown broke",
                                                     "when": "teardown"}},
        "flaky_excluded": {}}
    (suite / "baseline.json").write_text(json.dumps(baseline))
    monkeypatch.setattr(tb, "ROOT", suite)
    monkeypatch.setattr(tb, "_git", lambda *args, **kwargs: "d" * 40)
    argv = ["check", "--baseline", "baseline.json", "--scratch", str(tmp_path / "scratch")]
    assert tb.main(argv + ["--", "tests/test_alpha.py"]) == 0
    out = capsys.readouterr().out
    assert "baseline is from another commit" in out and "known_failures (3)" in out and "new_failures (0)" in out
    assert tb.main(argv + ["--json", "--", "tests"]) == 1
    summary = json.loads(capsys.readouterr().out)
    assert [row["nodeid"] for row in summary["new_failures"]] == ["tests/test_beta.py"]
    assert summary["stale_baseline"] is True and summary["counts"]["known_failures"] == 3


def git_repo(folder: Path, files: dict[str, str]) -> str:
    """A throwaway repository with one commit of ``files``; returns the commit."""
    for relative, text in files.items():
        (folder / relative).parent.mkdir(parents=True, exist_ok=True)
        (folder / relative).write_text(text)
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false",
           "-c", "core.hooksPath=/dev/null"]
    subprocess.run(["git", "init", "-q"], cwd=folder, check=True)
    subprocess.run(["git", "add", "-A"], cwd=folder, check=True)
    subprocess.run([*git, "commit", "-q", "-m", "base"], cwd=folder, check=True)
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=folder, check=True, capture_output=True,
                          text=True).stdout.strip()


def _marked_pids(base: Path) -> list[int]:
    """Processes still carrying a test_baseline marker whose results point under ``base``."""
    pids = []
    for proc in Path("/proc").iterdir():
        try:
            environ = (proc / "environ").read_bytes().split(b"\0")
        except OSError:
            continue
        if any(item.startswith(f"RAID_TEST_BASELINE_OUTPUT={base}/".encode()) for item in environ) and any(
                item.startswith(f"{tb.RUN_ENV}=".encode()) for item in environ):
            pids.append(int(proc.name))
    return pids


SLOW_SUITE = {
    "tests/test_slow.py": """import subprocess
import sys
import time


def test_slow():
    # a detached grandchild, like a fake worldserver that escapes its chunk's process group
    subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True)
    time.sleep(2)


def test_fail():
    assert 1 == 2
""",
}


def test_refresh_reaper_does_not_kill_other_refresh_same_commit(tmp_path, monkeypatch):
    repo, base = tmp_path / "repo", tmp_path / "scratch"
    commit = git_repo(repo, SLOW_SUITE)
    monkeypatch.setattr(tb, "ROOT", repo)
    # A third refresh of the same commit, still running: its own marker and the path the old shared
    # scratch directory (<sha12>) would have had.
    other = sleeper(tb.new_run_id(), base / commit[:12] / "run1" / "run1-000.jsonl")
    codes: dict[str, int] = {}

    def refresh(name: str) -> None:
        codes[name] = tb.main(["refresh", "--scratch", str(base), "--baseline", f"{name}.json", "--jobs", "1"])

    try:
        threads = [threading.Thread(target=refresh, args=(name,)) for name in ("a", "b")]
        for thread in threads:
            thread.start()
            time.sleep(0.5)  # b exports and starts while a's first run is still sleeping
        for thread in threads:
            thread.join(timeout=120)
        assert codes == {"a": 0, "b": 0}  # a killed or deleted chunk of either run would exit 3
        for name in ("a", "b"):
            baseline = json.loads((repo / f"{name}.json").read_text())
            assert baseline["commit"] == commit and list(baseline["failures"]) == ["tests/test_slow.py::test_fail"]
            assert [run["tests"] for run in baseline["runs"]] == [2, 2] and baseline["flaky_excluded"] == {}
        assert other.poll() is None  # neither refresh touched a process of another invocation
        assert set(_marked_pids(base)) == {other.pid}  # each reaped its own escaped grandchildren
        assert list(base.iterdir()) == []  # each removed only its own export
    finally:
        stop(other)


CRASHING_SUITES = {
    "sessionfinish_raises": ({"tests/conftest.py": "def pytest_sessionfinish(session, exitstatus):\n"
                                                   "    raise RuntimeError('boom in sessionfinish')\n"},
                             [], "an exception escaped pytest: RuntimeError: boom in sessionfinish"),
    "internal_error": ({"tests/conftest.py": "def pytest_collection_modifyitems(items):\n"
                                             "    raise RuntimeError('boom in collection')\n"},
                       [], "pytest exit 3 (internal error)"),
    "worker_exit": ({"tests/test_exit.py": "import os\n\n\ndef test_exit():\n    os._exit(0)\n"},
                    [], "the pytest runner never completed"),
    "usage_error": ({}, ["--no-such-option"], "pytest exit 4 (usage error)"),
    "hook_calls_sys_exit": ({"tests/conftest.py": "import sys\n\n\ndef pytest_unconfigure(config):\n"
                                                  "    sys.exit(0)\n"}, [], "an exception escaped pytest: SystemExit"),
    "failing_exit_handler": ({"tests/test_exit_handler.py": "import atexit\n\n\ndef test_registers():\n"
                                                             "    atexit.register(lambda: 1 / 0)\n"},
                             [], "an exit handler failed after pytest: ZeroDivisionError"),
}


@pytest.mark.parametrize("case", sorted(CRASHING_SUITES))
def test_baseline_internal_error_fails_check(tmp_path, monkeypatch, capsys, case):
    files, extra, problem = CRASHING_SUITES[case]
    suite = tmp_path / "suite"
    for relative, text in {"tests/test_ok.py": "def test_ok():\n    pass\n", **files}.items():
        (suite / relative).parent.mkdir(parents=True, exist_ok=True)
        (suite / relative).write_text(text)
    (suite / "baseline.json").write_text(json.dumps({"schema": tb.SCHEMA, "commit": "c" * 40, "failures": {},
                                                     "flaky_excluded": {}}))
    monkeypatch.setattr(tb, "ROOT", suite)
    monkeypatch.setattr(tb, "_git", lambda *args, **kwargs: "c" * 40)
    code = tb.main(["check", "--baseline", "baseline.json", "--scratch", str(tmp_path / "scratch"), "--json", "--",
                    *extra, "tests"])
    summary = json.loads(capsys.readouterr().out)
    assert code == tb.EXIT_PYTEST_ERROR  # also when the crash left a failure behind (exit 3 wins over 1)
    assert len(summary["pytest_errors"]) == 1 and problem in summary["pytest_errors"][0]["problem"]
    crashed = [row for row in summary["new_failures"] if row["reason"].startswith("crashed:")]
    assert summary["new_failures"] == crashed and len(crashed) == (case == "worker_exit")


def _problem(finish=1, complete=1, returncode=1, stderr="", escaped=None, timed_out=False, results_file=True):
    markers = {"finish": finish, "complete": complete, "escaped": escaped, "exit_error": None}
    return tb.chunk_problem(timed_out=timed_out, results_file=results_file, markers=markers, returncode=returncode,
                            timeout=60, stderr=stderr)


def test_chunk_problem_rules():
    assert _problem() is None and _problem(0, 0, 0) is None
    assert _problem(stderr="1 warning\nResourceWarning: unclosed file\n") is None
    assert "inconsistent exit statuses: session 0, pytest.main 1, process 1" in _problem(finish=0)
    assert "killed by SIGKILL" in _problem(returncode=-9)
    assert _problem(timed_out=True) == "timed out after 60 s"
    assert "session never finished" in _problem(finish=None)
    assert "runner never completed" in _problem(complete=None)
    assert "escaped pytest: RuntimeError: x" in _problem(escaped="RuntimeError: x", returncode=70)
    internal = "INTERNALERROR> Traceback (most recent call last):"
    assert "INTERNALERROR> Traceback" in _problem(stderr=internal)  # exit 1 with pytest's own line
    assert _problem(finish=0, complete=0, returncode=0, stderr=internal) is None  # exit 0: not an error
    assert _problem(stderr="Traceback (most recent call last):\nValueError: handled\n") is None


LATE_ERRORS = {
    "sessionfinish_wrapper": "import pytest\n\n\n@pytest.hookimpl(wrapper=True)\n"
                             "def pytest_sessionfinish(session, exitstatus):\n    yield\n"
                             "    raise RuntimeError('late wrapper error')\n",
    "sessionfinish_trylast": "import pytest\n\n\n@pytest.hookimpl(trylast=True)\n"
                             "def pytest_sessionfinish(session, exitstatus):\n"
                             "    raise RuntimeError('late trylast error')\n",
    "unconfigure": "def pytest_unconfigure(config):\n    raise RuntimeError('late unconfigure error')\n",
}
KNOWN_FAIL = "def test_ok():\n    pass\n\n\ndef test_fail():\n    assert 1 == 2\n"


@pytest.mark.parametrize("case", sorted(LATE_ERRORS))
def test_late_session_error_is_not_accepted_as_known_failure(tmp_path, monkeypatch, capsys, case):
    files = {"tests/test_known.py": KNOWN_FAIL, "tests/conftest.py": LATE_ERRORS[case]}
    repo = tmp_path / "repo"
    commit = git_repo(repo, files)
    (repo / "baseline.json").write_text(json.dumps({"schema": tb.SCHEMA, "commit": commit, "failures": {
        "tests/test_known.py::test_fail": {"reason": "assert 1 == 2", "when": "call"}}, "flaky_excluded": {}}))
    monkeypatch.setattr(tb, "ROOT", repo)
    code = tb.main(["check", "--baseline", "baseline.json", "--scratch", str(tmp_path / "scratch"), "--json", "--",
                    "tests"])
    summary = json.loads(capsys.readouterr().out)
    assert [row["nodeid"] for row in summary["known_failures"]] == ["tests/test_known.py::test_fail"]
    assert code == tb.EXIT_PYTEST_ERROR and summary["new_failures"] == []  # the known failure does not hide it
    assert [row["problem"] for row in summary["pytest_errors"]] == [f"an exception escaped pytest: RuntimeError: "
                                                                   f"late {case.split('_')[-1]} error"]
    # refresh refuses to turn such a run into a baseline
    assert tb.main(["refresh", "--scratch", str(tmp_path / "scratch"), "--baseline", "new.json", "--jobs", "1"]) == 3
    assert not (repo / "new.json").exists()


GIT_SUITE = {
    "helper.py": "VALUE = 'a'\n",
    "tests/test_x.py": """from pathlib import Path

import helper


def test_value():
    assert helper.VALUE == 'ok'


def test_git():
    assert Path('.git').exists() == 'x'  # False in the export, True in the checkout
""",
}


def test_dirty_checkout_failure_is_not_added_to_clean_baseline(tmp_path, monkeypatch):
    repo = tmp_path / "repo"
    commit = git_repo(repo, GIT_SUITE)
    monkeypatch.setattr(tb, "ROOT", repo)
    argv = ["refresh", "--scratch", str(tmp_path / "scratch"), "--baseline", "baseline.json", "--jobs", "1"]
    assert tb.main(argv) == 0
    clean = json.loads((repo / "baseline.json").read_text())
    assert clean["method"]["checkout_state"]["checkout_reasons_trusted"] is True
    assert clean["failures"]["tests/test_x.py::test_git"]["checkout_reason"] == "AssertionError: assert True == 'x'"
    assert "checkout_reason" not in clean["failures"]["tests/test_x.py::test_value"]

    (repo / "helper.py").write_text("VALUE = 'b'\n")  # an uncommitted regression changes the failure
    assert tb.main(argv) == 0
    dirty = json.loads((repo / "baseline.json").read_text())
    state = dirty["method"]["checkout_state"]
    assert state["checkout_reasons_trusted"] is False and state["before_rerun"]["clean"] is False
    assert state["before_rerun"]["tracked_changes"] == 1 and state["before_rerun"]["head"] == commit
    assert "not recorded" in dirty["method"]["checkout_reason_rule"]
    assert not any("checkout_reason" in row for row in dirty["failures"].values())
    assert dirty["failures"]["tests/test_x.py::test_value"]["reason"] == "AssertionError: assert 'a' == 'ok'"
    here = tb.run_pytest(repo, [["tests"]], 1, tmp_path / "rerun")["results"]
    buckets = tb.classify(here, dirty, [repo])
    assert [row["nodeid"] for row in buckets["new_failures"]] == ["tests/test_x.py::test_git",
                                                                   "tests/test_x.py::test_value"]
    assert buckets["new_failures"][1]["reason"] == "AssertionError: assert 'b' == 'ok'"


@pytest.mark.parametrize("revert", [False, True], ids=["kept", "reverted"])
def test_refresh_does_not_allow_regression_added_after_clean_snapshot(tmp_path, monkeypatch, revert):
    repo = tmp_path / "repo"
    git_repo(repo, GIT_SUITE)
    monkeypatch.setattr(tb, "ROOT", repo)
    real_run_pytest = tb.run_pytest
    original = (repo / "helper.py").read_text()

    def run_pytest(cwd, groups, jobs, scratch, **kwargs):
        if kwargs.get("label") != "checkout":
            return real_run_pytest(cwd, groups, jobs, scratch, **kwargs)
        (repo / "helper.py").write_text("VALUE = 'b'\n")  # a regression lands after the clean snapshot
        try:
            outcome = real_run_pytest(cwd, groups, jobs, scratch, **kwargs)
        finally:
            if revert:
                (repo / "helper.py").write_text(original)  # and is gone again before the second snapshot
        return outcome

    monkeypatch.setattr(tb, "run_pytest", run_pytest)
    assert tb.main(["refresh", "--scratch", str(tmp_path / "scratch"), "--baseline", "baseline.json",
                    "--jobs", "1"]) == 0
    baseline = json.loads((repo / "baseline.json").read_text())
    state = baseline["method"]["checkout_state"]
    assert state["before_rerun"]["clean"] is True and state["after_rerun"]["clean"] is revert
    assert state["unchanged"] is False and state["checkout_reasons_trusted"] is False
    assert not any("checkout_reason" in row for row in baseline["failures"].values())
    here = tb.run_pytest(repo, [["tests/test_x.py::test_value"]], 1, tmp_path / "rerun")["results"]
    if not revert:  # the regression is still there: check calls it new
        assert [row["nodeid"] for row in tb.classify(here, baseline, [repo])["new_failures"]] == [
            "tests/test_x.py::test_value"]


HANG_SUITE = """import os
import subprocess
import sys
import time
from pathlib import Path


def test_hang():
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(120)"], start_new_session=True)
    Path(os.environ["HANG_PIDS"]).write_text(f"{os.getpid()} {child.pid}")
    time.sleep(120)
"""


def _gone(pid: int, timeout: float = 15.0) -> bool:
    """The process no longer exists or is a zombie awaiting its reaper."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except (OSError, IndexError):
            return True
        if state in ("Z", "X"):
            return True
        time.sleep(0.1)
    return False


def _supervise_hanging_chunk(tmp_path: Path) -> tuple[subprocess.Popen, int, int, Path]:
    (tmp_path / "suite/tests").mkdir(parents=True)
    (tmp_path / "suite/tests/test_hang.py").write_text(HANG_SUITE)
    baseline = tmp_path / "baseline.json"
    baseline.write_text(json.dumps({"schema": tb.SCHEMA, "commit": "c" * 40, "failures": {}, "flaky_excluded": {}}))
    pids, scratch = tmp_path / "pids", tmp_path / "scratch"
    env = {key: value for key, value in os.environ.items() if not key.startswith("RAID_TEST_BASELINE")}
    supervisor = subprocess.Popen(
        [sys.executable, "-m", "tools.raid_program.test_baseline", "check", "--scratch", str(scratch), "--baseline",
         str(baseline), "--", str(tmp_path / "suite/tests/test_hang.py")],
        cwd=ROOT, env={**env, "HANG_PIDS": str(pids)}, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        start_new_session=True)
    deadline = time.monotonic() + 90
    while not (pids.exists() and len(pids.read_text().split()) == 2):
        assert time.monotonic() < deadline and supervisor.poll() is None, "the chunk never started"
        time.sleep(0.1)
    chunk, grandchild = (int(value) for value in pids.read_text().split())
    return supervisor, chunk, grandchild, scratch


@pytest.mark.parametrize("sig", [signal.SIGTERM, signal.SIGINT, signal.SIGHUP], ids=lambda sig: sig.name)
def test_terminating_supervisor_stops_the_chunk(tmp_path, sig):
    supervisor, chunk, grandchild, scratch = _supervise_hanging_chunk(tmp_path)
    try:
        supervisor.send_signal(sig)
        assert supervisor.wait(timeout=60) == 128 + sig
        assert _gone(chunk) and _gone(grandchild)  # the chunk's group, and what escaped it (run marker)
        assert list(scratch.iterdir()) == []
    finally:
        for pid in (chunk, grandchild):
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
        stop(supervisor)


def test_killed_supervisor_takes_its_chunk_down(tmp_path):
    supervisor, chunk, grandchild, _ = _supervise_hanging_chunk(tmp_path)
    try:
        supervisor.kill()  # no handler can run: the runner's PR_SET_PDEATHSIG stops the chunk
        supervisor.wait(timeout=30)
        assert _gone(chunk)
        # Known limitation: the detached grandchild survives; the next run's orphan sweep reaps it.
        assert not _gone(grandchild, timeout=1.0)
        assert str(grandchild) in [entry.split()[0] for entry in tb.reap_orphans()]
        assert _gone(grandchild)
    finally:
        for pid in (chunk, grandchild):
            with contextlib.suppress(ProcessLookupError):
                os.kill(pid, signal.SIGKILL)
        stop(supervisor)


def test_chunks_release_pytest_temp_dirs(tmp_path, monkeypatch):
    """The runner runs pytest's exit handlers before its marker, so the chunk's numbered basetemp keeps no
    lock and pytest can prune it (a lock left behind pins the directory for three days)."""
    suite = tmp_path / "suite"
    (suite / "tests").mkdir(parents=True)
    (suite / "tests/test_tmp.py").write_text("def test_tmp(tmp_path):\n    (tmp_path / 'x').write_text('x')\n")
    (tmp_path / "temproot").mkdir()
    monkeypatch.setenv("PYTEST_DEBUG_TEMPROOT", str(tmp_path / "temproot"))
    outcome = tb.run_pytest(suite, [["tests"]], 1, tmp_path / "scratch")
    assert outcome["errors"] == [] and outcome["results"]["tests/test_tmp.py::test_tmp"]["outcome"] == "passed"
    assert list((tmp_path / "temproot").glob("pytest-of-*/pytest-*"))
    assert list((tmp_path / "temproot").glob("pytest-of-*/pytest-*/.lock")) == []


def test_atexit_runs_after_normal_non_daemon_thread_shutdown(tmp_path):
    """The runner keeps Python's shutdown order: non-daemon threads are joined before atexit handlers."""
    suite = tmp_path / "suite"
    (suite / "tests").mkdir(parents=True)
    (suite / "tests/test_worker.py").write_text("""import atexit
import threading
import time

DONE = []


def _check():
    if not DONE:
        raise RuntimeError('atexit ran before the worker thread finished')


def test_worker():
    atexit.register(_check)
    threading.Thread(target=lambda: (time.sleep(1.0), DONE.append(1))).start()
""")
    outcome = tb.run_pytest(suite, [["tests"]], 1, tmp_path / "scratch")
    assert outcome["errors"] == [] and outcome["results"]["tests/test_worker.py::test_worker"]["outcome"] == "passed"


HANDLED = """import sys
import traceback


def test_handled({args}):
    {context}
        try:
            raise ValueError('handled')
        except ValueError:
            traceback.print_exc()
        print('INTERNALERROR> lookalike', file=sys.stderr)
"""


@pytest.mark.parametrize("case", ["minus_s", "capsys_disabled"])
def test_legitimate_handled_traceback_is_not_a_chunk_error(tmp_path, case):
    suite = tmp_path / "suite"
    (suite / "tests").mkdir(parents=True)
    body = (HANDLED.format(args="", context="if True:") if case == "minus_s"
            else HANDLED.format(args="capsys", context="with capsys.disabled():"))
    (suite / "tests/test_handled.py").write_text(body)
    outcome = tb.run_pytest(suite, [["tests"]], 1, tmp_path / "scratch", extra=["-s"] if case == "minus_s" else [])
    assert "Traceback (most recent call last)" in (tmp_path / "scratch/run-000.err").read_text()
    assert outcome["errors"] == [] and outcome["results"]["tests/test_handled.py::test_handled"]["outcome"] == "passed"


def test_next_run_reaps_orphans_of_a_killed_supervisor():
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    gone.wait()  # a pid that no longer exists: a supervisor killed by SIGKILL
    base = {key: value for key, value in os.environ.items() if not key.startswith("RAID_TEST_BASELINE")}
    orphan = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True,
                              env={**base, tb.RUN_ENV: "old", "RAID_TEST_BASELINE_SUPERVISOR": str(gone.pid)})
    owned = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True,
                             env={**base, tb.RUN_ENV: "live", "RAID_TEST_BASELINE_SUPERVISOR": str(os.getpid())})
    try:
        time.sleep(0.3)
        assert [entry.split()[0] for entry in tb.reap_orphans()] == [str(orphan.pid)]
        assert orphan.wait(timeout=10) != 0 and owned.poll() is None  # a live supervisor's process is kept
    finally:
        stop(orphan, owned)


def test_a_traceback_inside_a_test_is_not_a_chunk_error(tmp_path):
    suite = tmp_path / "suite"
    (suite / "tests").mkdir(parents=True)
    (suite / "tests/test_noisy.py").write_text(
        "import sys\nimport traceback\n\n\ndef test_noisy():\n    try:\n        raise ValueError('x')\n"
        "    except ValueError:\n        traceback.print_exc()\n    print('INTERNALERROR lookalike', file=sys.stderr)\n")
    outcome = tb.run_pytest(suite, [["tests"]], 1, tmp_path / "scratch")
    assert outcome["errors"] == [] and outcome["results"]["tests/test_noisy.py::test_noisy"]["outcome"] == "passed"


def test_flaky_test_with_different_failure_is_new():
    runs = [_run(wobbly="E: timeout waiting"), _run(wobbly="passed")]
    stable, flaky = tb.stable_failures(runs, [])
    baseline = {"failures": stable, "flaky_excluded": flaky}
    assert stable == {} and flaky["wobbly"]["failure_reasons"] == ["E: timeout waiting"]
    same = tb.classify(_run(wobbly="E: timeout waiting"), baseline)
    assert [row["nodeid"] for row in same["flaky"]] == ["wobbly"] and same["new_failures"] == []
    other = tb.classify(_run(wobbly="E: KeyError: 'child'"), baseline)
    assert other["flaky"] == [] and other["new_failures"] == [
        {"nodeid": "wobbly", "reason": "E: KeyError: 'child'", "flaky_reasons": ["E: timeout waiting"]}]
    legacy = {"failures": {}, "flaky_excluded": {"wobbly": ["E: timeout waiting", "passed"]}}  # pre-reasons format
    assert [row["nodeid"] for row in tb.classify(_run(wobbly="E: other"), legacy)["new_failures"]] == ["wobbly"]
    assert [row["nodeid"] for row in tb.classify(_run(wobbly="E: timeout waiting"), legacy)["flaky"]] == ["wobbly"]


def test_the_checked_in_baseline_is_well_formed():
    path = ROOT / tb.BASELINE
    if not path.is_file():
        pytest.skip("no baseline generated yet")
    baseline = tb.load_baseline(path)
    assert re.fullmatch(r"[0-9a-f]{40}", baseline["commit"])
    assert baseline["method"]["runs"] >= 2
    assert not set(baseline["failures"]) & set(baseline["flaky_excluded"])
    assert all(isinstance(row, dict) and row["failure_reasons"] for row in baseline["flaky_excluded"].values())
    if not baseline["method"]["checkout_state"]["checkout_reasons_trusted"]:
        assert not any("checkout_reason" in row for row in baseline["failures"].values())
    for nodeid, row in baseline["failures"].items():
        assert row["reason"] and row["when"] and isinstance(row["environment_only"], bool), nodeid
    counts = baseline["counts"]
    assert counts["known_failures"] == len(baseline["failures"])
    assert counts["flaky_excluded"] == len(baseline["flaky_excluded"])
