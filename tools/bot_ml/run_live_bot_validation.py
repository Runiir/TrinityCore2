from __future__ import annotations

import argparse
import base64
import html
import json
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

try:
    from .common import write_json
except ImportError:
    from common import write_json


DEFAULT_STAGES = [
    "movement_smoke",
    "kill_quest",
    "collect_quest",
    "quest_hub_batching",
    "trainer_visit",
    "vendor_repair",
    "profession_recipe_acquisition",
    "material_farming",
    "smart_loot",
    "normal_dungeon_trash",
    "dungeon_boss",
    "full_stonecore_clear",
    "raid_trash",
    "raid_boss",
    "full_blackwing_descent_clear",
]


def command_script(selector: str = "all", trace_limit: int = 20, start: bool = True, stop: bool = False, exit_server: bool = True) -> str:
    commands: list[str] = []
    if start:
        commands.append(".botauto start")
    commands.extend(
        [
            ".botauto status",
            f".botauto diagnose {selector}",
            f".botauto trace {selector} {trace_limit}",
            ".botexp summary",
        ]
    )
    if stop:
        commands.append(".botauto stop")
    if exit_server:
        commands.append("server exit")
    return "\n".join(commands) + "\n"


def parse_json_objects(output: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in output.splitlines():
        text = line.strip()
        if not text:
            continue
        start = text.find("{")
        end = text.rfind("}")
        if start == -1 or end == -1 or end <= start:
            continue
        try:
            payload = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def classify_payloads(payloads: list[dict[str, Any]]) -> dict[str, Any]:
    status = next((row for row in payloads if row.get("action") in {"botexp_status", "botauto_status"} or {"active", "active_bots", "target_bots"} & set(row)), {})
    diagnosis = next((row for row in payloads if row.get("diagnosis_schema_version") or row.get("diagnoses") or row.get("diagnosis")), {})
    trace = next((row for row in payloads if row.get("trace_schema_version") or row.get("entries")), {})
    summary = next((row for row in payloads if row.get("summary_schema_version") or "duration_minutes" in row or "total_kills" in row or "bot_learning" in row), {})
    return {"status": status, "diagnosis": diagnosis, "trace": trace, "summary": summary}


def command_errors(output: str) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    current_command = ""
    for line in output.splitlines():
        text = line.strip()
        if text.startswith("$ "):
            current_command = text[2:]
        elif "There is no such subcommand" in text:
            errors.append({"command": current_command, "error": "no_such_subcommand"})
    return errors


def count_trace_entries(trace: dict[str, Any]) -> int:
    entries = trace.get("entries")
    if isinstance(entries, list):
        return len(entries)
    bots = trace.get("bots")
    if isinstance(bots, list):
        return sum(len(bot.get("entries") or []) for bot in bots if isinstance(bot, dict))
    return 0


def trace_entries(trace: dict[str, Any]) -> list[dict[str, Any]]:
    entries = trace.get("entries")
    if isinstance(entries, list):
        return [entry for entry in entries if isinstance(entry, dict)]
    bots = trace.get("bots")
    if isinstance(bots, list):
        rows: list[dict[str, Any]] = []
        for bot in bots:
            if isinstance(bot, dict):
                rows.extend(entry for entry in bot.get("entries") or [] if isinstance(entry, dict))
        return rows
    return []


def diagnosis_rows(diagnosis: dict[str, Any]) -> list[dict[str, Any]]:
    rows = diagnosis.get("diagnoses") or diagnosis.get("bots") or ([] if not diagnosis else [diagnosis])
    return [row for row in rows if isinstance(row, dict)]


def nested_get(row: dict[str, Any], path: list[str], default: Any = None) -> Any:
    value: Any = row
    for key in path:
        if not isinstance(value, dict):
            return default
        value = value.get(key)
    return default if value is None else value


def live_evidence(status: dict[str, Any], diagnosis: dict[str, Any], trace: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    entries = trace_entries(trace)
    diagnoses = diagnosis_rows(diagnosis)
    non_spawn_trace_entries = sum(1 for entry in entries if str(entry.get("action") or entry.get("situation") or "") != "bot_spawned")
    decisions = max(int(status.get("decisions") or 0), int(summary.get("decisions") or 0), non_spawn_trace_entries)
    failures = max(int(status.get("failures") or 0), int(summary.get("failures_recorded") or 0))
    duration_seconds = int(status.get("duration_seconds") or 0)
    duration_minutes = float(summary.get("duration_minutes") or 0.0)
    moved_diagnoses = sum(1 for row in diagnoses if bool(nested_get(row, ["snapshot", "movement", "is_moving"], False)) or float(nested_get(row, ["snapshot", "movement", "distance_moved_since_last_decision"], 0) or 0) > 0.0)
    non_wait_diagnoses = sum(1 for row in diagnoses if str(nested_get(row, ["snapshot", "decision", "action"], "wait")) not in {"", "wait"})
    action_names = {
        str(entry.get("action") or entry.get("situation") or "")
        for entry in entries
        if entry.get("action") or entry.get("situation")
    }
    quest_acceptance_actions = sum(
        1
        for entry in entries
        if str(entry.get("action") or "").startswith("accept_quest") or str(entry.get("action") or "") == "accept_hub_quests"
    )
    quest_completion_actions = sum(
        1
        for entry in entries
        if str(entry.get("action") or "").startswith("complete_quest")
    )
    action_names.update(
        str(nested_get(row, ["snapshot", "decision", "action"], ""))
        for row in diagnoses
        if nested_get(row, ["snapshot", "decision", "action"], "")
    )
    action_text = " ".join(sorted(action_names)).lower()
    quest_progress = max(int(status.get("quest_objective_progress") or 0), int(summary.get("quest_objective_progress") or 0))
    quests_accepted = max(int(status.get("quests_accepted") or 0), int(summary.get("quests_accepted") or 0), quest_acceptance_actions)
    quests_completed = max(int(status.get("quests_completed") or 0), int(summary.get("quests_completed") or 0), quest_completion_actions)
    kills = max(int(status.get("kills") or 0), int(summary.get("total_kills") or 0))
    gear_upgrades = max(int(status.get("gear_upgrades") or 0), int(summary.get("gear_upgrades") or 0))
    active_decision_evidence = decisions > 0 or non_spawn_trace_entries > 0 or moved_diagnoses > 0 or non_wait_diagnoses > 0
    return {
        "decisions": decisions,
        "failures": failures,
        "duration_seconds": duration_seconds,
        "duration_minutes": duration_minutes,
        "moved_diagnoses": moved_diagnoses,
        "non_wait_diagnoses": non_wait_diagnoses,
        "non_spawn_trace_entries": non_spawn_trace_entries,
        "quest_objective_progress": quest_progress,
        "quests_accepted": quests_accepted,
        "quests_completed": quests_completed,
        "kills": kills,
        "gear_upgrades": gear_upgrades,
        "action_names": sorted(action_names),
        "vendor_or_trainer_action": any(token in action_text for token in ["vendor", "repair", "train"]),
        "profession_action": any(token in action_text for token in ["profession", "recipe", "craft"]),
        "material_farming_action": any(token in action_text for token in ["material", "farm", "gather", "herb", "mine", "skin"]),
        "loot_action": any(token in action_text for token in ["loot", "roll", "gear_upgrade"]),
        "active_decision_evidence": active_decision_evidence,
    }


def live_validation_report(output: str, stages: list[str] | None = None, returncode: int = 0, timed_out: bool = False, command: list[str] | None = None) -> dict[str, Any]:
    payloads = parse_json_objects(output)
    classified = classify_payloads(payloads)
    errors = command_errors(output)
    diagnosis = classified["diagnosis"]
    trace = classified["trace"]
    status = classified["status"]
    summary = classified["summary"]

    active_bots = int(status.get("active_bots") or status.get("bots") or status.get("activeBots") or 0)
    target_bots = int(status.get("target_bots") or status.get("targetBots") or 0)
    trace_entries = count_trace_entries(trace)
    diagnosis_count = len(diagnosis_rows(diagnosis))
    evidence = live_evidence(status, diagnosis, trace, summary)

    stage_rows = []
    for stage in stages or DEFAULT_STAGES:
        missing: list[str] = []
        if stage in {"movement_smoke", "kill_quest", "collect_quest", "quest_hub_batching", "trainer_visit", "vendor_repair", "profession_recipe_acquisition", "material_farming", "smart_loot"}:
            if active_bots <= 0:
                missing.append("active_autonomy_bots")
            if not diagnosis:
                missing.append("botauto_diagnose_json")
            if trace_entries <= 0:
                missing.append("botauto_trace_entries")
            if not evidence["active_decision_evidence"]:
                missing.append("active_decision_or_movement_evidence")
            if stage in {"kill_quest", "normal_dungeon_trash", "dungeon_boss"} and evidence["kills"] <= 0:
                missing.append("kill_evidence")
            if stage in {"collect_quest", "quest_hub_batching"} and evidence["quest_objective_progress"] <= 0 and evidence["quests_completed"] <= 0:
                missing.append("quest_progress_evidence")
            if stage == "quest_hub_batching" and evidence["quests_accepted"] <= 0:
                missing.append("quest_acceptance_evidence")
            if stage in {"trainer_visit", "vendor_repair"} and not evidence["vendor_or_trainer_action"]:
                missing.append("vendor_or_trainer_action_evidence")
            if stage == "profession_recipe_acquisition" and not evidence["profession_action"]:
                missing.append("profession_or_recipe_action_evidence")
            if stage == "material_farming" and not evidence["material_farming_action"]:
                missing.append("material_farming_action_evidence")
            if stage == "smart_loot" and evidence["gear_upgrades"] <= 0 and not evidence["loot_action"]:
                missing.append("loot_or_gear_upgrade_evidence")
        elif stage in {"normal_dungeon_trash", "dungeon_boss", "full_stonecore_clear"}:
            missing.extend(["prepared_5man_group", "stonecore_live_clear_report"])
        elif stage in {"raid_trash", "raid_boss", "full_blackwing_descent_clear"}:
            missing.extend(["prepared_10man_raid", "blackwing_descent_live_clear_report"])
        stage_rows.append({"stage": stage, "passed": not missing, "missing": missing})

    passed = sum(1 for row in stage_rows if row["passed"])
    return {
        "schema": "bot_live_validation_report_v1",
        "command": command or [],
        "returncode": returncode,
        "timed_out": timed_out,
        "json_payloads": len(payloads),
        "active_bots": active_bots,
        "target_bots": target_bots,
        "diagnosis_count": diagnosis_count,
        "trace_entries": trace_entries,
        "status": status,
        "diagnosis": diagnosis,
        "trace": trace,
        "summary": summary,
        "command_errors": errors,
        "evidence": evidence,
        "stages": stage_rows,
        "passed": passed,
        "failed": len(stage_rows) - passed,
        "all_passed": passed == len(stage_rows),
        "runtime_ml_control": "disabled_until_live_validation_passes",
    }


def run_worldserver(binary: Path, config: Path, timeout_sec: int, script: str, observe_sec: int = 0) -> tuple[str, int, bool, list[str]]:
    command = [str(binary), "--config", str(config)]
    if observe_sec > 0:
        deadline = time.monotonic() + timeout_sec
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert process.stdin is not None
        try:
            for raw_command in script.splitlines():
                process.stdin.write(raw_command + "\n")
                process.stdin.flush()
                if raw_command.strip() == ".botauto start":
                    time.sleep(observe_sec)
            process.stdin.close()
            process.stdin = None
            remaining = max(1, int(deadline - time.monotonic()))
            output, _ = process.communicate(timeout=remaining)
            returncode = process.returncode if process.returncode is not None else 0
            return output, returncode, False, command
        except (BrokenPipeError, subprocess.TimeoutExpired) as exc:
            process.kill()
            output = (exc.stdout or "") if isinstance(exc, subprocess.TimeoutExpired) else ""
            if not output and process.stdout:
                output = process.stdout.read()
            return output, 124, True, command

    try:
        completed = subprocess.run(command, input=script, text=True, capture_output=True, timeout=timeout_sec, check=False)
        return completed.stdout + completed.stderr, completed.returncode, False, command
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or "") + (exc.stderr or "")
        return output, 124, True, command


def soap_envelope(command: str) -> bytes:
    escaped = html.escape(command, quote=True)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<SOAP-ENV:Envelope xmlns:SOAP-ENV="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ns1="urn:TC">'
        "<SOAP-ENV:Body>"
        f"<ns1:executeCommand><command>{escaped}</command></ns1:executeCommand>"
        "</SOAP-ENV:Body>"
        "</SOAP-ENV:Envelope>"
    ).encode("utf-8")


