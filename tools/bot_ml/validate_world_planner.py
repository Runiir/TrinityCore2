from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

try:
    from .common import read_jsonl, stable_hash, write_json
except ImportError:
    from common import read_jsonl, stable_hash, write_json


STAGED_GATES = [
    "movement_smoke",
    "kill_quest",
    "collect_quest",
    "quest_hub_batching",
    "trainer_visit",
    "vendor_repair",
    "profession_recipe_acquisition",
    "material_farming",
    "smart_loot",
    "normal_dungeon_trash",
    "dungeon_boss",
    "full_stonecore_clear",
    "raid_trash",
    "raid_boss",
    "full_blackwing_descent_clear",
]


def load_manifest_dir(path: Path) -> dict[str, list[dict[str, Any]]]:
    names = [
        "quest_hubs",
        "quest_chains",
        "objective_clusters",
        "npc_index",
        "mob_index",
        "service_index",
        "trainer_index",
        "vendor_index",
        "item_source_index",
        "recipe_source_index",
        "material_source_index",
        "gathering_node_index",
        "travel_edges",
        "graveyard_index",
        "instance_entrance_index",
        "repair_point_index",
        "faction_restriction_index",
        "map_zone_index",
    ]
    return {name: read_jsonl(path / f"{name}.jsonl") for name in names}


def load_validation_scenario_dir(path: Path) -> dict[str, list[dict[str, Any]]]:
    names = [
        "validation_scenarios",
        "validation_routes",
        "validation_mechanics",
    ]
    return {name: read_jsonl(path / f"{name}.jsonl") for name in names}


def load_live_scenario_reports(path: Path | None) -> dict[str, dict[str, Any]]:
    if not path or not path.exists():
        return {}
    files = [path] if path.is_file() else sorted(path.glob("*.json"))
    reports: dict[str, dict[str, Any]] = {}
    for report_path in files:
        if report_path.name == "manifest.json":
            continue
        try:
            payload = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict):
            continue
        scenario_id = str(payload.get("scenario_id") or report_path.stem)
        if scenario_id:
            reports[scenario_id] = payload
    return reports


def manifest_file_evidence(root: Path, names: list[str]) -> dict[str, Any]:
    evidence: dict[str, Any] = {}
    manifest_path = root / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {}
    else:
        manifest = {}
    declared_files = manifest.get("files") if isinstance(manifest.get("files"), dict) else {}
    for name in names:
        file_meta = declared_files.get(name) if isinstance(declared_files.get(name), dict) else {}
        path = root / str(file_meta.get("path") or f"{name}.jsonl")
        rows = read_jsonl(path)
        evidence[name] = {
            "path": str(path),
            "exists": path.exists(),
            "rows": len(rows),
            "sha256": file_meta.get("sha256") or (stable_hash(rows) if path.exists() else ""),
        }
    return {
        "root": str(root),
        "manifest_path": str(manifest_path),
        "manifest_exists": manifest_path.exists(),
        "schema": manifest.get("schema", ""),
        "files": evidence,
    }


def has_service(services: list[dict[str, Any]], service_type: str) -> bool:
    return any(service_type in (row.get("service_types") or []) for row in services)


def has_objective_type(clusters: list[dict[str, Any]], objective_type: str) -> bool:
    return any(any(objective.get("type") == objective_type for objective in cluster.get("objectives") or []) for cluster in clusters)


def has_item_source_type(item_sources: list[dict[str, Any]], source_type: str) -> bool:
    return any(source_type in (row.get("source_types") or []) for row in item_sources)


def has_travel_edge(edges: list[dict[str, Any]], edge_type: str) -> bool:
    return any(edge.get("edge_type") == edge_type for edge in edges)


def scenario_ready(scenarios: list[dict[str, Any]], scenario_id: str) -> bool:
    return any(row.get("scenario_id") == scenario_id and bool(row.get("provisioning_ready")) for row in scenarios)


def has_route(routes: list[dict[str, Any]], scenario_id: str, kind: str | None = None) -> bool:
    return any(row.get("scenario_id") == scenario_id and (kind is None or row.get("kind") == kind) for row in routes)


def has_invalid_route_coordinates(routes: list[dict[str, Any]], scenario_id: str) -> bool:
    return any(row.get("scenario_id") == scenario_id and row.get("coordinates_valid") is False for row in routes)


