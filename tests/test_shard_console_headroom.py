"""Round 11: a console reply cut by a failed stdout write (user quota), its label and headroom."""
from __future__ import annotations

import gzip
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from tests.test_live_validation_round3_harness import (
    MANIFEST, TAIL, LoopKeptRunning, _diagnose, _route_rows, _status, _trace)
from tests.test_shard_coordinator import SCENARIOS, LatchedTransport, fast_watchdog, proof_plan, shard_row
from tools.bot_ml.live_validation_terminal_signals import TERMINAL_TRACE_DRAIN_FILE, drain_terminal_trace
from tools.bot_ml import run_live_bot_validation as harness
from tools.bot_ml.live_validation_heartbeat import drain_delta_command
from tools.raid_program import run_root_headroom as headroom
from tools.raid_program import shard_coordinator as sc

FULL = "blackwing_descent_10n_full_c0"


# ---------------------------------------------------------------- bounded full-raid trace


def test_full_raid_heartbeat_reads_a_bounded_trace_tail_not_the_delta() -> None:
    spec = sc.parse_shard(shard_row(FULL, FULL))
    assert sc.is_full_raid_shard(spec)
    lines = sc.shard_script(spec, sc.WatchdogPolicy()).splitlines()
    traces = [line for line in lines if line.startswith(".botauto trace")]
    assert traces == [f".botauto trace {FULL} all {sc.FULL_RAID_HEARTBEAT_TRACE_LIMIT}"]
    # No delta heartbeat: the terminal drain has no delta cursor to walk.
    _, heartbeat, _ = harness.heartbeat_commands_from_script("\n".join(lines))
    assert drain_delta_command(heartbeat) == ""
    # A smaller configured limit is kept.
    small = sc.shard_script(spec, sc.WatchdogPolicy(trace_limit=4)).splitlines()
    assert f".botauto trace {FULL} all 4" in small


def test_boss_shards_keep_the_delta_trace() -> None:
    spec = proof_plan().shards[0]
    assert not sc.is_full_raid_shard(spec)
    assert f".botauto trace {spec.cohort_id} all 128 delta" in sc.shard_script(spec, sc.WatchdogPolicy()).splitlines()


def test_full_raid_shards_name_one_bounded_terminal_trace() -> None:
    spec = sc.parse_shard(shard_row(FULL, FULL))
    assert sc.terminal_trace_command(spec, sc.WatchdogPolicy()) == f".botauto trace {FULL} all 128"
    assert sc.terminal_trace_command(proof_plan().shards[0], sc.WatchdogPolicy()) == ""


def test_without_a_delta_heartbeat_the_drain_captures_only_the_bounded_tail(tmp_path: Path) -> None:
    calls: list[str] = []

    def run(command: str) -> tuple[str, bool]:
        calls.append(command)
        return json.dumps(_trace(_route_rows(300, 128))), True

    heartbeat = [".botauto status c0", ".botauto trace c0 all 8"]
    receipt = json.loads(drain_terminal_trace(run, heartbeat, tmp_path, parse_payloads, tail_command=TAIL))
    assert calls == [TAIL]
    assert receipt["command"] == TAIL and receipt["delta_calls"] == 0
    assert receipt["delta_stop_reason"] == "no_delta_heartbeat" and receipt["timed_out"] is False
    assert receipt["tail_captured"] is True and receipt["newest_captured"] is True and receipt["completed"] is True
    with gzip.open(tmp_path / TERMINAL_TRACE_DRAIN_FILE, "rt", encoding="utf-8") as handle:
        assert len(handle.read().splitlines()) == 128
    # Without the opt-in a non-delta heartbeat still drains nothing (unchanged).
    assert drain_terminal_trace(run, heartbeat, tmp_path / "none", parse_payloads) == ""
    assert calls == [TAIL]


def parse_payloads(output: str) -> list[dict[str, Any]]:
    return harness.parse_json_objects(output)


