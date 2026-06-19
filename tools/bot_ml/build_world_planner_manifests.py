from __future__ import annotations

import argparse
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

try:
    from .common import read_jsonl, stable_hash, write_json, write_jsonl
except ImportError:
    from common import read_jsonl, stable_hash, write_json, write_jsonl


def first_spawn(entity: dict[str, Any]) -> dict[str, Any] | None:
    spawns = entity.get("spawns")
    if isinstance(spawns, list) and spawns:
        spawn = spawns[0]
        if isinstance(spawn, dict):
            return spawn
    return None


def distance2d(left: dict[str, Any], right: dict[str, Any]) -> float:
    return math.hypot(float(left.get("x") or 0.0) - float(right.get("x") or 0.0), float(left.get("y") or 0.0) - float(right.get("y") or 0.0))


def objective_anchor(objective: dict[str, Any], quest_by_id: dict[int, dict[str, Any]]) -> dict[str, Any] | None:
    if objective.get("type") in {"creature", "gameobject"}:
        return first_spawn(objective)
    quest = quest_by_id.get(int(objective.get("quest_id") or 0), {})
    poi = quest.get("poi") if isinstance(quest.get("poi"), dict) else {}
    if poi and (float(poi.get("x") or 0.0) or float(poi.get("y") or 0.0)):
        return {"map_id": int(poi.get("map_id") or 0), "zone_id": int(quest.get("sort_id") or 0), "area_id": 0, "x": float(poi.get("x") or 0.0), "y": float(poi.get("y") or 0.0), "z": 0.0}
    giver = first_spawn((quest.get("givers") or [{}])[0]) if quest.get("givers") else None
    return giver


