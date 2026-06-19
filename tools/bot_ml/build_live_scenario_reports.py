from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .common import read_jsonl, stable_hash, write_json
    from .run_live_bot_validation import trace_entries
except ImportError:
    from common import read_jsonl, stable_hash, write_json
    from run_live_bot_validation import trace_entries


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else {}


def load_live_report(path: Path) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    row: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "report_valid": False,
        "invalid_reason": "",
        "scenario_id": "",
        "segment_id": "",
    }
    if not path.exists():
        row["invalid_reason"] = "missing_live_report"
        return None, row
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        row["invalid_reason"] = "invalid_json"
        return None, row
    if not isinstance(payload, dict):
        row["invalid_reason"] = "live_report_not_object"
        return None, row
    if str(payload.get("schema") or "") != "bot_live_validation_report_v1":
        row["invalid_reason"] = "unexpected_live_report_schema"
        return None, row
    validation_context = payload.get("validation_context") if isinstance(payload.get("validation_context"), dict) else {}
    row.update(
        {
            "report_valid": True,
            "scenario_id": str(validation_context.get("scenario_id") or ""),
            "segment_id": str(validation_context.get("segment_id") or ""),
        }
    )
    payload["source_live_report"] = str(path)
    return payload, row


def load_scenarios(path: Path) -> dict[str, dict[str, Any]]:
    rows = read_jsonl(path / "validation_scenarios.jsonl")
    return {str(row.get("scenario_id") or ""): row for row in rows if row.get("scenario_id")}


def load_routes(path: Path) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in read_jsonl(path / "validation_routes.jsonl"):
        grouped.setdefault(str(row.get("scenario_id") or ""), []).append(row)
    for rows in grouped.values():
        rows.sort(key=lambda row: int(row.get("step") or 0))
    return grouped


def route_by_node(routes: list[dict[str, Any]], route_node_id: str, route_step: int, route_label: str) -> dict[str, Any]:
    for route in routes:
        if route_node_id and str(route.get("route_node_id") or "") == route_node_id:
            return route
    for route in routes:
        if route_step and int(route.get("step") or 0) == route_step:
            return route
    for route in routes:
        if route_label and str(route.get("label") or "") == route_label:
            return route
    return {}


def existing_scenario_report(report: dict[str, Any], scenario_id: str) -> dict[str, Any]:
    scenarios = report.get("scenario_reports") or {}
    if isinstance(scenarios, dict) and isinstance(scenarios.get(scenario_id), dict):
        return dict(scenarios[scenario_id])
    return {}


def action_names(report: dict[str, Any]) -> list[str]:
    trace = report.get("trace") or {}
    entries = trace_entries(trace if isinstance(trace, dict) else {})
    return [str(entry.get("action") or entry.get("situation") or "") for entry in entries if entry.get("action") or entry.get("situation")]


def stage_passed(report: dict[str, Any], stage: str) -> bool:
    for row in report.get("stages") or []:
        if isinstance(row, dict) and row.get("stage") == stage:
            return bool(row.get("passed"))
    return False


def unique_strings(*values: Any) -> list[str]:
    rows: list[str] = []
    for value in values:
        candidates = value if isinstance(value, list) else [value]
        for candidate in candidates:
            text = str(candidate or "")
            if text and text not in rows:
                rows.append(text)
    return rows


def evidence_counts(report: dict[str, Any]) -> dict[str, int]:
    evidence = report.get("evidence") if isinstance(report.get("evidence"), dict) else {}
    counts = evidence.get("validation_evidence_counts") if isinstance(evidence.get("validation_evidence_counts"), dict) else {}
    rows = {str(key): int(value or 0) for key, value in counts.items()}
    legacy = {
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
    for evidence_name, field in legacy.items():
        try:
            rows[evidence_name] = max(rows.get(evidence_name, 0), int(evidence.get(field) or 0))
        except (TypeError, ValueError):
            rows[evidence_name] = rows.get(evidence_name, 0)
    return rows


def missing_evidence(required_evidence: list[str], counts: dict[str, int]) -> list[str]:
    return [name for name in required_evidence if int(counts.get(name) or 0) <= 0]


def sum_evidence_counts(left: dict[str, int], right: dict[str, int]) -> dict[str, int]:
    rows = dict(left)
    for key, value in right.items():
        rows[str(key)] = int(rows.get(str(key), 0)) + int(value or 0)
    return dict(sorted(rows.items()))


def segment_output_name(route: dict[str, Any]) -> str:
    step = int(route.get("step") or 0)
    label = str(route.get("label") or route.get("route_node_id") or "segment")
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in label).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return f"{step:02d}_{slug or 'segment'}"


