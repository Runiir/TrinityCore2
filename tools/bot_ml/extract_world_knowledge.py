from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

try:
    from .common import git_commit, read_jsonl, stable_hash, write_json, write_jsonl
except ImportError:
    from common import git_commit, read_jsonl, stable_hash, write_json, write_jsonl


QUEST_OBJECTIVE_SLOTS = range(1, 5)
QUEST_ITEM_SLOTS = range(1, 7)
REWARD_SLOTS = range(1, 5)
REWARD_CHOICE_SLOTS = range(1, 7)
WORLD_MANIFEST_NAMES = [
    "quests",
    "quest_objectives",
    "npcs",
    "mobs",
    "npc_services",
    "trainers",
    "vendors",
    "item_sources",
    "recipe_sources",
    "material_sources",
    "gathering_nodes",
    "travel",
    "graveyards",
    "instance_entrances",
    "repair_points",
    "faction_restrictions",
    "map_zone_relationships",
    "zones",
]


def connect_mysql(database_url: str):
    try:
        import pymysql
    except ImportError as exc:
        raise SystemExit("pymysql is required; run through pixi") from exc

    parsed = urlparse(database_url)
    if parsed.scheme not in {"mysql", "mysql+pymysql"}:
        raise SystemExit(f"unsupported database URL scheme: {parsed.scheme}")
    return pymysql.connect(
        host=parsed.hostname or "127.0.0.1",
        port=parsed.port or 3306,
        user=parsed.username or "",
        password=parsed.password or "",
        database=(parsed.path or "/").lstrip("/"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def parse_trinity_database_info(value: str) -> dict[str, str | int]:
    parts = [part.strip() for part in value.strip().strip('"').split(";")]
    if len(parts) != 5:
        raise ValueError(f"expected Trinity database info as host;port;user;password;database, got {value!r}")
    host, port, user, password, database = parts
    return {"host": host, "port": int(port), "user": user, "password": password, "database": database}


def database_url_from_info(info: dict[str, str | int]) -> str:
    return f"mysql://{info['user']}:{info['password']}@{info['host']}:{info['port']}/{info['database']}"


def database_url_from_worldserver_conf(path: Path, key: str = "WorldDatabaseInfo") -> str:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=\s*(?P<value>\"[^\"]+\"|[^\s#]+)", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        raise SystemExit(f"{key} not found in {path}")
    return database_url_from_info(parse_trinity_database_info(match.group("value")))


def sanitize_database_url(database_url: str) -> dict[str, str | int]:
    parsed = urlparse(database_url)
    return {
        "scheme": parsed.scheme,
        "host": parsed.hostname or "",
        "port": parsed.port or 3306,
        "database": (parsed.path or "/").lstrip("/"),
        "user": parsed.username or "",
    }


def empty_world_manifests() -> dict[str, list[dict[str, Any]]]:
    return {name: [] for name in WORLD_MANIFEST_NAMES}


def load_existing_world_manifests(output_dir: Path) -> dict[str, list[dict[str, Any]]] | None:
    existing = [name for name in WORLD_MANIFEST_NAMES if (output_dir / f"{name}.jsonl").exists()]
    if not existing:
        return None
    missing = [name for name in WORLD_MANIFEST_NAMES if name not in existing]
    if missing:
        return None
    return {name: read_jsonl(output_dir / f"{name}.jsonl") for name in WORLD_MANIFEST_NAMES}


def fetch_all(conn, sql: str) -> list[dict[str, Any]]:
    with conn.cursor() as cursor:
        cursor.execute(sql)
        return list(cursor.fetchall())


def table_exists(conn, table: str) -> bool:
    with conn.cursor() as cursor:
        cursor.execute("SHOW TABLES LIKE %s", (table,))
        return cursor.fetchone() is not None


def compact_position(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "map_id": int(row.get("map_id") or row.get("map") or row.get("target_map") or 0),
        "zone_id": int(row.get("zone_id") or row.get("zoneId") or 0),
        "area_id": int(row.get("area_id") or row.get("areaId") or 0),
        "x": float(row.get("x") or row.get("position_x") or row.get("target_position_x") or 0.0),
        "y": float(row.get("y") or row.get("position_y") or row.get("target_position_y") or 0.0),
        "z": float(row.get("z") or row.get("position_z") or row.get("target_position_z") or 0.0),
        "o": float(row.get("o") or row.get("orientation") or row.get("target_orientation") or 0.0),
    }


def service_types_from_npcflag(npcflag: int) -> list[str]:
    types: list[str] = []
    if npcflag & 2:
        types.append("questgiver")
    if npcflag & 16:
        types.append("trainer")
    if npcflag & 128:
        types.append("vendor")
    if npcflag & 4096:
        types.append("repair")
    return types


def build_quest_objectives(quest: dict[str, Any]) -> list[dict[str, Any]]:
    objectives: list[dict[str, Any]] = []
    for slot in QUEST_OBJECTIVE_SLOTS:
        required = int(quest.get(f"RequiredNpcOrGo{slot}") or 0)
        count = int(quest.get(f"RequiredNpcOrGoCount{slot}") or 0)
        text = str(quest.get(f"ObjectiveText{slot}") or "")
        if required or count or text:
            objectives.append(
                {
                    "slot": slot,
                    "type": "gameobject" if required < 0 else "creature",
                    "entry": abs(required),
                    "required_count": count,
                    "text": text,
                }
            )
    for slot in QUEST_ITEM_SLOTS:
        item_id = int(quest.get(f"RequiredItemId{slot}") or 0)
        count = int(quest.get(f"RequiredItemCount{slot}") or 0)
        if item_id or count:
            objectives.append({"slot": slot, "type": "item", "item_id": item_id, "required_count": count})
    required_spell = int(quest.get("RequiredSpell") or 0)
    if required_spell:
        objectives.append({"slot": 0, "type": "spell", "spell_id": required_spell})
    return objectives


def build_rewards(quest: dict[str, Any]) -> list[dict[str, Any]]:
    rewards: list[dict[str, Any]] = []
    for slot in REWARD_SLOTS:
        item_id = int(quest.get(f"RewardItem{slot}") or 0)
        quantity = int(quest.get(f"RewardAmount{slot}") or 0)
        if item_id:
            rewards.append({"slot": slot, "mode": "fixed", "item_id": item_id, "quantity": quantity})
    for slot in REWARD_CHOICE_SLOTS:
        item_id = int(quest.get(f"RewardChoiceItemID{slot}") or 0)
        quantity = int(quest.get(f"RewardChoiceItemQuantity{slot}") or 0)
        if item_id:
            rewards.append({"slot": slot, "mode": "choice", "item_id": item_id, "quantity": quantity})
    return rewards


def index_spawns(rows: list[dict[str, Any]], entry_key: str) -> dict[int, list[dict[str, Any]]]:
    indexed: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        entry = int(row.get(entry_key) or 0)
        if entry:
            indexed[entry].append(compact_position(row))
    return indexed


def creature_spawn_meta(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    meta: dict[int, dict[str, Any]] = {}
    for row in rows:
        entry = int(row.get("entry") or 0)
        if not entry or entry in meta:
            continue
        meta[entry] = {
            "name": row.get("name") or "",
            "subname": row.get("subname") or "",
            "npcflag": int(row.get("npcflag") or 0),
            "creature_type": int(row.get("type") or 0),
            "rank": int(row.get("rank") or 0),
            "faction": int(row.get("faction") or 0),
        }
    return meta


def gameobject_spawn_meta(rows: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    meta: dict[int, dict[str, Any]] = {}
    for row in rows:
        entry = int(row.get("entry") or 0)
        if not entry or entry in meta:
            continue
        meta[entry] = {
            "name": row.get("name") or "",
            "gameobject_type": int(row.get("type") or 0),
        }
    return meta


def extract_world_knowledge(database_url: str) -> dict[str, list[dict[str, Any]]]:
    conn = connect_mysql(database_url)
    try:
        creature_spawns = fetch_all(
            conn,
            "SELECT c.guid, c.id AS entry, c.map AS map_id, c.zoneId AS zone_id, c.areaId AS area_id, "
            "c.position_x AS x, c.position_y AS y, c.position_z AS z, c.orientation AS o, "
            "ct.name, ct.subname, ct.npcflag, ct.type, ct.rank, ct.faction "
            "FROM creature c LEFT JOIN creature_template ct ON ct.entry = c.id",
        )
        gameobject_spawns = fetch_all(
            conn,
            "SELECT g.guid, g.id AS entry, g.map AS map_id, g.zoneId AS zone_id, g.areaId AS area_id, "
            "g.position_x AS x, g.position_y AS y, g.position_z AS z, g.orientation AS o, "
            "gt.name, gt.type "
            "FROM gameobject g LEFT JOIN gameobject_template gt ON gt.entry = g.id",
        )
        creature_by_entry = index_spawns(creature_spawns, "entry")
        gameobject_by_entry = index_spawns(gameobject_spawns, "entry")
        creature_meta_by_entry = creature_spawn_meta(creature_spawns)
        gameobject_meta_by_entry = gameobject_spawn_meta(gameobject_spawns)

        npcs = []
        for entry, meta in sorted(creature_meta_by_entry.items()):
            npcflag = int(meta.get("npcflag") or 0)
            npcs.append(
                {
                    "entry": entry,
                    "name": meta.get("name", ""),
                    "subname": meta.get("subname", ""),
                    "npcflag": npcflag,
                    "service_types": service_types_from_npcflag(npcflag),
                    "creature_type": int(meta.get("creature_type") or 0),
                    "rank": int(meta.get("rank") or 0),
                    "faction": int(meta.get("faction") or 0),
                    "spawns": creature_by_entry.get(entry, [])[:64],
                }
            )

        mobs = [
            {
                "entry": row["entry"],
                "name": row["name"],
                "creature_type": row["creature_type"],
                "rank": row["rank"],
                "faction": row["faction"],
                "spawns": row["spawns"],
            }
            for row in npcs
            if not row["service_types"] or row["creature_type"] not in {7}
        ]

        quest_rows = fetch_all(conn, "SELECT * FROM quest_template")
        addon_by_quest = {
            int(row["ID"]): row
            for row in (fetch_all(conn, "SELECT * FROM quest_template_addon") if table_exists(conn, "quest_template_addon") else [])
        }
        creature_starters = fetch_all(conn, "SELECT id AS entry, quest FROM creature_queststarter")
        creature_enders = fetch_all(conn, "SELECT id AS entry, quest FROM creature_questender")
        go_starters = fetch_all(conn, "SELECT id AS entry, quest FROM gameobject_queststarter")
        go_enders = fetch_all(conn, "SELECT id AS entry, quest FROM gameobject_questender")

        givers_by_quest: dict[int, list[dict[str, Any]]] = defaultdict(list)
        turnins_by_quest: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in creature_starters:
            givers_by_quest[int(row["quest"])].append({"type": "creature", "entry": int(row["entry"]), "spawns": creature_by_entry.get(int(row["entry"]), [])[:32]})
        for row in go_starters:
            givers_by_quest[int(row["quest"])].append({"type": "gameobject", "entry": int(row["entry"]), "spawns": gameobject_by_entry.get(int(row["entry"]), [])[:32]})
        for row in creature_enders:
            turnins_by_quest[int(row["quest"])].append({"type": "creature", "entry": int(row["entry"]), "spawns": creature_by_entry.get(int(row["entry"]), [])[:32]})
        for row in go_enders:
            turnins_by_quest[int(row["quest"])].append({"type": "gameobject", "entry": int(row["entry"]), "spawns": gameobject_by_entry.get(int(row["entry"]), [])[:32]})

        quests = []
        quest_objectives = []
        for quest in quest_rows:
            quest_id = int(quest["ID"])
            addon = addon_by_quest.get(quest_id, {})
            objectives = build_quest_objectives(quest)
            for objective in objectives:
                objective_row = {"quest_id": quest_id, **objective}
                if objective["type"] == "creature":
                    objective_row["spawns"] = creature_by_entry.get(int(objective.get("entry") or 0), [])[:64]
                elif objective["type"] == "gameobject":
                    objective_row["spawns"] = gameobject_by_entry.get(int(objective.get("entry") or 0), [])[:64]
                quest_objectives.append(objective_row)
            quests.append(
                {
                    "quest_id": quest_id,
                    "title": quest.get("LogTitle") or "",
                    "quest_level": int(quest.get("QuestLevel") or 0),
                    "min_level": int(quest.get("MinLevel") or 0),
                    "sort_id": int(quest.get("QuestSortID") or 0),
                    "suggested_group": int(quest.get("SuggestedGroupNum") or 0),
                    "required_factions": [
                        {"faction_id": int(quest.get("RequiredFactionId1") or 0), "value": int(quest.get("RequiredFactionValue1") or 0)},
                        {"faction_id": int(quest.get("RequiredFactionId2") or 0), "value": int(quest.get("RequiredFactionValue2") or 0)},
                    ],
                    "prev_quest_id": int(addon.get("PrevQuestID") or 0),
                    "next_quest_id": int(addon.get("NextQuestID") or quest.get("RewardNextQuest") or 0),
                    "breadcrumb_for_quest_id": int(addon.get("BreadcrumbForQuestId") or 0),
                    "poi": {
                        "map_id": int(quest.get("POIContinent") or 0),
                        "x": float(quest.get("POIx") or 0.0),
                        "y": float(quest.get("POIy") or 0.0),
                        "priority": int(quest.get("POIPriority") or 0),
                    },
                    "givers": givers_by_quest.get(quest_id, []),
                    "turnins": turnins_by_quest.get(quest_id, []),
                    "objectives": objectives,
                    "rewards": build_rewards(quest),
                    "support_class": "supported_simple" if objectives else "chain_or_scripted",
                }
            )

        npc_services = []
        vendors = []
        trainers = []
        repair_points = []
        vendor_items = fetch_all(conn, "SELECT entry, item, maxcount, incrtime, ExtendedCost, type, PlayerConditionID FROM npc_vendor")
        trainer_spells = fetch_all(
            conn,
            "SELECT t.Id AS trainer_id, t.Type AS trainer_type, ts.SpellId AS spell_id, ts.MoneyCost AS money_cost, "
            "ts.ReqSkillLine AS req_skill_line, ts.ReqSkillRank AS req_skill_rank, ts.ReqAbility1 AS req_ability1, "
            "ts.ReqLevel AS req_level FROM trainer t LEFT JOIN trainer_spell ts ON ts.TrainerId = t.Id",
        )
        creature_trainers = fetch_all(conn, "SELECT CreatureId AS entry, TrainerId AS trainer_id, MenuId AS menu_id, OptionId AS option_id FROM creature_trainer")
        trainer_by_id: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in trainer_spells:
            trainer_by_id[int(row.get("trainer_id") or 0)].append({key: row[key] for key in row if key not in {"trainer_id"}})
        vendors_by_entry: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for row in vendor_items:
            vendors_by_entry[int(row["entry"])].append({key: row[key] for key in row if key != "entry"})
        trainer_ids_by_entry: dict[int, list[int]] = defaultdict(list)
        for row in creature_trainers:
            trainer_ids_by_entry[int(row["entry"])].append(int(row["trainer_id"]))
        service_entries = set(vendors_by_entry) | set(trainer_ids_by_entry) | {entry for entry, meta in creature_meta_by_entry.items() if int(meta.get("npcflag") or 0) & 4096}
        for entry in sorted(service_entries):
            spells = [spell for trainer_id in trainer_ids_by_entry.get(entry, []) for spell in trainer_by_id.get(trainer_id, [])]
            meta = creature_meta_by_entry.get(entry, {})
            npcflag = int(meta.get("npcflag") or 0)
            service_types = sorted(set((["vendor"] if entry in vendors_by_entry else []) + (["trainer"] if entry in trainer_ids_by_entry else []) + (["repair"] if npcflag & 4096 else [])))
            service_row = {
                "entry": entry,
                "name": meta.get("name", ""),
                "subname": meta.get("subname", ""),
                "npcflag": npcflag,
                "faction": meta.get("faction", 0),
                "spawns": creature_by_entry.get(entry, [])[:64],
                "vendor_items": vendors_by_entry.get(entry, []),
                "trainer_ids": trainer_ids_by_entry.get(entry, []),
                "trainer_spells": spells,
                "service_types": service_types,
            }
            npc_services.append(
                service_row
            )
            if "vendor" in service_types:
                vendors.append(service_row)
            if "trainer" in service_types:
                trainers.append(service_row)
            if "repair" in service_types:
                repair_points.append(service_row)

        creature_loot = fetch_all(conn, "SELECT Entry AS source_entry, Item AS item_id, Reference AS reference, Chance AS chance, QuestRequired AS quest_required, MinCount AS min_count, MaxCount AS max_count FROM creature_loot_template")
        gameobject_loot = fetch_all(conn, "SELECT Entry AS source_entry, Item AS item_id, Reference AS reference, Chance AS chance, QuestRequired AS quest_required, MinCount AS min_count, MaxCount AS max_count FROM gameobject_loot_template")
        item_sources = [{"source_type": "creature_loot", **row} for row in creature_loot] + [{"source_type": "gameobject_loot", **row} for row in gameobject_loot]
        for row in vendor_items:
            item_sources.append({"source_type": "vendor", "source_entry": int(row["entry"]), "item_id": int(row["item"]), "max_count": int(row.get("maxcount") or 0), "player_condition_id": int(row.get("PlayerConditionID") or 0)})

        material_sources = []
        gathering_nodes = []
        for row in creature_loot:
            source_entry = int(row.get("source_entry") or 0)
            material_sources.append(
                {
                    "source_type": "creature_loot",
                    "source_entry": source_entry,
                    "item_id": int(row.get("item_id") or 0),
                    "chance": float(row.get("chance") or 0.0),
                    "quest_required": int(row.get("quest_required") or 0),
                    "min_count": int(row.get("min_count") or 0),
                    "max_count": int(row.get("max_count") or 0),
                    "spawns": creature_by_entry.get(source_entry, [])[:64],
                }
            )
        for row in gameobject_loot:
            source_entry = int(row.get("source_entry") or 0)
            source_meta = gameobject_meta_by_entry.get(source_entry, {})
            material_sources.append(
                {
                    "source_type": "gameobject_loot",
                    "source_entry": source_entry,
                    "source_name": source_meta.get("name", ""),
                    "gameobject_type": int(source_meta.get("gameobject_type") or 0),
                    "item_id": int(row.get("item_id") or 0),
                    "chance": float(row.get("chance") or 0.0),
                    "quest_required": int(row.get("quest_required") or 0),
                    "min_count": int(row.get("min_count") or 0),
                    "max_count": int(row.get("max_count") or 0),
                    "spawns": gameobject_by_entry.get(source_entry, [])[:64],
                }
            )
            gathering_nodes.append(
                {
                    "entry": source_entry,
                    "name": source_meta.get("name", ""),
                    "gameobject_type": int(source_meta.get("gameobject_type") or 0),
                    "loot_item_id": int(row.get("item_id") or 0),
                    "chance": float(row.get("chance") or 0.0),
                    "quest_required": int(row.get("quest_required") or 0),
                    "spawns": gameobject_by_entry.get(source_entry, [])[:64],
                }
            )
        for row in vendor_items:
            source_entry = int(row["entry"])
            material_sources.append(
                {
                    "source_type": "vendor",
                    "source_entry": source_entry,
                    "item_id": int(row["item"]),
                    "max_count": int(row.get("maxcount") or 0),
                    "player_condition_id": int(row.get("PlayerConditionID") or 0),
                    "spawns": creature_by_entry.get(source_entry, [])[:64],
                }
            )

        recipe_sources = []
        for service in npc_services:
            for spell in service.get("trainer_spells") or []:
                spell_id = int(spell.get("spell_id") or 0)
                if not spell_id:
                    continue
                recipe_sources.append(
                    {
                        "source_type": "trainer",
                        "source_entry": int(service["entry"]),
                        "trainer_ids": service.get("trainer_ids") or [],
                        "recipe_spell_id": spell_id,
                        "item_id": 0,
                        "profession_skill_id": int(spell.get("req_skill_line") or 0),
                        "req_skill_rank": int(spell.get("req_skill_rank") or 0),
                        "req_level": int(spell.get("req_level") or 0),
                        "money_cost": int(spell.get("money_cost") or 0),
                        "faction": int(service.get("faction") or 0),
                        "spawns": service.get("spawns") or [],
                    }
                )
            for item in service.get("vendor_items") or []:
                item_id = int(item.get("item") or 0)
                if not item_id:
                    continue
                recipe_sources.append(
                    {
                        "source_type": "vendor_item",
                        "source_entry": int(service["entry"]),
                        "recipe_spell_id": 0,
                        "item_id": item_id,
                        "profession_skill_id": 0,
                        "max_count": int(item.get("maxcount") or 0),
                        "player_condition_id": int(item.get("PlayerConditionID") or 0),
                        "faction": int(service.get("faction") or 0),
                        "spawns": service.get("spawns") or [],
                        "source_note": "candidate_recipe_or_material_vendor_item",
                    }
                )

        travel = []
        graveyards = []
        instance_entrances = []
        if table_exists(conn, "areatrigger_teleport"):
            for row in fetch_all(conn, "SELECT * FROM areatrigger_teleport"):
                entry = {"type": "areatrigger_teleport", "id": int(row["ID"]), "name": row.get("Name") or "", "destination": compact_position(row)}
                travel.append(entry)
                instance_entrances.append(entry)
        if table_exists(conn, "transports"):
            travel.extend({"type": "transport", **row} for row in fetch_all(conn, "SELECT * FROM transports"))
        if table_exists(conn, "graveyard_zone"):
            for row in fetch_all(conn, "SELECT * FROM graveyard_zone"):
                entry = {"type": "graveyard", **row}
                travel.append(entry)
                graveyards.append(entry)
        if table_exists(conn, "taxi_level_data"):
            travel.extend({"type": "taxi_level", **row} for row in fetch_all(conn, "SELECT * FROM taxi_level_data"))

        zone_index: dict[tuple[int, int], dict[str, Any]] = {}
        for row in creature_spawns + gameobject_spawns:
            key = (int(row.get("map_id") or 0), int(row.get("zone_id") or 0))
            zone = zone_index.setdefault(key, {"map_id": key[0], "zone_id": key[1], "creature_spawns": 0, "gameobject_spawns": 0, "areas": set()})
            zone["areas"].add(int(row.get("area_id") or 0))
            if "npcflag" in row:
                zone["creature_spawns"] += 1
            else:
                zone["gameobject_spawns"] += 1
        zones = [{**zone, "areas": sorted(zone["areas"])} for zone in zone_index.values()]
        map_zone_relationships = sorted(zones, key=lambda row: (row["map_id"], row["zone_id"]))

        faction_restrictions = []
        for quest in quests:
            for required in quest.get("required_factions") or []:
                if int(required.get("faction_id") or 0):
                    faction_restrictions.append({"source_type": "quest", "source_id": quest["quest_id"], **required})
        for service in npc_services:
            if int(service.get("faction") or 0):
                faction_restrictions.append({"source_type": "npc_service", "source_id": service["entry"], "faction_id": int(service.get("faction") or 0), "value": 0})

        return {
            "quests": quests,
            "quest_objectives": quest_objectives,
            "npcs": npcs,
            "mobs": mobs,
            "npc_services": npc_services,
            "trainers": trainers,
            "vendors": vendors,
            "item_sources": item_sources,
            "recipe_sources": recipe_sources,
            "material_sources": material_sources,
            "gathering_nodes": gathering_nodes,
            "travel": travel,
            "graveyards": graveyards,
            "instance_entrances": instance_entrances,
            "repair_points": repair_points,
            "faction_restrictions": faction_restrictions,
            "map_zone_relationships": map_zone_relationships,
            "zones": sorted(zones, key=lambda row: (row["map_id"], row["zone_id"])),
        }
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract DB-backed world knowledge manifests for autonomous bots.")
    parser.add_argument("--database-url", help="MySQL URL for the world database, e.g. mysql://trinity:trinity@127.0.0.1:3306/world")
    parser.add_argument("--worldserver-conf", type=Path, default=Path("trinity-worldserver-test.conf"), help="Worldserver config to read WorldDatabaseInfo from when --database-url is omitted.")
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/world_knowledge"))
    args = parser.parse_args()

    extraction_status = {"mode": "database", "ok": True, "reason": ""}
    try:
        database_url = args.database_url or database_url_from_worldserver_conf(args.worldserver_conf)
        manifests = extract_world_knowledge(database_url)
        source_database: dict[str, Any] = sanitize_database_url(database_url)
    except Exception as exc:
        existing = load_existing_world_manifests(args.output_dir)
        manifests = existing if existing is not None else empty_world_manifests()
        extraction_status = {
            "mode": "existing_generated_files" if existing is not None else "empty_db_unavailable",
            "ok": existing is not None,
            "reason": f"{type(exc).__name__}: {exc}",
        }
        source_database = {"available": False, "reason": extraction_status["reason"]}
    counts: dict[str, int] = {}
    hashes: dict[str, str] = {}
    for name in WORLD_MANIFEST_NAMES:
        rows = manifests.get(name, [])
        path = args.output_dir / f"{name}.jsonl"
        counts[name] = write_jsonl(path, rows)
        hashes[name] = stable_hash(rows)

    write_json(
        args.output_dir / "manifest.json",
        {
            "schema": "bot_world_knowledge_v1",
            "git_commit": git_commit(),
            "source_database": source_database,
            "extraction_status": extraction_status,
            "files": {name: {"path": f"{name}.jsonl", "rows": counts[name], "sha256": hashes[name]} for name in sorted(counts)},
            "planner_contract": {
                "quests": "quest hubs, chains, objectives, rewards, faction gates, POI hints",
                "npcs": "spawned NPC metadata for services, faction restrictions, and mob classification",
                "mobs": "combat-capable creature spawn priors for grinding, kill quests, and loot plans",
                "npc_services": "vendors, class/profession trainers, repair/restock candidates when item/NPC flags are available",
                "trainers": "trainer NPCs with spell and profession requirements",
                "vendors": "vendor NPCs with sold-item metadata and spawn positions",
                "item_sources": "loot, vendors, gatherable gameobjects through loot/source manifests",
                "recipe_sources": "trainer spells and vendor recipe/material candidates with profession requirements and spawns",
                "material_sources": "farmable or buyable item sources with source spawns for profession and gearing plans",
                "gathering_nodes": "gameobject loot nodes with item yields and spawn positions",
                "travel": "teleports, transports, taxi/graveyard source tables when available",
                "graveyards": "graveyard-zone restrictions for corpse-run recovery planning",
                "instance_entrances": "area trigger teleports usable as dungeon/raid entrance candidates",
                "repair_points": "repair-capable NPCs for durability recovery plans",
                "faction_restrictions": "quest and service faction gates with deterministic source IDs",
                "map_zone_relationships": "map-zone-area relationships derived from spawn coverage",
                "zones": "map-zone-area spawn coverage for route and discovery priors",
            },
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
