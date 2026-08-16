from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .common import read_jsonl, stable_hash, write_json
    from .live_validation_session import verify_report_acceptance
    from .run_live_bot_validation import confirmed_boss_death_event, forbidden_completion_assists, scoped_event_evidence, scoped_validation_evidence_counts, strict_manifest_evidence, trace_entries
except ImportError:
    from common import read_jsonl, stable_hash, write_json
    from live_validation_session import verify_report_acceptance
    from run_live_bot_validation import confirmed_boss_death_event, forbidden_completion_assists, scoped_event_evidence, scoped_validation_evidence_counts, strict_manifest_evidence, trace_entries


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
        for generation, row in enumerate(rows, 1):
            row["route_generation"] = generation
    return grouped


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
            return "missing" in row and not [value for value in (row.get("missing") or []) if value]
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
    return [segment_output_name(route) for route in routes]


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


def attached_full_clear_valid(existing: dict[str, Any], routes: list[dict[str, Any]]) -> bool:
    mode = str(existing.get("completion_evidence_mode") or existing.get("scenario_evidence_mode") or "")
    strict = strict_manifest_evidence(existing, {"routes": routes})
    segment_results = {
        (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0)): row
        for row in (existing.get("segment_results") or [])
        if isinstance(row, dict)
    }
    segment_evidence_complete = all(
        (row := segment_results.get((str(route.get("route_node_id") or ""), int(route.get("route_generation") or 0)))) is not None
        and bool(row.get("terminal_evidence"))
        and (str(route.get("kind") or "") != "boss" or bool(row.get("real_boss_kill_evidence")))
        and not row.get("failure_labels")
        and not row.get("failure_reason")
        and not row.get("forbidden_completion_assists")
        and not missing_evidence(
            [str(name) for name in (route.get("required_evidence") or [])],
            {str(name): int(value or 0) for name, value in (row.get("evidence_counts") or {}).items()},
        )
        for route in routes
    )
    return (
        mode in {"uninterrupted_live_clear", "attached_uninterrupted_live_clear"}
        and [str(row) for row in (existing.get("expected_segments") or [])] == expected_segment_ids(routes)
        and not strict["missing_terminal_route_nodes"]
        and not strict["missing_boss_route_nodes"]
        and not existing.get("forbidden_completion_assists")
        and not existing.get("failure_labels")
        and not existing.get("failure_reason")
        and segment_evidence_complete
    )


