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
                "vendor_items": [int(row.get("item") or row.get("item_id") or 0) for row in service.get("vendor_items") or []],
                "trainer_spells": [int(row.get("spell_id") or 0) for row in service.get("trainer_spells") or []],
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


def build_planner_manifests(world_dir: Path) -> dict[str, list[dict[str, Any]]]:
    quests = read_jsonl(world_dir / "quests.jsonl")
    objectives = read_jsonl(world_dir / "quest_objectives.jsonl")
    services = read_jsonl(world_dir / "npc_services.jsonl")
    item_sources = read_jsonl(world_dir / "item_sources.jsonl")
    travel = read_jsonl(world_dir / "travel.jsonl")
    return {
        "quest_hubs": build_quest_hubs(quests),
        "quest_chains": build_quest_chains(quests),
        "objective_clusters": build_objective_clusters(quests, objectives),
        "service_index": build_service_index(services),
        "item_source_index": build_item_source_index(item_sources),
        "travel_edges": build_travel_edges(travel),
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
