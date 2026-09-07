import json
import re
import sqlite3
from pathlib import Path

import pytest

from tools.raid_program.shared_instance_fixture import load_fixture, validate_shared_config

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "experiments/configs/cata_shared_instance_fixture_v1.json"


def test_checked_in_pair_resolves_disjoint_frozen_instances():
    pair = load_fixture(ROOT, FIXTURE)
    a, b = pair["subject"]["expected"], pair["witness"]["expected"]
    assert a.roster_guids == frozenset(range(30001, 30011))
    assert b.roster_guids == frozenset(range(30101, 30111))
    assert a.map_id == b.map_id == 669
    assert a.difficulty == b.difficulty == 0


@pytest.mark.parametrize("mutation", ["shared_shard", "input_drift", "escape", "bool_capacity"])
def test_fixture_rejects_invalid_pair_before_native_admission(tmp_path, mutation):
    fixture = json.loads(FIXTURE.read_text())
    if mutation == "shared_shard":
        fixture["witness_shard_id"] = fixture["subject_shard_id"]
    elif mutation == "input_drift":
        fixture["inputs"][next(iter(fixture["inputs"]))] = "0" * 64
    elif mutation == "escape":
        fixture["inputs"]["../outside"] = "0" * 64
    else:
        fixture["maximum_active_cohorts"] = True
    path = tmp_path / "fixture.json"
    path.write_text(json.dumps(fixture))
    with pytest.raises(ValueError):
        load_fixture(ROOT, path)


@pytest.mark.parametrize("override", ["MapUpdate.Threads = 2", 'BotWorld.RuntimeProfile = "one"',
                                      "BotWorld.AutoStart = 1", "BotPolicyModel.Enable = 1"])
def test_shared_config_rejects_unsafe_global_override(tmp_path, override):
    path = tmp_path / "server.conf"
    base = 'MapUpdate.Threads = 1\nBotWorld.AutoStart = 0\nBotWorld.RuntimeProfile = ""\nBotPolicyModel.Enable = 0\n'
    path.write_text(base)
    validate_shared_config(path)
    path.write_text(base + override + "\n")
    with pytest.raises(ValueError):
        validate_shared_config(path)


def test_pair_provisioning_excludes_other_frozen_pools(tmp_path, monkeypatch):
    from tools.bot_ml import run_live_bot_validation as live

    monkeypatch.setattr(live, "database_url_from_worldserver_conf",
                        lambda _path, key: "mysql://test:unused@localhost/" +
                        ("auth" if key == "LoginDatabaseInfo" else "characters"))
    pair = load_fixture(ROOT, FIXTURE)
    ids = [pair[role]["profile"] for role in ("subject", "witness")]
    report = live.prepare_validation_provisioning(
        tmp_path, ROOT / "experiments/configs/validation_provisioning_cata_001.json",
        ROOT / "dataset/validation_gear_profiles/profiles.json", tmp_path / "config",
        scenario_ids=ids,
    )
    statements = live.split_sql_statements(Path(report["character_sql"]).read_text())
    inserts = [s for s in statements if s.startswith("INSERT INTO `characters`.`characters`")]
    assert len(inserts) == 20
    assert set(report["scenario_ids"]) == set(ids)
    sql = Path(report["character_sql"]).read_text()
    shards = json.loads((ROOT / "experiments/configs/cata_raid_bwd_diagnostic_shards_v1.json").read_text())["shards"]
    for shard in shards:
        if shard["scenario_id"] not in ids:
            assert all("'" + bot["name"] + "'" not in sql for bot in shard["bots"])

    # Compare actual generated item allocation with the complete frozen layout.
    full = live.prepare_validation_provisioning(
        tmp_path / "full", ROOT / "experiments/configs/validation_provisioning_cata_001.json",
        ROOT / "dataset/validation_gear_profiles/profiles.json", tmp_path / "config")
    full_sql = Path(full["character_sql"]).read_text()
    item_pattern = re.compile(r"INSERT INTO `characters`.`item_instance`.*?SELECT (\d+),.*?c\.`name` = '([^']+)';")
    selected_items = {int(guid): name for guid, name in item_pattern.findall(sql)}
    full_items = {int(guid): name for guid, name in item_pattern.findall(full_sql)}
    assert selected_items
    selected_names = {bot["name"] for role in ("subject", "witness") for bot in pair[role]["shard"]["bots"]}
    assert selected_items == {guid: name for guid, name in full_items.items() if name in selected_names}

    # Execute the emitted cleanup joins against selected + excluded owners.
    # SQLite needs a rowid subquery for MySQL's multi-table DELETE syntax; the
    # generated JOIN and WHERE predicates are preserved verbatim.
    db = sqlite3.connect(":memory:")
    try:
        db.execute("ATTACH ':memory:' AS characters")
        db.execute("CREATE TABLE characters.characters(guid INTEGER, name TEXT)")
        db.execute("CREATE TABLE characters.character_inventory(guid INTEGER, item INTEGER)")
        db.execute("CREATE TABLE characters.item_instance(guid INTEGER, owner_guid INTEGER)")
        selected_name = next(iter(selected_names))
        excluded_name = next(name for name in full_items.values() if name not in selected_names)
        db.executemany("INSERT INTO characters.characters VALUES (?, ?)", [(1, selected_name), (2, excluded_name)])
        db.executemany("INSERT INTO characters.character_inventory VALUES (?, ?)", [(1, 9700001), (2, 9700002)])
        db.executemany("INSERT INTO characters.item_instance VALUES (?, ?)", [(9700001, 1), (9700002, 2)])
        deletes = [s for s in statements if s.startswith("DELETE i FROM")]
        assert len(deletes) == 2
        for statement in deletes:
            table = statement.split()[3]
            select = statement.replace("DELETE i FROM", "SELECT i.rowid FROM", 1).rstrip(";")
            db.execute(f"DELETE FROM {table} WHERE rowid IN ({select})")
        assert db.execute("SELECT * FROM characters.character_inventory").fetchall() == [(2, 9700002)]
        assert db.execute("SELECT * FROM characters.item_instance").fetchall() == [(9700002, 2)]
    finally:
        db.close()
