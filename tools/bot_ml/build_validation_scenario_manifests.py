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

MECHANIC_EVIDENCE_REQUIREMENTS = {
    "trash_pack": ["pulls"],
    "caster_pack": ["pulls", "interrupts"],
    "healer_mob": ["target_priority", "interrupts"],
    "patrol_risk": ["pulls", "regrouping"],
    "cleave_risk": ["tank_positioning", "healer_assignments"],
    "interrupt_required": ["interrupts"],
    "dispel_required": ["healer_assignments"],
    "tank_buster": ["tank_positioning", "healer_assignments"],
    "raid_aoe": ["healer_assignments", "regrouping"],
    "ground_danger": ["tank_positioning", "regrouping"],
    "stack": ["regrouping", "healer_assignments"],
    "spread": ["regrouping"],
    "adds": ["target_priority", "pulls"],
    "target_switch": ["target_priority"],
    "enrage": ["target_priority", "interrupts"],
    "movement_check": ["tank_positioning", "regrouping"],
    "boss_phase": ["target_priority", "pulls"],
    "wipe_risk": ["recovery", "instance_reset"],
}

EVIDENCE_ACTIONS = {
    "party_formation": ["party_formed", "raid_formed", "validation_group_formed"],
    "raid_formation": ["raid_formed", "validation_group_formed"],
    "role_assignments": ["role_assignment", "validation_role_assignment", "tank_assigned", "healer_assigned", "raid_role_assignment"],
    "pulls": ["trash_action", "validation_route_trash_action", "boss_started", "boss_action", "validation_route_pull"],
    "target_priority": ["target_priority", "target_switch", "validation_target_priority", "assist_target_search_authoritative_focus", "raid_add_wave", "raid_boss_action"],
    "interrupts": ["interrupt", "interrupt_success", "assigned_interrupt_success", "validation_interrupt", "raid_interrupt"],
    "healer_assignments": ["healer_assignment", "validation_route_group_heal", "trash_heal", "external_defensive", "raid_healer_cooldown"],
    "tank_positioning": ["validation_route_tank_boss", "tank_positioning", "force_tank_focus", "move_to_validation_route_assist_target", "raid_position_anchor", "raid_boss_action"],
    "regrouping": ["validation_route_regroup", "regroup", "validation_route_hold_anchor", "move_to_validation_route_focus", "raid_position_anchor", "validation_route_complete"],
    "recovery": ["stuck_detected", "unstuck", "death", "dead_recovery", "validation_route_recovery", "raid_wipe"],
    "instance_reset": ["instance_reset"],
}


def group_kind(required_roles: dict[str, int], difficulty: str) -> str:
    return "raid" if sum(required_roles.values()) >= 10 or "raid" in difficulty or "10" in difficulty else "party"


def role_assignment_contract(required_roles: dict[str, int], provisioned_roles: dict[str, int]) -> dict[str, Any]:
    assignments = []
    for role in ["tank", "healer", "dps"]:
        expected = int(required_roles.get(role) or 0)
        assignments.append(
            {
                "role": role,
                "required": expected,
                "provisioned": int(provisioned_roles.get(role) or 0),
                "evidence_actions": EVIDENCE_ACTIONS["role_assignments"],
            }
        )
    return {
        "required_roles": required_roles,
        "provisioned_roles": provisioned_roles,
        "assignments": assignments,
        "evidence_actions": EVIDENCE_ACTIONS["role_assignments"],
    }


def mechanic_required_evidence(families: list[str]) -> list[str]:
    required: list[str] = []
    for family in families:
        for evidence_name in MECHANIC_EVIDENCE_REQUIREMENTS.get(family, []):
            if evidence_name not in required:
                required.append(evidence_name)
    return required


def route_required_evidence(kind: str, families: list[str]) -> list[str]:
    required = ["pulls"] if kind in {"trash", "boss"} else []
    if kind == "boss":
        required.extend(["tank_positioning", "healer_assignments"])
    if kind in {"travel", "regroup", "descent"}:
        required.append("regrouping")
    for evidence_name in mechanic_required_evidence(families):
        if evidence_name not in required:
            required.append(evidence_name)
    return required


