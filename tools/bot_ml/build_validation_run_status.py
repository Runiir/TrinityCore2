from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .common import stable_hash, write_json
    from .run_live_bot_validation import scoped_event_evidence, scoped_validation_evidence_counts, trace_entries
except ImportError:
    from common import stable_hash, write_json
    from run_live_bot_validation import scoped_event_evidence, scoped_validation_evidence_counts, trace_entries


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


def evidence_counts(report: dict[str, Any], segment: dict[str, Any] | None = None) -> dict[str, int]:
    evidence = report.get("evidence") if isinstance(report.get("evidence"), dict) else {}
    if isinstance(report.get("evidence_counts"), dict):
        return {str(key): int(value or 0) for key, value in report["evidence_counts"].items()}
    if segment:
        trace = report.get("trace") if isinstance(report.get("trace"), dict) else {}
        return scoped_validation_evidence_counts(
            trace_entries(trace),
            str(segment.get("route_node_id") or ""),
            int(segment.get("route_generation") or 0),
        )
    counts = evidence.get("validation_evidence_counts") if isinstance(evidence.get("validation_evidence_counts"), dict) else {}
    rows = {str(key): int(value or 0) for key, value in counts.items()}
    aliases = {
        "role_assignments": "role_assignment_evidence",
        "party_formation": "group_formation_evidence",
        "raid_formation": "group_formation_evidence",
        "pulls": "trash_pulls",
        "target_priority": "target_priority_evidence",
        "interrupts": "interrupt_evidence",
        "healer_assignments": "healer_assignment_evidence",
        "tank_positioning": "tank_positioning_evidence",
        "regrouping": "regrouping_evidence",
        "recovery": "recovery_evidence",
        "instance_reset": "instance_reset_evidence",
    }
    for name, field in aliases.items():
        rows[name] = max(rows.get(name, 0), int(evidence.get(field) or 0))
    return rows


def missing_required_evidence(segment: dict[str, Any], report: dict[str, Any]) -> list[str]:
    required = [str(row) for row in (segment.get("required_evidence") or [])]
    counts = evidence_counts(report, segment)
    return [name for name in required if int(counts.get(name) or 0) <= 0]


def is_raid_scenario(scenario: dict[str, Any]) -> bool:
    scenario_id = str(scenario.get("scenario_id") or "").lower()
    difficulty = str(scenario.get("difficulty") or "").lower()
    instance = str(scenario.get("instance") or "").lower()
    return "raid" in difficulty or "10" in difficulty or "blackwing" in scenario_id or "blackwing" in instance


def expected_boss_stage(scenario: dict[str, Any]) -> str:
    return "raid_boss" if is_raid_scenario(scenario) else "dungeon_boss"


def expected_trash_stage(scenario: dict[str, Any]) -> str:
    return "raid_trash" if is_raid_scenario(scenario) else "normal_dungeon_trash"


def scoped_evidence(report: dict[str, Any], key: str, actions: set[str]) -> list[dict[str, Any]]:
    evidence = report.get("evidence") if isinstance(report.get("evidence"), dict) else {}
    rows = evidence.get(key) if isinstance(evidence.get(key), list) else None
    if rows is not None:
        return [row for row in rows if isinstance(row, dict)]
    trace = report.get("trace") if isinstance(report.get("trace"), dict) else {}
    entries = trace_entries(trace)
    if key == "real_boss_kill_evidence":
        entries = [entry for entry in entries if str(entry.get("result") or "") == "ok" and int(entry.get("target_id") or 0) > 0]
    return scoped_event_evidence(entries, actions)


def scope_matches(rows: list[dict[str, Any]], segment: dict[str, Any]) -> bool:
    node_id = str(segment.get("route_node_id") or "")
    generation = int(segment.get("route_generation") or 0)
    return any(
        isinstance(row, dict)
        and str(row.get("route_node_id") or "") == node_id
        and int(row.get("route_generation") or 0) == generation
        for row in rows
    )


def has_boss_kill_evidence(report: dict[str, Any], segment: dict[str, Any]) -> bool:
    return scope_matches(scoped_evidence(report, "real_boss_kill_evidence", {"boss_killed", "raid_boss_killed"}), segment)


def has_terminal_evidence(report: dict[str, Any], segment: dict[str, Any]) -> bool:
    return scope_matches(scoped_evidence(report, "route_terminal_evidence", {"validation_route_terminal"}), segment)


def has_trash_evidence(report: dict[str, Any], segment: dict[str, Any]) -> bool:
    return int(evidence_counts(report, segment).get("pulls") or 0) > 0


