import hashlib
import json
from pathlib import Path

from tools.raid_program.capture_timeline_artifacts import write_capture_timeline


def test_real_timeline_writer_binds_artifacts_and_does_not_invent_missing_evidence(tmp_path):
    receipt = write_capture_timeline([], {}, tmp_path / "report.json", raw_sha256="a" * 64)
    assert receipt["generated"] is True
    assert receipt["raw_sha256"] == "a" * 64
    for item in receipt["artifacts"]:
        data = Path(item["path"]).read_bytes()
        assert len(data) == item["bytes"]
        assert hashlib.sha256(data).hexdigest() == item["sha256"]
    summary = json.loads((tmp_path / "report.timeline-summary.json").read_text())
    assert summary["clear_accepted"] is False
    assert summary["window"]["elapsed_seconds"] is None
    assert summary["accounting"]["exact_party_dps"] is None


def test_failed_render_is_not_a_successful_capture_or_an_erased_native_kill(tmp_path, monkeypatch):
    from tools.raid_program import capture_timeline_artifacts as producer

    def fail(*args, **kwargs):
        raise ValueError("invalid timeline input")

    monkeypatch.setattr(producer, "write_capture_timeline", fail)
    report = {
        "classification": "success", "artifact_inventory": [],
        "optimization_acceptance": {"clear_accepted": True,
                                    "repair_edge_accepted": None,
                                    "performance_accepted": None},
    }
    assert producer.attach_capture_timeline([], report, tmp_path / "report.json", raw_sha256="a" * 64) is False
    assert report["capture_success"] is False
    assert report["classification"] == "incomplete_evidence"
    assert report["optimization_acceptance"]["clear_accepted"] is True
    assert report["optimization_acceptance"]["repair_edge_accepted"] is None
    assert report["optimization_acceptance"]["performance_accepted"] is None
