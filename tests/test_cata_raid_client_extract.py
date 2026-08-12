import json
from pathlib import Path

from tools.raid_program.extract_442_client_spell_rows import LOOKUP_TABLES, collect_json_spell_ids, referenced_spell_ids


def test_collects_structured_and_prose_spell_ids(tmp_path: Path):
    contract = tmp_path / "boss.json"
    contract.write_text(json.dumps({"spell_id": 103414, "nested": {"spell": 106108}, "npc": 55265}))
    dossier = tmp_path / "boss.md"
    dossier.write_text("Use spell `105925`; spell identity 106372. NPC 55265 is not a spell.")
    assert referenced_spell_ids([contract, dossier]) == {103414, 105925, 106108, 106372}


def test_json_collector_ignores_non_spell_ids_and_short_values():
    result: set[int] = set()
    collect_json_spell_ids({"spell": 999, "spell_id": 105925, "npc": 55265, "spells": [106108]}, result)
    assert result == {105925, 106108}


def test_small_index_tables_are_retained_for_foreign_key_resolution():
    assert LOOKUP_TABLES == {"SpellDuration", "SpellRadius", "SpellRange", "SpellCastTimes"}