def build_quest_hubs(quests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    hubs: dict[tuple[int, int, int, int], dict[str, Any]] = {}
    for quest in quests:
        for giver in quest.get("givers") or []:
            spawn = first_spawn(giver)
            if not spawn:
                continue
            key = (int(spawn.get("map_id") or 0), int(spawn.get("zone_id") or 0), int(spawn.get("area_id") or 0), int(giver.get("entry") or 0))
            hub = hubs.setdefault(
                key,
                {
                    "hub_id": stable_hash({"kind": "quest_hub", "key": key})[:16],
                    "giver_type": giver.get("type") or "unknown",
                    "giver_entry": int(giver.get("entry") or 0),
                    "map_id": key[0],
                    "zone_id": key[1],
                    "area_id": key[2],
                    "x": float(spawn.get("x") or 0.0),
                    "y": float(spawn.get("y") or 0.0),
                    "z": float(spawn.get("z") or 0.0),
                    "quests": [],
                },
            )
            hub["quests"].append(int(quest.get("quest_id") or 0))
    return sorted(hubs.values(), key=lambda row: (row["map_id"], row["zone_id"], row["area_id"], row["giver_entry"]))


def build_quest_chains(quests: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    quest_ids = {int(quest.get("quest_id") or 0) for quest in quests}
    for quest in quests:
        quest_id = int(quest.get("quest_id") or 0)
        prev_id = int(quest.get("prev_quest_id") or 0)
        next_id = int(quest.get("next_quest_id") or 0)
        breadcrumb_id = int(quest.get("breadcrumb_for_quest_id") or 0)
        if prev_id or next_id or breadcrumb_id:
            rows.append(
                {
                    "quest_id": quest_id,
                    "prev_quest_id": prev_id,
                    "next_quest_id": next_id,
                    "breadcrumb_for_quest_id": breadcrumb_id,
                    "prev_known": prev_id in quest_ids if prev_id else False,
                    "next_known": next_id in quest_ids if next_id else False,
                    "breadcrumb_known": breadcrumb_id in quest_ids if breadcrumb_id else False,
                }
            )
    return sorted(rows, key=lambda row: row["quest_id"])


def build_objective_clusters(quests: list[dict[str, Any]], objectives: list[dict[str, Any]], radius: float = 120.0) -> list[dict[str, Any]]:
    quest_by_id = {int(quest.get("quest_id") or 0): quest for quest in quests}
    clusters: list[dict[str, Any]] = []
    for objective in objectives:
        anchor = objective_anchor(objective, quest_by_id)
        if not anchor:
            continue
        placed = None
        for cluster in clusters:
            if int(cluster["map_id"]) == int(anchor.get("map_id") or 0) and distance2d(cluster, anchor) <= radius:
                placed = cluster
                break
        if placed is None:
            placed = {
                "cluster_id": stable_hash({"kind": "objective_cluster", "anchor": anchor, "index": len(clusters)})[:16],
                "map_id": int(anchor.get("map_id") or 0),
                "zone_id": int(anchor.get("zone_id") or 0),
                "area_id": int(anchor.get("area_id") or 0),
                "x": float(anchor.get("x") or 0.0),
                "y": float(anchor.get("y") or 0.0),
                "z": float(anchor.get("z") or 0.0),
                "objectives": [],
                "quests": [],
            }
            clusters.append(placed)
        placed["objectives"].append(
            {
                "quest_id": int(objective.get("quest_id") or 0),
                "type": objective.get("type") or "unknown",
                "entry": int(objective.get("entry") or 0),
                "item_id": int(objective.get("item_id") or 0),
                "spell_id": int(objective.get("spell_id") or 0),
                "required_count": int(objective.get("required_count") or 0),
            }
        )
        quest_id = int(objective.get("quest_id") or 0)
        if quest_id and quest_id not in placed["quests"]:
            placed["quests"].append(quest_id)
    for cluster in clusters:
        cluster["objective_count"] = len(cluster["objectives"])
        cluster["quests"] = sorted(cluster["quests"])
    return sorted(clusters, key=lambda row: (row["map_id"], row["zone_id"], row["area_id"], row["x"], row["y"]))


def build_service_index(services: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for service in services:
        spawn = first_spawn(service)
        rows.append(
            {
                "entry": int(service.get("entry") or 0),
                "service_types": service.get("service_types") or [],
                "map_id": int((spawn or {}).get("map_id") or 0),
                "zone_id": int((spawn or {}).get("zone_id") or 0),
                "area_id": int((spawn or {}).get("area_id") or 0),
                "x": float((spawn or {}).get("x") or 0.0),
                "y": float((spawn or {}).get("y") or 0.0),
                "z": float((spawn or {}).get("z") or 0.0),
                "vendor_item_count": len(service.get("vendor_items") or []),
                "trainer_spell_count": len(service.get("trainer_spells") or []),
                "can_repair": "repair" in (service.get("service_types") or []),
                "faction": int(service.get("faction") or 0),
                "vendor_items": [int(row.get("item") or row.get("item_id") or 0) for row in service.get("vendor_items") or []],
                "trainer_spells": [int(row.get("spell_id") or 0) for row in service.get("trainer_spells") or []],
            }
        )
    return sorted(rows, key=lambda row: (row["map_id"], row["zone_id"], row["entry"]))


def build_npc_index(npcs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for npc in npcs:
        spawn = first_spawn(npc)
        rows.append(
            {
                "entry": int(npc.get("entry") or 0),
                "name": npc.get("name") or "",
                "service_types": npc.get("service_types") or [],
                "creature_type": int(npc.get("creature_type") or 0),
                "rank": int(npc.get("rank") or 0),
                "faction": int(npc.get("faction") or 0),
                "spawn_count": len(npc.get("spawns") or []),
                "map_id": int((spawn or {}).get("map_id") or 0),
                "zone_id": int((spawn or {}).get("zone_id") or 0),
                "area_id": int((spawn or {}).get("area_id") or 0),
                "x": float((spawn or {}).get("x") or 0.0),
                "y": float((spawn or {}).get("y") or 0.0),
                "z": float((spawn or {}).get("z") or 0.0),
            }
        )
    return sorted(rows, key=lambda row: (row["map_id"], row["zone_id"], row["entry"]))


def build_mob_index(mobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for mob in mobs:
        spawn = first_spawn(mob)
        rows.append(
            {
                "entry": int(mob.get("entry") or 0),
                "name": mob.get("name") or "",
                "creature_type": int(mob.get("creature_type") or 0),
                "rank": int(mob.get("rank") or 0),
                "faction": int(mob.get("faction") or 0),
                "spawn_count": len(mob.get("spawns") or []),
                "map_id": int((spawn or {}).get("map_id") or 0),
                "zone_id": int((spawn or {}).get("zone_id") or 0),
                "area_id": int((spawn or {}).get("area_id") or 0),
                "x": float((spawn or {}).get("x") or 0.0),
                "y": float((spawn or {}).get("y") or 0.0),
                "z": float((spawn or {}).get("z") or 0.0),
            }
        )
    return sorted(rows, key=lambda row: (row["map_id"], row["zone_id"], row["entry"]))


def build_trainer_index(trainers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for trainer in trainers:
        spawn = first_spawn(trainer)
        spells = trainer.get("trainer_spells") or []
        rows.append(
            {
                "entry": int(trainer.get("entry") or 0),
                "trainer_ids": sorted({int(trainer_id or 0) for trainer_id in trainer.get("trainer_ids") or [] if int(trainer_id or 0)}),
                "trainer_spells": sorted({int(row.get("spell_id") or 0) for row in spells if int(row.get("spell_id") or 0)}),
                "profession_skill_ids": sorted({int(row.get("req_skill_line") or 0) for row in spells if int(row.get("req_skill_line") or 0)}),
                "min_req_level": min([int(row.get("req_level") or 0) for row in spells if int(row.get("req_level") or 0)] or [0]),
                "map_id": int((spawn or {}).get("map_id") or 0),
                "zone_id": int((spawn or {}).get("zone_id") or 0),
                "area_id": int((spawn or {}).get("area_id") or 0),
                "x": float((spawn or {}).get("x") or 0.0),
                "y": float((spawn or {}).get("y") or 0.0),
                "z": float((spawn or {}).get("z") or 0.0),
            }
        )
    return sorted(rows, key=lambda row: (row["map_id"], row["zone_id"], row["entry"]))


def build_vendor_index(vendors: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for vendor in vendors:
        spawn = first_spawn(vendor)
        items = [int(row.get("item") or row.get("item_id") or 0) for row in vendor.get("vendor_items") or []]
        rows.append(
            {
                "entry": int(vendor.get("entry") or 0),
                "item_count": len([item for item in items if item]),
                "vendor_items": sorted({item for item in items if item}),
                "faction": int(vendor.get("faction") or 0),
                "map_id": int((spawn or {}).get("map_id") or 0),
                "zone_id": int((spawn or {}).get("zone_id") or 0),
                "area_id": int((spawn or {}).get("area_id") or 0),
                "x": float((spawn or {}).get("x") or 0.0),
                "y": float((spawn or {}).get("y") or 0.0),
                "z": float((spawn or {}).get("z") or 0.0),
            }
        )
    return sorted(rows, key=lambda row: (row["map_id"], row["zone_id"], row["entry"]))


def build_item_source_index(item_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for source in item_sources:
        item_id = int(source.get("item_id") or 0)
        if not item_id:
            continue
        row = grouped.setdefault(item_id, {"item_id": item_id, "sources": [], "source_types": []})
        source_type = source.get("source_type") or "unknown"
        row["sources"].append(source)
        if source_type not in row["source_types"]:
            row["source_types"].append(source_type)
    for row in grouped.values():
        row["source_types"] = sorted(row["source_types"])
        row["source_count"] = len(row["sources"])
    return sorted(grouped.values(), key=lambda row: row["item_id"])


def build_recipe_source_index(recipe_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for source in recipe_sources:
        recipe_spell_id = int(source.get("recipe_spell_id") or 0)
        item_id = int(source.get("item_id") or 0)
        key = f"spell:{recipe_spell_id}" if recipe_spell_id else f"item:{item_id}"
        if key in {"spell:0", "item:0"}:
            continue
        row = grouped.setdefault(
            key,
            {
                "recipe_key": key,
                "recipe_spell_id": recipe_spell_id,
                "item_id": item_id,
                "profession_skill_ids": [],
                "source_types": [],
                "sources": [],
            },
        )
        profession_skill_id = int(source.get("profession_skill_id") or 0)
        if profession_skill_id and profession_skill_id not in row["profession_skill_ids"]:
            row["profession_skill_ids"].append(profession_skill_id)
        source_type = source.get("source_type") or "unknown"
        if source_type not in row["source_types"]:
            row["source_types"].append(source_type)
        row["sources"].append(source)
    for row in grouped.values():
        row["profession_skill_ids"] = sorted(row["profession_skill_ids"])
        row["source_types"] = sorted(row["source_types"])
        row["source_count"] = len(row["sources"])
    return sorted(grouped.values(), key=lambda row: (row["recipe_spell_id"] == 0, row["recipe_spell_id"], row["item_id"]))


def build_material_source_index(material_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for source in material_sources:
        item_id = int(source.get("item_id") or 0)
        if not item_id:
            continue
        spawn = first_spawn(source)
        row = grouped.setdefault(item_id, {"item_id": item_id, "source_types": [], "sources": [], "nearest_source": None})
        source_type = source.get("source_type") or "unknown"
        if source_type not in row["source_types"]:
            row["source_types"].append(source_type)
        compact = {
            "source_type": source_type,
            "source_entry": int(source.get("source_entry") or 0),
            "chance": float(source.get("chance") or 0.0),
            "quest_required": int(source.get("quest_required") or 0),
            "map_id": int((spawn or {}).get("map_id") or 0),
            "zone_id": int((spawn or {}).get("zone_id") or 0),
            "area_id": int((spawn or {}).get("area_id") or 0),
            "x": float((spawn or {}).get("x") or 0.0),
            "y": float((spawn or {}).get("y") or 0.0),
            "z": float((spawn or {}).get("z") or 0.0),
        }
        row["sources"].append(compact)
        if row["nearest_source"] is None or (compact["map_id"], compact["zone_id"], compact["source_entry"]) < (
            int(row["nearest_source"].get("map_id") or 0),
            int(row["nearest_source"].get("zone_id") or 0),
            int(row["nearest_source"].get("source_entry") or 0),
        ):
            row["nearest_source"] = compact
    for row in grouped.values():
        row["source_types"] = sorted(row["source_types"])
        row["source_count"] = len(row["sources"])
    return sorted(grouped.values(), key=lambda row: row["item_id"])


def build_gathering_node_index(gathering_nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[int, dict[str, Any]] = {}
    for node in gathering_nodes:
        entry = int(node.get("entry") or 0)
        if not entry:
            continue
        spawn = first_spawn(node)
        row = grouped.setdefault(
            entry,
            {
                "entry": entry,
                "name": node.get("name") or "",
                "gameobject_type": int(node.get("gameobject_type") or 0),
                "loot_item_ids": [],
                "node_count": 0,
                "map_id": int((spawn or {}).get("map_id") or 0),
                "zone_id": int((spawn or {}).get("zone_id") or 0),
                "area_id": int((spawn or {}).get("area_id") or 0),
                "x": float((spawn or {}).get("x") or 0.0),
                "y": float((spawn or {}).get("y") or 0.0),
                "z": float((spawn or {}).get("z") or 0.0),
            },
        )
        item_id = int(node.get("loot_item_id") or 0)
        if item_id and item_id not in row["loot_item_ids"]:
            row["loot_item_ids"].append(item_id)
        row["node_count"] += len(node.get("spawns") or [])
    for row in grouped.values():
        row["loot_item_ids"] = sorted(row["loot_item_ids"])
    return sorted(grouped.values(), key=lambda row: (row["map_id"], row["zone_id"], row["entry"]))


def build_travel_edges(travel: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for entry in travel:
        if entry.get("type") == "areatrigger_teleport":
            dest = entry.get("destination") or {}
            rows.append(
                {
                    "edge_type": "portal_or_instance_entrance",
                    "source_id": int(entry.get("id") or 0),
                    "name": entry.get("name") or "",
                    "to_map_id": int(dest.get("map_id") or 0),
                    "to_x": float(dest.get("x") or 0.0),
                    "to_y": float(dest.get("y") or 0.0),
                    "to_z": float(dest.get("z") or 0.0),
                    "requires_discovery": False,
                }
            )
        elif entry.get("type") in {"transport", "graveyard", "taxi_level"}:
            rows.append({"edge_type": entry.get("type"), "raw": entry})
    return rows


def build_graveyard_index(graveyards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for graveyard in graveyards:
        rows.append(
            {
                "id": int(graveyard.get("ID") or graveyard.get("id") or 0),
                "ghost_zone": int(graveyard.get("GhostZone") or graveyard.get("ghost_zone") or 0),
                "faction": int(graveyard.get("Faction") or graveyard.get("faction") or 0),
                "comment": graveyard.get("Comment") or graveyard.get("comment") or "",
                "raw": graveyard,
            }
        )
    return sorted(rows, key=lambda row: (row["ghost_zone"], row["id"], row["faction"]))


def build_instance_entrance_index(instance_entrances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for entrance in instance_entrances:
        dest = entrance.get("destination") or {}
        rows.append(
            {
                "entrance_id": int(entrance.get("id") or entrance.get("ID") or 0),
                "name": entrance.get("name") or entrance.get("Name") or "",
                "to_map_id": int(dest.get("map_id") or 0),
                "to_x": float(dest.get("x") or 0.0),
                "to_y": float(dest.get("y") or 0.0),
                "to_z": float(dest.get("z") or 0.0),
            }
        )
    return sorted(rows, key=lambda row: (row["to_map_id"], row["entrance_id"]))


def build_repair_point_index(repair_points: list[dict[str, Any]], services: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source = repair_points or [service for service in services if "repair" in (service.get("service_types") or [])]
    rows = []
    for repair in source:
        spawn = first_spawn(repair)
        rows.append(
            {
                "entry": int(repair.get("entry") or 0),
                "name": repair.get("name") or "",
                "faction": int(repair.get("faction") or 0),
                "map_id": int((spawn or {}).get("map_id") or 0),
                "zone_id": int((spawn or {}).get("zone_id") or 0),
                "area_id": int((spawn or {}).get("area_id") or 0),
                "x": float((spawn or {}).get("x") or 0.0),
                "y": float((spawn or {}).get("y") or 0.0),
                "z": float((spawn or {}).get("z") or 0.0),
            }
        )
    return sorted(rows, key=lambda row: (row["map_id"], row["zone_id"], row["entry"]))


def build_faction_restriction_index(restrictions: list[dict[str, Any]], quests: list[dict[str, Any]], services: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = list(restrictions)
    if not rows:
        for quest in quests:
            for required in quest.get("required_factions") or []:
                if int(required.get("faction_id") or 0):
                    rows.append({"source_type": "quest", "source_id": int(quest.get("quest_id") or 0), **required})
        for service in services:
            if int(service.get("faction") or 0):
                rows.append({"source_type": "npc_service", "source_id": int(service.get("entry") or 0), "faction_id": int(service.get("faction") or 0), "value": 0})
    normalized = [
        {
            "source_type": row.get("source_type") or "unknown",
            "source_id": int(row.get("source_id") or 0),
            "faction_id": int(row.get("faction_id") or 0),
            "value": int(row.get("value") or 0),
        }
        for row in rows
        if int(row.get("faction_id") or 0)
    ]
    return sorted(normalized, key=lambda row: (row["source_type"], row["source_id"], row["faction_id"], row["value"]))


def build_map_zone_index(zones: list[dict[str, Any]], map_zone_relationships: list[dict[str, Any]]) -> list[dict[str, Any]]:
    source = map_zone_relationships or zones
    rows = [
        {
            "map_id": int(row.get("map_id") or 0),
            "zone_id": int(row.get("zone_id") or 0),
            "areas": sorted({int(area or 0) for area in row.get("areas") or []}),
            "creature_spawns": int(row.get("creature_spawns") or 0),
            "gameobject_spawns": int(row.get("gameobject_spawns") or 0),
        }
        for row in source
    ]
    return sorted(rows, key=lambda row: (row["map_id"], row["zone_id"]))


def build_planner_manifests(world_dir: Path) -> dict[str, list[dict[str, Any]]]:
    quests = read_jsonl(world_dir / "quests.jsonl")
    objectives = read_jsonl(world_dir / "quest_objectives.jsonl")
    npcs = read_jsonl(world_dir / "npcs.jsonl")
    mobs = read_jsonl(world_dir / "mobs.jsonl")
    services = read_jsonl(world_dir / "npc_services.jsonl")
    trainers = read_jsonl(world_dir / "trainers.jsonl")
    vendors = read_jsonl(world_dir / "vendors.jsonl")
    item_sources = read_jsonl(world_dir / "item_sources.jsonl")
    recipe_sources = read_jsonl(world_dir / "recipe_sources.jsonl")
    material_sources = read_jsonl(world_dir / "material_sources.jsonl")
    gathering_nodes = read_jsonl(world_dir / "gathering_nodes.jsonl")
    travel = read_jsonl(world_dir / "travel.jsonl")
    graveyards = read_jsonl(world_dir / "graveyards.jsonl")
    instance_entrances = read_jsonl(world_dir / "instance_entrances.jsonl")
    repair_points = read_jsonl(world_dir / "repair_points.jsonl")
    faction_restrictions = read_jsonl(world_dir / "faction_restrictions.jsonl")
    map_zone_relationships = read_jsonl(world_dir / "map_zone_relationships.jsonl")
    zones = read_jsonl(world_dir / "zones.jsonl")
    return {
        "quest_hubs": build_quest_hubs(quests),
        "quest_chains": build_quest_chains(quests),
        "objective_clusters": build_objective_clusters(quests, objectives),
        "npc_index": build_npc_index(npcs),
        "mob_index": build_mob_index(mobs),
        "service_index": build_service_index(services),
        "trainer_index": build_trainer_index(trainers or [service for service in services if "trainer" in (service.get("service_types") or [])]),
        "vendor_index": build_vendor_index(vendors or [service for service in services if "vendor" in (service.get("service_types") or [])]),
        "item_source_index": build_item_source_index(item_sources),
        "recipe_source_index": build_recipe_source_index(recipe_sources),
        "material_source_index": build_material_source_index(material_sources),
        "gathering_node_index": build_gathering_node_index(gathering_nodes),
        "travel_edges": build_travel_edges(travel),
        "graveyard_index": build_graveyard_index(graveyards),
        "instance_entrance_index": build_instance_entrance_index(instance_entrances),
        "repair_point_index": build_repair_point_index(repair_points, services),
        "faction_restriction_index": build_faction_restriction_index(faction_restrictions, quests, services),
        "map_zone_index": build_map_zone_index(zones, map_zone_relationships),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build autonomous planner manifests from extracted world knowledge.")
    parser.add_argument("--world-dir", type=Path, default=Path("dataset/world_knowledge"))
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/world_planner"))
    args = parser.parse_args()

    manifests = build_planner_manifests(args.world_dir)
    counts: dict[str, int] = {}
    hashes: dict[str, str] = {}
    for name, rows in manifests.items():
        counts[name] = write_jsonl(args.output_dir / f"{name}.jsonl", rows)
        hashes[name] = stable_hash(rows)
    write_json(
        args.output_dir / "manifest.json",
        {
            "schema": "bot_world_planner_v1",
            "source": str(args.world_dir),
            "files": {name: {"path": f"{name}.jsonl", "rows": counts[name], "sha256": hashes[name]} for name in sorted(counts)},
            "runtime_ml_control": "disabled_shadow_or_teacher_only",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
