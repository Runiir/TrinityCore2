from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

try:
    from .common import read_jsonl, stable_hash, write_json
except ImportError:
    from common import read_jsonl, stable_hash, write_json


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def load_scenarios(path: Path) -> list[dict[str, Any]]:
    return read_jsonl(path / "validation_scenarios.jsonl")


def load_routes(path: Path) -> dict[str, list[dict[str, Any]]]:
    routes_by_scenario: dict[str, list[dict[str, Any]]] = {}
    route_path = path / "validation_routes.jsonl"
    if not route_path.exists():
        return routes_by_scenario
    for row in read_jsonl(route_path):
        scenario_id = str(row.get("scenario_id") or "")
        if not scenario_id:
            continue
        routes_by_scenario.setdefault(scenario_id, []).append(row)
    for rows in routes_by_scenario.values():
        rows.sort(key=lambda row: int(row.get("step") or 0))
    return routes_by_scenario


def scenario_output_name(scenario_id: str) -> str:
    return scenario_id.replace("/", "_").replace(" ", "_")


def segment_output_name(route: dict[str, Any]) -> str:
    step = int(route.get("step") or 0)
    label = str(route.get("label") or route.get("route_node_id") or "segment")
    slug = "".join(ch.lower() if ch.isalnum() else "_" for ch in label).strip("_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return f"{step:02d}_{slug or 'segment'}"


def live_validate_command(scenario: dict[str, Any], output_root: Path, observe_sec: int, timeout_sec: int, route: dict[str, Any] | None = None) -> list[str]:
    scenario_id = str(scenario.get("scenario_id") or "")
    output_dir = output_root / scenario_output_name(scenario_id)
    if route:
        output_dir = output_dir / segment_output_name(route)
    return [
        "pixi",
        "run",
        "bot-live-validate",
        "--apply-validation-provisioning",
        "--reset-bot-pool",
        "--bot-pool-tag",
        scenario_id,
        "--keep-bot-pool-position",
        "--observe-sec",
        str(observe_sec),
        "--timeout-sec",
        str(timeout_sec),
        "--output-dir",
        str(output_dir),
    ]


def scenario_report_command(scenario: dict[str, Any], output_root: Path, report_root: Path, validation_scenario_dir: Path, routes: list[dict[str, Any]] | None = None) -> list[str]:
    scenario_id = str(scenario.get("scenario_id") or "")
    live_reports: list[str]
    boss_routes = [row for row in routes or [] if row.get("kind") == "boss"]
    if boss_routes:
        live_reports = [
            str(output_root / scenario_output_name(scenario_id) / segment_output_name(route) / "report.json")
            for route in boss_routes
        ]
    else:
        live_reports = [str(output_root / scenario_output_name(scenario_id) / "report.json")]

    command = [
        "pixi",
        "run",
        "bot-live-scenario-reports",
    ]
    for live_report in live_reports:
        command.extend(["--live-report", live_report])
    command.extend(
        [
            "--validation-scenario-dir",
            str(validation_scenario_dir),
            "--scenario-id",
            scenario_id,
            "--output-dir",
            str(report_root),
        ]
    )
    return command


def render_command(command: list[str]) -> str:
    return " ".join(shell_quote(part) for part in command)


def build_plan(
    scenarios: list[dict[str, Any]],
    output_root: Path,
    report_root: Path,
    validation_scenario_dir: Path,
    observe_sec: int,
    timeout_sec: int,
    routes_by_scenario: dict[str, list[dict[str, Any]]] | None = None,
) -> dict[str, Any]:
    rows = []
    for scenario in sorted(scenarios, key=lambda row: str(row.get("scenario_id") or "")):
        scenario_id = str(scenario.get("scenario_id") or "")
        if not scenario_id:
            continue
        routes = (routes_by_scenario or {}).get(scenario_id, [])
        boss_routes = [route for route in routes if route.get("kind") == "boss"]
        live_command = live_validate_command(scenario, output_root, observe_sec, timeout_sec)
        report_command = scenario_report_command(scenario, output_root, report_root, validation_scenario_dir, boss_routes)
        segments = []
        for route in boss_routes:
            segment_command = live_validate_command(scenario, output_root, observe_sec, timeout_sec, route)
            segments.append(
                {
                    "segment_id": segment_output_name(route),
                    "route_node_id": route.get("route_node_id") or "",
                    "step": int(route.get("step") or 0),
                    "kind": route.get("kind") or "",
                    "label": route.get("label") or "",
                    "mechanic_profile": route.get("mechanic_profile") or "",
                    "live_output_dir": str(output_root / scenario_output_name(scenario_id) / segment_output_name(route)),
                    "live_validate_command": segment_command,
                    "live_validate_shell": render_command(segment_command),
                }
            )
        rows.append(
            {
                "scenario_id": scenario_id,
                "instance": scenario.get("instance") or "",
                "map_id": int(scenario.get("map_id") or 0),
                "difficulty": scenario.get("difficulty") or "",
                "required_roles": scenario.get("required_roles") or {},
                "live_output_dir": str(output_root / scenario_output_name(scenario_id)),
                "scenario_report_dir": str(report_root),
                "preserve_start_position": True,
                "bot_pool_tag": scenario_id,
                "segment_count": len(segments),
                "segments": segments,
                "live_validate_command": live_command,
                "scenario_report_command": report_command,
                "live_validate_shell": render_command(live_command),
                "scenario_report_shell": render_command(report_command),
            }
        )
    return {
        "schema": "bot_validation_run_plan_v1",
        "scenario_count": len(rows),
        "scenarios": rows,
        "runtime_ml_control": "disabled_until_live_clear_validation_passes",
        "plan_hash": stable_hash(rows),
    }


def write_shell_script(path: Path, plan: dict[str, Any]) -> None:
    lines = [
        "#!/usr/bin/env bash",
        "set -euo pipefail",
        "",
        "# Generated by tools.bot_ml.build_validation_run_plan.",
    ]
    for scenario in plan.get("scenarios") or []:
        lines.extend(
            [
                "",
                f"# {scenario['scenario_id']} - {scenario.get('instance', '')}",
            ]
        )
        if scenario.get("segments"):
            for segment in scenario.get("segments") or []:
                lines.extend(
                    [
                        f"# segment {segment['segment_id']} - {segment.get('label', '')}",
                        segment["live_validate_shell"],
                    ]
                )
        else:
            lines.append(scenario["live_validate_shell"])
        lines.append(scenario["scenario_report_shell"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    path.chmod(0o755)


def main() -> int:
    parser = argparse.ArgumentParser(description="Build reproducible live validation run commands for Stonecore/BWD scenarios.")
    parser.add_argument("--validation-scenario-dir", type=Path, default=Path("dataset/validation_scenarios"))
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/validation_run_plan"))
    parser.add_argument("--live-output-root", type=Path, default=Path("dataset/live_validation_scenarios"))
    parser.add_argument("--scenario-report-root", type=Path, default=Path("dataset/live_validation_scenario_reports_built"))
    parser.add_argument("--observe-sec", type=int, default=300)
    parser.add_argument("--timeout-sec", type=int, default=900)
    args = parser.parse_args()

    plan = build_plan(
        load_scenarios(args.validation_scenario_dir),
        args.live_output_root,
        args.scenario_report_root,
        args.validation_scenario_dir,
        args.observe_sec,
        args.timeout_sec,
        load_routes(args.validation_scenario_dir),
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "manifest.json", plan)
    write_shell_script(args.output_dir / "run_validation_scenarios.sh", plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
