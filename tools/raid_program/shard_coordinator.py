"""Drive one worldserver with up to six boss shards at once.

docs/bot_raids/full_raid_parallel_shards.md, package B. Each shard is one
native cohort in its own raid instance (a fresh one, or a lockout seeded
through package A's `.botauto lockout` commands). This coordinator is the
only writer to worldserver stdin: every shard's commands pass through one
serialized console, are addressed to that shard's cohort, and every reply is
demultiplexed so a shard's run directory holds only its own cohort's payloads.

Each shard runs the unchanged completion watchdog of
tools/bot_ml/run_live_bot_validation.py (heartbeats, semantic liveness,
repeated-decision and death-loop rules, emergency cap) and is finalized by the
same code as a single-cohort run (report.json, combat artifacts, heartbeats).
The evidence is not byte-identical to a single-cohort run: a shard's
worldserver_output.log holds only its own cohort's replies, and server log
lines that name the cohort or its instance are copied to
worldserver_cohort_lines.log. Each run directory can be recorded with

    pixi run python -m tools.raid_program.scoreboard ingest --scenario S --label L --run-dir DIR

Round 1 keeps MapUpdate.Threads = 1. A seeded lockout is diagnostic assistance:
the shard identity records it and it never certifies a predecessor kill.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
import time
import uuid
from typing import Any, Callable, Mapping, Sequence

from tools.bot_ml import run_live_bot_validation as harness
from tools.raid_program.shared_instance_console import ConsoleTransport

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_PLAN_SCHEMA = "raid_shard_run_plan_v1"
SOURCE_PLAN_SCHEMA = "raid_shard_plan_v1"  # tools.raid_program.raid_shard_plan (package C)
RUN_SCHEMA = "raid_shard_run_v1"
IDENTITY_SCHEMA = "raid_shard_identity_v1"
LOCKOUT_SCHEMA = "raid_shard_lockout_receipt_v1"
MAX_SHARDS = 6
COHORT_ID_RE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*_(?:10|25)[nh]_[a-z][a-z0-9_]*_c[0-9]+")
TOKEN_RE = re.compile(r"[A-Za-z0-9._-]{1,64}")
BOSS_KEY_RE = re.compile(r"[a-z][a-z0-9_]*")
DIFFICULTIES = ("10n", "25n", "10h", "25h")
# Verbs a shard's watchdog may send; each must name the shard's cohort.
SHARD_VERBS = frozenset({"start", "status", "diagnose", "trace", "combatlog", "stop"})
# Unkeyed adaptive state stays frozen while shards share one worldserver
# (BotExperienceLearningPolicy::ShardIsolationEnabled, BotSemantic writes).
# Server-side re-provisioning on start would rewrite every validation
# character, including other live shards'; provisioning happens once, offline.
SHARD_CONFIG_OVERRIDES: tuple[tuple[str, str], ...] = (
    ("BotWorld.AutoStart", "0"),
    ("BotWorld.RuntimeProfile", '""'),
    ("Console.Enable", "1"),
    ("MapUpdate.Threads", "1"),
    ("BotWorld.ShardIsolation", "1"),
    ("BotLearning.Enable", "0"),
    ("BotLearning.AllowGlobalMemoryFallback", "0"),
    ("BotSemantic.UpdateOutcomeStats", "0"),
    ("BotWorld.ValidationProvisionOnPrepare", "0"),
    ("BotWorld.SafePositionMemorySec", "900"),
)
CommandTransport = Callable[[str, int], tuple[str, int, bool]]


class ShardPlanError(ValueError):
    pass


class ShardRunError(RuntimeError):
    pass


# ---------------------------------------------------------------- plan


@dataclass(frozen=True)
class LockoutRequest:
    raid: str
    difficulty: str
    boss_keys: tuple[str, ...]

    @property
    def seed_argument(self) -> str:
        return ",".join(self.boss_keys) if self.boss_keys else "none"


@dataclass(frozen=True)
class ShardSpec:
    cohort_id: str
    profile: str
    scenario_id: str
    pool_tag: str
    raid: str
    mode: str
    boss_key: str
    lockout: LockoutRequest | None = None

    @property
    def seeded(self) -> bool:
        return self.lockout is not None

    @property
    def precompleted_boss_keys(self) -> tuple[str, ...]:
        return self.lockout.boss_keys if self.lockout else ()


@dataclass(frozen=True)
class WatchdogPolicy:
    heartbeat_sec: int = 30
    no_progress_window_sec: int = 180
    max_repeated_decisions: int = 20
    max_death_loops: int = 3
    emergency_timeout_sec: int = 3600
    transition_timeout_sec: int = 180
    selector: str = "all"
    trace_limit: int = 128

    @classmethod
    def from_mapping(cls, row: Mapping[str, Any] | None) -> "WatchdogPolicy":
        row = dict(row or {})
        unknown = set(row) - set(cls.__dataclass_fields__)
        if unknown:
            raise ShardPlanError(f"unknown watchdog fields: {sorted(unknown)}")
        policy = cls(**row)
        for name in ("heartbeat_sec", "no_progress_window_sec", "max_repeated_decisions",
                     "max_death_loops", "emergency_timeout_sec", "transition_timeout_sec", "trace_limit"):
            value = getattr(policy, name)
            if type(value) is not int or value < 1:
                raise ShardPlanError(f"watchdog {name} must be a positive integer")
        if not isinstance(policy.selector, str) or not TOKEN_RE.fullmatch(policy.selector):
            raise ShardPlanError("watchdog selector is invalid")
        return policy


@dataclass(frozen=True)
class ShardRunPlan:
    shards: tuple[ShardSpec, ...]
    watchdog: WatchdogPolicy = WatchdogPolicy()


def _text(row: Mapping[str, Any], name: str, default: str = "") -> str:
    value = row.get(name, default)
    if value is None:
        value = default
    if not isinstance(value, str):
        raise ShardPlanError(f"{name} must be a string")
    return value


def parse_lockout(row: Any) -> LockoutRequest | None:
    """None is a fresh instance (today's admission); a mapping is a seeded lockout."""
    if row is None:
        return None
    if not isinstance(row, Mapping):
        raise ShardPlanError("lockout must be an object or null")
    difficulty = _text(row, "difficulty").lower()
    if difficulty not in DIFFICULTIES:
        raise ShardPlanError(f"lockout difficulty must be one of {DIFFICULTIES}")
    keys = row.get("precompleted_boss_keys", row.get("bosses_done", []))
    if not isinstance(keys, list) or any(not isinstance(key, str) or not BOSS_KEY_RE.fullmatch(key) for key in keys):
        raise ShardPlanError("precompleted_boss_keys must be a list of boss keys")
    if len(set(keys)) != len(keys):
        raise ShardPlanError("precompleted_boss_keys has duplicates")
    request = LockoutRequest(raid=_text(row, "raid"), difficulty=difficulty, boss_keys=tuple(keys))
    if not BOSS_KEY_RE.fullmatch(request.raid):
        raise ShardPlanError("lockout raid is invalid")
    declared = row.get("seed_boss_argument")
    if declared is not None and declared != request.seed_argument:
        raise ShardPlanError("seed_boss_argument does not match precompleted_boss_keys")
    return request


def parse_shard(row: Mapping[str, Any]) -> ShardSpec:
    if not isinstance(row, Mapping):
        raise ShardPlanError("shard must be an object")
    cohort = _text(row, "cohort_id")
    if not COHORT_ID_RE.fullmatch(cohort) or len(cohort) > 64:
        raise ShardPlanError(f"cohort_id {cohort!r} does not follow <raid>_<size><diff>_<boss>_c<copy>")
    profile = _text(row, "runtime_profile_id") or _text(row, "profile") or f"{cohort}_diagnostic"
    scenario = _text(row, "scenario_id") or profile
    pool = _text(row, "pool_tag") or scenario
    mode = _text(row, "mode").lower()
    spec = ShardSpec(
        cohort_id=cohort, profile=profile, scenario_id=scenario, pool_tag=pool,
        raid=_text(row, "raid"), mode=mode, boss_key=_text(row, "boss_key"),
        lockout=parse_lockout(row.get("lockout")),
    )
    for name in ("profile", "scenario_id", "pool_tag"):
        if not TOKEN_RE.fullmatch(getattr(spec, name)):
            raise ShardPlanError(f"{name} of {cohort} is invalid")
    if spec.mode and spec.mode not in DIFFICULTIES:
        raise ShardPlanError(f"mode of {cohort} must be one of {DIFFICULTIES}")
    if spec.lockout and spec.boss_key and spec.boss_key in spec.lockout.boss_keys:
        raise ShardPlanError(f"{cohort} seeds its own boss as done")
    return spec


def validate_plan(plan: ShardRunPlan, *, capacity: int = MAX_SHARDS) -> None:
    shards = plan.shards
    limit = min(capacity, MAX_SHARDS)
    if not 1 <= len(shards) <= limit:
        raise ShardPlanError(f"a shard run needs 1..{limit} shards, got {len(shards)}")
    for name in ("cohort_id", "profile", "pool_tag"):
        values = [getattr(shard, name) for shard in shards]
        if len(set(values)) != len(values):
            raise ShardPlanError(f"shards must have distinct {name}")
    # Pool resets match experiment tags by substring (tag_predicate), so one
    # shard's tag inside another's would reset the other shard's characters.
    for left in shards:
        for right in shards:
            if left is not right and left.pool_tag in right.pool_tag:
                raise ShardPlanError(f"pool tag {left.pool_tag} is contained in {right.pool_tag}")


def load_run_plan(path: Path, *, select: Sequence[str] = (),
                  watchdog: Mapping[str, Any] | None = None) -> ShardRunPlan:
    """Read a raid_shard_run_plan_v1, or pick shards from package C's raid_shard_plan_v1."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    schema = payload.get("schema") if isinstance(payload, Mapping) else None
    if schema not in {RUN_PLAN_SCHEMA, SOURCE_PLAN_SCHEMA}:
        raise ShardPlanError(f"{path} is neither {RUN_PLAN_SCHEMA} nor {SOURCE_PLAN_SCHEMA}")
    rows = payload.get("shards")
    if not isinstance(rows, list):
        raise ShardPlanError("plan has no shards list")
    shards = [parse_shard(row) for row in rows]
    if select:
        by_id = {shard.cohort_id: shard for shard in shards}
        missing = [cohort for cohort in select if cohort not in by_id]
        if missing:
            raise ShardPlanError(f"plan has no shards {missing}")
        shards = [by_id[cohort] for cohort in select]
    elif schema == SOURCE_PLAN_SCHEMA:
        raise ShardPlanError("select the shards to run from a raid_shard_plan_v1 (--shard)")
    policy = WatchdogPolicy.from_mapping(watchdog if watchdog is not None else payload.get("watchdog"))
    plan = ShardRunPlan(shards=tuple(shards), watchdog=policy)
    validate_plan(plan)
    return plan


# ---------------------------------------------------------------- console


class ShardConsoleTransport(ConsoleTransport):
    """Owned-console transport whose reply markers also cover package A's lockout verb."""

    @staticmethod
    def reply_marker(command: str) -> re.Pattern[bytes]:
        tokens = command.lstrip(".").split()
        if len(tokens) < 2 or tokens[0] != "botauto":
            raise ValueError("coordinator transport accepts botauto commands only")
        verb = tokens[1]
        if verb == "start":
            # `.botauto start <cohort> <profile>` first prints the profile
            # selection; an unknown profile ends the command right there.
            actions = rb"(?:botauto_status|botauto_start|botauto_profile)"
        elif verb == "combatlog":
            actions = rb"(?:botauto_combatlog|botauto_combatlog_complete|botauto_combatlog_delta)"
        elif verb == "calibrate":
            actions = (rb"(?:botauto_calibrate|botauto_calibrate_start|botauto_calibrate_stop"
                       rb"|botauto_calibrate_status|botauto_calibrate_status_complete)")
        elif verb == "lockout":
            actions = rb"botauto_lockout(?:_[a-z_]+)?"
        else:
            actions = re.escape(("botauto_" + verb).encode())
        return re.compile(rb'"action"\s*:\s*"' + actions + rb'"')

    @classmethod
    def adopt(cls, transport: ConsoleTransport,
              max_response_bytes: int = 256 * 1024 * 1024) -> "ShardConsoleTransport":
        return cls(transport.process, transport.log_path, max_response_bytes)

    def __call__(self, command: str, timeout_sec: int) -> tuple[str, int, bool]:
        # Same framing and failure latch as ConsoleTransport; only the marker differs.
        if self.failed or self.process.poll() is not None:
            return "", 1, False
        if "\n" in command or "\r" in command or "\0" in command:
            raise ValueError("one console command required")
        marker = self.reply_marker(command)
        deadline = time.monotonic() + timeout_sec
        output = bytearray()
        with self.log_path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            assert self.process.stdin is not None
            try:
                self.process.stdin.write((command.lstrip(".") + "\n").encode())
                self.process.stdin.flush()
            except (BrokenPipeError, OSError):
                self.failed = True
                return "", 1, False
            while time.monotonic() < deadline:
                output.extend(stream.read(1024 * 1024))
                if len(output) > self.max_response_bytes:
                    self.failed = True
                    return "console response exceeded byte budget", 1, False
                found = marker.search(output)
                if found and b"TC>" in output[found.end():]:
                    return output.decode(errors="replace"), 0, False
                if self.process.poll() is not None:
                    self.failed = True
                    return output.decode(errors="replace"), 1, False
                time.sleep(0.05)
        self.failed = True
        return output.decode(errors="replace"), 1, True


class SerializedConsole:
    """The single stdin owner: one command in flight, every exchange journaled."""

    def __init__(self, transport: CommandTransport, journal_path: Path | None = None):
        self._transport = transport
        self._lock = threading.Lock()
        self._journal_path = journal_path
        self.exchanges = 0

    def __call__(self, command: str, timeout_sec: int, *,
                 owner: str = "coordinator") -> tuple[str, int, bool]:
        with self._lock:
            started = time.time()
            try:
                output, returncode, timed_out = self._transport(command, timeout_sec)
            except Exception as error:  # a transport fault is a failed exchange, never a crash
                output, returncode, timed_out = f"transport_error:{type(error).__name__}:{error}", 1, False
            self.exchanges += 1
            if self._journal_path is not None:
                row = {"sequence": self.exchanges, "owner": owner, "command": command,
                       "sent_at_unix": round(started, 3), "elapsed_sec": round(time.time() - started, 3),
                       "returncode": returncode, "timed_out": timed_out,
                       "response_bytes": len(output or "")}
                with self._journal_path.open("a", encoding="utf-8") as stream:
                    stream.write(json.dumps(row, sort_keys=True) + "\n")
        return output or "", returncode, timed_out

    def health(self) -> dict[str, Any]:
        """Whether the console can still be trusted: no latched failure, server alive."""
        failed = bool(getattr(self._transport, "failed", False))
        process = getattr(self._transport, "process", None)
        exit_code = process.poll() if process is not None else None
        return {"transport_failed": failed, "server_exited": exit_code is not None,
                "server_exit_code": exit_code, "healthy": not failed and exit_code is None}


# ---------------------------------------------------------------- demultiplexing


def payload_spans(output: str) -> list[tuple[int, int, dict[str, Any]]]:
    """Top-level JSON objects with their raw text positions."""
    decoder = json.JSONDecoder()
    spans: list[tuple[int, int, dict[str, Any]]] = []
    index = 0
    while True:
        start = output.find("{", index)
        if start < 0:
            return spans
        try:
            payload, end = decoder.raw_decode(output, start)
        except json.JSONDecodeError:
            index = start + 1
            continue
        if isinstance(payload, dict):
            spans.append((start, end, payload))
        index = end


@dataclass
class Demultiplexed:
    text: str
    kept: int = 0
    foreign: list[dict[str, Any]] = field(default_factory=list)
    unscoped: int = 0

    @property
    def cross_cohort(self) -> bool:
        return any(str(row.get("action") or "").startswith("botauto_") for row in self.foreign)


def demultiplex(output: str, cohort_id: str, adopt_unscoped: frozenset[str] = frozenset()) -> Demultiplexed:
    """Keep the raw text of this cohort's payloads; count everything else.

    Every botauto reply carries its cohort_id (AppendGenericRuntimeIdentityJson,
    UnknownCohortJson, combat-log frames). Server log lines and other cohorts'
    payloads stay in the shared console log only. `adopt_unscoped` names reply
    actions printed without a cohort_id (a failed profile selection) that the
    serialized console proves belong to this shard's own command.
    """
    kept: list[str] = []
    result = Demultiplexed(text="")
    for start, end, payload in payload_spans(output):
        owner = payload.get("cohort_id")
        if owner == cohort_id or (owner is None and payload.get("action") in adopt_unscoped):
            kept.append(output[start:end])
        elif owner is None:
            result.unscoped += 1
        else:
            result.foreign.append({key: payload.get(key) for key in ("action", "cohort_id", "ok")})
    result.kept = len(kept)
    result.text = "\n".join(kept) + ("\n" if kept else "")
    return result


class ShardTransport:
    """One shard's addressed view of the shared console (the watchdog's execute_command)."""

    # Admission and cleanup are bounded transitions, never the emergency budget.
    TRANSITION_VERBS = frozenset({"start", "stop"})
    START_REPLIES = frozenset({"botauto_profile", "botauto_start"})

    def __init__(self, console: SerializedConsole, spec: ShardSpec, shard_dir: Path,
                 interrupted: threading.Event | None = None, transition_timeout_sec: int = 180):
        self.console = console
        self.spec = spec
        self.shard_dir = shard_dir
        self.interrupted = interrupted or threading.Event()
        self.transition_timeout_sec = transition_timeout_sec
        self.failed_starts = 0
        self.rejections_path = shard_dir / "demux_rejections.jsonl"
        self.foreign_payloads = 0
        self.cross_cohort_replies = 0
        self.refused_commands = 0

    def check(self, command: str) -> None:
        tokens = command.split()
        if (any(character in command for character in "\r\n\x00") or len(tokens) < 3
                or tokens[0] != ".botauto" or tokens[1] not in SHARD_VERBS
                or tokens[2] != self.spec.cohort_id):
            raise ShardRunError(f"shard {self.spec.cohort_id} may not send {command!r}")
        if tokens[1] == "start" and tokens[3:] != [self.spec.profile]:
            raise ShardRunError(f"shard {self.spec.cohort_id} must start profile {self.spec.profile}")

    def __call__(self, command: str, timeout_sec: int) -> tuple[str, int, bool]:
        if self.interrupted.is_set():
            # Operator interruption: the watchdog ends on this failed exchange;
            # the owned console's shutdown then removes every bot.
            return "", 1, False
        try:
            self.check(command)
        except ShardRunError as error:
            self.refused_commands += 1
            self._reject({"reason": "command_refused", "command": command, "detail": str(error)})
            return "", 1, False
        verb = command.split()[1]
        if verb in self.TRANSITION_VERBS:
            timeout_sec = max(1, min(int(timeout_sec), self.transition_timeout_sec))
        output, returncode, timed_out = self.console(command, timeout_sec, owner=self.spec.cohort_id)
        split = demultiplex(output, self.spec.cohort_id,
                            self.START_REPLIES if verb == "start" else frozenset())
        if split.foreign:
            self.foreign_payloads += len(split.foreign)
            self._reject({"reason": "foreign_payloads", "command": command, "payloads": split.foreign})
        if split.cross_cohort:
            # A reply addressed to another cohort inside this shard's exchange
            # would attribute one shard's state to another: fail the command.
            self.cross_cohort_replies += 1
            return split.text, returncode or 1, timed_out
        if verb == "start" and not returncode and not timed_out and not self.started(split.text):
            # A refused profile or admission is a failed start: the watchdog
            # stops and cleans up instead of polling an inactive cohort.
            self.failed_starts += 1
            self._reject({"reason": "start_failed", "command": command})
            return split.text, 1, timed_out
        return split.text, returncode, timed_out

    def started(self, text: str) -> bool:
        rows = harness.parse_json_objects(text)
        if any(row.get("action") in self.START_REPLIES and row.get("ok") is not True for row in rows):
            return False
        return any(row.get("action") == "botauto_status" and row.get("ok") is True
                   and row.get("cohort_id") == self.spec.cohort_id for row in rows)

    def _reject(self, row: dict[str, Any]) -> None:
        row = {"cohort_id": self.spec.cohort_id, "at_unix": round(time.time(), 3), **row}
        with self.rejections_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, sort_keys=True) + "\n")


