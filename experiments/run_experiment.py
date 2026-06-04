#!/usr/bin/env python3
"""Headless player bot experiment runner.

The runner can execute against a live worldserver through RA or SOAP, or use the
local adapter for smoke validation when no server is available.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dvclive import Live


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RUNS_DIR = REPO_ROOT / "experiments" / "runs"
DEFAULT_RAW_DIR = REPO_ROOT / "dataset" / "raw"

EXECUTION_MODES = {
    "headless_ra_soap",
    "headless_server_script",
    "live_client_observed",
    "live_client_recording",
    "mixed_human_bot",
}

CLASS_SPEC_HINTS = {
    "holy_paladin": {"class_id": 2, "spec_id": 65, "role": "healer"},
    "warrior": {"class_id": 1, "spec_id": 71, "role": "solo"},
    "hunter": {"class_id": 3, "spec_id": 253, "role": "solo"},
    "rogue": {"class_id": 4, "spec_id": 259, "role": "solo"},
    "mage": {"class_id": 8, "spec_id": 63, "role": "solo"},
}


class ExperimentError(RuntimeError):
    pass


def now_ms() -> int:
    return int(time.time() * 1000)


def distance_3d(a: list[float], b: list[float]) -> float:
    return sum((a[i] - b[i]) ** 2 for i in range(3)) ** 0.5


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


class JsonlFrameWriter:
    def __init__(self, path: Path, episode_id: str, execution_mode: str, live_client_present: bool):
        self.path = path
        self.episode_id = episode_id
        self.execution_mode = execution_mode
        self.live_client_present = live_client_present
        self.frame_id = 0
        self._start = time.monotonic()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._handle = self.path.open("w", encoding="utf-8")

    def close(self) -> None:
        self._handle.close()

    def write(
        self,
        *,
        domain: str,
        subdomain: str,
        trigger: str,
        actor: dict[str, Any] | None = None,
        task: dict[str, Any] | None = None,
        state: dict[str, Any] | None = None,
        valid_actions: dict[str, Any] | None = None,
        policy_output: dict[str, Any] | None = None,
        resolved_action: dict[str, Any] | None = None,
        future_labels: dict[str, Any] | None = None,
        outcome: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.frame_id += 1
        frame = {
            "episode_id": self.episode_id,
            "frame_id": self.frame_id,
            "t": round(time.monotonic() - self._start, 3),
            "domain": domain,
            "subdomain": subdomain,
            "trigger": trigger,
            "execution_mode": self.execution_mode,
            "live_client_present": self.live_client_present,
            "actor": actor or {
                "guid": None,
                "is_bot": False,
                "role": None,
                "class_id": None,
                "spec_id": None,
            },
            "task": task or {},
            "state": state or {},
            "valid_actions": valid_actions or {},
            "policy_output": policy_output or {},
            "resolved_action": resolved_action or {},
            "future_labels": future_labels or {},
            "outcome": outcome or {},
        }
        self._handle.write(json.dumps(frame, sort_keys=True, separators=(",", ":")) + "\n")
        self._handle.flush()
        return frame


@dataclass
class CommandResult:
    ok: bool
    command: str
    output: str
    parsed: dict[str, Any] | list[Any] | None = None


class CommandAdapter:
    def execute(self, command: str) -> CommandResult:
        raise NotImplementedError


class LocalCommandAdapter(CommandAdapter):
    """Serverless adapter used to validate the runner and JSONL substrate."""

    def __init__(self) -> None:
        self.bot_guid = 50101
        self.leader_guid = 10001
        self.recording = False
        self.spawned = False
        self.mode = "stay"
        self.bot_position = [18.0, 0.0, 0.0]
        self.leader_position = [0.0, 0.0, 0.0]
        self.marker_position = [6.0, 0.0, 0.0]
        self.stuck_ticks = 0
        self.combat_target_guid = 70001
        self.combat_target_entry = 41234
        self.combat_target_hp = 1.0
        self.combat_started = False
        self.combat_looted = False
        self.bot_hp = 1.0
        self.quest_id = 28808
        self.quest_accepted = False
        self.quest_turned_in = False
        self.quest_progress = 0
        self.quest_required = 3
        self.quest_objective_center = [6.0, 0.0, 0.0]

    def execute(self, command: str) -> CommandResult:
        output: dict[str, Any]
        if command.startswith("playerbot spawn"):
            self.spawned = True
            output = {
                "ok": True,
                "action": "spawn",
                "bot_guid": self.bot_guid,
                "name": "LocalSmokeBot",
                "role": "holy_paladin",
                "class_spec_tag": "holy_paladin",
                "class_id": 2,
                "spec_id": 65,
                "state": "spawned",
                "count": 1,
                "selector": "local",
                "mode": "",
                "failure_reason": None,
            }
        elif command.startswith("playerbot record on"):
            self.recording = True
            output = {"ok": self.spawned, "action": "record", "state": "on", "failure_reason": None if self.spawned else "no_active_bot"}
        elif command.startswith("playerbot record off"):
            self.recording = False
            output = {"ok": True, "action": "record", "state": "off", "failure_reason": None}
        elif command.startswith("playerbot follow"):
            self.mode = "follow_leader"
            output = {"ok": self.spawned, "action": "movement", "state": "", "count": 1 if self.spawned else 0, "mode": "follow", "failure_reason": None if self.spawned else "no_active_bot"}
        elif command.startswith("playerbot stay"):
            self.mode = "stay_position"
            output = {"ok": self.spawned, "action": "movement", "state": "", "count": 1 if self.spawned else 0, "mode": "stay", "failure_reason": None if self.spawned else "no_active_bot"}
        elif command.startswith("playerbot stop"):
            self.mode = "stop"
            output = {"ok": self.spawned, "action": "movement", "state": "", "count": 1 if self.spawned else 0, "mode": "stop", "failure_reason": None if self.spawned else "no_active_bot"}
        elif command.startswith("playerbot move_to"):
            parts = command.split()
            if len(parts) >= 5:
                self.marker_position = [float(parts[2]), float(parts[3]), float(parts[4])]
            self.mode = "move_to_marker"
            output = {"ok": self.spawned, "action": "movement", "state": "", "count": 1 if self.spawned else 0, "mode": "move_to", "failure_reason": None if self.spawned else "no_active_bot"}
        elif command.startswith("playerbot return_to_group"):
            self.mode = "return_to_group"
            output = {"ok": self.spawned, "action": "movement", "state": "", "count": 1 if self.spawned else 0, "mode": "return_to_group", "failure_reason": None if self.spawned else "no_active_bot"}
        elif command.startswith("playerbot move_safe"):
            self.mode = "avoid_hazard"
            output = {"ok": self.spawned, "action": "movement", "state": "", "count": 1 if self.spawned else 0, "mode": "move_safe", "failure_reason": None if self.spawned else "no_active_bot"}
        elif command.startswith("playerbot unstuck"):
            self.mode = "unstuck"
            self.stuck_ticks = 0
            output = {"ok": self.spawned, "action": "movement", "state": "", "count": 1 if self.spawned else 0, "mode": "unstuck", "failure_reason": None if self.spawned else "no_active_bot"}
        elif command.startswith("playerbot combat_target"):
            self.combat_started = True
            if self.quest_accepted and self.quest_progress < self.quest_required and self.combat_target_hp <= 0.0:
                self.combat_target_hp = 1.0
                self.combat_looted = False
            output = {"ok": self.spawned, "action": "combat_target", "state": "targeted", "count": 1 if self.spawned else 0, "mode": "nearest", "target_guid": self.combat_target_guid, "failure_reason": None if self.spawned else "no_active_bot"}
        elif command.startswith("playerbot combat_clear"):
            self.combat_started = False
            output = {"ok": self.spawned, "action": "combat_clear", "state": "cleared", "count": 1 if self.spawned else 0, "failure_reason": None if self.spawned else "no_active_bot"}
        elif command.startswith("playerbot loot"):
            self.combat_looted = self.combat_target_hp <= 0.0
            output = {"ok": self.spawned and self.combat_looted, "action": "loot", "state": "looted" if self.combat_looted else "not_lootable", "count": 1 if self.combat_looted else 0, "mode": "selected", "failure_reason": None if self.combat_looted else "target_not_lootable"}
        elif command.startswith("playerbot quest accept"):
            self.quest_accepted = self.spawned
            output = {"ok": self.quest_accepted, "action": "quest_accept", "quest_id": self.quest_id, "state": "accepted" if self.quest_accepted else "not_spawned", "failure_reason": None if self.quest_accepted else "no_active_bot"}
        elif command.startswith("playerbot quest objective"):
            output = {"ok": self.spawned, "action": "quest_objective", "quest": self.quest_state(), "failure_reason": None if self.spawned else "no_active_bot"}
        elif command.startswith("playerbot quest interact"):
            if self.quest_accepted and self.quest_progress < self.quest_required:
                self.quest_progress += 1
            output = {"ok": self.quest_accepted, "action": "quest_interact", "quest": self.quest_state(), "failure_reason": None if self.quest_accepted else "quest_not_accepted"}
        elif command.startswith("playerbot quest use_item"):
            if self.quest_accepted and self.quest_progress < self.quest_required:
                self.quest_progress += 1
            output = {"ok": self.quest_accepted, "action": "quest_use_item", "quest": self.quest_state(), "failure_reason": None if self.quest_accepted else "quest_not_accepted"}
        elif command.startswith("playerbot quest turn_in"):
            self.quest_turned_in = self.quest_accepted and self.quest_progress >= self.quest_required
            output = {"ok": self.quest_turned_in, "action": "quest_turn_in", "quest_id": self.quest_id, "state": "rewarded" if self.quest_turned_in else "incomplete", "failure_reason": None if self.quest_turned_in else "quest_incomplete"}
        elif command.startswith("playerbot status"):
            output = {"ok": True, "action": "status", "count": 1 if self.spawned else 0, "bots": [{"guid": self.bot_guid, "role": "holy_paladin", "movement": self.movement_state(), "combat": self.combat_state()}] if self.spawned else []}
        elif command.startswith("playerbot remove"):
            removed = 1 if self.spawned else 0
            self.spawned = False
            output = {"ok": True, "action": "remove", "state": "removed", "count": removed, "failure_reason": None}
        else:
            output = {"ok": True, "action": "noop", "command": command, "failure_reason": None}
        return CommandResult(bool(output.get("ok")), command, json.dumps(output), output)

    def combat_state(self) -> dict[str, Any]:
        return {
            "target_guid": self.combat_target_guid if self.combat_started else 0,
            "target_entry": self.combat_target_entry,
            "target_hp": max(0.0, self.combat_target_hp),
            "target_distance": 4.0,
            "bot_hp": self.bot_hp,
            "nearby_hostile_count": 1,
            "extra_pull_risk": 0.0,
            "looted": self.combat_looted,
        }

    def advance_combat(self) -> dict[str, Any]:
        if self.combat_started and self.combat_target_hp > 0.0:
            self.combat_target_hp = max(0.0, self.combat_target_hp - 0.22)
            self.bot_hp = max(0.55, self.bot_hp - 0.035)
            if self.quest_accepted and self.combat_target_hp <= 0.0 and self.quest_progress < self.quest_required:
                self.quest_progress += 1
        return self.combat_state()

    def quest_state(self) -> dict[str, Any]:
        return {
            "quest_id": self.quest_id,
            "objective_index": 0,
            "objective_type": "kill",
            "target_entry": self.combat_target_entry,
            "progress_current": self.quest_progress,
            "progress_required": self.quest_required,
            "status": "rewarded" if self.quest_turned_in else ("complete" if self.quest_progress >= self.quest_required else ("incomplete" if self.quest_accepted else "none")),
            "objective_area": {"map_id": 0, "zone_id": 12, "center": self.quest_objective_center, "radius": 80.0},
        }

    def movement_state(self) -> dict[str, Any]:
        distance = distance_3d(self.bot_position, self.leader_position)
        return {
            "distance_to_leader": distance,
            "distance_to_group_center": distance,
            "line_of_sight_to_leader": True,
            "stuck_score": min(1.0, self.stuck_ticks / 4.0),
            "path_available": True,
            "nearby_hazard": False,
            "safe_position_available": True,
        }

    def advance_movement(self) -> dict[str, Any]:
        if self.mode in {"follow_leader", "return_to_group", "avoid_hazard", "unstuck"}:
            target = self.leader_position
            follow_range = 6.0
        elif self.mode == "move_to_marker":
            target = self.marker_position
            follow_range = 1.0
        else:
            target = self.bot_position
            follow_range = 0.0

        before = distance_3d(self.bot_position, target)
        if before > follow_range:
            step = min(5.0, before - follow_range)
            for i in range(3):
                self.bot_position[i] += (target[i] - self.bot_position[i]) / before * step
        after = distance_3d(self.bot_position, self.leader_position)
        self.stuck_ticks = 0 if after < before or self.mode in {"stay_position", "stop"} else self.stuck_ticks + 1
        return self.movement_state()


class RACommandAdapter(CommandAdapter):
    def __init__(self, host: str, port: int, username: str, password: str, timeout_sec: float = 10.0):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout_sec = timeout_sec

    def execute(self, command: str) -> CommandResult:
        with socket.create_connection((self.host, self.port), timeout=self.timeout_sec) as sock:
            sock.settimeout(self.timeout_sec)
            banner = sock.recv(4096).decode("utf-8", errors="replace")
            sock.sendall((self.username + "\n").encode("utf-8"))
            sock.recv(4096)
            sock.sendall((self.password + "\n").encode("utf-8"))
            sock.recv(4096)
            sock.sendall((command + "\n").encode("utf-8"))
            chunks: list[str] = []
            deadline = time.monotonic() + self.timeout_sec
            while time.monotonic() < deadline:
                try:
                    chunk = sock.recv(4096)
                except socket.timeout:
                    break
                if not chunk:
                    break
                text = chunk.decode("utf-8", errors="replace")
                chunks.append(text)
                if "\r\n" in text or "\n" in text:
                    break
            output = "".join(chunks).strip() or banner.strip()
        parsed = parse_first_json(output)
        ok = bool(parsed.get("ok", True)) if isinstance(parsed, dict) else True
        return CommandResult(ok, command, output, parsed)


class SOAPCommandAdapter(CommandAdapter):
    def __init__(self, url: str, username: str, password: str, timeout_sec: float = 10.0):
        self.url = url
        self.username = username
        self.password = password
        self.timeout_sec = timeout_sec

    def execute(self, command: str) -> CommandResult:
        envelope = f"""<?xml version="1.0" encoding="UTF-8"?>
