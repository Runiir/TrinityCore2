from __future__ import annotations

import argparse
import copy
import datetime as dt
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

try:
    from .common import stable_hash, write_json
except ImportError:
    from common import stable_hash, write_json


REPO_ROOT = Path(__file__).resolve().parents[2]
AUTO_BOTS_DIR = REPO_ROOT / ".codex" / "plans" / "auto_bots"
ORCHESTRATOR_DIR = REPO_ROOT / ".codex" / "plans" / "orchestrator"
ORCHESTRATOR_INSTANCES_DIR = ORCHESTRATOR_DIR / "instances"
ORCHESTRATOR_WORKTREES_DIR = REPO_ROOT / "generated" / "orchestrator_worktrees"
DEFAULT_CONFIG_PATH = AUTO_BOTS_DIR / "daemon_config.json"
DEFAULT_STATE_PATH = AUTO_BOTS_DIR / "daemon_state.json"
DEFAULT_CHECKLIST_PATH = AUTO_BOTS_DIR / "master_checklist.json"
DEFAULT_RUNS_DIR = AUTO_BOTS_DIR / "runs"
DEFAULT_LOCK_PATH = AUTO_BOTS_DIR / "daemon.lock"
DEFAULT_PID_PATH = AUTO_BOTS_DIR / "daemon.pid"
DEFAULT_STOP_PATH = AUTO_BOTS_DIR / "daemon.stop"
DEFAULT_LOG_PATH = AUTO_BOTS_DIR / "daemon.log"
ACTIVITY_SCHEMA = "codex_agent_activity_v1"
AGENT_REGISTRY_SCHEMA = "orchestrator_agent_registry_v1"
ACTIVITY_RECENT_LIMIT = 10
ACTIVITY_TEXT_LIMIT = 500

RATE_LIMIT_RE = re.compile(
    r"(rate[\s_-]*limit|too many requests|quota|429|retry-after|retry after|reset in|rate_limit_exceeded)",
    re.IGNORECASE,
)
THREAD_KEYS = ("thread_id", "session_id", "conversation_id", "id")
LEGACY_INSTANCE_ID = "legacy"

DEFAULT_WORKER_MODEL_TIERS: dict[str, dict[str, str]] = {
    "simple": {"model": "gpt-5.3-codex-spark", "reasoning_effort": "low"},
    "medium": {"model": "gpt-5.6-terra", "reasoning_effort": "medium"},
    "large": {"model": "gpt-5.6-sol", "reasoning_effort": "high"},
}

DEFAULT_WORKER_MODEL_CATALOG: list[dict[str, str]] = [
    {
        "model": "gpt-5.6-sol",
        "intelligence": "highest",
        "taste": "best detail, judgment, and polish",
        "cost": "highest usage",
        "best_for": "complex, ambiguous, difficult, or high-value work",
    },
    {
        "model": "gpt-5.6-terra",
        "intelligence": "high; competitive with GPT-5.5",
        "taste": "pragmatic and balanced",
        "cost": "lower than GPT-5.5",
        "best_for": "everyday implementation, debugging, and tool use",
    },
    {
        "model": "gpt-5.6-luna",
        "intelligence": "strong",
        "taste": "clear and consistent",
        "cost": "lowest in the GPT-5.6 family",
        "best_for": "specific, repeatable, high-volume structured work",
    },
    {
        "model": "gpt-5.3-codex-spark",
        "intelligence": "focused coding capability",
        "taste": "rapid iteration over polish",
        "cost": "no ChatGPT credits; Pro research preview",
        "best_for": "near-instant, tightly scoped coding iteration",
    },
]

TASK_COMPLEXITY_ALIASES = {
    "simple": "simple",
    "small": "simple",
    "trivial": "simple",
    "quick": "simple",
    "scoped": "simple",
    "low": "simple",
    "medium": "medium",
    "moderate": "medium",
    "normal": "medium",
    "standard": "medium",
    "default": "medium",
    "large": "large",
    "complex": "large",
    "hard": "large",
    "broad": "large",
    "high": "large",
    "deep": "large",
}


DEFAULT_CONFIG: dict[str, Any] = {
    "orchestrator_model": "gpt-5.6-sol",
    "worker_model": "gpt-5.6-terra",
    "worker_model_tiers": copy.deepcopy(DEFAULT_WORKER_MODEL_TIERS),
    "worker_model_catalog": copy.deepcopy(DEFAULT_WORKER_MODEL_CATALOG),
    "reviewer_model": "gpt-5.6-sol",
    "orchestrator_reasoning_effort": "high",
    "worker_reasoning_effort": "medium",
    "reviewer_reasoning_effort": "medium",
    "sandbox": "danger-full-access",
    "max_parallel_workers": 1,
    "heartbeat_sec": 30,
    "no_progress_window_sec": 180,
    "emergency_timeout_sec": 900,
    "rate_limit_default_sleep_sec": 3600,
    "rate_limit_max_sleep_sec": 86400,
    "prompt_file": "",
    "repo": str(REPO_ROOT),
    "test_command": "pixi run pytest -q",
    "dvc_status_command": "pixi run dvc status",
    "dvc_push_command": "pixi run dvc push",
}


def now_unix() -> int:
    return int(time.time())


def read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict[str, Any]:
    if not path.exists():
        write_json(path, DEFAULT_CONFIG)
        return copy.deepcopy(DEFAULT_CONFIG)
    payload = read_json(path, {})
    if not isinstance(payload, dict):
        payload = {}
    config = copy.deepcopy(DEFAULT_CONFIG)
    config.update(payload)
    return config


def resolve_path(value: str | Path | None, base: Path = REPO_ROOT) -> Path | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    path = Path(text).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


def slugify_instance_name(value: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip().lower()).strip(".-_")
    if not slug:
        raise SystemExit("--instance must contain at least one letter, number, dot, underscore, or dash")
    return slug


def instance_dir(instance_id: str) -> Path:
    return ORCHESTRATOR_INSTANCES_DIR / instance_id


def instance_worktree_path(instance_id: str) -> Path:
    return ORCHESTRATOR_WORKTREES_DIR / instance_id


def instance_branch(instance_id: str) -> str:
    return f"orchestrator/{instance_id}"


def git_branch_exists(repo: Path, branch: str) -> bool:
    completed = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=repo,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def ensure_instance_worktree(repo: Path, instance_id: str) -> Path:
    worktree = instance_worktree_path(instance_id)
    if worktree.exists():
        return worktree
    worktree.parent.mkdir(parents=True, exist_ok=True)
    branch = instance_branch(instance_id)
    if git_branch_exists(repo, branch):
        command = ["git", "worktree", "add", str(worktree), branch]
    else:
        command = ["git", "worktree", "add", "-b", branch, str(worktree), "HEAD"]
    subprocess.run(command, cwd=repo, check=True)
    return worktree


def copy_checklist_once(source: Path, destination: Path) -> None:
    if destination.exists():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.exists():
        shutil.copy2(source, destination)
    else:
        write_json(destination, {})


def apply_instance_paths(args: argparse.Namespace) -> argparse.Namespace:
    instance_name = getattr(args, "instance", None)
    if not instance_name:
        args.instance_id = LEGACY_INSTANCE_ID
        args.instance_dir = AUTO_BOTS_DIR
        args.runs_dir = DEFAULT_RUNS_DIR
        args.worktree_path = Path("")
        return args

    instance_id = slugify_instance_name(str(instance_name))
    root = instance_dir(instance_id)
    checklist_source = Path(args.checklist)
    copied_checklist = root / "master_checklist.json"
    copy_checklist_once(checklist_source, copied_checklist)
    args.instance_id = instance_id
    args.instance_dir = root
    args.state = root / "daemon_state.json"
    args.checklist = copied_checklist
    args.lock = root / "daemon.lock"
    args.pid = root / "daemon.pid"
    args.stop_file = root / "daemon.stop"
    args.log = root / "daemon.log"
    args.runs_dir = root / "runs"
    args.worktree_path = instance_worktree_path(instance_id)
    return args


def cli_prompt_file(args: argparse.Namespace) -> Path | None:
    command_prompt = getattr(args, "command_prompt_file", None)
    if command_prompt:
        return resolve_path(command_prompt)
    return resolve_path(getattr(args, "prompt_file", None))


def effective_prompt_file(config: dict[str, Any], args: argparse.Namespace | None = None) -> Path | None:
    if args is not None:
        path = cli_prompt_file(args)
        if path is not None:
            return path
    return resolve_path(config.get("prompt_file"))


def read_prompt_text(prompt_file: Path | None) -> str:
    if prompt_file is None:
        return ""
    return prompt_file.read_text(encoding="utf-8")


def runs_dir(config: dict[str, Any]) -> Path:
    return Path(str(config.get("runs_dir") or DEFAULT_RUNS_DIR))


def run_dir_for_cycle(config: dict[str, Any], cycle_id: int) -> Path:
    return runs_dir(config) / f"{cycle_id:06d}"


