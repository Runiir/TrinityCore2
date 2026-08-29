from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = (
    ROOT
    / "experiments/configs/"
    "cata_raid_magmaw_748d63431c_receipt_tagged_progress_replay_summary_v1.json"
)
SUMMARY_SHA256 = "3e3dac61dcd39c6af8c76abe9c17eb505802acf83cec617e67c33f6d6d9fbebd"


def test_map669_receipt_620_proves_identity_bound_consumed_launch() -> None:
    payload = SUMMARY.read_bytes()
    assert hashlib.sha256(payload).hexdigest() == SUMMARY_SHA256
    summary = json.loads(payload)

    assert summary["schema"] == (
        "cata_raid_magmaw_receipt_tagged_progress_replay_summary_v1"
    )
    assert summary["purpose"] == "fixture_expansion_replay"
    assert summary["source"]["worktree_clean_during_run"] is True
    assert summary["admission"]["gameplay_canary_admitted"] is False
    assert summary["admission"]["gameplay_mutations_allowed"] is False
    assert summary["checkpoint"]["all_ready"] is True
    assert summary["checkpoint"]["release_count"] == 1

    receipt = summary["target_observation"]
    assert receipt["receipt_id"] == 620
    assert receipt["planner_complete"] is True
    assert receipt["planner_path_type"] == 1
    assert receipt["planner_control_fingerprint"] == (
        receipt["second_path_control_fingerprint"]
    )
    assert receipt["direct_two_point_selected"] is False
    assert receipt["direct_two_point_fallback"] is False
    assert receipt["motion_master_generator_type"] == 8
    assert receipt["point_generator_initialized"] is True
    assert receipt["spline_launch_succeeded"] is True
    assert receipt["spline_id"] == 7140
    assert receipt["sample_count"] == 10
    assert receipt["same_receipt_id_in_all_samples"] is True
    assert receipt["same_spline_id_in_all_samples"] is True
    assert receipt["endpoint_distance_start"] > receipt["endpoint_distance_end"]
    assert receipt["endpoint_distance_end"] == 0.0
    assert receipt["terminal_outcome"] == "selected_endpoint_reached"
    assert receipt["selected_platform_compatible_all_samples"] is True
    assert receipt["dropped_sample_count"] == 0

    safety = summary["boss_scope_safety_observation"]
    assert safety["unique_receipt_count"] == 25
    assert safety["planner_floor_conflict_count"] == 0
    assert safety["platform_incompatible_sample_count"] == 0
    assert safety["wrong_floor_drop_observed"] is False
    assert "canary122_exact_floor_conflicting_seq745_mechanism_recurred" in (
        summary["claims"]["unproven"]
    )
