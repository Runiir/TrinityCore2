from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .common import stable_hash, write_json, write_jsonl
except ImportError:
    from common import stable_hash, write_json, write_jsonl


MECHANIC_FAMILIES = {
    "trash_pack",
    "caster_pack",
    "healer_mob",
    "patrol_risk",
    "cleave_risk",
    "interrupt_required",
    "dispel_required",
    "tank_buster",
    "raid_aoe",
    "ground_danger",
    "stack",
    "spread",
    "adds",
    "target_switch",
    "enrage",
    "movement_check",
    "boss_phase",
    "wipe_risk",
}


def load_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return default or {}
    return json.loads(path.read_text(encoding="utf-8"))


def scenario_by_id(report: dict[str, Any]) -> dict[str, dict[str, Any]]:
    scenarios = report.get("scenarios") or []
    return {
        str(row.get("scenario_id") or row.get("id") or ""): row
        for row in scenarios
        if isinstance(row, dict) and (row.get("scenario_id") or row.get("id"))
    }


def provisioning_ready(row: dict[str, Any] | None, expected_roles: dict[str, int]) -> tuple[bool, list[str]]:
    if not row:
        return False, ["provisioning_scenario_report"]
    missing = list(row.get("missing") or [])
    role_counts = {str(k): int(v) for k, v in (row.get("role_counts") or {}).items()}
    for role, expected in expected_roles.items():
        if role_counts.get(role, 0) < int(expected):
            missing.append(f"{role}_role_count")
    return not missing, sorted(set(missing))


def route_coordinate_status(step: dict[str, Any]) -> tuple[bool, str]:
    if not all(key in step for key in ("x", "y", "z")):
        return False, "missing_xyz"
    x = float(step.get("x") or 0.0)
    y = float(step.get("y") or 0.0)
    z = float(step.get("z") or 0.0)
    if abs(x) < 0.001 and abs(y) < 0.001 and abs(z) < 0.001:
        return False, "zero_xyz"
    return True, ""


