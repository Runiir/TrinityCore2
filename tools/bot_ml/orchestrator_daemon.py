from __future__ import annotations

import argparse
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

RATE_LIMIT_RE = re.compile(
    r"(rate[\s_-]*limit|too many requests|quota|429|retry-after|retry after|reset in|rate_limit_exceeded)",
    re.IGNORECASE,
)
THREAD_KEYS = ("thread_id", "session_id", "conversation_id", "id")
LEGACY_INSTANCE_ID = "legacy"


DEFAULT_CONFIG: dict[str, Any] = {
    "orchestrator_model": "gpt-5.5",
    "worker_model": "gpt-5.5",
    "reviewer_model": "gpt-5.5",
    "orchestrator_reasoning_effort": "high",
    "worker_reasoning_effort": "medium",
    "reviewer_reasoning_effort": "high",
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
        return dict(DEFAULT_CONFIG)
    payload = read_json(path, {})
    if not isinstance(payload, dict):
        payload = {}
    config = dict(DEFAULT_CONFIG)
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
        "latest_orchestrator_result": {},
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
        if str(event.get("type") or "") in {"error", "turn.failed"} or RATE_LIMIT_RE.search(event_text(event))
    ]
    combined = "\n".join([stdout_text, stderr_text] + [event_text(event) for event in event_matches])
    if not event_matches and not RATE_LIMIT_RE.search(combined):
        return None
    if returncode == 0 and not RATE_LIMIT_RE.search(combined):
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
            "-C",
            str(repo),
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
        }
    )
    save_state(state, state_path)
    completed = subprocess.run(
        command,
        input=stdin_text,
        text=True,
        capture_output=True,
        cwd=repo,
        check=False,
    )
    jsonl_path.write_text(completed.stdout, encoding="utf-8")
    stderr_path.write_text(completed.stderr, encoding="utf-8")
    events = read_jsonl_events(jsonl_path)
    discovered_thread_id = extract_thread_id(events) or thread_id
    rate_limit = detect_rate_limit(
        events=events,
        stdout_text=completed.stdout,
        stderr_text=completed.stderr,
        returncode=completed.returncode,
        default_sleep_sec=int(config["rate_limit_default_sleep_sec"]),
        max_sleep_sec=int(config["rate_limit_max_sleep_sec"]),
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
        "returncode": completed.returncode,
        "jsonl_path": jsonl_path,
        "stderr_path": stderr_path,
        "last_message_path": last_message_path,
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
    return {
        "latest_jsonl_path": state.get("latest_jsonl_path", ""),
        "latest_stderr_path": state.get("latest_stderr_path", ""),
        "latest_last_message_path": state.get("latest_last_message_path", ""),
        "latest_orchestrator_result": state.get("latest_orchestrator_result", {}),
        "latest_report": state.get("latest_report", ""),
        "last_completed_cycle_id": state.get("last_completed_cycle_id", 0),
        "consecutive_orchestrator_failures": state.get("consecutive_orchestrator_failures", 0),
    }


def orchestrator_prompt(checklist: dict[str, Any], state: dict[str, Any], user_prompt: str = "") -> str:
    return (
        "You are the prompt-driven bot autonomy orchestrator for this TrinityCore repo. "
        "Run one durable orchestration pass toward the user's original goal.\n\n"
        "Responsibilities for this pass:\n"
        "- Read and follow the user prompt snapshot shown below.\n"
        "- Inspect the current repo, checklist, daemon state, and prior run artifacts.\n"
        "- Create or resume worker/reviewer Codex sessions as needed; the daemon will not launch them for you.\n"
        "- Run validation yourself with the repo tools when validation is needed.\n"
        "- Commit experiment code/configs to git, checkpoint generated data/artifacts with DVC, run dvc status, and push DVC artifacts when appropriate.\n"
        "- Update progress/checklist files with evidence paths.\n\n"
        "Worktree cleanup requirement:\n"
        "- Before returning, inspect git status in the active worktree.\n"
        "- Commit useful finished changes with a focused message, including progress/checklist updates and useful experiment configs/code.\n"
        "- Discard only changes you made in this pass that are wrong or failed; do not discard pre-existing user changes from the starting status snapshot unless the user explicitly asked you to.\n"
        "- This requirement applies whether the pass succeeds, fails, or needs follow-up; leave the worktree clean except for protected pre-existing changes.\n\n"
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
            state.update({"status": "stopping", "phase": "stop_requested"})
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
        }
    )
    save_state(state, state_path)

    if was_paused_rate_limit:
        role = "orchestrator"
        state.update(
            {
                "prompt_file": existing_rate_limit.get("prompt_file", state.get("prompt_file", "")),
                "prompt_hash": existing_rate_limit.get("prompt_hash", state.get("prompt_hash", "")),
                "prompt_snapshot_path": existing_rate_limit.get("prompt_snapshot_path", state.get("prompt_snapshot_path", "")),
            }
        )
        model = str(config["orchestrator_model"])
        resumed = run_codex_role(
            role=role,
            prompt=str(existing_rate_limit.get("prompt") or "Resume after the rate-limit reset and finish the interrupted orchestrator pass."),
            model=model,
            repo=repo,
            sandbox=str(config["sandbox"]),
            cycle_id=cycle_id,
            state=state,
            config=config,
            thread_id=str(existing_rate_limit.get("thread_id") or ""),
            state_path=state_path,
        )
        if resumed["rate_limit"]:
            handle_rate_limit(state, resumed["rate_limit"], state_path)
            return {"done": False, "rate_limit": True}
        if resumed["returncode"] != 0:
            result = {
                "status": "failure",
                "error": "orchestrator_resume_failed",
                "returncode": resumed["returncode"],
                "thread_id": resumed.get("thread_id", ""),
                "jsonl_path": str(resumed["jsonl_path"]),
                "stderr_path": str(resumed["stderr_path"]),
                "last_message_path": str(resumed["last_message_path"]),
            }
            state.update(
                {
                    "status": "running",
                    "phase": "orchestrator_resume_failed",
                    "latest_orchestrator_result": result,
                    "consecutive_orchestrator_failures": int(state.get("consecutive_orchestrator_failures") or 0) + 1,
                    "rate_limit": {},
                    "thread_id": resumed.get("thread_id", ""),
                }
            )
            save_state(state, state_path)
            return {"done": False, "error": "orchestrator_resume_failed", "returncode": resumed["returncode"]}
        result = read_orchestrator_result(resumed["last_message_path"])
        if not result:
            result = {
                "status": "failure",
                "error": "orchestrator_result_contract_invalid",
                "returncode": resumed["returncode"],
                "thread_id": resumed.get("thread_id", ""),
                "jsonl_path": str(resumed["jsonl_path"]),
                "stderr_path": str(resumed["stderr_path"]),
                "last_message_path": str(resumed["last_message_path"]),
            }
            state.update(
                {
                    "status": "running",
                    "phase": "orchestrator_result_contract_invalid",
                    "latest_orchestrator_result": result,
                    "consecutive_orchestrator_failures": int(state.get("consecutive_orchestrator_failures") or 0) + 1,
                    "rate_limit": {},
                    "thread_id": resumed.get("thread_id", ""),
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
                "thread_id": resumed.get("thread_id", ""),
            }
        )
        save_state(state, state_path)
        return {"done": result["status"] == "complete", "status": result["status"], "resumed": role}

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
        prompt=orchestrator_prompt(checklist, state, user_prompt),
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
    try:
        while True:
            state = load_state(args.state)
            update_state_instance_metadata(state, args, config)
            if state.get("status") == "paused_rate_limit":
                if not sleep_until_resume(state, args.stop_file, args.state):
                    return 0
            if args.stop_file.exists():
                state.update({"status": "stopped", "phase": "stop_requested"})
                save_state(state, args.state)
                return 0
            result = run_one_cycle(state, config, args.state)
            if result.get("done"):
                return 0
            if result.get("rate_limit"):
                continue
            error = str(result.get("error") or "")
            if error:
                state = load_state(args.state)
                state.update({"status": "running", "phase": error})
                save_state(state, args.state)
            if args.once or (args.max_cycles and int(state.get("cycle_id") or 0) >= args.max_cycles):
                return 0
            time.sleep(max(1, int(config["heartbeat_sec"])))
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


def status_payload(args: argparse.Namespace) -> dict[str, Any]:
    state = load_state(args.state)
    update_state_instance_metadata(state, args, {"runs_dir": str(getattr(args, "runs_dir", DEFAULT_RUNS_DIR))})
    checklist = load_checklist(args.checklist)
    rate_limit = state.get("rate_limit") if isinstance(state.get("rate_limit"), dict) else {}
    return {
        "schema": "orchestrator_daemon_status_v1",
        "instance_id": str(getattr(args, "instance_id", LEGACY_INSTANCE_ID)),
        "state": state,
        "checklist": checklist_summary(checklist),
        "lock_exists": args.lock.exists(),
        "pid": args.pid.read_text(encoding="utf-8").strip() if args.pid.exists() else "",
        "rate_limit_sleep_remaining_sec": max(0, int(rate_limit.get("resume_at_unix") or 0) - now_unix()),
        "stop_requested": args.stop_file.exists(),
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