def prepare_prompt_snapshot(
    *,
    config: dict[str, Any],
    state: dict[str, Any],
    cycle_id: int,
) -> tuple[str, Path]:
    prompt_file = resolve_path(config.get("prompt_file"))
    prompt_text = read_prompt_text(prompt_file)
    run_dir = run_dir_for_cycle(config, cycle_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = run_dir / "orchestrator_prompt.md"
    snapshot_path.write_text(prompt_text, encoding="utf-8")
    state.update(
        {
            "prompt_file": str(prompt_file or ""),
            "prompt_hash": stable_hash(prompt_text),
            "prompt_snapshot_path": str(snapshot_path),
        }
    )
    return prompt_text, snapshot_path


def initial_state() -> dict[str, Any]:
    return {
        "schema": "orchestrator_daemon_state_v1",
        "instance_id": LEGACY_INSTANCE_ID,
        "instance_dir": str(AUTO_BOTS_DIR),
        "runs_dir": str(DEFAULT_RUNS_DIR),
        "checklist_path": str(DEFAULT_CHECKLIST_PATH),
        "log_path": str(DEFAULT_LOG_PATH),
        "worktree_path": "",
        "status": "idle",
        "cycle_id": 0,
        "phase": "",
        "active_agent_role": "",
        "thread_id": "",
        "codex_command": [],
        "latest_jsonl_path": "",
        "latest_stderr_path": "",
        "latest_last_message_path": "",
        "latest_activity_path": "",
        "active_process": {},
        "latest_orchestrator_result": {},
        "previous_orchestrator_result": {},
        "last_completed_cycle_id": 0,
        "consecutive_orchestrator_failures": 0,
        "rate_limit": {},
        "lane_id": "",
        "latest_report": "",
        "prompt_file": "",
        "prompt_hash": "",
        "prompt_snapshot_path": "",
        "cycle_start_git_status": "",
        "cycle_start_git_status_path": "",
        "merge_back": {},
        "goal_complete": False,
        "updated_at_unix": now_unix(),
    }


def load_state(path: Path = DEFAULT_STATE_PATH) -> dict[str, Any]:
    payload = read_json(path, initial_state())
    if not isinstance(payload, dict):
        payload = initial_state()
    state = initial_state()
    state.update(payload)
    return state


def save_state(state: dict[str, Any], path: Path = DEFAULT_STATE_PATH) -> None:
    state["updated_at_unix"] = now_unix()
    write_json(path, state)


def update_state_instance_metadata(state: dict[str, Any], args: argparse.Namespace, config: dict[str, Any]) -> None:
    state.update(
        {
            "schema": "orchestrator_daemon_state_v1",
            "instance_id": str(getattr(args, "instance_id", LEGACY_INSTANCE_ID)),
            "instance_dir": str(getattr(args, "instance_dir", AUTO_BOTS_DIR)),
            "runs_dir": str(config.get("runs_dir") or getattr(args, "runs_dir", DEFAULT_RUNS_DIR)),
            "checklist_path": str(args.checklist),
            "log_path": str(getattr(args, "log", DEFAULT_LOG_PATH)),
            "worktree_path": str(getattr(args, "worktree_path", "") or ""),
        }
    )


def load_checklist(path: Path = DEFAULT_CHECKLIST_PATH) -> dict[str, Any]:
    payload = read_json(path, {})
    return payload if isinstance(payload, dict) else {}


def deliverables(checklist: dict[str, Any]) -> list[dict[str, Any]]:
    rows = checklist.get("deliverables")
    return [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []


def checklist_complete(checklist: dict[str, Any]) -> bool:
    rows = deliverables(checklist)
    return bool(rows) and all(row.get("status") == "accepted" and row.get("evidence_artifact") for row in rows)


def checklist_summary(checklist: dict[str, Any]) -> dict[str, Any]:
    rows = deliverables(checklist)
    counts: dict[str, int] = {}
    for row in rows:
        status = str(row.get("status") or "unknown")
        counts[status] = counts.get(status, 0) + 1
    return {
        "total": len(rows),
        "counts": counts,
        "accepted": counts.get("accepted", 0),
        "all_complete": checklist_complete(checklist),
        "checklist_hash": stable_hash(rows) if rows else "",
    }


def extract_thread_id(events: list[dict[str, Any]]) -> str:
    for event in reversed(events):
        for key in THREAD_KEYS:
            value = event.get(key)
            if isinstance(value, str) and value:
                return value
        nested = event.get("session") or event.get("conversation") or event.get("thread")
        if isinstance(nested, dict):
            for key in THREAD_KEYS:
                value = nested.get(key)
                if isinstance(value, str) and value:
                    return value
    return ""


def read_jsonl_events(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def truncate_text(value: Any, limit: int = ACTIVITY_TEXT_LIMIT) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)] + "..."


def tail_lines(text: str, line_count: int) -> str:
    if line_count <= 0:
        return ""
    return "\n".join(text.splitlines()[-line_count:])


def file_tail_lines(path: Path, line_count: int) -> str:
    if line_count <= 0 or not path.exists() or not path.is_file():
        return ""
    try:
        return tail_lines(path.read_text(encoding="utf-8", errors="replace"), line_count)
    except OSError:
        return ""


def event_timestamp_unix(event: dict[str, Any]) -> int | None:
    for key in ("created_at_unix", "timestamp_unix", "time_unix", "ts_unix"):
        value = event.get(key)
        if isinstance(value, (int, float)):
            return int(value)
    for key in ("created_at", "timestamp", "time", "ts"):
        value = event.get(key)
        if isinstance(value, (int, float)):
            return int(value)
        if not isinstance(value, str) or not value.strip():
            continue
        text = value.strip()
        if text.isdigit():
            return int(text)
        normalized = text.replace(" ", "T")
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        try:
            parsed = dt.datetime.fromisoformat(normalized)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
        return int(parsed.timestamp())
    return None


def event_item(event: dict[str, Any]) -> dict[str, Any]:
    item = event.get("item")
    return item if isinstance(item, dict) else event


def item_id(event: dict[str, Any], index: int) -> str:
    item = event_item(event)
    for key in ("id", "item_id", "call_id"):
        value = item.get(key) or event.get(key)
        if isinstance(value, str) and value:
            return value
    return f"event_{index}"


def item_type(event: dict[str, Any]) -> str:
    item = event_item(event)
    for key in ("type", "item_type", "kind"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return value
    return str(event.get("type") or "")


def item_status(event: dict[str, Any]) -> str:
    item = event_item(event)
    value = item.get("status") or event.get("status")
    return str(value or "")


def command_from_item(item: dict[str, Any]) -> str:
    command = item.get("command") or item.get("cmd") or item.get("argv")
    if isinstance(command, list):
        return " ".join(str(part) for part in command)
    return str(command or "")


def output_tail_from_item(item: dict[str, Any], line_count: int = 8) -> str:
    for key in ("aggregated_output", "output", "stdout", "stderr"):
        value = item.get(key)
        if isinstance(value, str) and value:
            return truncate_text(tail_lines(value, line_count), 1200)
    return ""


def exit_code_from_item(item: dict[str, Any]) -> int | None:
    value = item.get("exit_code")
    if value is None:
        value = item.get("returncode")
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, str) and re.fullmatch(r"-?\d+", value.strip()):
        return int(value)
    return None


def activity_record_from_event(event: dict[str, Any], index: int) -> dict[str, Any]:
    item = event_item(event)
    event_type = str(event.get("type") or "")
    record = {
        "id": item_id(event, index),
        "event_index": index,
        "event_type": event_type,
        "type": item_type(event),
        "status": item_status(event),
        "started_at_unix": event_timestamp_unix(event),
    }
    if record["type"] == "command_execution" or command_from_item(item):
        record.update(
            {
                "type": "command_execution",
                "command": command_from_item(item),
                "exit_code": exit_code_from_item(item),
                "output_tail": output_tail_from_item(item),
            }
        )
    elif record["type"] == "agent_message":
        record["text"] = truncate_text(item.get("text") or item.get("message") or event.get("message"))
    elif record["type"] in {"file_change", "file_edit", "file_operation"}:
        record["path"] = str(item.get("path") or item.get("file") or item.get("filename") or "")
    elif record["type"] in {"web_search", "web_search_call", "search_query"}:
        record["query"] = truncate_text(item.get("query") or item.get("q") or item.get("search_query"))
    return record


def activity_summary_from_events(
    events: list[dict[str, Any]],
    *,
    role: str = "",
    jsonl_path: Path | None = None,
    stderr_path: Path | None = None,
    last_message_path: Path | None = None,
    generated_at_unix: int | None = None,
    previous_activity: dict[str, Any] | None = None,
    no_progress_window_sec: int | None = None,
) -> dict[str, Any]:
    generated_at_unix = generated_at_unix or now_unix()
    active_by_id: dict[str, dict[str, Any]] = {}
    recent_commands: list[dict[str, Any]] = []
    recent_failures: list[dict[str, Any]] = []
    file_events: list[dict[str, Any]] = []
    web_searches: list[dict[str, Any]] = []
    latest_message = ""
    last_completed_command: dict[str, Any] = {}
    last_failed_command: dict[str, Any] = {}
    token_usage: dict[str, Any] = {}
    thread_id = extract_thread_id(events)
    last_event_at = 0
    last_event_index = -1

    previous_active = previous_activity.get("active_item") if isinstance(previous_activity, dict) else {}
    previous_active_items = previous_activity.get("active_items") if isinstance(previous_activity, dict) else []
    previous_started_at: dict[str, int] = {}
    if isinstance(previous_active, dict) and previous_active.get("id"):
        previous_started_at[str(previous_active["id"])] = int(previous_active.get("started_at_unix") or 0)
    if isinstance(previous_active_items, list):
        for row in previous_active_items:
            if isinstance(row, dict) and row.get("id"):
                previous_started_at[str(row["id"])] = int(row.get("started_at_unix") or 0)

    for index, event in enumerate(events):
        event_type = str(event.get("type") or "")
        event_time = event_timestamp_unix(event) or 0
        last_event_at = max(last_event_at, event_time)
        last_event_index = index
        item = event_item(event)
        record = activity_record_from_event(event, index)
        status = str(record.get("status") or "")
        record_type = str(record.get("type") or "")

        if event_type.endswith("started") or status == "in_progress":
            started_at = int(record.get("started_at_unix") or 0) or previous_started_at.get(str(record["id"])) or generated_at_unix
            record["started_at_unix"] = started_at
            active_by_id[str(record["id"])] = record
            continue

        if record_type == "agent_message":
            text = str(record.get("text") or item.get("text") or "")
            if text:
                latest_message = truncate_text(text)

        if record_type == "command_execution":
            prior = active_by_id.pop(str(record["id"]), {})
            started_at = int(prior.get("started_at_unix") or 0) or int(record.get("started_at_unix") or 0)
            if started_at:
                record["started_at_unix"] = started_at
                record["duration_sec"] = max(0, generated_at_unix - started_at) if not event_time else max(0, event_time - started_at)
            if not record.get("command"):
                record["command"] = str(prior.get("command") or "")
            exit_code = record.get("exit_code")
            if exit_code is None:
                exit_code = prior.get("exit_code")
                record["exit_code"] = exit_code
            if not record.get("status"):
                record["status"] = "failed" if exit_code not in {None, 0} else "completed"
            compact = {key: value for key, value in record.items() if key in {"id", "command", "status", "exit_code", "duration_sec", "output_tail", "event_index"}}
            recent_commands.append(compact)
            last_completed_command = compact
            if record.get("status") == "failed" or (isinstance(exit_code, int) and exit_code != 0):
                recent_failures.append(compact)
                last_failed_command = compact
        elif record_type in {"file_change", "file_edit", "file_operation"}:
            file_events.append({key: value for key, value in record.items() if key in {"id", "type", "path", "status", "event_index"}})
        elif record_type in {"web_search", "web_search_call", "search_query"}:
            web_searches.append({key: value for key, value in record.items() if key in {"id", "type", "query", "status", "event_index"}})

        usage = event.get("usage") or item.get("usage")
        if isinstance(usage, dict):
            token_usage = usage

    active_items = list(active_by_id.values())
    for record in active_items:
        started_at = int(record.get("started_at_unix") or 0)
        if started_at:
            record["duration_sec"] = max(0, generated_at_unix - started_at)
    active_commands = [row for row in active_items if row.get("type") == "command_execution"]
    active_item = active_commands[-1] if active_commands else (active_items[-1] if active_items else {})
    last_event_age_sec = max(0, generated_at_unix - last_event_at) if last_event_at else None
    if last_event_age_sec is None and jsonl_path and jsonl_path.exists():
        last_event_age_sec = max(0, generated_at_unix - int(jsonl_path.stat().st_mtime))
    no_progress_window_sec = max(1, int(no_progress_window_sec or DEFAULT_CONFIG["no_progress_window_sec"]))
    stuck_suspected = bool(active_item) and last_event_age_sec is not None and last_event_age_sec >= no_progress_window_sec
    return {
        "schema": ACTIVITY_SCHEMA,
        "role": role,
        "thread_id": thread_id,
        "generated_at_unix": generated_at_unix,
        "jsonl_path": str(jsonl_path or ""),
        "stderr_path": str(stderr_path or ""),
        "last_message_path": str(last_message_path or ""),
        "event_count": len(events),
        "last_event_index": last_event_index,
        "last_event_age_sec": last_event_age_sec,
        "latest_message": latest_message,
        "active_item": active_item,
        "active_items": active_items,
        "recent_commands": recent_commands[-ACTIVITY_RECENT_LIMIT:],
        "last_completed_command": last_completed_command,
        "last_failed_command": last_failed_command,
        "recent_failures": recent_failures[-ACTIVITY_RECENT_LIMIT:],
        "recent_file_events": file_events[-ACTIVITY_RECENT_LIMIT:],
        "recent_web_searches": web_searches[-ACTIVITY_RECENT_LIMIT:],
        "token_usage": token_usage,
        "stuck_suspected": stuck_suspected,
    }


def write_activity_snapshot(
    *,
    role: str,
    jsonl_path: Path,
    stderr_path: Path,
    last_message_path: Path,
    activity_path: Path,
    no_progress_window_sec: int | None = None,
) -> dict[str, Any]:
    previous = read_json(activity_path, {}) if activity_path.exists() else {}
    activity = activity_summary_from_events(
        read_jsonl_events(jsonl_path),
        role=role,
        jsonl_path=jsonl_path,
        stderr_path=stderr_path,
        last_message_path=last_message_path,
        generated_at_unix=now_unix(),
        previous_activity=previous if isinstance(previous, dict) else {},
        no_progress_window_sec=no_progress_window_sec,
    )
    write_json(activity_path, activity)
    return activity


def compact_activity(activity: dict[str, Any]) -> dict[str, Any]:
    return {
        "latest_message": activity.get("latest_message", ""),
        "active_item": activity.get("active_item", {}),
        "recent_commands": activity.get("recent_commands", []),
        "last_completed_command": activity.get("last_completed_command", {}),
        "last_failed_command": activity.get("last_failed_command", {}),
        "last_event_age_sec": activity.get("last_event_age_sec"),
        "stuck_suspected": bool(activity.get("stuck_suspected")),
    }


def path_debug(path: str | Path, *, include_tail: bool = False, tail_bytes: int = 4000) -> dict[str, Any]:
    resolved = Path(path) if path else Path("")
    payload: dict[str, Any] = {
        "path": str(path or ""),
        "exists": bool(path) and resolved.exists(),
    }
    if not payload["exists"]:
        return payload
    stat = resolved.stat()
    payload.update(
        {
            "size_bytes": stat.st_size,
            "modified_at_unix": int(stat.st_mtime),
            "modified_age_sec": max(0, now_unix() - int(stat.st_mtime)),
        }
    )
    if include_tail and resolved.is_file() and stat.st_size:
        with resolved.open("rb") as handle:
            handle.seek(max(0, stat.st_size - tail_bytes))
            payload["tail"] = handle.read(tail_bytes).decode("utf-8", errors="replace")
    return payload


def proc_table() -> dict[int, dict[str, Any]]:
    proc_root = Path("/proc")
    if not proc_root.exists():
        return {}
    ticks_per_second = os.sysconf("SC_CLK_TCK")
    try:
        uptime_seconds = float((proc_root / "uptime").read_text(encoding="utf-8").split()[0])
    except (OSError, ValueError, IndexError):
        uptime_seconds = 0.0
    rows: dict[int, dict[str, Any]] = {}
    for entry in proc_root.iterdir():
        if not entry.name.isdigit():
            continue
        pid = int(entry.name)
        try:
            stat_text = (entry / "stat").read_text(encoding="utf-8", errors="replace")
            right = stat_text.rsplit(")", 1)[1].strip().split()
            state = right[0]
            ppid = int(right[1])
            start_ticks = int(right[19])
            raw_cmdline = (entry / "cmdline").read_bytes().replace(b"\0", b" ").strip()
            command = raw_cmdline.decode("utf-8", errors="replace")
            if not command:
                command = stat_text.split("(", 1)[1].rsplit(")", 1)[0]
        except (OSError, ValueError, IndexError):
            continue
        elapsed_sec = max(0, int(uptime_seconds - (start_ticks / ticks_per_second))) if uptime_seconds else 0
        rows[pid] = {"pid": pid, "ppid": ppid, "state": state, "elapsed_sec": elapsed_sec, "command": command}
    return rows


def descendant_processes(root_pid: int, table: dict[int, dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    if root_pid <= 0:
        return []
    rows = table or proc_table()
    children_by_parent: dict[int, list[dict[str, Any]]] = {}
    for row in rows.values():
        children_by_parent.setdefault(int(row["ppid"]), []).append(row)
    descendants: list[dict[str, Any]] = []
    pending = list(children_by_parent.get(root_pid, []))
    while pending:
        child = pending.pop(0)
        descendants.append(child)
        pending.extend(children_by_parent.get(int(child["pid"]), []))
    return descendants


def daemon_diagnostics(
    args: argparse.Namespace,
    state: dict[str, Any],
    *,
    include_tails: bool = False,
    table: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    config = load_config(args.config)
    heartbeat_sec = max(1, int(config.get("heartbeat_sec") or DEFAULT_CONFIG["heartbeat_sec"]))
    no_progress_window_sec = max(1, int(config.get("no_progress_window_sec") or DEFAULT_CONFIG["no_progress_window_sec"]))
    pid_text = args.pid.read_text(encoding="utf-8").strip() if args.pid.exists() else ""
    try:
        daemon_pid = int(pid_text)
    except ValueError:
        daemon_pid = 0
    processes = table or proc_table()
    daemon_process = processes.get(daemon_pid, {})
    descendants = descendant_processes(daemon_pid, processes)
    codex_children = [row for row in descendants if "codex exec" in str(row.get("command") or "")]
    artifact_paths = {
        "jsonl": state.get("latest_jsonl_path", ""),
        "stderr": state.get("latest_stderr_path", ""),
        "last_message": state.get("latest_last_message_path", ""),
        "prompt_snapshot": state.get("prompt_snapshot_path", ""),
        "cycle_start_git_status": state.get("cycle_start_git_status_path", ""),
    }
    artifacts = {name: path_debug(path, include_tail=include_tails and name in {"stderr", "last_message"}) for name, path in artifact_paths.items()}
    output_artifacts = [artifacts["jsonl"], artifacts["stderr"], artifacts["last_message"]]
    output_bytes = sum(int(row.get("size_bytes") or 0) for row in output_artifacts)
    newest_output_at = max((int(row.get("modified_at_unix") or 0) for row in output_artifacts if row.get("exists")), default=0)
    active_process = state.get("active_process") if isinstance(state.get("active_process"), dict) else {}
    state_age_sec = max(0, now_unix() - int(state.get("updated_at_unix") or 0))
    max_codex_elapsed_sec = max((int(row.get("elapsed_sec") or 0) for row in codex_children), default=0)
    suspicions: list[str] = []
    if args.lock.exists() and not daemon_pid:
        suspicions.append("lock_exists_without_pid")
    if daemon_pid and not daemon_process:
        suspicions.append("pid_file_process_missing")
    if state.get("status") == "running" and str(state.get("phase") or "").startswith("codex_") and not codex_children:
        suspicions.append("codex_phase_without_active_codex_child")
    if state.get("status") == "running" and codex_children and state_age_sec > heartbeat_sec * 2:
        suspicions.append("daemon_state_not_heartbeating_while_codex_active")
    if codex_children and output_bytes == 0 and max_codex_elapsed_sec >= no_progress_window_sec:
        suspicions.append("active_codex_no_output_over_no_progress_window")
    latest_result = state.get("latest_orchestrator_result") if isinstance(state.get("latest_orchestrator_result"), dict) else {}
    if latest_result.get("status") == "failure":
        suspicions.append(f"latest_orchestrator_failure:{latest_result.get('error') or 'unknown'}")
    return {
        "schema": "orchestrator_daemon_diagnostics_v1",
        "generated_at_unix": now_unix(),
        "state_age_sec": state_age_sec,
        "heartbeat_sec": heartbeat_sec,
        "no_progress_window_sec": no_progress_window_sec,
        "daemon_pid": daemon_pid,
        "daemon_process": daemon_process,
        "descendant_processes": descendants,
        "active_codex_processes": codex_children,
        "active_process": active_process,
        "artifacts": artifacts,
        "newest_output_at_unix": newest_output_at,
        "output_bytes": output_bytes,
        "suspicions": suspicions,
        "healthy": bool(daemon_process) and not suspicions,
    }


def event_text(event: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("type", "message", "error", "details", "reason"):
        value = event.get(key)
        if isinstance(value, str):
            parts.append(value)
        elif isinstance(value, dict):
            parts.append(json.dumps(value, sort_keys=True, default=str))
    return " ".join(parts)


def parse_duration_seconds(text: str) -> int | None:
    lowered = text.lower()
    match = re.search(r"(?:retry-after|retry after|reset in|try again in)\s*[:=]?\s*(\d+)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)?", lowered)
    if not match:
        match = re.search(r"\b(\d+)\s*(seconds?|secs?|minutes?|mins?|hours?|hrs?)\b", lowered)
    if not match:
        return None
    value = int(match.group(1))
    unit = (match.group(2) or "seconds").lower()
    if unit.startswith(("h", "hour")):
        return value * 3600
    if unit.startswith(("m", "min")):
        return value * 60
    return value


def parse_absolute_reset_unix(text: str, current_time: int | None = None) -> int | None:
    current_time = current_time or now_unix()
    candidates = re.findall(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:Z|[+-]\d{2}:?\d{2})?", text)
    for candidate in candidates:
        normalized = candidate.replace(" ", "T")
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        if re.search(r"[+-]\d{4}$", normalized):
            normalized = normalized[:-5] + normalized[-5:-2] + ":" + normalized[-2:]
        try:
            parsed = dt.datetime.fromisoformat(normalized)
        except ValueError:
            continue
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=dt.datetime.now().astimezone().tzinfo)
        unix = int(parsed.timestamp())
        if unix >= current_time:
            return unix
    return None


def detect_rate_limit(
    *,
    events: list[dict[str, Any]],
    stdout_text: str,
    stderr_text: str,
    returncode: int,
    default_sleep_sec: int,
    max_sleep_sec: int,
    current_time: int | None = None,
) -> dict[str, Any] | None:
    current_time = current_time or now_unix()
    event_matches = [
        event
        for event in events
        if str(event.get("type") or "") in {"error", "turn.failed"} and RATE_LIMIT_RE.search(event_text(event))
    ]
    combined = "\n".join([stderr_text] + [event_text(event) for event in event_matches])
    if not event_matches and not RATE_LIMIT_RE.search(stderr_text):
        return None
    if returncode == 0 and not event_matches and not RATE_LIMIT_RE.search(stderr_text):
        return None
    reset_unix = parse_absolute_reset_unix(combined, current_time)
    if reset_unix is None:
        duration = parse_duration_seconds(combined)
        if duration is None:
            duration = default_sleep_sec
        reset_unix = current_time + max(1, min(duration, max_sleep_sec))
    else:
        reset_unix = current_time + min(max_sleep_sec, max(1, reset_unix - current_time))
    return {
        "detected": True,
        "resume_at_unix": reset_unix,
        "sleep_sec": max(0, reset_unix - current_time),
        "matched_event_count": len(event_matches),
        "signature": "rate_limit_or_quota",
    }


def role_reasoning_effort(role: str, config: dict[str, Any]) -> str:
    value = config.get(f"{role}_reasoning_effort")
    if value:
        return str(value)
    return str(DEFAULT_CONFIG.get(f"{role}_reasoning_effort") or "")


def normalize_task_complexity(value: Any, default: str = "medium") -> str:
    normalized_default = TASK_COMPLEXITY_ALIASES.get(str(default or "medium").strip().lower(), "medium")
    text = str(value or "").strip().lower()
    return TASK_COMPLEXITY_ALIASES.get(text, normalized_default)


def worker_model_fallback(config: dict[str, Any]) -> dict[str, str]:
    return {
        "model": str(config.get("worker_model") or DEFAULT_CONFIG["worker_model"]),
        "reasoning_effort": str(config.get("worker_reasoning_effort") or DEFAULT_CONFIG["worker_reasoning_effort"]),
    }


def select_worker_model_tier(config: dict[str, Any], complexity: Any) -> dict[str, str]:
    normalized = normalize_task_complexity(complexity)
    fallback = worker_model_fallback(config)
    tiers = config.get("worker_model_tiers")
    if not isinstance(tiers, dict):
        return {"complexity": normalized, "source": "fallback", **fallback}
    tier = tiers.get(normalized)
    if not isinstance(tier, dict):
        return {"complexity": normalized, "source": "fallback", **fallback}
    model = str(tier.get("model") or "").strip()
    reasoning_effort = str(tier.get("reasoning_effort") or tier.get("reasoning") or "").strip()
    if not model or not reasoning_effort:
        return {"complexity": normalized, "source": "fallback", **fallback}
    return {"complexity": normalized, "source": "worker_model_tiers", "model": model, "reasoning_effort": reasoning_effort}


def worker_model_tier_table(config: dict[str, Any]) -> list[dict[str, str]]:
    return [select_worker_model_tier(config, complexity) for complexity in ("simple", "medium", "large")]


def render_worker_codex_command_template(config: dict[str, Any], repo: Path = REPO_ROOT, complexity: Any = "medium") -> str:
    tier = select_worker_model_tier(config, complexity)
    reasoning_args = f' -c model_reasoning_effort="{tier["reasoning_effort"]}"' if tier["reasoning_effort"] else ""
    return (
        f'codex exec --json -m {tier["model"]}{reasoning_args} '
        f'--sandbox {config.get("sandbox", DEFAULT_CONFIG["sandbox"])} -C {repo} '
        "-o <last_message_path> - > <jsonl_path> 2> <stderr_path>"
    )


def codex_command(
    *,
    role: str,
    prompt: str,
    model: str,
    repo: Path,
    sandbox: str,
    jsonl_path: Path,
    last_message_path: Path,
    reasoning_effort: str = "",
    thread_id: str = "",
) -> tuple[list[str], str | None]:
    reasoning_args = ["-c", f'model_reasoning_effort="{reasoning_effort}"'] if reasoning_effort else []
    if thread_id:
        command = [
            "codex",
            "exec",
            "resume",
            "--json",
            "-m",
            model,
            *reasoning_args,
            "-o",
            str(last_message_path),
            thread_id,
            "-",
        ]
        return command, prompt
    command = [
        "codex",
        "exec",
        "--json",
        "-m",
        model,
        *reasoning_args,
        "--sandbox",
        sandbox,
        "-C",
        str(repo),
        "-o",
        str(last_message_path),
        "-",
    ]
    return command, prompt


def run_codex_role(
    *,
    role: str,
    prompt: str,
    model: str,
    repo: Path,
    sandbox: str,
    cycle_id: int,
    state: dict[str, Any],
    config: dict[str, Any],
    thread_id: str = "",
    state_path: Path = DEFAULT_STATE_PATH,
) -> dict[str, Any]:
    run_dir = run_dir_for_cycle(config, cycle_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = run_dir / f"{role}.jsonl"
    stderr_path = run_dir / f"{role}.stderr"
    last_message_path = run_dir / f"{role}.last_message.md"
    activity_path = run_dir / "activity.json" if role == "orchestrator" else run_dir / f"{role}.activity.json"
    jsonl_path.write_text("", encoding="utf-8")
    stderr_path.write_text("", encoding="utf-8")
    command, stdin_text = codex_command(
        role=role,
        prompt=prompt,
        model=model,
        reasoning_effort=role_reasoning_effort(role, config),
        repo=repo,
        sandbox=sandbox,
        jsonl_path=jsonl_path,
        last_message_path=last_message_path,
        thread_id=thread_id,
    )
    state.update(
        {
            "status": "running",
            "phase": f"codex_{role}",
            "active_agent_role": role,
            "thread_id": thread_id,
            "codex_command": command,
            "latest_jsonl_path": str(jsonl_path),
            "latest_stderr_path": str(stderr_path),
            "latest_last_message_path": str(last_message_path),
            "latest_activity_path": str(activity_path),
            "active_process": {},
        }
    )
    save_state(state, state_path)
    write_activity_snapshot(
        role=role,
        jsonl_path=jsonl_path,
        stderr_path=stderr_path,
        last_message_path=last_message_path,
        activity_path=activity_path,
        no_progress_window_sec=int(config.get("no_progress_window_sec") or DEFAULT_CONFIG["no_progress_window_sec"]),
    )
    started_at = now_unix()
    heartbeat_sec = max(1, int(config.get("heartbeat_sec") or DEFAULT_CONFIG["heartbeat_sec"]))
    no_progress_window_sec = max(1, int(config.get("no_progress_window_sec") or DEFAULT_CONFIG["no_progress_window_sec"]))
    with jsonl_path.open("w", encoding="utf-8") as stdout_handle, stderr_path.open("w", encoding="utf-8") as stderr_handle:
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
            cwd=repo,
        )
        try:
            if process.stdin is not None:
                process.stdin.write(stdin_text or "")
                process.stdin.close()
            last_heartbeat_monotonic = 0.0
            while True:
                returncode = process.poll()
                now_monotonic = time.monotonic()
                should_heartbeat = returncode is not None or now_monotonic - last_heartbeat_monotonic >= heartbeat_sec
                if should_heartbeat:
                    stdout_handle.flush()
                    stderr_handle.flush()
                    jsonl = path_debug(jsonl_path)
                    stderr = path_debug(stderr_path)
                    last_message = path_debug(last_message_path)
                    activity = write_activity_snapshot(
                        role=role,
                        jsonl_path=jsonl_path,
                        stderr_path=stderr_path,
                        last_message_path=last_message_path,
                        activity_path=activity_path,
                        no_progress_window_sec=no_progress_window_sec,
                    )
                    newest_output_at = max(
                        int(row.get("modified_at_unix") or 0)
                        for row in (jsonl, stderr, last_message)
                        if row.get("exists")
                    )
                    output_age_sec = max(0, now_unix() - newest_output_at) if newest_output_at else max(0, now_unix() - started_at)
                    active_process = {
                        "pid": process.pid,
                        "role": role,
                        "status": "exited" if returncode is not None else "running",
                        "started_at_unix": started_at,
                        "running_sec": max(0, now_unix() - started_at),
                        "last_heartbeat_at_unix": now_unix(),
                        "returncode": returncode,
                        "stdout_bytes": int(jsonl.get("size_bytes") or 0),
                        "stderr_bytes": int(stderr.get("size_bytes") or 0),
                        "last_message_bytes": int(last_message.get("size_bytes") or 0),
                        "output_age_sec": output_age_sec,
                        "no_progress_window_sec": no_progress_window_sec,
                        "stuck_suspected": bool(activity.get("stuck_suspected")) or output_age_sec >= no_progress_window_sec,
                        "activity_path": str(activity_path),
                    }
                    state["active_process"] = active_process
                    save_state(state, state_path)
                    last_heartbeat_monotonic = now_monotonic
                if returncode is not None:
                    break
                time.sleep(min(5, heartbeat_sec))
        finally:
            if process.poll() is None:
                process.wait()
    stdout_text = jsonl_path.read_text(encoding="utf-8", errors="replace")
    stderr_text = stderr_path.read_text(encoding="utf-8", errors="replace")
    events = read_jsonl_events(jsonl_path)
    write_activity_snapshot(
        role=role,
        jsonl_path=jsonl_path,
        stderr_path=stderr_path,
        last_message_path=last_message_path,
        activity_path=activity_path,
        no_progress_window_sec=no_progress_window_sec,
    )
    discovered_thread_id = extract_thread_id(events) or thread_id
    rate_limit = detect_rate_limit(
        events=events,
        stdout_text=stdout_text,
        stderr_text=stderr_text,
        returncode=process.returncode,
        default_sleep_sec=int(config.get("rate_limit_default_sleep_sec") or DEFAULT_CONFIG["rate_limit_default_sleep_sec"]),
        max_sleep_sec=int(config.get("rate_limit_max_sleep_sec") or DEFAULT_CONFIG["rate_limit_max_sleep_sec"]),
    )
    if rate_limit:
        rate_limit.update(
            {
                "agent_role": role,
                "thread_id": discovered_thread_id,
                "command": command,
                "prompt": prompt,
                "prompt_file": state.get("prompt_file", ""),
                "prompt_hash": state.get("prompt_hash", ""),
                "prompt_snapshot_path": state.get("prompt_snapshot_path", ""),
                "jsonl_path": str(jsonl_path),
                "stderr_path": str(stderr_path),
                "last_message_path": str(last_message_path),
            }
        )
    return {
        "role": role,
        "command": command,
        "returncode": process.returncode,
        "jsonl_path": jsonl_path,
        "stderr_path": stderr_path,
        "last_message_path": last_message_path,
        "activity_path": activity_path,
        "events": events,
        "thread_id": discovered_thread_id,
        "rate_limit": rate_limit,
    }


def extract_json_object(text: str) -> dict[str, Any]:
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", stripped, re.DOTALL)
    candidates = [fence.group(1)] if fence else []
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start != -1 and end > start:
        candidates.append(stripped[start : end + 1])
    for candidate in candidates:
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def previous_run_artifacts(state: dict[str, Any]) -> dict[str, Any]:
    latest_result = state.get("latest_orchestrator_result") if isinstance(state.get("latest_orchestrator_result"), dict) else {}
    previous_result = state.get("previous_orchestrator_result") if isinstance(state.get("previous_orchestrator_result"), dict) else {}
    return {
        "latest_jsonl_path": state.get("latest_jsonl_path", ""),
        "latest_stderr_path": state.get("latest_stderr_path", ""),
        "latest_last_message_path": state.get("latest_last_message_path", ""),
        "latest_activity_path": state.get("latest_activity_path", ""),
        "latest_orchestrator_result": latest_result or previous_result,
        "latest_report": state.get("latest_report", ""),
        "last_completed_cycle_id": state.get("last_completed_cycle_id", 0),
        "consecutive_orchestrator_failures": state.get("consecutive_orchestrator_failures", 0),
    }


def orchestrator_prompt(
    checklist: dict[str, Any],
    state: dict[str, Any],
    user_prompt: str = "",
    config: dict[str, Any] | None = None,
) -> str:
    prompt_config = copy.deepcopy(DEFAULT_CONFIG)
    if config:
        prompt_config.update(config)
    worker_tiers = worker_model_tier_table(prompt_config)
    worker_model_catalog = prompt_config["worker_model_catalog"]
    worker_repo = resolve_path(prompt_config.get("repo"), REPO_ROOT) or REPO_ROOT
    worker_commands = {
        row["complexity"]: render_worker_codex_command_template(prompt_config, worker_repo, row["complexity"]) for row in worker_tiers
    }
    active_run_dir = run_dir_for_cycle(prompt_config, int(state.get("cycle_id") or 0)) if state.get("cycle_id") else runs_dir(prompt_config)
    agent_registry_path = active_run_dir / "agent_registry.json"
    return (
        "You are the prompt-driven bot autonomy orchestrator for this TrinityCore repo. "
        "Run one durable orchestration pass toward the user's original goal.\n\n"
        "Responsibilities for this pass:\n"
        "- Read and follow the user prompt snapshot shown below.\n"
        "- Inspect the current repo, checklist, daemon state, and prior run artifacts.\n"
        "- Create or resume worker/reviewer Codex sessions as needed; the daemon will not launch them for you.\n"
        "- Run validation yourself with the repo tools when validation is needed.\n"
        "- Commit experiment code/configs to git, checkpoint generated data/artifacts with DVC, run dvc status, and push DVC artifacts when appropriate.\n"
        "- Update progress/checklist/status files with evidence paths, validation outcomes, blockers, and the exact next handoff prompt for the next fresh agent.\n\n"
        "Worktree cleanup requirement:\n"
        "- Before returning, inspect git status in the active worktree.\n"
        "- Commit useful finished changes with a focused message, including progress/checklist/status updates and useful experiment configs/code.\n"
        "- Checkpoint generated data/artifacts with DVC, run dvc status, and run dvc push when artifacts were produced.\n"
        "- Discard only changes you made in this pass that are wrong or failed; do not discard pre-existing user changes from the starting status snapshot unless the user explicitly asked you to.\n"
        "- This requirement applies whether the pass succeeds, fails, or needs follow-up; leave the worktree clean except for protected pre-existing changes.\n\n"
        "Worker model routing requirement:\n"
        "- Before creating or resuming a worker Codex session, assign the worker task complexity as simple, medium, or large and choose the best model for that specific task.\n"
        "- Use simple for near-instant scoped edits, inspections, or test updates with limited blast radius.\n"
        "- Use medium for normal implementation tasks that require several files, local tests, or moderate debugging.\n"
        "- Use large for broad, ambiguous, high-risk, or long-running investigations and changes.\n"
        "- Treat the tier table as defaults, not a restriction. Select from the model catalog by task ambiguity, difficulty, repetition, required polish, latency, and usage cost.\n"
        "- Use the lowest reasoning effort that can reliably complete the task; use high for difficult multi-step work and medium for normal implementation or review.\n"
        "- Launch worker sessions with the selected model and reasoning effort; the daemon will not launch workers for you.\n"
        "- When a worker tier affects the work, record the chosen complexity, model, and reasoning effort in progress summaries.\n\n"
        "Worker/reviewer visibility requirement:\n"
        f"- Put worker and reviewer artifacts under the current run directory: {active_run_dir}\n"
        "- For each launched or resumed worker/reviewer, use JSONL, stderr, and last-message paths in that run directory.\n"
        f"- Write or update {agent_registry_path} whenever launching or resuming a worker/reviewer.\n"
        f"- Use registry schema {AGENT_REGISTRY_SCHEMA} with an agents array; each entry should include id, role, status, complexity, model, reasoning_effort, jsonl_path, stderr_path, last_message_path, prompt_path, and started_at_unix when known.\n\n"
        f"Worker model catalog:\n{json.dumps(worker_model_catalog, indent=2, sort_keys=True)}\n\n"
        f"Worker model tier defaults:\n{json.dumps(worker_tiers, indent=2, sort_keys=True)}\n\n"
        f"Reviewer default:\n{json.dumps({'model': prompt_config['reviewer_model'], 'reasoning_effort': prompt_config['reviewer_reasoning_effort']}, indent=2, sort_keys=True)}\n\n"
        f"Worker Codex command templates:\n{json.dumps(worker_commands, indent=2, sort_keys=True)}\n\n"
        "At the end of this pass, return a final JSON object and no other trailing text. "
        "The JSON contract is: status (continue, complete, or needs_followup), summary, "
        "progress_artifacts (array of paths), and optional next_prompt.\n\n"
        f"User prompt snapshot path: {state.get('prompt_snapshot_path', '')}\n\n"
        f"User prompt:\n{user_prompt}\n\n"
        f"Starting git status snapshot path: {state.get('cycle_start_git_status_path', '')}\n\n"
        f"Starting git status snapshot:\n{state.get('cycle_start_git_status', '') or '<clean>'}\n\n"
        f"Checklist summary:\n{json.dumps(checklist_summary(checklist), indent=2, sort_keys=True)}\n\n"
        f"Previous run artifacts:\n{json.dumps(previous_run_artifacts(state), indent=2, sort_keys=True)}\n\n"
        f"Current daemon state:\n{json.dumps(state, indent=2, sort_keys=True)}\n"
    )


def normalize_orchestrator_result(payload: dict[str, Any]) -> dict[str, Any]:
    status = str(payload.get("status") or "").strip().lower()
    if status not in {"continue", "complete", "needs_followup"}:
        return {}
    artifacts = payload.get("progress_artifacts")
    if not isinstance(artifacts, list):
        artifacts = []
    normalized = {
        "status": status,
        "summary": str(payload.get("summary") or ""),
        "progress_artifacts": [str(path) for path in artifacts if isinstance(path, (str, Path))],
    }
    if payload.get("next_prompt") is not None:
        normalized["next_prompt"] = str(payload.get("next_prompt") or "")
    return normalized


def read_orchestrator_result(last_message_path: Path) -> dict[str, Any]:
    text = last_message_path.read_text(encoding="utf-8", errors="replace") if last_message_path.exists() else ""
    return normalize_orchestrator_result(extract_json_object(text))


def worker_prompt(action: dict[str, Any], checklist: dict[str, Any]) -> str:
    return (
        "Implement the next blocker fix for the bot autonomy checklist. "
        "Use pixi for Python commands. Commit code/config changes to git in this worker branch. "
        "Keep changes scoped and update tests when behavior changes.\n\n"
        f"Selected action:\n{json.dumps(action, indent=2, sort_keys=True)}\n\n"
        f"Checklist:\n{json.dumps(checklist, indent=2, sort_keys=True)}\n"
    )


def reviewer_prompt(action: dict[str, Any]) -> str:
    return (
        "Review the worker changes for correctness, regressions, and missing tests. "
        "Return only JSON with fields accepted (boolean), reason, required_fixes (array).\n\n"
        f"Action:\n{json.dumps(action, indent=2, sort_keys=True)}\n"
    )


def run_shell(command: str, cwd: Path, timeout_sec: int | None = None) -> dict[str, Any]:
    completed = subprocess.run(command, shell=True, cwd=cwd, text=True, capture_output=True, timeout=timeout_sec, check=False)
    return {"command": command, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def run_command(command: list[str], cwd: Path, timeout_sec: int | None = None) -> dict[str, Any]:
    completed = subprocess.run(command, cwd=cwd, text=True, capture_output=True, timeout=timeout_sec, check=False)
    return {"command": command, "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr}


def git_status_porcelain(repo: Path) -> str:
    completed = subprocess.run(
        ["git", "status", "--short"],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        return f"<git status failed: {completed.stderr.strip()}>"
    return completed.stdout.strip()


def git_current_branch(repo: Path) -> str:
    result = run_command(["git", "branch", "--show-current"], repo)
    return result["stdout"].strip() if result["returncode"] == 0 else ""


def git_rev_parse(repo: Path, ref: str = "HEAD") -> str:
    result = run_command(["git", "rev-parse", "--verify", ref], repo)
    return result["stdout"].strip() if result["returncode"] == 0 else ""


def git_commit_count(repo: Path, revision_range: str) -> int:
    result = run_command(["git", "rev-list", "--count", revision_range], repo)
    if result["returncode"] != 0:
        return -1
    try:
        return int(result["stdout"].strip() or "0")
    except ValueError:
        return -1


def git_conflict_files(repo: Path) -> list[str]:
    result = run_command(["git", "diff", "--name-only", "--diff-filter=U"], repo)
    if result["returncode"] != 0:
        return []
    return [line for line in result["stdout"].splitlines() if line.strip()]


def git_unstaged_or_untracked(repo: Path) -> str:
    unstaged = run_command(["git", "diff", "--name-only"], repo)
    untracked = run_command(["git", "ls-files", "--others", "--exclude-standard"], repo)
    rows: list[str] = []
    if unstaged["returncode"] == 0:
        rows.extend(line for line in unstaged["stdout"].splitlines() if line.strip())
    if untracked["returncode"] == 0:
        rows.extend(line for line in untracked["stdout"].splitlines() if line.strip())
    return "\n".join(rows)


def git_merge_in_progress(repo: Path) -> bool:
    result = run_command(["git", "rev-parse", "--git-path", "MERGE_HEAD"], repo)
    if result["returncode"] != 0:
        return False
    return (repo / result["stdout"].strip()).exists()


def git_abort_merge(repo: Path) -> dict[str, Any]:
    if not git_merge_in_progress(repo):
        return {"command": ["git", "merge", "--abort"], "returncode": 0, "stdout": "", "stderr": ""}
    return run_command(["git", "merge", "--abort"], repo)


def merge_back_report_path(args: argparse.Namespace) -> Path:
    return Path(getattr(args, "instance_dir", AUTO_BOTS_DIR)) / "merge_back_failure.json"


def save_merge_back_state(state: dict[str, Any], state_path: Path, report: dict[str, Any], args: argparse.Namespace | None = None) -> None:
    state["merge_back"] = report
    save_state(state, state_path)
    if args is not None and report.get("status") == "failed":
        failure_path = merge_back_report_path(args)
        report["failure_report_path"] = str(failure_path)
        write_json(failure_path, report)
        state["merge_back"] = report
        save_state(state, state_path)


def run_merge_back_verification(repo: Path, config: dict[str, Any]) -> dict[str, Any]:
    timeout_sec = int(config["emergency_timeout_sec"])
    steps = [
        run_shell(str(config.get("test_command") or "pixi run pytest -q"), repo, None),
        run_shell(str(config.get("dvc_status_command") or "pixi run dvc status"), repo, timeout_sec),
    ]
    return {
        "schema": "orchestrator_merge_back_verification_v1",
        "ok": all(step["returncode"] == 0 for step in steps),
        "steps": steps,
    }


def merge_back_preflight_prompt(status: str, target_branch: str, instance_branch_name: str) -> str:
    return (
        "The main workspace is dirty before an orchestrator instance can be merged back.\n\n"
        f"Target branch: {target_branch}\n"
        f"Instance branch waiting to merge: {instance_branch_name}\n\n"
        "Inspect the current uncommitted main-workspace changes. Commit coherent useful work with a focused message. "
        "If the changes cannot be safely classified, do not discard them; leave a concise explanation in your final response. "
        "The required final state for success is `git status --short` clean in the main workspace.\n\n"
        f"Starting status:\n{status or '<clean>'}\n"
    )


def merge_back_conflict_prompt(conflict_files: list[str], target_branch: str, instance_branch_name: str) -> str:
    return (
        "Resolve the orchestrator merge-back conflicts in the main workspace.\n\n"
        f"Target branch: {target_branch}\n"
        f"Instance branch: {instance_branch_name}\n"
        f"Conflict files:\n{json.dumps(conflict_files, indent=2)}\n\n"
        "Resolve conflicts without discarding either side's useful work. Stage the resolved files, but do not commit the merge; "
        "the daemon will run verification and create the merge commit. If the conflicts cannot be resolved safely, stop and explain why."
    )


def run_merge_back_codex_pass(
    *,
    role: str,
    prompt: str,
    repo: Path,
    config: dict[str, Any],
    state: dict[str, Any],
    state_path: Path,
) -> dict[str, Any]:
    return run_codex_role(
        role=role,
        prompt=prompt,
        model=str(config["orchestrator_model"]),
        repo=repo,
        sandbox=str(config["sandbox"]),
        cycle_id=max(1, int(state.get("cycle_id") or 0) + 1),
        state=state,
        config=config,
        state_path=state_path,
    )


def finalize_named_instance_merge_back(args: argparse.Namespace, config: dict[str, Any]) -> dict[str, Any] | None:
    if not getattr(args, "instance", None):
        return None
    state = load_state(args.state)
    if state.get("status") not in {"stopped", "complete"}:
        return None
    existing = state.get("merge_back") if isinstance(state.get("merge_back"), dict) else {}
    if existing.get("status") in {"merged", "skipped", "failed"}:
        return existing

    instance_id = str(getattr(args, "instance_id", ""))
    instance_branch_name = instance_branch(instance_id)
    worktree = Path(getattr(args, "worktree_path", "") or state.get("worktree_path", "")).resolve()
    report: dict[str, Any] = {
        "schema": "orchestrator_merge_back_v1",
        "status": "running",
        "target_repo": str(REPO_ROOT),
        "target_branch": "",
        "instance_id": instance_id,
        "instance_branch": instance_branch_name,
        "instance_worktree": str(worktree),
        "merge_commit": "",
        "preflight_commit": "",
        "verification": {},
        "conflict_files": [],
        "failure_reason": "",
        "started_at_unix": now_unix(),
    }
    save_merge_back_state(state, args.state, report)

    try:
        instance_status = git_status_porcelain(worktree)
        if instance_status:
            report.update({"status": "failed", "failure_reason": "instance_worktree_dirty", "instance_git_status": instance_status})
            save_merge_back_state(state, args.state, report, args)
            return report

        target_branch = git_current_branch(REPO_ROOT)
        report["target_branch"] = target_branch
        if not target_branch:
            report.update({"status": "failed", "failure_reason": "target_branch_detached_or_unknown"})
            save_merge_back_state(state, args.state, report, args)
            return report
        if not git_branch_exists(REPO_ROOT, instance_branch_name):
            report.update({"status": "failed", "failure_reason": "instance_branch_missing"})
            save_merge_back_state(state, args.state, report, args)
            return report

        unique_commits = git_commit_count(REPO_ROOT, f"{target_branch}..{instance_branch_name}")
        report["unique_commit_count"] = unique_commits
        if unique_commits < 0:
            report.update({"status": "failed", "failure_reason": "unique_commit_count_failed"})
            save_merge_back_state(state, args.state, report, args)
            return report
        if unique_commits == 0:
            report.update({"status": "skipped", "failure_reason": "", "reason": "instance_branch_already_reachable"})
            save_merge_back_state(state, args.state, report)
            return report

        main_status = git_status_porcelain(REPO_ROOT)
        if main_status:
            before_head = git_rev_parse(REPO_ROOT)
            preflight = run_merge_back_codex_pass(
                role="merge_back_preflight",
                prompt=merge_back_preflight_prompt(main_status, target_branch, instance_branch_name),
                repo=REPO_ROOT,
                config=config,
                state=state,
                state_path=args.state,
            )
            report["preflight"] = {
                "returncode": preflight.get("returncode"),
                "jsonl_path": str(preflight.get("jsonl_path", "")),
                "stderr_path": str(preflight.get("stderr_path", "")),
                "last_message_path": str(preflight.get("last_message_path", "")),
            }
            after_head = git_rev_parse(REPO_ROOT)
            if after_head and after_head != before_head:
                report["preflight_commit"] = after_head
            main_status = git_status_porcelain(REPO_ROOT)
            if preflight.get("returncode") != 0 or main_status:
                report.update({"status": "failed", "failure_reason": "main_workspace_dirty_after_preflight", "main_git_status": main_status})
                save_merge_back_state(state, args.state, report, args)
                return report

        merge = run_command(["git", "merge", "--no-ff", "--no-commit", instance_branch_name], REPO_ROOT)
        report["merge_command"] = merge
        if merge["returncode"] != 0:
            conflicts = git_conflict_files(REPO_ROOT)
            report["conflict_files"] = conflicts
            if not conflicts:
                git_abort_merge(REPO_ROOT)
                report.update({"status": "failed", "failure_reason": "merge_failed_without_conflicts"})
                save_merge_back_state(state, args.state, report, args)
                return report
            resolver = run_merge_back_codex_pass(
                role="merge_back_conflict_resolver",
                prompt=merge_back_conflict_prompt(conflicts, target_branch, instance_branch_name),
                repo=REPO_ROOT,
                config=config,
                state=state,
                state_path=args.state,
            )
            report["resolver"] = {
                "returncode": resolver.get("returncode"),
                "jsonl_path": str(resolver.get("jsonl_path", "")),
                "stderr_path": str(resolver.get("stderr_path", "")),
                "last_message_path": str(resolver.get("last_message_path", "")),
            }
            unresolved = git_conflict_files(REPO_ROOT)
            if resolver.get("returncode") != 0 or unresolved:
                abort = git_abort_merge(REPO_ROOT)
                report.update(
                    {
                        "status": "failed",
                        "failure_reason": "conflict_resolver_failed",
                        "unresolved_conflict_files": unresolved,
                        "abort": abort,
                    }
                )
                save_merge_back_state(state, args.state, report, args)
                return report

            unstaged_or_untracked = git_unstaged_or_untracked(REPO_ROOT)
            if unstaged_or_untracked:
                abort = git_abort_merge(REPO_ROOT)
                report.update(
                    {
                        "status": "failed",
                        "failure_reason": "conflict_resolver_left_unstaged_or_untracked_changes",
                        "unstaged_or_untracked": unstaged_or_untracked,
                        "abort": abort,
                    }
                )
                save_merge_back_state(state, args.state, report, args)
                return report

        verification = run_merge_back_verification(REPO_ROOT, config)
        report["verification"] = verification
        if not verification["ok"]:
            abort = git_abort_merge(REPO_ROOT)
            report.update({"status": "failed", "failure_reason": "verification_failed", "abort": abort})
            save_merge_back_state(state, args.state, report, args)
            return report

        if git_merge_in_progress(REPO_ROOT):
            unstaged_or_untracked = git_unstaged_or_untracked(REPO_ROOT)
            if unstaged_or_untracked:
                abort = git_abort_merge(REPO_ROOT)
                report.update(
                    {
                        "status": "failed",
                        "failure_reason": "verification_left_unstaged_or_untracked_changes",
                        "unstaged_or_untracked": unstaged_or_untracked,
                        "abort": abort,
                    }
                )
                save_merge_back_state(state, args.state, report, args)
                return report
            commit = run_command(["git", "commit", "-m", f"Merge orchestrator instance {instance_id}"], REPO_ROOT)
            report["commit_command"] = commit
            if commit["returncode"] != 0:
                abort = git_abort_merge(REPO_ROOT)
                report.update({"status": "failed", "failure_reason": "merge_commit_failed", "abort": abort})
                save_merge_back_state(state, args.state, report, args)
                return report

        final_status = git_status_porcelain(REPO_ROOT)
        if final_status:
            report.update({"status": "failed", "failure_reason": "main_workspace_dirty_after_merge", "main_git_status": final_status})
            save_merge_back_state(state, args.state, report, args)
            return report

        report.update({"status": "merged", "merge_commit": git_rev_parse(REPO_ROOT), "completed_at_unix": now_unix()})
        save_merge_back_state(state, args.state, report)
        return report
    except Exception as exc:  # pragma: no cover - defensive state reporting for daemon cleanup
        if git_merge_in_progress(REPO_ROOT):
            report["abort"] = git_abort_merge(REPO_ROOT)
        report.update({"status": "failed", "failure_reason": "merge_back_exception", "exception": repr(exc)})
        save_merge_back_state(state, args.state, report, args)
        return report


def next_lane_id(state: dict[str, Any], action: dict[str, Any]) -> str:
    explicit = str(action.get("lane_id") or "").strip()
    if explicit:
        return explicit.replace(" ", "_")
    return f"autonomy_cycle_{int(state.get('cycle_id') or 0):06d}"


def create_worker_worktree(repo: Path, lane_id: str) -> Path:
    root = repo / "generated" / "bot_autonomy_worktrees"
    root.mkdir(parents=True, exist_ok=True)
    worktree = root / lane_id
    branch = f"bot-autonomy/{lane_id}"
    if worktree.exists():
        return worktree
    subprocess.run(["git", "worktree", "add", "-B", branch, str(worktree), "HEAD"], cwd=repo, check=True)
    return worktree


def reviewer_accepted(last_message_path: Path) -> bool:
    payload = extract_json_object(last_message_path.read_text(encoding="utf-8", errors="replace") if last_message_path.exists() else "")
    return bool(payload.get("accepted") is True or str(payload.get("decision") or "").lower() in {"accept", "accepted"})


def handle_rate_limit(state: dict[str, Any], rate_limit: dict[str, Any], state_path: Path = DEFAULT_STATE_PATH) -> None:
    state.update(
        {
            "status": "paused_rate_limit",
            "phase": "paused_rate_limit",
            "active_agent_role": rate_limit.get("agent_role", ""),
            "thread_id": rate_limit.get("thread_id", ""),
            "rate_limit": rate_limit,
        }
    )
    save_state(state, state_path)


def sleep_until_resume(state: dict[str, Any], stop_path: Path, state_path: Path = DEFAULT_STATE_PATH) -> bool:
    rate_limit = state.get("rate_limit") if isinstance(state.get("rate_limit"), dict) else {}
    resume_at = int(rate_limit.get("resume_at_unix") or 0)
    while resume_at > now_unix():
        if stop_path.exists():
            state.update({"status": "stopped", "phase": "stop_requested", "rate_limit": {}})
            save_state(state, state_path)
            return False
        time.sleep(min(30, max(1, resume_at - now_unix())))
    return True


def run_validation_cycle(repo: Path, config: dict[str, Any]) -> dict[str, Any]:
    steps = [
        run_shell(str(config["validation_plan_command"]), repo, int(config["emergency_timeout_sec"])),
        run_shell(str(config["validation_command"]), repo, None),
        run_shell(str(config["scenario_report_command"]), repo, int(config["emergency_timeout_sec"])),
        run_shell(str(config["dvc_status_command"]), repo, int(config["emergency_timeout_sec"])),
        run_shell(str(config["dvc_push_command"]), repo, None),
    ]
    return {
        "schema": "bot_autonomy_validation_cycle_v1",
        "steps": steps,
        "accepted": all(step["returncode"] == 0 for step in steps),
    }


def run_one_cycle(state: dict[str, Any], config: dict[str, Any], state_path: Path = DEFAULT_STATE_PATH) -> dict[str, Any]:
    repo = Path(config["repo"]).resolve()
    checklist = load_checklist(resolve_path(config.get("checklist_path")) or DEFAULT_CHECKLIST_PATH)

    was_paused_rate_limit = state.get("status") == "paused_rate_limit"
    existing_rate_limit = state.get("rate_limit") if isinstance(state.get("rate_limit"), dict) else {}
    previous_orchestrator_result = state.get("latest_orchestrator_result") if isinstance(state.get("latest_orchestrator_result"), dict) else {}
    cycle_id = int(state.get("cycle_id") or 0) + 1
    run_dir = run_dir_for_cycle(config, cycle_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    start_git_status = git_status_porcelain(repo)
    start_git_status_path = run_dir / "cycle_start_git_status.txt"
    start_git_status_path.write_text(start_git_status + ("\n" if start_git_status else ""), encoding="utf-8")
    state.update(
        {
            "cycle_id": cycle_id,
            "status": "running",
            "phase": "orchestrator",
            "goal_complete": False,
            "cycle_start_git_status": start_git_status,
            "cycle_start_git_status_path": str(start_git_status_path),
            "latest_orchestrator_result": {},
            "previous_orchestrator_result": previous_orchestrator_result,
        }
    )
    save_state(state, state_path)

    if was_paused_rate_limit:
        state.update(
            {
                "rate_limit": {},
                "thread_id": "",
                "rate_limit_recovered_at_unix": now_unix(),
                "previous_rate_limit": {
                    key: existing_rate_limit.get(key)
                    for key in ("agent_role", "thread_id", "jsonl_path", "stderr_path", "last_message_path", "resume_at_unix", "signature")
                    if existing_rate_limit.get(key) is not None
                },
            }
        )
        save_state(state, state_path)

    try:
        user_prompt, _snapshot_path = prepare_prompt_snapshot(config=config, state=state, cycle_id=cycle_id)
    except OSError as exc:
        result = {"status": "failure", "error": "prompt_file_unreadable", "detail": str(exc)}
        state.update(
            {
                "status": "running",
                "phase": "prompt_file_unreadable",
                "latest_orchestrator_result": result,
                "consecutive_orchestrator_failures": int(state.get("consecutive_orchestrator_failures") or 0) + 1,
            }
        )
        save_state(state, state_path)
        return {"done": False, "error": "prompt_file_unreadable"}
    save_state(state, state_path)

    orchestrator = run_codex_role(
        role="orchestrator",
        prompt=orchestrator_prompt(checklist, state, user_prompt, config),
        model=str(config["orchestrator_model"]),
        repo=repo,
        sandbox=str(config["sandbox"]),
        cycle_id=cycle_id,
        state=state,
        config=config,
        state_path=state_path,
    )
    if orchestrator["rate_limit"]:
        handle_rate_limit(state, orchestrator["rate_limit"], state_path)
        return {"done": False, "rate_limit": True}
    if orchestrator["returncode"] != 0:
        result = {
            "status": "failure",
            "error": "orchestrator_failed",
            "returncode": orchestrator["returncode"],
            "thread_id": orchestrator.get("thread_id", ""),
            "jsonl_path": str(orchestrator["jsonl_path"]),
            "stderr_path": str(orchestrator["stderr_path"]),
            "last_message_path": str(orchestrator["last_message_path"]),
        }
        state.update(
            {
                "status": "running",
                "phase": "orchestrator_failed",
                "latest_orchestrator_result": result,
                "consecutive_orchestrator_failures": int(state.get("consecutive_orchestrator_failures") or 0) + 1,
                "thread_id": orchestrator.get("thread_id", ""),
            }
        )
        save_state(state, state_path)
        return {"done": False, "error": "orchestrator_failed", "returncode": orchestrator["returncode"]}

    result = read_orchestrator_result(orchestrator["last_message_path"])
    if not result:
        result = {
            "status": "failure",
            "error": "orchestrator_result_contract_invalid",
            "returncode": orchestrator["returncode"],
            "thread_id": orchestrator.get("thread_id", ""),
            "jsonl_path": str(orchestrator["jsonl_path"]),
            "stderr_path": str(orchestrator["stderr_path"]),
            "last_message_path": str(orchestrator["last_message_path"]),
        }
        state.update(
            {
                "status": "running",
                "phase": "orchestrator_result_contract_invalid",
                "latest_orchestrator_result": result,
                "consecutive_orchestrator_failures": int(state.get("consecutive_orchestrator_failures") or 0) + 1,
                "thread_id": orchestrator.get("thread_id", ""),
            }
        )
        save_state(state, state_path)
        return {"done": False, "error": "orchestrator_result_contract_invalid"}

    state.update(
        {
            "status": "complete" if result["status"] == "complete" else "running",
            "phase": "complete" if result["status"] == "complete" else "orchestrator_pass_complete",
            "goal_complete": result["status"] == "complete",
            "latest_orchestrator_result": result,
            "last_completed_cycle_id": cycle_id,
            "consecutive_orchestrator_failures": 0,
            "rate_limit": {},
            "thread_id": orchestrator.get("thread_id", ""),
        }
    )
    save_state(state, state_path)
    return {"done": result["status"] == "complete", "status": result["status"]}


def acquire_lock(lock_path: Path, pid_path: Path) -> None:
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    if lock_path.exists():
        raise SystemExit(f"daemon lock exists: {lock_path}")
    lock_path.write_text(str(os.getpid()), encoding="utf-8")
    pid_path.write_text(str(os.getpid()), encoding="utf-8")


def release_lock(lock_path: Path, pid_path: Path) -> None:
    for path in (lock_path, pid_path):
        try:
            path.unlink()
        except FileNotFoundError:
            pass


def run_daemon(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    prompt_file = effective_prompt_file(config, args)
    config["prompt_file"] = str(prompt_file or "")
    config["checklist_path"] = str(args.checklist)
    config["runs_dir"] = str(getattr(args, "runs_dir", runs_dir(config)))
    if getattr(args, "instance", None):
        repo = resolve_path(config.get("repo")) or REPO_ROOT
        worktree = ensure_instance_worktree(repo, str(args.instance_id))
        args.worktree_path = worktree
        config["repo"] = str(worktree)
    state = load_state(args.state)
    update_state_instance_metadata(state, args, config)
    save_state(state, args.state)
    acquire_lock(args.lock, args.pid)
    clean_exit = False
    try:
        while True:
            state = load_state(args.state)
            update_state_instance_metadata(state, args, config)
            if state.get("status") == "paused_rate_limit":
                if not sleep_until_resume(state, args.stop_file, args.state):
                    clean_exit = True
                    return 0
            if args.stop_file.exists():
                state.update({"status": "stopped", "phase": "stop_requested", "rate_limit": {}})
                save_state(state, args.state)
                clean_exit = True
                return 0
            result = run_one_cycle(state, config, args.state)
            if result.get("done"):
                clean_exit = True
                return 0
            if result.get("rate_limit"):
                continue
            error = str(result.get("error") or "")
            if error:
                state = load_state(args.state)
                state.update({"status": "running", "phase": error})
                save_state(state, args.state)
            if args.once or (args.max_cycles and int(state.get("cycle_id") or 0) >= args.max_cycles):
                clean_exit = True
                return 0
            time.sleep(max(1, int(config["heartbeat_sec"])))
    finally:
        try:
            if clean_exit and getattr(args, "instance", None):
                finalize_named_instance_merge_back(args, config)
        finally:
            release_lock(args.lock, args.pid)


def start_daemon(args: argparse.Namespace) -> int:
    if args.lock.exists():
        raise SystemExit(f"daemon already appears to be running: {args.lock}")
    args.log.parent.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "-m",
        "tools.bot_ml.orchestrator_daemon",
    ]
    if getattr(args, "instance", None):
        command.extend(["--instance", str(args.instance_id)])
    command.extend(
        [
            "--config",
            str(args.config),
            "--state",
            str(args.state),
            "--checklist",
            str(args.checklist),
            "--lock",
            str(args.lock),
            "--pid",
            str(args.pid),
            "--stop-file",
            str(args.stop_file),
            "--log",
            str(args.log),
        ]
    )
    prompt_file = cli_prompt_file(args)
    if prompt_file is not None:
        command.extend(["--prompt-file", str(prompt_file)])
    command.append("run")
    with args.log.open("ab") as log:
        process = subprocess.Popen(
            command,
            cwd=REPO_ROOT,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    args.pid.write_text(str(process.pid), encoding="utf-8")
    print(json.dumps({"started": True, "pid": process.pid, "log": str(args.log)}, indent=2, sort_keys=True))
    return 0


def load_activity_for_artifacts(
    *,
    role: str,
    jsonl_path: Path | None,
    stderr_path: Path | None = None,
    last_message_path: Path | None = None,
    activity_path: Path | None = None,
    no_progress_window_sec: int | None = None,
    raw_tail: int = 0,
) -> dict[str, Any]:
    activity: dict[str, Any] = {}
    if activity_path and activity_path.exists():
        payload = read_json(activity_path, {})
        if isinstance(payload, dict):
            activity = payload
    if not activity and jsonl_path:
        activity = activity_summary_from_events(
            read_jsonl_events(jsonl_path),
            role=role,
            jsonl_path=jsonl_path,
            stderr_path=stderr_path,
            last_message_path=last_message_path,
            generated_at_unix=now_unix(),
            no_progress_window_sec=no_progress_window_sec,
        )
    if not activity:
        activity = activity_summary_from_events([], role=role, generated_at_unix=now_unix(), no_progress_window_sec=no_progress_window_sec)
    if raw_tail:
        if jsonl_path:
            activity["raw_jsonl_tail"] = file_tail_lines(jsonl_path, raw_tail)
        if stderr_path:
            activity["stderr_tail"] = file_tail_lines(stderr_path, raw_tail)
    return activity


def resolve_run_relative_path(value: Any, run_dir: Path) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text).expanduser()
    return path if path.is_absolute() else (run_dir / path).resolve()


def agent_registry_entries(run_dir: Path) -> list[dict[str, Any]]:
    registry_path = run_dir / "agent_registry.json"
    payload = read_json(registry_path, {}) if registry_path.exists() else {}
    if not isinstance(payload, dict):
        return []
    rows = payload.get("agents")
    if isinstance(rows, dict):
        candidates = list(rows.values())
    elif isinstance(rows, list):
        candidates = rows
    else:
        candidates = payload.get("entries") if isinstance(payload.get("entries"), list) else []
    return [row for row in candidates if isinstance(row, dict)]


def latest_activity_summary(args: argparse.Namespace, state: dict[str, Any], *, raw_tail: int = 0, agent_filter: str = "") -> dict[str, Any]:
    config = load_config(args.config)
    no_progress_window_sec = int(config.get("no_progress_window_sec") or DEFAULT_CONFIG["no_progress_window_sec"])
    jsonl_path = resolve_path(state.get("latest_jsonl_path"))
    stderr_path = resolve_path(state.get("latest_stderr_path"))
    last_message_path = resolve_path(state.get("latest_last_message_path"))
    activity_path = resolve_path(state.get("latest_activity_path"))
    if activity_path is None and jsonl_path is not None:
        activity_path = jsonl_path.parent / "activity.json"
    primary_role = str(state.get("active_agent_role") or "orchestrator")
    primary = load_activity_for_artifacts(
        role=primary_role,
        jsonl_path=jsonl_path,
        stderr_path=stderr_path,
        last_message_path=last_message_path,
        activity_path=activity_path,
        no_progress_window_sec=no_progress_window_sec,
        raw_tail=raw_tail,
    )
    primary["id"] = primary.get("id") or primary_role

    agents: list[dict[str, Any]] = []
    run_dir = jsonl_path.parent if jsonl_path else None
    if run_dir and run_dir.exists():
        for entry in agent_registry_entries(run_dir):
            role = str(entry.get("role") or entry.get("id") or "worker")
            agent_id = str(entry.get("id") or role)
            if agent_filter and agent_filter not in {role, agent_id}:
                continue
            agent_jsonl = resolve_run_relative_path(entry.get("jsonl_path"), run_dir)
            agent_stderr = resolve_run_relative_path(entry.get("stderr_path"), run_dir)
            agent_last_message = resolve_run_relative_path(entry.get("last_message_path"), run_dir)
            agent_activity = resolve_run_relative_path(entry.get("activity_path"), run_dir)
            snapshot = load_activity_for_artifacts(
                role=role,
                jsonl_path=agent_jsonl,
                stderr_path=agent_stderr,
                last_message_path=agent_last_message,
                activity_path=agent_activity,
                no_progress_window_sec=no_progress_window_sec,
                raw_tail=raw_tail,
            )
            snapshot.update(
                {
                    "id": agent_id,
                    "registry_status": entry.get("status", ""),
                    "complexity": entry.get("complexity", ""),
                    "model": entry.get("model", ""),
                    "reasoning_effort": entry.get("reasoning_effort", ""),
                }
            )
            agents.append(snapshot)

    if agent_filter and agent_filter not in {str(primary.get("role") or ""), str(primary.get("id") or "")}:
        selected_primary: dict[str, Any] = {}
    else:
        selected_primary = primary
    base = compact_activity(selected_primary) if selected_primary else {
        "latest_message": "",
        "active_item": {},
        "recent_commands": [],
        "last_completed_command": {},
        "last_failed_command": {},
        "last_event_age_sec": None,
        "stuck_suspected": False,
    }
    base.update(
        {
            "schema": "orchestrator_daemon_activity_summary_v1",
            "primary": selected_primary,
            "agents": agents,
        }
    )
    return base


def render_activity_line(activity: dict[str, Any]) -> list[str]:
    role = str(activity.get("role") or activity.get("id") or "agent")
    agent_id = str(activity.get("id") or "")
    label = f"{role}:{agent_id}" if agent_id and agent_id != role else role
    status = str(activity.get("registry_status") or "")
    active = activity.get("active_item") if isinstance(activity.get("active_item"), dict) else {}
    lines = [f"[{label}] events={activity.get('event_count', 0)} age={activity.get('last_event_age_sec')}s stuck={bool(activity.get('stuck_suspected'))}"]
    if status:
        lines[0] += f" status={status}"
    if activity.get("latest_message"):
        lines.append(f"  latest: {truncate_text(activity.get('latest_message'), 220)}")
    if active:
        if active.get("type") == "command_execution":
            lines.append(f"  active command ({active.get('duration_sec', 0)}s): {truncate_text(active.get('command'), 220)}")
        else:
            lines.append(f"  active item: {active.get('type')} {active.get('id', '')}")
    completed = activity.get("last_completed_command") if isinstance(activity.get("last_completed_command"), dict) else {}
    failed = activity.get("last_failed_command") if isinstance(activity.get("last_failed_command"), dict) else {}
    if completed:
        lines.append(f"  last command: rc={completed.get('exit_code')} {truncate_text(completed.get('command'), 220)}")
    if failed:
        lines.append(f"  last failure: rc={failed.get('exit_code')} {truncate_text(failed.get('command'), 220)}")
    if activity.get("raw_jsonl_tail"):
        lines.append("  raw jsonl tail:")
        lines.extend(f"    {line}" for line in str(activity["raw_jsonl_tail"]).splitlines())
    if activity.get("stderr_tail"):
        lines.append("  stderr tail:")
        lines.extend(f"    {line}" for line in str(activity["stderr_tail"]).splitlines())
    return lines


def render_watch_payload(payload: dict[str, Any]) -> str:
    state = payload.get("state") if isinstance(payload.get("state"), dict) else {}
    lines = [
        f"daemon status={state.get('status', '')} phase={state.get('phase', '')} cycle={state.get('cycle_id', 0)}",
        f"artifacts: {state.get('latest_jsonl_path', '')}",
    ]
    primary = payload.get("primary") if isinstance(payload.get("primary"), dict) else {}
    if primary:
        lines.extend(render_activity_line(primary))
    agents = payload.get("agents") if isinstance(payload.get("agents"), list) else []
    for agent in agents:
        if isinstance(agent, dict):
            lines.extend(render_activity_line(agent))
    return "\n".join(lines)


def watch_payload(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state(args.state)
    update_state_instance_metadata(state, args, {"runs_dir": str(getattr(args, "runs_dir", DEFAULT_RUNS_DIR))})
    activity = latest_activity_summary(args, state, raw_tail=max(0, int(getattr(args, "raw_tail", 0) or 0)), agent_filter=str(getattr(args, "agent", "") or ""))
    return {
        "schema": "orchestrator_daemon_watch_v1",
        "generated_at_unix": now_unix(),
        "instance_id": str(getattr(args, "instance_id", LEGACY_INSTANCE_ID)),
        "state": state,
        **activity,
    }


def watch_daemon(args: argparse.Namespace) -> int:
    interval = max(1.0, float(getattr(args, "interval", 2.0) or 2.0))
    while True:
        payload = watch_payload(args)
        print(render_watch_payload(payload), flush=True)
        if getattr(args, "once", False):
            return 0
        if not args.lock.exists() and not args.pid.exists():
            return 0
        time.sleep(interval)


def status_payload(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state(args.state)
    update_state_instance_metadata(state, args, {"runs_dir": str(getattr(args, "runs_dir", DEFAULT_RUNS_DIR))})
    checklist = load_checklist(args.checklist)
    rate_limit = state.get("rate_limit") if isinstance(state.get("rate_limit"), dict) else {}
    paused_rate_limit = state.get("status") == "paused_rate_limit"
    merge_back = state.get("merge_back") if isinstance(state.get("merge_back"), dict) else {}
    payload = {
        "schema": "orchestrator_daemon_status_v1",
        "instance_id": str(getattr(args, "instance_id", LEGACY_INSTANCE_ID)),
        "state": state,
        "checklist": checklist_summary(checklist),
        "lock_exists": args.lock.exists(),
        "pid": args.pid.read_text(encoding="utf-8").strip() if args.pid.exists() else "",
        "rate_limit_sleep_remaining_sec": max(0, int(rate_limit.get("resume_at_unix") or 0) - now_unix()) if paused_rate_limit else 0,
        "merge_back": merge_back,
        "stop_requested": args.stop_file.exists(),
    }
    diagnostics = daemon_diagnostics(args, state, include_tails=False)
    payload["diagnostics"] = {
        "healthy": diagnostics["healthy"],
        "state_age_sec": diagnostics["state_age_sec"],
        "active_codex_process_count": len(diagnostics["active_codex_processes"]),
        "output_bytes": diagnostics["output_bytes"],
        "suspicions": diagnostics["suspicions"],
    }
    payload["activity"] = latest_activity_summary(args, state)
    return payload


def debug_payload(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state(args.state)
    update_state_instance_metadata(state, args, {"runs_dir": str(getattr(args, "runs_dir", DEFAULT_RUNS_DIR))})
    checklist = load_checklist(args.checklist)
    return {
        "schema": "orchestrator_daemon_debug_v1",
        "instance_id": str(getattr(args, "instance_id", LEGACY_INSTANCE_ID)),
        "state": state,
        "checklist": checklist_summary(checklist),
        "lock_exists": args.lock.exists(),
        "pid": args.pid.read_text(encoding="utf-8").strip() if args.pid.exists() else "",
        "stop_requested": args.stop_file.exists(),
        "diagnostics": daemon_diagnostics(args, state, include_tails=True),
        "activity": latest_activity_summary(args, state, raw_tail=20),
    }


def instance_status_row(instance_id: str, root: Path, worktree_path: Path | str = "") -> dict[str, Any]:
    state_path = root / "daemon_state.json"
    lock_path = root / "daemon.lock"
    pid_path = root / "daemon.pid"
    stop_path = root / "daemon.stop"
    log_path = root / "daemon.log"
    checklist_path = root / "master_checklist.json"
    state = load_state(state_path)
    return {
        "instance_id": instance_id,
        "instance_dir": str(root),
        "status": state.get("status", "idle"),
        "pid": pid_path.read_text(encoding="utf-8").strip() if pid_path.exists() else "",
        "lock_exists": lock_path.exists(),
        "stop_requested": stop_path.exists(),
        "prompt_file": state.get("prompt_file", ""),
        "cycle_id": state.get("cycle_id", 0),
        "latest_orchestrator_result": state.get("latest_orchestrator_result", {}),
        "merge_back": state.get("merge_back", {}) if isinstance(state.get("merge_back"), dict) else {},
        "log_path": str(log_path),
        "checklist_path": str(checklist_path),
        "worktree_path": str(worktree_path or state.get("worktree_path", "")),
    }


def instances_payload(_args: argparse.Namespace) -> dict[str, Any]:
    rows = [instance_status_row(LEGACY_INSTANCE_ID, AUTO_BOTS_DIR, "")]
    if ORCHESTRATOR_INSTANCES_DIR.exists():
        for root in sorted(path for path in ORCHESTRATOR_INSTANCES_DIR.iterdir() if path.is_dir()):
            rows.append(instance_status_row(root.name, root, instance_worktree_path(root.name)))
    return {"schema": "orchestrator_daemon_instances_v1", "instances": rows}


def stop_daemon(args: argparse.Namespace) -> int:
    args.stop_file.parent.mkdir(parents=True, exist_ok=True)
    args.stop_file.write_text(str(now_unix()), encoding="utf-8")
    print(json.dumps({"stop_requested": True, "stop_file": str(args.stop_file)}, indent=2, sort_keys=True))
    return 0


def doctor(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    prompt_file = effective_prompt_file(config, args)
    checks: list[dict[str, Any]] = []
    for name, command in [
        ("codex", "codex --version"),
        ("dvc", "pixi run dvc --version"),
    ]:
        result = run_shell(command, REPO_ROOT, int(config["emergency_timeout_sec"]))
        checks.append({"name": name, "ok": result["returncode"] == 0, "returncode": result["returncode"], "stderr_tail": result["stderr"][-1000:]})
    worldserver = REPO_ROOT / "build" / "src" / "server" / "worldserver" / "worldserver"
    checks.append({"name": "worldserver_binary", "ok": worldserver.exists(), "path": str(worldserver)})
    if prompt_file is None:
        checks.append({"name": "prompt_file", "ok": True, "configured": False, "path": ""})
    else:
        readable = prompt_file.exists() and prompt_file.is_file() and os.access(prompt_file, os.R_OK)
        checks.append({"name": "prompt_file", "ok": readable, "configured": True, "path": str(prompt_file)})
    checks.append({"name": "daemon_lock", "ok": not args.lock.exists(), "path": str(args.lock), "locked": args.lock.exists()})
    payload = {
        "schema": "orchestrator_daemon_doctor_v1",
        "instance_id": str(getattr(args, "instance_id", LEGACY_INSTANCE_ID)),
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
        "config": config,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the long-lived local Codex orchestrator daemon.")
    parser.add_argument("--instance", default="", help="Run against a named isolated orchestrator instance.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--checklist", type=Path, default=DEFAULT_CHECKLIST_PATH)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK_PATH)
    parser.add_argument("--pid", type=Path, default=DEFAULT_PID_PATH)
    parser.add_argument("--stop-file", type=Path, default=DEFAULT_STOP_PATH)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG_PATH)
    parser.add_argument("--prompt-file", type=Path, default=None)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Run the daemon in the foreground.")
    run_parser.add_argument("--prompt-file", type=Path, default=None, dest="command_prompt_file")
    run_parser.add_argument("--once", action="store_true", help="Run at most one daemon cycle.")
    run_parser.add_argument("--max-cycles", type=int, default=0)
    start_parser = subparsers.add_parser("start", help="Start the daemon in the background.")
    start_parser.add_argument("--prompt-file", type=Path, default=None, dest="command_prompt_file")
    subparsers.add_parser("status", help="Print daemon status as JSON.")
    subparsers.add_parser("debug", help="Print daemon process, artifact, and stuck diagnostics as JSON.")
    watch_parser = subparsers.add_parser("watch", help="Print a summarized live activity view.")
    watch_parser.add_argument("--once", action="store_true", help="Print one activity snapshot and exit.")
    watch_parser.add_argument("--raw-tail", type=int, default=0, help="Include the last N raw JSONL/stderr lines.")
    watch_parser.add_argument("--agent", default="", help="Filter to an agent role or registry id.")
    watch_parser.add_argument("--interval", type=float, default=2.0, help="Refresh interval in seconds.")
    subparsers.add_parser("stop", help="Request graceful stop after the current atomic step.")
    subparsers.add_parser("instances", help="List legacy and named daemon instances.")
    doctor_parser = subparsers.add_parser("doctor", help="Validate local prerequisites.")
    doctor_parser.add_argument("--prompt-file", type=Path, default=None, dest="command_prompt_file")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    apply_instance_paths(args)
    if args.command == "run":
        return run_daemon(args)
    if args.command == "start":
        return start_daemon(args)
    if args.command == "status":
        print(json.dumps(status_payload(args), indent=2, sort_keys=True))
        return 0
    if args.command == "debug":
        print(json.dumps(debug_payload(args), indent=2, sort_keys=True))
        return 0
    if args.command == "watch":
        return watch_daemon(args)
    if args.command == "stop":
        return stop_daemon(args)
    if args.command == "instances":
        print(json.dumps(instances_payload(args), indent=2, sort_keys=True))
        return 0
    if args.command == "doctor":
        return doctor(args)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