def has_mechanics(mechanics: list[dict[str, Any]], scenario_id: str) -> bool:
    return any(row.get("scenario_id") == scenario_id and bool(row.get("valid", True)) and row.get("families") for row in mechanics)


def missing_validation_inputs(
    scenario_id: str,
    scenarios: list[dict[str, Any]],
    routes: list[dict[str, Any]],
    mechanics: list[dict[str, Any]],
    *,
    route_name: str,
    provision_name: str,
    mechanics_name: str | None = None,
    live_name: str,
) -> list[str]:
    missing: list[str] = []
    if not has_route(routes, scenario_id):
        missing.append(route_name)
    elif has_invalid_route_coordinates(routes, scenario_id):
        missing.append(f"{route_name}_coordinates")
    if not scenario_ready(scenarios, scenario_id):
        missing.append(provision_name)
    if mechanics_name and not has_mechanics(mechanics, scenario_id):
        missing.append(mechanics_name)
    missing.append(live_name)
    return missing


def scenario_report_bool(report: dict[str, Any], *keys: str) -> bool:
    return any(bool(report.get(key)) for key in keys)


def scenario_report_int(report: dict[str, Any], *keys: str) -> int:
    values: list[int] = []
    for key in keys:
        try:
            values.append(int(report.get(key) or 0))
        except (TypeError, ValueError):
            values.append(0)
    return max(values or [0])


def live_report_ready(report: dict[str, Any], requirement: str) -> bool:
    if not report:
        return False
    if not scenario_report_bool(report, "prepared_group", "group_ready", "provisioning_ready"):
        return False
    if requirement == "clear":
        return scenario_report_bool(report, "clear_complete", "all_passed", "scenario_passed")
    if requirement == "boss":
        return scenario_report_int(report, "boss_kills", "raid_boss_kills", "bosses_killed") > 0
    if requirement == "trash":
        return scenario_report_bool(report, "trash_cleared", "trash_passed") or scenario_report_int(report, "trash_pulls", "trash_kills", "trash_packs_cleared") > 0
    return False


def live_missing(static_missing: list[str], report: dict[str, Any], live_name: str, requirement: str) -> list[str]:
    missing = [item for item in static_missing if item != live_name]
    if not live_report_ready(report, requirement):
        missing.append(live_name)
    return missing


def gate_result(name: str, ok: bool, evidence: dict[str, Any], missing: list[str] | None = None) -> dict[str, Any]:
    return {
        "gate": name,
        "passed": bool(ok),
        "missing": missing or [],
        "evidence": evidence,
    }


