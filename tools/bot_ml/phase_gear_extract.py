"""The pinned database rows a content-phase gear build reads (``dataset/raid_phase_gear_db_extract``).

``extract_phase_gear_db`` reads them once from the read-only world and hotfix
databases and writes one sorted, deterministic JSON file per phase; the file is
tracked with ``dvc add`` and is a declared dependency of ``raid_phase_gear``,
so a changed loot, vendor or hotfix row changes a pinned input instead of
silently changing the gear. The builder reads only this file.

The loader fails closed: a wrong schema, a phase whose loot maps or
DungeonEncounter.dbc differ from what the extract was selected with, a missing
or reshaped table, or rows that no longer match their recorded digests.

Item data follows the server's store: the client Item.db2/Item-sparse.db2 row,
overridden by the hotfix ``item``/``item_sparse`` row where one exists
(``DB2Storage`` loads the hotfix rows over the client file).
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from tools.bot_ml.build_validation_gear_profiles import ITEM_FMT, ITEM_SPARSE_FMT, load_db2_item_rows, load_wdb2
from tools.bot_ml.phase_gear_profiles import REPO_ROOT
from tools.bot_ml.phase_gear_sources import WORLD_TABLES, PhaseSourceError, _digest, loot_maps

EXTRACT_SCHEMA = "raid_phase_gear_db_extract_v2"
DEFAULT_EXTRACT_DIR = REPO_ROOT / "dataset/raid_phase_gear_db_extract"
LOOT_COLUMNS = ("Entry", "Item", "Reference")
TEMPLATE_COLUMNS = ("entry", "difficulty_entry_1", "difficulty_entry_2", "difficulty_entry_3", "lootid")
WORLD_COLUMNS: dict[str, tuple[str, ...]] = {
    "creature_spawns": ("map", "id"),
    "encounter_credits": ("entry", "creditType", "creditEntry"),
    "creature_templates": TEMPLATE_COLUMNS,
    "difficulty_templates": TEMPLATE_COLUMNS,
    "chests": ("map", "entry", "Data1"),
    "creature_loot": LOOT_COLUMNS,
    "gameobject_loot": LOOT_COLUMNS,
    "reference_loot": LOOT_COLUMNS,
    "npc_vendor": ("entry", "item", "ExtendedCost"),
}
STAT_COLUMNS = tuple(f"ItemStat{kind}{index}" for index in range(1, 11) for kind in ("Type", "Value"))
SOCKET_COLUMNS = ("SocketColor1", "SocketColor2", "SocketColor3")
# Item-sparse fields the gear build reads, as hotfix columns.
SPARSE_ITEM_COLUMNS = ("Display", "Quality", "ItemLevel", "RequiredLevel", "AllowableClass", *SOCKET_COLUMNS,
                       "GemProperties", "ItemLimitCategory", *STAT_COLUMNS)
# Item facts: name -> (Item-sparse.db2 field, hotfix item_sparse column). The use restrictions are the
# ItemSparseEntry fields Player::CanUseItem checks (phase_gear_equip_restrictions).
FACT_FIELDS = {"flags": (2, "Flags1"), "flags2": (3, "Flags2"), "inventory_type": (9, "InventoryType"),
               "allowable_class": (10, "AllowableClass"), "allowable_race": (11, "AllowableRace"),
               "required_level": (13, "RequiredLevel"), "required_skill": (14, "RequiredSkill"),
               "required_skill_rank": (15, "RequiredSkillRank"), "required_spell": (16, "RequiredSpell"),
               "required_reputation_faction": (19, "RequiredReputationFaction"),
               "required_reputation_rank": (20, "RequiredReputationRank"), "max_count": (21, "MaxCount"),
               "bonding": (98, "Bonding"), "item_set": (113, "ItemSet"), "socket_bonus": (124, "SocketBonus"),
               "limit_category": (128, "ItemLimitCategory"), "holiday_id": (129, "HolidayID"),
               # Item spells (phase_gear_item_effects): SpellID[5] 68-72, SpellTrigger[5] 73-77.
               **{f"spell_id_{index}": (67 + index, f"SpellID{index}") for index in range(1, 6)},
               **{f"spell_trigger_{index}": (72 + index, f"SpellTrigger{index}") for index in range(1, 6)}}
UNSIGNED_FLAG_FACTS = ("flags", "flags2")
HOTFIX_COLUMNS: dict[str, tuple[str, ...]] = {
    "item": ("ID", "ClassID", "SubclassID", "InventoryType"),
    "item_sparse": ("ID", *SPARSE_ITEM_COLUMNS, *sorted({column for _field, column in FACT_FIELDS.values()} - set(SPARSE_ITEM_COLUMNS))),
}
if tuple(WORLD_COLUMNS) != WORLD_TABLES:
    raise PhaseSourceError("phase_db_extract_world_table_set")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract_path(extract_dir: Path, phase_id: str) -> Path:
    return Path(extract_dir) / f"{phase_id}.json"


def encode_table(rows: Iterable[Mapping[str, Any]], columns: tuple[str, ...]) -> dict[str, Any]:
    return {"columns": list(columns), "rows": [[row[column] for column in columns] for row in rows]}


def decode_table(table: Mapping[str, Any], columns: tuple[str, ...], where: str) -> list[dict[str, Any]]:
    if not isinstance(table, Mapping) or tuple(table.get("columns") or ()) != columns or not isinstance(table.get("rows"), list):
        raise PhaseSourceError(f"phase_db_extract_table_shape:{where}")
    rows = table["rows"]
    if any(not isinstance(row, list) or len(row) != len(columns) for row in rows):
        raise PhaseSourceError(f"phase_db_extract_row_width:{where}")
    return [dict(zip(columns, row)) for row in rows]


def extract_inputs(config: Mapping[str, Any], dbc_dir: Path) -> dict[str, Any]:
    """What the row selection depends on besides the database: a change here needs a new extract."""
    return {"loot_map_ids": sorted(loot_maps(config)),
            "dungeon_encounter_dbc_sha256": sha256_file(Path(dbc_dir) / "DungeonEncounter.dbc")}


def load_phase_extract(extract_dir: Path, config: Mapping[str, Any], dbc_dir: Path) -> dict[str, Any]:
    """The verified extract of one phase: {'path', 'sha256', 'world': {table: rows}, 'hotfix': {...}, 'row_digests'}."""
    path = extract_path(extract_dir, str(config["phase_id"]))
    if not path.is_file():
        raise PhaseSourceError(f"phase_db_extract_missing:{path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != EXTRACT_SCHEMA or payload.get("phase_id") != config["phase_id"]:
        raise PhaseSourceError(f"phase_db_extract_schema:{path}")
    if payload.get("inputs") != extract_inputs(config, dbc_dir):
        raise PhaseSourceError(f"phase_db_extract_stale_inputs:{config['phase_id']}")
    tables = payload.get("tables") or {}
    decoded: dict[str, dict[str, list[dict[str, Any]]]] = {"world": {}, "hotfix": {}}
    for scope, columns in (("world", WORLD_COLUMNS), ("hotfix", HOTFIX_COLUMNS)):
        present = set((tables.get(scope) or {}).keys())
        if present != set(columns):
            raise PhaseSourceError(f"phase_db_extract_tables:{scope}:{sorted(present ^ set(columns))}")
        for name, wanted in columns.items():
            decoded[scope][name] = decode_table(tables[scope][name], wanted, f"{scope}.{name}")
    digests = {scope: {name: _digest(rows) for name, rows in sorted(decoded[scope].items())} for scope in decoded}
    if payload.get("row_digests") != digests:
        raise PhaseSourceError(f"phase_db_extract_digest_mismatch:{config['phase_id']}")
    return {"path": path, "sha256": sha256_file(path), "world": decoded["world"], "hotfix": decoded["hotfix"],
            "row_digests": digests}


def item_facts(dbc_dir: Path, hotfix: Mapping[str, list[Mapping[str, Any]]]) -> dict[int, dict[str, int]]:
    """Item-sparse facts by item ID (flag words unsigned), the hotfix row replacing the client row."""
    facts = {int(row["values"][0]): {name: int(row["values"][field]) for name, (field, _column) in FACT_FIELDS.items()}
             for row in load_wdb2(Path(dbc_dir) / "Item-sparse.db2", ITEM_SPARSE_FMT)}
    for row in hotfix["item_sparse"]:
        facts[int(row["ID"])] = {name: int(row[column] or 0) for name, (_field, column) in FACT_FIELDS.items()}
    for fact in facts.values():
        for name in UNSIGNED_FLAG_FACTS:
            fact[name] &= 0xFFFFFFFF
    return facts


def phase_items(dbc_dir: Path, hotfix: Mapping[str, list[Mapping[str, Any]]], facts: Mapping[int, Mapping[str, int]],
                max_required_level: int) -> list[dict[str, Any]]:
    """Every item template of level >= 1 a character up to ``max_required_level`` can use, by item ID.

    InventoryType is the Item row's, or the Item-sparse row's when that is 0
    (``COALESCE(NULLIF(i.InventoryType, 0), s.InventoryType)``); a hotfix ID
    without both an Item and an Item-sparse row has no template in the core.
    """
    rows = {int(row["ID"]): row for row in load_db2_item_rows(Path(dbc_dir))}
    item_layer = {int(row["values"][0]): {"ClassID": int(row["values"][1]), "SubclassID": int(row["values"][2]),
                                          "InventoryType": int(row["values"][6])}
                  for row in load_wdb2(Path(dbc_dir) / "Item.db2", ITEM_FMT)}
    hot_items = {int(row["ID"]): row for row in hotfix["item"]}
    hot_sparse = {int(row["ID"]): row for row in hotfix["item_sparse"]}
    for item_id in sorted(set(hot_items) | set(hot_sparse)):
        layer = hot_items.get(item_id) or item_layer.get(item_id)
        if layer is None or (item_id not in hot_sparse and item_id not in rows):
            rows.pop(item_id, None)
            continue
        row = dict(rows.get(item_id) or {})
        if item_id in hot_sparse:
            row.update({column: hot_sparse[item_id][column] for column in SPARSE_ITEM_COLUMNS})
        row.update({"ID": item_id, "ClassID": int(layer["ClassID"]), "SubclassID": int(layer["SubclassID"]),
                    "InventoryType": int(layer["InventoryType"]) or int(facts[item_id]["inventory_type"]),
                    "source": "hotfix_db_extract"})
        rows[item_id] = row
    return [row for _item_id, row in sorted(rows.items())
            if int(row.get("ItemLevel") or 0) >= 1 and int(row.get("RequiredLevel") or 0) <= int(max_required_level)]
