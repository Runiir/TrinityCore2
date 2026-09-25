"""A post-clear bot diagnosis error never overrides a native Magmaw-style clear."""
from __future__ import annotations

from tools.bot_ml.run_live_bot_validation import completion_reason, validation_failure_labels

CLEAR = [{"route_node_id": "bwd.magmaw.encounter", "route_generation": 4}]


def _evidence(**overrides):
    evidence = {"actionable_error_diagnoses": 2, "error_diagnoses": 2, "validation_route_actions": 0,
                "kill_evidence": 4, "boss_kill_evidence": 1, "post_failure_progress": True,
                "manifest_completion_evidence": CLEAR, "real_boss_kill_evidence": CLEAR}
    return {**evidence, **overrides}


def _labels(evidence):
    return validation_failure_labels(0, False, 10, 10, 1184, 10, [], evidence)


def test_errors_after_a_native_clear_do_not_label_the_run():
    labels = _labels(_evidence())
    assert "bot_diagnosis_error" not in labels
    state = {"progress_counters": {"kills": 4, "validation_route_actions": 0}, "progress_total": 5}
    assert completion_reason(all_passed=False, returncode=0, timed_out=False, failure_labels=labels,
                             state=state, evidence=_evidence()) == "validation_route_manifest_complete"


def test_errors_without_a_proven_clear_still_label_the_run():
    for evidence in (_evidence(manifest_completion_evidence=[]), _evidence(real_boss_kill_evidence=[])):
        assert "bot_diagnosis_error" in _labels(evidence)
