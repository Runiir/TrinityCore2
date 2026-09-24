"""Magmaw duty receipts: extraction from synthetic run dirs and tarballs, and the committed step-0 fixture.

Synthetic evidence only; nothing here launches a server or touches DVC.
"""
import json
import os
import tarfile
import tempfile
from pathlib import Path

import pytest

from tools.raid_program import magmaw_duty_receipts as receipts
from tools.raid_program.magmaw_duty_receipts import (
    build_fixture, evidence_confirmed, extract_duty_receipts, main, wave_alternation,
)

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/fixtures/magmaw_full_roster_duties_v1.json"
NODE = "bwd.magmaw.encounter"


def rotation(revision, history, completed=2):
    return {"active_mage_guid": 30007, "alternate_mage_guid": 30007, "primary_mage_guid": 30006,
            "hunter_guid": 30009, "completed_waves": completed, "last_revision": revision, "wave": completed + 1,
            "history": [{"wave": wave, "mage_guid": mage, "reason": reason, "revision": wave * 100}
                        for wave, mage, reason in history]}


def outcome(actor, spell, *, action="offensive_cooldown", result="ok", phase="cast", node=NODE, count=1):
    return {"action_name": action, "action_type": "cast", "actor_guid": actor, "spell_id": spell,
            "result": result, "phase": phase, "route_node_id": node, "count": count}


def run_dir(folder: Path, *, log=True, latest=True) -> Path:
    folder.mkdir(parents=True)
    newest = rotation(2648, [(3, 30006, "alternate"), (1, 30006, "initial"), (2, 30007, "alternate")])
    older = rotation(1200, [(1, 30006, "initial")], completed=0)
    if latest:
        (folder / "latest.json").write_text(json.dumps({"diagnosis": {"bots": [
            {"diagnosis": {"magmaw_personal_parasite_escape": {"baiter_rotation": older}}},
            {"snapshot": {"magmaw_personal_parasite_escape": {"baiter_rotation": newest}}}]}}))
    if log:
        rows = [outcome(30001, 88747, count=3), outcome(30008, 88747, result="cast_failed"),
                outcome(30001, 88751, result="casting"), outcome(30002, 56222, action="taunt"),
                outcome(30004, 62124, action="taunt", node="bwd.magmaw.drudges"),
                outcome(30010, 2825), outcome(30006, 80353, result="casting", phase="profile_resolve"),
                outcome(30006, 133)]
        (folder / "combat_log.json").write_text(json.dumps({"action_outcomes": rows, "recent_events": []}))
    (folder / "report.json").write_text('{"large": "not read"}')
    return folder


def check_receipt(receipt):
    assert receipt["baiter_rotation"] == {
        "primary_mage_guid": 30006, "alternate_mage_guid": 30007, "hunter_guid": 30009, "completed_waves": 2,
        "last_revision": 2648, "history": [{"wave": 1, "mage_guid": 30006, "reason": "initial"},
                                           {"wave": 2, "mage_guid": 30007, "reason": "alternate"},
                                           {"wave": 3, "mage_guid": 30006, "reason": "alternate"}]}
    assert receipt["wild_mushroom"] == {"casters": [30001], "cast_count": 3, "attempted_by": [30008],
                                        "spell_ids": [88747], "by_caster": {"30001": [88747]}}
    assert receipt["detonate"]["casters"] == [30001]
    assert receipt["taunt"]["casters"] == [30002] and receipt["taunt"]["spell_ids"] == [56222]
    assert receipt["taunt"]["by_caster"] == {"30002": [56222]}  # the drudge-node taunt is not the encounter
    assert receipt["bloodlust"]["casters"] == [30010] and receipt["bloodlust"]["attempted_by"] == [30006]
    assert receipt["misdirection"] == {"casters": [], "cast_count": 0, "attempted_by": [], "spell_ids": [],
                                       "by_caster": {}}
    assert receipt["encounter_action_rows"] == 7 and receipt["missing"] == []


def test_run_dir_receipts(tmp_path):
    receipt = extract_duty_receipts(run_dir(tmp_path / "scoreboard-x-k1"))
    check_receipt(receipt)
    assert receipt["run_dir_name"] == "scoreboard-x-k1"