<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ns1="urn:TC">
  <SOAP-ENV:Body>
    <ns1:executeCommand>
      <command>{xml_escape(command)}</command>
    </ns1:executeCommand>
  </SOAP-ENV:Body>
</SOAP-ENV:Envelope>
"""
        request = urllib.request.Request(
            self.url,
            data=envelope.encode("utf-8"),
            headers={"Content-Type": "text/xml; charset=utf-8", "SOAPAction": "executeCommand"},
            method="POST",
        )
        auth = ("%s:%s" % (self.username, self.password)).encode("utf-8").hex()
        request.add_header("Authorization", "Basic " + basic_auth(self.username, self.password))
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_sec) as response:
                output = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            output = exc.read().decode("utf-8", errors="replace")
            raise ExperimentError(f"SOAP command failed: {exc.code} {output}") from exc
        parsed = parse_first_json(output)
        ok = bool(parsed.get("ok", True)) if isinstance(parsed, dict) else True
        return CommandResult(ok, command, output, parsed)


def basic_auth(username: str, password: str) -> str:
    import base64

    return base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")


def xml_escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")


def parse_first_json(text: str) -> dict[str, Any] | list[Any] | None:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char not in "[{":
            continue
        try:
            parsed, _ = decoder.raw_decode(text[index:])
            return parsed
        except json.JSONDecodeError:
            continue
    return None


def load_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    mode = config.get("execution_mode", "headless_ra_soap")
    if mode not in EXECUTION_MODES:
        raise ExperimentError(f"unsupported execution_mode: {mode}")
    return config


def next_episode_id(runs_dir: Path) -> str:
    runs_dir.mkdir(parents=True, exist_ok=True)
    highest = 0
    for child in runs_dir.iterdir():
        if child.is_dir() and child.name.startswith("run_"):
            try:
                highest = max(highest, int(child.name.removeprefix("run_")))
            except ValueError:
                pass
    return f"run_{highest + 1:06d}"


def make_adapter(config: dict[str, Any], force_local: bool) -> CommandAdapter:
    adapter = config.get("adapter", {})
    kind = "local" if force_local else adapter.get("type", "local")
    if kind == "local":
        return LocalCommandAdapter()
    if kind == "ra":
        return RACommandAdapter(
            adapter.get("host", os.environ.get("TRINITY_RA_HOST", "127.0.0.1")),
            int(adapter.get("port", os.environ.get("TRINITY_RA_PORT", "3443"))),
            adapter.get("username", os.environ.get("TRINITY_RA_USER", "")),
            adapter.get("password", os.environ.get("TRINITY_RA_PASSWORD", "")),
            float(adapter.get("timeout_sec", 10)),
        )
    if kind == "soap":
        return SOAPCommandAdapter(
            adapter.get("url", os.environ.get("TRINITY_SOAP_URL", "http://127.0.0.1:7878/")),
            adapter.get("username", os.environ.get("TRINITY_SOAP_USER", "")),
            adapter.get("password", os.environ.get("TRINITY_SOAP_PASSWORD", "")),
            float(adapter.get("timeout_sec", 10)),
        )
    raise ExperimentError(f"unsupported adapter type: {kind}")


def playerbot_command(config: dict[str, Any], action: str, *parts: str) -> str:
    owner = config.get("owner_selector")
    tokens = ["playerbot", action, *[part for part in parts if part]]
    if owner:
        tokens.extend(["owner", str(owner)])
    return " ".join(tokens)


def first_party_role(config: dict[str, Any]) -> str:
    party_template = config.get("party_template") or {"healer": "holy_paladin"}
    if not isinstance(party_template, dict) or not party_template:
        raise ExperimentError("party_template must contain at least one role mapping")
    return str(next(iter(party_template.values())))


def movement_state_from_status(parsed: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        return {}
    bots = parsed.get("bots")
    if not isinstance(bots, list) or not bots:
        return {}
    movement = bots[0].get("movement") if isinstance(bots[0], dict) else None
    return movement if isinstance(movement, dict) else {}


def movement_frame_state(adapter: CommandAdapter, status: CommandResult) -> dict[str, Any]:
    if isinstance(adapter, LocalCommandAdapter):
        return adapter.advance_movement()
    return movement_state_from_status(status.parsed)


def combat_state_from_status(parsed: dict[str, Any] | list[Any] | None) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        return {}
    bots = parsed.get("bots")
    if not isinstance(bots, list) or not bots:
        return {}
    combat = bots[0].get("combat") if isinstance(bots[0], dict) else None
    return combat if isinstance(combat, dict) else {}


def combat_frame_state(adapter: CommandAdapter, status: CommandResult) -> dict[str, Any]:
    if isinstance(adapter, LocalCommandAdapter):
        return adapter.advance_combat()
    return combat_state_from_status(status.parsed)


def quest_state_from_result(result: CommandResult) -> dict[str, Any]:
    parsed = result.parsed
    if isinstance(parsed, dict):
        quest = parsed.get("quest")
        if isinstance(quest, dict):
            return quest
    return {}


def quest_frame_state(adapter: CommandAdapter, result: CommandResult) -> dict[str, Any]:
    if isinstance(adapter, LocalCommandAdapter):
        return adapter.quest_state()
    return quest_state_from_result(result)


def movement_metrics(frames_path: Path) -> dict[str, Any]:
    movement_frames = 0
    stuck_frames = 0
    los_failures = 0
    hazard_hits = 0
    invalid_commands = 0
    distances: list[float] = []
    return_success = False
    max_stuck_score = 0.0

    with frames_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            frame = json.loads(line)
            if frame.get("domain") != "movement":
                continue
            movement_frames += 1
            state = frame.get("state", {})
            self_state = state.get("self", state)
            nav_state = state.get("navigation", {})
            distance = float(self_state.get("distance_to_leader", state.get("distance_to_leader", 0.0)) or 0.0)
            stuck_score = float(nav_state.get("stuck_score", state.get("stuck_score", 0.0)) or 0.0)
            distances.append(distance)
            max_stuck_score = max(max_stuck_score, stuck_score)
            if stuck_score >= 1.0 or frame.get("outcome", {}).get("stuck"):
                stuck_frames += 1
            if not bool(self_state.get("line_of_sight_to_leader", state.get("line_of_sight_to_leader", True))):
                los_failures += 1
            if bool(nav_state.get("nearby_hazard", state.get("nearby_hazard", False))):
                hazard_hits += 1
            if not bool(frame.get("resolved_action", {}).get("valid", True)):
                invalid_commands += 1
            task = frame.get("task", {})
            if task.get("task_type") in {"return_to_group", "follow_leader"} and distance <= 8.0:
                return_success = True

    average_distance = sum(distances) / len(distances) if distances else 0.0
    return {
        "movement_frame_count": movement_frames,
        "time_stuck_frames": stuck_frames,
        "path_failure_rate": 0.0 if movement_frames else 1.0,
        "average_distance_to_leader": average_distance,
        "max_distance_to_leader": max(distances) if distances else 0.0,
        "line_of_sight_failure_count": los_failures,
        "hazard_hits": hazard_hits,
        "return_to_group_success": return_success,
        "movement_command_invalid_rate": invalid_commands / movement_frames if movement_frames else 1.0,
        "unstuck_recovery_time_frames": 0 if max_stuck_score < 1.0 else stuck_frames,
    }


def solo_combat_metrics(frames_path: Path) -> dict[str, Any]:
    combat_frames = 0
    deaths = 0
    invalid_actions = 0
    loot_success = False
    kill_success = False
    extra_pull_count = 0
    interrupt_success = 0
    damage_taken = 0.0
    first_t: float | None = None
    kill_t: float | None = None

    with frames_path.open("r", encoding="utf-8") as handle:
        previous_self_hp = 1.0
        for line in handle:
            if not line.strip():
                continue
            frame = json.loads(line)
            if frame.get("domain") != "combat" or frame.get("subdomain") != "solo_combat":
                continue
            combat_frames += 1
            t = float(frame.get("t", combat_frames))
            if first_t is None:
                first_t = t
            state = frame.get("state", {})
            self_state = state.get("self", {})
            env_state = state.get("environment", {})
            outcome = frame.get("outcome", {})
            resolved = frame.get("resolved_action", {})
            policy = frame.get("policy_output", {})
            self_hp = float(self_state.get("hp_pct", previous_self_hp) or 0.0)
            if self_hp <= 0:
                deaths += 1
            damage_taken += max(0.0, previous_self_hp - self_hp)
            previous_self_hp = self_hp
            extra_pull_count += max(0, int(env_state.get("nearby_hostile_count", 0) or 0) - 1)
            if not bool(resolved.get("valid", True)):
                invalid_actions += 1
            if policy.get("intent") == "interrupt" and resolved.get("result") == "ok":
                interrupt_success += 1
            if outcome.get("target_dead_10s"):
                kill_success = True
                kill_t = kill_t or t
            if outcome.get("loot_success"):
                loot_success = True

    return {
        "combat_frame_count": combat_frames,
        "kill_success_rate": 1.0 if kill_success else 0.0,
        "death_rate": 1.0 if deaths else 0.0,
        "time_to_kill_sec": round((kill_t or 0.0) - (first_t or 0.0), 3) if kill_success else 0.0,
        "damage_taken_per_kill": round(damage_taken, 6) if kill_success else 0.0,
        "extra_pull_count": extra_pull_count,
        "interrupt_success": interrupt_success,
        "invalid_action_rate": invalid_actions / combat_frames if combat_frames else 1.0,
        "loot_success": loot_success,
        "recovery_time_after_combat_sec": 0.0 if loot_success else None,
    }


def quest_metrics(frames_path: Path) -> dict[str, Any]:
    quest_frames = 0
    accepted = False
    turned_in = False
    deaths = 0
    invalid_actions = 0
    progress_start: int | None = None
    progress_end = 0
    first_t: float | None = None
    turn_in_t: float | None = None
    travel_time = 0.0
    stuck_failures = 0
    wrong_interactions = 0
    bag_interruptions = 0

    with frames_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            frame = json.loads(line)
            if frame.get("domain") != "quest":
                continue
            quest_frames += 1
            t = float(frame.get("t", quest_frames))
            if first_t is None:
                first_t = t
            task = frame.get("task", {})
            state = frame.get("state", {})
            resolved = frame.get("resolved_action", {})
            outcome = frame.get("outcome", {})
            progress_current = int(task.get("progress_current", state.get("progress_current", 0)) or 0)
            if progress_start is None:
                progress_start = progress_current
            progress_end = max(progress_end, progress_current)
            accepted = accepted or outcome.get("quest_accepted") or task.get("status") in {"incomplete", "complete", "rewarded"}
            turned_in = turned_in or outcome.get("quest_turned_in") or task.get("status") == "rewarded"
            if turned_in and turn_in_t is None:
                turn_in_t = t
            if outcome.get("death"):
                deaths += 1
            if not bool(resolved.get("valid", True)):
                invalid_actions += 1
            if frame.get("policy_output", {}).get("intent") == "move_to_objective_area":
                travel_time += float(outcome.get("time_spent_sec", 0.5) or 0.5)
            if outcome.get("stuck") or outcome.get("path_failed"):
                stuck_failures += 1
            if outcome.get("wrong_target_interaction"):
                wrong_interactions += 1
            if outcome.get("bag_full"):
                bag_interruptions += 1

    progress_delta = progress_end - (progress_start or 0)
    elapsed_minutes = max(((turn_in_t or first_t or 0.0) - (first_t or 0.0)) / 60.0, 1.0 / 60.0)
    return {
        "quest_frame_count": quest_frames,
        "quest_completion_success": bool(accepted and turned_in),
        "objective_progress_per_minute": round(progress_delta / elapsed_minutes, 6),
        "deaths_per_quest": deaths,
        "travel_time_sec": round(travel_time, 3),
        "stuck_path_failures": stuck_failures,
        "wrong_target_interactions": wrong_interactions,
        "bag_full_interruptions": bag_interruptions,
        "time_to_turn_in_sec": round((turn_in_t or 0.0) - (first_t or 0.0), 3) if turned_in else None,
        "invalid_action_rate": invalid_actions / quest_frames if quest_frames else 1.0,
    }


def write_initial_metadata(config: dict[str, Any], episode_id: str, episode_dir: Path) -> dict[str, Any]:
    metadata = {
        "episode_id": episode_id,
        "experiment_id": config["experiment_id"],
        "domain": config.get("domain", "system_smoke"),
        "execution_mode": config.get("execution_mode", "headless_ra_soap"),
        "live_client_present": bool(config.get("live_client_present", False)),
        "server_build": config.get("server_build", "wow_4.3.4"),
        "map_id": config.get("map_id", 0),
        "instance_id": config.get("instance_id"),
        "party_guid": config.get("party_guid"),
        "owner_guid": config.get("owner_guid"),
        "controller": config.get("controller", "external_script"),
        "bots": [],
        "start_time_server_ms": now_ms(),
        "duration_sec": 0,
        "result": "unknown",
        "episode_quality": "unknown",
    }
    write_json(episode_dir / "metadata.json", metadata)
    return metadata


def run_experiment(config: dict[str, Any], adapter: CommandAdapter, runs_dir: Path, raw_dir: Path, live_dir: Path | None = None) -> dict[str, Any]:
    runs_dir = resolve_repo_path(runs_dir)
    raw_dir = resolve_repo_path(raw_dir)
    live_dir = resolve_repo_path(live_dir) if live_dir else None
    episode_id = next_episode_id(runs_dir)
    episode_dir = runs_dir / episode_id
    raw_episode_dir = raw_dir / episode_id
    episode_dir.mkdir(parents=True, exist_ok=False)
    raw_episode_dir.mkdir(parents=True, exist_ok=False)

    metadata = write_initial_metadata(config, episode_id, episode_dir)
    frames_path = raw_episode_dir / "frames.jsonl"
    command_log_path = episode_dir / "commands.jsonl"
    frame_writer = JsonlFrameWriter(frames_path, episode_id, metadata["execution_mode"], metadata["live_client_present"])
    command_log = command_log_path.open("w", encoding="utf-8")
    live = Live(dir=str(live_dir), save_dvc_exp=True) if live_dir else None
    start = time.monotonic()
    result = "success"
    quality = "usable"
    produced_paths = {
        "episode_dir": display_path(episode_dir),
        "metadata": display_path(episode_dir / "metadata.json"),
        "command_log": display_path(command_log_path),
        "frames": display_path(frames_path),
    }

    if live:
        live.log_param("experiment_id", config["experiment_id"])
        live.log_param("domain", metadata["domain"])
        live.log_param("execution_mode", metadata["execution_mode"])
        live.log_param("live_client_present", metadata["live_client_present"])

    def execute(command: str) -> CommandResult:
        command_result = adapter.execute(command)
        command_log.write(json.dumps({
            "t": round(time.monotonic() - start, 3),
            "command": command,
            "ok": command_result.ok,
            "output": command_result.output,
            "parsed": command_result.parsed,
        }, sort_keys=True) + "\n")
        command_log.flush()
        return command_result

    try:
        role = first_party_role(config)
        spawn = execute(playerbot_command(config, "spawn", role))
        if not spawn.ok:
            raise ExperimentError("bot_spawn_failed")
        if isinstance(spawn.parsed, dict):
            bot_guid = spawn.parsed.get("bot_guid")
            class_spec_tag = spawn.parsed.get("class_spec_tag") or role
            class_spec_hint = CLASS_SPEC_HINTS.get(str(class_spec_tag), {})
            metadata["bots"].append({
                "guid": bot_guid,
                "name": spawn.parsed.get("name"),
                "role": spawn.parsed.get("role") or role,
                "class_spec_tag": class_spec_tag,
                "class_id": spawn.parsed.get("class_id", class_spec_hint.get("class_id")),
                "spec_id": spawn.parsed.get("spec_id", class_spec_hint.get("spec_id")),
            })

        if config.get("setup", {}).get("recording", True):
            recording = execute(playerbot_command(config, "record", "on"))
            if not recording.ok:
                raise ExperimentError("recording_start_failed")

        status = execute(playerbot_command(config, "status"))
        frame_writer.write(
            domain=config.get("domain", "system_smoke"),
            subdomain="headless_smoke",
            trigger="task_change",
            actor={
                "guid": metadata["bots"][0].get("guid") if metadata["bots"] else None,
                "is_bot": bool(metadata["bots"]),
                "role": metadata["bots"][0].get("role") if metadata["bots"] else None,
                "class_id": metadata["bots"][0].get("class_id") if metadata["bots"] else None,
                "spec_id": metadata["bots"][0].get("spec_id") if metadata["bots"] else None,
            },
            task={"experiment_id": config["experiment_id"], "success_conditions": config.get("run", {}).get("success_conditions", [])},
            state={"status": status.parsed},
            resolved_action={"command": status.command},
            outcome={"recording_file_created": frames_path.exists(), "bot_spawned": bool(metadata["bots"])},
        )

        if config.get("domain") == "movement" or config.get("run", {}).get("movement_ticks"):
            movement_modes = config.get("run", {}).get("movement_modes", ["follow", "stay", "return_to_group", "move_safe", "unstuck"])
            ticks_per_mode = int(config.get("run", {}).get("movement_ticks_per_mode", 2))
            marker = config.get("run", {}).get("marker_position", [3.0, 0.0, 0.0])
            for mode in movement_modes:
                if mode == "move_to_marker":
                    movement_command = playerbot_command(config, "move_to", str(marker[0]), str(marker[1]), str(marker[2]))
                elif mode == "follow_leader":
                    movement_command = playerbot_command(config, "follow")
                elif mode == "stay_position":
                    movement_command = playerbot_command(config, "stay")
                else:
                    movement_command = playerbot_command(config, mode)
                movement_result = execute(movement_command)
                if not movement_result.ok:
                    raise ExperimentError(f"movement_command_failed:{mode}")
                for _ in range(ticks_per_mode):
                    status = execute(playerbot_command(config, "status"))
                    movement_state = movement_frame_state(adapter, status)
                    distance = float(movement_state.get("distance_to_leader", 0.0) or 0.0)
                    frame_writer.write(
                        domain="movement",
                        subdomain="follow",
                        trigger="movement_tick",
                        actor={
                            "guid": metadata["bots"][0].get("guid") if metadata["bots"] else None,
                            "is_bot": bool(metadata["bots"]),
                            "role": metadata["bots"][0].get("role") if metadata["bots"] else None,
                        },
                        task={"task_type": mode, "leader_guid": getattr(adapter, "leader_guid", config.get("owner_guid"))},
                        state={
                            "self": {
                                "position": getattr(adapter, "bot_position", [0.0, 0.0, 0.0]),
                                "orientation": 0.0,
                                "moving": mode not in {"stay_position", "stop"},
                                "mounted": False,
                                "in_combat": False,
                                "hp_pct": 1.0,
                                "distance_to_leader": distance,
                                "distance_to_group_center": movement_state.get("distance_to_group_center", distance),
                                "line_of_sight_to_leader": movement_state.get("line_of_sight_to_leader", True),
                                "on_transport": False,
                                "indoors": False,
                            },
                            "navigation": {
                                "current_path_length": distance,
                                "path_available": movement_state.get("path_available", True),
                                "stuck_score": movement_state.get("stuck_score", 0.0),
                                "last_progress_time_ms": 0,
                                "nearby_hazard": movement_state.get("nearby_hazard", False),
                                "safe_position_available": movement_state.get("safe_position_available", True),
                            },
                        },
                        policy_output={"mode": mode, "intent": "move_to_follow_range" if mode == "follow_leader" else mode},
                        resolved_action={"type": movement_command.split()[1], "valid": movement_result.ok},
                        outcome={"distance_to_leader_after_2s": distance, "stuck": movement_state.get("stuck_score", 0.0) >= 1.0},
                    )

        if config.get("domain") == "combat" or config.get("run", {}).get("combat_ticks"):
            target_selector = str(config.get("run", {}).get("target_selector", "nearest"))
            target_result = execute(playerbot_command(config, "combat_target", target_selector))
            if not target_result.ok:
                raise ExperimentError("combat_target_failed")

            max_ticks = int(config.get("run", {}).get("combat_ticks", 8))
            previous_target_hp = 1.0
            previous_self_hp = 1.0
            target_dead = False
            for _ in range(max_ticks):
                status = execute(playerbot_command(config, "status"))
                combat_state = combat_frame_state(adapter, status)
                target_hp = float(combat_state.get("target_hp", previous_target_hp) or 0.0)
                self_hp = float(combat_state.get("bot_hp", previous_self_hp) or 0.0)
                target_dead = target_hp <= 0.0
                intent = "loot" if target_dead else ("pull_target" if previous_target_hp >= 1.0 else "maintain_rotation")
                action_type = "loot" if target_dead else "cast"
                loot_success = False
                if target_dead:
                    loot_result = execute(playerbot_command(config, "loot", "selected"))
                    loot_success = loot_result.ok
                frame_writer.write(
                    domain="combat",
                    subdomain="solo_combat",
                    trigger="gcd_ready",
                    actor={
                        "guid": metadata["bots"][0].get("guid") if metadata["bots"] else None,
                        "class_id": metadata["bots"][0].get("class_id") if metadata["bots"] else None,
                        "spec_id": metadata["bots"][0].get("spec_id") if metadata["bots"] else None,
                        "role": "solo",
                    },
                    state={
                        "self": {
                            "hp_pct": self_hp,
                            "primary_power_pct": 0.75,
                            "class_id": metadata["bots"][0].get("class_id") if metadata["bots"] else None,
                            "spec_id": metadata["bots"][0].get("spec_id") if metadata["bots"] else None,
                            "moving": False,
                            "casting": False,
                            "gcd_remaining": 0.0,
                            "active_aura_ids": [],
                        },
                        "target": {
                            "guid": combat_state.get("target_guid"),
                            "entry_id": combat_state.get("target_entry"),
                            "hp_pct": target_hp,
                            "distance": combat_state.get("target_distance", 4.0),
                            "casting_spell_id": None,
                            "cast_remaining": 0.0,
                            "interruptible": False,
                        },
                        "environment": {
                            "nearby_hostile_count": combat_state.get("nearby_hostile_count", 1),
                            "elite_nearby": False,
                            "extra_pull_risk": combat_state.get("extra_pull_risk", 0.0),
                            "safe_position_available": True,
                        },
                    },
                    valid_actions={"intents": ["pull_target", "maintain_rotation", "interrupt", "use_defensive", "heal_self", "move_to_range", "loot", "recover", "wait"]},
                    policy_output={"mode": "single_target", "intent": intent},
                    resolved_action={
                        "type": action_type,
                        "spell_id": 6603 if action_type == "cast" else 0,
                        "target_guid": combat_state.get("target_guid"),
                        "valid": True,
                        "result": "ok",
                    },
                    outcome={
                        "target_hp_delta_3s": round(target_hp - previous_target_hp, 6),
                        "self_hp_delta_3s": round(self_hp - previous_self_hp, 6),
                        "target_dead_10s": target_dead,
                        "loot_success": loot_success,
                    },
                )
                previous_target_hp = target_hp
                previous_self_hp = self_hp
                if target_dead and loot_success:
                    break

            if not target_dead:
                raise ExperimentError("combat_target_not_killed")

        if config.get("domain") == "quest" or config.get("run", {}).get("quest_ticks"):
            quest = config.get("quest", {})
            quest_id = int(quest.get("quest_id", 28808))
            target_entry = int(quest.get("target_entry", getattr(adapter, "combat_target_entry", 0)))
            required = int(quest.get("progress_required", getattr(adapter, "quest_required", 1)))
            accept = execute(playerbot_command(config, "quest", "accept", str(quest_id)))
            if not accept.ok:
                raise ExperimentError("quest_accept_failed")

            objective = execute(playerbot_command(config, "quest", "objective", str(quest_id)))
            quest_state = quest_frame_state(adapter, objective)
            objective_area = quest_state.get("objective_area", quest.get("objective_area", {"map_id": config.get("map_id", 0), "zone_id": config.get("zone_id", 0), "center": [0.0, 0.0, 0.0], "radius": 80.0}))
            center = objective_area.get("center", [0.0, 0.0, 0.0])
            travel = execute(playerbot_command(config, "move_to", str(center[0]), str(center[1]), str(center[2])))
            if not travel.ok:
                raise ExperimentError("quest_travel_failed")

            for tick in range(int(config.get("run", {}).get("quest_ticks", max(3, required + 2)))):
                status = execute(playerbot_command(config, "status"))
                movement_state = movement_frame_state(adapter, status)
                distance = float(movement_state.get("distance_to_leader", 0.0) or 0.0)
                current = int(quest_state.get("progress_current", 0) or 0)
                if current < required:
                    if quest.get("objective_type", "kill") == "kill":
                        target_result = execute(playerbot_command(config, "combat_target", str(quest.get("target_selector", "nearest"))))
                        combat_state = combat_frame_state(adapter, target_result)
                        if float(combat_state.get("target_hp", 1.0) or 0.0) <= 0.0:
                            execute(playerbot_command(config, "loot", "selected"))
                        intent = "kill_objective_target"
                        action_type = "combat_target"
                    elif quest.get("objective_type") == "use_item":
                        interaction = execute(playerbot_command(config, "quest", "use_item", str(quest_id)))
                        quest_state = quest_frame_state(adapter, interaction)
                        intent = "use_item_on_target"
                        action_type = "use_item"
                    else:
                        interaction = execute(playerbot_command(config, "quest", "interact", str(quest_id)))
                        quest_state = quest_frame_state(adapter, interaction)
                        intent = "interact_gameobject"
                        action_type = "interact"
                else:
                    intent = "return_to_questgiver"
                    action_type = "move_to"

                objective = execute(playerbot_command(config, "quest", "objective", str(quest_id)))
                quest_state = quest_frame_state(adapter, objective)
                new_current = int(quest_state.get("progress_current", current) or 0)
                complete = new_current >= required
                frame_writer.write(
                    domain="quest",
                    subdomain="quest_objective",
                    trigger="task_decision",
                    actor={
                        "guid": metadata["bots"][0].get("guid") if metadata["bots"] else None,
                        "is_bot": bool(metadata["bots"]),
                        "class_id": metadata["bots"][0].get("class_id") if metadata["bots"] else None,
                        "spec_id": metadata["bots"][0].get("spec_id") if metadata["bots"] else None,
                    },
                    task={
                        "type": "quest_objective",
                        "quest_id": quest_id,
                        "objective_index": int(quest.get("objective_index", 0)),
                        "objective_type": quest.get("objective_type", quest_state.get("objective_type", "kill")),
                        "target_entry": target_entry,
                        "progress_current": new_current,
                        "progress_required": required,
                        "status": quest_state.get("status", "incomplete"),
                        "objective_area": objective_area,
                    },
                    state={
                        "zone_id": objective_area.get("zone_id", config.get("zone_id", 0)),
                        "distance_to_objective": distance,
                        "nearby_hostile_count": 1 if action_type == "combat_target" else 0,
                        "elite_nearby": False,
                        "hp_pct": getattr(adapter, "bot_hp", 1.0),
                        "primary_power_pct": 0.67,
                        "bag_free_slots": 12,
                    },
                    valid_actions={"task_abstractions": ["accept_quest", "turn_in_quest", "travel_to_objective_area", "kill_objective_target", "loot_objective_item", "interact_gameobject", "use_item_on_target", "talk_to_npc", "return_to_questgiver", "repair_vendor_if_needed"]},
                    policy_output={"mode": "complete_objective", "intent": "return_to_questgiver" if complete else intent, "target_entry": target_entry},
                    resolved_action={"type": action_type, "valid": True},
                    outcome={
                        "objective_progress_delta": max(0, new_current - current),
                        "death": False,
                        "time_spent_sec": 0.5,
                        "quest_accepted": True,
                    },
                )
                if complete:
                    break

            turn_in = execute(playerbot_command(config, "quest", "turn_in", str(quest_id)))
            quest_state = quest_frame_state(adapter, turn_in)
            frame_writer.write(
                domain="quest",
                subdomain="quest_objective",
                trigger="task_decision",
                actor={"guid": metadata["bots"][0].get("guid") if metadata["bots"] else None, "is_bot": bool(metadata["bots"])},
                task={"type": "quest_objective", "quest_id": quest_id, "objective_type": quest.get("objective_type", "kill"), "target_entry": target_entry, "progress_current": required, "progress_required": required, "status": "rewarded" if turn_in.ok else "complete"},
                state={"zone_id": objective_area.get("zone_id", 0), "distance_to_objective": 0.0, "nearby_hostile_count": 0, "elite_nearby": False, "hp_pct": getattr(adapter, "bot_hp", 1.0), "primary_power_pct": 0.67, "bag_free_slots": 12},
                policy_output={"mode": "complete_objective", "intent": "turn_in_quest", "target_entry": target_entry},
                resolved_action={"type": "turn_in_quest", "valid": turn_in.ok},
                outcome={"objective_progress_delta": 0, "death": False, "time_spent_sec": 0.5, "quest_accepted": True, "quest_turned_in": turn_in.ok},
            )
            if not turn_in.ok:
                raise ExperimentError("quest_turn_in_failed")

        timeout_sec = float(config.get("run", {}).get("timeout_sec", 60))
        if time.monotonic() - start > timeout_sec:
            raise ExperimentError("timeout")
    except Exception as exc:
        result = "failure"
        quality = "invalid"
        frame_writer.write(domain=config.get("domain", "system_smoke"), subdomain="headless_smoke", trigger="task_change", outcome={"error": str(exc)})
        raise
    finally:
        if config.get("cleanup", {}).get("stop_recording", True):
            try:
                execute(playerbot_command(config, "record", "off"))
            except Exception as exc:
                result = "failure"
                quality = "invalid"
                command_log.write(json.dumps({"cleanup_error": str(exc), "command": "record off"}, sort_keys=True) + "\n")
        if config.get("cleanup", {}).get("remove_bots", True):
            try:
                execute(playerbot_command(config, "remove", "all"))
            except Exception as exc:
                result = "failure"
                quality = "invalid"
                command_log.write(json.dumps({"cleanup_error": str(exc), "command": "remove all"}, sort_keys=True) + "\n")
        frame_writer.close()
        command_log.close()

        metadata["duration_sec"] = round(time.monotonic() - start, 3)
        metadata["result"] = result
        metadata["episode_quality"] = quality
        write_json(episode_dir / "metadata.json", metadata)
        summary = {
            "episode_id": episode_id,
            "experiment_id": config["experiment_id"],
            "result": result,
            "episode_quality": quality,
            "paths": produced_paths,
        }
        if frames_path.exists():
            metrics = movement_metrics(frames_path)
            if metrics["movement_frame_count"]:
                write_json(episode_dir / "movement_metrics.json", metrics)
                summary["movement_metrics"] = metrics
                produced_paths["movement_metrics"] = display_path(episode_dir / "movement_metrics.json")
            combat_metrics = solo_combat_metrics(frames_path)
            if combat_metrics["combat_frame_count"]:
                write_json(episode_dir / "solo_combat_metrics.json", combat_metrics)
                summary["solo_combat_metrics"] = combat_metrics
                produced_paths["solo_combat_metrics"] = display_path(episode_dir / "solo_combat_metrics.json")
            q_metrics = quest_metrics(frames_path)
            if q_metrics["quest_frame_count"]:
                write_json(episode_dir / "quest_metrics.json", q_metrics)
                summary["quest_metrics"] = q_metrics
                produced_paths["quest_metrics"] = display_path(episode_dir / "quest_metrics.json")
        write_json(episode_dir / "summary.json", summary)
        if live:
            command_count = 0
            if command_log_path.exists():
                with command_log_path.open("r", encoding="utf-8") as handle:
                    command_count = sum(1 for line in handle if line.strip())
            live.log_metric("duration_sec", metadata["duration_sec"])
            live.log_metric("bot_count", len(metadata["bots"]))
            live.log_metric("command_count", command_count)
            live.log_metric("success", 1 if result == "success" else 0)
            live.log_artifact(str(episode_dir / "summary.json"), name="run_summary", type="json")
            live.log_artifact(str(episode_dir / "metadata.json"), name="run_metadata", type="json")
            live.next_step()
            live.end()
    return summary


def validate_jsonl(path: Path) -> int:
    count = 0
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            json.loads(line)
            count += 1
    if count == 0:
        raise ExperimentError(f"{path} did not contain any frames")
    return count


def resolve_repo_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a headless player bot experiment")
    parser.add_argument("config", type=Path, help="experiment config JSON")
    parser.add_argument("--runs-dir", type=Path, default=DEFAULT_RUNS_DIR)
    parser.add_argument("--raw-dir", type=Path, default=DEFAULT_RAW_DIR)
    parser.add_argument("--live-dir", type=Path, default=None, help="optional DVCLive output directory")
    parser.add_argument("--local", action="store_true", help="force local serverless adapter")
    args = parser.parse_args(argv)

    config = load_config(args.config)
    adapter = make_adapter(config, args.local)
    summary = run_experiment(config, adapter, args.runs_dir, args.raw_dir, args.live_dir)
    frame_count = validate_jsonl(REPO_ROOT / summary["paths"]["frames"])
    summary["frame_count"] = frame_count
    write_json(REPO_ROOT / summary["paths"]["episode_dir"] / "summary.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
