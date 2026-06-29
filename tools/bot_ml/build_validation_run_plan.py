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


def live_validate_command(
    scenario: dict[str, Any],
    output_root: Path,
    observe_sec: int | None = None,
    timeout_sec: int | None = None,
    route: dict[str, Any] | None = None,
    segment_output: bool = True,
    route_sequence: bool = False,
    duration_policy: str = "completion-watchdog",
    heartbeat_sec: int = 30,
    no_progress_window_sec: int = 180,
    max_repeated_decisions: int = 20,
    max_death_loops: int = 3,
) -> list[str]:
    scenario_id = str(scenario.get("scenario_id") or "")
    output_dir = output_root / scenario_output_name(scenario_id)
    context_args: list[str] = [
        "--validation-scenario-id",
        scenario_id,
    ]
    if route:
        if segment_output:
            output_dir = output_dir / segment_output_name(route)
        context_args.extend(
            [
                "--validation-route-node-id",
                str(route.get("route_node_id") or ""),
                "--validation-route-label",
                str(route.get("label") or ""),
                "--validation-route-kind",
                str(route.get("kind") or ""),
                "--validation-route-step",
                str(int(route.get("step") or 0)),
                "--validation-mechanic-profile",
                str(route.get("mechanic_profile") or ""),
            ]
        )
        if segment_output:
            context_args[2:2] = [
                "--validation-segment-id",
                segment_output_name(route),
            ]
    command = [
        "pixi",
        "run",
        "bot-live-validate",
        "--duration-policy",
        duration_policy,
        "--apply-validation-provisioning",
        "--reset-bot-pool",
        "--bot-pool-tag",
        scenario_id,
        "--keep-bot-pool-position",
        "--heartbeat-sec",
        str(heartbeat_sec),
        "--no-progress-window-sec",
        str(no_progress_window_sec),
        "--max-repeated-decision-count",
        str(max_repeated_decisions),
        "--max-death-loop-count",
        str(max_death_loops),
        *context_args,
        "--output-dir",
        str(output_dir),
    ]
    if route_sequence:
        command.append("--validation-route-manifest")
    if duration_policy == "fixed-window":
        if observe_sec is not None:
            command.extend(["--observe-sec", str(observe_sec)])
        if timeout_sec is not None:
            command.extend(["--timeout-sec", str(timeout_sec)])
    return command


def route_coordinates_valid(route: dict[str, Any]) -> bool:
    if "coordinates_valid" in route:
        return bool(route.get("coordinates_valid"))
    return True


