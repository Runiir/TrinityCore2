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


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=True)
        handle.write("\n")


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
        self.recording = False
        self.spawned = False

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
        elif command.startswith("playerbot status"):
            output = {"ok": True, "action": "status", "count": 1 if self.spawned else 0, "bots": [{"guid": self.bot_guid, "role": "holy_paladin"}] if self.spawned else []}
        elif command.startswith("playerbot remove"):
            removed = 1 if self.spawned else 0
            self.spawned = False
            output = {"ok": True, "action": "remove", "state": "removed", "count": removed, "failure_reason": None}
        else:
            output = {"ok": True, "action": "noop", "command": command, "failure_reason": None}
        return CommandResult(bool(output.get("ok")), command, json.dumps(output), output)


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
        "episode_dir": str(episode_dir.relative_to(REPO_ROOT)),
        "metadata": str((episode_dir / "metadata.json").relative_to(REPO_ROOT)),
        "command_log": str(command_log_path.relative_to(REPO_ROOT)),
        "frames": str(frames_path.relative_to(REPO_ROOT)),
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