def test_a_failed_full_raid_watchdog_captures_the_tail_before_the_stop(tmp_path: Path) -> None:
    """End to end: bounded heartbeat trace, terminal failure, one bounded tail, then the stop."""
    heartbeat_trace = ".botauto trace c0 all 8"
    beats = [{"status": _status(), "trace": _trace(_route_rows(1, 39))},
             {"status": _status(), "diagnose": _diagnose(error=True),
              "trace": _trace([{**row, "action": "cast_spell"} for row in _route_rows(40, 8)])}]
    commands: list[str] = []
    state = {"beat": 0}

    def execute(command: str, _timeout: int) -> tuple[str, int, bool]:
        commands.append(command)
        beat = beats[min(state["beat"], len(beats)) - 1]
        if command.startswith((".botauto combatlog", ".botauto stop")):
            payload = {"ok": True, "action": "botauto_combatlog" if "combatlog" in command else "botauto_stop"}
        elif command.startswith(".botauto status"):
            payload = beat["status"]
        elif command.startswith(".botauto diagnose"):
            payload = beat.get("diagnose") or _diagnose()
        elif command == TAIL:
            payload = _trace(_route_rows(200, 128))
        else:
            assert command == heartbeat_trace, command
            payload = beat["trace"]
        return json.dumps(payload) + "\n", 0, False

    def sleep(_seconds: float) -> None:
        state["beat"] += 1
        if state["beat"] > len(beats):
            raise LoopKeptRunning

    output_dir = tmp_path / "run"
    harness.run_transport_completion_watchdog(
        execute, ["attached"], None,
        harness.command_script(selector="all", trace_limit=8, start=False, stop=True,
                               exit_server=False, cohort_id="c0", trace_delta=False),
        output_dir, {}, {"scenario_id": "blackwing_descent_10n_c0_diagnostic"},
        validation_route_manifest=MANIFEST, heartbeat_sec=1, no_progress_window_sec=600,
        status_command=".botauto status c0", sleep=sleep, terminal_trace_command=TAIL,
    )
    stop = commands.index(".botauto stop c0")
    traces = [command for command in commands[:stop] if command.startswith(".botauto trace")]
    assert traces[-1] == TAIL and TAIL not in traces[:-1]
    assert not any(command.endswith(" delta") for command in commands)
    with gzip.open(output_dir / TERMINAL_TRACE_DRAIN_FILE, "rt", encoding="utf-8") as handle:
        assert len(handle.read().splitlines()) == 128


# ---------------------------------------------------------------- headroom


GIB = headroom.GIB
NOW = 1_800_000_000.0


def test_an_active_soft_grace_period_still_allows_writes_up_to_the_hard_limit() -> None:
    """Reviewer case: hard 20 GiB, soft 10 GiB, 11 GiB used, 7 days of grace left."""
    quota = headroom.enforceable_quota(hard_bytes=20 * GIB, soft_bytes=10 * GIB, used_bytes=11 * GIB,
                                       grace_expires_unix=int(NOW) + 7 * 86400, now=NOW)
    assert quota["over_soft_limit"] and quota["grace_active"] and not quota["grace_expired"]
    assert quota["limit_bytes"] == 20 * GIB
    assert (quota["hard_limit_bytes"], quota["soft_limit_bytes"]) == (20 * GIB, 10 * GIB)
    assert quota["grace_expires_unix"] == int(NOW) + 7 * 86400


def test_an_expired_soft_grace_period_caps_writes_at_the_soft_limit(tmp_path: Path) -> None:
    quota = headroom.enforceable_quota(hard_bytes=20 * GIB, soft_bytes=10 * GIB, used_bytes=11 * GIB,
                                       grace_expires_unix=int(NOW) - 1, now=NOW)
    assert quota["grace_expired"] and not quota["grace_active"] and quota["limit_bytes"] == 10 * GIB
    row = headroom.writable_headroom(tmp_path, quota_reader=lambda path: quota)
    assert row["headroom_bytes"] == 0 and row["quota"]["grace_expired"] is True


