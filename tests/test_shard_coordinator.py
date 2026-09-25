"""tools.raid_program.shard_coordinator against a fake worldserver console."""
from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from tools.bot_ml import run_live_bot_validation as harness
from tools.raid_program import shard_coordinator as sc

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = ROOT / "dataset/validation_scenarios"
MAGMAW = "blackwing_descent_10n_magmaw_diagnostic"
MALORIAK = "blackwing_descent_10n_maloriak_diagnostic"


def shard_row(cohort: str, profile: str, lockout: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    return {"cohort_id": cohort, "runtime_profile_id": profile, "scenario_id": profile, "pool_tag": profile,
            "raid": "blackwing_descent", "mode": "10N", "boss_key": cohort.split("_")[-2] if "_" in cohort else "",
            "lockout": lockout, **extra}


MALORIAK_LOCKOUT = {"raid": "blackwing_descent", "difficulty": "10N",
                    "precompleted_boss_keys": ["magmaw", "omnotron"], "seed_boss_argument": "magmaw,omnotron"}


def proof_plan(**watchdog: Any) -> sc.ShardRunPlan:
    return sc.ShardRunPlan(
        shards=(
            sc.parse_shard(shard_row("blackwing_descent_10n_magmaw_c0", MAGMAW)),
            sc.parse_shard(shard_row("blackwing_descent_10n_maloriak_c0", MALORIAK, MALORIAK_LOCKOUT)),
        ),
        watchdog=sc.WatchdogPolicy.from_mapping(watchdog),
    )


class FakeWorld:
    """A console that answers botauto commands per cohort, with server noise."""

    def __init__(self, *, capacity: int = 6, threads: int = 1, isolation: bool = True, pid: int = 4242,
                 lockout_action: str = "botauto_lockout", foreign_on: str = "",
                 bad_profiles: frozenset[str] = frozenset(), lockout_failure: str = "",
                 sticky_active: frozenset[str] = frozenset()):
        self.capacity, self.threads, self.isolation, self.pid = capacity, threads, isolation, pid
        self.lockout_action = lockout_action
        self.foreign_on = foreign_on
        self.bad_profiles = bad_profiles
        self.lockout_failure = lockout_failure  # "seed_refused" | "wrong_bosses" | ""
        self.sticky_active = sticky_active  # cohorts whose stop never takes effect
        self.timeouts: list[tuple[str, int]] = []
        self.failed = False
        self.cohorts: dict[str, dict[str, Any]] = {"default": {"active": False, "attempt": 0}}
        self.lockouts: dict[str, dict[str, Any]] = {}
        self.commands: list[str] = []
        self.next_instance = 100
        self.in_flight = 0
        self.max_in_flight = 0
        self._guard = threading.Lock()

    def reply(self, *payloads: dict[str, Any]) -> str:
        noise = "2026-09-25 12:00:00 BotWorld unsolicited log line map=669\n{\"server_note\":\"no cohort\"}\n"
        return noise + "\n".join(json.dumps(payload, separators=(",", ":")) for payload in payloads) + "\nTC> "

    def status(self, cohort: str) -> dict[str, Any]:
        state = self.cohorts[cohort]
        return {"ok": True, "action": "botauto_status", "cohort_id": cohort, "server_epoch": 77,
                "attempt_id": state["attempt"], "active_profile": state.get("profile"), "active": state["active"],
                "active_bots": 10 if state["active"] else 0, "target_bots": 10,
                "raid_runtime": {"map_id": 669, "instance_id": state.get("instance", 0)}, "failure_reason": None}

    def __call__(self, command: str, timeout: int) -> tuple[str, int, bool]:
        with self._guard:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            time.sleep(0.001)
            self.commands.append(command)
            self.timeouts.append((command, timeout))
            return self.answer(command)
        finally:
            with self._guard:
                self.in_flight -= 1

    def answer(self, command: str) -> tuple[str, int, bool]:
        tokens = command.split()
        verb = tokens[1]
        if verb == "cohorts":
            rows = [{"cohort_id": cohort, "active": state["active"], "attempt_id": state["attempt"],
                     "lease_count": 10 if state["active"] else 0, "party_bot_count": 0}
                    for cohort, state in self.cohorts.items()]
            active = sum(row["active"] for row in rows)
            return self.reply({"ok": True, "action": "botauto_cohorts", "server_epoch": 77,
                               "server_process_id": self.pid, "max_active_cohorts": self.capacity,
                               "active_cohort_count": active, "map_worker_threads": self.threads,
                               "concurrent_admission_open": active < self.capacity,
                               "shard_isolation": self.isolation, "cohort_count": len(rows),
                               "cohorts": rows, "failure_reason": None}), 0, False
        cohort = tokens[2] if len(tokens) > 2 else ""
        if verb == "create":
            self.cohorts.setdefault(cohort, {"active": False, "attempt": 0})
            return self.reply({"ok": True, "action": "botauto_create", "cohort_id": cohort, "created": True,
                               "failure_reason": None}), 0, False
        if verb == "lockout":
            operation, cohort = tokens[2], tokens[3]
            if operation == "seed" and self.lockout_failure == "seed_refused":
                return self.reply({"ok": False, "action": "botauto_lockout_seed", "cohort_id": cohort,
                                   "instance_id": 0, "map_id": 0, "bosses_done": [],
                                   "failure_reason": "prerequisites_unavailable"}), 0, False
            if operation == "seed":
                raid, difficulty, bosses = tokens[4], tokens[5], tokens[6]
                if self.lockout_failure == "wrong_bosses":
                    bosses = bosses.split(",")[0]
                self.next_instance += 1
                self.lockouts[cohort] = {"instance_id": self.next_instance, "map_id": 669,
                                         "bosses_done": [] if bosses == "none" else bosses.split(","),
                                         "raid": raid, "difficulty": difficulty}
            if operation == "clear":
                self.lockouts.pop(cohort, None)
                return self.reply({"ok": True, "action": f"{self.lockout_action}", "cohort_id": cohort,
                                   "failure_reason": None}), 0, False
            lockout = self.lockouts[cohort]
            return self.reply({"ok": True, "action": self.lockout_action, "cohort_id": cohort,
                               "instance_id": lockout["instance_id"], "map_id": lockout["map_id"],
                               "bosses_done": lockout["bosses_done"], "failure_reason": None}), 0, False
        if cohort not in self.cohorts:
            return self.reply({"ok": False, "action": f"botauto_{verb}", "cohort_id": cohort,
                               "failure_reason": "unknown_cohort"}), 0, False
        state = self.cohorts[cohort]
        extra = []
        if self.foreign_on and command.startswith(self.foreign_on):
            extra.append({"ok": True, "action": "botauto_status", "cohort_id": "some_other_c9", "active": True})
        if verb == "start" and tokens[3] in self.bad_profiles:
            # SelectRuntimeProfile's refusal carries no cohort_id and ends the command.
            return self.reply({"ok": False, "action": "botauto_profile", "failure_reason": "unknown_profile",
                               "profile": tokens[3]}), 0, False
        if verb == "start":
            state.update(active=True, attempt=state["attempt"] + 1, profile=tokens[3])
            seeded = self.lockouts.get(cohort)
            if seeded:
                state["instance"] = seeded["instance_id"]
            else:
                self.next_instance += 1
                state["instance"] = self.next_instance
            return self.reply(self.status(cohort), *extra), 0, False
        if verb == "status":
            return self.reply(self.status(cohort), *extra), 0, False
        if verb == "diagnose":
            return self.reply({"ok": True, "action": "botauto_diagnose", "cohort_id": cohort,
                               "diagnosis_schema_version": 1, "bots": []}, *extra), 0, False
        if verb == "trace":
            entry = {"sequence": len(self.commands), "action": "validation_route_hold", "situation": "regroup",
                     "result": "waiting", "reason_code": "fake_console"}
            return self.reply({"ok": True, "action": "botauto_trace", "cohort_id": cohort,
                               "trace_schema_version": 1,
                               "bots": [{"bot_guid": 30001, "entries": [entry]}]}, *extra), 0, False
        if verb == "combatlog":
            return self.reply({"ok": False, "action": "botauto_combatlog", "cohort_id": cohort,
                               "failure_reason": "fake_console"}), 0, False
        if verb == "stop":
            state["active"] = cohort in self.sticky_active
            return self.reply({"ok": True, "action": "botauto_stop", "cohort_id": cohort,
                               "failure_reason": None}), 0, False
        raise AssertionError(command)


def fast_watchdog(sleep_sec: float = 0.05):
    return lambda seconds: time.sleep(min(seconds, sleep_sec))


# ---------------------------------------------------------------- plan


def test_run_plan_and_package_c_plan_parse(tmp_path: Path) -> None:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"schema": sc.RUN_PLAN_SCHEMA, "watchdog": {"heartbeat_sec": 15},
                                "shards": [shard_row("blackwing_descent_10n_magmaw_c0", MAGMAW),
                                           shard_row("blackwing_descent_10n_maloriak_c0", MALORIAK,
                                                     MALORIAK_LOCKOUT)]}))
    plan = sc.load_run_plan(path)
    assert [spec.cohort_id for spec in plan.shards] == ["blackwing_descent_10n_magmaw_c0",
                                                        "blackwing_descent_10n_maloriak_c0"]
    assert plan.watchdog.heartbeat_sec == 15
    assert plan.shards[0].lockout is None and not plan.shards[0].seeded
    assert plan.shards[1].lockout.seed_argument == "magmaw,omnotron"
    assert plan.shards[1].lockout.difficulty == "10n"

    source = tmp_path / "source.json"
    row = shard_row("blackwing_descent_10n_nefarian_c1", "blackwing_descent_10n_nefarian_c1_diagnostic",
                    {"raid": "blackwing_descent", "difficulty": "10N", "precompleted_boss_keys": [],
                     "seed_boss_argument": "none"})
    source.write_text(json.dumps({"schema": sc.SOURCE_PLAN_SCHEMA, "shards": [row]}))
    with pytest.raises(sc.ShardPlanError, match="--shard"):
        sc.load_run_plan(source)
    picked = sc.load_run_plan(source, select=["blackwing_descent_10n_nefarian_c1"])
    assert picked.shards[0].lockout.seed_argument == "none" and picked.shards[0].seeded