def scenario_report_command(scenario: dict[str, Any], output_root: Path, report_root: Path, validation_scenario_dir: Path, routes: list[dict[str, Any]] | None = None) -> list[str]:
    scenario_id = str(scenario.get("scenario_id") or "")
    live_reports: list[str]
    executable_routes = [row for row in routes or [] if route_coordinates_valid(row)]
    full_report = str(output_root / scenario_output_name(scenario_id) / "report.json")
    if executable_routes:
        live_reports = [full_report] + [
            str(output_root / scenario_output_name(scenario_id) / segment_output_name(route) / "report.json")
            for route in executable_routes
        ]
    else:
        live_reports = [full_report]

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
    duration_policy: str = "completion-watchdog",
    heartbeat_sec: int = 30,
    no_progress_window_sec: int = 180,
    max_repeated_decisions: int = 20,
    max_death_loops: int = 3,
) -> dict[str, Any]:
    rows = []
    for scenario in sorted(scenarios, key=lambda row: str(row.get("scenario_id") or "")):
        scenario_id = str(scenario.get("scenario_id") or "")
        if not scenario_id:
            continue
        routes = (routes_by_scenario or {}).get(scenario_id, [])
        route_segments = [route for route in routes if route.get("kind") in {"trash", "boss"}]
        executable_route_segments = [route for route in route_segments if route_coordinates_valid(route)]
        live_command = live_validate_command(
            scenario,
            output_root,
            observe_sec,
            timeout_sec,
            None,
            segment_output=False,
            route_sequence=bool(executable_route_segments),
            duration_policy=duration_policy,
            heartbeat_sec=heartbeat_sec,
            no_progress_window_sec=no_progress_window_sec,
            max_repeated_decisions=max_repeated_decisions,
            max_death_loops=max_death_loops,
        )
        report_command = scenario_report_command(scenario, output_root, report_root, validation_scenario_dir, route_segments)
        segments = []
        for route in route_segments:
            segment_command = live_validate_command(
                scenario,
                output_root,
                observe_sec,
                timeout_sec,
                route,
                duration_policy=duration_policy,
                heartbeat_sec=heartbeat_sec,
                no_progress_window_sec=no_progress_window_sec,
                max_repeated_decisions=max_repeated_decisions,
                max_death_loops=max_death_loops,
            )
            executable = route_coordinates_valid(route)
            segments.append(
                {
                    "segment_id": segment_output_name(route),
                    "route_node_id": route.get("route_node_id") or "",
                    "step": int(route.get("step") or 0),
                    "kind": route.get("kind") or "",
                    "label": route.get("label") or "",
                    "mechanic_profile": route.get("mechanic_profile") or "",
                    "required_evidence": route.get("required_evidence") or [],
                    "evidence_contract": route.get("evidence_contract") or [],
                    "x": float(route.get("x") or 0.0),
                    "y": float(route.get("y") or 0.0),
                    "z": float(route.get("z") or 0.0),
                    "coordinates_valid": executable,
                    "coordinate_missing_reason": route.get("coordinate_missing_reason") or "",
                    "executable": executable,
                    "skip_reason": "" if executable else "missing_route_coordinates",
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
                "group_kind": scenario.get("group_kind") or "",
                "role_assignment": scenario.get("role_assignment") or {},
                "required_evidence": scenario.get("required_evidence") or [],
                "evidence_contract": scenario.get("evidence_contract") or [],
                "live_output_dir": str(output_root / scenario_output_name(scenario_id)),
                "scenario_report_dir": str(report_root),
                "preserve_start_position": True,
                "bot_pool_tag": scenario_id,
                "lane_name": f"{scenario_output_name(scenario_id)}_full_clear",
                "duration_policy": duration_policy,
                "watchdog": {
                    "heartbeat_sec": heartbeat_sec,
                    "no_progress_window_sec": no_progress_window_sec,
                    "max_repeated_decisions": max_repeated_decisions,
                    "max_death_loops": max_death_loops,
                    "emergency_timeout_sec": timeout_sec,
                    "fixed_observe_sec": observe_sec if duration_policy == "fixed-window" else None,
                },
                "segment_count": len(segments),
                "executable_segment_count": sum(1 for segment in segments if segment["executable"]),
                "invalid_segment_count": sum(1 for segment in segments if not segment["executable"]),
                "segments": segments,
                "live_validate_command": live_command,
                "scenario_report_command": report_command,
                "live_validate_shell": render_command(live_command),
                "scenario_report_shell": render_command(report_command),
            }
        )
    return {
        "schema": "bot_validation_run_plan_v1",
        "duration_policy": duration_policy,
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
            lines.append(scenario["live_validate_shell"])
            for segment in scenario.get("segments") or []:
                if not segment.get("executable", True):
                    lines.extend(
                        [
                            f"# segment {segment['segment_id']} - {segment.get('label', '')}",
                            f"printf '%s\\n' {shell_quote('Skipping non-executable validation segment ' + segment['segment_id'] + ': ' + segment.get('skip_reason', ''))}",
                        ]
                    )
                    continue
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
    parser.add_argument("--duration-policy", choices=["completion-watchdog", "fixed-window"], default="completion-watchdog")
    parser.add_argument("--heartbeat-sec", type=int, default=30)
    parser.add_argument("--no-progress-window-sec", type=int, default=180)
    parser.add_argument("--max-repeated-decision-count", type=int, default=20)
    parser.add_argument("--max-death-loop-count", type=int, default=3)
    args = parser.parse_args()

    plan = build_plan(
        load_scenarios(args.validation_scenario_dir),
        args.live_output_root,
        args.scenario_report_root,
        args.validation_scenario_dir,
        args.observe_sec,
        args.timeout_sec,
        load_routes(args.validation_scenario_dir),
        duration_policy=args.duration_policy,
        heartbeat_sec=args.heartbeat_sec,
        no_progress_window_sec=args.no_progress_window_sec,
        max_repeated_decisions=args.max_repeated_decision_count,
        max_death_loops=args.max_death_loop_count,
    )
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_json(args.output_dir / "manifest.json", plan)
    write_shell_script(args.output_dir / "run_validation_scenarios.sh", plan)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
