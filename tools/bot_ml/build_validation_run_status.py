from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .common import stable_hash, write_json
except ImportError:
    from common import stable_hash, write_json


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def load_report(path: Path) -> tuple[dict[str, Any], str]:
    if not path.exists():
        return {}, "missing_report"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, "invalid_json"
    if not isinstance(payload, dict):
        return {}, "report_not_object"
    return payload, ""


def segment_report_path(segment: dict[str, Any]) -> Path:
    return Path(str(segment.get("live_output_dir") or "")) / "report.json"


def scenario_report_path(report_root: Path, scenario_id: str) -> Path:
    return report_root / f"{scenario_id}.json"


def stage_passed(report: dict[str, Any], stage: str) -> bool:
    for row in report.get("stages") or []:
        if isinstance(row, dict) and row.get("stage") == stage:
            return bool(row.get("passed"))
    return False


def trace_actions(report: dict[str, Any]) -> list[str]:
    trace = report.get("trace") if isinstance(report.get("trace"), dict) else {}
    entries = trace.get("entries") if isinstance(trace.get("entries"), list) else []
    return [str(row.get("action") or row.get("situation") or "") for row in entries if isinstance(row, dict)]


def int_field(row: dict[str, Any], *keys: str) -> int:
    values = []
    for key in keys:
        try:
            values.append(int(row.get(key) or 0))
        except (TypeError, ValueError):
            values.append(0)
    return max(values or [0])


def is_raid_scenario(scenario: dict[str, Any]) -> bool:
    scenario_id = str(scenario.get("scenario_id") or "").lower()
    difficulty = str(scenario.get("difficulty") or "").lower()
    instance = str(scenario.get("instance") or "").lower()
    return "raid" in difficulty or "10" in difficulty or "blackwing" in scenario_id or "blackwing" in instance


def expected_boss_stage(scenario: dict[str, Any]) -> str:
    return "raid_boss" if is_raid_scenario(scenario) else "dungeon_boss"


def expected_trash_stage(scenario: dict[str, Any]) -> str:
    return "raid_trash" if is_raid_scenario(scenario) else "normal_dungeon_trash"


def has_boss_kill_evidence(report: dict[str, Any], scenario: dict[str, Any]) -> bool:
    stage = expected_boss_stage(scenario)
    if stage_passed(report, stage):
        return True
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    evidence = report.get("evidence") if isinstance(report.get("evidence"), dict) else {}
    actions = set(trace_actions(report))
    if int_field(evidence, "boss_kill_evidence") > 0:
        return True
    if is_raid_scenario(scenario):
        return int_field(summary, "raid_boss_kills", "boss_kills", "bosses_killed") > 0 or "raid_boss_killed" in actions
    return int_field(summary, "boss_kills", "dungeon_boss_kills", "bosses_killed") > 0 or "boss_killed" in actions


def has_trash_evidence(report: dict[str, Any], scenario: dict[str, Any]) -> bool:
    if stage_passed(report, expected_trash_stage(scenario)):
        return True
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    evidence = report.get("evidence") if isinstance(report.get("evidence"), dict) else {}
    actions = set(trace_actions(report))
    return (
        int_field(summary, "trash_pulls", "trash_kills", "trash_packs_cleared") > 0
        or int_field(evidence, "trash_pulls", "trash_kills", "trash_packs_cleared", "trash_action_evidence") > 0
        or bool(actions & {"trash_action", "trash_killed", "dungeon_trash_cleared", "raid_trash_cleared"})
    )


def scenario_segment_result(scenario_report: dict[str, Any], segment: dict[str, Any]) -> dict[str, Any]:
    expected_segment_id = str(segment.get("segment_id") or "")
    expected_route_node_id = str(segment.get("route_node_id") or "")
    for row in scenario_report.get("segment_results") or []:
        if not isinstance(row, dict):
            continue
        if expected_segment_id and str(row.get("segment_id") or "") != expected_segment_id:
            continue
        if expected_route_node_id and str(row.get("route_node_id") or "") != expected_route_node_id:
            continue
        return row
    return {}


