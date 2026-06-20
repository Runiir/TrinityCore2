from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
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


DEFAULT_CONFIG: dict[str, Any] = {
    "orchestrator_model": "gpt-5",
    "worker_model": "gpt-5",
    "reviewer_model": "gpt-5",
    "sandbox": "danger-full-access",
    "max_parallel_workers": 1,
    "heartbeat_sec": 30,
    "no_progress_window_sec": 180,
    "emergency_timeout_sec": 900,
    "rate_limit_default_sleep_sec": 3600,
    "rate_limit_max_sleep_sec": 86400,
    "repo": str(REPO_ROOT),
    "test_command": "pixi run pytest -q",
    "validation_plan_command": "pixi run bot-validation-run-plan --duration-policy completion-watchdog --observe-sec 300 --timeout-sec 900",
    "validation_command": "bash dataset/validation_run_plan/run_validation_scenarios.sh",
    "scenario_report_command": "pixi run bot-live-scenario-reports",
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


def initial_state() -> dict[str, Any]:
    return {
        "schema": "bot_autonomy_daemon_state_v1",
        "status": "idle",
        "cycle_id": 0,
        "phase": "",
        "active_agent_role": "",
        "thread_id": "",
        "codex_command": [],
        "latest_jsonl_path": "",
        "latest_stderr_path": "",
        "latest_last_message_path": "",
        "rate_limit": {},
        "lane_id": "",
        "latest_report": "",
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


def codex_command(
    *,
    role: str,
    prompt: str,
    model: str,
    repo: Path,
    sandbox: str,
    jsonl_path: Path,
    last_message_path: Path,
    thread_id: str = "",
) -> tuple[list[str], str | None]:
    if thread_id:
        command = [
            "codex",
            "exec",
            "resume",
            "--json",
            "-m",
            model,
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
    run_dir = DEFAULT_RUNS_DIR / f"{cycle_id:06d}"
    run_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = run_dir / f"{role}.jsonl"
    stderr_path = run_dir / f"{role}.stderr"
    last_message_path = run_dir / f"{role}.last_message.md"
    command, stdin_text = codex_command(
        role=role,
        prompt=prompt,
        model=model,
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


def orchestrator_prompt(checklist: dict[str, Any], state: dict[str, Any]) -> str:
    return (
        "You are the bot autonomy orchestrator for this TrinityCore repo. "
        "Choose the next single atomic action needed to get every deliverable in "
        ".codex/plans/auto_bots/master_checklist.json to status accepted with promoted final evidence.\n\n"
        "Return only a JSON object with fields: action, lane_id, deliverable, reason. "
        "Valid actions: fix_blocker, run_validation, stop_complete.\n\n"
        f"Checklist summary:\n{json.dumps(checklist_summary(checklist), indent=2, sort_keys=True)}\n\n"
        f"Current daemon state:\n{json.dumps(state, indent=2, sort_keys=True)}\n"
    )


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
    checklist = load_checklist()
    if checklist_complete(checklist):
        state.update({"status": "complete", "phase": "complete", "goal_complete": True})
        save_state(state, state_path)
        return {"done": True, "reason": "checklist_complete"}

    was_paused_rate_limit = state.get("status") == "paused_rate_limit"
    existing_rate_limit = state.get("rate_limit") if isinstance(state.get("rate_limit"), dict) else {}
    cycle_id = int(state.get("cycle_id") or 0) + 1
    state.update({"cycle_id": cycle_id, "status": "running", "phase": "orchestrator", "goal_complete": False})
    save_state(state, state_path)

    if was_paused_rate_limit:
        role = str(existing_rate_limit.get("agent_role") or "orchestrator")
        model = str(config["orchestrator_model"])
        if role == "worker":
            model = str(config["worker_model"])
        elif role == "reviewer":
            model = str(config["reviewer_model"])
        resumed = run_codex_role(
            role=role,
            prompt=str(existing_rate_limit.get("prompt") or "Resume after the rate-limit reset and finish the interrupted atomic step."),
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
            return {"done": False, "error": f"{role}_resume_failed", "returncode": resumed["returncode"]}
        state.update({"status": "running", "phase": f"{role}_resumed", "rate_limit": {}, "thread_id": resumed.get("thread_id", "")})
        save_state(state, state_path)
        return {"done": False, "resumed": role}

    orchestrator = run_codex_role(
        role="orchestrator",
        prompt=orchestrator_prompt(checklist, state),
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
        return {"done": False, "error": "orchestrator_failed", "returncode": orchestrator["returncode"]}

    action = extract_json_object(orchestrator["last_message_path"].read_text(encoding="utf-8", errors="replace") if orchestrator["last_message_path"].exists() else "")
    if action.get("action") == "stop_complete" or checklist_complete(load_checklist()):
        state.update({"status": "complete", "phase": "complete", "goal_complete": True})
        save_state(state, state_path)
        return {"done": True, "reason": "orchestrator_stop_complete"}

    lane_id = next_lane_id(state, action)
    state.update({"lane_id": lane_id})
    save_state(state, state_path)

    if action.get("action") == "fix_blocker":
        worktree = create_worker_worktree(repo, lane_id)
        worker = run_codex_role(
            role="worker",
            prompt=worker_prompt(action, checklist),
            model=str(config["worker_model"]),
            repo=worktree,
            sandbox=str(config["sandbox"]),
            cycle_id=cycle_id,
            state=state,
            config=config,
            state_path=state_path,
        )
        if worker["rate_limit"]:
            handle_rate_limit(state, worker["rate_limit"], state_path)
            return {"done": False, "rate_limit": True}
        if worker["returncode"] != 0:
            return {"done": False, "error": "worker_failed", "returncode": worker["returncode"]}
        tests = run_shell(str(config["test_command"]), worktree, None)
        run_dir = DEFAULT_RUNS_DIR / f"{cycle_id:06d}"
        write_json(run_dir / "tests.json", tests)
        if tests["returncode"] != 0:
            state.update({"latest_report": str(run_dir / "tests.json"), "phase": "tests_failed"})
            save_state(state, state_path)
            return {"done": False, "error": "tests_failed", "returncode": tests["returncode"]}
        reviewer = run_codex_role(
            role="reviewer",
            prompt=reviewer_prompt(action),
            model=str(config["reviewer_model"]),
            repo=worktree,
            sandbox=str(config["sandbox"]),
            cycle_id=cycle_id,
            state=state,
            config=config,
            state_path=state_path,
        )
        if reviewer["rate_limit"]:
            handle_rate_limit(state, reviewer["rate_limit"], state_path)
            return {"done": False, "rate_limit": True}
        if reviewer["returncode"] != 0 or not reviewer_accepted(reviewer["last_message_path"]):
            return {"done": False, "error": "reviewer_rejected", "returncode": reviewer["returncode"]}
        branch = f"bot-autonomy/{lane_id}"
        merge = subprocess.run(["git", "merge", "--no-ff", "--no-edit", branch], cwd=repo, text=True, capture_output=True, check=False)
        write_json(DEFAULT_RUNS_DIR / f"{cycle_id:06d}" / "merge.json", {"returncode": merge.returncode, "stdout": merge.stdout, "stderr": merge.stderr})
        if merge.returncode != 0:
            return {"done": False, "error": "merge_failed", "returncode": merge.returncode}

    if action.get("action") in {"run_validation", "fix_blocker"}:
        validation = run_validation_cycle(repo, config)
        report_path = DEFAULT_RUNS_DIR / f"{cycle_id:06d}" / "validation.json"
        write_json(report_path, validation)
        state.update({"latest_report": str(report_path), "phase": "validation_complete" if validation["accepted"] else "validation_failed"})
        save_state(state, state_path)
        return {"done": False, "validation": validation["accepted"]}

    return {"done": False, "error": "unknown_action", "action": action}


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
    state = load_state(args.state)
    acquire_lock(args.lock, args.pid)
    failures: dict[str, int] = {}
    try:
        while True:
            state = load_state(args.state)
            checklist = load_checklist(args.checklist)
            if checklist_complete(checklist):
                state.update({"status": "complete", "phase": "complete", "goal_complete": True})
                save_state(state, args.state)
                return 0
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
                failures[error] = failures.get(error, 0) + 1
                state.update({"status": "blocked" if failures[error] >= 3 else "running", "phase": error})
                save_state(state, args.state)
                if failures[error] >= 3:
                    return 2
            if args.once or (args.max_cycles and int(state.get("cycle_id") or 0) >= args.max_cycles):
                return 0
            time.sleep(max(1, int(config["heartbeat_sec"])))
    finally:
        release_lock(args.lock, args.pid)


def start_daemon(args: argparse.Namespace) -> int:
    if args.lock.exists():
        raise SystemExit(f"daemon already appears to be running: {args.lock}")
    args.log.parent.mkdir(parents=True, exist_ok=True)
    with args.log.open("ab") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tools.bot_ml.bot_autonomy_daemon",
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
                "run",
            ],
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
    checklist = load_checklist(args.checklist)
    rate_limit = state.get("rate_limit") if isinstance(state.get("rate_limit"), dict) else {}
    return {
        "schema": "bot_autonomy_daemon_status_v1",
        "state": state,
        "checklist": checklist_summary(checklist),
        "lock_exists": args.lock.exists(),
        "pid": args.pid.read_text(encoding="utf-8").strip() if args.pid.exists() else "",
        "rate_limit_sleep_remaining_sec": max(0, int(rate_limit.get("resume_at_unix") or 0) - now_unix()),
        "stop_requested": args.stop_file.exists(),
    }


def stop_daemon(args: argparse.Namespace) -> int:
    args.stop_file.parent.mkdir(parents=True, exist_ok=True)
    args.stop_file.write_text(str(now_unix()), encoding="utf-8")
    print(json.dumps({"stop_requested": True, "stop_file": str(args.stop_file)}, indent=2, sort_keys=True))
    return 0


def doctor(args: argparse.Namespace) -> int:
    config = load_config(args.config)
    checks: list[dict[str, Any]] = []
    for name, command in [
        ("codex", "codex --version"),
        ("dvc_status", str(config["dvc_status_command"])),
    ]:
        result = run_shell(command, REPO_ROOT, int(config["emergency_timeout_sec"]))
        checks.append({"name": name, "ok": result["returncode"] == 0, "returncode": result["returncode"], "stderr_tail": result["stderr"][-1000:]})
    worldserver = REPO_ROOT / "build" / "src" / "server" / "worldserver" / "worldserver"
    checks.append({"name": "worldserver_binary", "ok": worldserver.exists(), "path": str(worldserver)})
    checks.append({"name": "daemon_lock", "ok": not args.lock.exists(), "path": str(args.lock), "locked": args.lock.exists()})
    payload = {
        "schema": "bot_autonomy_daemon_doctor_v1",
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
        "config": config,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload["ok"] else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the long-lived local Codex bot-autonomy daemon.")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_PATH)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--checklist", type=Path, default=DEFAULT_CHECKLIST_PATH)
    parser.add_argument("--lock", type=Path, default=DEFAULT_LOCK_PATH)
    parser.add_argument("--pid", type=Path, default=DEFAULT_PID_PATH)
    parser.add_argument("--stop-file", type=Path, default=DEFAULT_STOP_PATH)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_parser = subparsers.add_parser("run", help="Run the daemon in the foreground.")
    run_parser.add_argument("--once", action="store_true", help="Run at most one daemon cycle.")
    run_parser.add_argument("--max-cycles", type=int, default=0)
    subparsers.add_parser("start", help="Start the daemon in the background.")
    subparsers.add_parser("status", help="Print daemon status as JSON.")
    subparsers.add_parser("stop", help="Request graceful stop after the current atomic step.")
    subparsers.add_parser("doctor", help="Validate local prerequisites.")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "run":
        return run_daemon(args)
    if args.command == "start":
        return start_daemon(args)
    if args.command == "status":
        print(json.dumps(status_payload(args), indent=2, sort_keys=True))
        return 0
    if args.command == "stop":
        return stop_daemon(args)
    if args.command == "doctor":
        return doctor(args)
    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