def test_soft_limit_semantics_without_a_running_timer() -> None:
    # Under the soft limit: the hard limit is the ceiling (crossing soft starts grace).
    under = headroom.enforceable_quota(hard_bytes=20 * GIB, soft_bytes=10 * GIB, used_bytes=5 * GIB,
                                       grace_expires_unix=0, now=NOW)
    assert under["limit_bytes"] == 20 * GIB and not under["over_soft_limit"]
    # Over soft with btime unset: the kernel starts the timer on the next write, which succeeds.
    unset = headroom.enforceable_quota(hard_bytes=20 * GIB, soft_bytes=10 * GIB, used_bytes=11 * GIB,
                                       grace_expires_unix=0, now=NOW)
    assert unset["limit_bytes"] == 20 * GIB and not unset["grace_active"] and not unset["grace_expired"]
    # Soft limit only, grace running: nothing caps writes yet.
    soft_only = headroom.enforceable_quota(hard_bytes=0, soft_bytes=10 * GIB, used_bytes=11 * GIB,
                                           grace_expires_unix=int(NOW) + 60, now=NOW)
    assert soft_only["limit_bytes"] is None and soft_only["hard_limit_bytes"] is None


def test_an_uncapped_quota_leaves_free_space_as_the_headroom(tmp_path: Path) -> None:
    quota = headroom.enforceable_quota(hard_bytes=0, soft_bytes=10 * GIB, used_bytes=11 * GIB,
                                       grace_expires_unix=int(NOW) + 60, now=NOW)
    row = headroom.writable_headroom(tmp_path, quota_reader=lambda path: quota)
    assert row["quota_available_bytes"] is None
    assert row["headroom_bytes"] == row["filesystem_available_bytes"]
    assert row["quota"]["grace_active"] is True


def test_headroom_is_the_smaller_of_free_space_and_the_user_quota(tmp_path: Path) -> None:
    quota = {"limit_bytes": 1000, "used_bytes": 900}
    row = headroom.writable_headroom(tmp_path / "not" / "yet", quota_reader=lambda path: quota)
    assert row["path"] == str(tmp_path)
    assert row["quota_available_bytes"] == 100 and row["headroom_bytes"] == 100
    assert row["filesystem_available_bytes"] > 100
    over = headroom.writable_headroom(tmp_path, quota_reader=lambda path: {"limit_bytes": 10, "used_bytes": 50})
    assert over["headroom_bytes"] == 0
    free = headroom.writable_headroom(tmp_path, quota_reader=lambda path: None)
    assert free["quota_available_bytes"] is None
    assert free["headroom_bytes"] == free["filesystem_available_bytes"]


def test_user_quota_never_raises(tmp_path: Path) -> None:
    row = headroom.user_quota(tmp_path)
    # limit_bytes is None when no ceiling is enforceable (soft-only, or grace active with no hard limit).
    assert row is None or (
        (row["limit_bytes"] is None or row["limit_bytes"] > 0) and row["used_bytes"] >= 0)


def test_run_root_headroom_refuses_before_launch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sc, "safe_headroom", lambda path: {
        "path": str(path), "filesystem_available_bytes": 3 << 30, "quota_available_bytes": 17 << 20,
        "headroom_bytes": 17 << 20})
    with pytest.raises(sc.RunRootHeadroomError, match="run_root_headroom_insufficient"):
        sc.require_run_root_headroom(tmp_path, headroom.DEFAULT_MIN_HEADROOM_BYTES)
    assert sc.require_run_root_headroom(tmp_path, 0)["headroom_bytes"] == 17 << 20
    assert sc.require_run_root_headroom(tmp_path, 1 << 20)["headroom_bytes"] == 17 << 20