@pytest.mark.parametrize(("rows", "message"), [
    ([shard_row("magmaw", MAGMAW)], "does not follow"),
    ([shard_row("blackwing_descent_10n_magmaw_c0", MAGMAW)] * 2, "distinct cohort_id"),
    ([shard_row("blackwing_descent_10n_magmaw_c0", MAGMAW),
      shard_row("blackwing_descent_10n_magmaw_c1", MAGMAW)], "distinct profile"),
    ([shard_row("blackwing_descent_10n_magmaw_c0", "bwd_c1_diagnostic"),
      shard_row("blackwing_descent_10n_magmaw_c1", "bwd_c1_diagnostic_extra")], "contained in"),
    ([shard_row(f"blackwing_descent_10n_magmaw_c{index}", f"profile_{index}_x") for index in range(7)],
     "1..6 shards"),
    ([shard_row("blackwing_descent_10n_magmaw_c0", MAGMAW, dict(MALORIAK_LOCKOUT, seed_boss_argument="none"))],
     "seed_boss_argument"),
    ([shard_row("blackwing_descent_10n_magmaw_c0", MAGMAW, dict(MALORIAK_LOCKOUT, difficulty="normal"))],
     "difficulty"),
    ([shard_row("blackwing_descent_10n_magmaw_c0", MAGMAW, dict(
        MALORIAK_LOCKOUT, precompleted_boss_keys=["magmaw"], seed_boss_argument="magmaw"))], "its own boss"),
])
def test_invalid_plans_are_refused(tmp_path: Path, rows: list[dict[str, Any]], message: str) -> None:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps({"schema": sc.RUN_PLAN_SCHEMA, "shards": rows}))
    with pytest.raises(sc.ShardPlanError, match=message):
        sc.load_run_plan(path)