def validate_manifest_coverage(
    manifests: dict[str, list[dict[str, Any]]],
    validation_manifests: dict[str, list[dict[str, Any]]] | None = None,
    live_reports: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    hubs = manifests["quest_hubs"]
    chains = manifests["quest_chains"]
    clusters = manifests["objective_clusters"]
    npc_index = manifests.get("npc_index") or []
    mob_index = manifests.get("mob_index") or []
    services = manifests["service_index"]
    trainer_index = manifests.get("trainer_index") or []
    vendor_index = manifests.get("vendor_index") or []
    item_sources = manifests["item_source_index"]
    recipe_sources = manifests["recipe_source_index"]
    material_sources = manifests["material_source_index"]
    gathering_node_index = manifests.get("gathering_node_index") or []
    travel_edges = manifests["travel_edges"]
    graveyard_index = manifests.get("graveyard_index") or []
    instance_entrance_index = manifests.get("instance_entrance_index") or []
    repair_point_index = manifests.get("repair_point_index") or []
    faction_restriction_index = manifests.get("faction_restriction_index") or []
    map_zone_index = manifests.get("map_zone_index") or []
    validation_manifests = validation_manifests or {}
    validation_scenarios = validation_manifests.get("validation_scenarios") or []
    validation_routes = validation_manifests.get("validation_routes") or []
    validation_mechanics = validation_manifests.get("validation_mechanics") or []
    live_reports = live_reports or {}
    stonecore_live = live_reports.get("stonecore_5n") or {}
    bwd_live = live_reports.get("blackwing_descent_10n") or {}

    evidence = {
        "quest_hubs": len(hubs),
        "quest_chains": len(chains),
        "objective_clusters": len(clusters),
        "npc_index": len(npc_index),
        "mob_index": len(mob_index),
        "service_index": len(services),
        "trainer_index": len(trainer_index),
        "vendor_index": len(vendor_index),
        "item_source_index": len(item_sources),
        "recipe_source_index": len(recipe_sources),
        "material_source_index": len(material_sources),
        "gathering_node_index": len(gathering_node_index),
        "travel_edges": len(travel_edges),
        "graveyard_index": len(graveyard_index),
        "instance_entrance_index": len(instance_entrance_index),
        "repair_point_index": len(repair_point_index),
        "faction_restriction_index": len(faction_restriction_index),
        "map_zone_index": len(map_zone_index),
        "validation_scenarios": len(validation_scenarios),
        "validation_routes": len(validation_routes),
        "validation_mechanics": len(validation_mechanics),
        "validation_scenario_ids": sorted({row.get("scenario_id") for row in validation_scenarios if row.get("scenario_id")}),
        "validation_route_scenario_ids": sorted({row.get("scenario_id") for row in validation_routes if row.get("scenario_id")}),
        "validation_mechanic_scenario_ids": sorted({row.get("scenario_id") for row in validation_mechanics if row.get("scenario_id")}),
        "live_scenario_ids": sorted(live_reports),
        "live_scenario_label_quality": {scenario_id: report.get("teacher_label_quality", "") for scenario_id, report in sorted(live_reports.items())},
        "objective_types": sorted({objective.get("type") for cluster in clusters for objective in (cluster.get("objectives") or []) if objective.get("type")}),
        "service_types": sorted({service_type for row in services for service_type in (row.get("service_types") or [])}),
        "item_source_types": sorted({source_type for row in item_sources for source_type in (row.get("source_types") or [])}),
        "recipe_source_types": sorted({source_type for row in recipe_sources for source_type in (row.get("source_types") or [])}),
        "material_source_types": sorted({source_type for row in material_sources for source_type in (row.get("source_types") or [])}),
        "travel_edge_types": sorted({edge.get("edge_type") for edge in travel_edges if edge.get("edge_type")}),
        "map_ids": sorted({row.get("map_id") for row in map_zone_index if row.get("map_id") is not None}),
        "zone_ids": sorted({row.get("zone_id") for row in map_zone_index if row.get("zone_id") is not None})[:256],
    }
    stonecore_missing = missing_validation_inputs(
        "stonecore_5n",
        validation_scenarios,
        validation_routes,
        validation_mechanics,
        route_name="stonecore_route_manifest",
        provision_name="prepared_5man_provisioning",
        live_name="stonecore_live_clear_report",
    )
    bwd_boss_missing = missing_validation_inputs(
        "blackwing_descent_10n",
        validation_scenarios,
        validation_routes,
        validation_mechanics,
        route_name="blackwing_descent_route_manifest",
        provision_name="prepared_10man_provisioning",
        mechanics_name="blackwing_descent_boss_mechanic_manifest",
        live_name="blackwing_descent_live_boss_report",
    )
    bwd_clear_missing = missing_validation_inputs(
        "blackwing_descent_10n",
        validation_scenarios,
        validation_routes,
        validation_mechanics,
        route_name="blackwing_descent_route_manifest",
        provision_name="prepared_10man_provisioning",
        mechanics_name="blackwing_descent_boss_mechanic_manifest",
        live_name="blackwing_descent_live_clear_report",
    )
    stonecore_live_missing = live_missing(stonecore_missing, stonecore_live, "stonecore_live_clear_report", "clear")
    bwd_boss_live_missing = live_missing(bwd_boss_missing, bwd_live, "blackwing_descent_live_boss_report", "boss")
    bwd_clear_live_missing = live_missing(bwd_clear_missing, bwd_live, "blackwing_descent_live_clear_report", "clear")

    gates = [
        gate_result("movement_smoke", bool(clusters or hubs or travel_edges), evidence, [] if clusters or hubs or travel_edges else ["objective_clusters_or_hubs_or_travel_edges"]),
        gate_result("kill_quest", has_objective_type(clusters, "creature"), evidence, [] if has_objective_type(clusters, "creature") else ["creature_objective_cluster"]),
        gate_result("collect_quest", has_objective_type(clusters, "item") and has_item_source_type(item_sources, "creature_loot"), evidence, [] if has_objective_type(clusters, "item") and has_item_source_type(item_sources, "creature_loot") else ["item_objective_cluster", "creature_loot_item_source"]),
        gate_result("quest_hub_batching", any(len(row.get("quests") or []) >= 1 for row in hubs), evidence, [] if hubs else ["quest_hubs"]),
        gate_result("trainer_visit", bool(trainer_index) or has_service(services, "trainer"), evidence, [] if bool(trainer_index) or has_service(services, "trainer") else ["trainer_service"]),
        gate_result("vendor_repair", (bool(vendor_index) or has_service(services, "vendor")) and (bool(repair_point_index) or has_service(services, "repair") or has_service(services, "vendor")), evidence, [] if bool(vendor_index) or has_service(services, "vendor") else ["vendor_service"]),
        gate_result("profession_recipe_acquisition", bool(recipe_sources), evidence, [] if recipe_sources else ["recipe_source_index"]),
        gate_result("material_farming", (bool(material_sources) or bool(gathering_node_index)) and (has_item_source_type(material_sources, "creature_loot") or has_item_source_type(material_sources, "gameobject_loot") or bool(gathering_node_index)), evidence, [] if material_sources or gathering_node_index else ["material_source_index_or_gathering_node_index"]),
        gate_result("smart_loot", bool(item_sources), evidence, [] if item_sources else ["item_source_index"]),
        gate_result("normal_dungeon_trash", has_travel_edge(travel_edges, "portal_or_instance_entrance") or bool(instance_entrance_index), evidence, [] if has_travel_edge(travel_edges, "portal_or_instance_entrance") or bool(instance_entrance_index) else ["instance_entrance_travel_edge"]),
        gate_result("dungeon_boss", has_travel_edge(travel_edges, "portal_or_instance_entrance") or bool(instance_entrance_index), evidence, [] if has_travel_edge(travel_edges, "portal_or_instance_entrance") or bool(instance_entrance_index) else ["instance_entrance_travel_edge"]),
        gate_result("full_stonecore_clear", not stonecore_live_missing, evidence, stonecore_live_missing),
        gate_result("raid_trash", has_travel_edge(travel_edges, "portal_or_instance_entrance") or bool(instance_entrance_index), evidence, [] if has_travel_edge(travel_edges, "portal_or_instance_entrance") or bool(instance_entrance_index) else ["raid_instance_entrance_travel_edge"]),
        gate_result("raid_boss", not bwd_boss_live_missing, evidence, bwd_boss_live_missing),
        gate_result("full_blackwing_descent_clear", not bwd_clear_live_missing, evidence, bwd_clear_live_missing),
    ]

    passed = sum(1 for gate in gates if gate["passed"])
    return {
        "schema": "bot_world_planner_validation_v1",
        "passed": passed,
        "failed": len(gates) - passed,
        "total": len(gates),
        "all_passed": passed == len(gates),
        "gates": gates,
        "evidence": evidence,
        "runtime_ml_control": "disabled_until_shadow_assist_replay_validation_passes",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate autonomous world/planner manifests against staged bot gates.")
    parser.add_argument("--planner-dir", type=Path, default=Path("dataset/world_planner"))
    parser.add_argument("--validation-scenario-dir", type=Path, default=Path("dataset/validation_scenarios"))
    parser.add_argument("--live-scenario-report-dir", type=Path, default=Path("dataset/live_validation_scenario_reports_built"))
    parser.add_argument("--report", type=Path, default=Path("dataset/world_planner/validation_report.json"))
    parser.add_argument("--fail-on-missing", action="store_true")
    args = parser.parse_args()

    planner_manifests = load_manifest_dir(args.planner_dir)
    validation_manifests = load_validation_scenario_dir(args.validation_scenario_dir)
    report = validate_manifest_coverage(planner_manifests, validation_manifests, load_live_scenario_reports(args.live_scenario_report_dir))
    report["dataset_inputs"] = {
        "planner": manifest_file_evidence(args.planner_dir, sorted(planner_manifests)),
        "validation_scenarios": manifest_file_evidence(args.validation_scenario_dir, sorted(validation_manifests)),
        "live_scenario_report_dir": str(args.live_scenario_report_dir),
        "live_scenario_report_files": sorted(str(path) for path in args.live_scenario_report_dir.glob("*.json")) if args.live_scenario_report_dir.exists() else [],
    }
    write_json(args.report, report)
    if args.fail_on_missing and not report["all_passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
