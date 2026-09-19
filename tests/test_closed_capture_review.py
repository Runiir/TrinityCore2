from pathlib import Path
import hashlib
import json

import pytest

from tools.bot_ml.closed_capture_inputs import load_canonical_capture
from tools.bot_ml import analyze_magmaw_trace as analyzer


def capture(tmp_path):
    rows = [{"action": "botauto_diagnose", "payload": {"action": "botauto_diagnose",
             "bots": [{"bot_guid": 30002, "role": "tank", "class_spec": "blood_death_knight"}]}}]
    raw = b"".join((json.dumps(row) + "\n").encode() for row in rows)
    (tmp_path / "report.raw.jsonl").write_bytes(raw)
    report = {"capture_id": "cata_raid_phase1_test_v1",
              "raw_normalized_batch": {"path": "/evicted/original/report.raw.jsonl",
                                       "sha256": hashlib.sha256(raw).hexdigest(), "row_count": 1},
              "development_run": {"requested": True, "native_boss_death_accepted": True},
              "capture_success": False, "combat_analysis": {}}
    (tmp_path / "report.json").write_text(json.dumps(report))
    return report


def test_canonical_review_joins_bound_raw_and_keeps_clear_separate(tmp_path):
    report = capture(tmp_path)
    inputs = load_canonical_capture(tmp_path, report)
    assert inputs["combat_log"] == {}  # absent is not an invented complete stream
    review = analyzer.analyze(tmp_path, env_file=tmp_path/"no-key", expected_route=(),
        run_id="canonical-test", segment_id="magmaw", change_id="test", change_note="",
        baseline_path=None, combat_analysis_path=None, prepare_only=True)
    outcome = review["jev_input"]["state"]["native_gameplay_outcome"]
    assert outcome["native_clear"] is True
    assert outcome["capture_success"] is False
    assert outcome["certification_status"] == "uncertified"
    assert analyzer._actor_identity(inputs["payloads"])["30002"]["class_spec"] == "blood_death_knight"


def test_canonical_capture_rejects_stale_raw(tmp_path):
    report = capture(tmp_path)
    (tmp_path / "report.raw.jsonl").write_text('{}\n')
    with pytest.raises(ValueError, match="hash mismatch"):
        load_canonical_capture(tmp_path, report)


def test_native_mushroom_probe_radius_is_not_spell_radius(tmp_path):
    path = tmp_path / "native.log"
    path.write_text("MagmawWildMushroomNative event=nearby_targets "
                    "destination=1.000,2.000,3.000 probe_radius=12.000 "
                    "native_radius=6.000 target_count=2\n")
    row, = analyzer._native_mushroom_diagnostics(path)
    assert row["radius"] == 12
    assert row["native_radius"] == 6
