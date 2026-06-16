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


def load_scenarios(path: Path) -> dict[str, dict[str, Any]]:
    rows = read_jsonl(path / "validation_scenarios.jsonl")
    return {str(row.get("scenario_id") or ""): row for row in rows if row.get("scenario_id")}


def load_routes(path: Path) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in read_jsonl(path / "validation_routes.jsonl"):
        grouped.setdefault(str(row.get("scenario_id") or ""), []).append(row)
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
            return bool(row.get("passed"))
    return False


def infer_report(report: dict[str, Any], scenario: dict[str, Any], routes: list[dict[str, Any]], existing: dict[str, Any]) -> dict[str, Any]:
    scenario_id = str(scenario.get("scenario_id") or "")
    difficulty = str(scenario.get("difficulty") or "")
    raid = "10" in difficulty or "raid" in difficulty
    actions = action_names(report)
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    evidence = report.get("evidence") if isinstance(report.get("evidence"), dict) else {}
    boss_action = "raid_boss_killed" if raid else "boss_killed"
    observed_boss_kills = sum(1 for action in actions if action == boss_action)
    observed_boss_kills = max(observed_boss_kills, int(summary.get("raid_boss_kills") or 0) if raid else 0)
    expected_bosses = int(scenario.get("boss_count") or sum(1 for route in routes if route.get("kind") == "boss"))
    trash_actions = sum(1 for action in actions if action in {"trash_action", "trash_heal", "material_farming_source"} or "trash" in action)
    trash_pulls = max(int(existing.get("trash_pulls") or 0), trash_actions)

    full_clear_stage = "full_blackwing_descent_clear" if raid else "full_stonecore_clear"
    boss_stage = "raid_boss" if raid else "dungeon_boss"
    trash_stage = "raid_trash" if raid else "normal_dungeon_trash"
    boss_kills = max(int(existing.get("raid_boss_kills" if raid else "boss_kills") or 0), observed_boss_kills)
    clear_complete = bool(existing.get("clear_complete")) or stage_passed(report, full_clear_stage) or (expected_bosses > 0 and boss_kills >= expected_bosses and int(evidence.get("failures") or 0) == 0)

    source_live_report = str(report.get("source_live_report") or "")
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
    merged.update(
        {
            "prepared_group": bool(left.get("prepared_group") or right.get("prepared_group")),
            "trash_pulls": int(left.get("trash_pulls") or 0) + int(right.get("trash_pulls") or 0),
            "trash_cleared": bool(left.get("trash_cleared") or right.get("trash_cleared")),
            "boss_kills": boss_kills,
            "raid_boss_kills": raid_boss_kills,
            "expected_bosses": expected_bosses,
            "boss_stage_passed": bool(left.get("boss_stage_passed") or right.get("boss_stage_passed") or boss_kills > 0 or raid_boss_kills > 0),
            "clear_complete": bool(left.get("clear_complete") or right.get("clear_complete") or (expected_bosses > 0 and max(boss_kills, raid_boss_kills) >= expected_bosses)),
            "source_live_report": source_reports[0] if source_reports else "",
            "source_live_reports": source_reports,
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
        for live_report in live_reports:
            inferred = infer_report(live_report, scenario, routes.get(scenario_id, []), existing_scenario_report(live_report, scenario_id))
            merged = merge_report_rows(merged, inferred)
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
    for path in live_report_paths:
        live_report = load_json(path)
        live_report["source_live_report"] = str(path)
        live_reports.append(live_report)
    reports = build_reports_from_live_reports(live_reports, args.validation_scenario_dir, args.scenario_id or None)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for scenario_id, report in reports.items():
        write_json(args.output_dir / f"{scenario_id}.json", report)
    summary = {
        "schema": "bot_live_scenario_reports_manifest_v1",
        "source_live_reports": [str(path) for path in live_report_paths],
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
