"""The pinned database inputs of raid_phase_gear (tools.bot_ml.phase_gear_extract, extract_phase_gear_db).

The builder reads world loot/vendor rows and hotfix item rows only from a
DVC-tracked extract, never from the database; the extract script reads the
database read-only and fails closed when either database is unreachable (no
client-data fallback); the loader refuses an extract whose selection inputs,
tables or row digests no longer match.
"""

from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path

import pytest
import yaml

from tools.bot_ml import extract_phase_gear_db as extractor
from tools.bot_ml.phase_gear_extract import (
    DEFAULT_EXTRACT_DIR,
    HOTFIX_COLUMNS,
    WORLD_COLUMNS,
    decode_table,
    extract_path,
    item_facts,
    load_phase_extract,
    phase_items,
)
from tools.bot_ml.phase_gear_profiles import load_phase_config
from tools.bot_ml.phase_gear_sources import PhaseSourceError, world_sources_from_rows

ROOT = Path(__file__).resolve().parents[1]
T11 = ROOT / "experiments/configs/raid_gear_phases/cata_t11_v1.json"
DBC = ROOT / "data/dbc/enUS"
PHASE_OUTPUT = ROOT / "dataset/raid_phase_gear_profiles"


def _world() -> dict[str, list[dict]]:
    """Magmaw-like rows: a spawned creature with a difficulty entry, a reference chain, a script-summoned boss."""
    return {
        "creature_spawns": [{"map": 669, "id": 100}],
        "encounter_credits": [{"entry": 1024, "creditType": 0, "creditEntry": 200}],
        "creature_templates": [{"entry": 100, "difficulty_entry_1": 101, "difficulty_entry_2": 0, "difficulty_entry_3": 0, "lootid": 100},
                               {"entry": 200, "difficulty_entry_1": 0, "difficulty_entry_2": 0, "difficulty_entry_3": 0, "lootid": 200}],
        "difficulty_templates": [{"entry": 101, "difficulty_entry_1": 0, "difficulty_entry_2": 0, "difficulty_entry_3": 0, "lootid": 101}],
        "chests": [],
        "creature_loot": [{"Entry": 100, "Item": 415700, "Reference": 415700}, {"Entry": 101, "Item": 5, "Reference": 0},
                          {"Entry": 200, "Item": 6, "Reference": 0}],
        "gameobject_loot": [],
        "reference_loot": [{"Entry": 415700, "Item": 59341, "Reference": 0}],
        "npc_vendor": [{"entry": 7, "item": 59341, "ExtendedCost": 3400}],
    }


def _hotfix() -> dict[str, list[dict]]:
    sparse = {column: 0 for column in HOTFIX_COLUMNS["item_sparse"]}
    return {"item": [{"ID": 68601, "ClassID": 2, "SubclassID": 15, "InventoryType": 13}],
            "item_sparse": [{**sparse, "ID": 68601, "Display": "Scaleslicer (hotfixed)", "Quality": 4, "ItemLevel": 372,
                             "RequiredLevel": 85, "AllowableClass": -1, "InventoryType": 13, "Flags1": 0x80000,
                             "MaxCount": 0, "ItemStatType1": 3, "ItemStatValue1": 160}]}


def _config(**sources) -> dict:
    config = json.loads(T11.read_text(encoding="utf-8"))
    config["sources"].update(sources)
    return config


def _write(folder: Path, config: dict, world=None, hotfix=None) -> Path:
    payload = extractor.build_extract(config, DBC, world or _world(), hotfix or _hotfix(), {"world": "world", "hotfix": "hotfixes"})
    path = extract_path(folder, config["phase_id"])
    extractor.write_extract(path, payload)
    return path


# --- the pure derivation from pinned rows ---------------------------------------------------------------

def test_world_sources_follow_the_pinned_rows():
    world = world_sources_from_rows(_world(), _config(), {1024: 669})
    assert [row["reference_chain"] for row in world["loot"][59341]] == [[415700]]
    assert world["loot"][5][0]["source_entry"] == 101 and world["loot"][5][0]["map_id"] == 669, "difficulty entry"
    assert world["loot"][6][0]["source_entry"] == 200, "the encounter's kill-credit creature has no spawn row"
    assert world["vendor"][59341] == [{"vendor_entry": 7, "extended_cost": 3400}]
    broken = _world()
    broken["reference_loot"] = []
    with pytest.raises(PhaseSourceError, match="phase_loot_tables_empty"):
        world_sources_from_rows(broken, _config(), {1024: 669})
    broken = _world()
    del broken["npc_vendor"]
    with pytest.raises(PhaseSourceError, match="phase_world_rows_missing"):
        world_sources_from_rows(broken, _config(), {1024: 669})


