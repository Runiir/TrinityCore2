"""Pin the database rows a content-phase gear build reads, one sorted JSON file per phase.

    pixi run python -m tools.bot_ml.extract_phase_gear_db --output-dir dataset/raid_phase_gear_db_extract

Read-only (the sessions are ``SET SESSION TRANSACTION READ ONLY``). From the
world database it selects exactly the rows ``world_sources_from_rows`` uses,
with the same helpers: the creatures spawned on the phase's loot maps and its
encounters' kill-credit creatures, their templates and difficulty entries, the
chests spawned there, their creature/gameobject loot rows, every
``reference_loot_template`` row those reach (transitively) and the item rows
of ``npc_vendor``. From the hotfix database it copies every ``item`` and
``item_sparse`` row with the columns the build reads. An unreachable world or
hotfix database raises: there is no client-data fallback.

The output is tracked with ``dvc add`` and declared by the ``raid_phase_gear``
stage; ``build_phase_gear_profiles`` reads only it and never the database.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from tools.bot_ml.extract_world_knowledge import connect_mysql, database_url_from_worldserver_conf, sanitize_database_url
from tools.bot_ml.phase_gear_extract import (
    EXTRACT_SCHEMA,
    HOTFIX_COLUMNS,
    WORLD_COLUMNS,
    decode_table,
    encode_table,
    extract_inputs,
    extract_path,
)
from tools.bot_ml.phase_gear_profiles import PHASE_CONFIG_DIR, load_phase_config
from tools.bot_ml.phase_gear_sources import (
    GAMEOBJECT_TYPE_CHEST,
    MAX_REFERENCE_DEPTH,
    PhaseSourceError,
    _digest,
    chest_owners,
    encounter_maps,
    loot_maps,
    loot_owners,
    spawn_maps,
    template_bases,
)

ITEM_VENDOR_TYPE_ITEM = 1


def _ids(values: Iterable[int]) -> str:
    wanted = sorted({int(value) for value in values if int(value) > 0})
    if not wanted:
        raise PhaseSourceError("phase_source_query_empty_id_set")
    return ",".join(str(value) for value in wanted)


def _fetch(conn, sql: str) -> list[dict[str, Any]]:
    with conn.cursor() as cursor:
        cursor.execute(sql)
        return list(cursor.fetchall())


def read_only(conn):
    with conn.cursor() as cursor:
        cursor.execute("SET SESSION TRANSACTION READ ONLY")
    return conn


def reference_closure(conn, loot_rows: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Every reference_loot_template row the loot rows reach, following references to a fixed point."""
    pending = sorted({int(row["Reference"]) for row in loot_rows if int(row["Reference"] or 0) > 0})
    seen: set[int] = set()
    rows: list[dict[str, Any]] = []
    for _level in range(MAX_REFERENCE_DEPTH + 1):
        if not pending:
            break
        found = _fetch(conn, "SELECT Entry, Item, Reference FROM reference_loot_template "
                             f"WHERE Entry IN ({_ids(pending)}) ORDER BY Entry, Item")
        rows += found
        seen.update(pending)
        pending = sorted({int(row["Reference"]) for row in found if int(row["Reference"] or 0) > 0} - seen)
    else:
        if pending:
            raise PhaseSourceError(f"phase_loot_reference_too_deep:{pending[:5]}")
    return sorted(rows, key=lambda row: (int(row["Entry"]), int(row["Item"])))


def fetch_world_rows(conn, config: Mapping[str, Any], encounters: Mapping[int, int]) -> dict[str, list[dict[str, Any]]]:
    maps = loot_maps(config)
    tables: dict[str, list[dict[str, Any]]] = {name: [] for name in WORLD_COLUMNS}
    if maps:
        tables["creature_spawns"] = _fetch(conn, f"SELECT DISTINCT map, id FROM creature WHERE map IN ({_ids(maps)}) ORDER BY map, id")
        tables["encounter_credits"] = _fetch(conn, "SELECT entry, creditType, creditEntry FROM instance_encounters "
                                                   "ORDER BY entry, creditType, creditEntry")
        spawn_map = spawn_maps(tables["creature_spawns"], tables["encounter_credits"], encounters, maps)
        tables["creature_templates"] = _fetch(conn, "SELECT entry, difficulty_entry_1, difficulty_entry_2, difficulty_entry_3, "
                                                    f"lootid FROM creature_template WHERE entry IN ({_ids(spawn_map)}) ORDER BY entry")
        base = template_bases(tables["creature_templates"])
        difficulty = [entry for entry in base if entry not in spawn_map]
        if difficulty:
            tables["difficulty_templates"] = _fetch(conn, "SELECT entry, 0 AS difficulty_entry_1, 0 AS difficulty_entry_2, "
                                                          "0 AS difficulty_entry_3, lootid FROM creature_template "
                                                          f"WHERE entry IN ({_ids(difficulty)}) ORDER BY entry")
        creature_loot_ids = loot_owners([*tables["creature_templates"], *tables["difficulty_templates"]], base, spawn_map)
        tables["chests"] = _fetch(conn, "SELECT DISTINCT g.map, t.entry, t.Data1 FROM gameobject g JOIN gameobject_template t "
                                        f"ON t.entry = g.id WHERE g.map IN ({_ids(maps)}) AND t.type = {GAMEOBJECT_TYPE_CHEST} "
                                        "AND t.Data1 > 0 ORDER BY g.map, t.entry, t.Data1")
        chest_loot_ids = chest_owners(tables["chests"])
        tables["creature_loot"] = _fetch(conn, "SELECT Entry, Item, Reference FROM creature_loot_template "
                                               f"WHERE Entry IN ({_ids(creature_loot_ids)}) ORDER BY Entry, Item")
        if chest_loot_ids:
            tables["gameobject_loot"] = _fetch(conn, "SELECT Entry, Item, Reference FROM gameobject_loot_template "
                                                     f"WHERE Entry IN ({_ids(chest_loot_ids)}) ORDER BY Entry, Item")
        tables["reference_loot"] = reference_closure(conn, [*tables["creature_loot"], *tables["gameobject_loot"]])
        if not tables["creature_loot"] or not tables["reference_loot"]:
            raise PhaseSourceError("phase_loot_tables_empty")
    # Item rows only: a currency row (type 2) names a currency ID, not an item ID.
    tables["npc_vendor"] = _fetch(conn, "SELECT entry, item, ExtendedCost FROM npc_vendor "
                                        f"WHERE item > 0 AND type = {ITEM_VENDOR_TYPE_ITEM} ORDER BY entry, item, ExtendedCost")
    if not tables["npc_vendor"]:
        raise PhaseSourceError("phase_vendor_table_empty")
    return tables