STONECORE_TRASH_PACKS = {
    "crystalspawn corridor": [42810, 42696, 43430, 43537, 42695, 42692],
    "stonecore sentry gauntlet": [42428, 42696, 42695, 42692],
    "twilight flayer packs": [42808],
}

STONECORE_SCRIPTED_EVENT_ACTORS = {
    "Corborus approach corridor": [43391],
}


def route_node_kind(step: dict[str, Any]) -> str:
    explicit = str(step.get("node_kind") or "")
    if explicit:
        return explicit
    if step.get("kind") in {"travel", "regroup", "descent"}:
        return str(step.get("kind"))
    return "boss" if step.get("kind") == "boss" else "trash_cluster"


def pack_target_entries(scenario_id: str, step: dict[str, Any]) -> list[int]:
    if route_node_kind(step) == "discovery_leg":
        return []
    explicit = [int(entry) for entry in (step.get("pack_target_entries") or []) if int(entry)]
    if explicit:
        return sorted(set(explicit))
    if step.get("kind") != "trash":
        return []
    label = str(step.get("label") or "")
    entries = list(STONECORE_TRASH_PACKS.get(label, [])) if scenario_id == "stonecore_5n" else []
    scripted_entries = set(scripted_event_entries(scenario_id, step))
    entries = [entry for entry in entries if entry not in scripted_entries]
    source_entry = int(step.get("source_entry") or 0)
    if source_entry and source_entry not in entries:
        entries.insert(0, source_entry)
    return entries


def scripted_event_entries(scenario_id: str, step: dict[str, Any]) -> list[int]:
    explicit = [int(entry) for entry in (step.get("scripted_event_entries") or []) if int(entry)]
    if explicit:
        return sorted(set(explicit))
    if step.get("kind") != "trash" or scenario_id != "stonecore_5n":
        return []
    return list(STONECORE_SCRIPTED_EVENT_ACTORS.get(str(step.get("label") or ""), []))


def expected_alive_count(step: dict[str, Any], cluster_entries: list[int]) -> int:
    explicit = int(step.get("expected_alive_count") or 0)
    return explicit if explicit > 0 else len(cluster_entries)


def evidence_contract(required_evidence: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "evidence": evidence_name,
            "actions": EVIDENCE_ACTIONS.get(evidence_name, []),
            "required": True,
        }
        for evidence_name in required_evidence
    ]


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


