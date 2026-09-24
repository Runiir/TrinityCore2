"""Generated-SQL checks for the play-mode human participant provisioner (no DB needed)."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

from tools.bot_ml import provision_human_participant as human
from tools.bot_ml.build_validation_provisioning import (
    DEFAULT_DBC_DIR,
    DEFAULT_WOWSIMS_GEAR_PROFILES,
    apply_gear_profiles,
    build_character_insert_sql,
    gem_item_enchant_map,
    load_config,
    load_gear_profiles,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CLASS_SPEC = "retribution_paladin"
TARGET = human.HumanTarget(guid=1, name="Dorala", account=1)
OTHER = human.HumanTarget(guid=4242, name="Testhuman", account=7)
DML = re.compile(r"^(INSERT|UPDATE|DELETE|REPLACE)\b", re.IGNORECASE)
ALLOWED_DML_TABLES = {"characters", "character_inventory", "item_instance", "character_talent",
                      "character_spell", "character_skills", "character_glyphs"}
ALLOWED_CHARACTER_COLUMNS = {"level", "xp", "health", "power1", "talentTree", "talentGroupsCount",
                             "activeTalentGroup", "at_login", "equipmentCache"}
IDENTITY_AND_APPEARANCE = {"name", "account", "race", "class", "gender", "skin", "face", "hairStyle",
                           "hairColor", "facialStyle", "playerBytes", "playerBytes2", "position_x",
                           "position_y", "position_z", "map", "orientation", "zone", "money", "online"}


@pytest.fixture(scope="module", autouse=True)
def repo_cwd():
    previous = os.getcwd()
    os.chdir(REPO_ROOT)  # provisioning helpers resolve data/dbc/enUS relative to the checkout
    yield
    os.chdir(previous)


@pytest.fixture(scope="module")
def loadout():
    return human.resolve_loadout(CLASS_SPEC, TARGET)


@pytest.fixture(scope="module")
def sql(loadout):
    return human.build_human_participant_sql(TARGET, loadout)


@pytest.fixture(scope="module")
def other_sql():
    return human.build_human_participant_sql(OTHER, human.resolve_loadout(CLASS_SPEC, OTHER))


@pytest.fixture(scope="module")
def bot_reference():
    """What build_validation_provisioning emits for the same template bot and profile."""
    config = load_config(human.DEFAULT_PROVISIONING_CONFIG)
    scenario, bot = human.select_template_bot(config, CLASS_SPEC)
    single = {**config, "scenarios": [{**scenario, "bots": [bot]}]}
    profiles = load_gear_profiles(DEFAULT_WOWSIMS_GEAR_PROFILES, profile_ids={CLASS_SPEC})
    applied = apply_gear_profiles(single, profiles)
    text = build_character_insert_sql(applied, gem_mapping=gem_item_enchant_map(DEFAULT_DBC_DIR),
                                      dbc_dir=DEFAULT_DBC_DIR)
    return parse_bot_sql(text, str(bot["name"]))


def statements(text: str) -> list[str]:
    return [line for line in text.splitlines() if line and not line.startswith("--")]


def dml(text: str) -> list[str]:
    return [line for line in statements(text) if DML.match(line)]


def dml_table(statement: str) -> str:
    match = re.search(r"(?:INTO|UPDATE|FROM) `characters`\.`(\w+)`", statement)
    assert match, statement
    return match.group(1)


def parse_bot_sql(text: str, name: str) -> dict:
    rows = [line for line in text.splitlines() if f"'{name}'" in line
            and not line.startswith(("DELETE", "UPDATE", "CREATE", "INSERT IGNORE"))]
    items, slots, consumables = {}, {}, set()
    for line in rows:
        if "`item_instance`" in line:
            guid, entry, count, enchantments = re.search(
                r"SELECT (\d+), (\d+), c\.`guid`, 0, 0, (\d+), 0, '', 0, '([^']*)'", line).groups()
            if enchantments:
                items[int(guid)] = (int(entry), enchantments)
            else:
                consumables.add((int(entry), int(count)))
        elif "`character_inventory`" in line:
            slot, guid = re.search(r"SELECT c\.`guid`, 0, (\d+), (\d+) FROM", line).groups()
            slots[int(guid)] = int(slot)
    return {
        "equipment": {slots[guid]: value for guid, value in items.items()},
        "consumables": consumables,
        "consumable_slots": {slots[g] for g in slots if g not in items},
        "spells": {int(v) for line in rows if "`character_spell`" in line
                   for v in re.findall(r"SELECT c\.`guid`, (\d+), 1, 0", line)},
        "talents": {int(v) for line in rows if "`character_talent`" in line
                    for v in re.findall(r"SELECT c\.`guid`, (\d+), 0 FROM", line)},
        "skills": {tuple(map(int, m)) for line in rows if "`character_skills`" in line
                   for m in re.findall(r"SELECT c\.`guid`, (\d+), (\d+), (\d+)", line)},
        "glyphs": [int(v) for line in rows if "`character_glyphs`" in line
                   for v in re.search(r"SELECT c\.`guid`, 0, ([\d, ]+) FROM", line).group(1).split(", ")],
        "talent_tree": re.search(r"'(\d+) 0 ', '", next(l for l in rows if "INSERT INTO `characters`.`characters`" in l)).group(1),
    }


def parse_human_sql(text: str, guid: int) -> dict:
    lines = statements(text)
    items, slots, consumables = {}, {}, set()
    for line in lines:
        if line.startswith("INSERT INTO `characters`.`item_instance`"):
            item_guid, entry, owner, count, enchantments = re.search(
                r"(?:VALUES \(|SELECT )(\d+), (\d+), (\d+), 0, 0, (\d+), 0, '', 0, '([^']*)'", line).groups()
            assert int(owner) == guid, line
            if enchantments:
                items[int(item_guid)] = (int(entry), enchantments)
            else:
                consumables.add((int(entry), int(count)))
        elif line.startswith("INSERT INTO `characters`.`character_inventory`"):
            owner, slot, item_guid = re.search(r"(?:VALUES \(|SELECT )(\d+), 0, (\d+), (\d+)", line).groups()
            assert int(owner) == guid, line
            slots[int(item_guid)] = int(slot)

    def tuples(table: str) -> list[tuple[int, ...]]:
        line = next(l for l in lines if l.startswith(f"INSERT INTO `characters`.`{table}`"))
        values = line.split(" VALUES ", 1)[1].split(" ON DUPLICATE KEY", 1)[0].rstrip(";")
        return [tuple(int(v) for v in row.split(", ")) for row in re.findall(r"\(([\d, ]+)\)", values)]

    return {
        "equipment": {slots[g]: value for g, value in items.items()},
        "consumables": consumables,
        "consumable_slots": {slots[g] for g in slots if g not in items},
        "item_guids": sorted(set(items) | set(slots)),
        "spells": {row[1] for row in tuples("character_spell")},
        "talents": {row[1] for row in tuples("character_talent")},
        "skills": {row[1:] for row in tuples("character_skills")},
        "glyphs": list(tuples("character_glyphs")[0][2:]),
        "talent_tree": re.search(r"`talentTree` = CONCAT\('(\d+) '", text).group(1),
    }


def test_item_enchantment_strings_match_bot_provisioning(sql, bot_reference):
    mine = parse_human_sql(sql, TARGET.guid)
    assert mine["equipment"] == bot_reference["equipment"]
    assert len(mine["equipment"]) == 16
    # Permanent enchants, gems (6/9/12), socket bonus (15), extra sockets (18) and reforge (24) all present.
    fields = {slot: [int(v) for v in ench.split()] for slot, (_entry, ench) in mine["equipment"].items()}
    assert all(len(row) == 45 for row in fields.values())
    assert fields[8][18] == 3717 and fields[9][18] == 3723 and fields[5][18] == 3729
    assert fields[15][0] == 4099 and fields[0][24] == 140


def test_loadout_matches_bot_talents_glyphs_spells_skills(sql, bot_reference, loadout):
    mine = parse_human_sql(sql, TARGET.guid)
    assert mine["talents"] == bot_reference["talents"]
    assert mine["glyphs"] == bot_reference["glyphs"]
    assert mine["skills"] == bot_reference["skills"]
    assert (164, 525, 525) in mine["skills"]  # Blacksmithing for the bracer/glove sockets, as bots get
    assert mine["spells"] - set(human.RIDING_SPELL_IDS) == bot_reference["spells"]
    assert mine["talent_tree"] == bot_reference["talent_tree"] == "855"
    assert mine["consumables"] == bot_reference["consumables"]
    assert mine["consumable_slots"] == bot_reference["consumable_slots"]
    assert loadout.talent_points == 41 and loadout.template_race == 1


def test_matches_checked_in_bot_provisioning_artifact(sql):
    artifact = REPO_ROOT / "dataset/validation_provisioning/provision_characters.sql"
    if not artifact.is_file():
        pytest.skip("DVC provisioning artifact not pulled")
    text = artifact.read_text(encoding="utf-8")
    reference = parse_bot_sql(text, "Retpally")
    mine = parse_human_sql(sql, TARGET.guid)
    assert mine["equipment"] == reference["equipment"]
    assert mine["talents"] == reference["talents"] and mine["glyphs"] == reference["glyphs"]
    bot_item_guids = [int(v) for v in re.findall(r"INSERT INTO `characters`\.`item_instance` .*? SELECT (\d+),", text)]
    assert max(bot_item_guids) < human.HUMAN_ITEM_GUID_BASE < min(mine["item_guids"])


def test_never_writes_bot_pool_or_group_tables(sql):
    for statement in dml(sql):
        assert "character_bot_pool" not in statement
    assert not re.search(r"`(groups|group_member|group_instance)`", sql)
    pool_mentions = [s for s in statements(sql) if "character_bot_pool" in s]
    assert pool_mentions and all(s.startswith("SET @abort_") for s in pool_mentions)


def test_every_statement_is_scoped_to_the_target_guid(other_sql):
    guid = OTHER.guid
    assert dml(other_sql)
    for statement in dml(other_sql):
        table = dml_table(statement)
        assert table in ALLOWED_DML_TABLES, statement
        if statement.startswith(("UPDATE", "DELETE")):
            where = statement.split(" WHERE ", 1)[1]
            assert re.search(rf"`(guid|owner_guid)` = {guid}\b", where), statement
            if statement.startswith("DELETE ci, ii"):
                assert f"ii.`owner_guid` = {guid}" in statement and f"ci.`guid` = {guid}" in where
        elif table == "item_instance":
            assert re.search(rf"(?:VALUES \(|SELECT )\d+, \d+, {guid}, ", statement), statement
        else:
            rows = re.findall(r"\((\d+), [\d, ]+\)", statement.split(" VALUES ", 1)[1]) \
                if " VALUES " in statement else re.findall(r"SELECT (\d+), ", statement)
            assert rows and set(rows) == {str(guid)}, statement
    # Nothing still points at guid 1 (the default target) when another guid is requested.
    assert not re.search(r"`(guid|owner_guid)` = 1\b", other_sql)


def test_character_update_preserves_identity_and_appearance(sql):
    updates = [s for s in dml(sql) if dml_table(s) == "characters"]
    assert len(updates) == 1 and updates[0].startswith("UPDATE `characters`.`characters` SET ")
    assert updates[0].endswith(f" WHERE `guid` = {TARGET.guid};")
    assignments = updates[0].split(" SET ", 1)[1].rsplit(" WHERE ", 1)[0]
    columns = set(re.findall(r"(?:^|, )`(\w+)` = ", assignments))
    assert columns == ALLOWED_CHARACTER_COLUMNS
    assert not columns & IDENTITY_AND_APPEARANCE


def test_transaction_guards_and_idempotence_structure(sql, loadout):
    assert sql == human.build_human_participant_sql(TARGET, human.resolve_loadout(CLASS_SPEC, TARGET))
    body = statements(sql)
    assert body[0] == "START TRANSACTION;"
    commit = body.index("COMMIT;")
    assert all(not DML.match(s) for s in body[commit + 1:])
    first_dml = next(i for i, s in enumerate(body) if DML.match(s))
    guards = [s for s in body[:first_dml] if s.startswith("SET @abort_")]
    assert {g.split(" = ", 1)[0] for g in guards} == {
        "SET @abort_unless_target_character_matches", "SET @abort_if_bot_pool_character",
        "SET @abort_if_character_online", "SET @abort_if_item_guid_block_foreign"}
    assert all("(SELECT 1 AS `a` UNION ALL SELECT 2)" in g for g in guards)
    assert "`account` = 1" in guards[0] and "`class` = 2" in guards[0]

    block = human.item_guid_block(TARGET.guid)
    guids = loadout.all_item_guids()
    assert guids == list(range(block + 1, block + 1 + len(guids)))
    guid_list = ", ".join(map(str, guids))
    purge_inv = body.index(f"DELETE FROM `characters`.`character_inventory` WHERE `guid` = 1 AND `item` IN ({guid_list});")
    purge_items = body.index(f"DELETE FROM `characters`.`item_instance` WHERE `owner_guid` = 1 AND `guid` IN ({guid_list});")
    clear_slots = next(i for i, s in enumerate(body) if s.startswith("DELETE ci, ii"))
    first_item_insert = next(i for i, s in enumerate(body) if s.startswith("INSERT INTO `characters`.`item_instance`"))
    assert purge_inv < purge_items < first_item_insert and clear_slots < first_item_insert
    cleared = {int(v) for v in re.search(r"ci\.`slot` IN \(([\d, ]+)\)", body[clear_slots]).group(1).split(", ")}
    assert {item["slot"] for item in loadout.equipment} <= cleared and not cleared & {3, 18, 19, 20, 21, 22}

    talent_delete = body.index("DELETE FROM `characters`.`character_talent` WHERE `guid` = 1 AND `talentGroup` = 0;")
    assert talent_delete < next(i for i, s in enumerate(body) if s.startswith("INSERT INTO `characters`.`character_talent`"))
    for table in ("character_spell", "character_skills", "character_glyphs"):
        insert = next(s for s in body if s.startswith(f"INSERT INTO `characters`.`{table}`"))
        assert " ON DUPLICATE KEY UPDATE " in insert
    for statement in body:
        if statement.startswith("INSERT INTO") and "SELECT" in statement.split(" VALUES ")[0] and "FROM DUAL" in statement:
            assert "NOT EXISTS (SELECT 1 FROM `characters`.`character_inventory` WHERE `guid` = 1 AND `bag` = 0" in statement


def test_specialization_spell_cleanup_is_class_scoped(loadout):
    assert set(loadout.talent_spell_ids) <= set(loadout.specialization_spell_ids)
    assert {20473, 53563, 31935} <= set(loadout.specialization_spell_ids)  # holy/prot paladin tree spells
    assert 51490 not in loadout.specialization_spell_ids  # Thunderstorm: shaman elemental tree spell


def test_options_drop_riding_spells_consumables_and_online_guard():
    lean = human.resolve_loadout(CLASS_SPEC, TARGET, include_consumables=False, include_riding_spells=False)
    text = human.build_human_participant_sql(TARGET, lean, online_guard=False)
    assert not lean.consumables and not lean.riding_spell_ids
    assert "@abort_if_character_online" not in text and "FROM DUAL" not in text
    assert "(1, 34091, 1, 0)" not in text and len(lean.all_item_guids()) == 16


def _facts(**overrides):
    facts = {
        "character": {"guid": 1, "account": 1, "name": "Dorala", "race": 10, "class": 2, "gender": 1,
                      "level": 85, "online": 0, "talentGroupsCount": 1, "activeTalentGroup": 0,
                      "talentTree": "0 0 ", "at_login": 0},
        "bot_pool_rows": [], "inventory": [{"bag": 0, "slot": 23, "item": 10, "itemEntry": 6948, "owner_guid": 1}],
        "skills": [], "block_items": [], "block_inventory": [], "max_foreign_item_guid": 9702128,
    }
    facts.update(overrides)
    return facts


def test_database_refusals(loadout):
    ok, notes = human.evaluate_database_facts(_facts(), TARGET, loadout, check_offline=True)
    assert ok == [] and any("race 10" in note for note in notes)
    pool, _ = human.evaluate_database_facts(_facts(bot_pool_rows=[{"guid": 1}]), TARGET, loadout, check_offline=False)
    assert any("character_bot_pool" in reason for reason in pool)
    online = _facts(character={**_facts()["character"], "online": 1})
    refused, _ = human.evaluate_database_facts(online, TARGET, loadout, check_offline=True)
    assert any("online=1" in reason for reason in refused)
    allowed, notes = human.evaluate_database_facts(online, TARGET, loadout, check_offline=False)
    assert allowed == [] and any("online=1" in note for note in notes)
    renamed = _facts(character={**_facts()["character"], "name": "Someone"})
    assert human.evaluate_database_facts(renamed, TARGET, loadout, check_offline=False)[0]
    warrior = _facts(character={**_facts()["character"], "class": 1})
    assert human.evaluate_database_facts(warrior, TARGET, loadout, check_offline=False)[0]
    foreign = _facts(block_items=[{"guid": loadout.equipment[0]["guid"], "owner_guid": 30001}])
    assert human.evaluate_database_facts(foreign, TARGET, loadout, check_offline=False)[0]
    busy = _facts(inventory=[{"bag": 0, "slot": 26, "item": 55, "itemEntry": 1, "owner_guid": 1}],
                  skills=[{"skill": 182, "value": 1, "max": 75}, {"skill": 186, "value": 1, "max": 75}])
    _, notes = human.evaluate_database_facts(busy, TARGET, loadout, check_offline=False)
    assert any("26" in note and "skipped" in note for note in notes)
    assert any("primary professions" in note for note in notes)


def test_cli_refuses_pool_character_and_writes_nothing(tmp_path, monkeypatch):
    output = tmp_path / "out.sql"
    monkeypatch.setattr(human, "read_database_facts", lambda *a, **k: _facts(bot_pool_rows=[{"guid": 1}]))
    assert human.main(["--guid", "1", "--name", "Dorala", "--class-spec", CLASS_SPEC, "--output", str(output)]) == 2
    assert not output.exists()


def test_cli_writes_sql_without_db(tmp_path, capsys):
    output = tmp_path / "play" / "dorala.sql"
    assert human.main(["--guid", "1", "--name", "Dorala", "--class-spec", CLASS_SPEC,
                       "--output", str(output), "--no-db", "--account", "1"]) == 0
    assert output.read_text(encoding="utf-8").startswith("-- Generated by tools.bot_ml.provision_human_participant")
    assert '"item_count": 16' in capsys.readouterr().out
    with pytest.raises(SystemExit):
        human.main(["--guid", "1", "--name", "Dorala", "--class-spec", CLASS_SPEC,
                    "--output", str(output), "--no-db", "--check-offline"])