def test_main_reports_the_headroom_refusal(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(plan: Any, **kwargs: Any) -> dict[str, Any]:
        assert kwargs["min_headroom_bytes"] == 3 << 30
        raise sc.RunRootHeadroomError("run_root_headroom_insufficient: test")

    monkeypatch.setattr(sc, "load_run_plan", lambda path, select=(): proof_plan())
    monkeypatch.setattr(sc, "run_live", refuse)
    # main() refuses an --output-dir inside the source tree; pytest's basetemp may be there.
    monkeypatch.setattr(sc, "REPO_ROOT", tmp_path / "source")
    with pytest.raises(SystemExit, match="run_root_headroom_insufficient"):
        sc.main(["--plan", str(tmp_path / "plan.json"), "--output-dir", str(tmp_path / "run"),
                 "--min-run-root-headroom-gib", "3"])


# ---------------------------------------------------------------- truncated reply


CUT_REPLY = r"""
import sys, time
sys.stdin.readline()
# The status reply's first 4 KiB block reached the log; the rest of the write
# failed (EDQUOT), so neither the closing brace nor the TC> prompt ever follows.
sys.stdout.write('TC>{"ok":true,"action":"botauto_status","cohort_id":"c","bots":[' + '0,' * 64)
sys.stdout.flush()
time.sleep(30)
"""


def test_a_reply_cut_by_a_failed_write_records_why_and_the_headroom(tmp_path: Path) -> None:
    log = tmp_path / "worldserver.console.log"
    with log.open("ab") as sink:
        process = subprocess.Popen([sys.executable, "-c", CUT_REPLY], stdin=subprocess.PIPE,
                                   stdout=sink, stderr=sink)
    try:
        transport = sc.ShardConsoleTransport(process, log)
        console = sc.SerializedConsole(transport)
        output, code, timed_out = console(".botauto status c", 1)
        assert (code, timed_out) == (1, True) and transport.failed
        assert '"action":"botauto_status"' in output
        failure = console.health()["last_failure"]
        assert failure["reason"] == "reply_prompt_missing"
        assert failure["command"] == ".botauto status c"
        assert failure["reply_bytes_after_marker"] > 0
        assert failure["console_log_headroom"]["path"] == str(tmp_path)
        assert "headroom_bytes" in failure["console_log_headroom"]
    finally:
        process.kill()
        process.wait()


# ---------------------------------------------------------------- completion label


def shard_reports(root: Path) -> list[dict[str, Any]]:
    return [json.loads(path.read_text()) for path in sorted(root.glob("shards/*/report.json"))]


def test_a_console_timeout_before_the_cap_is_not_the_emergency_cap(tmp_path: Path) -> None:
    world = LatchedTransport(fail_after=12)
    plan = proof_plan(heartbeat_sec=1, no_progress_window_sec=1, emergency_timeout_sec=600)
    summary = sc.ShardCoordinator(plan, sc.SerializedConsole(world), tmp_path, scenario_dir=SCENARIOS,
                                  sleep=fast_watchdog()).run()
    assert summary["terminal_reason"] == "infrastructure_loss"
    timed_out = [row for row in summary["shards"] if row["timed_out"]]
    assert timed_out, summary["shards"]
    assert {row["completion_reason"] for row in timed_out} == {sc.CONSOLE_COMMAND_TIMEOUT_REASON}
    assert all(row["completion_reason"] != "emergency_wall_clock_timeout" for row in summary["shards"])
    reports = [report for report in shard_reports(tmp_path)
               if report.get("completion_reason") == sc.CONSOLE_COMMAND_TIMEOUT_REASON]
    assert reports and all(report["semantic_liveness"]["emergency_cap_reached"] is False for report in reports)


def test_other_watchdog_callers_keep_the_emergency_label(tmp_path: Path) -> None:
    """Without the opt-in (bot-live-validate, SOAP, serial soak) a timeout keeps its old label."""
    def watchdog(transport: Any, command: Any, *args: Any, **kwargs: Any) -> Any:
        kwargs.pop("console_timeout_reason")
        return harness.run_transport_completion_watchdog(transport, command, *args, **kwargs)

    world = LatchedTransport(fail_after=12)
    plan = proof_plan(heartbeat_sec=1, no_progress_window_sec=1, emergency_timeout_sec=600)
    summary = sc.ShardCoordinator(plan, sc.SerializedConsole(world), tmp_path, scenario_dir=SCENARIOS,
                                  watchdog=watchdog, sleep=fast_watchdog()).run()
    timed_out = [row for row in summary["shards"] if row["timed_out"]]
    assert timed_out and {row["completion_reason"] for row in timed_out} == {"emergency_wall_clock_timeout"}
