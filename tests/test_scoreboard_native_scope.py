"""Native DPS over the WCL references' enemy set (Nefarian: no Animated Bone Warriors)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.bot_ml.analyze_combat_log import _damage_by_target_entry
from tools.raid_program.scoreboard_record import (
    NATIVE_SCOPE_KEY, native_excluded_entries, record_from_summary, scope_native_dps, summarize_run_dir)

ROOT = Path(__file__).resolve().parents[1]
NEFARIAN_TARGET = ROOT / "experiments/configs/raid_targets/blackwing_descent_10n_nefarian.json"
NEFARIAN_DPS = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/nefarian_wcl_dps_reference_v1.json"
BONE_WARRIOR = 41918


def test_analyzer_splits_originated_damage_by_target_entry() -> None:
    rows = [{"target_entry": 41376, "originated_amount": 700, "raw_event_amount": 900},
            {"target_entry": BONE_WARRIOR, "originated_amount": 300},
            {"target_entry": 41376, "originated_amount": 100},
            {"target_entry": None, "originated_amount": 5}]
    assert _damage_by_target_entry(rows) == {"0": 5, "41376": 800, str(BONE_WARRIOR): 300}


def test_nefarian_references_and_target_share_one_enemy_set() -> None:
    manifest = json.loads(NEFARIAN_DPS.read_text())
    target = json.loads(NEFARIAN_TARGET.read_text())
    matched = [ref for ref in manifest["references"] if ref["id"] in target["matched_reference_ids"]]
    assert len(matched) == 10 and len({ref["target_scope"] for ref in matched}) == 1
    assert "excludes Animated Bone Warriors (41918)" in matched[0]["target_scope"]
    assert native_excluded_entries(target) == [BONE_WARRIOR]


def test_scope_native_dps_subtracts_excluded_entries_and_fails_closed() -> None:
    summary = {"actors": [{"bot_guid": 1, "damage": 1000, "encounter_window_dps": 100.0},
                          {"bot_guid": 2, "damage": 500, "encounter_window_dps": 50.0}],
               "encounter": {"party_damage": 1500, "encounter_window_party_dps": 150.0}}
    encounter = {"duration_sec": 10.0, "actors": [
        {"actor_guid": 1, "damage_by_target_entry": {"41376": 600, str(BONE_WARRIOR): 400}},
        {"actor_guid": 2, "damage_by_target_entry": {"41270": 500}}]}
    scope_native_dps(summary, encounter, [BONE_WARRIOR])
    first, second = summary["actors"]
    assert (first["encounter_window_dps"], first["encounter_window_dps_all_targets"]) == (60.0, 100.0)
    assert second["encounter_window_dps"] == 50.0 and second[NATIVE_SCOPE_KEY] == [BONE_WARRIOR]
    assert summary["encounter"]["encounter_window_party_dps"] == 110.0
    del encounter["actors"][1]["damage_by_target_entry"]
    with pytest.raises(ValueError, match="no damage_by_target_entry"):
        scope_native_dps({"actors": [{"bot_guid": 2, "damage": 1, "encounter_window_dps": 1.0}]}, encounter,
                         [BONE_WARRIOR])


def test_an_unscoped_summary_cannot_be_recorded_for_nefarian() -> None:
    target = json.loads(NEFARIAN_TARGET.read_text())
    summary = {"actors": [{"bot_guid": 1, "encounter_window_dps": 100.0}]}
    with pytest.raises(ValueError, match="not scoped to the target's native DPS enemy set"):
        record_from_summary(summary, root=ROOT, target=target, scenario="s", label="l", kill_id="k",
                            deaths={"deaths": []})


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def test_summarize_run_dir_reads_the_nefarian_node_and_scopes_native_dps(tmp_path: Path) -> None:
    node = "bwd.nefarian.encounter"
    _write(tmp_path / "report.json", {"run_id": "nef", "completion_reason": "validation_route_manifest_complete",
                                      "native_gameplay_outcome": {"native_clear": True}, "status": {"deaths": 0}})
    _write(tmp_path / "combat_analysis.json", {"encounters": [{
        "route_node_id": node, "duration_sec": 10.0, "party_damage": 1000, "encounter_window_party_dps": 100.0,
        "actors": [{"actor_guid": 7, "actor_name": "Fire", "actor_role": "dps", "damage": 1000,
                    "encounter_window_dps": 100.0,
                    "damage_by_target_entry": {"41376": 750, str(BONE_WARRIOR): 250}}]}]})
    summary = summarize_run_dir(tmp_path, None, "label", None, node, [BONE_WARRIOR])
    actor = summary["actors"][0]
    assert (actor["encounter_window_dps"], actor["encounter_window_dps_all_targets"]) == (75.0, 100.0)
    assert summary["encounter"]["encounter_window_party_dps"] == 75.0
    # Without a declared exclusion the same run keeps the analyzer's value (Magmaw's path).
    plain = summarize_run_dir(tmp_path, None, "label", None, node)
    assert plain["actors"][0]["encounter_window_dps"] == 100.0 and NATIVE_SCOPE_KEY not in plain["actors"][0]


def test_a_no_reference_spec_cannot_qualify_on_the_wowsims_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    from tools.raid_program import scoreboard_core
    from tools.raid_program.scoreboard_core import declared_no_reference_specs, reference_targets
    target = json.loads((ROOT / "experiments/configs/raid_targets/blackwing_descent_10n_maloriak.json").read_text())
    assert declared_no_reference_specs(target) == {"feral_druid_tank"}
    # Even when a verified WoWSims value exists for the spec, the declared gap stays no_reference.
    monkeypatch.setattr(scoreboard_core, "fallback_targets",
                        lambda root, target: {"feral_druid_tank": 9000.0, "fire_mage": 30000.0})
    # Round 2 matched fire_mage to WCL; drop that match so the fallback path is still exercised.
    real_spec_targets = scoreboard_core.spec_targets
    monkeypatch.setattr(scoreboard_core, "spec_targets",
                        lambda root, target: {spec: dps for spec, dps in real_spec_targets(root, target).items()
                                              if spec != "fire_mage"})
    references = reference_targets(ROOT, target)
    assert "feral_druid_tank" not in references
    assert references["fire_mage"]["basis"] == "wowsims_fallback"
    # A declared, gated spec that also has a matched WCL value is a contradiction, not a silent pass.
    monkeypatch.setattr(scoreboard_core, "spec_targets", lambda root, target: {"feral_druid_tank": 16202.0})
    gated = {**target, "dps_gate_exempt_specs": []}
    with pytest.raises(ValueError, match="declared no_reference_until_wcl but has a matched WCL reference"):
        reference_targets(ROOT, gated)
    # For an exempt spec (user decision 2026-09-27) the declaration is documentation and fails nothing.
    assert reference_targets(ROOT, target)["feral_druid_tank"]["basis"] == "wcl"


def test_every_target_declaring_no_reference_keeps_those_specs_unreferenced() -> None:
    from tools.raid_program.scoreboard_core import declared_no_reference_specs, reference_targets
    for path in sorted((ROOT / "experiments/configs/raid_targets").glob("blackwing_descent_10n_*.json")):
        target = json.loads(path.read_text())
        declared = declared_no_reference_specs(target)
        assert not declared & set(reference_targets(ROOT, target)), path.name


# --- persisted enemy scope, validated at evaluation (verdict) -----------------------------------------

from tests.test_raid_scoreboard import SCENARIO, TARGET, kill, record_all, root  # noqa: E402,F401 (fixture)
from tools.raid_program.scoreboard_core import dps_enemy_scope  # noqa: E402
from tools.raid_program.scoreboard_verdict import evaluate_target  # noqa: E402

SCOPE = dps_enemy_scope([BONE_WARRIOR])


def _scope_the_target(root: Path) -> None:
    target = json.loads((root / TARGET).read_text())
    target[NATIVE_SCOPE_KEY] = [BONE_WARRIOR]
    (root / TARGET).write_text(json.dumps(target))


def _marked(record: dict, scope: dict = SCOPE) -> dict:
    record["encounter"]["dps_enemy_scope"] = scope
    for actor in record["actors"]:
        actor["dps_enemy_scope"] = scope
    return record


def test_scoped_target_rejects_unmarked_and_mixed_records(root: Path) -> None:
    _scope_the_target(root)
    # All-target DPS at full strength would pass; unmarked it must not count.
    record_all(root, *(kill("old", f"k{i}") for i in range(3)))
    verdict = evaluate_target(root, SCENARIO, "old")
    assert verdict["status"] == "fail" and "enemy_scope_mismatch" in verdict["reasons"] and verdict["kills"] == 0
    # A mix of marked and unmarked records fails too, and the unmarked one never enters the means.
    record_all(root, *(_marked(kill("mix", f"k{i}")) for i in range(3)), kill("mix", "k9", scale=5.0))
    verdict = evaluate_target(root, SCENARIO, "mix")
    assert verdict["status"] == "fail" and "enemy_scope_mismatch" in verdict["reasons"] and verdict["kills"] == 3
    # A record marked with a different enemy set is a mismatch as well.
    record_all(root, *(_marked(kill("other", f"k{i}"), dps_enemy_scope([BONE_WARRIOR, 1])) for i in range(3)))
    assert "enemy_scope_mismatch" in evaluate_target(root, SCENARIO, "other")["reasons"]
    # Correctly marked records are judged normally.
    record_all(root, *(_marked(kill("new", f"k{i}")) for i in range(3)))
    assert evaluate_target(root, SCENARIO, "new")["status"] == "pass"


def test_unscoped_target_ignores_the_marker(root: Path) -> None:
    record_all(root, *(kill("a", f"k{i}") for i in range(3)))
    assert evaluate_target(root, SCENARIO, "a")["status"] == "pass"


def test_scoped_records_persist_the_marker_and_all_target_values() -> None:
    target = json.loads(NEFARIAN_TARGET.read_text())
    summary = {"native_clear": True, "completion_reason": "validation_route_manifest_complete",
               "encounter": {"duration_sec": 10.0, "encounter_window_party_dps": 60.0,
                             "encounter_window_party_dps_all_targets": 100.0, NATIVE_SCOPE_KEY: [BONE_WARRIOR]},
               "actors": [{"bot_guid": 1, "encounter_window_dps": 60.0, "encounter_window_dps_all_targets": 100.0,
                           NATIVE_SCOPE_KEY: [BONE_WARRIOR]}]}
    record = record_from_summary(summary, root=ROOT, target=target, scenario="s", label="l", kill_id="k",
                                 deaths={"deaths": []})
    assert record["encounter"]["dps_enemy_scope"] == SCOPE
    assert record["encounter"]["encounter_window_party_dps_all_targets"] == 100.0
    assert record["actors"][0]["dps_enemy_scope"] == SCOPE
    assert record["actors"][0]["encounter_window_dps_all_targets"] == 100.0
    # A summary whose encounter lacks the marker is refused like an unmarked actor.
    del summary["encounter"][NATIVE_SCOPE_KEY]
    with pytest.raises(ValueError, match="not scoped"):
        record_from_summary(summary, root=ROOT, target=target, scenario="s", label="l", kill_id="k",
                            deaths={"deaths": []})


def test_scoped_ratio_to_wcl_is_recomputed_and_the_old_one_kept() -> None:
    summary = {"actors": [{"bot_guid": 1, "damage": 1000, "encounter_window_dps": 100.0,
                           "wcl_observed_dps": 50.0, "ratio_to_wcl": 2.0}]}
    encounter = {"duration_sec": 10.0, "actors": [{"actor_guid": 1, "damage_by_target_entry": {str(BONE_WARRIOR): 500}}]}
    scope_native_dps(summary, encounter, [BONE_WARRIOR])
    actor = summary["actors"][0]
    assert (actor["ratio_to_wcl"], actor["ratio_to_wcl_all_targets"]) == (1.0, 2.0)


def test_timeline_bot_damage_excludes_bone_warriors_but_wcl_casts_are_kept(tmp_path: Path) -> None:
    from tests.test_encounter_timeline_comparator import _damage, _run
    from tools.raid_program.scoreboard_record import write_timeline
    node = "bwd.nefarian.encounter"
    run_dir = _run(tmp_path, node, 10.0, [(30001, "tank", "blood_death_knight")], [
        _damage(node, 41376, 30001, 2000, 300), _damage(node, BONE_WARRIOR, 30001, 3000, 700)])
    manifest = tmp_path / "nefarian_wcl_cast_timelines_v1.json"
    _write(manifest, {"reference_id": "r", "duration_sec": 10.0, "actors": [
        {"actor_id": "r-source1", "class_spec": "blood_death_knight", "source_name": "Tank",
         "casts": [{"t": 1.0, "ability": "Death Strike", "target": "Nefarian"},
                   {"t": 2.0, "ability": "Death Strike", "target": "Animated Bone Warrior 1"}]}]})
    output = write_timeline(run_dir, manifest, tmp_path / "timeline.json", node, frozenset(), [BONE_WARRIOR])
    result = json.loads(output.read_text())
    assert result["scope"]["bot_damage_excluded_target_entries"] == [BONE_WARRIOR]
    assert result["scope"]["wcl_casts_filtered_by_target"] is False
    actor = result["actors"][0]
    assert actor["bot_common_window_damage"] == 300
    assert actor["wcl"]["completed_casts"] == 2


def test_omnotron_no_reference_specs_is_an_alias() -> None:
    from tools.raid_program.scoreboard_core import declared_no_reference_specs, reference_targets
    target = json.loads((ROOT / "experiments/configs/raid_targets/"
                         "blackwing_descent_10n_omnotron_defense_system.json").read_text())
    assert declared_no_reference_specs(target) == {"feral_druid_tank"}
    assert "feral_druid_tank" not in reference_targets(ROOT, target)


def test_scope_check_runs_after_existing_exclusions_and_detail_agrees(root: Path) -> None:
    _scope_the_target(root)
    record_all(root, *(_marked(kill("a", f"k{i}")) for i in range(3)), kill("a", "raw"))
    verdict = evaluate_target(root, SCENARIO, "a")
    assert verdict["status"] == "fail" and "enemy_scope_mismatch" in verdict["reasons"] and verdict["kills"] == 3
    detail = {row["kill_id"]: row for row in verdict["kills_detail"]}
    assert detail["a-raw"]["counted"] is False and detail["a-raw"]["exclusion_reason"] == "enemy_scope_mismatch"
    assert all(detail[f"a-k{i}"]["counted"] for i in range(3))
    # Voiding the unmarked record removes it before the scope check: the label passes, and the
    # existing exclusion (voided) takes precedence in kills_detail.
    record_all(root, *(_marked(kill("b", f"k{i}")) for i in range(3)),
               kill("b", "raw", voided={"reason": "unscoped legacy record", "at": "2026-09-27T00:00:00Z"}))
    verdict = evaluate_target(root, SCENARIO, "b")
    assert verdict["status"] == "pass", verdict["reason"]
    detail = {row["kill_id"]: row for row in verdict["kills_detail"]}
    assert detail["b-raw"]["exclusion_reason"] == "voided" and detail["b-raw"]["counted"] is False