# ---------------------------------------------------------------- native contracts


def one_payload(output: str, action_prefix: str) -> dict[str, Any]:
    rows = [row for row in harness.parse_json_objects(output)
            if str(row.get("action") or "").startswith(action_prefix)]
    if len(rows) != 1:
        raise ShardRunError(f"expected one {action_prefix} reply, got {len(rows)}")
    return rows[0]


def read_registry(console: SerializedConsole, timeout: int) -> dict[str, Any]:
    output, code, timed_out = console(".botauto cohorts", timeout)
    if code or timed_out:
        raise ShardRunError("cohort registry transport failed")
    registry = one_payload(output, "botauto_cohorts")
    if registry.get("action") != "botauto_cohorts" or registry.get("ok") is not True:
        raise ShardRunError("cohort registry reply is not ok")
    return registry


def require_shard_capacity(registry: Mapping[str, Any], shard_count: int, *,
                           server_pid: int | None = None) -> None:
    """The server must admit every shard at once, serialized, with frozen learning."""
    capacity = registry.get("max_active_cohorts")
    if type(capacity) is not int or capacity < shard_count:
        raise ShardRunError(f"server admits {capacity} active cohorts, plan needs {shard_count}")
    if registry.get("active_cohort_count") != 0:
        raise ShardRunError("server already has active cohorts")
    threads = registry.get("map_worker_threads")
    if type(threads) is not int or threads > 1:
        raise ShardRunError("parallel shards require MapUpdate.Threads <= 1 in round 1")
    if registry.get("shard_isolation") is not True:
        raise ShardRunError("server does not report BotWorld.ShardIsolation")
    if server_pid is not None and registry.get("server_process_id") != server_pid:
        raise ShardRunError("native responder does not match the owned worldserver")


