import json

from tools.raid_program.encounter_damage_targets import load_encounter_damage_targets


def test_native_body_parts_are_boss_damage_without_name_heuristics():
    roles = load_encounter_damage_targets(41570)
    assert roles["boss_entries"] == [41570, 42347, 48270]
    assert roles["add_entries"] == [41806, 42321]
    assert roles["sources"][0]["sha256"]


def test_unknown_and_conflicting_contracts_do_not_guess_auxiliary_roles(tmp_path):
    assert load_encounter_damage_targets(123, tmp_path)["boss_entries"] == [123]
    folder = tmp_path / "experiments/configs/cata_raid_encounters/example"
    folder.mkdir(parents=True)
    for index, auxiliary in enumerate((124, 125)):
        (folder / f"contract{index}.json").write_text(json.dumps({"native_damage_targets": {
            "primary_entry": 123, "boss_auxiliary_entries": [auxiliary], "add_entries": [126],
        }}))
    roles = load_encounter_damage_targets(123, tmp_path)
    assert roles["basis"] == "conflicting_encounter_contracts"
    assert roles["boss_entries"] == [123] and roles["add_entries"] == []