def test_missing_members_are_recorded_as_empty(tmp_path):
    receipt = extract_duty_receipts(run_dir(tmp_path / "bare", log=False, latest=False))
    assert receipt["missing"] == ["latest.json", "combat_log.json"] and receipt["baiter_rotation"] is None
    assert receipt["taunt"]["casters"] == [] and receipt["wild_mushroom"]["casters"] == []


def test_tarball_extracts_only_the_needed_members_and_cleans_up(tmp_path, monkeypatch):
    folder = run_dir(tmp_path / "scoreboard-x-k2")
    (tmp_path / "scoreboard-x-k2-analysis").mkdir()
    (tmp_path / "scoreboard-x-k2-analysis" / "summary.json").write_text("{}")
    tarball = tmp_path / "scoreboard_x-k2.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        tar.add(folder, arcname=folder.name)
        tar.add(tmp_path / "scoreboard-x-k2-analysis", arcname="scoreboard-x-k2-analysis")
    seen = {}
    original = receipts.receipts_from_run_dir

    def spy(path, source=None):
        seen["temp"] = path.parent
        seen["files"] = sorted(os.listdir(path))
        return original(path, source)
    monkeypatch.setattr(receipts, "receipts_from_run_dir", spy)
    receipt = extract_duty_receipts(tarball)
    check_receipt(receipt)
    assert receipt["source"] == tarball.name and receipt["run_dir_name"] == "scoreboard-x-k2"
    assert seen["files"] == ["combat_log.json", "latest.json"]
    assert seen["temp"].name.startswith("magmaw-duty-receipts-") and not seen["temp"].exists()
    assert seen["temp"].parent == Path(tempfile.gettempdir())


def test_cli_writes_receipts_per_run(tmp_path):
    first = run_dir(tmp_path / "scoreboard-x-k1")
    second = run_dir(tmp_path / "scoreboard-x-k2")
    tarball = tmp_path / "k2.tar.gz"
    with tarfile.open(tarball, "w:gz") as tar:
        tar.add(second, arcname=second.name)
    output = tmp_path / "out" / "receipts.json"
    assert main(["--kill", str(first), "--kill", str(tarball), "--output", str(output)]) == 0
    written = json.loads(output.read_text())
    assert written["schema"] == "magmaw_duty_receipts_v1"
    assert sorted(written["kills"]) == ["scoreboard-x-k1", "scoreboard-x-k2"]
    merged = tmp_path / "merged.json"
    assert main(["--receipts", str(output), "--output", str(merged)]) == 0
    assert json.loads(merged.read_text()) == written


def test_wave_alternation_rule():
    base = {"primary_mage_guid": 1, "alternate_mage_guid": 2}
    history = [{"wave": 1, "mage_guid": 1, "reason": "initial"}, {"wave": 2, "mage_guid": 2, "reason": "alternate"},
               {"wave": 3, "mage_guid": 1, "reason": "alternate"}]
    assert wave_alternation(base | {"history": history}) is True
    assert wave_alternation(base | {"history": [history[0], history[0] | {"wave": 2}]}) is False
    assert wave_alternation(base | {"history": [history[1]]}) is False
    assert wave_alternation(base | {"history": []}) is None