def create_cohort(console: SerializedConsole, spec: ShardSpec, timeout: int) -> dict[str, Any]:
    output, code, timed_out = console(f".botauto create {spec.cohort_id}", timeout)
    reply = one_payload(output, "botauto_create")
    if code or timed_out or reply.get("ok") is not True or reply.get("cohort_id") != spec.cohort_id:
        raise ShardRunError(f"cohort {spec.cohort_id} was not created")
    return reply


def _lockout_reply(output: str, spec: ShardSpec) -> dict[str, Any]:
    reply = one_payload(output, "botauto_lockout")
    if "cohort_id" in reply and reply.get("cohort_id") != spec.cohort_id:
        raise ShardRunError(f"lockout reply names cohort {reply.get('cohort_id')}, not {spec.cohort_id}")
    return reply


def verify_lockout(reply: Mapping[str, Any], spec: ShardSpec) -> dict[str, Any]:
    """Contract: ok, instance_id, map_id, bosses_done and failure_reason (package A)."""
    assert spec.lockout is not None
    done = reply.get("bosses_done")
    instance = reply.get("instance_id")
    map_id = reply.get("map_id")
    problems = []
    if reply.get("ok") is not True:
        problems.append(f"failure_reason={reply.get('failure_reason')}")
    if type(instance) is not int or instance <= 0:
        problems.append("instance_id")
    if type(map_id) is not int or map_id <= 0:
        problems.append("map_id")
    if not isinstance(done, list) or sorted(map(str, done)) != sorted(spec.lockout.boss_keys):
        problems.append(f"bosses_done={done}")
    if problems:
        raise ShardRunError(f"lockout of {spec.cohort_id} failed: {', '.join(problems)}")
    return {"instance_id": instance, "map_id": map_id, "bosses_done": sorted(map(str, done))}


