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
        elif command.startswith("playerbot status"):
            output = {"ok": True, "action": "status", "count": 1 if self.spawned else 0, "bots": [{"guid": self.bot_guid, "role": "holy_paladin", "movement": self.movement_state()}] if self.spawned else []}
        elif command.startswith("playerbot remove"):
            removed = 1 if self.spawned else 0
            self.spawned = False
            output = {"ok": True, "action": "remove", "state": "removed", "count": removed, "failure_reason": None}
        else:
            output = {"ok": True, "action": "noop", "command": command, "failure_reason": None}
        return CommandResult(bool(output.get("ok")), command, json.dumps(output), output)

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
