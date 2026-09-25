"""Raid-target roster variants: a canonical-composition shard run is judged against its own roster.

The accepted Magmaw target stays byte-identical (its verdicts pin target_sha256); the c0 roster lives in
the sidecar experiments/configs/raid_target_roster_variants/blackwing_descent_10n_magmaw.json.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tests.test_raid_scoreboard import SCENARIO, TARGET, kill, root  # noqa: F401  (root is a fixture)
from tools.raid_program import graph_acceptance
from tools.raid_program.scoreboard import append_record, evaluate_target
from tools.raid_program.scoreboard_core import (
    ROSTER_VARIANTS_DIR, file_sha256, load_target, roster, roster_variants_path, target_for_records,
)
from tools.raid_program.scoreboard_record import record_from_summary
from tools.raid_program.scoreboard_show import render

ROOT = Path(__file__).resolve().parents[1]
C0 = "blackwing_descent_10n_magmaw_c0_diagnostic"
SIDECAR = f"{ROSTER_VARIANTS_DIR}/{SCENARIO}.json"
C0_ROSTER = json.loads((ROOT / SIDECAR).read_text())["variants"][0]["roster"]


def _kill(scenario_id: str | None) -> dict:
    return {"shard_identity": {"scenario_id": scenario_id}} if scenario_id else {}


def test_c0_shard_runs_use_the_canonical_variant_and_legacy_runs_keep_the_accepted_roster():
    target = load_target(ROOT, SCENARIO)
    legacy = roster(target)
    assert sorted(legacy) == [str(guid) for guid in range(30001, 30011)]
    judged = target_for_records(ROOT, target, [_kill(C0), _kill(C0)])
    assert sorted(roster(judged)) == [str(guid) for guid in range(11000001, 11000011)]
    assert roster(judged)["11000003"]["spec"] == "beast_mastery_hunter"
    assert judged["validation_scenario_id"] == C0
    assert judged["roster_variant"] == {"path": SIDECAR, "sha256": file_sha256(ROOT / SIDECAR),
                                        "validation_scenario_id": C0}
    for records in ([], [_kill(None)], [_kill("blackwing_descent_10n_magmaw_diagnostic")], [_kill(C0), _kill(None)]):
        assert target_for_records(ROOT, target, records) is target


def test_a_sidecar_of_another_target_is_refused(tmp_path):
    path = roster_variants_path(tmp_path, SCENARIO)
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"schema": "raid_target_roster_variants_v1", "target_scenario": "other",
                                "variants": []}))
    with pytest.raises(ValueError, match="sidecar"):
        target_for_records(tmp_path, {"scenario": SCENARIO, "roster": {}}, [_kill(C0)])
    assert target_for_records(tmp_path, {}, [_kill(C0)]) == {}  # no scenario: nothing to look up


def _c0_kill(label: str, name: str) -> dict:
    record = kill(label, name, shard_identity={"scenario_id": C0, "cohort_id": "blackwing_descent_10n_magmaw_c0"})
    record["actors"] = [{"actor_id": actor_id, "name": row["name"], "spec": row["spec"], "role": row["role"],
                         "encounter_window_dps": 30000.0, "damage_uptime": 0.8, "casts_per_minute": 30.0,
                         "hps": 0.0} for actor_id, row in C0_ROSTER.items()]
    return record


def test_c0_kills_are_judged_and_shown_with_the_c0_roster(root):  # noqa: F811
    (root / SIDECAR).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / SIDECAR, root / SIDECAR)
    for name in ("k1", "k2", "k3"):
        append_record(root, SCENARIO, _c0_kill("c0", name))
    for name in ("k1", "k2", "k3"):
        append_record(root, SCENARIO, kill("legacy", name))
    verdict = evaluate_target(root, SCENARIO, "c0")
    assert verdict["roster"]["expected"] == sorted(C0_ROSTER) and not verdict["roster"]["missing"]
    assert sorted(verdict["actors"]) == sorted(C0_ROSTER)
    assert verdict["roster_variant"]["validation_scenario_id"] == C0
    assert verdict["target_sha256"] == file_sha256(root / TARGET)
    legacy = evaluate_target(root, SCENARIO, "legacy")
    assert "roster_variant" not in legacy and "11000001" not in legacy["actors"]
    shown = render(root, SCENARIO, "c0")
    assert f"roster={C0}" in shown.splitlines()[0]
    assert "Bwmgwnbc" in shown and "beast_mastery_hunter" in shown
    assert "roster=" not in render(root, SCENARIO, "legacy").splitlines()[0]


def test_a_c0_summary_takes_specs_from_the_c0_roster(root):  # noqa: F811
    (root / SIDECAR).parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(ROOT / SIDECAR, root / SIDECAR)
    target = load_target(root, SCENARIO)
    summary = {"native_clear": True, "completion_reason": "validation_route_manifest_complete",
               "shard_identity": {"scenario_id": C0},
               "actors": [{"bot_guid": 11000003, "bot_name": "Bwmgwnbc", "class_spec": "unknown",
                           "encounter_window_dps": 1.0}]}
    record = record_from_summary(summary, root=root, target=target, scenario=SCENARIO, label="c0",
                                 kill_id="c0-k1", deaths={})
    assert record["actors"][0]["spec"] == "beast_mastery_hunter" and record["actors"][0]["role"] == "dps"


def test_the_accepted_magmaw_graph_still_accepts_its_verdict():
    """The target bytes the saved Magmaw verdicts pin are unchanged (review blocker: target_sha256)."""
    unit = json.loads((ROOT / "experiments/configs/cata_raid_active_work_unit_v1.json").read_text())
    verdict_path = ROOT / "artifacts/cata_raid_program/verdicts/blackwing_descent_10n_magmaw-b5-d1898555-7fcea04e9dd3.json"
    if not verdict_path.is_file():
        pytest.skip("accepted Magmaw verdict not hydrated")
    verdict = json.loads(verdict_path.read_text())
    assert verdict["target_sha256"] == "46c17523fec43f26350d414a8fc5bf66c930109094ac3821bea0c87ff6b36ef2"
    assert "roster_variant" not in verdict
    graph_acceptance.check_inputs(ROOT, unit["development_graph"], verdict)
    tampered = {**verdict, "roster_variant": {"path": SIDECAR, "sha256": "0" * 64}}
    with pytest.raises(Exception, match="roster variant changed"):
        graph_acceptance.check_inputs(ROOT, unit["development_graph"], tampered)