def seed_command(spec: ShardSpec) -> str:
    assert spec.lockout is not None
    lockout = spec.lockout
    return (f".botauto lockout seed {spec.cohort_id} {lockout.raid} "
            f"{lockout.difficulty} {lockout.seed_argument}")


def pending_lockout(spec: ShardSpec) -> dict[str, Any]:
    """Recorded before the seed is sent: from here on teardown must clear it."""
    return {"schema": LOCKOUT_SCHEMA, "state": "pending", "command": seed_command(spec),
            "diagnostic_only_assistance": True, "certifies_predecessors": False}


def seed_lockout(console: SerializedConsole, spec: ShardSpec, timeout: int) -> dict[str, Any]:
    """Seed, then read back before any bot acts; both must match the request."""
    command = seed_command(spec)
    output, code, timed_out = console(command, timeout)
    if code or timed_out:
        raise ShardRunError(f"lockout seed transport failed for {spec.cohort_id}")
    seeded = verify_lockout(_lockout_reply(output, spec), spec)
    output, code, timed_out = console(f".botauto lockout status {spec.cohort_id}", timeout)
    if code or timed_out:
        raise ShardRunError(f"lockout readback transport failed for {spec.cohort_id}")
    readback = verify_lockout(_lockout_reply(output, spec), spec)
    if readback != seeded:
        raise ShardRunError(f"lockout readback of {spec.cohort_id} differs from the seed")
    return {"schema": LOCKOUT_SCHEMA, "state": "verified", "command": command, "seed": seeded,
            "readback": readback, "diagnostic_only_assistance": True, "certifies_predecessors": False}


def clear_lockout(console: SerializedConsole, spec: ShardSpec, timeout: int) -> dict[str, Any]:
    output, code, timed_out = console(f".botauto lockout clear {spec.cohort_id}", timeout)
    try:
        reply = _lockout_reply(output, spec)
    except ShardRunError as error:
        return {"ok": False, "error": str(error), "returncode": code, "timed_out": timed_out}
    return {"ok": reply.get("ok") is True and not code and not timed_out,
            "failure_reason": reply.get("failure_reason")}


def shard_script(spec: ShardSpec, policy: WatchdogPolicy) -> str:
    """The harness watchdog script, addressed to the shard, starting its profile."""
    script = harness.command_script(
        selector=policy.selector, trace_limit=policy.trace_limit, start=True, stop=True,
        exit_server=False, cohort_id=spec.cohort_id, trace_delta=True,
    )
    start = f".botauto start {spec.cohort_id}"
    lines = [f"{start} {spec.profile}" if line == start else line for line in script.splitlines()]
    if f"{start} {spec.profile}" not in lines:
        raise ShardRunError("watchdog script has no start command")
    return "\n".join(lines) + "\n"


