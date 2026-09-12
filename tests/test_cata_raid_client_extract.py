import json
from pathlib import Path

from tools.raid_program.extract_442_client_spell_rows import LOOKUP_TABLES, collect_json_spell_ids, referenced_spell_ids
from tools.raid_program import extract_442_client_spell_rows as extractor


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


def test_trigger_closure_handles_cycles_missing_children_and_reverse_references():
    effects = [
        {"SpellID": "1000", "EffectTriggerSpell": "1001"},
        {"SpellID": "1001", "EffectTriggerSpell": "1000"},
        {"SpellID": "1001", "EffectTriggerSpell": "1002"},
        {"SpellID": "9999", "EffectTriggerSpell": "1000"},
    ]
    assert extractor.trigger_closure({1000}, effects) == {1000, 1001, 1002}


def test_follow_triggers_fetches_each_table_once_and_reports_missing_metadata(tmp_path, monkeypatch):
    calls = []
    def download(table, ids, *, retain_all=False):
        calls.append((table, set(ids), retain_all))
        rows = []
        if table == "SpellEffect":
            rows = [{"SpellID": "1000", "EffectTriggerSpell": "1001"},
                    {"SpellID": "9999", "EffectTriggerSpell": "1000"}]
        elif table == "SpellName":
            rows = [{"ID": "1000"}]
        return {"table": table, "retained_rows": len(rows)}, rows
    output = tmp_path / "extract.json"
    monkeypatch.setattr(extractor, "download_table", download)
    monkeypatch.setattr("sys.argv", ["extract", "--output", str(output),
                                   "--spell-id", "1000", "--follow-triggers"])
    assert extractor.main() == 0
    result = json.loads(output.read_text())
    assert len(calls) == len(extractor.TABLES)
    assert len({call[0] for call in calls}) == len(calls)
    assert calls[0] == ("SpellEffect", {1000}, True)
    assert all(ids == {1000, 1001} for _, ids, _ in calls[1:])
    assert result["missing_spell_name_ids"] == [1001]
    assert result["missing_spell_effect_ids"] == [1001]
    assert result["rows"]["SpellEffect"] == [{"SpellID": "1000", "EffectTriggerSpell": "1001"}]