def test_shard_config_isolates_learning_and_owns_the_console(tmp_path: Path) -> None:
    base = tmp_path / "base.conf"
    base.write_text("BotWorld.AutoStart = 1\nBotLearning.Enable = 1\nBotSemantic.UpdateOutcomeStats = 1\n"
                    "MapUpdate.Threads = 4\nConsole.Enable = 0\n")
    config = sc.write_shard_config(base, tmp_path / "run")
    text = config.read_text()
    for key, value in sc.SHARD_CONFIG_OVERRIDES:
        assert f"{key} = {value}" in text
    assert "BotLearning.Enable = 1" not in text and "MapUpdate.Threads = 4" not in text
    assert base.read_text().startswith("BotWorld.AutoStart = 1")  # base config untouched


def test_shard_script_is_addressed_and_starts_the_profile() -> None:
    spec = proof_plan().shards[1]
    script = sc.shard_script(spec, sc.WatchdogPolicy())
    lines = script.splitlines()
    assert lines[0] == f".botauto start {spec.cohort_id} {MALORIAK}"
    assert all(line.split()[2] == spec.cohort_id for line in lines)
    assert f".botauto trace {spec.cohort_id} all 128 delta" in lines
    assert lines[-1] == f".botauto stop {spec.cohort_id}"
    assert not any(line.startswith((".botexp", "server")) for line in lines)
    startup, heartbeat, cleanup = harness.heartbeat_commands_from_script(script)
    assert startup == [lines[0]] and cleanup[-1] == lines[-1]
    assert harness.expected_cohort_id_from_heartbeat_commands(heartbeat) == spec.cohort_id


# ---------------------------------------------------------------- demux and transport


def test_demultiplex_keeps_only_the_cohort_raw_payloads() -> None:
    mine = '{"ok":true,"action":"botauto_status","cohort_id":"a_10n_b_c0","ratio":1.500}'
    chunk = '{"ok":true,"action":"botauto_combatlog_chunk","cohort_id":"a_10n_b_c0","data":"e30="}'
    other = '{"ok":true,"action":"botauto_trace","cohort_id":"a_10n_b_c1"}'
    output = f"log line\n{mine}\n{{\"note\":1}}\n{other}\n{chunk}\nTC> "
    split = sc.demultiplex(output, "a_10n_b_c0")
    assert split.text == f"{mine}\n{chunk}\n"  # raw bytes, float formatting preserved
    assert split.kept == 2 and split.unscoped == 1 and split.cross_cohort
    assert split.foreign == [{"action": "botauto_trace", "cohort_id": "a_10n_b_c1", "ok": True}]
    assert not sc.demultiplex(f"{mine}\n", "a_10n_b_c0").cross_cohort


def test_shard_transport_refuses_foreign_commands_and_replies(tmp_path: Path) -> None:
    world = FakeWorld(foreign_on=".botauto diagnose")
    world.cohorts["blackwing_descent_10n_magmaw_c0"] = {"active": True, "attempt": 1, "instance": 7}
    spec = proof_plan().shards[0]
    transport = sc.ShardTransport(sc.SerializedConsole(world), spec, tmp_path)
    for command in (".botauto status", ".botauto status blackwing_descent_10n_maloriak_c0",
                    f".botauto rotations reload {spec.cohort_id}", f".botauto start {spec.cohort_id}",
                    f".botauto start {spec.cohort_id} {MALORIAK}", ".botexp summary"):
        assert transport(command, 5) == ("", 1, False)
    assert world.commands == []  # nothing reached the console
    output, code, _ = transport(f".botauto status {spec.cohort_id}", 5)
    assert code == 0 and harness.bot_status_snapshot(output)["active"] is True
    assert "unsolicited" not in output and "server_note" not in output
    output, code, _ = transport(f".botauto diagnose {spec.cohort_id} all", 5)
    assert code == 1 and "some_other_c9" not in output  # cross-cohort reply fails the command
    assert transport.refused_commands == 6 and transport.cross_cohort_replies == 1
    rows = [json.loads(line) for line in (tmp_path / "demux_rejections.jsonl").read_text().splitlines()]
    assert {row["reason"] for row in rows} == {"command_refused", "foreign_payloads"}