def parse_soap_result(payload: str) -> str:
    start = payload.find("<result>")
    end = payload.find("</result>")
    if start == -1 or end == -1 or end <= start:
        return payload
    return html.unescape(payload[start + len("<result>") : end])


def run_soap_commands(soap_url: str, username: str, password: str, script: str, timeout_sec: int, observe_sec: int = 0) -> tuple[str, int, bool, list[str]]:
    output_parts: list[str] = []
    auth = base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")
    command = ["SOAP", soap_url]
    deadline = time.monotonic() + timeout_sec
    for raw_command in script.splitlines():
        command_text = raw_command.strip()
        if not command_text:
            continue
        remaining_float = deadline - time.monotonic()
        if remaining_float <= 0:
            return "\n".join(output_parts), 124, True, command
        remaining = max(1, int(remaining_float))
        request = urllib.request.Request(
            soap_url,
            data=soap_envelope(command_text),
            headers={
                "Authorization": f"Basic {auth}",
                "Content-Type": "text/xml; charset=utf-8",
                "SOAPAction": "urn:TC#executeCommand",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=remaining) as response:
                payload = response.read().decode("utf-8", errors="replace")
                output_parts.append(f"$ {command_text}")
                output_parts.append(parse_soap_result(payload))
                if observe_sec > 0 and command_text == ".botauto start":
                    output_parts.append(f"$ sleep {observe_sec}")
                    time.sleep(observe_sec)
        except urllib.error.HTTPError as exc:
            payload = exc.read().decode("utf-8", errors="replace")
            output_parts.append(f"$ {command_text}")
            output_parts.append(payload)
            return "\n".join(output_parts), exc.code, False, command
        except TimeoutError:
            return "\n".join(output_parts), 124, True, command
        except OSError as exc:
            output_parts.append(f"$ {command_text}")
            output_parts.append(str(exc))
            return "\n".join(output_parts), 1, False, command
    return "\n".join(output_parts), 0, False, command


def main() -> int:
    parser = argparse.ArgumentParser(description="Run or prepare live BotWorld validation diagnostics.")
    parser.add_argument("--worldserver", type=Path, default=Path("build/src/server/worldserver/worldserver"))
    parser.add_argument("--config", type=Path, default=Path("trinity-worldserver-test.conf"))
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/live_validation"))
    parser.add_argument("--timeout-sec", type=int, default=90)
    parser.add_argument("--selector", default="all")
    parser.add_argument("--trace-limit", type=int, default=20)
    parser.add_argument("--no-start", action="store_true")
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--transport", choices=["process", "soap"], default="process")
    parser.add_argument("--soap-url", default="http://127.0.0.1:7878/")
    parser.add_argument("--soap-user")
    parser.add_argument("--soap-password")
    parser.add_argument("--observe-sec", type=int, default=0, help="Sleep after .botauto start before collecting diagnostics.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--input-log", type=Path)
    args = parser.parse_args()

    script = command_script(selector=args.selector, trace_limit=args.trace_limit, start=not args.no_start, stop=args.stop, exit_server=args.transport == "process")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "commands.txt").write_text(script, encoding="utf-8")

    if args.dry_run:
        report = {
            "schema": "bot_live_validation_report_v1",
            "dry_run": True,
            "command_script": script,
            "worldserver": str(args.worldserver),
            "config": str(args.config),
            "transport": args.transport,
            "soap_url": args.soap_url if args.transport == "soap" else "",
            "timeout_sec": args.timeout_sec,
            "observe_sec": args.observe_sec,
            "instructions": "Run make host-world-botexp-small for attached diagnostics or execute this script without --dry-run when the worldserver binary and config are ready.",
        }
        write_json(args.output_dir / "report.json", report)
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0

    if args.input_log:
        output = args.input_log.read_text(encoding="utf-8")
        returncode = 0
        timed_out = False
        command: list[str] = []
    else:
        if args.transport == "soap":
            if not args.soap_user or not args.soap_password:
                raise SystemExit("--soap-user and --soap-password are required with --transport soap")
            output, returncode, timed_out, command = run_soap_commands(args.soap_url, args.soap_user, args.soap_password, script, args.timeout_sec, args.observe_sec)
        else:
            output, returncode, timed_out, command = run_worldserver(args.worldserver, args.config, args.timeout_sec, script, args.observe_sec)

    (args.output_dir / "worldserver_output.log").write_text(output, encoding="utf-8")
    report = live_validation_report(output, returncode=returncode, timed_out=timed_out, command=command)
    report["generated_at_unix"] = int(time.time())
    write_json(args.output_dir / "report.json", report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if returncode == 0 and not timed_out else 1


if __name__ == "__main__":
    raise SystemExit(main())