# --- the extract is a pinned, verified input --------------------------------------------------------------

def test_the_extract_is_deterministic_and_round_trips(tmp_path):
    config = _config()
    first = _write(tmp_path / "a", config).read_bytes()
    world = _world()
    world["npc_vendor"] = list(world["npc_vendor"])
    assert _write(tmp_path / "b", config, world).read_bytes() == first
    loaded = load_phase_extract(tmp_path / "a", config, DBC)
    assert loaded["world"] == _world() and loaded["hotfix"]["item"] == _hotfix()["item"]
    assert set(loaded["row_digests"]["world"]) == set(WORLD_COLUMNS)


def test_the_extract_loader_fails_closed(tmp_path):
    config = _config()
    with pytest.raises(PhaseSourceError, match="phase_db_extract_missing"):
        load_phase_extract(tmp_path, config, DBC)
    path = _write(tmp_path, config)
    moved = _config(loot_maps=[*config["sources"]["loot_maps"], {"map_id": 859, "name": "Zul'Gurub", "kind": "heroic_dungeon"}])
    with pytest.raises(PhaseSourceError, match="phase_db_extract_stale_inputs"):
        load_phase_extract(tmp_path, moved, DBC)
    payload = json.loads(path.read_text(encoding="utf-8"))
    # The review's scenario: a reachable loot row changed without re-extracting (the row digests no longer match).
    tampered = copy.deepcopy(payload)
    tampered["tables"]["world"]["creature_loot"]["rows"][0][1] = 59501
    path.write_text(json.dumps(tampered))
    with pytest.raises(PhaseSourceError, match="phase_db_extract_digest_mismatch"):
        load_phase_extract(tmp_path, config, DBC)
    reshaped = copy.deepcopy(payload)
    del reshaped["tables"]["hotfix"]["item_sparse"]
    path.write_text(json.dumps(reshaped))
    with pytest.raises(PhaseSourceError, match="phase_db_extract_tables"):
        load_phase_extract(tmp_path, config, DBC)


def test_a_row_of_the_wrong_width_is_refused(tmp_path):
    """The review's scenario: a declared one-column row holding two cells decoded through zip, dropping a cell."""
    assert decode_table({"columns": ["a"], "rows": [[1]]}, ("a",), "t") == [{"a": 1}]
    for rows in ([[1, 2]], [[]], [1], [{"a": 1}]):
        with pytest.raises(PhaseSourceError, match="phase_db_extract_row_width:t"):
            decode_table({"columns": ["a"], "rows": rows}, ("a",), "t")
    config = _config()
    path = _write(tmp_path, config)
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["tables"]["world"]["creature_spawns"]["rows"][0].append(1)
    path.write_text(json.dumps(payload))
    with pytest.raises(PhaseSourceError, match="phase_db_extract_row_width:world.creature_spawns"):
        load_phase_extract(tmp_path, config, DBC)


def test_hotfix_rows_replace_the_client_item_rows():
    if not (DBC / "Item-sparse.db2").is_file():
        pytest.skip("client DB2 files not extracted")
    client = {int(row["ID"]): row for row in phase_items(DBC, {"item": [], "item_sparse": []}, item_facts(DBC, {"item_sparse": []}), 85)}
    facts = item_facts(DBC, _hotfix())
    items = {int(row["ID"]): row for row in phase_items(DBC, _hotfix(), facts, 85)}
    assert int(client[68601]["ItemLevel"]) == 359 and int(items[68601]["ItemLevel"]) == 372
    assert items[68601]["Display"] == "Scaleslicer (hotfixed)" and items[68601]["source"] == "hotfix_db_extract"
    assert facts[68601]["flags"] == 0x80000 and item_facts(DBC, {"item_sparse": []})[68601]["flags"] == 0


# --- the extract script reads the database read-only and fails closed ---------------------------------------