def observed_instance(report: Mapping[str, Any] | None) -> tuple[int, int]:
    """(map_id, instance_id) of the shard's raid runtime in its last status."""
    status = (report or {}).get("status") or {}
    raid = status.get("raid_runtime") if isinstance(status, Mapping) else None
    raid = raid if isinstance(raid, Mapping) else {}
    return int(raid.get("map_id") or 0), int(raid.get("instance_id") or 0)


def shard_identity(spec: ShardSpec, *, run_id: str, server: Mapping[str, Any],
                   lockout: Mapping[str, Any] | None, observed: tuple[int, int]) -> dict[str, Any]:
    """What a scoreboard record needs so it never mixes shards."""
    seed = (lockout or {}).get("seed") or {}
    return {
        "schema": IDENTITY_SCHEMA,
        "run_id": run_id,
        "cohort_id": spec.cohort_id,
        "runtime_profile_id": spec.profile,
        "scenario_id": spec.scenario_id,
        "pool_tag": spec.pool_tag,
        "raid": spec.raid,
        "mode": spec.mode,
        "boss_key": spec.boss_key,
        "lockout_mode": "seeded" if spec.seeded else "fresh",
        "precompleted_boss_keys": list(spec.precompleted_boss_keys),
        "seeded_instance_id": seed.get("instance_id"),
        "map_id": observed[0] or seed.get("map_id"),
        "instance_id": observed[1] or seed.get("instance_id"),
        "diagnostic_only_assistance": spec.seeded,
        "certifies_predecessors": False,
        "server_epoch": server.get("server_epoch"),
        "server_process_id": server.get("server_process_id"),
    }


# ---------------------------------------------------------------- run


@dataclass
class ShardRoute:
    routes: list[dict[str, Any]]
    manifest_path: Path
    manifest: dict[str, Any]
    context: dict[str, Any]

    @property
    def first(self) -> dict[str, Any]:
        return self.routes[0] if self.routes else {}


def load_shard_route(spec: ShardSpec, scenario_dir: Path, shard_dir: Path) -> ShardRoute:
    routes = harness.load_validation_routes_for_scenario(scenario_dir, spec.scenario_id)
    if not routes:
        raise ShardPlanError(f"scenario {spec.scenario_id} has no executable route rows")
    manifest_path, manifest = harness.write_validation_route_manifest(shard_dir, spec.scenario_id, routes)
    context = harness.route_validation_context(spec.scenario_id, routes[0], include_segment=False)
    return ShardRoute(routes, manifest_path, manifest, context)


@dataclass
class ShardOutcome:
    spec: ShardSpec
    shard_dir: Path
    route: ShardRoute
    transport: ShardTransport
    lockout: dict[str, Any] | None = None
    output: str = ""
    returncode: int = 1
    timed_out: bool = False
    command: list[str] = field(default_factory=list)
    error: str = ""
    watchdog_report: dict[str, Any] | None = None
    lockout_cleared: dict[str, Any] | None = None
    report: dict[str, Any] | None = None
    exit_code: int = 1

    def summary(self) -> dict[str, Any]:
        report = self.report or self.watchdog_report or {}
        outcome = report.get("native_gameplay_outcome") or {}
        identity = report.get("shard_identity") or {}
        return {
            "cohort_id": self.spec.cohort_id,
            "run_dir": str(self.shard_dir),
            "runtime_profile_id": self.spec.profile,
            "lockout": self.lockout,
            "lockout_cleared": self.lockout_cleared,
            "instance_id": identity.get("instance_id"),
            "map_id": identity.get("map_id"),
            "completion_reason": report.get("completion_reason"),
            "native_clear": bool(outcome.get("native_clear")),
            "returncode": self.returncode,
            "timed_out": self.timed_out,
            "exit_code": self.exit_code,
            "error": self.error,
            "foreign_payloads": self.transport.foreign_payloads,
            "cross_cohort_replies": self.transport.cross_cohort_replies,
            "refused_commands": self.transport.refused_commands,
            "failed_starts": self.transport.failed_starts,
        }


Watchdog = Callable[..., tuple[str, int, bool, list[str]]]
Finalizer = Callable[[ShardOutcome], tuple[dict[str, Any], int]]