def completion_blockers(
    *,
    clear_complete: bool,
    segmented_evidence: bool,
    expected_bosses: int,
    boss_kills: int,
    evidence_complete: bool,
    failure_labels: list[str],
    failure_reason: str,
    full_clear_signal: bool,
) -> list[str]:
    if clear_complete:
        return []
    blockers: list[str] = []
    if segmented_evidence:
        blockers.append("segment_evidence_debug_only")
    if not full_clear_signal:
        blockers.append("missing_uninterrupted_full_clear_report")
    if expected_bosses > 0 and boss_kills < expected_bosses:
        blockers.append("missing_required_boss_kills")
    if not evidence_complete:
        blockers.append("missing_required_evidence")
    if failure_labels or failure_reason:
        blockers.append("failure_labels_present")
    return blockers


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
    entries = trace_entries(report.get("trace") if isinstance(report.get("trace"), dict) else {})
    evidence = report.get("evidence") if isinstance(report.get("evidence"), dict) else {}
    session = report.get("session") if isinstance(report.get("session"), dict) else {}
    heroic_admission_verified = bool(session.get("heroic_admission_verified"))
    validation_context = report.get("validation_context") if isinstance(report.get("validation_context"), dict) else {}
    failure_labels = unique_strings(report.get("failure_labels") or [])
    failure_reason = str(report.get("failure_reason") or (failure_labels[0] if failure_labels else ""))
    source_acceptance = verify_report_acceptance(report)
    route_segment_id = str(validation_context.get("segment_id") or "")
    route_node_id = str(validation_context.get("route_node_id") or "")
    route_label = str(validation_context.get("route_label") or "")
    mechanic_profile = str(validation_context.get("mechanic_profile") or "")
    observed_evidence = evidence_counts(report)
    evidence_mode = scenario_evidence_mode(validation_context, existing)
    expected_bosses = sum(1 for route in routes if route.get("kind") == "boss")
    expected_segments = expected_segment_ids(routes)
    expected_route_evidence = [
        {
            "segment_id": segment_output_name(expected_route),
            "route_node_id": str(expected_route.get("route_node_id") or ""),
            "route_generation": int(expected_route.get("route_generation") or 0),
            "route_kind": str(expected_route.get("kind") or ""),
        }
        for expected_route in routes
    ]
    expected_route_scopes = {(row["route_node_id"], row["route_generation"]) for row in expected_route_evidence}
    expected_boss_scopes = {
        (row["route_node_id"], row["route_generation"])
        for row in expected_route_evidence
        if row["route_kind"] == "boss"
    }
    attached_full_clear = attached_full_clear_valid(existing, routes)
    attached_segment_results = {
        (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0)): row
        for row in (existing.get("segment_results") or [])
        if attached_full_clear and isinstance(row, dict)
    }
    scoped_counts_by_scope = {
        (row["route_node_id"], row["route_generation"]): sum_evidence_counts(
            scoped_validation_evidence_counts(entries, row["route_node_id"], row["route_generation"]),
            {
                str(name): int(value or 0)
                for name, value in (
                    attached_segment_results.get((row["route_node_id"], row["route_generation"]), {}).get("evidence_counts") or {}
                ).items()
            },
        )
        for row in expected_route_evidence
    }
    route_evidence_complete = all(
        not missing_evidence(
            [str(name) for name in (expected_route.get("required_evidence") or [])],
            scoped_counts_by_scope[(str(expected_route.get("route_node_id") or ""), int(expected_route.get("route_generation") or 0))],
        )
        for expected_route in routes
    )
    route_manifest = report.get("validation_route_manifest") if isinstance(report.get("validation_route_manifest"), dict) else {}
    route_manifest_scenario_id = str(route_manifest.get("scenario_id") or "")
    manifest_expected_segments = [str(row) for row in (route_manifest.get("expected_segments") or [])]
    route_terminal_evidence = [
        row
        for row in [
            *scoped_event_evidence(entries, {"validation_route_terminal"}),
            *[row for row in (evidence.get("route_terminal_evidence") or []) if isinstance(row, dict)],
            *([row for row in (existing.get("route_terminal_evidence") or []) if isinstance(row, dict)] if attached_full_clear else []),
        ]
        if (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0)) in expected_route_scopes
    ]
    route_terminal_evidence = [
        {"route_node_id": node_id, "route_generation": generation}
        for node_id, generation in sorted({(str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0)) for row in route_terminal_evidence})
    ]
    real_boss_kill_evidence = [
        row
        for row in [
            *scoped_event_evidence(
                [entry for entry in entries if confirmed_boss_death_event(entry)],
                {"boss_killed", "raid_boss_killed"},
            ),
            *[row for row in (evidence.get("real_boss_kill_evidence") or []) if isinstance(row, dict)],
            *([row for row in (existing.get("real_boss_kill_evidence") or []) if isinstance(row, dict)] if attached_full_clear else []),
        ]
        if (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0)) in expected_boss_scopes
    ]
    real_boss_kill_evidence = [
        {"route_node_id": node_id, "route_generation": generation}
        for node_id, generation in sorted({(str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0)) for row in real_boss_kill_evidence})
    ]
    forbidden_assists = forbidden_completion_assists(entries)
    strict_evidence = strict_manifest_evidence(
        {"route_terminal_evidence": route_terminal_evidence, "real_boss_kill_evidence": real_boss_kill_evidence},
        {"routes": routes},
    )
    manifest_route_scopes = [
        (str(row.get("route_node_id") or ""), int(row.get("route_generation") or generation), str(row.get("kind") or ""))
        for generation, row in enumerate(route_manifest.get("routes") or [], 1)
        if isinstance(row, dict)
    ]
    expected_manifest_scopes = [(row["route_node_id"], row["route_generation"], row["route_kind"]) for row in expected_route_evidence]
    manifest_full_clear = (
        bool(source_acceptance["accepted"])
        and str(report.get("completion_reason") or "") == "validation_route_manifest_complete"
        and route_manifest_scenario_id == scenario_id
        and bool(route_manifest.get("routes"))
        and manifest_expected_segments == expected_segments
        and manifest_route_scopes == expected_manifest_scopes
        and not route_node_id
        and not route_segment_id
        and not strict_evidence["missing_terminal_route_nodes"]
        and not strict_evidence["missing_boss_route_nodes"]
        and not forbidden_assists
        and not failure_labels
        and not failure_reason
        and (difficulty != "heroic_5man" or heroic_admission_verified)
    )
    observed_boss_kills = len(real_boss_kill_evidence)
    trash_pulls = sum(
        int(scoped_counts_by_scope[(row["route_node_id"], row["route_generation"])].get("pulls") or 0)
        for row in expected_route_evidence
        if row["route_kind"] == "trash"
    )
    expected_evidence = unique_strings(scenario.get("required_evidence") or [], *[route.get("required_evidence") or [] for route in routes])
    missing_scenario_evidence = missing_evidence(expected_evidence, observed_evidence)
    evidence_complete = not missing_scenario_evidence

    boss_stage = "raid_boss" if raid else "dungeon_boss"
    trash_stage = "raid_trash" if raid else "normal_dungeon_trash"
    boss_kills = observed_boss_kills
    terminal_scopes = {
        (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0))
        for row in route_terminal_evidence
    }
    source_segments = [
        segment_output_name(expected_route)
        for expected_route in routes
        if (str(expected_route.get("route_node_id") or ""), int(expected_route.get("route_generation") or 0)) in terminal_scopes
    ]
    missing_segment_rows = missing_segments(expected_segments, source_segments)
    complete_segment_coverage = bool(expected_segments) and not missing_segment_rows
    segmented_evidence = evidence_mode == "route_segment_context" and bool(expected_segments)
    observed_uninterrupted_full_clear_signal = (
        manifest_full_clear
        and expected_bosses > 0
        and boss_kills >= expected_bosses
        and evidence_complete
        and (trash_pulls > 0 or not any(route.get("kind") == "trash" for route in routes))
    )
    full_clear_signal = observed_uninterrupted_full_clear_signal
    natural_full_clear = (
        not segmented_evidence
        and manifest_full_clear
        and expected_bosses > 0
        and boss_kills >= expected_bosses
        and complete_segment_coverage
        and route_evidence_complete
        and not forbidden_assists
        and int(evidence.get("failures") or 0) == 0
        and evidence_complete
        and not failure_labels
        and not failure_reason
    )
    clear_complete = natural_full_clear or attached_full_clear
    completion_evidence_mode = "uninterrupted_live_clear" if natural_full_clear else ("attached_uninterrupted_live_clear" if attached_full_clear else ("segment_debug_only" if segmented_evidence else "incomplete_or_smoke_only"))
    blockers = completion_blockers(
        clear_complete=clear_complete,
        segmented_evidence=segmented_evidence,
        expected_bosses=expected_bosses,
        boss_kills=boss_kills,
        evidence_complete=evidence_complete,
        failure_labels=failure_labels,
        failure_reason=failure_reason,
        full_clear_signal=full_clear_signal or attached_full_clear,
    )

    source_live_report = str(report.get("source_live_report") or "")
    segment_results = []
    for expected_route in routes:
        expected_node_id = str(expected_route.get("route_node_id") or "")
        expected_generation = int(expected_route.get("route_generation") or 0)
        terminal_ready = (expected_node_id, expected_generation) in terminal_scopes
        boss_ready = str(expected_route.get("kind") or "") != "boss" or (expected_node_id, expected_generation) in {
            (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0)) for row in real_boss_kill_evidence
        }
        if not terminal_ready:
            continue
        expected_required_evidence = [str(row) for row in (expected_route.get("required_evidence") or [])]
        expected_scoped_evidence = scoped_counts_by_scope[(expected_node_id, expected_generation)]
        expected_missing_evidence = missing_evidence(expected_required_evidence, expected_scoped_evidence)
        segment_results.append(
            {
                "segment_id": segment_output_name(expected_route),
                "route_node_id": expected_node_id,
                "route_generation": expected_generation,
                "route_label": expected_route.get("label") or "",
                "route_kind": expected_route.get("kind") or "",
                "route_step": int(expected_route.get("step") or 0),
                "mechanic_profile": expected_route.get("mechanic_profile") or "",
                "boss_kills": 1 if boss_ready and expected_route.get("kind") == "boss" else 0,
                "raid_boss_kills": 1 if raid and boss_ready and expected_route.get("kind") == "boss" else 0,
                "trash_pulls": int(expected_scoped_evidence.get("pulls") or 0) if expected_route.get("kind") == "trash" else 0,
                "clear_complete": False,
                "terminal_evidence": True,
                "real_boss_kill_evidence": boss_ready,
                "forbidden_completion_assists": forbidden_assists,
                "segment_complete": boss_ready and not expected_missing_evidence and not failure_labels and not failure_reason,
                "failure_labels": failure_labels,
                "failure_reason": failure_reason,
                "required_evidence": expected_required_evidence,
                "evidence_counts": expected_scoped_evidence,
                "missing_evidence": expected_missing_evidence,
                "evidence_complete": not expected_missing_evidence,
                "source_live_report": source_live_report,
            }
        )
    label_quality = merged_teacher_label_quality([evidence_mode], complete_segment_coverage)
    if not evidence_complete:
        label_quality = "weak"
    row = {
        "schema": "bot_live_scenario_report_v1",
        "scenario_id": scenario_id,
        "runtime_profile_id": str(scenario.get("runtime_profile_id") or scenario_id),
        "diagnostic_only": bool(scenario.get("diagnostic_only")),
        "diagnostic_parent_scenario_id": str(scenario.get("diagnostic_parent_scenario_id") or ""),
        "diagnostic_target_boss": str(scenario.get("diagnostic_target_boss") or ""),
        "prerequisite_contract": scenario.get("prerequisite_contract") if isinstance(scenario.get("prerequisite_contract"), dict) else {},
        "certifies_predecessors": scenario.get("certifies_predecessors") if scenario.get("diagnostic_only") else None,
        "instance": scenario.get("instance") or "",
        "map_id": int(scenario.get("map_id") or 0),
        "difficulty": difficulty,
        "prepared_group": bool(existing.get("prepared_group") or existing.get("group_ready") or scenario.get("provisioning_ready"))
        and (difficulty != "heroic_5man" or heroic_admission_verified),
        "heroic_admission_verified": heroic_admission_verified,
        "heroic_admission_receipt_sha256": str((session.get("heroic_admission") or {}).get("receipt_sha256") or ""),
        "trash_pulls": trash_pulls,
        "trash_cleared": bool(existing.get("trash_cleared")) or stage_passed(report, trash_stage) or trash_pulls > 0,
        "boss_kills": boss_kills,
        "raid_boss_kills": boss_kills if raid else 0,
        "expected_bosses": expected_bosses,
        "boss_stage_passed": bool(existing.get("boss_stage_passed")) or stage_passed(report, boss_stage) or boss_kills > 0,
        "clear_complete": clear_complete,
        "source_live_report": source_live_report,
        "source_live_reports": [source_live_report] if source_live_report else [],
        "source_acceptance_verification": source_acceptance,
        "expected_segments": expected_segments,
        "expected_route_evidence": expected_route_evidence,
        "source_segments": source_segments,
        "missing_segments": missing_segment_rows,
        "complete_segment_coverage": complete_segment_coverage,
        "route_terminal_evidence": route_terminal_evidence,
        "real_boss_kill_evidence": real_boss_kill_evidence,
        "missing_terminal_route_nodes": strict_evidence["missing_terminal_route_nodes"],
        "missing_boss_route_nodes": strict_evidence["missing_boss_route_nodes"],
        "forbidden_completion_assists": forbidden_assists,
        "strict_completion_evidence": complete_segment_coverage and route_evidence_complete and not strict_evidence["missing_boss_route_nodes"] and not forbidden_assists,
        "source_route_nodes": unique_strings(route_node_id),
        "source_route_labels": unique_strings(route_label),
        "source_mechanic_profiles": unique_strings(mechanic_profile),
        "required_evidence": expected_evidence,
        "evidence_counts": observed_evidence,
        "missing_evidence": missing_scenario_evidence,
        "evidence_complete": evidence_complete,
        "segment_results": segment_results,
        "natural_full_clear_evidence": natural_full_clear,
        "observed_uninterrupted_full_clear_signal": observed_uninterrupted_full_clear_signal,
        "attached_full_clear_evidence": attached_full_clear,
        "completion_evidence_mode": completion_evidence_mode,
        "completion_claim_valid": clear_complete,
        "clear_complete_blockers": blockers,
        "source_scenario_report_attached": bool(existing),
        "scenario_evidence_mode": evidence_mode,
        "scenario_evidence_modes": [evidence_mode],
        "teacher_label_quality": label_quality,
        "failure_labels": failure_labels,
        "failure_reason": failure_reason,
        "ml_training_label": "failed_teacher_attempt" if failure_labels else ("candidate_teacher_label" if label_quality in {"strong", "medium"} else "weak_inferred_label"),
        "source_trace_entries": int(report.get("trace_entries") or 0),
        "runtime_ml_control": "offline_shadow_only",
        "control_eligible": False,
    }
    row["report_hash"] = stable_hash(row)[:16]
    return row