def fetch_hotfix_rows(conn) -> dict[str, list[dict[str, Any]]]:
    return {name: _fetch(conn, f"SELECT {', '.join(columns)} FROM {name} ORDER BY ID") for name, columns in HOTFIX_COLUMNS.items()}


def build_extract(config: Mapping[str, Any], dbc_dir: Path, world: Mapping[str, list], hotfix: Mapping[str, list],
                  databases: Mapping[str, str]) -> dict[str, Any]:
    tables = {"world": {name: encode_table(world[name], columns) for name, columns in WORLD_COLUMNS.items()},
              "hotfix": {name: encode_table(hotfix[name], columns) for name, columns in HOTFIX_COLUMNS.items()}}
    # Digest the rows as the loader will decode them (after the JSON round trip).
    tables = json.loads(json.dumps(tables, sort_keys=True))
    digests = {scope: {name: _digest(decode_table(tables[scope][name], columns, f"{scope}.{name}"))
                       for name, columns in sorted(columns_by_table.items())}
               for scope, columns_by_table in (("world", WORLD_COLUMNS), ("hotfix", HOTFIX_COLUMNS))}
    return {"schema": EXTRACT_SCHEMA, "phase_id": config["phase_id"], "inputs": extract_inputs(config, dbc_dir),
            "databases": dict(databases), "tables": tables, "row_digests": digests,
            "row_counts": {scope: {name: len(table["rows"]) for name, table in sorted(tables[scope].items())} for scope in tables}}


def write_extract(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Pin the world/hotfix rows of content-phase gear builds (read-only).")
    parser.add_argument("--phase-config", type=Path, action="append",
                        help="Phase config JSON; defaults to every file in experiments/configs/raid_gear_phases.")
    parser.add_argument("--worldserver-conf", type=Path, default=Path("trinity-worldserver-test.conf"))
    parser.add_argument("--world-database-url")
    parser.add_argument("--hotfix-database-url")
    parser.add_argument("--dbc-dir", type=Path, default=Path("data/dbc/enUS"))
    parser.add_argument("--output-dir", type=Path, default=Path("dataset/raid_phase_gear_db_extract"))
    args = parser.parse_args()
    world_url = args.world_database_url or database_url_from_worldserver_conf(args.worldserver_conf, "WorldDatabaseInfo")
    hotfix_url = args.hotfix_database_url or database_url_from_worldserver_conf(args.worldserver_conf, "HotfixDatabaseInfo")
    databases = {"world": str(sanitize_database_url(world_url)["database"]), "hotfix": str(sanitize_database_url(hotfix_url)["database"])}
    encounters = encounter_maps(args.dbc_dir)
    hotfix_conn = read_only(connect_mysql(hotfix_url))
    try:
        hotfix = fetch_hotfix_rows(hotfix_conn)
    finally:
        hotfix_conn.close()
    written = {}
    for config_path in args.phase_config or sorted(PHASE_CONFIG_DIR.glob("*.json")):
        config = load_phase_config(config_path)
        world_conn = read_only(connect_mysql(world_url))
        try:
            world = fetch_world_rows(world_conn, config, encounters)
        finally:
            world_conn.close()
        payload = build_extract(config, args.dbc_dir, world, hotfix, databases)
        path = extract_path(args.output_dir, config["phase_id"])
        write_extract(path, payload)
        written[config["phase_id"]] = {"path": str(path), "row_counts": payload["row_counts"]}
    print(json.dumps(written, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