class ShardCoordinator:
    """Create, seed, start, poll and stop every shard of one worldserver."""

    def __init__(self, plan: ShardRunPlan, console: SerializedConsole, run_root: Path, *,
                 scenario_dir: Path = REPO_ROOT / "dataset/validation_scenarios",
                 server_pid: int | None = None, run_id: str | None = None,
                 watchdog: Watchdog | None = None, finalizer: Finalizer | None = None,
                 sleep: Callable[[float], None] = time.sleep, console_log: Path | None = None):
        validate_plan(plan)
        self.plan = plan
        self.console = console
        self.run_root = run_root
        self.scenario_dir = scenario_dir
        self.server_pid = server_pid
        self.run_id = run_id or uuid.uuid4().hex
        self.watchdog = watchdog or harness.run_transport_completion_watchdog
        self.finalizer = finalizer
        self.sleep = sleep
        self.server: dict[str, Any] = {}
        self.outcomes: list[ShardOutcome] = []
        self.created: set[str] = set()
        self.interrupted = threading.Event()
        self.console_log = console_log

    def shard_dir(self, spec: ShardSpec) -> Path:
        return self.run_root / "shards" / spec.cohort_id

    def prepare_outcomes(self) -> None:
        for spec in self.plan.shards:
            shard_dir = self.shard_dir(spec)
            shard_dir.mkdir(parents=True, exist_ok=False)
            route = load_shard_route(spec, self.scenario_dir, shard_dir)
            transport = ShardTransport(self.console, spec, shard_dir, self.interrupted,
                                       self.plan.watchdog.transition_timeout_sec)
            self.outcomes.append(ShardOutcome(spec=spec, shard_dir=shard_dir, route=route, transport=transport))

    def admit(self) -> None:
        timeout = self.plan.watchdog.transition_timeout_sec
        registry = read_registry(self.console, timeout)
        require_shard_capacity(registry, len(self.plan.shards), server_pid=self.server_pid)
        self.server = {key: registry.get(key) for key in (
            "server_epoch", "server_process_id", "max_active_cohorts", "map_worker_threads", "shard_isolation")}
        for outcome in self.outcomes:
            create_cohort(self.console, outcome.spec, timeout)
            self.created.add(outcome.spec.cohort_id)
        for outcome in self.outcomes:
            if not outcome.spec.seeded:
                continue
            outcome.lockout = pending_lockout(outcome.spec)
            harness.write_json(outcome.shard_dir / "lockout.json", outcome.lockout)
            try:
                outcome.lockout = seed_lockout(self.console, outcome.spec, timeout)
            except ShardRunError as error:
                outcome.lockout["error"] = str(error)
                raise
            finally:
                harness.write_json(outcome.shard_dir / "lockout.json", outcome.lockout)

    def run_one(self, outcome: ShardOutcome) -> None:
        policy = self.plan.watchdog
        spec = outcome.spec
        command = ["shard_coordinator", self.run_id, spec.cohort_id, spec.profile]
        try:
            output, returncode, timed_out, command = self.watchdog(
                outcome.transport, command, policy.emergency_timeout_sec, shard_script(spec, policy),
                outcome.shard_dir, {}, outcome.route.context,
                validation_route_manifest=outcome.route.manifest,
                duration_policy="completion-watchdog",
                heartbeat_sec=policy.heartbeat_sec,
                no_progress_window_sec=policy.no_progress_window_sec,
                max_repeated_decisions=policy.max_repeated_decisions,
                max_death_loops=policy.max_death_loops,
                status_command=f".botauto status {spec.cohort_id}",
                sleep=self.sleep,
            )
            outcome.output, outcome.returncode, outcome.timed_out = output, returncode, timed_out
            outcome.command = list(command)
        except Exception as error:  # one shard's failure never stops the others' watchdogs
            outcome.error = f"{type(error).__name__}: {error}"
            outcome.command = command
            # Never leave a failed shard admitted (teardown verifies it).
            outcome.output += outcome.transport(f".botauto stop {spec.cohort_id}",
                                                policy.transition_timeout_sec)[0]

    def run_watchdogs(self) -> None:
        threads = [threading.Thread(target=self.run_one, args=(outcome,),
                                    name=f"shard-{outcome.spec.cohort_id}") for outcome in self.outcomes]
        for thread in threads:
            thread.start()
        try:
            while any(thread.is_alive() for thread in threads):
                for thread in threads:
                    thread.join(timeout=0.5)
        except KeyboardInterrupt:
            self.interrupted.set()
            for thread in threads:
                thread.join()
            raise

    def teardown(self) -> dict[str, Any]:
        """Stop every admitted shard, clear every lockout that reached its seed, verify."""
        timeout = self.plan.watchdog.transition_timeout_sec
        stopped: list[str] = []
        try:
            registry = read_registry(self.console, timeout)
            still_active = {row.get("cohort_id") for row in registry.get("cohorts") or []
                            if isinstance(row, Mapping) and row.get("active")}
        except ShardRunError:
            still_active = set(self.created)  # unknown state: stop everything this run created
        for outcome in self.outcomes:
            if outcome.spec.cohort_id in self.created and outcome.spec.cohort_id in still_active:
                self.console(f".botauto stop {outcome.spec.cohort_id}", timeout, owner="coordinator")
                stopped.append(outcome.spec.cohort_id)
        for outcome in self.outcomes:
            if outcome.lockout is not None and outcome.lockout_cleared is None:
                outcome.lockout_cleared = clear_lockout(self.console, outcome.spec, timeout)
        receipt: dict[str, Any] = {"stopped_by_teardown": stopped,
                                   "lockouts_cleared": {outcome.spec.cohort_id: outcome.lockout_cleared
                                                        for outcome in self.outcomes
                                                        if outcome.lockout is not None}}
        try:
            registry = read_registry(self.console, timeout)
        except ShardRunError as error:
            return {**receipt, "verified": False, "error": str(error)}
        active = sorted(row.get("cohort_id") for row in registry.get("cohorts") or []
                        if isinstance(row, Mapping) and row.get("active"))
        cleared = all((row or {}).get("ok") is True for row in receipt["lockouts_cleared"].values())
        return {**receipt, "verified": not active and registry.get("active_cohort_count") == 0 and cleared,
                "active_cohorts": active}

    def attach_identities(self) -> None:
        for outcome in self.outcomes:
            path = outcome.shard_dir / "report.json"
            report = None
            if path.is_file():
                try:
                    report = json.loads(path.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    report = None
            if report is not None:
                report["shard_identity"] = shard_identity(
                    outcome.spec, run_id=self.run_id, server=self.server,
                    lockout=outcome.lockout, observed=observed_instance(report))
            outcome.watchdog_report = report

    def isolation(self) -> dict[str, Any]:
        instances: dict[str, int] = {}
        for outcome in self.outcomes:
            identity = (outcome.report or outcome.watchdog_report or {}).get("shard_identity") or {}
            if identity.get("instance_id"):
                instances[outcome.spec.cohort_id] = int(identity["instance_id"])
        seeded_match = all(
            not outcome.lockout
            or instances.get(outcome.spec.cohort_id)
            in {None, ((outcome.lockout.get("seed") or {}).get("instance_id"))}
            for outcome in self.outcomes)
        return {
            "instance_ids": instances,
            "distinct_instance_ids": len(set(instances.values())) == len(instances),
            "seeded_instances_entered": seeded_match,
            "foreign_payloads": sum(outcome.transport.foreign_payloads for outcome in self.outcomes),
            "cross_cohort_replies": sum(outcome.transport.cross_cohort_replies for outcome in self.outcomes),
            "refused_commands": sum(outcome.transport.refused_commands for outcome in self.outcomes),
        }

    def finalize(self) -> None:
        for outcome in self.outcomes:
            if self.finalizer is not None:
                try:
                    outcome.report, outcome.exit_code = self.finalizer(outcome)
                except Exception as error:
                    outcome.error = outcome.error or f"finalize {type(error).__name__}: {error}"
            elif outcome.watchdog_report is not None:
                harness.write_json(outcome.shard_dir / "report.json", outcome.watchdog_report)
                outcome.report = outcome.watchdog_report

    def copy_cohort_log_lines(self) -> None:
        if self.console_log is None or not self.console_log.is_file():
            return
        for outcome in self.outcomes:
            identity = (outcome.report or outcome.watchdog_report or {}).get("shard_identity") or {}
            instances = {int(value) for value in (identity.get("instance_id"), identity.get("seeded_instance_id"))
                         if value}
            lines = cohort_log_lines(self.console_log, outcome.spec.cohort_id, instances)
            (outcome.shard_dir / "worldserver_cohort_lines.log").write_text("".join(lines), encoding="utf-8")

    def run(self) -> dict[str, Any]:
        summary: dict[str, Any] = {"schema": RUN_SCHEMA, "run_id": self.run_id,
                                   "started_utc": datetime.now(timezone.utc).isoformat(),
                                   "terminal_reason": "infrastructure_loss"}
        completed = False
        try:
            self.prepare_outcomes()
            self.admit()
            summary["server"] = self.server
            self.run_watchdogs()
            summary["teardown"] = self.teardown()
            self.attach_identities()
            self.finalize()
            self.copy_cohort_log_lines()
            summary["isolation"] = self.isolation()
            completed = True
        except KeyboardInterrupt:
            summary["terminal_reason"] = "interruption"
            self.interrupted.set()
            raise
        except (ShardRunError, ShardPlanError) as error:
            summary["error"] = str(error)
        finally:
            if "teardown" not in summary and (self.created or any(outcome.lockout for outcome in self.outcomes)):
                # Every failure path stops what was admitted and clears every
                # lockout that reached its seed command, pending or verified.
                summary["teardown"] = self.teardown()
            summary["console"] = self.console.health()
            infrastructure = [reason for reason, failed in (
                ("console_transport_failed", summary["console"]["transport_failed"]),
                ("worldserver_exited", summary["console"]["server_exited"]),
                ("teardown_unverified", "teardown" in summary and not summary["teardown"].get("verified")),
            ) if failed]
            summary["infrastructure_failures"] = infrastructure
            if completed:
                summary["terminal_reason"] = "infrastructure_loss" if infrastructure else "completed"
            summary["shards"] = [outcome.summary() for outcome in self.outcomes]
            summary["ingest"] = [ingest_command(outcome) for outcome in self.outcomes]
            summary["closed_utc"] = datetime.now(timezone.utc).isoformat()
            harness.write_json(self.run_root / "shard_run.json", summary)
        return summary


def cohort_log_lines(log_path: Path, cohort_id: str, instance_ids: set[int],
                     limit: int = 200_000) -> list[str]:
    """Server log lines naming the cohort (as a token) or one of its instances."""
    patterns = [re.compile(rf"(?<![A-Za-z0-9_.-]){re.escape(cohort_id)}(?![A-Za-z0-9_.-])")]
    patterns += [re.compile(rf"\binstance(?:_id)?[=:]\s*{instance}\b") for instance in sorted(instance_ids)]
    lines: list[str] = []
    with log_path.open("r", encoding="utf-8", errors="replace") as stream:
        for line in stream:
            if line.lstrip().startswith("{"):
                continue  # command replies live in the demultiplexed transcript
            if any(pattern.search(line) for pattern in patterns):
                lines.append(line if line.endswith("\n") else line + "\n")
                if len(lines) >= limit:
                    break
    return lines


def ingest_command(outcome: ShardOutcome) -> list[str]:
    """The scoreboard command that records this shard (the scenario needs a raid target)."""
    scenario = outcome.spec.scenario_id.removesuffix("_diagnostic")
    return ["pixi", "run", "python", "-m", "tools.raid_program.scoreboard", "ingest",
            "--scenario", scenario, "--label", "<label>", "--run-dir", str(outcome.shard_dir)]


# ---------------------------------------------------------------- live glue


def write_shard_config(base_config: Path, run_root: Path) -> Path:
    """The run's worldserver config: no autostart, console owned, shard isolation on."""
    config = harness.write_validation_config(base_config, run_root, autostart=False, console_enabled=True)
    text = config.read_text(encoding="utf-8")
    for key, value in SHARD_CONFIG_OVERRIDES:
        text = harness.upsert_trinity_config(text, key, value)
    config.write_text(text, encoding="utf-8")
    return config


@dataclass
class LiveContext:
    worldserver: Path
    config: Path
    provisioning_config: Path
    gear_profiles: Path
    runtime_asset_closure: dict[str, Any]
    stage_preflight: dict[str, Any]
    preparation: dict[str, Any]


def prepare_databases(plan: ShardRunPlan, *, config: Path, run_root: Path, provisioning_config: Path,
                      gear_profiles: Path, apply: bool) -> dict[str, Any]:
    """Provision every validation character once, then reset each shard's pool, before launch."""
    root = run_root / "preparation"
    provisioning = harness.prepare_validation_provisioning(
        root, provisioning_config, gear_profiles, config, apply=apply)
    harness.bind_validation_provisioning_sql(config, provisioning)
    resets = {spec.cohort_id: harness.prepare_bot_pool_reset(
        root / spec.cohort_id, config, [spec.pool_tag], apply=apply,
        reset_positions=False, reset_quests=True, reset_memory=True) for spec in plan.shards}
    return {"validation_provisioning": provisioning, "bot_pool_reset": resets}


def finalize_live_shard(outcome: ShardOutcome, context: LiveContext, policy: WatchdogPolicy,
                        server: Mapping[str, Any], run_id: str) -> tuple[dict[str, Any], int]:
    """Write the shard's run directory through the single-cohort finalizer."""
    spec = outcome.spec
    args = argparse.Namespace(
        output_dir=outcome.shard_dir, transport="shard", worldserver=context.worldserver,
        config=context.config, cohort_id=spec.cohort_id, session_profile=spec.profile,
        session_attempt_index=1, bot_pool_tag=[spec.pool_tag], selector=policy.selector,
        duration_policy="completion-watchdog", heartbeat_sec=policy.heartbeat_sec,
        no_progress_window_sec=policy.no_progress_window_sec,
        max_repeated_decision_count=policy.max_repeated_decisions,
        max_death_loop_count=policy.max_death_loops, observe_sec=policy.heartbeat_sec,
        timeout_sec=policy.emergency_timeout_sec, run_to_completion=False, preserve_worldserver=False,
        calibration_only=False, calibration_observation_mode="", calibration_reference_conditions=False,
        calibration_self_provided_baseline=False, calibration_mode="single_target_300",
        calibration_target_spec="protection_paladin", calibration_seed=1,
        role_calibration_policy=REPO_ROOT / "experiments/configs/all_spec_role_calibration_policy_v3.json",
        party_spec_target=[], party_pool_tag="", evidence_identity_manifest=None,
        validation_provisioning_config=context.provisioning_config, gear_profiles=context.gear_profiles,
        publish_batch=False, retain_published_batch=False,
    )
    lifecycle = {"transport": "shard", "cohort_id": spec.cohort_id, "attempt_index": 1,
                 "server_pid": server.get("server_process_id"), "server_epoch": server.get("server_epoch"),
                 "lockout": outcome.lockout, "lockout_cleared": outcome.lockout_cleared}
    attempt = harness.AttemptFinalization(
        output=outcome.output, returncode=outcome.returncode, timed_out=outcome.timed_out,
        command=outcome.command, watchdog_report=outcome.watchdog_report, scenario_reports={},
        validation_context=outcome.route.context, validation_route=outcome.route.first,
        validation_route_manifest=outcome.route.manifest,
        validation_route_manifest_path=outcome.route.manifest_path, config_autostart=False,
        effective_config=context.config, pool_tag_filter=spec.pool_tag, exact_party_specs=[],
        send_start_command=True,
        calibration_reference_preflight=harness.preflight_calibration_reference_binding(
            calibration_only=False, calibration_mode="single_target_300", target_spec="protection_paladin"),
        validation_scenario_stage_preflight=context.stage_preflight.get(spec.cohort_id, {}),
        runtime_asset_closure=context.runtime_asset_closure,
        preparation={"shared": context.preparation, "lockout": outcome.lockout},
        session_lifecycle=lifecycle,
    )
    report, code = harness.finalize_attempt_report(args, attempt, echo=False)
    if "shard_identity" not in report:  # no watchdog heartbeat: annotate the written report
        report["shard_identity"] = shard_identity(spec, run_id=run_id, server=server, lockout=outcome.lockout,
                                                  observed=observed_instance(report))
        harness.write_json(outcome.shard_dir / "report.json", report)
    return report, code


def preflight(plan: ShardRunPlan, *, config: Path, run_root: Path, scenario_dir: Path) -> dict[str, Any]:
    """Route/profile contracts, DVC stage currency and runtime assets, before any mutation."""
    from tools.raid_program.runtime_asset_closure import (
        add_runtime_asset_closure_arguments, enforce_runtime_asset_closure_from_args)
    from tools.raid_program.runtime_asset_launch import prepare_asset_arguments

    stage: dict[str, Any] = {}
    maps: dict[int, dict[str, Any]] = {}
    for spec in plan.shards:
        if spec.profile != spec.scenario_id or spec.pool_tag != spec.scenario_id:
            raise ShardPlanError(f"{spec.cohort_id}: runtime profile, scenario and pool tag must be one id")
        routes = harness.load_validation_routes_for_scenario(scenario_dir, spec.scenario_id)
        harness.validate_route_runtime_profile_contract(config, scenario_dir, spec.scenario_id, routes)
        stage[spec.cohort_id] = harness.preflight_validation_scenario_stage(
            scenario_dir, spec.scenario_id, profile_name=spec.profile, pool_tag=spec.pool_tag)
        maps.setdefault(int(routes[0].get("map_id") or 0), routes[0])
    closures = {}
    for map_id, route in maps.items():
        parser = argparse.ArgumentParser(add_help=False)
        add_runtime_asset_closure_arguments(parser)
        args = parser.parse_args([])
        args.config, args.output_dir = config, run_root
        prepare_asset_arguments(args, REPO_ROOT, route)
        closures[str(map_id)] = enforce_runtime_asset_closure_from_args(args, worldserver_config=args.config)
    return {"stage": stage, "runtime_asset_closure": closures}


def run_live(plan: ShardRunPlan, *, worldserver: Path, base_config: Path, run_root: Path,
             scenario_dir: Path, provisioning_config: Path, gear_profiles: Path) -> dict[str, Any]:
    from tools.raid_program.shared_instance_console import owned_console, verify_process_binary
    from tools.raid_program.shared_instance_fixture import sha256

    run_root.mkdir(parents=True, exist_ok=False)
    config = write_shard_config(base_config, run_root)
    checks = preflight(plan, config=config, run_root=run_root, scenario_dir=scenario_dir)
    binary_sha256 = sha256(worldserver)
    lifecycle: dict[str, Any] = {"server_started": False}
    preparation: dict[str, Any] = {}

    def before_launch() -> None:
        # Under the owner lock with no worldserver running: nothing live can be clobbered.
        preparation.update(prepare_databases(plan, config=config, run_root=run_root,
                                             provisioning_config=provisioning_config,
                                             gear_profiles=gear_profiles, apply=True))

    with owned_console(repository=REPO_ROOT, source=REPO_ROOT, binary=worldserver, config=config,
                       output_dir=run_root, before_launch=before_launch, lifecycle=lifecycle) as base:
        verify_process_binary(base.process, binary_sha256)
        console = SerializedConsole(ShardConsoleTransport.adopt(base), run_root / "console_journal.jsonl")
        context = LiveContext(worldserver=worldserver, config=config, provisioning_config=provisioning_config,
                              gear_profiles=gear_profiles,
                              runtime_asset_closure=checks["runtime_asset_closure"],
                              stage_preflight=checks["stage"], preparation=preparation)
        coordinator = ShardCoordinator(plan, console, run_root, scenario_dir=scenario_dir,
                                       server_pid=base.process.pid, console_log=base.log_path)
        coordinator.finalizer = lambda outcome: finalize_live_shard(
            outcome, context, plan.watchdog, coordinator.server, coordinator.run_id)
        summary = coordinator.run()
    summary["worldserver"] = {"path": str(worldserver), "sha256": binary_sha256, "lifecycle": lifecycle}
    if lifecycle.get("process_return_code") not in (0, None) and summary.get("terminal_reason") == "completed":
        summary["terminal_reason"] = "infrastructure_loss"
        summary.setdefault("infrastructure_failures", []).append("worldserver_exit_code_nonzero")
    harness.write_json(run_root / "shard_run.json", summary)
    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--plan", type=Path, required=True,
                        help=f"{RUN_PLAN_SCHEMA}, or {SOURCE_PLAN_SCHEMA} with --shard")
    parser.add_argument("--shard", action="append", default=[], help="cohort id to run (repeatable)")
    parser.add_argument("--output-dir", type=Path, required=True, help="new run root, outside the source tree")
    parser.add_argument("--worldserver", type=Path, default=Path("build/src/server/worldserver/worldserver"))
    parser.add_argument("--config", type=Path, default=Path("trinity-worldserver-test.conf"))
    parser.add_argument("--validation-scenario-dir", type=Path, default=Path("dataset/validation_scenarios"))
    parser.add_argument("--validation-provisioning-config", type=Path,
                        default=Path("experiments/configs/validation_provisioning_cata_001.json"))
    parser.add_argument("--gear-profiles", type=Path, default=Path("dataset/validation_gear_profiles/profiles.json"))
    parser.add_argument("--dry-run", action="store_true", help="validate the plan and print the shard scripts")
    args = parser.parse_args(argv)
    plan = load_run_plan(args.plan, select=args.shard)
    if args.dry_run:
        print(json.dumps({"schema": RUN_SCHEMA, "dry_run": True, "config_overrides": dict(SHARD_CONFIG_OVERRIDES),
                          "shards": [{"cohort_id": spec.cohort_id, "profile": spec.profile,
                                      "lockout": spec.lockout.seed_argument if spec.lockout else "fresh",
                                      "script": shard_script(spec, plan.watchdog).splitlines()}
                                     for spec in plan.shards]}, indent=2))
        return 0
    output = args.output_dir.resolve()
    if output.is_relative_to(REPO_ROOT):
        raise SystemExit("--output-dir must be outside the source tree (evidence is archived with DVC)")
    summary = run_live(plan, worldserver=args.worldserver.resolve(), base_config=args.config.resolve(),
                       run_root=output, scenario_dir=args.validation_scenario_dir.resolve(),
                       provisioning_config=args.validation_provisioning_config.resolve(),
                       gear_profiles=args.gear_profiles.resolve())
    print(json.dumps({"shard_run": str(output / "shard_run.json"), "terminal_reason": summary.get("terminal_reason"),
                      "shards": [(row["cohort_id"], row["completion_reason"], row["native_clear"])
                                 for row in summary.get("shards", [])]}))
    return 0 if summary.get("terminal_reason") == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