def validate_scenario_segment_result(row: dict[str, Any], segment: dict[str, Any], scenario: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    if not row:
        return {
            "report_valid": False,
            "validation_context_matches": False,
            "boss_evidence_ready": False,
            "segment_ready": False,
            "invalid_reasons": ["missing_scenario_segment_result"],
        }
    if str(row.get("route_kind") or "") != str(segment.get("kind") or ""):
        reasons.append("route_kind_mismatch")
    if str(row.get("mechanic_profile") or "") != str(segment.get("mechanic_profile") or ""):
        reasons.append("mechanic_profile_mismatch")
    failure_labels = row.get("failure_labels") if isinstance(row.get("failure_labels"), list) else []
    failure_reason = str(row.get("failure_reason") or "")
    if failure_labels or failure_reason:
        reasons.append("scenario_segment_has_failures")
    boss_ready = True
    if str(segment.get("kind") or "") == "boss":
        boss_ready = int_field(row, "boss_kills", "raid_boss_kills", "bosses_killed") > 0
        if not boss_ready:
            reasons.append("missing_boss_kill_evidence")
    trash_ready = True
    if str(segment.get("kind") or "") == "trash":
        trash_ready = int_field(row, "trash_pulls", "trash_kills", "trash_packs_cleared") > 0 or bool(row.get("trash_cleared"))
        if not trash_ready:
            reasons.append("missing_trash_evidence")
    context_matches = not any(reason.endswith("_mismatch") for reason in reasons)
    return {
        "report_valid": True,
        "validation_context_matches": context_matches,
        "boss_evidence_ready": boss_ready,
        "trash_evidence_ready": trash_ready,
        "segment_ready": context_matches and boss_ready and trash_ready and not failure_labels and not failure_reason,
        "invalid_reasons": reasons,
    }


def validate_segment_report(report: dict[str, Any], segment: dict[str, Any], scenario: dict[str, Any], load_error: str = "") -> dict[str, Any]:
    reasons = []
    if load_error:
        reasons.append(load_error)
    if not report:
        return {
            "report_valid": False,
            "validation_context_matches": False,
            "boss_evidence_ready": False,
            "segment_ready": False,
            "invalid_reasons": reasons or ["empty_report"],
        }

    schema = str(report.get("schema") or "")
    if schema != "bot_live_validation_report_v1":
        reasons.append("unexpected_report_schema")
    if bool(report.get("timed_out")):
        reasons.append("live_validation_timed_out")
    if int_field(report, "returncode") != 0:
        reasons.append("live_validation_returncode_nonzero")
    failure_labels = report.get("failure_labels") if isinstance(report.get("failure_labels"), list) else []
    failure_reason = str(report.get("failure_reason") or "")
    if failure_labels or failure_reason:
        reasons.append("live_validation_has_failures")

    context = report.get("validation_context") if isinstance(report.get("validation_context"), dict) else {}
    expected_context = {
        "scenario_id": scenario.get("scenario_id") or "",
        "segment_id": segment.get("segment_id") or "",
        "route_node_id": segment.get("route_node_id") or "",
        "route_kind": segment.get("kind") or "",
        "mechanic_profile": segment.get("mechanic_profile") or "",
    }
    context_matches = True
    for key, expected in expected_context.items():
        if expected and str(context.get(key) or "") != str(expected):
            context_matches = False
            reasons.append(f"{key}_mismatch")
    if not context:
        context_matches = False
        reasons.append("missing_validation_context")

    boss_ready = True
    if str(segment.get("kind") or "") == "boss":
        boss_ready = has_boss_kill_evidence(report, scenario)
        if not boss_ready:
            reasons.append("missing_boss_kill_evidence")
    trash_ready = True
    if str(segment.get("kind") or "") == "trash":
        trash_ready = has_trash_evidence(report, scenario)
        if not trash_ready:
            reasons.append("missing_trash_evidence")

    report_valid = not load_error and schema == "bot_live_validation_report_v1" and not bool(report.get("timed_out")) and int_field(report, "returncode") == 0 and not failure_labels and not failure_reason
    return {
        "report_valid": report_valid,
        "validation_context_matches": context_matches,
        "boss_evidence_ready": boss_ready,
        "trash_evidence_ready": trash_ready,
        "segment_ready": report_valid and context_matches and boss_ready and trash_ready,
        "invalid_reasons": reasons,
    }


def build_status(plan: dict[str, Any], report_root: Path) -> dict[str, Any]:
    scenarios = []
    for scenario in plan.get("scenarios") or []:
        scenario_id = str(scenario.get("scenario_id") or "")
        segments = [segment for segment in scenario.get("segments") or [] if segment.get("executable", True)]
        scenario_report_file = scenario_report_path(report_root, scenario_id)
        scenario_report = load_json(scenario_report_file)
        present_segments = []
        existing_segments = []
        missing_segments = []
        invalid_segments = []
        segment_reports = []
        for segment in segments:
            report_path = segment_report_path(segment)
            report, load_error = load_report(report_path)
            validation = validate_segment_report(report, segment, scenario, load_error)
            evidence_source = "segment_report"
            scenario_segment = {}
            if not validation["segment_ready"]:
                scenario_segment = scenario_segment_result(scenario_report, segment)
                scenario_validation = validate_scenario_segment_result(scenario_segment, segment, scenario)
                if scenario_validation["segment_ready"]:
                    validation = scenario_validation
                    evidence_source = "scenario_segment_result"
                    source_live_report = str(scenario_segment.get("source_live_report") or "")
                    if source_live_report:
                        report_path = Path(source_live_report)
            row = {
                "segment_id": segment.get("segment_id") or "",
                "route_node_id": segment.get("route_node_id") or "",
                "label": segment.get("label") or "",
                "mechanic_profile": segment.get("mechanic_profile") or "",
                "report": str(report_path),
                "report_exists": report_path.exists() or bool(scenario_segment),
                "report_valid": validation["report_valid"],
                "validation_context_matches": validation["validation_context_matches"],
                "boss_evidence_ready": validation["boss_evidence_ready"],
                "trash_evidence_ready": validation.get("trash_evidence_ready", True),
                "segment_ready": validation["segment_ready"],
                "invalid_reasons": validation["invalid_reasons"],
                "evidence_source": evidence_source,
                "live_validate_command": segment.get("live_validate_command") or [],
                "live_validate_shell": segment.get("live_validate_shell") or "",
            }
            segment_reports.append(row)
            if row["report_exists"]:
                existing_segments.append(row["segment_id"])
            if row["segment_ready"]:
                present_segments.append(row["segment_id"])
            elif row["report_exists"]:
                invalid_segments.append(row["segment_id"])
            else:
                missing_segments.append(row["segment_id"])

        complete_segment_coverage = bool(scenario_report.get("complete_segment_coverage"))
        clear_complete = bool(scenario_report.get("clear_complete"))
        segment_coverage_ready = bool(segments) and not missing_segments and not invalid_segments
        scenario_report_ready = scenario_report_file.exists()
        full_clear_ready = clear_complete and segment_coverage_ready and (complete_segment_coverage or not segments)

        next_commands = [
            row["live_validate_shell"]
            for row in segment_reports
            if not row["segment_ready"] and row["live_validate_shell"]
        ]
        if (not scenario_report_ready or not full_clear_ready) and scenario.get("scenario_report_shell"):
            next_commands.append(str(scenario["scenario_report_shell"]))

        blockers = []
        if missing_segments:
            blockers.append("missing_segment_live_reports")
        if invalid_segments:
            blockers.append("invalid_segment_live_reports")
        if not scenario_report_ready:
            blockers.append("missing_scenario_report")
        elif not complete_segment_coverage and segments:
            blockers.append("incomplete_segment_coverage")
        if scenario_report_ready and not clear_complete:
            blockers.append("scenario_clear_not_complete")

        scenarios.append(
            {
                "scenario_id": scenario_id,
                "instance": scenario.get("instance") or "",
                "expected_segments": [segment.get("segment_id") or "" for segment in segments],
                "present_segments": present_segments,
                "existing_segments": existing_segments,
                "missing_segments": missing_segments,
                "invalid_segments": invalid_segments,
                "segment_reports": segment_reports,
                "segment_coverage_ready": segment_coverage_ready,
                "scenario_report": str(scenario_report_file),
                "scenario_report_exists": scenario_report_ready,
                "scenario_report_clear_complete": clear_complete,
                "scenario_report_complete_segment_coverage": complete_segment_coverage,
                "full_clear_ready": full_clear_ready,
                "blockers": blockers,
                "next_commands": next_commands,
            }
        )

    blocked = [scenario for scenario in scenarios if not scenario["full_clear_ready"]]
    return {
        "schema": "bot_validation_run_status_v1",
        "scenario_count": len(scenarios),
        "ready_scenarios": sum(1 for scenario in scenarios if scenario["full_clear_ready"]),
        "blocked_scenarios": len(blocked),
        "all_ready": not blocked,
        "scenarios": scenarios,
        "next_commands": [command for scenario in scenarios for command in scenario["next_commands"]],
        "status_hash": stable_hash(scenarios),
        "runtime_ml_control": "disabled_until_live_clear_validation_passes",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Summarize validation run-plan execution status and missing live segment reports.")
    parser.add_argument("--run-plan", type=Path, default=Path("dataset/validation_run_plan/manifest.json"))
    parser.add_argument("--scenario-report-root", type=Path, default=Path("dataset/live_validation_scenario_reports_built"))
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/validation_run_status"))
    args = parser.parse_args()

    status = build_status(load_json(args.run_plan), args.scenario_report_root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "manifest.json", status)
    print(json.dumps(status, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