def expected_segment_ids(routes: list[dict[str, Any]]) -> list[str]:
    return [segment_output_name(route) for route in routes if route.get("kind") in {"trash", "boss"}]


def missing_segments(expected_segments: list[str], source_segments: list[str]) -> list[str]:
    present = set(source_segments)
    return [segment for segment in expected_segments if segment not in present]


def scenario_evidence_mode(validation_context: dict[str, Any], existing: dict[str, Any]) -> str:
    if validation_context.get("segment_id") or validation_context.get("route_node_id"):
        return "route_segment_context"
    if existing:
        return "attached_scenario_report"
    return "generic_live_trace_inference"


def teacher_label_quality(mode: str) -> str:
    if mode == "route_segment_context":
        return "strong"
    if mode == "attached_scenario_report":
        return "medium"
    return "weak"


def merged_teacher_label_quality(modes: list[str], complete_segment_coverage: bool) -> str:
    if "generic_live_trace_inference" in modes:
        return "weak"
    if "route_segment_context" in modes and complete_segment_coverage:
        return "strong"
    if "route_segment_context" in modes or "attached_scenario_report" in modes:
        return "medium"
    return "weak"


def infer_report(report: dict[str, Any], scenario: dict[str, Any], routes: list[dict[str, Any]], existing: dict[str, Any]) -> dict[str, Any]:
    scenario_id = str(scenario.get("scenario_id") or "")
    difficulty = str(scenario.get("difficulty") or "")
    raid = "10" in difficulty or "raid" in difficulty
    actions = action_names(report)
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    evidence = report.get("evidence") if isinstance(report.get("evidence"), dict) else {}
    validation_context = report.get("validation_context") if isinstance(report.get("validation_context"), dict) else {}
    failure_labels = unique_strings(report.get("failure_labels") or [])
    failure_reason = str(report.get("failure_reason") or (failure_labels[0] if failure_labels else ""))
    route_segment_id = str(validation_context.get("segment_id") or "")
    route_node_id = str(validation_context.get("route_node_id") or "")
    route_label = str(validation_context.get("route_label") or "")
    route_kind = str(validation_context.get("route_kind") or "")
    route_step = int(validation_context.get("route_step") or 0)
    mechanic_profile = str(validation_context.get("mechanic_profile") or "")
    route = route_by_node(routes, route_node_id, route_step, route_label)
    segment_required_evidence = [str(row) for row in (route.get("required_evidence") or [])]
    observed_evidence = evidence_counts(report)
    segment_missing_evidence = missing_evidence(segment_required_evidence, observed_evidence)
    evidence_mode = scenario_evidence_mode(validation_context, existing)
    boss_action = "raid_boss_killed" if raid else "boss_killed"
    observed_boss_kills = sum(1 for action in actions if action == boss_action)
    observed_boss_kills = max(observed_boss_kills, int(summary.get("raid_boss_kills") or 0) if raid else 0)
    expected_bosses = int(scenario.get("boss_count") or sum(1 for route in routes if route.get("kind") == "boss"))
    expected_segments = expected_segment_ids(routes)
    trash_actions = sum(1 for action in actions if action in {"trash_action", "trash_heal", "material_farming_source"} or "trash" in action)
    trash_pulls = max(int(existing.get("trash_pulls") or 0), trash_actions, int(summary.get("trash_pulls") or 0), int(evidence.get("trash_pulls") or 0))

    full_clear_stage = "full_blackwing_descent_clear" if raid else "full_stonecore_clear"
    boss_stage = "raid_boss" if raid else "dungeon_boss"
    trash_stage = "raid_trash" if raid else "normal_dungeon_trash"
    boss_kills = max(int(existing.get("raid_boss_kills" if raid else "boss_kills") or 0), observed_boss_kills)
    source_segments = unique_strings(route_segment_id)
    missing_segment_rows = missing_segments(expected_segments, source_segments)
    complete_segment_coverage = bool(expected_segments) and not missing_segment_rows
    segment_clear_ready = evidence_mode != "route_segment_context" or not expected_segments or complete_segment_coverage
    segmented_evidence = evidence_mode == "route_segment_context" and bool(expected_segments)
    clear_complete = bool(existing.get("clear_complete")) or stage_passed(report, full_clear_stage) or (segment_clear_ready and expected_bosses > 0 and boss_kills >= expected_bosses and int(evidence.get("failures") or 0) == 0)
    if segmented_evidence:
        clear_complete = segment_clear_ready and expected_bosses > 0 and boss_kills >= expected_bosses and int(evidence.get("failures") or 0) == 0

    source_live_report = str(report.get("source_live_report") or "")
    segment_results = []
    if route_segment_id or route_node_id:
        segment_results.append(
            {
                "segment_id": route_segment_id,
                "route_node_id": route_node_id,
                "route_label": route_label,
                "route_kind": route_kind,
                "route_step": route_step,
                "mechanic_profile": mechanic_profile,
                "boss_kills": boss_kills,
                "raid_boss_kills": boss_kills if raid else 0,
                "trash_pulls": trash_pulls,
                "clear_complete": clear_complete,
                "failure_labels": failure_labels,
                "failure_reason": failure_reason,
                "required_evidence": segment_required_evidence,
                "evidence_counts": observed_evidence,
                "missing_evidence": segment_missing_evidence,
                "evidence_complete": not segment_missing_evidence,
                "source_live_report": source_live_report,
            }
        )
    expected_evidence = unique_strings(scenario.get("required_evidence") or [], *[route.get("required_evidence") or [] for route in routes])
    missing_scenario_evidence = missing_evidence(expected_evidence, observed_evidence)
    row = {
        "schema": "bot_live_scenario_report_v1",
        "scenario_id": scenario_id,
        "instance": scenario.get("instance") or "",
        "map_id": int(scenario.get("map_id") or 0),
        "difficulty": difficulty,
        "prepared_group": bool(existing.get("prepared_group") or existing.get("group_ready") or scenario.get("provisioning_ready")),
        "trash_pulls": trash_pulls,
        "trash_cleared": bool(existing.get("trash_cleared")) or stage_passed(report, trash_stage) or trash_pulls > 0,
        "boss_kills": boss_kills,
        "raid_boss_kills": boss_kills if raid else 0,
        "expected_bosses": expected_bosses,
        "boss_stage_passed": bool(existing.get("boss_stage_passed")) or stage_passed(report, boss_stage) or boss_kills > 0,
        "clear_complete": clear_complete,
        "source_live_report": source_live_report,
        "source_live_reports": [source_live_report] if source_live_report else [],
        "expected_segments": expected_segments,
        "source_segments": source_segments,
        "missing_segments": missing_segment_rows,
        "complete_segment_coverage": complete_segment_coverage,
        "source_route_nodes": unique_strings(route_node_id),
        "source_route_labels": unique_strings(route_label),
        "source_mechanic_profiles": unique_strings(mechanic_profile),
        "required_evidence": expected_evidence,
        "evidence_counts": observed_evidence,
        "missing_evidence": missing_scenario_evidence,
        "evidence_complete": not missing_scenario_evidence,
        "segment_results": segment_results,
        "source_scenario_report_attached": bool(existing),
        "scenario_evidence_mode": evidence_mode,
        "scenario_evidence_modes": [evidence_mode],
        "teacher_label_quality": merged_teacher_label_quality([evidence_mode], complete_segment_coverage),
        "failure_labels": failure_labels,
        "failure_reason": failure_reason,
        "ml_training_label": "failed_teacher_attempt" if failure_labels else ("candidate_teacher_label" if merged_teacher_label_quality([evidence_mode], complete_segment_coverage) in {"strong", "medium"} else "weak_inferred_label"),
        "source_trace_entries": int(report.get("trace_entries") or 0),
        "runtime_ml_control": "disabled_until_live_clear_validation_passes",
    }
    row["report_hash"] = stable_hash(row)[:16]
    return row


