from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

try:
    from .common import read_jsonl, write_json
except ImportError:
    from common import read_jsonl, write_json


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
        "service_index",
        "item_source_index",
        "recipe_source_index",
        "material_source_index",
        "travel_edges",
    ]
    return {name: read_jsonl(path / f"{name}.jsonl") for name in names}


def load_validation_scenario_dir(path: Path) -> dict[str, list[dict[str, Any]]]:
    names = [
        "validation_scenarios",
        "validation_routes",
        "validation_mechanics",
    ]
    return {name: read_jsonl(path / f"{name}.jsonl") for name in names}


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
    if not scenario_ready(scenarios, scenario_id):
        missing.append(provision_name)
    if mechanics_name and not has_mechanics(mechanics, scenario_id):
        missing.append(mechanics_name)
    missing.append(live_name)
    return missing


def gate_result(name: str, ok: bool, evidence: dict[str, Any], missing: list[str] | None = None) -> dict[str, Any]:
    return {
        "gate": name,
        "passed": bool(ok),
        "missing": missing or [],
        "evidence": evidence,
    }


def validate_manifest_coverage(manifests: dict[str, list[dict[str, Any]]], validation_manifests: dict[str, list[dict[str, Any]]] | None = None) -> dict[str, Any]:
    hubs = manifests["quest_hubs"]
    chains = manifests["quest_chains"]
    clusters = manifests["objective_clusters"]
    services = manifests["service_index"]
    item_sources = manifests["item_source_index"]
    recipe_sources = manifests["recipe_source_index"]
    material_sources = manifests["material_source_index"]
    travel_edges = manifests["travel_edges"]
    validation_manifests = validation_manifests or {}
    validation_scenarios = validation_manifests.get("validation_scenarios") or []
    validation_routes = validation_manifests.get("validation_routes") or []
    validation_mechanics = validation_manifests.get("validation_mechanics") or []

    evidence = {
        "quest_hubs": len(hubs),
        "quest_chains": len(chains),
        "objective_clusters": len(clusters),
        "service_index": len(services),
        "item_source_index": len(item_sources),
        "recipe_source_index": len(recipe_sources),
        "material_source_index": len(material_sources),
        "travel_edges": len(travel_edges),
        "validation_scenarios": len(validation_scenarios),
        "validation_routes": len(validation_routes),
        "validation_mechanics": len(validation_mechanics),
        "validation_scenario_ids": sorted({row.get("scenario_id") for row in validation_scenarios if row.get("scenario_id")}),
        "validation_route_scenario_ids": sorted({row.get("scenario_id") for row in validation_routes if row.get("scenario_id")}),
        "validation_mechanic_scenario_ids": sorted({row.get("scenario_id") for row in validation_mechanics if row.get("scenario_id")}),
        "objective_types": sorted({objective.get("type") for cluster in clusters for objective in (cluster.get("objectives") or []) if objective.get("type")}),
        "service_types": sorted({service_type for row in services for service_type in (row.get("service_types") or [])}),
        "item_source_types": sorted({source_type for row in item_sources for source_type in (row.get("source_types") or [])}),
        "recipe_source_types": sorted({source_type for row in recipe_sources for source_type in (row.get("source_types") or [])}),
        "material_source_types": sorted({source_type for row in material_sources for source_type in (row.get("source_types") or [])}),
        "travel_edge_types": sorted({edge.get("edge_type") for edge in travel_edges if edge.get("edge_type")}),
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

    gates = [
        gate_result("movement_smoke", bool(clusters or hubs or travel_edges), evidence, [] if clusters or hubs or travel_edges else ["objective_clusters_or_hubs_or_travel_edges"]),
        gate_result("kill_quest", has_objective_type(clusters, "creature"), evidence, [] if has_objective_type(clusters, "creature") else ["creature_objective_cluster"]),
        gate_result("collect_quest", has_objective_type(clusters, "item") and has_item_source_type(item_sources, "creature_loot"), evidence, [] if has_objective_type(clusters, "item") and has_item_source_type(item_sources, "creature_loot") else ["item_objective_cluster", "creature_loot_item_source"]),
        gate_result("quest_hub_batching", any(len(row.get("quests") or []) >= 1 for row in hubs), evidence, [] if hubs else ["quest_hubs"]),
        gate_result("trainer_visit", has_service(services, "trainer"), evidence, [] if has_service(services, "trainer") else ["trainer_service"]),
        gate_result("vendor_repair", has_service(services, "vendor"), evidence, [] if has_service(services, "vendor") else ["vendor_service"]),
        gate_result("profession_recipe_acquisition", bool(recipe_sources), evidence, [] if recipe_sources else ["recipe_source_index"]),
        gate_result("material_farming", bool(material_sources) and (has_item_source_type(material_sources, "creature_loot") or has_item_source_type(material_sources, "gameobject_loot")), evidence, [] if material_sources else ["material_source_index"]),
        gate_result("smart_loot", bool(item_sources), evidence, [] if item_sources else ["item_source_index"]),
        gate_result("normal_dungeon_trash", has_travel_edge(travel_edges, "portal_or_instance_entrance"), evidence, [] if has_travel_edge(travel_edges, "portal_or_instance_entrance") else ["instance_entrance_travel_edge"]),
        gate_result("dungeon_boss", has_travel_edge(travel_edges, "portal_or_instance_entrance"), evidence, [] if has_travel_edge(travel_edges, "portal_or_instance_entrance") else ["instance_entrance_travel_edge"]),
        gate_result("full_stonecore_clear", False, evidence, stonecore_missing),
        gate_result("raid_trash", has_travel_edge(travel_edges, "portal_or_instance_entrance"), evidence, [] if has_travel_edge(travel_edges, "portal_or_instance_entrance") else ["raid_instance_entrance_travel_edge"]),
        gate_result("raid_boss", False, evidence, bwd_boss_missing),
        gate_result("full_blackwing_descent_clear", False, evidence, bwd_clear_missing),
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
    parser.add_argument("--report", type=Path, default=Path("dataset/world_planner/validation_report.json"))
    parser.add_argument("--fail-on-missing", action="store_true")
    args = parser.parse_args()

    report = validate_manifest_coverage(load_manifest_dir(args.planner_dir), load_validation_scenario_dir(args.validation_scenario_dir))
    write_json(args.report, report)
    if args.fail_on_missing and not report["all_passed"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