def build_manifests(config: dict[str, Any], provisioning_report: dict[str, Any], provisioning_verify_report: dict[str, Any]) -> dict[str, list[dict[str, Any]] | dict[str, Any]]:
    provisioned = scenario_by_id(provisioning_report)
    verification_ready = bool(provisioning_verify_report.get("all_passed"))
    scenarios: list[dict[str, Any]] = []
    routes: list[dict[str, Any]] = []
    mechanics: list[dict[str, Any]] = []

    for scenario in config.get("scenarios") or []:
        scenario_id = str(scenario.get("id") or "")
        provision_id = str(scenario.get("provisioning_scenario_id") or scenario_id)
        required_roles = {str(k): int(v) for k, v in (scenario.get("required_roles") or {}).items()}
        route_steps = scenario.get("route") or []
        profiles = scenario.get("mechanic_profiles") or {}
        ready, missing = provisioning_ready(provisioned.get(provision_id), required_roles)
        provisioned_roles = {str(k): int(v) for k, v in ((provisioned.get(provision_id) or {}).get("role_counts") or {}).items()}
        expected_bot_count = sum(provisioned_roles.values()) or sum(required_roles.values())
        if not verification_ready:
            missing.append("provisioning_verifier_ready")
        invalid_route_steps = [
            {
                "step": int(step.get("step") or 0),
                "kind": step.get("kind") or "unknown",
                "label": step.get("label") or "",
                "reason": route_coordinate_status(step)[1],
            }
            for step in route_steps
            if not route_coordinate_status(step)[0]
        ]
        if invalid_route_steps:
            missing.append("route_coordinates")

        scenario_row = {
            "scenario_id": scenario_id,
            "instance": scenario.get("instance") or "",
            "map_id": int(scenario.get("map_id") or 0),
            "difficulty": scenario.get("difficulty") or "",
            "provisioning_scenario_id": provision_id,
            "required_roles": required_roles,
            "expected_bot_count": expected_bot_count,
            "provisioning_ready": bool(ready and verification_ready),
            "missing": sorted(set(missing)),
            "route_step_count": len(route_steps),
            "boss_count": sum(1 for step in route_steps if step.get("kind") == "boss"),
            "trash_cluster_count": sum(1 for step in route_steps if step.get("kind") == "trash"),
            "mechanic_profile_count": len(profiles),
            "route_coordinates_ready": not invalid_route_steps,
            "invalid_route_steps": invalid_route_steps,
        }
        scenario_row["scenario_hash"] = stable_hash(scenario_row)[:16]
        scenarios.append(scenario_row)

        for step in route_steps:
            coordinates_valid, coordinate_missing_reason = route_coordinate_status(step)
            route = {
                "scenario_id": scenario_id,
                "map_id": int(scenario.get("map_id") or 0),
                "step": int(step.get("step") or 0),
                "kind": step.get("kind") or "unknown",
                "label": step.get("label") or "",
                "mechanic_profile": step.get("mechanic_profile") or "",
                "x": float(step.get("x") or 0.0),
                "y": float(step.get("y") or 0.0),
                "z": float(step.get("z") or 0.0),
                "o": float(step.get("o") or step.get("orientation") or 0.0),
                "source_entry": int(step.get("source_entry") or 0),
                "source_guid": str(step.get("source_guid") or ""),
                "source_table": step.get("source_table") or "",
                "source_sql": step.get("source_sql") or "",
                "coordinates_valid": coordinates_valid,
                "coordinate_missing_reason": coordinate_missing_reason,
            }
            route["route_node_id"] = stable_hash(route)[:16]
            route["expected_bot_count"] = expected_bot_count
            bot_start = step.get("bot_start") or {}
            route["bot_start_map_id"] = int(bot_start.get("map_id") or step.get("bot_start_map_id") or 0)
            route["bot_start_x"] = float(bot_start.get("x") or step.get("bot_start_x") or 0.0)
            route["bot_start_y"] = float(bot_start.get("y") or step.get("bot_start_y") or 0.0)
            route["bot_start_z"] = float(bot_start.get("z") or step.get("bot_start_z") or 0.0)
            route["bot_start_o"] = float(bot_start.get("o") or step.get("bot_start_o") or 0.0)
            route["opener_target_entry"] = int(step.get("opener_target_entry") or 0)
            route["activation_data_id"] = int(step.get("activation_data_id") or 0)
            route["activation_data_value"] = int(step.get("activation_data_value") or 0)
            route["activation_spawn_group_id"] = int(step.get("activation_spawn_group_id") or 0)
            route["activation_action_entry"] = int(step.get("activation_action_entry") or 0)
            route["activation_action_id"] = int(step.get("activation_action_id") or 0)
            route["activation_summon_entry"] = int(step.get("activation_summon_entry") or 0)
            route["activation_summon_x"] = float(step.get("activation_summon_x") or 0.0)
            route["activation_summon_y"] = float(step.get("activation_summon_y") or 0.0)
            route["activation_summon_z"] = float(step.get("activation_summon_z") or 0.0)
            route["activation_summon_o"] = float(step.get("activation_summon_o") or 0.0)
            route["opener_summon_entry"] = int(step.get("opener_summon_entry") or 0)
            route["opener_summon_x"] = float(step.get("opener_summon_x") or 0.0)
            route["opener_summon_y"] = float(step.get("opener_summon_y") or 0.0)
            route["opener_summon_z"] = float(step.get("opener_summon_z") or 0.0)
            route["opener_summon_o"] = float(step.get("opener_summon_o") or 0.0)
            routes.append(route)

        for profile, families in profiles.items():
            family_rows = [str(family) for family in families]
            unknown = sorted(set(family_rows) - MECHANIC_FAMILIES)
            mechanic = {
                "scenario_id": scenario_id,
                "mechanic_profile": str(profile),
                "families": family_rows,
                "unknown_families": unknown,
                "role_responses": {
                    "tank": "survive_position_interrupt_or_swap",
                    "healer": "heal_dispel_or_external",
                    "dps": "interrupt_switch_move_or_maintain_uptime",
                },
                "valid": not unknown,
            }
            mechanic["mechanic_hash"] = stable_hash(mechanic)[:16]
            mechanics.append(mechanic)

    report = {
        "schema": "bot_validation_scenario_manifest_report_v1",
        "scenarios": len(scenarios),
        "routes": len(routes),
        "mechanic_profiles": len(mechanics),
        "ready_scenarios": sum(1 for row in scenarios if row["provisioning_ready"]),
        "invalid_mechanic_profiles": [row for row in mechanics if not row["valid"]],
        "invalid_route_steps": [
            {
                "scenario_id": scenario["scenario_id"],
                **invalid_step,
            }
            for scenario in scenarios
            for invalid_step in scenario["invalid_route_steps"]
        ],
        "runtime_ml_control": "disabled_until_live_clear_validation_passes",
    }
    return {
        "validation_scenarios": sorted(scenarios, key=lambda row: row["scenario_id"]),
        "validation_routes": sorted(routes, key=lambda row: (row["scenario_id"], row["step"])),
        "validation_mechanics": sorted(mechanics, key=lambda row: (row["scenario_id"], row["mechanic_profile"])),
        "report": report,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build Stonecore/BWD validation route and mechanic manifests.")
    parser.add_argument("--config", type=Path, default=Path("experiments/configs/validation_scenarios_cata_001.json"))
    parser.add_argument("--provisioning-report", type=Path, default=Path("dataset/validation_provisioning/report.json"))
    parser.add_argument("--provisioning-verification", type=Path, default=Path("dataset/validation_provisioning_verification/report.json"))
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/validation_scenarios"))
    args = parser.parse_args()

    manifests = build_manifests(load_json(args.config), load_json(args.provisioning_report), load_json(args.provisioning_verification))
    counts: dict[str, int] = {}
    hashes: dict[str, str] = {}
    for name in ["validation_scenarios", "validation_routes", "validation_mechanics"]:
        rows = manifests[name]
        assert isinstance(rows, list)
        counts[name] = write_jsonl(args.output_dir / f"{name}.jsonl", rows)
        hashes[name] = stable_hash(rows)
    report = manifests["report"]
    assert isinstance(report, dict)
    write_json(args.output_dir / "report.json", report)
    write_json(
        args.output_dir / "manifest.json",
        {
            "schema": "bot_validation_scenario_manifests_v1",
            "source_config": str(args.config),
            "files": {name: {"path": f"{name}.jsonl", "rows": counts[name], "sha256": hashes[name]} for name in sorted(counts)},
            "runtime_ml_control": "disabled_until_live_clear_validation_passes",
        },
    )
    return 0 if not report["invalid_mechanic_profiles"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