def merge_report_rows(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
    if not left:
        return dict(right)
    merged = dict(left)
    source_reports = []
    for row in [left, right]:
        source = row.get("source_live_report")
        if source and source not in source_reports:
            source_reports.append(str(source))
        for extra in row.get("source_live_reports") or []:
            if extra and extra not in source_reports:
                source_reports.append(str(extra))
    left_expected_routes = [row for row in (left.get("expected_route_evidence") or []) if isinstance(row, dict)]
    right_expected_routes = [row for row in (right.get("expected_route_evidence") or []) if isinstance(row, dict)]
    route_contract_matches = bool(left_expected_routes) and left_expected_routes == right_expected_routes
    expected_route_evidence = left_expected_routes if route_contract_matches else []
    expected_route_scopes = {
        (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0))
        for row in expected_route_evidence
    }
    expected_boss_scopes = {
        (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0))
        for row in expected_route_evidence
        if str(row.get("route_kind") or "") == "boss"
    }
    expected_segments = [str(row.get("segment_id") or "") for row in expected_route_evidence]
    expected_bosses = len(expected_boss_scopes)
    source_route_nodes = unique_strings(left.get("source_route_nodes") or [], right.get("source_route_nodes") or [])
    source_route_labels = unique_strings(left.get("source_route_labels") or [], right.get("source_route_labels") or [])
    source_mechanic_profiles = unique_strings(left.get("source_mechanic_profiles") or [], right.get("source_mechanic_profiles") or [])
    required_evidence = unique_strings(left.get("required_evidence") or [], right.get("required_evidence") or [])
    evidence_count_rows = sum_evidence_counts(
        {str(key): int(value or 0) for key, value in (left.get("evidence_counts") or {}).items()},
        {str(key): int(value or 0) for key, value in (right.get("evidence_counts") or {}).items()},
    )
    missing_evidence_rows = missing_evidence(required_evidence, evidence_count_rows)
    evidence_complete = not missing_evidence_rows
    segment_results = list(left.get("segment_results") or []) + list(right.get("segment_results") or [])
    evidence_modes = unique_strings(left.get("scenario_evidence_modes") or left.get("scenario_evidence_mode") or [], right.get("scenario_evidence_modes") or right.get("scenario_evidence_mode") or [])
    failure_labels = unique_strings(left.get("failure_labels") or [], right.get("failure_labels") or [])
    failure_reason = str(left.get("failure_reason") or right.get("failure_reason") or (failure_labels[0] if failure_labels else ""))
    route_terminal_evidence = [
        {"route_node_id": node_id, "route_generation": generation}
        for node_id, generation in sorted(
            {
                (str(item.get("route_node_id") or ""), int(item.get("route_generation") or 0))
                for row in [left, right]
                for item in row.get("route_terminal_evidence") or []
                if isinstance(item, dict)
            }
            & expected_route_scopes
        )
    ]
    real_boss_kill_evidence = [
        {"route_node_id": node_id, "route_generation": generation}
        for node_id, generation in sorted(
            {
                (str(item.get("route_node_id") or ""), int(item.get("route_generation") or 0))
                for row in [left, right]
                for item in row.get("real_boss_kill_evidence") or []
                if isinstance(item, dict)
            }
            & expected_boss_scopes
        )
    ]
    terminal_scopes = {(str(row["route_node_id"]), int(row["route_generation"])) for row in route_terminal_evidence}
    killed_boss_scopes = {(str(row["route_node_id"]), int(row["route_generation"])) for row in real_boss_kill_evidence}
    source_segments = [
        str(row.get("segment_id") or "")
        for row in expected_route_evidence
        if (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0)) in terminal_scopes
    ]
    missing_segment_rows = missing_segments(expected_segments, source_segments)
    complete_segment_coverage = bool(expected_segments) and not missing_segment_rows
    boss_kills = len(real_boss_kill_evidence)
    raid_boss_kills = boss_kills if int(left.get("raid_boss_kills") or right.get("raid_boss_kills") or 0) > 0 else 0
    forbidden_assists = list(left.get("forbidden_completion_assists") or []) + list(right.get("forbidden_completion_assists") or [])
    missing_terminal_route_nodes = [
        str(row.get("route_node_id") or "")
        for row in expected_route_evidence
        if (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0)) not in terminal_scopes
    ]
    missing_boss_route_nodes = [
        str(row.get("route_node_id") or "")
        for row in expected_route_evidence
        if str(row.get("route_kind") or "") == "boss"
        and (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0)) not in killed_boss_scopes
    ]
    label_quality = merged_teacher_label_quality(evidence_modes, complete_segment_coverage)
    if not evidence_complete:
        label_quality = "weak"
    segmented_evidence = "route_segment_context" in evidence_modes and bool(expected_segments)
    natural_full_clear = bool(left.get("natural_full_clear_evidence") or right.get("natural_full_clear_evidence"))
    attached_full_clear = bool(left.get("attached_full_clear_evidence") or right.get("attached_full_clear_evidence"))
    heroic_required = str(left.get("difficulty") or right.get("difficulty") or "") == "heroic_5man"
    heroic_admission_verified = bool(left.get("heroic_admission_verified")) and bool(right.get("heroic_admission_verified"))
    completed_segment_scopes = {
        (str(row.get("route_node_id") or ""), int(row.get("route_generation") or 0))
        for row in segment_results
        if isinstance(row, dict) and bool(row.get("segment_complete")) and bool(row.get("evidence_complete"))
    }
    strict_completion_evidence = (
        route_contract_matches
        and complete_segment_coverage
        and not missing_boss_route_nodes
        and expected_route_scopes <= completed_segment_scopes
        and not forbidden_assists
    )
    clear_complete = (natural_full_clear or attached_full_clear) and evidence_complete and strict_completion_evidence
    if heroic_required and not heroic_admission_verified:
        clear_complete = False
    if failure_labels or failure_reason:
        clear_complete = False
    completion_evidence_mode = "uninterrupted_live_clear" if natural_full_clear else ("attached_uninterrupted_live_clear" if attached_full_clear else ("segment_debug_only" if segmented_evidence else "incomplete_or_smoke_only"))
    blockers = completion_blockers(
        clear_complete=clear_complete,
        segmented_evidence=segmented_evidence,
        expected_bosses=expected_bosses,
        boss_kills=max(boss_kills, raid_boss_kills),
        evidence_complete=evidence_complete,
        failure_labels=failure_labels,
        failure_reason=failure_reason,
        full_clear_signal=natural_full_clear or attached_full_clear,
    )
    merged.update(
        {
            "prepared_group": bool(left.get("prepared_group") or right.get("prepared_group"))
            and (not heroic_required or heroic_admission_verified),
            "heroic_admission_verified": heroic_admission_verified,
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
            "expected_route_evidence": expected_route_evidence,
            "source_segments": source_segments,
            "missing_segments": missing_segment_rows,
            "complete_segment_coverage": complete_segment_coverage,
            "route_terminal_evidence": route_terminal_evidence,
            "real_boss_kill_evidence": real_boss_kill_evidence,
            "missing_terminal_route_nodes": missing_terminal_route_nodes,
            "missing_boss_route_nodes": missing_boss_route_nodes,
            "forbidden_completion_assists": forbidden_assists,
            "strict_completion_evidence": strict_completion_evidence,
            "source_route_nodes": source_route_nodes,
            "source_route_labels": source_route_labels,
            "source_mechanic_profiles": source_mechanic_profiles,
            "required_evidence": required_evidence,
            "evidence_counts": evidence_count_rows,
            "missing_evidence": missing_evidence_rows,
            "evidence_complete": evidence_complete,
            "segment_results": segment_results,
            "natural_full_clear_evidence": natural_full_clear,
            "observed_uninterrupted_full_clear_signal": bool(left.get("observed_uninterrupted_full_clear_signal") or right.get("observed_uninterrupted_full_clear_signal")),
            "attached_full_clear_evidence": attached_full_clear,
            "completion_evidence_mode": completion_evidence_mode,
            "completion_claim_valid": clear_complete,
            "clear_complete_blockers": blockers,
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
        "runtime_ml_control": "offline_shadow_only",
        "control_eligible": False,
    }
    write_json(args.output_dir / "manifest.json", summary)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