def has_valid_full_clear_claim(report: dict[str, Any], segments: list[dict[str, Any]]) -> bool:
    if not bool(report.get("clear_complete")):
        return False
    if not bool(report.get("completion_claim_valid")):
        return False
    mode = str(report.get("completion_evidence_mode") or report.get("scenario_evidence_mode") or "")
    if mode not in {"uninterrupted_live_clear", "attached_uninterrupted_live_clear"}:
        return False
    terminal_rows = report.get("route_terminal_evidence") if isinstance(report.get("route_terminal_evidence"), list) else []
    boss_rows = report.get("real_boss_kill_evidence") if isinstance(report.get("real_boss_kill_evidence"), list) else []
    return (
        bool(segments)
        and all(scope_matches(terminal_rows, segment) for segment in segments)
        and all(str(segment.get("kind") or "") != "boss" or scope_matches(boss_rows, segment) for segment in segments)
        and not report.get("forbidden_completion_assists")
        and not report.get("failure_labels")
        and not report.get("failure_reason")
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
        if int(row.get("route_generation") or 0) != int(segment.get("route_generation") or 0):
            continue
        return row
    return {}


def validate_scenario_segment_result(row: dict[str, Any], segment: dict[str, Any], scenario: dict[str, Any], scenario_report: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    warnings = []
    scenario_terminal_rows = scenario_report.get("route_terminal_evidence") if isinstance(scenario_report.get("route_terminal_evidence"), list) else []
    scenario_boss_rows = scenario_report.get("real_boss_kill_evidence") if isinstance(scenario_report.get("real_boss_kill_evidence"), list) else []
    if not row:
        return {
            "report_valid": False,
            "validation_context_matches": False,
            "boss_evidence_ready": False,
            "segment_ready": False,
            "invalid_reasons": ["missing_scenario_segment_result"],
            "warnings": [],
        }
    if str(row.get("route_kind") or "") != str(segment.get("kind") or ""):
        reasons.append("route_kind_mismatch")
    if str(row.get("mechanic_profile") or "") != str(segment.get("mechanic_profile") or ""):
        reasons.append("mechanic_profile_mismatch")
    expected_route_node_id = str(segment.get("route_node_id") or "")
    actual_route_node_id = str(row.get("route_node_id") or "")
    if expected_route_node_id != actual_route_node_id:
        reasons.append("route_node_id_mismatch")
    if int(row.get("route_generation") or 0) != int(segment.get("route_generation") or 0):
        reasons.append("route_generation_mismatch")
    failure_labels = row.get("failure_labels") if isinstance(row.get("failure_labels"), list) else []
    failure_reason = str(row.get("failure_reason") or "")
    if failure_labels or failure_reason:
        reasons.append("scenario_segment_has_failures")
    if row.get("forbidden_completion_assists") or scenario_report.get("forbidden_completion_assists"):
        reasons.append("forced_or_teacher_kill_evidence")
    boss_ready = True
    if str(segment.get("kind") or "") == "boss":
        boss_ready = scope_matches(scenario_boss_rows, segment)
        if not boss_ready:
            reasons.append("missing_boss_kill_evidence")
    trash_ready = True
    if str(segment.get("kind") or "") == "trash":
        trash_ready = int(evidence_counts(row, segment).get("pulls") or 0) > 0
        if not trash_ready:
            reasons.append("missing_trash_evidence")
    missing_evidence = missing_required_evidence(segment, row)
    reasons.extend(f"missing_{name}_evidence" for name in missing_evidence)
    terminal_ready = scope_matches(scenario_terminal_rows, segment)
    if not terminal_ready:
        reasons.append("missing_node_terminal_evidence")
    context_matches = not any(reason.endswith("_mismatch") for reason in reasons)
    return {
        "report_valid": True,
        "validation_context_matches": context_matches,
        "boss_evidence_ready": boss_ready,
        "trash_evidence_ready": trash_ready,
        "missing_evidence": missing_evidence,
        "evidence_counts": evidence_counts(row),
        "evidence_complete": not missing_evidence,
        "segment_ready": context_matches and terminal_ready and boss_ready and trash_ready and not missing_evidence and not failure_labels and not failure_reason and not row.get("forbidden_completion_assists") and not scenario_report.get("forbidden_completion_assists"),
        "invalid_reasons": reasons,
        "warnings": warnings,
    }


def validate_segment_report(report: dict[str, Any], segment: dict[str, Any], scenario: dict[str, Any], load_error: str = "") -> dict[str, Any]:
    reasons = []
    warnings = []
    if load_error:
        reasons.append(load_error)
    if not report:
        missing_evidence = [str(row) for row in (segment.get("required_evidence") or [])]
        return {
            "report_valid": False,
            "validation_context_matches": False,
            "boss_evidence_ready": False,
            "trash_evidence_ready": False,
            "missing_evidence": missing_evidence,
            "evidence_counts": {},
            "evidence_complete": not missing_evidence,
            "segment_ready": False,
            "invalid_reasons": reasons or ["empty_report"],
            "warnings": warnings,
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
    evidence = report.get("evidence") if isinstance(report.get("evidence"), dict) else {}
    forbidden_assists = evidence.get("forbidden_completion_assists") if isinstance(evidence.get("forbidden_completion_assists"), list) else []
    if forbidden_assists:
        reasons.append("forced_or_teacher_kill_evidence")

    context = report.get("validation_context") if isinstance(report.get("validation_context"), dict) else {}
    expected_context = {
        "scenario_id": scenario.get("scenario_id") or "",
        "segment_id": segment.get("segment_id") or "",
        "route_node_id": segment.get("route_node_id") or "",
        "route_kind": segment.get("kind") or "",
        "route_generation": segment.get("route_generation") or 0,
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
        boss_ready = has_boss_kill_evidence(report, segment)
        if not boss_ready:
            reasons.append("missing_boss_kill_evidence")
    trash_ready = True
    if str(segment.get("kind") or "") == "trash":
        trash_ready = has_trash_evidence(report, segment)
        if not trash_ready:
            reasons.append("missing_trash_evidence")
    missing_evidence = missing_required_evidence(segment, report)
    reasons.extend(f"missing_{name}_evidence" for name in missing_evidence)
    terminal_ready = has_terminal_evidence(report, segment)
    if not terminal_ready:
        reasons.append("missing_node_terminal_evidence")

    report_valid = not load_error and schema == "bot_live_validation_report_v1" and not bool(report.get("timed_out")) and int_field(report, "returncode") == 0 and not failure_labels and not failure_reason and not forbidden_assists
    return {
        "report_valid": report_valid,
        "validation_context_matches": context_matches,
        "boss_evidence_ready": boss_ready,
        "trash_evidence_ready": trash_ready,
        "missing_evidence": missing_evidence,
        "evidence_counts": evidence_counts(report, segment),
        "evidence_complete": not missing_evidence,
        "segment_ready": report_valid and context_matches and terminal_ready and boss_ready and trash_ready and not missing_evidence,
        "invalid_reasons": reasons,
        "warnings": warnings,
    }


def build_status(plan: dict[str, Any], report_root: Path) -> dict[str, Any]:
    scenarios = []
    for scenario in plan.get("scenarios") or []:
        scenario_id = str(scenario.get("scenario_id") or "")
        segments = [dict(segment) for segment in scenario.get("segments") or [] if segment.get("executable", True)]
        for generation, segment in enumerate(segments, 1):
            segment["route_generation"] = int(segment.get("route_generation") or generation)
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
                scenario_validation = validate_scenario_segment_result(scenario_segment, segment, scenario, scenario_report)
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
                "required_evidence": segment.get("required_evidence") or [],
                "evidence_counts": validation.get("evidence_counts") or {},
                "missing_evidence": validation.get("missing_evidence") or [],
                "evidence_complete": validation.get("evidence_complete", True),
                "segment_ready": validation["segment_ready"],
                "invalid_reasons": validation["invalid_reasons"],
                "warnings": validation.get("warnings") or [],
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
        clear_complete = has_valid_full_clear_claim(scenario_report, segments)
        segment_coverage_ready = bool(segments) and not missing_segments and not invalid_segments
        scenario_report_ready = scenario_report_file.exists()
        full_clear_ready = clear_complete and segment_coverage_ready and (complete_segment_coverage or not segments)

        segment_rerun_commands = [
            row["live_validate_shell"]
            for row in segment_reports
            if not row["segment_ready"] and row["live_validate_shell"]
        ]
        full_clear_command = ""
        if not clear_complete and scenario.get("live_validate_shell"):
            full_clear_command = str(scenario["live_validate_shell"])
        scenario_report_command = ""
        if (not scenario_report_ready or not full_clear_ready) and scenario.get("scenario_report_shell"):
            scenario_report_command = str(scenario["scenario_report_shell"])

        next_commands = list(segment_rerun_commands)
        for command in [full_clear_command, scenario_report_command]:
            if command and command not in next_commands:
                next_commands.append(command)

        blockers = []
        if missing_segments:
            blockers.append("missing_segment_live_reports")
        if invalid_segments:
            blockers.append("invalid_segment_live_reports")
        if any(row.get("missing_evidence") for row in segment_reports):
            blockers.append("missing_segment_required_evidence")
        if not scenario_report_ready:
            blockers.append("missing_scenario_report")
        elif not complete_segment_coverage and segments:
            blockers.append("incomplete_segment_coverage")
        if scenario_report_ready and not clear_complete:
            blockers.append("scenario_clear_not_complete")
            for blocker in scenario_report.get("clear_complete_blockers") or []:
                blocker_text = str(blocker or "")
                if blocker_text and blocker_text not in blockers:
                    blockers.append(blocker_text)
            if bool(scenario_report.get("clear_complete")):
                blockers.append("invalid_full_clear_completion_claim")

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
                "validation_next_commands": {
                    "segment_reruns": segment_rerun_commands,
                    "uninterrupted_full_clear": full_clear_command,
                    "scenario_report_rebuild": scenario_report_command,
                    "ordered": next_commands,
                },
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
        "runtime_ml_control": "offline_shadow_only",
        "control_eligible": False,
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
