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


def segment_report_path(segment: dict[str, Any]) -> Path:
    return Path(str(segment.get("live_output_dir") or "")) / "report.json"


def scenario_report_path(report_root: Path, scenario_id: str) -> Path:
    return report_root / f"{scenario_id}.json"


def build_status(plan: dict[str, Any], report_root: Path) -> dict[str, Any]:
    scenarios = []
    for scenario in plan.get("scenarios") or []:
        scenario_id = str(scenario.get("scenario_id") or "")
        segments = [segment for segment in scenario.get("segments") or [] if segment.get("executable", True)]
        present_segments = []
        missing_segments = []
        segment_reports = []
        for segment in segments:
            report_path = segment_report_path(segment)
            row = {
                "segment_id": segment.get("segment_id") or "",
                "route_node_id": segment.get("route_node_id") or "",
                "label": segment.get("label") or "",
                "mechanic_profile": segment.get("mechanic_profile") or "",
                "report": str(report_path),
                "report_exists": report_path.exists(),
                "live_validate_command": segment.get("live_validate_command") or [],
                "live_validate_shell": segment.get("live_validate_shell") or "",
            }
            segment_reports.append(row)
            if row["report_exists"]:
                present_segments.append(row["segment_id"])
            else:
                missing_segments.append(row["segment_id"])

        scenario_report_file = scenario_report_path(report_root, scenario_id)
        scenario_report = load_json(scenario_report_file)
        complete_segment_coverage = bool(scenario_report.get("complete_segment_coverage"))
        clear_complete = bool(scenario_report.get("clear_complete"))
        segment_coverage_ready = bool(segments) and not missing_segments
        scenario_report_ready = scenario_report_file.exists()
        full_clear_ready = clear_complete and (complete_segment_coverage or not segments)

        next_commands = [
            row["live_validate_shell"]
            for row in segment_reports
            if not row["report_exists"] and row["live_validate_shell"]
        ]
        if (not scenario_report_ready or not full_clear_ready) and scenario.get("scenario_report_shell"):
            next_commands.append(str(scenario["scenario_report_shell"]))

        blockers = []
        if missing_segments:
            blockers.append("missing_segment_live_reports")
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
                "missing_segments": missing_segments,
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