def route_navigation_anchor_status(step: dict[str, Any]) -> tuple[bool, str]:
    anchor = step.get("navigation_anchor")
    if anchor is None:
        return route_coordinate_status(step)
    if not isinstance(anchor, dict):
        return False, "navigation_anchor_not_object"
    if not all(key in anchor for key in ("x", "y", "z")):
        return False, "navigation_anchor_missing_xyz"
    return route_coordinate_status(anchor)


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
        difficulty = str(scenario.get("difficulty") or "")
        scenario_group_kind = group_kind(required_roles, difficulty)
        scenario_required_evidence = ["role_assignments", "party_formation" if scenario_group_kind == "party" else "raid_formation"]
        if any(step.get("kind") in {"trash", "boss"} for step in route_steps):
            scenario_required_evidence.extend(["pulls", "regrouping", "recovery"])
            if scenario_group_kind == "raid":
                scenario_required_evidence.append("instance_reset")
        if not verification_ready:
            missing.append("provisioning_verifier_ready")
        invalid_route_steps = [
            {
                "step": int(step.get("step") or 0),
                "kind": step.get("kind") or "unknown",
                "label": step.get("label") or "",
                "reason": route_coordinate_status(step)[1] or route_navigation_anchor_status(step)[1],
            }
            for step in route_steps
            if not route_coordinate_status(step)[0] or not route_navigation_anchor_status(step)[0]
        ]
        if invalid_route_steps:
            missing.append("route_coordinates")

        scenario_row = {
            "scenario_id": scenario_id,
            "instance": scenario.get("instance") or "",
            "map_id": int(scenario.get("map_id") or 0),
            "difficulty": scenario.get("difficulty") or "",
            "group_kind": scenario_group_kind,
            "provisioning_scenario_id": provision_id,
            "required_roles": required_roles,
            "role_assignment": role_assignment_contract(required_roles, provisioned_roles),
            "expected_bot_count": expected_bot_count,
            "provisioning_ready": bool(ready and verification_ready),
            "missing": sorted(set(missing)),
            "route_step_count": len(route_steps),
            "boss_count": sum(1 for step in route_steps if step.get("kind") == "boss"),
            "trash_cluster_count": sum(1 for step in route_steps if step.get("kind") == "trash"),
            "mechanic_profile_count": len(profiles),
            "route_coordinates_ready": not invalid_route_steps,
            "invalid_route_steps": invalid_route_steps,
            "required_evidence": scenario_required_evidence,
            "evidence_contract": evidence_contract(scenario_required_evidence),
        }
        scenario_row["scenario_hash"] = stable_hash(scenario_row)[:16]
        scenarios.append(scenario_row)

        for step in route_steps:
            coordinates_valid, coordinate_missing_reason = route_coordinate_status(step)
            family_rows = [str(family) for family in profiles.get(step.get("mechanic_profile") or "", [])]
            route_evidence = route_required_evidence(str(step.get("kind") or ""), family_rows)
            node_kind = route_node_kind(step)
            cluster_entries = pack_target_entries(scenario_id, step)
            event_entries = scripted_event_entries(scenario_id, step)
            event_transition_aura_ids = [int(aura_id) for aura_id in (step.get("scripted_event_transition_aura_ids") or []) if int(aura_id)]
            cluster_radius_yards = 0.0 if node_kind == "discovery_leg" else float(step.get("cluster_radius_yards") or (90.0 if step.get("kind") == "trash" else 0.0))
            navigation_anchor = step.get("navigation_anchor") or step
            route = {
                "scenario_id": scenario_id,
                "map_id": int(scenario.get("map_id") or 0),
                "step": int(step.get("step") or 0),
                "kind": step.get("kind") or "unknown",
                "node_kind": node_kind,
                "label": step.get("label") or "",
                "mechanic_profile": step.get("mechanic_profile") or "",
                "x": float(step.get("x") or 0.0),
                "y": float(step.get("y") or 0.0),
                "z": float(step.get("z") or 0.0),
                "o": float(step.get("o") or step.get("orientation") or 0.0),
                "navigation_anchor_x": float(navigation_anchor.get("x") or 0.0),
                "navigation_anchor_y": float(navigation_anchor.get("y") or 0.0),
                "navigation_anchor_z": float(navigation_anchor.get("z") or 0.0),
                "navigation_anchor_o": float(navigation_anchor.get("o") or navigation_anchor.get("orientation") or 0.0),
                "source_entry": int(step.get("source_entry") or 0),
                "source_guid": str(step.get("source_guid") or ""),
                "source_table": step.get("source_table") or "",
                "source_sql": step.get("source_sql") or "",
                "cluster_id": step.get("cluster_id") or (f"{scenario_id}_{int(step.get('step') or 0):02d}_{node_kind}" if node_kind == "trash_cluster" else ""),
                "cluster_center": [float(step.get("x") or 0.0), float(step.get("y") or 0.0), float(step.get("z") or 0.0)],
                "cluster_radius_yards": cluster_radius_yards,
                "pack_target_entries": cluster_entries,
                "scripted_event_entries": event_entries,
                "scripted_event_transition_aura_ids": event_transition_aura_ids,
                "scripted_event_require_passive": bool(step.get("scripted_event_require_passive")),
                "hazard_source_entry": int(step.get("hazard_source_entry") or 0),
                "hazard_detection_spell_id": int(step.get("hazard_detection_spell_id") or 0),
                "hazard_damage_spell_id": int(step.get("hazard_damage_spell_id") or 0),
                "hazard_shape": str(step.get("hazard_shape") or ""),
                "hazard_radius_yards": float(step.get("hazard_radius_yards") or 0.0),
                "hazard_safety_margin_yards": float(step.get("hazard_safety_margin_yards") or 0.0),
                "expected_alive_count_semantics": "descriptive_only",
                "completion_policy": step.get("completion_policy") or ("cluster_clear_after_pull" if node_kind in {"trash_cluster", "discovery_leg"} else ("arrival" if node_kind in {"travel", "regroup", "descent"} else "boss_kill")),
                "coordinates_valid": coordinates_valid,
                "coordinate_missing_reason": coordinate_missing_reason,
                "mechanic_families": family_rows,
                "required_evidence": route_evidence,
                "evidence_contract": evidence_contract(route_evidence),
                "pull_contract": {
                    "required": str(step.get("kind") or "") in {"trash", "boss"},
                    "kind": step.get("kind") or "unknown",
                    "actions": EVIDENCE_ACTIONS["pulls"],
                },
                "target_priority": {
                    "required": "target_priority" in route_evidence,
                    "source_entry": int(step.get("source_entry") or 0),
                    "opener_target_entry": int(step.get("opener_target_entry") or 0),
                    "actions": EVIDENCE_ACTIONS["target_priority"],
                },
                "interrupt_assignments": {
                    "required": "interrupts" in route_evidence,
                    "actions": EVIDENCE_ACTIONS["interrupts"],
                },
                "healer_assignments": {
                    "required": "healer_assignments" in route_evidence,
                    "actions": EVIDENCE_ACTIONS["healer_assignments"],
                },
                "tank_positioning": {
                    "required": "tank_positioning" in route_evidence,
                    "actions": EVIDENCE_ACTIONS["tank_positioning"],
                },
                "regrouping": {
                    "required": "regrouping" in route_evidence,
                    "actions": EVIDENCE_ACTIONS["regrouping"],
                },
                "recovery": {
                    "required": "recovery" in route_evidence,
                    "actions": EVIDENCE_ACTIONS["recovery"],
                },
                "instance_reset": {
                    "required": "instance_reset" in route_evidence,
                    "actions": EVIDENCE_ACTIONS["instance_reset"],
                },
            }
            if node_kind != "discovery_leg":
                route["expected_alive_count"] = expected_alive_count(step, cluster_entries)
            route["route_node_id"] = stable_hash(route)[:16]
            route["expected_bot_count"] = expected_bot_count
            alternate_target_entries = []
            for entry in step.get("alternate_target_entries") or []:
                entry_id = int(entry or 0)
                if entry_id > 0 and entry_id not in alternate_target_entries:
                    alternate_target_entries.append(entry_id)
            route["alternate_target_entries"] = alternate_target_entries
            route["target_priority"]["alternate_target_entries"] = alternate_target_entries
            route["add_target_entries"] = sorted({int(entry) for entry in step.get("add_target_entries") or [] if int(entry) > 0})
            scenario_start = scenario.get("start_position") or {}
            bot_start = step.get("bot_start") or scenario_start
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
            required_evidence = mechanic_required_evidence(family_rows)
            mechanic = {
                "scenario_id": scenario_id,
                "mechanic_profile": str(profile),
                "families": family_rows,
                "unknown_families": unknown,
                "required_evidence": required_evidence,
                "evidence_contract": evidence_contract(required_evidence),
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
        "runtime_ml_control": "offline_shadow_only",
        "control_eligible": False,
        "evidence_surfaces": sorted(EVIDENCE_ACTIONS),
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
            "runtime_ml_control": "offline_shadow_only",
            "control_eligible": False,
        },
    )
    return 0 if not report["invalid_mechanic_profiles"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