def merge_report_rows(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    if not left:
        return dict(right)
    merged = dict(left)
    expected_bosses = max(int(left.get("expected_bosses") or 0), int(right.get("expected_bosses") or 0))
    boss_kills = min(expected_bosses or 999, int(left.get("boss_kills") or 0) + int(right.get("boss_kills") or 0))
    raid_boss_kills = min(expected_bosses or 999, int(left.get("raid_boss_kills") or 0) + int(right.get("raid_boss_kills") or 0))
    source_reports = []
    for row in [left, right]:
        source = row.get("source_live_report")
        if source and source not in source_reports:
            source_reports.append(str(source))
        for extra in row.get("source_live_reports") or []:
            if extra and extra not in source_reports:
                source_reports.append(str(extra))
    source_segments = unique_strings(left.get("source_segments") or [], right.get("source_segments") or [])
    expected_segments = unique_strings(left.get("expected_segments") or [], right.get("expected_segments") or [])
    missing_segment_rows = missing_segments(expected_segments, source_segments)
    complete_segment_coverage = bool(expected_segments) and not missing_segment_rows
    source_route_nodes = unique_strings(left.get("source_route_nodes") or [], right.get("source_route_nodes") or [])
    source_route_labels = unique_strings(left.get("source_route_labels") or [], right.get("source_route_labels") or [])
    source_mechanic_profiles = unique_strings(left.get("source_mechanic_profiles") or [], right.get("source_mechanic_profiles") or [])
    required_evidence = unique_strings(left.get("required_evidence") or [], right.get("required_evidence") or [])
    evidence_count_rows = sum_evidence_counts(
        {str(key): int(value or 0) for key, value in (left.get("evidence_counts") or {}).items()},
        {str(key): int(value or 0) for key, value in (right.get("evidence_counts") or {}).items()},
    )
    missing_evidence_rows = missing_evidence(required_evidence, evidence_count_rows)
    segment_results = list(left.get("segment_results") or []) + list(right.get("segment_results") or [])
    evidence_modes = unique_strings(left.get("scenario_evidence_modes") or left.get("scenario_evidence_mode") or [], right.get("scenario_evidence_modes") or right.get("scenario_evidence_mode") or [])
    failure_labels = unique_strings(left.get("failure_labels") or [], right.get("failure_labels") or [])
    failure_reason = str(left.get("failure_reason") or right.get("failure_reason") or (failure_labels[0] if failure_labels else ""))
    label_quality = merged_teacher_label_quality(evidence_modes, complete_segment_coverage)
    segmented_evidence = "route_segment_context" in evidence_modes and bool(expected_segments)
    clear_complete = bool(left.get("clear_complete") or right.get("clear_complete"))
    if segmented_evidence:
        clear_complete = complete_segment_coverage and max(boss_kills, raid_boss_kills) >= expected_bosses
    else:
        clear_complete = clear_complete or (expected_bosses > 0 and max(boss_kills, raid_boss_kills) >= expected_bosses)
    if failure_labels or failure_reason:
        clear_complete = False
    merged.update(
        {
            "prepared_group": bool(left.get("prepared_group") or right.get("prepared_group")),
            "trash_pulls": int(left.get("trash_pulls") or 0) + int(right.get("trash_pulls") or 0),
            "trash_cleared": bool(left.get("trash_cleared") or right.get("trash_cleared")),
            "boss_kills": boss_kills,
            "raid_boss_kills": raid_boss_kills,
            "expected_bosses": expected_bosses,
            "boss_stage_passed": bool(left.get("boss_stage_passed") or right.get("boss_stage_passed") or boss_kills > 0 or raid_boss_kills > 0),
            "clear_complete": clear_complete,
            "source_live_report": source_reports[0] if source_reports else "",
            "source_live_reports": source_reports,
            "expected_segments": expected_segments,
            "source_segments": source_segments,
            "missing_segments": missing_segment_rows,
            "complete_segment_coverage": complete_segment_coverage,
            "source_route_nodes": source_route_nodes,
            "source_route_labels": source_route_labels,
            "source_mechanic_profiles": source_mechanic_profiles,
            "required_evidence": required_evidence,
            "evidence_counts": evidence_count_rows,
            "missing_evidence": missing_evidence_rows,
            "evidence_complete": not missing_evidence_rows,
            "segment_results": segment_results,
            "source_scenario_report_attached": bool(left.get("source_scenario_report_attached") or right.get("source_scenario_report_attached")),
            "scenario_evidence_mode": evidence_modes[0] if evidence_modes else "",
            "scenario_evidence_modes": evidence_modes,
            "teacher_label_quality": label_quality,
            "failure_labels": failure_labels,
            "failure_reason": failure_reason,
            "ml_training_label": "failed_teacher_attempt" if failure_labels else ("candidate_teacher_label" if label_quality in {"strong", "medium"} else "weak_inferred_label"),
            "source_trace_entries": int(left.get("source_trace_entries") or 0) + int(right.get("source_trace_entries") or 0),
        }
    )
    merged["report_hash"] = stable_hash(merged)[:16]
    return merged


def build_reports_from_live_reports(live_reports: list[dict[str, Any]], scenario_dir: Path, scenario_ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
    scenarios = load_scenarios(scenario_dir)
    routes = load_routes(scenario_dir)
    selected = scenario_ids or sorted(scenarios)
    reports: dict[str, dict[str, Any]] = {}
    for scenario_id in selected:
        scenario = scenarios.get(scenario_id)
        if not scenario:
            continue
        merged: dict[str, Any] = {}
        used_live_report = False
        for live_report in live_reports:
            validation_context = live_report.get("validation_context") if isinstance(live_report.get("validation_context"), dict) else {}
            context_scenario_id = str(validation_context.get("scenario_id") or "")
            if context_scenario_id and context_scenario_id != scenario_id:
                continue
            used_live_report = True
            inferred = infer_report(live_report, scenario, routes.get(scenario_id, []), existing_scenario_report(live_report, scenario_id))
            merged = merge_report_rows(merged, inferred)
        if used_live_report:
            reports[scenario_id] = merged
    return reports


def build_reports(live_report: dict[str, Any], scenario_dir: Path, scenario_ids: list[str] | None = None) -> dict[str, dict[str, Any]]:
    return build_reports_from_live_reports([live_report], scenario_dir, scenario_ids)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build per-scenario Stonecore/BWD live reports from bot-live-validate output.")
    parser.add_argument("--live-report", type=Path, action="append", default=[], help="Input bot-live-validate report. May be passed multiple times to aggregate segmented scenario progress.")
    parser.add_argument("--validation-scenario-dir", type=Path, default=Path("dataset/validation_scenarios"))
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/live_validation_scenario_reports_built"))
    parser.add_argument("--scenario-id", action="append", default=[])
    args = parser.parse_args()

    live_report_paths = args.live_report or [Path("dataset/live_validation/report.json")]
    live_reports = []
    input_reports = []
    for path in live_report_paths:
        live_report, input_row = load_live_report(path)
        input_reports.append(input_row)
        if live_report:
            live_reports.append(live_report)
    reports = build_reports_from_live_reports(live_reports, args.validation_scenario_dir, args.scenario_id or None)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    selected_scenarios = args.scenario_id or sorted(load_scenarios(args.validation_scenario_dir))
    for scenario_id in selected_scenarios:
        stale_report = args.output_dir / f"{scenario_id}.json"
        if scenario_id not in reports and stale_report.exists():
            stale_report.unlink()
    for scenario_id, report in reports.items():
        write_json(args.output_dir / f"{scenario_id}.json", report)
    summary = {
        "schema": "bot_live_scenario_reports_manifest_v1",
        "requested_live_reports": [str(path) for path in live_report_paths],
        "source_live_reports": [row["path"] for row in input_reports if row["report_valid"]],
        "invalid_live_reports": [row for row in input_reports if not row["report_valid"]],
        "valid_live_report_count": sum(1 for row in input_reports if row["report_valid"]),
        "invalid_live_report_count": sum(1 for row in input_reports if not row["report_valid"]),
        "validation_scenario_dir": str(args.validation_scenario_dir),
        "scenario_count": len(reports),
        "scenarios": sorted(reports),
        "clear_complete": {scenario_id: bool(report.get("clear_complete")) for scenario_id, report in sorted(reports.items())},
        "runtime_ml_control": "disabled_until_live_clear_validation_passes",
    }
    write_json(args.output_dir / "manifest.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