def test_serialized_console_never_overlaps_and_journals(tmp_path: Path) -> None:
    world = FakeWorld()
    console = sc.SerializedConsole(world, tmp_path / "journal.jsonl")

    def worker(index: int) -> None:
        for _ in range(20):
            console(".botauto cohorts", 5, owner=f"shard{index}")

    threads = [threading.Thread(target=worker, args=(index,)) for index in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert world.max_in_flight == 1
    rows = [json.loads(line) for line in (tmp_path / "journal.jsonl").read_text().splitlines()]
    assert [row["sequence"] for row in rows] == list(range(1, 121))
    assert {row["owner"] for row in rows} == {f"shard{index}" for index in range(6)}


def test_console_transport_markers_cover_lockout_replies() -> None:
    marker = sc.ShardConsoleTransport.reply_marker
    for action in ("botauto_lockout", "botauto_lockout_seed", "botauto_lockout_status"):
        assert marker(".botauto lockout seed c x 10n none").search(f'{{"action":"{action}"}}'.encode())
    assert marker(".botauto start c p").search(b'{"action":"botauto_status"}')
    assert not marker(".botauto combatlog c").search(b'{"action":"botauto_combatlog_chunk"}')
    assert marker(".botauto combatlog c").search(b'{"action":"botauto_combatlog_complete"}')
    with pytest.raises(ValueError):
        marker("server shutdown force 0")


# ---------------------------------------------------------------- native contracts


@pytest.mark.parametrize(("change", "message"), [
    ({"max_active_cohorts": 1}, "admits 1 active"),
    ({"active_cohort_count": 1}, "already has active"),
    ({"map_worker_threads": 2}, "MapUpdate.Threads"),
    ({"shard_isolation": False}, "ShardIsolation"),
    ({"server_process_id": 1}, "owned worldserver"),
])
def test_capacity_gate(change: dict[str, Any], message: str) -> None:
    registry = {"max_active_cohorts": 6, "active_cohort_count": 0, "map_worker_threads": 1,
                "shard_isolation": True, "server_process_id": 4242}
    sc.require_shard_capacity(registry, 2, server_pid=4242)
    with pytest.raises(sc.ShardRunError, match=message):
        sc.require_shard_capacity({**registry, **change}, 2, server_pid=4242)


@pytest.mark.parametrize(("reply", "message"), [
    ({"ok": False, "failure_reason": "no_prerequisite_file"}, "failure_reason=no_prerequisite_file"),
    ({"bosses_done": ["magmaw"]}, "bosses_done"),
    ({"instance_id": 0}, "instance_id"),
    ({"cohort_id": "someone_else_c9"}, "names cohort"),
])
def test_lockout_contract_fails_closed(reply: dict[str, Any], message: str) -> None:
    spec = proof_plan().shards[1]
    good = {"ok": True, "action": "botauto_lockout", "cohort_id": spec.cohort_id, "instance_id": 5,
            "map_id": 669, "bosses_done": ["omnotron", "magmaw"], "failure_reason": None}
    assert sc.verify_lockout(good, spec) == {"instance_id": 5, "map_id": 669, "bosses_done": ["magmaw", "omnotron"]}
    with pytest.raises(sc.ShardRunError, match=message):
        sc._lockout_reply(json.dumps({**good, **reply}) + "\nTC> ", spec)
        sc.verify_lockout({**good, **reply}, spec)


# ---------------------------------------------------------------- full run


def test_two_shards_run_isolated_through_the_real_watchdog(tmp_path: Path) -> None:
    world = FakeWorld(lockout_action="botauto_lockout_seed")
    console = sc.SerializedConsole(world, tmp_path / "console_journal.jsonl")
    plan = proof_plan(heartbeat_sec=1, no_progress_window_sec=1, emergency_timeout_sec=30)
    coordinator = sc.ShardCoordinator(plan, console, tmp_path, scenario_dir=SCENARIOS, server_pid=4242,
                                      run_id="test-run", sleep=fast_watchdog())
    summary = coordinator.run()

    assert summary["terminal_reason"] == "completed", summary
    assert world.max_in_flight == 1
    magmaw, maloriak = (tmp_path / "shards" / spec.cohort_id for spec in plan.shards)
    # Create every cohort, seed only the seeded shard (then read it back), before any start.
    first_start = next(index for index, command in enumerate(world.commands)
                       if command.startswith(".botauto start"))
    setup = world.commands[:first_start]
    assert setup[0] == ".botauto cohorts"
    assert ".botauto create blackwing_descent_10n_magmaw_c0" in setup
    assert (".botauto lockout seed blackwing_descent_10n_maloriak_c0 blackwing_descent 10n magmaw,omnotron"
            in setup)
    assert ".botauto lockout status blackwing_descent_10n_maloriak_c0" in setup
    assert not any("lockout" in command and "magmaw_c0" in command for command in world.commands)
    assert world.commands[-3:] == [".botauto cohorts", ".botauto lockout clear blackwing_descent_10n_maloriak_c0",
                                   ".botauto cohorts"]

    # Each shard's run dir holds only its own cohort's payloads and heartbeats.
    for shard_dir, spec in ((magmaw, plan.shards[0]), (maloriak, plan.shards[1])):
        report = json.loads((shard_dir / "report.json").read_text())
        identity = report["shard_identity"]
        assert identity["cohort_id"] == spec.cohort_id and identity["run_id"] == "test-run"
        assert identity["runtime_profile_id"] == spec.profile
        assert report["expected_cohort_id"] == spec.cohort_id
        # A fake world never progresses: the unchanged watchdog stops on its plateau rule.
        assert report["completion_reason"] == "semantic_progress_plateau_watchdog"
        assert report["heartbeat_index"] > 1
        heartbeats = (shard_dir / "heartbeat_events.jsonl").read_text()
        other = plan.shards[1 - plan.shards.index(spec)].cohort_id
        assert spec.cohort_id in heartbeats and other not in heartbeats
        assert not (shard_dir / "demux_rejections.jsonl").exists()
        assert json.loads((shard_dir / "validation_route_manifest.json").read_text())["scenario_id"] == spec.scenario_id
    fresh = json.loads((magmaw / "report.json").read_text())["shard_identity"]
    seeded = json.loads((maloriak / "report.json").read_text())["shard_identity"]
    assert fresh["lockout_mode"] == "fresh" and fresh["precompleted_boss_keys"] == []
    assert fresh["diagnostic_only_assistance"] is False
    assert seeded["lockout_mode"] == "seeded" and seeded["precompleted_boss_keys"] == ["magmaw", "omnotron"]
    assert seeded["diagnostic_only_assistance"] is True and seeded["certifies_predecessors"] is False
    assert seeded["instance_id"] == seeded["seeded_instance_id"] != fresh["instance_id"]
    lockout = json.loads((maloriak / "lockout.json").read_text())
    assert lockout["seed"] == lockout["readback"] and lockout["certifies_predecessors"] is False

    isolation = summary["isolation"]
    assert isolation["distinct_instance_ids"] and isolation["seeded_instances_entered"]
    assert isolation["foreign_payloads"] == isolation["cross_cohort_replies"] == isolation["refused_commands"] == 0
    assert summary["teardown"] == {"verified": True, "active_cohorts": [], "stopped_by_teardown": [],
                                   "lockouts_cleared": {"blackwing_descent_10n_maloriak_c0":
                                                        {"ok": True, "failure_reason": None}}}
    assert summary["console"]["healthy"] and summary["infrastructure_failures"] == []
    assert [row["lockout_cleared"] for row in summary["shards"]] == [None, {"ok": True, "failure_reason": None}]
    assert summary["ingest"][0][-4:] == ["--label", "<label>", "--run-dir", str(magmaw)]
    assert summary["ingest"][0][summary["ingest"][0].index("--scenario") + 1] == "blackwing_descent_10n_magmaw"
    owners = {json.loads(line)["owner"] for line in (tmp_path / "console_journal.jsonl").read_text().splitlines()}
    assert owners == {"coordinator", *(spec.cohort_id for spec in plan.shards)}
    assert json.loads((tmp_path / "shard_run.json").read_text())["run_id"] == "test-run"


def test_admission_failure_stops_what_was_admitted(tmp_path: Path) -> None:
    world = FakeWorld(capacity=1)
    console = sc.SerializedConsole(world)
    summary = sc.ShardCoordinator(proof_plan(), console, tmp_path, scenario_dir=SCENARIOS,
                                  sleep=fast_watchdog()).run()
    assert summary["terminal_reason"] == "infrastructure_loss"
    assert "admits 1 active" in summary["error"]
    assert not any(command.startswith((".botauto create", ".botauto start")) for command in world.commands)


def test_finalized_shard_run_dir_is_ingestible(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.raid_program import scoreboard_core, scoreboard_record

    # Informational fidelity reads the character database; keep the test offline.
    monkeypatch.setattr(harness, "attach_encounter_fidelity", lambda *args, **kwargs: None)
    monkeypatch.setattr(scoreboard_record, "fidelity_fields", lambda *args, **kwargs: {})
    world = FakeWorld()
    plan = sc.ShardRunPlan(shards=proof_plan().shards[:1],
                           watchdog=sc.WatchdogPolicy(heartbeat_sec=1, no_progress_window_sec=1,
                                                      emergency_timeout_sec=30))
    worldserver = tmp_path / "worldserver"
    worldserver.write_bytes(b"fake worldserver")
    config = sc.write_shard_config(ROOT / "trinity-worldserver-test.conf", tmp_path / "config")
    context = sc.LiveContext(worldserver=worldserver, config=config,
                             provisioning_config=ROOT / "experiments/configs/validation_provisioning_cata_001.json",
                             gear_profiles=ROOT / "dataset/validation_gear_profiles/profiles.json",
                             runtime_asset_closure={}, stage_preflight={}, preparation={})
    run_root = tmp_path / "run"
    run_root.mkdir()
    coordinator = sc.ShardCoordinator(plan, sc.SerializedConsole(world), run_root, scenario_dir=SCENARIOS,
                                      run_id="ingest-run", sleep=fast_watchdog())
    coordinator.finalizer = lambda outcome: sc.finalize_live_shard(
        outcome, context, plan.watchdog, coordinator.server, coordinator.run_id)
    summary = coordinator.run()
    assert summary["terminal_reason"] == "completed", summary
    shard_dir = run_root / "shards" / plan.shards[0].cohort_id
    report = json.loads((shard_dir / "report.json").read_text())
    assert report["shard_identity"]["cohort_id"] == plan.shards[0].cohort_id
    assert report["evidence_envelope"]["scope_ids"]["cohort_id"] == plan.shards[0].cohort_id
    assert report["native_gameplay_outcome"]["native_clear"] is False
    assert (shard_dir / "worldserver_output.log").is_file()

    target = scoreboard_core.load_target(ROOT, "blackwing_descent_10n_magmaw")
    record = scoreboard_record.record_from_run_dir(
        ROOT, target, scenario="blackwing_descent_10n_magmaw", label="shardtest", kill_id="shardtest-k1",
        run_dir=shard_dir, timeline_path=None, source_commit=None)
    assert record["schema"] == scoreboard_core.KILL_SCHEMA
    assert record["run_dir"] == str(shard_dir)
    assert record["native_clear"] is False and record["outcome"] in {"infrastructure_failure", "gameplay_failure"}


def test_one_failing_shard_never_stops_the_others(tmp_path: Path) -> None:
    world = FakeWorld()
    plan = proof_plan(heartbeat_sec=1, no_progress_window_sec=1, emergency_timeout_sec=30)

    def watchdog(transport, command, *args, **kwargs):
        if transport.spec.cohort_id.endswith("maloriak_c0"):
            raise RuntimeError("synthetic watchdog fault")
        return harness.run_transport_completion_watchdog(transport, command, *args, **kwargs)

    summary = sc.ShardCoordinator(plan, sc.SerializedConsole(world), tmp_path, scenario_dir=SCENARIOS,
                                  watchdog=watchdog, sleep=fast_watchdog()).run()
    by_id = {row["cohort_id"]: row for row in summary["shards"]}
    assert by_id["blackwing_descent_10n_maloriak_c0"]["error"] == "RuntimeError: synthetic watchdog fault"
    assert by_id["blackwing_descent_10n_magmaw_c0"]["completion_reason"] == "semantic_progress_plateau_watchdog"
    assert ".botauto stop blackwing_descent_10n_maloriak_c0" in world.commands
    assert summary["teardown"]["verified"] is True


def test_interruption_closes_every_shard_transport(tmp_path: Path) -> None:
    world = FakeWorld()
    spec = proof_plan().shards[0]
    event = threading.Event()
    transport = sc.ShardTransport(sc.SerializedConsole(world), spec, tmp_path, event)
    event.set()
    assert transport(f".botauto status {spec.cohort_id}", 5) == ("", 1, False)
    assert world.commands == []


def test_admission_failure_never_touches_uncreated_cohorts(tmp_path: Path) -> None:
    world = FakeWorld(threads=2)
    summary = sc.ShardCoordinator(proof_plan(), sc.SerializedConsole(world), tmp_path,
                                  scenario_dir=SCENARIOS).run()
    assert "MapUpdate.Threads" in summary["error"]
    assert world.commands == [".botauto cohorts"]


@pytest.mark.parametrize(("capacity", "admitted"), [(1, False), (2, True), (6, True)])
def test_isolation_canary_needs_room_for_its_pair(tmp_path: Path, capacity: int, admitted: bool) -> None:
    """The two-cohort canary still runs once the server admits six shards."""
    from tools.raid_program import shared_instance_validation as canary

    assert canary.CANARY_COHORTS == 2
    row = {"ok": True, "action": "botauto_cohorts", "server_epoch": 5, "server_process_id": 7,
           "max_active_cohorts": capacity, "active_cohort_count": 0,
           "cohorts": [{"cohort_id": "default", "active": False, "attempt_id": 0, "lease_count": 0}]}
    recorder = canary._RawRecorder(tmp_path / "raw.jsonl", lambda: 0.0)

    def check() -> None:
        canary._registry(lambda command, timeout: (json.dumps(row) + "\n", 0, False), recorder,
                         phase="admission", timeout=5, expected_epoch=5, expected_process_id=7,
                         expected_active=set())

    if admitted:
        check()
    else:
        with pytest.raises(canary.SharedInstanceValidationError, match="registry_identity_mismatch"):
            check()


def test_harness_route_kinds_come_from_the_route_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.raid_program import canonical_route_catalog as catalog

    source = (ROOT / "tools/bot_ml/run_live_bot_validation.py").read_text(encoding="utf-8")
    assert '{"trash", "boss", "travel", "regroup", "descent"}' not in source
    loader = source[source.index("def load_validation_routes_for_scenario"):]
    loader = loader[:loader.index("\ndef ")]
    assert "from tools.raid_program.canonical_route_catalog import ALLOWED_ROUTE_KINDS" in loader
    # The accepted Magmaw scenario has no interaction rows: its route is the
    # same with or without package D's `interaction` kind.
    magmaw = [row["kind"] for row in harness.load_validation_routes_for_scenario(SCENARIOS, MAGMAW)]
    assert sorted(magmaw) == ["boss", "regroup", "trash", "trash"]
    monkeypatch.setattr(catalog, "ALLOWED_ROUTE_KINDS", catalog.ALLOWED_ROUTE_KINDS | {"interaction"})
    assert [row["kind"] for row in harness.load_validation_routes_for_scenario(SCENARIOS, MAGMAW)] == magmaw
    nefarian = harness.load_validation_routes_for_scenario(SCENARIOS, "blackwing_descent_10n_nefarian_diagnostic")
    assert "interaction" in {row["kind"] for row in nefarian}



# ---------------------------------------------------------------- review fixes


def test_unknown_profile_is_a_failed_start_that_ends_the_watchdog(tmp_path: Path) -> None:
    world = FakeWorld(bad_profiles=frozenset({MALORIAK}))
    plan = proof_plan(heartbeat_sec=1, no_progress_window_sec=1, emergency_timeout_sec=30,
                      transition_timeout_sec=7)
    summary = sc.ShardCoordinator(plan, sc.SerializedConsole(world), tmp_path, scenario_dir=SCENARIOS,
                                  sleep=fast_watchdog()).run()
    by_id = {row["cohort_id"]: row for row in summary["shards"]}
    maloriak = by_id["blackwing_descent_10n_maloriak_c0"]
    assert maloriak["failed_starts"] == 1
    shard = tmp_path / "shards" / "blackwing_descent_10n_maloriak_c0"
    rejections = [json.loads(line) for line in (shard / "demux_rejections.jsonl").read_text().splitlines()]
    assert {"reason": "start_failed"}.items() <= rejections[0].items()
    # No heartbeat was polled for the refused shard; only its cleanup ran.
    maloriak_commands = [command for command in world.commands if "maloriak_c0" in command and "lockout" not in command]
    assert not any(command.startswith((".botauto diagnose", ".botauto trace")) for command in maloriak_commands)
    assert ".botauto stop blackwing_descent_10n_maloriak_c0" in maloriak_commands
    assert by_id["blackwing_descent_10n_magmaw_c0"]["completion_reason"] == "semantic_progress_plateau_watchdog"
    # Start and stop exchanges are bounded by the transition budget, not the emergency cap.
    for command, timeout in world.timeouts:
        if command.startswith((".botauto start", ".botauto stop")):
            assert timeout <= 7, (command, timeout)


def test_start_reply_keeps_unscoped_profile_refusal(tmp_path: Path) -> None:
    world = FakeWorld(bad_profiles=frozenset({MAGMAW}))
    world.cohorts["blackwing_descent_10n_magmaw_c0"] = {"active": False, "attempt": 0}
    spec = proof_plan().shards[0]
    transport = sc.ShardTransport(sc.SerializedConsole(world), spec, tmp_path, transition_timeout_sec=9)
    output, code, timed_out = transport(f".botauto start {spec.cohort_id} {MAGMAW}", 3600)
    assert (code, timed_out) == (1, False)
    assert '"unknown_profile"' in output and "unsolicited" not in output
    assert world.timeouts[-1] == (f".botauto start {spec.cohort_id} {MAGMAW}", 9)
    output, code, _ = transport(f".botauto status {spec.cohort_id}", 3600)
    assert code == 0 and world.timeouts[-1][1] == 3600  # heartbeats keep their own budget
    assert sc.ShardConsoleTransport.reply_marker(".botauto start c p").search(
        b'{"ok":false,"action":"botauto_profile","failure_reason":"unknown_profile"}')


@pytest.mark.parametrize("failure", ["seed_refused", "wrong_bosses"])
def test_failed_seed_is_still_cleared(tmp_path: Path, failure: str) -> None:
    world = FakeWorld(lockout_failure=failure)
    summary = sc.ShardCoordinator(proof_plan(), sc.SerializedConsole(world), tmp_path,
                                  scenario_dir=SCENARIOS, sleep=fast_watchdog()).run()
    assert summary["terminal_reason"] == "infrastructure_loss"
    assert "lockout of blackwing_descent_10n_maloriak_c0 failed" in summary["error"]
    assert ".botauto lockout clear blackwing_descent_10n_maloriak_c0" in world.commands
    assert not any(command.startswith(".botauto start") for command in world.commands)
    receipt = json.loads((tmp_path / "shards" / "blackwing_descent_10n_maloriak_c0" / "lockout.json").read_text())
    assert receipt["state"] == "pending" and "failed" in receipt["error"]
    assert receipt["command"].startswith(".botauto lockout seed blackwing_descent_10n_maloriak_c0 ")
    assert summary["teardown"]["lockouts_cleared"]["blackwing_descent_10n_maloriak_c0"]["ok"] is True


def test_every_seeded_shard_is_cleared_when_a_later_seed_fails(tmp_path: Path) -> None:
    rows = (sc.parse_shard(shard_row("blackwing_descent_10n_nefarian_c0", "blackwing_descent_10n_nefarian_diagnostic",
                                     {"raid": "blackwing_descent", "difficulty": "10n",
                                      "precompleted_boss_keys": ["magmaw"]})),
            sc.parse_shard(shard_row("blackwing_descent_10n_maloriak_c0", MALORIAK, MALORIAK_LOCKOUT)))

    class SecondSeedFails(FakeWorld):
        def answer(self, command: str) -> tuple[str, int, bool]:
            if command.startswith(".botauto lockout seed blackwing_descent_10n_maloriak_c0"):
                return "partial reply without prompt", 1, True
            return super().answer(command)

    world = SecondSeedFails()
    summary = sc.ShardCoordinator(sc.ShardRunPlan(shards=rows), sc.SerializedConsole(world), tmp_path,
                                  scenario_dir=SCENARIOS, sleep=fast_watchdog()).run()
    assert summary["terminal_reason"] == "infrastructure_loss"
    cleared = [command for command in world.commands if command.startswith(".botauto lockout clear")]
    assert cleared == [".botauto lockout clear blackwing_descent_10n_nefarian_c0",
                       ".botauto lockout clear blackwing_descent_10n_maloriak_c0"]


class LatchedTransport(FakeWorld):
    """Latches failed (a console reply that never finished) after N exchanges."""

    def __init__(self, fail_after: int, **kwargs: Any):
        super().__init__(**kwargs)
        self.fail_after = fail_after

    def answer(self, command: str) -> tuple[str, int, bool]:
        if self.failed or len(self.commands) > self.fail_after:
            self.failed = True
            return "", 1, True
        return super().answer(command)


def test_latched_console_failure_is_infrastructure_loss(tmp_path: Path) -> None:
    world = LatchedTransport(fail_after=12)
    plan = proof_plan(heartbeat_sec=1, no_progress_window_sec=1, emergency_timeout_sec=30)
    summary = sc.ShardCoordinator(plan, sc.SerializedConsole(world), tmp_path, scenario_dir=SCENARIOS,
                                  sleep=fast_watchdog()).run()
    assert summary["terminal_reason"] == "infrastructure_loss"
    assert "console_transport_failed" in summary["infrastructure_failures"]
    assert summary["console"]["healthy"] is False


def test_worldserver_exit_is_infrastructure_loss(tmp_path: Path) -> None:
    class Exited:
        def poll(self) -> int:
            return 139

    world = FakeWorld()
    world.process = Exited()
    plan = proof_plan(heartbeat_sec=1, no_progress_window_sec=1, emergency_timeout_sec=30)
    summary = sc.ShardCoordinator(plan, sc.SerializedConsole(world), tmp_path, scenario_dir=SCENARIOS,
                                  sleep=fast_watchdog()).run()
    assert summary["terminal_reason"] == "infrastructure_loss"
    assert summary["console"] == {"transport_failed": False, "server_exited": True, "server_exit_code": 139,
                                  "healthy": False}


def test_unverified_teardown_is_infrastructure_loss(tmp_path: Path) -> None:
    world = FakeWorld(sticky_active=frozenset({"blackwing_descent_10n_magmaw_c0"}))
    plan = proof_plan(heartbeat_sec=1, no_progress_window_sec=1, emergency_timeout_sec=30)
    summary = sc.ShardCoordinator(plan, sc.SerializedConsole(world), tmp_path, scenario_dir=SCENARIOS,
                                  sleep=fast_watchdog()).run()
    assert summary["terminal_reason"] == "infrastructure_loss"
    assert summary["teardown"]["verified"] is False
    assert summary["teardown"]["stopped_by_teardown"] == ["blackwing_descent_10n_magmaw_c0"]
    assert summary["teardown"]["active_cohorts"] == ["blackwing_descent_10n_magmaw_c0"]
    assert summary["infrastructure_failures"] == ["teardown_unverified"]


def test_main_exits_non_zero_on_infrastructure_loss(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps({"schema": sc.RUN_PLAN_SCHEMA,
                                     "shards": [shard_row("blackwing_descent_10n_magmaw_c0", MAGMAW)]}))
    outside = Path("/tmp") / f"shard-main-{time.time_ns()}"
    for reason, code in (("infrastructure_loss", 1), ("completed", 0)):
        monkeypatch.setattr(sc, "run_live", lambda plan, **kwargs: {"terminal_reason": reason, "shards": []})
        assert sc.main(["--plan", str(plan_path), "--output-dir", str(outside)]) == code


def test_cohort_log_lines_select_the_shard(tmp_path: Path) -> None:
    log = tmp_path / "worldserver.console.log"
    log.write_text(
        "BotWorld validation prepare reset profile=p cohort=blackwing_descent_10n_magmaw_c0 attempt=1\n"
        "BotWorld validation prepare reset profile=p cohort=blackwing_descent_10n_magmaw_c01 attempt=1\n"
        "BotRaidLockout seeded cohort=blackwing_descent_10n_maloriak_c0 map=669 instance=101 difficulty=10n\n"
        "BotWorld boss death callback scope=failure entry=41570 map=669 instance=101 alive=0\n"
        "BotWorld boss death callback scope=failure entry=41570 map=669 instance=1011 alive=0\n"
        '{"ok":true,"action":"botauto_status","cohort_id":"blackwing_descent_10n_magmaw_c0"}\n'
        "TC> unrelated\n")
    magmaw = sc.cohort_log_lines(log, "blackwing_descent_10n_magmaw_c0", set())
    assert magmaw == ["BotWorld validation prepare reset profile=p cohort=blackwing_descent_10n_magmaw_c0 attempt=1\n"]
    maloriak = sc.cohort_log_lines(log, "blackwing_descent_10n_maloriak_c0", {101})
    assert [line.split()[0:2] for line in maloriak] == [["BotRaidLockout", "seeded"], ["BotWorld", "boss"]]
    assert "instance=1011" not in "".join(maloriak)


def test_coordinator_copies_cohort_log_lines(tmp_path: Path) -> None:
    log = tmp_path / "worldserver.console.log"
    log.write_text("x cohort=blackwing_descent_10n_magmaw_c0 y\nz cohort=blackwing_descent_10n_maloriak_c0 w\n")
    plan = proof_plan(heartbeat_sec=1, no_progress_window_sec=1, emergency_timeout_sec=30)
    run_root = tmp_path / "run"
    run_root.mkdir()
    sc.ShardCoordinator(plan, sc.SerializedConsole(FakeWorld()), run_root, scenario_dir=SCENARIOS,
                        sleep=fast_watchdog(), console_log=log).run()
    for spec in plan.shards:
        lines = (run_root / "shards" / spec.cohort_id / "worldserver_cohort_lines.log").read_text().splitlines()
        assert len(lines) == 1 and spec.cohort_id in lines[0]


def test_attempt_finalization_docstring_is_accurate() -> None:
    doc = harness.AttemptFinalization.__doc__ or ""
    assert "byte-for-byte" not in doc
    assert "only this cohort's replies" in doc