def test_build_fixture_matches_scoreboard_kills(tmp_path):
    root = tmp_path / "repo"
    routes = root / receipts.ROUTES_PATH
    routes.parent.mkdir(parents=True)
    roster = [{"guid": 30000 + index, "roster_slot_id": f"slot_{index}"} for index in range(1, 11)]
    routes.write_text(json.dumps({"scenario_id": "other", "route_node_id": NODE, "roster_identity": []}) + "\n"
                      + json.dumps({"scenario_id": receipts.ROUTE_SCENARIO, "route_node_id": NODE,
                                    "roster_identity": roster}) + "\n")
    board = root / "artifacts/cata_raid_program/scoreboard" / f"{receipts.SCENARIO}.jsonl"
    board.parent.mkdir(parents=True)
    kills = [{"schema": "raid_scoreboard_kill_v1", "kill_id": f"lab-k{n}", "label": "lab", "native_clear": True,
              "run_dir": f"/tmp/scoreboard-lab-k{n}", "evidence_dvc_pointer": f"artifacts/k{n}.tar.gz.dvc"}
             for n in (1, 2)]
    board.write_text("".join(json.dumps(kill) + "\n" for kill in kills))
    found = {name: extract_duty_receipts(run_dir(tmp_path / name)) for name in ("scoreboard-lab-k1", "scoreboard-lab-k2")}
    found["scoreboard-lab-k2"]["taunt"] = found["scoreboard-lab-k2"]["taunt"] | {"casters": [], "spell_ids": []}
    fixture = build_fixture(root, "lab", found)
    assert fixture["schema"] == "magmaw_full_roster_duties_v1" and fixture["roster_identity"] == roster
    assert sorted(fixture["per_kill"]) == ["lab-k1", "lab-k2"]
    assert fixture["per_kill"]["lab-k1"]["evidence_dvc_pointer"] == "artifacts/k1.tar.gz.dvc"
    confirmed = fixture["evidence_confirmed"]
    assert confirmed["baiter_primary_mage_guid"]["value"] == 30006 and confirmed["baiter_primary_mage_guid"]["consistent"]
    assert confirmed["taunt_casters"]["consistent"] is False and confirmed["taunt_casters"]["consistent_when_present"]
    assert confirmed["taunt_casters"]["union"] == [30002] and confirmed["taunt_casters"]["kills_with_value"] == 1
    with pytest.raises(ValueError, match="no receipts for kills lab-k2"):
        build_fixture(root, "lab", {"scoreboard-lab-k1": found["scoreboard-lab-k1"]})


# --- committed fixture --------------------------------------------------------------------------

def test_committed_fixture_is_well_formed():
    assert FIXTURE.stat().st_size < 30 * 1024
    fixture = json.loads(FIXTURE.read_text())
    assert fixture["schema"] == "magmaw_full_roster_duties_v1" and fixture["label"] == "b5-d1898555"
    assert fixture["scenario"] == "blackwing_descent_10n_magmaw"
    roster = fixture["roster_identity"]
    assert len(roster) == 10 and [row["guid"] for row in roster] == list(range(30001, 30011))
    assert {row["roster_slot_id"] for row in roster} >= {"raid_tank_1", "raid_dps_4", "raid_dps_5"}
    assert fixture["code_derived_not_in_evidence"] == ["hook_riders", "pull_tank", "bloodlust_owner"]
    assert "tests/test_magmaw_duty_plan.py" in fixture["code_derived_note"]
    per_kill = fixture["per_kill"]
    assert len(per_kill) == 8 and all(kill_id.startswith("b5-d1898555-") for kill_id in per_kill)
    for kill in per_kill.values():
        assert kill["native_clear"] is True and kill["evidence_dvc_pointer"].endswith(".tar.gz.dvc")
        for duty in ("wild_mushroom", "detonate", "taunt", "bloodlust", "misdirection"):
            assert isinstance(kill[duty]["casters"], list)
    confirmed = fixture["evidence_confirmed"]
    for item in confirmed.values():
        assert isinstance(item["consistent"], bool) and item["observed"]
    assert confirmed == evidence_confirmed(per_kill)  # the summary is reproducible from the per-kill receipts
    # What every accepted kill agrees on (the allocator's tier-1 selectors must reproduce these).
    for key, value in (("baiter_primary_mage_guid", 30006), ("baiter_alternate_mage_guid", 30007),
                       ("baiter_hunter_guid", 30009), ("baiter_per_wave_alternation", True),
                       ("wild_mushroom_casters", [30001])):
        assert confirmed[key]["consistent"] is True and confirmed[key]["value"] == value, key
    for key, union in (("detonate_casters", [30001]), ("taunt_casters", [30002]), ("taunt_spell_ids", [56222])):
        assert confirmed[key]["consistent_when_present"] is True and confirmed[key]["union"] == union, key