class _FakeConnection:
    def __init__(self, references: dict[int, list[dict]]):
        self.references, self.statements = references, []

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql):
        self.statements.append(sql)
        wanted = [int(value) for value in re.search(r"IN \(([\d,]+)\)", sql).group(1).split(",")]
        self.rows = [row for entry in wanted for row in self.references.get(entry, [])]

    def fetchall(self):
        return self.rows


def test_reference_rows_are_followed_to_a_fixed_point():
    references = {1: [{"Entry": 1, "Item": 2, "Reference": 2}, {"Entry": 1, "Item": 10, "Reference": 0}],
                  2: [{"Entry": 2, "Item": 1, "Reference": 1}, {"Entry": 2, "Item": 11, "Reference": 0}],
                  3: [{"Entry": 3, "Item": 12, "Reference": 0}]}
    conn = _FakeConnection(references)
    rows = extractor.reference_closure(conn, [{"Entry": 9, "Item": 1, "Reference": 1}])
    assert [(row["Entry"], row["Item"]) for row in rows] == [(1, 2), (1, 10), (2, 1), (2, 11)], "cycle closed, 3 unreachable"
    assert len(conn.statements) == 2


def test_the_extract_script_fails_closed_without_the_hotfix_database(tmp_path, monkeypatch):
    def unreachable(url):
        raise ConnectionRefusedError(f"cannot reach {url.rsplit('@', 1)[-1]}")

    monkeypatch.setattr(extractor, "connect_mysql", unreachable)
    monkeypatch.setattr(sys, "argv", ["extract_phase_gear_db", "--world-database-url", "mysql://u:p@127.0.0.1:1/world",
                                      "--hotfix-database-url", "mysql://u:p@127.0.0.1:1/hotfixes", "--output-dir", str(tmp_path)])
    with pytest.raises(ConnectionRefusedError, match="hotfixes"):
        extractor.main()
    assert not list(tmp_path.iterdir()), "nothing is written from client data alone"


# --- the stage and builder never touch the database -----------------------------------------------------

def test_the_phase_stage_declares_the_extract_and_no_database():
    import tools.bot_ml.build_phase_gear_profiles as builder

    stage = yaml.safe_load((ROOT / "dvc.yaml").read_text(encoding="utf-8"))["stages"]["raid_phase_gear"]
    deps = {str(dep) for dep in stage["deps"]}
    assert {"dataset/raid_phase_gear_db_extract", "tools/bot_ml/phase_gear_extract.py",
            "tools/bot_ml/phase_gear_spell_requirements.py"} <= deps
    assert "--db-extract-dir dataset/raid_phase_gear_db_extract" in " ".join(stage["cmd"].split())
    assert "database" not in stage["cmd"] and "worldserver" not in stage["cmd"]
    assert not {"connect_mysql", "fetch_items", "fetch_hotfix_items", "database_url_from_worldserver_conf"} & set(vars(builder))
    assert DEFAULT_EXTRACT_DIR == ROOT / "dataset/raid_phase_gear_db_extract"


def test_the_stage_output_rebuilds_byte_identically_without_a_database(tmp_path, monkeypatch):
    """The pinned extract alone reproduces the DVC output (run with every database connection refused)."""
    import pymysql

    import tools.bot_ml.extract_world_knowledge as world_knowledge
    from tools.bot_ml import build_phase_gear_profiles as builder

    if not extract_path(DEFAULT_EXTRACT_DIR, "cata_t11").is_file() or not (PHASE_OUTPUT / "profiles.json").is_file():
        pytest.skip("raid_phase_gear extract or output not hydrated (dvc pull)")

    def refused(*_args, **_kwargs):
        raise AssertionError("the phase-gear build opened a database connection")

    monkeypatch.setattr(pymysql, "connect", refused)
    monkeypatch.setattr(world_knowledge, "connect_mysql", refused)
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(sys, "argv", ["build_phase_gear_profiles", "--output-dir", str(tmp_path)])
    assert builder.main() == 0
    for name in ("profiles.json", "sources.json", "report.json", "manifest.json"):
        assert (tmp_path / name).read_bytes() == (PHASE_OUTPUT / name).read_bytes(), name
    assert load_phase_config(T11)["phase_id"] == "cata_t11"
